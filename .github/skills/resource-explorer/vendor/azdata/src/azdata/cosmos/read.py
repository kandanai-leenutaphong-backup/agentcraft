"""Cosmos DB NoSQL connector — a container handle with a breaker and a
health probe that cannot lie.

WHY THIS EXISTS
---------------
Two problems, one of which is a genuine landmine.

**The store must not be the reason startup fails.** A service that cannot
boot without its database cannot be deployed during a database incident.
The pattern here is: boot on an in-memory implementation, probe the real
store, upgrade if it answers. That requires a *bounded* probe.

**The bounded probe is where it goes wrong.** The Cosmos SDK's default
retry policy is nine attempts over roughly thirty seconds, so an unbounded
"is it up" query blocks a readiness endpoint. Wrapping it in
``asyncio.timeout`` fixes that — and the ``except Exception: return False``
that makes the probe non-raising will then happily swallow the
``NameError`` raised when the asyncio import is absent, pinning the
service on its fallback store forever with no error anywhere. The import
below is load-bearing, and ``tests/`` asserts the probe returns True on a healthy
container precisely so that failure cannot recur (GOTCHAS.md G11).

WHAT THIS IS NOT
----------------
Not an ORM and not a repository. It owns connection, resilience and
lifecycle; the caller writes its own queries against ``.container``.

DEPENDENCIES
------------
Standard library, plus ``azure-cosmos`` loaded on first use.
"""

from __future__ import annotations

# Load-bearing: asyncio.timeout bounds the health probe, and the probe's
# bare except would silently swallow the NameError if this were missing.
# See GOTCHAS.md G11 before touching this import.
import asyncio
import logging
from typing import Any

from azdata.core.breaker import CircuitBreaker, CircuitBreakerRegistry
from azdata.core.config import AzureDataConfig
from azdata.core.optional import load

logger = logging.getLogger(__name__)


class CosmosUnavailable(RuntimeError):
    """The store's circuit breaker is open, or the call failed.

    Subclass it per store so a caller can dispatch on the specific store
    while shared code still catches the base.
    """


class CosmosContainer:
    """One Cosmos NoSQL container, with a breaker and a bounded health probe.

    The client and container are injected rather than constructed here, so
    the class is unit-testable with a double and carries no import-time
    dependency on the Azure SDK. Use :meth:`connect` for the normal path.
    """

    def __init__(
        self,
        *,
        client: Any,
        container: Any,
        breaker_name: str,
        unavailable_exc: type[CosmosUnavailable] = CosmosUnavailable,
        failure_threshold: int = 3,
        cooldown_secs: float = 30.0,
    ) -> None:
        self._client = client
        self._container = container
        # Per-instance, not registry-owned, so tests are isolated. Publish it
        # with register_breaker when the process wants health visibility.
        self._breaker = CircuitBreaker(
            breaker_name,
            failure_threshold=failure_threshold,
            cooldown_secs=cooldown_secs,
        )
        self._lock = asyncio.Lock()
        self._unavailable_exc = unavailable_exc

    @classmethod
    def connect(
        cls,
        *,
        endpoint: str,
        database: str,
        container: str,
        credential: Any,
        breaker_name: str = "cosmos",
        **kwargs,
    ) -> "CosmosContainer":
        """Build the async Cosmos client and return a wired container.

        The async client is used deliberately: with the synchronous one,
        every method on an async store would need a thread hop.
        """
        aio = load("azure.cosmos.aio", dist="azure-cosmos")
        client = aio.CosmosClient(url=endpoint, credential=credential)
        container_client = client.get_database_client(database).get_container_client(
            container
        )
        return cls(
            client=client,
            container=container_client,
            breaker_name=breaker_name,
            **kwargs,
        )

    @classmethod
    def from_config(
        cls,
        config: AzureDataConfig,
        credential: Any,
        *,
        database: str,
        container: str,
        breaker_name: str = "cosmos",
        **kwargs,
    ) -> "CosmosContainer":
        kwargs.setdefault("failure_threshold", config.breaker_threshold)
        return cls.connect(
            endpoint=config.cosmos_endpoint,
            database=database,
            container=container,
            credential=credential,
            breaker_name=breaker_name,
            **kwargs,
        )

    @property
    def container(self) -> Any:
        """The container client. Write your own queries against it."""
        return self._container

    @property
    def lock(self) -> asyncio.Lock:
        """Serialises read-modify-write sequences a caller needs atomic."""
        return self._lock

    @property
    def breaker(self) -> CircuitBreaker:
        return self._breaker

    def check_breaker(self) -> None:
        """Raise if the breaker is open. Call before every operation."""
        if self._breaker.is_open():
            raise self._unavailable_exc("Cosmos store temporarily unavailable")

    def ok(self) -> None:
        """Record a successful operation."""
        self._breaker.record_success()

    def fail(self, exc: Exception) -> CosmosUnavailable:
        """Record a failure and return the wrapper to raise.

        Returned rather than raised so the call site can write
        ``raise store.fail(exc)`` and keep the ``__cause__`` chain.
        """
        self._breaker.record_failure()
        wrapper = self._unavailable_exc("Cosmos store temporarily unavailable")
        wrapper.__cause__ = exc
        return wrapper

    async def is_healthy(self, timeout: float = 2.0) -> bool:
        """Probe connectivity, auth and throughput with a bounded query.

        Returns False rather than raising: the caller is usually deciding
        whether to upgrade from a fallback store, and an exception there
        would defeat the point. See G11 for why the bare except is
        dangerous and what guards it.
        """
        try:
            async with asyncio.timeout(timeout):
                async for _ in self._container.query_items(
                    query="SELECT TOP 1 c.id FROM c", parameters=[]
                ):
                    break
            return True
        except TimeoutError:
            # Distinguished from other failures: slow is not the same as
            # unreachable, and only one of them is a firewall.
            logger.warning(
                "cosmos.health_probe_timeout breaker=%s timeout_s=%s",
                self._breaker.name, timeout,
            )
            return False
        except Exception:
            return False

    def register_breaker(self, registry: CircuitBreakerRegistry) -> None:
        """Publish this instance's breaker so a health endpoint can see it."""
        registry.register(self._breaker)

    async def close(self) -> None:
        """Close the Cosmos client. Never the credential (G8)."""
        await self._client.close()


__all__ = ["CosmosContainer", "CosmosUnavailable"]
