"""Cosmos DB Gremlin connector — TinkerPop over WebSocket, with the two
things the SDK will not do for you.

WHY THIS EXISTS
---------------
``gremlin_python.driver.client.Client`` is a fine transport and a poor
citizen of an async web process. Two failures are guaranteed in production
and neither is obvious from the SDK docs.

**The event loop.** The driver builds and drives its own asyncio loop
inside ``submit()``. Called from a running loop it raises "this event loop
is already running"; called under uvloop it fails differently, because the
driver assumes a standard-library loop. The fix is to run every submit on
a worker thread that owns a fresh standard loop, and to close that loop
afterwards (GOTCHAS.md G2).

**The token.** Cosmos authenticates the WebSocket with an access token
passed as the connection password. The token expires roughly hourly; the
client does not refresh it, and the connection does not fail at expiry but
at the next call, as an opaque transport error. The fix is to cache the
client alongside its token expiry and rebuild before the margin runs out
(GOTCHAS.md G1), plus a single retry on a transient-looking failure so a
racing expiry costs one retry rather than one failed request.

DOMAIN-BLIND BY CONSTRUCTION
----------------------------
The connector executes query text and serialises whatever comes back. It
never inspects meaning. Read-only enforcement, limit injection and result
projection arrive as injected callables, so vocabulary stays with the
caller.

DEPENDENCIES
------------
Standard library, plus ``gremlinpython`` loaded on first query.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from azdata.core.config import AzureDataConfig
from azdata.core.envelope import error_envelope
from azdata.core.guardrails import limit_injector, read_only_validator
from azdata.core.optional import load

logger = logging.getLogger(__name__)

# Cosmos data-plane scope. Not the management-plane scope; using the wrong
# one produces a 403 that reads like a missing role assignment.
COSMOS_TOKEN_SCOPE = "https://cosmos.azure.com/.default"

# Substrings that justify rebuilding the client and retrying once. Matched
# against lowercased exception text because the driver wraps transport
# failures in types that carry no status code.
_AUTH_MARKERS = (
    "401", "403", "unauthorized", "unauthori", "forbidden",
    "token", "expired", "authentication",
)
_TRANSPORT_MARKERS = (
    "connection was already closed",
    "connection is closed",
    "connection reset",
    "websocket",
    "transport",
    "broken pipe",
    "eof",
)


@dataclass(frozen=True)
class GremlinTarget:
    """Endpoint coordinates for one graph."""

    endpoint: str
    database: str
    graph: str


class GremlinConnector:
    """Read-only Gremlin execution against a Cosmos DB graph.

    Args:
        resolve_target: Called per query. A callable rather than a value so
            a multi-tenant caller can vary the graph per request.
        credential_provider: Returns a ``TokenCredential``.
        validate_fn: Returns a refusal message or None. Defaults to the
            built-in read-only guard; pass ``None`` explicitly to disable.
        transform_query: Rewrites the query before execution. Defaults to
            limit injection.
        max_rows: Row cap for the default limit injector.
    """

    def __init__(
        self,
        *,
        resolve_target: Callable[[], GremlinTarget],
        credential_provider: Callable[[], Any],
        token_scope: str = COSMOS_TOKEN_SCOPE,
        validate_fn: Callable[[str], str | None] | None = ...,  # type: ignore[assignment]
        transform_query: Callable[[str], str] | None = ...,  # type: ignore[assignment]
        max_rows: int | None = None,
        token_refresh_margin_secs: int = 300,
        not_configured_detail: str = "Gremlin endpoint not configured.",
        error_detail_prefix: str = "Gremlin query failed",
    ) -> None:
        # Ellipsis means "not specified" so that an explicit None can mean
        # "no guard", which a caller enforcing read-only via RBAC wants.
        self._validate_fn = (
            read_only_validator("gremlin") if validate_fn is ... else validate_fn
        )
        self._transform_query = (
            limit_injector("gremlin", max_rows) if transform_query is ...
            else transform_query
        )
        self._resolve_target = resolve_target
        self._credential_provider = credential_provider
        self._token_scope = token_scope
        self._refresh_margin = token_refresh_margin_secs
        self._not_configured_detail = not_configured_detail
        self._error_detail_prefix = error_detail_prefix

        self._client: Any = None
        self._token_expires_on: float = 0.0
        self._lock = asyncio.Lock()
        # Last traversal's status attributes, which is where Cosmos reports
        # the RU charge. Empty until a traversal has run in this process.
        self._last_status_attributes: dict[str, Any] = {}

    @property
    def last_status_attributes(self) -> dict[str, Any]:
        """Status attributes of the most recent traversal, or ``{}``.

        The only place ``x-ms-total-request-charge`` is ever visible: the
        driver hangs it on the result set and the rows carry no trace of
        it. Empty is *unknown*, never zero.
        """
        return dict(self._last_status_attributes)

    @classmethod
    def from_config(
        cls,
        config: AzureDataConfig,
        credential_provider: Callable[[], Any],
        **kwargs,
    ) -> "GremlinConnector":
        """Build from a frozen config. The coordinates are fixed at startup."""
        target = GremlinTarget(
            endpoint=config.gremlin_endpoint,
            database=config.gremlin_database,
            graph=config.gremlin_graph,
        )
        kwargs.setdefault("max_rows", config.max_rows)
        kwargs.setdefault(
            "token_refresh_margin_secs", config.token_refresh_margin_secs
        )
        return cls(
            resolve_target=lambda: target,
            credential_provider=credential_provider,
            **kwargs,
        )

    async def _build_client(self, target: GremlinTarget) -> tuple[Any, float]:
        """Construct a driver client and return it with its token expiry."""
        gclient = load("gremlin_python.driver.client", dist="gremlinpython")
        gserializer = load("gremlin_python.driver.serializer", dist="gremlinpython")

        cred = self._credential_provider()
        # get_token is synchronous and does network I/O; off the loop.
        token_obj = await asyncio.to_thread(cred.get_token, self._token_scope)
        client = gclient.Client(
            url=target.endpoint,
            traversal_source="g",
            username=f"/dbs/{target.database}/colls/{target.graph}",
            password=token_obj.token,
            message_serializer=gserializer.GraphSONSerializersV2d0(),
        )
        return client, float(token_obj.expires_on)

    async def _get_client(
        self, target: GremlinTarget, *, force_refresh: bool = False
    ) -> Any:
        """Return a cached client whose token still has margin left."""
        if not force_refresh and self._client is not None:
            if (self._token_expires_on - time.time()) > self._refresh_margin:
                return self._client

        async with self._lock:
            # Re-check inside the lock: a concurrent caller may have rebuilt.
            if not force_refresh and self._client is not None:
                if (self._token_expires_on - time.time()) > self._refresh_margin:
                    return self._client

            if self._client is not None:
                try:
                    await asyncio.to_thread(self._client.close)
                except Exception as exc:
                    # A failed close must not block the rebuild; the old
                    # socket is being discarded either way.
                    logger.warning("gremlin.client_close_failed: %s", exc)
                self._client = None

            self._client, self._token_expires_on = await self._build_client(target)
            logger.info(
                "gremlin.client_created db=%s graph=%s token_ttl_s=%d",
                target.database, target.graph,
                int(max(0.0, self._token_expires_on - time.time())),
            )
            return self._client

    async def execute(
        self, query: str, /, *, project: Callable[[Any], Any] | None = None
    ) -> str:
        """Run ``query`` and return a JSON string.

        Returns a JSON list of results, or an error envelope. Never raises
        for a query or transport failure — the caller is usually a tool
        surface that must return text.
        """
        target = self._resolve_target()
        if not target.endpoint:
            return error_envelope(self._not_configured_detail)

        if self._validate_fn is not None:
            violation = self._validate_fn(query)
            if violation:
                return error_envelope(violation)

        safe_query = (
            self._transform_query(query) if self._transform_query else query
        )
        logger.info("gremlin.execute: %s", safe_query[:200])

        retried = False
        while True:
            try:
                client = await self._get_client(target)

                def _run() -> Any:
                    """Drive the driver's own loop on a worker thread (G2)."""
                    import asyncio as _aio

                    loop = _aio.new_event_loop()
                    try:
                        _aio.set_event_loop(loop)
                        result_set = client.submit(safe_query)
                        rows = result_set.all().result()
                        # The RU charge lives only here, on the result set,
                        # and is gone once the rows are serialised.
                        return rows, getattr(result_set, "status_attributes", None)
                    finally:
                        loop.close()

                result, attributes = await asyncio.to_thread(_run)
                self._last_status_attributes = (
                    dict(attributes) if isinstance(attributes, Mapping) else {}
                )
                logger.info("gremlin.execute complete: %d results", len(result))
                shaped = project(result) if project is not None else result
                return json.dumps(shaped, default=str)

            except Exception as exc:
                text = str(exc).lower()
                transient = not retried and any(
                    marker in text for marker in _AUTH_MARKERS + _TRANSPORT_MARKERS
                )
                if transient:
                    retried = True
                    logger.warning(
                        "gremlin.transient_failure, rebuilding client: %s",
                        str(exc)[:200],
                    )
                    try:
                        await self._get_client(target, force_refresh=True)
                    except Exception as refresh_exc:
                        logger.exception(
                            "gremlin.client_refresh_failed: %s", refresh_exc
                        )
                    continue

                logger.exception("gremlin.execute failed: %s", exc)
                return error_envelope(
                    f"{self._error_detail_prefix}: {str(exc)[:500]}"
                )

    async def is_healthy(self) -> bool:
        """True when a trivial traversal returns without an error envelope."""
        target = self._resolve_target()
        if not target.endpoint:
            return False
        from azdata.core.envelope import is_error

        return not is_error(await self.execute("g.V().limit(1).count()"))

    async def close(self) -> None:
        """Close the cached client. The credential is not ours to close (G8)."""
        if self._client is not None:
            try:
                await asyncio.to_thread(self._client.close)
            finally:
                self._client = None
                self._token_expires_on = 0.0


__all__ = ["COSMOS_TOKEN_SCOPE", "GremlinConnector", "GremlinTarget"]
