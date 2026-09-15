"""Temporary synchronous adapter for CyberEye callers of the async azdata library."""

from __future__ import annotations

import asyncio
import json
import re
import time
from collections.abc import Mapping
from concurrent.futures import Future, wait
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from threading import Lock, Thread
from typing import Any
from urllib.parse import urlsplit

from azdata import ConnectorConfig, Limits, Policy, QueryRequest, ResourceAddress, connect


@dataclass(frozen=True, slots=True)
class QueryRows:
    columns: tuple[str, ...]
    rows: tuple[tuple[Any, ...], ...]
    client_request_id: str
    elapsed_seconds: float
    truncated: bool = False


def bind_parameters(parameters: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    declarations: list[str] = []
    values: dict[str, Any] = {}
    scalar_types = {bool: "bool", int: "long", float: "real", str: "string"}
    for name, value in parameters.items():
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", name):
            raise ValueError("invalid ADX parameter name")
        if type(value) in scalar_types:
            kind = scalar_types[type(value)]
        elif isinstance(value, datetime):
            kind, value = "datetime", value.isoformat()
        elif isinstance(value, timedelta):
            kind, value = "timespan", str(value)
        elif isinstance(value, (list, tuple, dict, set, frozenset)):
            if isinstance(value, (set, frozenset)):
                value = sorted(value)
            kind, value = "dynamic", json.dumps(value, default=str, allow_nan=False)
        else:
            raise ValueError("unsupported ADX parameter type")
        declarations.append(f"{name}:{kind}")
        values[name] = value
    prologue = "declare query_parameters(" + ", ".join(declarations) + ");\n" if declarations else ""
    return prologue, values


def _mutable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _mutable(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_mutable(item) for item in value]
    return value


class AdxQueryClient:
    def __init__(self, *, endpoint: str, database: str, credential: Any,
                 max_rows: int, timeout_seconds: int, transport: Any = None) -> None:
        self.endpoint, self.database = endpoint, database
        self.limits = Limits(timeout_seconds=timeout_seconds, max_items=max_rows + 1,
                             max_output_bytes=1_048_576, max_attempts=3)
        self._connector = connect(
            "adx", ConnectorConfig(endpoint, ResourceAddress({"database": database}),
                                   (urlsplit(endpoint).hostname or "",)),
            credential=credential, transport=transport,
            policy=Policy("cybereye:telemetry", grants={"query"}, limits=self.limits),
        )
        self._loop = asyncio.new_event_loop()
        self._lock = Lock()
        self._closed = False
        self._pending: set[Future] = set()
        self._thread = Thread(target=self._serve, name="cybereye-azdata", daemon=True)
        self._thread.start()

    def _serve(self) -> None:
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_forever()
            self._loop.run_until_complete(self._loop.shutdown_asyncgens())
            self._loop.run_until_complete(self._loop.shutdown_default_executor())
        finally:
            self._loop.close()

    def query(self, kql: str, parameters: Mapping[str, Any] | None = None, *,
              timeout_seconds: int | None = None) -> QueryRows:
        prologue, values = bind_parameters(parameters or {})
        limits = replace(self.limits, timeout_seconds=min(
            timeout_seconds if timeout_seconds is not None else self.limits.timeout_seconds,
            self.limits.timeout_seconds,
        ))
        request = QueryRequest(dialect="kql", expression=prologue + kql,
                               parameters=values, limits=limits)
        started = time.monotonic()
        with self._lock:
            if self._closed:
                raise RuntimeError("ADX connector is closed")
            future = asyncio.run_coroutine_threadsafe(self._connector.query(request), self._loop)
            self._pending.add(future)
        try:
            result = future.result()
        finally:
            with self._lock:
                self._pending.discard(future)
        if result.status != "success":
            codes = ", ".join(error.code for error in result.errors) or result.status
            error_type = ValueError if result.status in {"denied", "invalid", "unsupported"} else RuntimeError
            raise error_type(f"ADX read failed ({result.status}: {codes})")
        tables = result.metadata.get("columns", ())
        if len(tables) > 1:
            raise RuntimeError("ADX read returned multiple primary tables")
        columns = tuple(column["name"] for column in tables[0]) if tables else ()
        rows = tuple(tuple(_mutable(item.content.data[name]) for name in columns)
                     for item in result.items if item.content is not None)
        return QueryRows(columns, rows, "azdata;" + request.request_id,
                         time.monotonic() - started, result.truncated)

    def health(self) -> dict[str, Any]:
        report: dict[str, Any] = {"cluster_uri": self.endpoint, "database": self.database}
        try:
            result = self.query("print principal = current_principal()")
            report.update(reachable=bool(result.rows), database_exists=bool(result.rows),
                          principal=result.rows[0][0] if result.rows else None)
        except (RuntimeError, ValueError) as exc:
            report.update(reachable=False, error=str(exc))
        return report

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            pending = tuple(self._pending)
        wait(pending)
        try:
            asyncio.run_coroutine_threadsafe(self._connector.aclose(), self._loop).result()
        finally:
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.join()