"""One-time sign-in claims and token-bounded serialized session records."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Callable, Mapping

from ._errors import AuthError
from ._signin import SignInFlow, constant_time_equals, new_session_id, session_lookup_key
from ._store import RecordStore

logger = logging.getLogger(__name__)

_FLOW_TOKEN_MIN = 16
_FLOW_TOKEN_MAX = 128
_FLOW_TOKEN = re.compile(r"^[A-Za-z0-9_-]+$")


def _well_formed_flow_token(value: str) -> bool:
    return (
        isinstance(value, str)
        and _FLOW_TOKEN_MIN <= len(value) <= _FLOW_TOKEN_MAX
        and bool(_FLOW_TOKEN.match(value))
    )


def _now() -> datetime:
    return datetime.now(timezone.utc)


class SessionService:
    """Store host-serialized identities without interpreting or authorizing them.

    Stores enforce read expiry and atomic consumption. Store failures propagate so the
    host can refuse using its own transport and logging policy. ``clock`` returns UTC
    aware datetimes; the host supplies stores, flow TTL and the session lifetime ceiling.
    """

    def __init__(
        self,
        *,
        store: RecordStore,
        flow_store: RecordStore,
        max_lifetime: timedelta,
        clock: Callable[[], datetime] = _now,
    ) -> None:
        self._store = store
        self._flows = flow_store
        self._max_lifetime = max_lifetime
        self._clock = clock

    async def start_flow(self, flow: SignInFlow, *, ttl: timedelta) -> None:
        await self._flows.put(flow.flow_id, flow.to_record(), self._clock() + ttl)

    async def claim_flow(self, flow_id: str, state: str) -> dict[str, str] | None:
        """Consume once, including on a state mismatch; malformed inputs touch no store."""
        if not _well_formed_flow_token(flow_id) or not _well_formed_flow_token(state):
            return None
        record = await self._flows.consume(flow_id)
        if record is None:
            return None
        if not constant_time_equals(record.get("state", ""), state):
            logger.warning("auth.signin.state_mismatch")
            return None
        return record

    async def create(
        self, identity: Mapping[str, str], *, token_expires_at: datetime,
    ) -> tuple[str, datetime]:
        """Persist an already-validated identity, capped by its token and session TTL."""
        session_id = new_session_id()
        expires_at = min(self._clock() + self._max_lifetime, token_expires_at)
        if expires_at <= self._clock():
            raise AuthError("expired", "token expires too soon to mint a session")
        await self._store.put(session_lookup_key(session_id), identity, expires_at)
        return session_id, expires_at

    async def resolve(self, session_id: str) -> dict[str, str] | None:
        """Look up the digest, never the cookie value; unavailable stores raise."""
        if not session_id:
            return None
        return await self._store.get(session_lookup_key(session_id))

    async def revoke(self, session_id: str) -> None:
        """Revoke by digest. Empty or absent sessions are already revoked."""
        if session_id:
            await self._store.delete(session_lookup_key(session_id))

    async def purge_expired(self) -> int:
        """Remove expired sessions and flows; read-time expiry belongs to each store."""
        return await self._store.purge_expired() + await self._flows.purge_expired()