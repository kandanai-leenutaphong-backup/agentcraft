"""KQL connector — Fabric Eventhouse and Azure Data Explorer (Kusto).

WHY THIS EXISTS
---------------
The Kusto SDK is synchronous, so every call must leave the event loop or
the process stalls. Beyond that, Eventhouse runs on shared capacity: the
service answers a single query happily and returns 429 when a handful
arrive together, including from other workloads in the same workspace.
Retrying a 429 without bounding concurrency makes it worse.

This connector therefore does three things the SDK does not: it caches one
client per cluster URI, it runs execution through a :class:`ThrottleGate`
so concurrency is bounded and repeated failure trips a breaker, and it
shapes the response into ``{columns, rows}`` with datetimes already
stringified, so the payload survives ``json.dumps`` without a custom
encoder.

DOMAIN-BLIND BY CONSTRUCTION
----------------------------
Query text is the caller's. The connector adds a read-only guard and a row
cap by default, and applies an injected ``project`` hook to the shaped
response before serialising. It never renames a column.

DEPENDENCIES
------------
Standard library, plus ``azure-kusto-data`` loaded on first query.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from azdata.core.breaker import ThrottleGate, get_gate
from azdata.core.config import AzureDataConfig
from azdata.core.envelope import error_envelope
from azdata.core.guardrails import limit_injector, read_only_validator

from azdata.core.optional import load

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class KqlTarget:
    """Cluster query URI plus database name."""

    query_uri: str
    database: str


def shape_kusto_response(response: Any) -> dict[str, list]:
    """Turn a Kusto response into ``{"columns": [...], "rows": [...]}``.

    Columns become ``{name, type}``; rows become dicts keyed by column
    name. Values exposing ``isoformat`` are converted to strings here
    rather than at serialisation time, so the result is plain JSON data
    that any consumer can hold, log or re-serialise.
    """
    primary = response.primary_results[0] if response.primary_results else None
    if primary is None:
        return {"columns": [], "rows": []}

    columns = [{"name": c.column_name, "type": c.column_type} for c in primary.columns]
    rows: list[dict[str, Any]] = []
    for row in primary:
        record: dict[str, Any] = {}
        for col in primary.columns:
            value = row[col.column_name]
            if hasattr(value, "isoformat"):
                value = value.isoformat()
            record[col.column_name] = value
        rows.append(record)
    return {"columns": columns, "rows": rows}


class KqlConnector:
    """Read-only KQL execution behind a concurrency gate.

    Args:
        resolve_target: Called per query, so per-request cluster routing
            works without rebuilding the connector.
        credential_provider: Returns a ``TokenCredential``.
        gate_provider: Async callable returning the :class:`ThrottleGate`
            to bound this capacity. Async because a gate is often created
            lazily inside the running loop.
        sanitize_error: Rewrites the SDK error before it reaches the caller.
            The default envelope already strips URLs; override to keep more
            or less of the Kusto diagnostic.
    """

    def __init__(
        self,
        *,
        resolve_target: Callable[[], KqlTarget],
        credential_provider: Callable[[], Any],
        gate_provider: Callable[[], Awaitable[ThrottleGate]],
        validate_fn: Callable[[str], str | None] | None = ...,  # type: ignore[assignment]
        transform_query: Callable[[str], str] | None = ...,  # type: ignore[assignment]
        max_rows: int | None = None,
        not_configured_detail: str = "KQL endpoint not configured.",
        error_detail_prefix: str = "KQL query failed",
        sanitize_error: Callable[[str], str] | None = None,
    ) -> None:
        self._validate_fn = (
            read_only_validator("kql") if validate_fn is ... else validate_fn
        )
        self._transform_query = (
            limit_injector("kql", max_rows) if transform_query is ...
            else transform_query
        )
        self._resolve_target = resolve_target
        self._credential_provider = credential_provider
        self._gate_provider = gate_provider
        self._not_configured_detail = not_configured_detail
        self._error_detail_prefix = error_detail_prefix
        self._sanitize_error = sanitize_error

        self._clients: dict[str, Any] = {}
        self._lock = asyncio.Lock()
        self._last_gate: ThrottleGate | None = None

    @classmethod
    def from_config(
        cls,
        config: AzureDataConfig,
        credential_provider: Callable[[], Any],
        *,
        gate_name: str = "kql",
        **kwargs,
    ) -> "KqlConnector":
        """Build from a frozen config, sharing the named process-wide gate."""
        target = KqlTarget(
            query_uri=config.kql_query_uri, database=config.kql_database
        )

        async def _gate() -> ThrottleGate:
            return get_gate(
                gate_name,
                max_concurrent=config.max_concurrent,
                failure_threshold=config.breaker_threshold,
                cooldown_secs=config.breaker_cooldown_secs,
                max_cooldown_secs=config.breaker_max_cooldown_secs,
            )

        kwargs.setdefault("max_rows", config.max_rows)
        return cls(
            resolve_target=lambda: target,
            credential_provider=credential_provider,
            gate_provider=_gate,
            **kwargs,
        )

    @property
    def circuit_state(self) -> Any:
        """Breaker state of the last gate used, or None before the first call."""
        return self._last_gate.state if self._last_gate is not None else None

    async def _get_client(self, query_uri: str) -> Any:
        """One client per cluster URI, built once."""
        cached = self._clients.get(query_uri)
        if cached is not None:
            return cached
        async with self._lock:
            if query_uri in self._clients:
                return self._clients[query_uri]
            kusto = load("azure.kusto.data", dist="azure-kusto-data")
            kcsb = kusto.KustoConnectionStringBuilder.with_azure_token_credential(
                query_uri, self._credential_provider()
            )
            client = kusto.KustoClient(kcsb)
            self._clients[query_uri] = client
            return client

    async def execute(
        self, query: str, /, *, project: Callable[[dict], Any] | None = None
    ) -> str:
        """Run ``query`` and return a JSON string.

        ``{"columns": [...], "rows": [...]}`` on success, an error envelope
        otherwise. A 429 is recorded as a throttle event and any other
        failure as a server error, so the breaker sees the difference even
        though both count against it.
        """
        target = self._resolve_target()
        if not target.query_uri or not target.database:
            return error_envelope(self._not_configured_detail)

        if self._validate_fn is not None:
            violation = self._validate_fn(query)
            if violation:
                return error_envelope(violation)

        safe_query = (
            self._transform_query(query) if self._transform_query else query
        )
        logger.info("kql.execute: %s", safe_query[:200])

        gate = await self._gate_provider()
        self._last_gate = gate
        try:
            was_probe = await gate.acquire()
        except Exception as exc:
            # Circuit open. The message is already caller-safe.
            return error_envelope(str(exc))

        try:
            client = await self._get_client(target.query_uri)
            response = await asyncio.to_thread(
                client.execute, target.database, safe_query
            )
            shaped = shape_kusto_response(response)
            await gate.record_success()
            logger.info("kql.execute complete: %d rows", len(shaped["rows"]))
            result = project(shaped) if project is not None else shaped
            return json.dumps(result, default=str)
        except Exception as exc:
            logger.exception("kql.execute failed: %s", exc)
            text = str(exc).lower()
            if "429" in text or "throttl" in text:
                await gate.record_429()
            else:
                await gate.record_server_error()
            detail = (
                self._sanitize_error(str(exc))
                if self._sanitize_error is not None
                else str(exc)[:500]
            )
            return error_envelope(f"{self._error_detail_prefix}: {detail}")
        finally:
            # Must be unconditional: a leaked permit never comes back and
            # the gate blocks for the process lifetime.
            gate.release(was_probe=was_probe)

    async def is_healthy(self) -> bool:
        """True when a trivial query returns without an error envelope."""
        target = self._resolve_target()
        if not target.query_uri or not target.database:
            return False
        from azdata.core.envelope import is_error

        return not is_error(await self.execute("print healthy = 1"))

    async def close(self) -> None:
        """Close every cached Kusto client."""
        for client in self._clients.values():
            close = getattr(client, "close", None)
            if close is not None:
                try:
                    await asyncio.to_thread(close)
                except Exception as exc:
                    logger.warning("kql.client_close_failed: %s", exc)
        self._clients.clear()


__all__ = ["KqlConnector", "KqlTarget", "shape_kusto_response"]
