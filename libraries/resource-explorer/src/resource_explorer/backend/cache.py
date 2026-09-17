"""A TTL cache with single flight, keyed by whatever the caller is repeating.

Adopted from `resource_explorer_api/cache.py`.
See `PROVENANCE.md`.

WHY IT EXISTS
-------------
Opening a use case reads metadata for each of its sources; re-opening it
seconds later asks the same questions again, and the tree, the detail pane
and the preview can each want the same row count. Without a cache one click
becomes three round trips to the same cluster.

WHY SINGLE FLIGHT AND NOT ONLY A TTL
------------------------------------
The frontend expands siblings concurrently. A plain TTL lets N concurrent
misses each start their own read, which is precisely the load the cache was
added to remove. One in-flight call per key, and every other waiter gets its
result.

A returned failure value is cached like any other answer; raised exceptions
are not cached. A dark branch
that re-probes on every keystroke turns a 403 into a rate limit.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable, Hashable
from typing import Any, Literal


class ResultCache:
    """One bounded, deduplicated answer per key.

    The fetch is supplied per call rather than at construction, so one cache
    serves metadata reads, row counts and anything else that is repeated
    within a single expansion.
    """

    def __init__(
        self,
        *,
        ttl_secs: float,
        clock: Callable[[], float] = time.monotonic,
        ttl_origin: Literal["started", "completed"] = "completed",
    ) -> None:
        if ttl_origin not in {"started", "completed"}:
            raise ValueError("unknown_ttl_origin")
        self._ttl = ttl_secs
        self._clock = clock
        self._ttl_origin = ttl_origin
        self._entries: dict[Hashable, tuple[float, Any]] = {}
        self._locks: dict[Hashable, asyncio.Lock] = {}

    async def get(self, key: Hashable, fetch: Callable[[], Awaitable[Any]]) -> Any:
        fresh = self._fresh(key)
        if fresh is not None:
            return fresh[1]
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            # Re-checked inside the lock: the waiter queued behind the
            # in-flight call must serve its result, not start a second.
            fresh = self._fresh(key)
            if fresh is not None:
                return fresh[1]
            started = self._clock()
            value = await fetch()
            stored_at = started if self._ttl_origin == "started" else self._clock()
            self._entries[key] = (stored_at, value)
            return value

    def invalidate(self) -> None:
        self._entries.clear()

    def _fresh(self, key: Hashable) -> tuple[float, Any] | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        stored_at, _ = entry
        if self._clock() - stored_at >= self._ttl:
            return None
        return entry


__all__ = ["ResultCache"]
