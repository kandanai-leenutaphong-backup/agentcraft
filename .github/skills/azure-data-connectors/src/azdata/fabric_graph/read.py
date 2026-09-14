"""Fabric GraphModel connector — GQL over HTTPS, with the retry loop the
service actually requires.

WHY THIS EXISTS
---------------
A Fabric GraphModel query is one HTTP POST, and four distinct things can
come back that are not the answer:

* **429** — capacity throttled. Honour ``Retry-After``, add jitter, cap the
  parsed value so a hostile or wrong header cannot park the process for an
  hour.
* **500 ColdStartTimeout** — the model was not warm. Exponential backoff
  and try again; this is a delay, not a failure. Any other 500 is real.
* **status 02000 with a ``nextPage``** — a partial result. Continue with
  the continuation token and accumulate. Ignoring it returns silently
  truncated data, which is worse than an error.
* **HTTP 200 with a non-zero GQL status code** — the query failed. A
  transport-only error check reports success (GOTCHAS.md G7).

The subtle one is the gate. Waits here are seconds to a minute, and a
retrying call that holds a permit across its own sleep starves every other
query against the same capacity. The permit is released before each sleep
and re-acquired after (GOTCHAS.md G3).

WHY IT RETURNS A DICT
---------------------
Alone among the connectors, ``execute`` returns a ``dict``, not a JSON
string. Every caller projects ``data`` into its own vocabulary before
serialising, so returning a string would force an immediate re-parse. The
dict return is the projection seam.

DEPENDENCIES
------------
Standard library, plus ``httpx`` loaded on first query.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from azdata.core.breaker import ThrottleGate, get_gate
from azdata.core.config import AzureDataConfig
from azdata.core.optional import load
from azdata.core.token import TokenCache

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GraphRetryBudget:
    """Every retry and timeout knob for the executeQuery loop.

    A dataclass rather than constants because these are the numbers an
    operator tunes when capacity changes, and they should be visible in one
    object rather than scattered through a loop.
    """

    http_timeout_secs: float = 100.0
    default_429_wait: int = 5
    max_429_retries: int = 5
    max_coldstart_retries: int = 5
    max_continuation_retries: int = 50
    token_stale_secs: float = 2700.0
    continuation_wait_secs: float = 10.0


def parse_retry_after(headers: Any, default: int) -> int:
    """Read ``Retry-After`` in seconds, bounded to (0, 120].

    Bounded because the header is attacker- or bug-controlled: an
    unbounded value silently converts a throttle into an outage.
    """
    raw = ""
    try:
        raw = headers.get("Retry-After", "")
    except AttributeError:
        pass
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return value if 0 < value <= 120 else default


class GraphConnector:
    """Read-only GQL execution against a Fabric GraphModel.

    Args:
        resolve_url: Called per query, returning the executeQuery URL. An
            empty string means unconfigured.
        token_provider: Async callable returning a bearer token.
        gate_provider: Async callable returning the shared capacity gate.
        budget: Retry and timeout knobs.
        metadata_url_provider: Optional callable for the health probe URL.
    """

    def __init__(
        self,
        *,
        resolve_url: Callable[[], str],
        token_provider: Callable[[], Awaitable[str]],
        gate_provider: Callable[[], Awaitable[ThrottleGate]],
        budget: GraphRetryBudget | None = None,
        not_configured_detail: str = (
            "Fabric GraphModel not configured: set the workspace id and "
            "graph model id."
        ),
        metadata_url_provider: Callable[[], str] | None = None,
    ) -> None:
        self._resolve_url = resolve_url
        self._token_provider = token_provider
        self._gate_provider = gate_provider
        self._budget = budget or GraphRetryBudget()
        self._not_configured_detail = not_configured_detail
        self._metadata_url_provider = metadata_url_provider
        # Last GQL status code seen. None until a query has run: the observe
        # plane reports that absence rather than inventing a success code.
        self._last_query_status_code: str | None = None

    @property
    def last_query_status_code(self) -> str | None:
        """GQL status code of the most recent query, or None before the first.

        HTTP 200 does not mean the query succeeded (G7), so this is the
        code from the body's ``status`` block, not the HTTP status.
        """
        return self._last_query_status_code

    @classmethod
    def from_config(
        cls,
        config: AzureDataConfig,
        credential_provider: Callable[[], Any],
        *,
        gate_name: str = "fabric",
        **kwargs,
    ) -> "GraphConnector":
        """Build from a frozen config, with a Fabric-scoped token cache."""
        tokens = TokenCache(
            credential_provider=credential_provider,
            scope=config.fabric_scope,
            stale_after_secs=config.token_stale_secs,
        )

        async def _gate() -> ThrottleGate:
            return get_gate(
                gate_name,
                max_concurrent=config.max_concurrent,
                failure_threshold=config.breaker_threshold,
                cooldown_secs=config.breaker_cooldown_secs,
                max_cooldown_secs=config.breaker_max_cooldown_secs,
            )

        return cls(
            resolve_url=lambda: config.fabric_graph_url,
            token_provider=tokens.get,
            gate_provider=_gate,
            metadata_url_provider=config.fabric_metadata_url,
            **kwargs,
        )

    async def execute(self, query: str) -> dict[str, Any]:
        """Run ``query``; return ``{columns, data}`` or ``{error, detail}``."""
        url = self._resolve_url()
        if not url:
            return {"error": True, "detail": self._not_configured_detail}

        gate = await self._gate_provider()
        held = {"permit": False, "was_probe": False}
        try:
            held["was_probe"] = await gate.acquire()
            held["permit"] = True
        except Exception as exc:
            return {"error": True, "detail": str(exc)}

        try:
            return await self._execute_inner(query, url, gate, held)
        except Exception as exc:
            logger.exception("graph.execute failed")
            return {"error": True, "detail": str(exc)[:500]}
        finally:
            if held["permit"]:
                gate.release(was_probe=held["was_probe"])
                held["permit"] = False

    async def _execute_inner(
        self, query: str, url: str, gate: ThrottleGate, held: dict
    ) -> dict[str, Any]:
        """The retry loop: throttling, cold start, and continuation paging."""
        budget = self._budget
        httpx = load("httpx", dist="httpx")

        token = await self._token_provider()
        token_acquired_at = time.monotonic()

        retries_429 = 0
        retries_coldstart = 0
        retries_continuation = 0
        continuation_token: str | None = None
        rows: list[dict[str, Any]] = []
        columns: list[dict[str, Any]] | None = None

        # One bound covering every retry class, so a pathological mix
        # cannot loop indefinitely.
        max_attempts = (
            budget.max_429_retries
            + budget.max_coldstart_retries
            + budget.max_continuation_retries
            + 2
        )

        async with httpx.AsyncClient(timeout=budget.http_timeout_secs) as client:
            for _ in range(max_attempts):
                payload: dict[str, Any] = {"query": query}
                if continuation_token:
                    payload["continuationToken"] = continuation_token

                response = await client.post(
                    url,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                )

                if response.status_code == 429:
                    retries_429 += 1
                    await gate.record_429()
                    if retries_429 > budget.max_429_retries:
                        return {
                            "error": True,
                            "detail": "Capacity exhausted (HTTP 429).",
                        }
                    wait = parse_retry_after(
                        response.headers, budget.default_429_wait
                    ) * random.uniform(0.75, 1.25)
                    logger.warning(
                        "graph.429 attempt=%d/%d wait=%.0fs",
                        retries_429, budget.max_429_retries, wait,
                    )
                    await self._sleep_without_permit(gate, held, wait)
                    continue

                if response.status_code == 500:
                    body = _json_or_empty(response)
                    if body.get("errorCode") != "ColdStartTimeout":
                        await gate.record_server_error()
                        return {
                            "error": True,
                            "detail": f"GraphModel 500: {response.text[:300]}",
                        }
                    retries_coldstart += 1
                    if retries_coldstart > budget.max_coldstart_retries:
                        return {
                            "error": True,
                            "detail": (
                                "GraphModel cold start exceeded the retry "
                                "budget. Try again shortly."
                            ),
                        }
                    wait = min(
                        10 * (2 ** (retries_coldstart - 1)), 60
                    ) * random.uniform(0.75, 1.25)
                    logger.warning(
                        "graph.coldstart attempt=%d/%d wait=%.0fs",
                        retries_coldstart, budget.max_coldstart_retries, wait,
                    )
                    # A cold-start restart invalidates any partial paging.
                    continuation_token = None
                    await self._sleep_without_permit(gate, held, wait)
                    if time.monotonic() - token_acquired_at > budget.token_stale_secs:
                        token = await self._token_provider()
                        token_acquired_at = time.monotonic()
                    continue

                if response.status_code != 200:
                    await gate.record_server_error()
                    return {
                        "error": True,
                        "detail": (
                            f"GraphModel HTTP {response.status_code}: "
                            f"{response.text[:300]}"
                        ),
                    }

                body = _json_or_empty(response)
                if not body:
                    return {
                        "error": True,
                        "detail": "GraphModel returned a non-JSON payload.",
                    }

                # HTTP 200 does not mean the query succeeded (G7).
                status = body.get("status") or {}
                code = status.get("code", "")
                result = body.get("result") or {}
                if code:
                    self._last_query_status_code = code

                if code and code not in ("00000", "02000"):
                    cause = status.get("cause") or {}
                    detail = (
                        cause.get("description")
                        or status.get("description")
                        or f"GQL error code {code}"
                    )
                    return {"error": True, "detail": f"GQL {code}: {detail[:300]}"}

                page_columns = result.get("columns") or []
                if columns is None and page_columns:
                    columns = page_columns
                rows.extend(result.get("data") or [])

                if code == "02000" and result.get("nextPage"):
                    retries_continuation += 1
                    if retries_continuation > budget.max_continuation_retries:
                        return {
                            "error": True,
                            "detail": "GQL continuation budget exhausted.",
                        }
                    continuation_token = result["nextPage"]
                    logger.info(
                        "graph.continuation attempt=%d/%d",
                        retries_continuation, budget.max_continuation_retries,
                    )
                    await self._sleep_without_permit(
                        gate, held, budget.continuation_wait_secs
                    )
                    continue

                await gate.record_success()
                return {"columns": columns or [], "data": rows}

        return {"error": True, "detail": "GQL exhausted all retry attempts."}

    async def _sleep_without_permit(
        self, gate: ThrottleGate, held: dict, wait: float
    ) -> None:
        """Release the permit, sleep, re-acquire.

        Holding a permit across a minute-long backoff starves every other
        caller of the same capacity (G3).
        """
        try:
            gate.release(was_probe=held["was_probe"])
        finally:
            held["permit"] = False
            held["was_probe"] = False
        await asyncio.sleep(wait)
        held["was_probe"] = await gate.acquire()
        held["permit"] = True

    async def is_healthy(self) -> bool:
        """True when the GraphModel metadata endpoint answers 200."""
        if self._metadata_url_provider is None:
            return False
        url = self._metadata_url_provider()
        if not url:
            return False
        try:
            httpx = load("httpx", dist="httpx")
            token = await self._token_provider()
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.get(
                    url, headers={"Authorization": f"Bearer {token}"}
                )
                return response.status_code == 200
        except Exception:
            # A health probe reports, it does not raise.
            return False


def _json_or_empty(response: Any) -> dict:
    """Parse a JSON body, returning {} rather than raising on garbage."""
    try:
        parsed = response.json()
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


__all__ = ["GraphConnector", "GraphRetryBudget", "parse_retry_after"]
