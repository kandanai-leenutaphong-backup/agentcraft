"""Bounded, read-only access to the configured telemetry table."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import azdata
from azdata import ConnectorConfig, Limits, Policy, QueryRequest, ResourceAddress, connect

from ..config import settings
from ..models import QueryResponse

# User/model-authored KQL is one read-only pipeline rooted at the one allowed
# table. Management commands and data exfiltration plugins never cross this boundary.
_FORBIDDEN = re.compile(
    r"(?m)(^\s*\.|[\s|;](set\b|let\b|declare\b|externaldata\b|evaluate\b|invoke\b|ingest\b|"
    r"execute\b|http_request\b|python\b|sql_request\b))",
    re.IGNORECASE,
)
#: Built from settings so a new telemetry source is a config change, not a code change.
_ROOT = re.compile(r"^\s*(?:" + "|".join(re.escape(name) for name in settings.tables) + r")\b",
                   re.IGNORECASE)
_ROOT_NAMES = " or ".join(settings.tables)
MAX_CELL_CHARS = 4_000
MAX_RESULT_BYTES = 256_000


class ReadOnlyAdx:
    def __init__(self, *, credential: Any, transport: Any = None) -> None:
        self.connector = connect("adx", ConnectorConfig(
            settings.adx_cluster_uri, ResourceAddress({"database": settings.adx_database}),
            (urlsplit(settings.adx_cluster_uri).hostname or "",)),
            credential=credential, transport=transport,
            policy=Policy("investigation:telemetry", grants={"query"}, limits=Limits(
                timeout_seconds=settings.query_timeout_seconds, max_items=settings.max_rows + 1,
                max_output_bytes=1_048_576, max_attempts=3)))
        self._transport_kind = "injected" if transport is not None else "native"
        self._query_metrics = {"submitted": 0, "completed": 0, "known_attempts": 0,
                               "unknown_attempt_queries": 0}

    async def aclose(self) -> None:
        await self.connector.aclose()

    def library_identity(self) -> dict[str, Any]:
        package_root = Path(azdata.__file__).resolve().parent
        sources = {path.relative_to(package_root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                   for path in package_root.rglob("*.py")}
        distribution = importlib.metadata.distribution("azdata")
        direct_url = json.loads(distribution.read_text("direct_url.json") or "{}")
        editable = bool(direct_url.get("dir_info", {}).get("editable", False))
        return {
            "distribution": "azdata", "version": distribution.version,
            "source_sha256": hashlib.sha256(json.dumps(sources, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
            "import_origin": str(package_root / "__init__.py"), "editable": editable,
            "wheel_install": bool(distribution.read_text("WHEEL")) and not editable
                and Path(distribution.locate_file("azdata/__init__.py")).resolve() == package_root / "__init__.py",
            "transport": self._transport_kind, "query_metrics": dict(self._query_metrics),
        }

    async def health(self) -> dict[str, Any]:
        report: dict[str, Any] = {"cluster_uri": settings.adx_cluster_uri, "database": settings.adx_database}
        try:
            result = await self._read("print principal = current_principal()", {}, 1)
            report.update(reachable=bool(result.rows), database_exists=bool(result.rows),
                          principal=result.rows[0][0] if result.rows else None)
        except (RuntimeError, ValueError) as error:
            report.update(reachable=False, error=str(error))
        return report

    @staticmethod
    def _bounded_rows(raw_rows: Any, limit: int) -> tuple[list[list[Any]], bool]:
        rows: list[list[Any]] = []
        used = 0
        truncated = len(raw_rows) > limit
        for raw in raw_rows[:limit]:
            row: list[Any] = []
            for value in raw:
                if isinstance(value, str) and len(value) > MAX_CELL_CHARS:
                    value = value[:MAX_CELL_CHARS] + "…[cell truncated]"
                    truncated = True
                cell_bytes = len(json.dumps(value, default=str).encode("utf-8"))
                if used + cell_bytes > MAX_RESULT_BYTES:
                    truncated = True
                    return rows, truncated
                used += cell_bytes
                row.append(value)
            rows.append(row)
        return rows, truncated

    async def query(self, kql: str, max_rows: int = 100) -> QueryResponse:
        text = kql.strip()
        if not _ROOT.match(text):
            raise ValueError(f"query must start with {_ROOT_NAMES}")
        if ";" in text or _FORBIDDEN.search(text):
            raise ValueError("query contains a forbidden command or plugin")
        if type(max_rows) is not int or max_rows < 1:
            raise ValueError("max_rows must be a positive integer")
        limit = min(max_rows, settings.max_rows)
        return await self._read(text, {}, limit)

    async def parameterized(self, kql: str, params: dict[str, Any], max_rows: int = 100) -> QueryResponse:
        if not _ROOT.match(kql.strip()) or ";" in kql or _FORBIDDEN.search(kql):
            raise ValueError(f"query must be one read-only {_ROOT_NAMES} pipeline")
        if type(max_rows) is not int or max_rows < 1:
            raise ValueError("max_rows must be a positive integer")
        limit = min(max_rows, settings.max_rows)
        return await self._read(kql.strip(), params, limit)

    async def _read(self, kql: str, params: dict[str, Any], limit: int) -> QueryResponse:
        request = QueryRequest(dialect="kql", expression=f"{kql}\n| take {limit + 1}", parameters=params)
        started = time.monotonic()
        result = None
        self._query_metrics["submitted"] += 1
        try:
            result = await self.connector.query(request)
        finally:
            self._query_metrics["completed"] += 1
            attempts = result.metrics.get("attempts") if result is not None else None
            if type(attempts) is int and attempts >= 0:
                self._query_metrics["known_attempts"] += attempts
            else:
                self._query_metrics["unknown_attempt_queries"] += 1
        if result.status != "success":
            code = ", ".join(error.code for error in result.errors) or result.status
            error_type = ValueError if result.status in {"denied", "invalid", "unsupported"} else RuntimeError
            raise error_type(f"ADX read failed ({result.status}: {code})")
        tables = result.metadata.get("columns", ())
        if len(tables) > 1:
            raise RuntimeError("ADX read returned multiple primary tables")
        columns = [column["name"] for column in tables[0]] if tables else []
        contents = (item.content.to_native() for item in result.items if item.content is not None)
        raw_rows = [[row[name] for name in columns] for row in contents]
        rows, truncated = self._bounded_rows(raw_rows, limit)
        return QueryResponse(
            columns=columns, rows=rows, row_count=len(rows), truncated=truncated or result.truncated,
            max_rows=limit, elapsed_ms=round((time.monotonic() - started) * 1000),
            client_request_id="azdata;" + request.request_id,
        )
