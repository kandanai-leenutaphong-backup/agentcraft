"""Bounded, read-only access to the configured telemetry table."""

from __future__ import annotations

import json
import re
from typing import Any

from ..config import settings
from ..models import QueryResponse
from .azdata_client import AdxQueryClient

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
    def __init__(self, *, credential: Any) -> None:
        self.connector = AdxQueryClient(
            endpoint=settings.adx_cluster_uri,
            database=settings.adx_database,
            max_rows=settings.max_rows,
            timeout_seconds=settings.query_timeout_seconds,
            credential=credential,
        )

    def close(self) -> None:
        self.connector.close()

    def health(self) -> dict[str, Any]:
        return self.connector.health()

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

    def query(self, kql: str, max_rows: int = 100) -> QueryResponse:
        text = kql.strip()
        if not _ROOT.match(text):
            raise ValueError(f"query must start with {_ROOT_NAMES}")
        if ";" in text or _FORBIDDEN.search(text):
            raise ValueError("query contains a forbidden command or plugin")
        if type(max_rows) is not int or max_rows < 1:
            raise ValueError("max_rows must be a positive integer")
        limit = min(max_rows, settings.max_rows)
        bounded = f"{text}\n| take {limit + 1}"
        result = self.connector.query(bounded, timeout_seconds=settings.query_timeout_seconds)
        rows, truncated = self._bounded_rows(result.rows, limit)
        return QueryResponse(
            columns=list(result.columns),
            rows=rows,
            row_count=len(rows),
            truncated=truncated or getattr(result, "truncated", False),
            max_rows=limit,
            elapsed_ms=round(result.elapsed_seconds * 1000),
            client_request_id=result.client_request_id,
        )

    def parameterized(self, kql: str, params: dict[str, Any], max_rows: int = 100) -> QueryResponse:
        if not _ROOT.match(kql.strip()) or ";" in kql or _FORBIDDEN.search(kql):
            raise ValueError(f"query must be one read-only {_ROOT_NAMES} pipeline")
        if type(max_rows) is not int or max_rows < 1:
            raise ValueError("max_rows must be a positive integer")
        limit = min(max_rows, settings.max_rows)
        result = self.connector.query(
            f"{kql.strip()}\n| take {limit + 1}", params,
            timeout_seconds=settings.query_timeout_seconds,
        )
        rows, truncated = self._bounded_rows(result.rows, limit)
        return QueryResponse(
            columns=list(result.columns), rows=rows,
            row_count=len(rows), truncated=truncated or getattr(result, "truncated", False), max_rows=limit,
            elapsed_ms=round(result.elapsed_seconds * 1000),
            client_request_id=result.client_request_id,
        )
