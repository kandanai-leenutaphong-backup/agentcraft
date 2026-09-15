"""Microsoft Entra ID, adapted to this application's one principal model.

This module is the whole Entra seam. ``app.components.entra_auth`` owns the cryptography, the
key set, the claim rules and the PKCE mechanics and knows nothing about CyberEye; this file
maps what that component proves onto :class:`~.principal.Principal` and nothing else. There is
exactly one identity type in the application, and adding a second is how two ownership checks
appear and the second one is wrong.

Two ways an Entra identity arrives, and both end at the same place:

* ``Authorization: Bearer <access token>`` \u2014 a programmatic caller, or the browser during the
  one request that trades a token for a session. Validated on every request.
* ``cy_session`` \u2014 an opaque, ``HttpOnly`` browser cookie minted only after a token was
  validated. It exists because a browser navigating to ``/`` cannot set a header, so without
  it the application bundle and its assets could not be protected at all without publishing
  them.

The cookie is **not** a second credential path with weaker rules. It is a receipt for one that
already passed, it holds no token, it cannot outlive the token that minted it, and the record
behind it is a hash \u2014 read access to the table yields nothing that can be presented as a
cookie.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping

from app.components.entra_auth import (
    AuthError,
    AzureTableRecordStore,
    EntraAuthConfig,
    RecordStore,
    RecordStoreUnavailable,
    SignInFlow,
    TokenValidator,
    VerifiedToken,
    constant_time_equals,
    extract_bearer,
    first_header,
    new_session_id,
    session_lookup_key,
)

from .config import SecuritySettings
from .principal import KIND_SERVICE, KIND_USER, Principal, entra_principal

logger = logging.getLogger(__name__)

#: The browser session cookie. Opaque, ``HttpOnly``, ``Secure``, ``SameSite=Lax``.
SESSION_COOKIE = "cy_session"
#: Names an in-progress sign-in. Also ``HttpOnly``: a flow id readable by script is a flow id
#: an injected script can finish on somebody else's behalf.
FLOW_COOKIE = "cy_flow"

#: Partitions inside the one authentication table. Flows and sessions have different
#: lifetimes and different blast radii, so they never share a partition.
FLOW_PARTITION = "flow"
SESSION_PARTITION = "session"

#: Marks a request whose identity came from a cookie rather than a header. Cookie-borne
#: identity is sent by the browser automatically, so unsafe methods carrying it need the
#: cross-site checks a header-borne identity does not.
COOKIE_AUTH_SCOPE_KEY = "auth_via_cookie"

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

#: A flow id and a state are both URL-safe base64 of 32 random bytes, minted by this
#: application and echoed back through the identity provider. Bounding them before either
#: reaches the store means a caller cannot spend a store round trip, or a comparison, on an
#: identifier that could never have been issued.
_FLOW_TOKEN_MIN = 16
_FLOW_TOKEN_MAX = 128
_FLOW_TOKEN = re.compile(r"^[A-Za-z0-9_-]+$")


def _well_formed_flow_token(value: str) -> bool:
    return (
        isinstance(value, str)
        and _FLOW_TOKEN_MIN <= len(value) <= _FLOW_TOKEN_MAX
        and bool(_FLOW_TOKEN.match(value))
    )


def principal_from_token(verified: VerifiedToken) -> Principal:
    """Map a verified token onto this application's identity.

    The identifier is ``entra:<tenant>:<object-id>`` and comes only from verified claims.
    Nothing here reads a header, and no display value influences it: an identity that names
    itself is not an identity.
    """
    return entra_principal(
        tenant_id=verified.tenant_id,
        object_id=verified.object_id,
        display=verified.display or verified.username,
        kind=KIND_SERVICE if verified.is_service else KIND_USER,
        scopes=verified.scopes,
        roles=verified.roles,
    )


def build_record_store(settings: SecuritySettings) -> RecordStore:
    """Build the shared store sign-in flows and browser sessions live in.

    Durable by construction when Entra is configured: :class:`SecuritySettings` refuses the
    combination that would leave a deployed application with process-local state.
    """
    return AzureTableRecordStore(
        endpoint=settings.session_table_endpoint,
        table_name=settings.session_table_name,
        partition_key=SESSION_PARTITION,
    )


class BrowserSessions:
    """Mints, resolves and revokes the cookie a signed-in person carries.

    Args:
        store: Shared expiring store. Sessions live under one partition, flows under another,
            so the two stores are separate objects over the same table.
        flow_store: Store for in-progress sign-ins.
        max_lifetime: Ceiling on a session, applied on top of the token's own expiry.
    """

    def __init__(
        self,
        *,
        store: RecordStore,
        flow_store: RecordStore,
        max_lifetime: timedelta,
    ) -> None:
        self._store = store
        self._flows = flow_store
        self._max_lifetime = max_lifetime

    async def start_flow(self, flow: SignInFlow, *, ttl: timedelta) -> None:
        await self._flows.put(flow.flow_id, flow.to_record(), _now() + ttl)

    async def claim_flow(self, flow_id: str, state: str) -> dict[str, str] | None:
        """Consume an in-progress sign-in, or refuse.

        One atomic consume, so exactly one callback can ever be handed a flow's PKCE verifier.
        Read-then-delete was not equivalent: a durable store suspends on network I/O between
        the two, and a second callback arriving in that window received the same one-time
        secret.

        The flow is spent whether or not the state matched. A flow that survives a failed
        attempt is a flow an attacker may retry, and a sign-in nobody completed is not worth
        keeping alive to be completed by somebody else.
        """
        if not _well_formed_flow_token(flow_id) or not _well_formed_flow_token(state):
            return None
        record = await self._flows.consume(flow_id)
        if record is None:
            return None
        if not constant_time_equals(record.get("state", ""), state):
            logger.warning("auth.signin.state_mismatch")
            return None
        return record

    async def create(self, verified: VerifiedToken) -> tuple[str, datetime]:
        """Mint a session for a validated token. Returns the cookie value and its expiry.

        The expiry is the earlier of the token's own ``exp`` and the configured ceiling, so a
        session is never a way to hold access for longer than the credential that proved it.
        """
        session_id = new_session_id()
        token_expiry = datetime.fromtimestamp(verified.expires_at, tz=timezone.utc)
        expires_at = min(_now() + self._max_lifetime, token_expiry)
        if expires_at <= _now():
            raise AuthError("expired", "token expires too soon to mint a session")
        principal = principal_from_token(verified)
        await self._store.put(
            session_lookup_key(session_id),
            {
                "principal_id": principal.id,
                "tenant_id": principal.tenant_id,
                "kind": principal.kind,
                "display": principal.display,
                "scopes": " ".join(principal.scopes),
                "roles": " ".join(principal.roles),
            },
            expires_at,
        )
        return session_id, expires_at

    async def resolve(self, session_id: str) -> Principal | None:
        """Return the identity behind a cookie, or ``None``.

        The identifier is never looked up directly; its digest is. An unreadable store is a
        refusal, never an admission.
        """
        if not session_id:
            return None
        try:
            record = await self._store.get(session_lookup_key(session_id))
        except RecordStoreUnavailable:
            logger.error("auth.session.store_unavailable")
            return None
        if record is None:
            return None
        identity = record.get("principal_id", "")
        if not identity.startswith("entra:"):
            return None
        return Principal(
            id=identity,
            kind=record.get("kind", KIND_USER),
            issuer="entra",
            display=record.get("display", ""),
            tenant_id=record.get("tenant_id", ""),
            scopes=tuple(f for f in record.get("scopes", "").split(" ") if f),
            roles=tuple(f for f in record.get("roles", "").split(" ") if f),
        )

    async def revoke(self, session_id: str) -> None:
        """Delete a session. Absent is success: sign-out must be idempotent."""
        if session_id:
            await self._store.delete(session_lookup_key(session_id))

    async def purge_expired(self) -> int:
        """Housekeeping. Removing a dead record late is harmless; reading one is not, and
        :meth:`resolve` already refuses anything past its expiry."""
        return await self._store.purge_expired() + await self._flows.purge_expired()


def bearer_resolver(validator: TokenValidator) -> Callable[[Mapping[str, Any]], Any]:
    """A gate resolver that believes a validated ``Authorization: Bearer`` token.

    Returns ``None`` for every failure, including an absent header, so the gate produces one
    indistinguishable refusal. A caller learns whether their token was accepted, never why it
    was not.
    """

    async def resolve(scope: Mapping[str, Any]) -> Principal | None:
        headers = _headers(scope)
        try:
            token = extract_bearer(headers)
            verified = await validator.validate_token(token)
        except AuthError:
            return None
        return principal_from_token(verified)

    return resolve


def cookie_resolver(sessions: BrowserSessions) -> Callable[[Mapping[str, Any]], Any]:
    """A gate resolver that believes a browser session cookie."""

    async def resolve(scope: Mapping[str, Any]) -> Principal | None:
        session_id = read_cookie(_headers(scope), SESSION_COOKIE)
        principal = await sessions.resolve(session_id)
        if principal is not None:
            # Recorded so the cross-site guard downstream knows this identity arrived
            # automatically rather than because a client chose to send it.
            scope[COOKIE_AUTH_SCOPE_KEY] = True  # type: ignore[index]
        return principal

    return resolve


class CookieCrossSiteGuard:
    """Refuses an unsafe request whose only credential is a cookie the browser sent for it.

    ``SameSite=Lax`` already stops the cookie travelling on a cross-site ``POST``, and this is
    the second lock: browsers that do not enforce it, and any future need to relax it, must
    not silently become a cross-site request forgery. Two conditions, both required:

    * ``Origin`` must be this application's own origin. A missing ``Origin`` on an unsafe
      method is refused rather than trusted, because the browsers that omit it are the ones
      whose ``SameSite`` behaviour cannot be relied on either.
    * the body must be declared as JSON. An HTML form cannot send that content type
      cross-site without a preflight, so requiring it removes the form-post shape entirely.

    A signed request and a bearer token are untouched: neither is sent automatically by a
    browser, so neither has the property that makes forgery possible.
    """

    def __init__(self, app: Callable, *, expected_origin: str) -> None:
        self._app = app
        self._origin = expected_origin.rstrip("/")

    async def __call__(self, scope: dict, receive: Callable, send: Callable) -> None:
        if scope.get("type") != "http" or not scope.get(COOKIE_AUTH_SCOPE_KEY):
            await self._app(scope, receive, send)
            return
        method = str(scope.get("method", "")).upper()
        if method in _SAFE_METHODS:
            await self._app(scope, receive, send)
            return

        headers = _headers(scope)
        origin = first_header(headers, "origin").rstrip("/")
        content_type = first_header(headers, "content-type").split(";")[0].strip().lower()
        if origin != self._origin or content_type != "application/json":
            logger.warning(
                "auth.session.cross_site_refused",
                extra={"origin_present": bool(origin), "content_type": content_type},
            )
            await _send_403(send)
            return
        await self._app(scope, receive, send)


async def _send_403(send: Callable) -> None:
    """A refusal a browser can act on, with nothing in it about the application.

    403 rather than 401 deliberately: the caller *is* authenticated, and telling them to
    authenticate again would send a signed-in person round the sign-in loop forever.
    """
    await send({
        "type": "http.response.start",
        "status": 403,
        "headers": [(b"content-length", b"0"), (b"cache-control", b"no-store, private")],
    })
    await send({"type": "http.response.body", "body": b"", "more_body": False})


def read_cookie(headers: Mapping[str, str], name: str) -> str:
    """Read one cookie value from a request.

    Parsed here rather than with the standard library's cookie module, which is lenient about
    malformed input in ways that have historically let a crafted header shadow a real cookie.
    An unparseable pair is skipped, and a name repeated *within one* ``Cookie`` header yields
    the first occurrence.

    Two separate ``Cookie`` headers resolve the other way: :func:`_headers` flattens the ASGI
    header list into a dict, so the **last** header wins and this function never sees the first.
    Measured, not assumed. Not an escalation — no browser emits a second ``Cookie`` header, and
    an injected trailing one substitutes only the injector's own session — but it differs from
    the signed path, which refuses a duplicated header outright.
    """
    raw = first_header(headers, "cookie")
    if not raw:
        return ""
    for part in raw.split(";"):
        key, _, value = part.strip().partition("=")
        if key == name:
            return value.strip().strip('"')
    return ""


def set_cookie_header(
    name: str, value: str, *, expires_at: datetime | None, path: str = "/", max_age: int | None = None
) -> str:
    """Build a ``Set-Cookie`` value with every protective attribute, always.

    ``Secure`` is unconditional. The application is only ever reached over HTTPS, and a cookie
    that is allowed to travel in the clear during local development is a cookie whose
    protection depends on the environment being right.
    """
    parts = [f"{name}={value}", f"Path={path}", "HttpOnly", "Secure", "SameSite=Lax"]
    if max_age is not None:
        parts.append(f"Max-Age={max_age}")
    if expires_at is not None:
        parts.append(f"Expires={expires_at.astimezone(timezone.utc).strftime('%a, %d %b %Y %H:%M:%S GMT')}")
    return "; ".join(parts)


def clear_cookie_header(name: str, *, path: str = "/") -> str:
    return set_cookie_header(name, "", expires_at=datetime(1970, 1, 1, tzinfo=timezone.utc), path=path, max_age=0)


def build_entra_config(settings: SecuritySettings) -> EntraAuthConfig:
    """Turn resolved settings into the component's trust boundary.

    Single-tenant, human callers only, and one delegated scope. A service principal that wants
    in gets its own decision and its own application role, not a quiet inheritance of a
    person's access.
    """
    return EntraAuthConfig(
        tenant_id=settings.entra_tenant_id,
        client_id=settings.entra_client_id,
        allow_service_principals=False,
    )


def _headers(scope: Mapping[str, Any]) -> dict[str, str]:
    return {
        key.decode("latin-1"): value.decode("latin-1")
        for key, value in scope.get("headers", [])
    }


def _now() -> datetime:
    return datetime.now(timezone.utc)


__all__ = [
    "BrowserSessions",
    "COOKIE_AUTH_SCOPE_KEY",
    "CookieCrossSiteGuard",
    "FLOW_COOKIE",
    "FLOW_PARTITION",
    "SESSION_COOKIE",
    "SESSION_PARTITION",
    "bearer_resolver",
    "build_entra_config",
    "build_record_store",
    "clear_cookie_header",
    "cookie_resolver",
    "principal_from_token",
    "read_cookie",
    "set_cookie_header",
]
