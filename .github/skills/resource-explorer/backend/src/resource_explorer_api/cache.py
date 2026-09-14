"""A TTL cache with single flight, keyed by whatever the caller is repeating.

WHY IT EXISTS
-------------
Expanding a resource group lists its resources; each of the type groups under
it then filters that same listing, and a resource node under those needs the
same row again to know its type. Without a cache, opening one group and its
twelve type groups costs thirteen identical Resource Graph queries.

WHY SINGLE FLIGHT AND NOT ONLY A TTL
------------------------------------
The frontend expands siblings concurrently. A plain TTL lets N concurrent
misses each start their own listing, which is precisely the load the cache was
added to remove. One in-flight call per key, and every other waiter gets its
result.

A failure is cached like any other answer, for the same TTL. A dark branch
that re-probes on every keystroke turns a 403 into a rate limit.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable, Hashable
from typing import Any


class ResultCache:
    """One bounded, deduplicated answer per key.

    The fetch is supplied per call rather than at construction, so one cache
    serves resource-group listings, cluster URI lookups and anything else that
    is repeated within a single tree walk.
    """

    def __init__(
        self,
        *,
        ttl_secs: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ttl = ttl_secs
        self._clock = clock
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
            value = await fetch()
            self._entries[key] = (self._clock(), value)
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
