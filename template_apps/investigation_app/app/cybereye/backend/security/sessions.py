"""Per-principal chat sessions and scan results.

Both stores answered every caller before this change: `SessionStore.create()` recorded no
owner, `chat` resolved a session from a posted identifier alone, and `last_scan` was one
process-wide slot that the next caller's evidence lookup read. Any authenticated caller could
therefore continue another caller's conversation and read another caller's scan result by
guessing or replaying an identifier.

Ownership is now part of the lookup, not a check bolted after it. A caller who is not the
owner gets the same ``None`` as a caller asking for a session that never existed, so the
identifier space cannot be probed for which sessions are real.

None of this claims the telemetry is per-caller. The replay corpus is shared, historical, and
readable by every authenticated caller by design. What is owned here is what a caller
*created*: their conversation thread and their scan result.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass(slots=True)
class ChatSession:
    """One conversation thread, bound to the principal that created it."""

    owner_id: str
    previous_response_id: str | None = None
    agent_version_key: str = ""
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    touched: float = field(default_factory=time.monotonic)


class SessionStore:
    """Bounded, idle-expiring, owner-bound chat sessions.

    In-process only: a restart drops every session, and a second replica has none of them.
    That is a usability property, not a security one — a session is a conversation thread, and
    losing it costs a caller their history, not their access.
    """

    def __init__(self, *, max_sessions: int = 256, idle_seconds: float = 12 * 3600.0) -> None:
        self._sessions: OrderedDict[str, ChatSession] = OrderedDict()
        self._max_sessions = max_sessions
        self._idle_seconds = idle_seconds

    def create(self, owner_id: str) -> str:
        """Open a session owned by ``owner_id``. An empty owner is a programming error."""
        if not owner_id:
            raise ValueError("a session needs an owner")
        self._expire()
        session_id = uuid.uuid4().hex
        self._sessions[session_id] = ChatSession(owner_id=owner_id)
        while len(self._sessions) > self._max_sessions:
            self._sessions.popitem(last=False)
        return session_id

    def get(self, session_id: str, owner_id: str) -> ChatSession | None:
        """Resolve a session for its owner, or ``None``.

        Someone else's session and a session that does not exist are the same answer on
        purpose: distinguishing them turns the identifier space into a directory.
        """
        session = self._sessions.get(session_id)
        if session is None:
            return None
        if time.monotonic() - session.touched > self._idle_seconds:
            del self._sessions[session_id]
            return None
        if not owner_id or session.owner_id != owner_id:
            return None
        session.touched = time.monotonic()
        self._sessions.move_to_end(session_id)
        return session

    def _expire(self) -> None:
        cutoff = time.monotonic() - self._idle_seconds
        for session_id in [key for key, item in self._sessions.items() if item.touched < cutoff]:
            del self._sessions[session_id]

    def __len__(self) -> int:
        return len(self._sessions)


class OwnedCache(Generic[T]):
    """Bounded last-value-per-owner cache.

    The scan cache it holds is a convenience, never a source of truth: an evidence lookup that
    misses re-derives the situation from the window the caller supplies, because the scan is
    deterministic. So a miss costs a query and never leaks, and a caller can only ever hit
    their own entry.
    """

    def __init__(self, *, max_owners: int = 64) -> None:
        self._values: OrderedDict[str, T] = OrderedDict()
        self._max_owners = max_owners

    def put(self, owner_id: str, value: T) -> None:
        if not owner_id:
            raise ValueError("a cached value needs an owner")
        self._values[owner_id] = value
        self._values.move_to_end(owner_id)
        while len(self._values) > self._max_owners:
            self._values.popitem(last=False)

    def get(self, owner_id: str) -> T | None:
        if not owner_id:
            return None
        value = self._values.get(owner_id)
        if value is not None:
            self._values.move_to_end(owner_id)
        return value

    def __len__(self) -> int:
        return len(self._values)
