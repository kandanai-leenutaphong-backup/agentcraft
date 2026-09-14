"""Circuit breaker and throttle gate — the two things that keep a shared
capacity from being taken down by its own clients.

WHY THIS EXISTS
---------------
A cloud data service fails in two ways that need opposite responses.

**It is down.** Every call will fail. Retrying costs latency on every
request and prolongs the outage. The answer is a circuit breaker: count
consecutive failures, trip, fail fast, and let exactly one probe through
after a cooldown to test recovery.

**It is busy.** Calls succeed but the capacity is shared and finite —
Fabric bills concurrency against a fixed capacity unit, and eight parallel
queries from one process will throttle a whole workspace including the
background jobs nobody is watching. The answer is a semaphore, not a
breaker.

:class:`ThrottleGate` composes both, because a connector needs both and
they interact: the half-open probe must *bypass* the semaphore. If the
probe queued behind saturated capacity, recovery detection would depend on
load, and a busy service could never be observed to have recovered.

DOMAIN-BLIND BY CONSTRUCTION
----------------------------
The breaker owns only the state machine. It does not retry, does not
choose a fallback, and does not know what it is protecting. Those are the
caller's decisions.

THREAD SAFETY
-------------
``threading.Lock``, not ``asyncio.Lock``: transitions are a counter and a
timestamp compare with no await point, and they are made from both async
code and SDK calls running in worker threads.

DEPENDENCIES
------------
Standard library only.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from enum import Enum

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """CLOSED: pass through. OPEN: fail fast. HALF_OPEN: one probe allowed."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half-open"


class ThrottleError(RuntimeError):
    """Raised when the gate refuses a call because the circuit is open.

    The message is caller-visible — it reaches agent transcripts and user
    interfaces — so it names no internal service and carries a retry hint
    instead of jargon.
    """

    def __init__(self, retry_after: int) -> None:
        self.retry_after = retry_after
        super().__init__(
            f"Data service temporarily unavailable - retry in {retry_after}s"
        )


class CircuitBreaker:
    """Closed -> Open -> Half-Open -> Closed, with exponential re-open backoff.

    Args:
        name: Identifier used in logs and in the registry.
        failure_threshold: Consecutive failures that trip the breaker.
        cooldown_secs: Time in OPEN before the first probe is allowed.
        max_cooldown_secs: Ceiling for the doubling applied on probe failure.
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 3,
        cooldown_secs: float = 60.0,
        max_cooldown_secs: float = 300.0,
    ) -> None:
        self._name = name
        self._failure_threshold = failure_threshold
        self._base_cooldown = cooldown_secs
        self._max_cooldown = max_cooldown_secs

        self._state = CircuitState.CLOSED
        self._consecutive_failures = 0
        self._open_until = 0.0
        self._current_cooldown = cooldown_secs
        self._probe_allowed = True

        self._lock = threading.Lock()

    @property
    def name(self) -> str:
        return self._name

    @property
    def state(self) -> CircuitState:
        return self._state

    def is_open(self) -> bool:
        """True when the call should be rejected.

        Side effect: expires the cooldown (OPEN -> HALF_OPEN) and grants the
        single probe. Granting inside the check is what makes the grant
        atomic; a separate ``try_probe()`` would race under concurrency.
        """
        with self._lock:
            if self._state is CircuitState.CLOSED:
                return False

            if self._state is CircuitState.OPEN:
                if time.monotonic() < self._open_until:
                    return True
                self._state = CircuitState.HALF_OPEN
                self._probe_allowed = True
                logger.info(
                    "circuit_breaker.half_open name=%s cooldown_s=%.0f",
                    self._name, self._current_cooldown,
                )

            if self._state is CircuitState.HALF_OPEN:
                if self._probe_allowed:
                    self._probe_allowed = False
                    return False
                return True

            return True

    def record_success(self) -> None:
        """Clear the failure count; close the breaker if this was the probe."""
        with self._lock:
            self._consecutive_failures = 0
            if self._state is CircuitState.HALF_OPEN:
                self._state = CircuitState.CLOSED
                self._current_cooldown = self._base_cooldown
                logger.info("circuit_breaker.closed name=%s", self._name)

    def record_failure(self) -> None:
        """Count a failure; trip on threshold, or re-open with doubled cooldown."""
        with self._lock:
            self._consecutive_failures += 1

            if self._state is CircuitState.HALF_OPEN:
                self._current_cooldown = min(
                    self._current_cooldown * 2, self._max_cooldown
                )
                self._open_until = time.monotonic() + self._current_cooldown
                self._state = CircuitState.OPEN
                logger.warning(
                    "circuit_breaker.reopened name=%s cooldown_s=%.0f",
                    self._name, self._current_cooldown,
                )
            elif (
                self._state is CircuitState.CLOSED
                and self._consecutive_failures >= self._failure_threshold
            ):
                self._open_until = time.monotonic() + self._current_cooldown
                self._state = CircuitState.OPEN
                logger.warning(
                    "circuit_breaker.opened name=%s failures=%d cooldown_s=%.0f",
                    self._name, self._consecutive_failures, self._current_cooldown,
                )

    def reset(self) -> None:
        """Force back to CLOSED. Manual recovery and tests."""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._consecutive_failures = 0
            self._open_until = 0.0
            self._current_cooldown = self._base_cooldown
            self._probe_allowed = True

    def status(self) -> dict:
        """Diagnostic dict for a health endpoint."""
        with self._lock:
            seconds_until_probe = None
            if self._state is CircuitState.OPEN:
                seconds_until_probe = round(
                    max(0.0, self._open_until - time.monotonic()), 1
                )
            return {
                "name": self._name,
                "state": self._state.value,
                "consecutive_failures": self._consecutive_failures,
                "cooldown_secs": self._current_cooldown,
                "failure_threshold": self._failure_threshold,
                "seconds_until_probe": seconds_until_probe,
            }


class CircuitBreakerRegistry:
    """Named breakers, so a health endpoint can report all of them at once."""

    def __init__(self) -> None:
        self._breakers: dict[str, CircuitBreaker] = {}
        self._lock = threading.Lock()

    def get_or_create(self, name: str, **kwargs) -> CircuitBreaker:
        """Return the breaker for ``name``; first caller's kwargs win."""
        existing = self._breakers.get(name)
        if existing is not None:
            return existing
        with self._lock:
            if name not in self._breakers:
                self._breakers[name] = CircuitBreaker(name, **kwargs)
            return self._breakers[name]

    def get(self, name: str) -> CircuitBreaker | None:
        return self._breakers.get(name)

    def register(self, breaker: CircuitBreaker) -> None:
        """Publish an externally constructed breaker under its own name.

        Per-instance breakers keep tests isolated; this is how they become
        visible to a health endpoint without the caller writing into a
        private dictionary.
        """
        with self._lock:
            self._breakers[breaker.name] = breaker

    def all_statuses(self) -> dict[str, dict]:
        return {name: cb.status() for name, cb in self._breakers.items()}

    def reset_all(self) -> None:
        for cb in self._breakers.values():
            cb.reset()


# Process-wide registry. Connectors publish here so one health endpoint can
# report every dependency without being told about each in advance.
registry = CircuitBreakerRegistry()


class ThrottleGate:
    """Concurrency semaphore plus circuit breaker for one shared capacity.

    Usage is strictly paired::

        was_probe = await gate.acquire()      # raises ThrottleError if open
        try:
            ...
            await gate.record_success()
        finally:
            gate.release(was_probe=was_probe)

    ``release`` must run in a ``finally``. A leaked permit is permanent:
    the semaphore never recovers and every later call blocks forever.
    """

    def __init__(
        self,
        name: str = "azdata",
        *,
        max_concurrent: int = 2,
        failure_threshold: int = 3,
        cooldown_secs: float = 60.0,
        max_cooldown_secs: float = 300.0,
    ) -> None:
        # max(1, ...) — a misconfigured 0 would build a permanently
        # deadlocked semaphore (GOTCHAS.md G6).
        self._semaphore = asyncio.Semaphore(max(1, max_concurrent))
        self._breaker = CircuitBreaker(
            name,
            failure_threshold=failure_threshold,
            cooldown_secs=cooldown_secs,
            max_cooldown_secs=max_cooldown_secs,
        )

    @property
    def state(self) -> CircuitState:
        return self._breaker.state

    @property
    def breaker(self) -> CircuitBreaker:
        """The composed breaker, for registry publication."""
        return self._breaker

    async def acquire(self) -> bool:
        """Take a permit. Returns True when this call is the recovery probe.

        Raises:
            ThrottleError: The circuit is open.
        """
        if self._breaker.is_open():
            raise ThrottleError(int(self._breaker.status()["seconds_until_probe"] or 1))

        # The breaker admitted this caller during HALF_OPEN, so it is the
        # single probe: bypass the semaphore, or recovery detection would
        # queue behind saturated capacity and never happen under load.
        if self._breaker.state is CircuitState.HALF_OPEN:
            return True

        await self._semaphore.acquire()

        # Re-check: the circuit may have tripped while this call was queued.
        if self._breaker.is_open():
            self._semaphore.release()
            raise ThrottleError(int(self._breaker.status()["seconds_until_probe"] or 1))
        return False

    def release(self, *, was_probe: bool = False) -> None:
        """Return the permit. A probe never took one, so it releases nothing."""
        if not was_probe:
            self._semaphore.release()

    async def record_success(self) -> None:
        self._breaker.record_success()

    async def record_429(self) -> None:
        """A throttling response is a failure for breaker purposes."""
        self._breaker.record_failure()

    async def record_server_error(self) -> None:
        self._breaker.record_failure()

    def status(self) -> dict:
        base = self._breaker.status()
        base["semaphore_available"] = self._semaphore._value  # noqa: SLF001
        return base


_gates: dict[str, ThrottleGate] = {}
_gate_lock = threading.Lock()


def get_gate(name: str = "azdata", **kwargs) -> ThrottleGate:
    """Return the named process-wide gate, creating and publishing it once.

    Named rather than global because two capacities fail independently: a
    saturated Eventhouse must not close the gate on a healthy search
    service.
    """
    existing = _gates.get(name)
    if existing is not None:
        return existing
    with _gate_lock:
        if name not in _gates:
            gate = ThrottleGate(name, **kwargs)
            registry.register(gate.breaker)
            _gates[name] = gate
        return _gates[name]


def reset_gates() -> None:
    """Drop every cached gate. Tests only."""
    with _gate_lock:
        _gates.clear()


__all__ = [
    "CircuitBreaker",
    "CircuitBreakerRegistry",
    "CircuitState",
    "ThrottleError",
    "ThrottleGate",
    "get_gate",
    "registry",
    "reset_gates",
]
