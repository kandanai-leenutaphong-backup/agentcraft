"""The four public routes a person needs to sign in, and the two that prove they did.

Public surface, in full, and nothing else is reachable without a principal:

============================  ======  ==================================================
``/auth/login``               GET     starts a flow, redirects to Entra
``/auth/callback``            GET     the redirect target: redeems the code in the browser
``/auth/session``             POST    trades a validated access token for a session cookie
``/auth/signed-out``          GET     where sign-out lands, with a way back in
============================  ======  ==================================================

Each is an **exact** path with an exact method, registered with the authorization gate in
process. None of them serves application data, application configuration, or a secret. The
callback page is fourteen lines of inline script under a nonce; it is not the application
bundle, and the bundle stays behind the gate.

Why the browser redeems the code rather than the server
-------------------------------------------------------
The registration is a **public client with a SPA redirect URI**, so there is no client secret
anywhere \u2014 nothing to rotate, nothing to leak, nothing to keep out of an image. Entra issues
codes for that platform to be redeemed cross-origin from a browser, and refuses server-side
redemption of them outright. The verifier the browser needs is still generated server-side and
held against an ``HttpOnly`` flow cookie, so it never touches web storage and lives only for
the seconds the redirect takes.

The access token exists in page memory for exactly one ``fetch``: the page posts it to
``/auth/session``, this application validates it as it would any bearer token, and what comes
back is an opaque cookie. The token is never stored, never put in a URL, and never returned.
"""

from __future__ import annotations

import json
import logging
import secrets
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse

from app.components.entra_auth import (
    DEFAULT_FLOW_TTL_SECONDS,
    AuthError,
    RecordStoreUnavailable,
    TokenValidator,
    authorize_url,
    logout_url,
    new_flow,
)

from .config import SecuritySettings
from .entra import (
    FLOW_COOKIE,
    SESSION_COOKIE,
    BrowserSessions,
    clear_cookie_header,
    read_cookie,
    set_cookie_header,
)
from .gate import PublicRoute, safe_return_path
from .principal import Principal

logger = logging.getLogger(__name__)

#: The exact public routes this module contributes. The composition root hands this list to
#: the gate; nothing here is inferred from the router, so a route added by accident is not
#: published by accident.
PUBLIC_ROUTES: tuple[PublicRoute, ...] = (
    PublicRoute("/auth/login", frozenset({"GET"})),
    PublicRoute("/auth/callback", frozenset({"GET"})),
    PublicRoute("/auth/session", frozenset({"POST"})),
    PublicRoute("/auth/signed-out", frozenset({"GET"})),
)

SIGN_IN_PATH = "/auth/login"

#: Ceiling on the one body an unauthenticated caller may send. A JWT access token is a few
#: kilobytes; 16 KiB accepts every real one and nothing that could be mistaken for an upload.
#: The signed path's own 1 MiB ceiling is unrelated and unchanged — that caller has a key.
MAX_SESSION_BODY_BYTES = 16_384

#: Ceiling on chunks. A stream of empty chunks never reaches the byte cap and would otherwise
#: hold the connection open indefinitely.
MAX_SESSION_BODY_CHUNKS = 64

#: Sentinel distinguishing "too large" from "unreadable", so one gets 413 and the other 400.
_OVERSIZED = object()


def _content_type_of(request: Request) -> str:
    """The media type alone, lowercased. ``Application/JSON; charset=utf-8`` is JSON."""
    return request.headers.get("content-type", "").split(";")[0].strip().lower()


async def _read_bounded_body(request: Request) -> bytes | object | None:
    """Read the body under a byte and a chunk ceiling.

    Returns the bytes, :data:`_OVERSIZED` when either ceiling is passed, or ``None`` when the
    caller disconnected or the stream ended without completing. The stream is abandoned the
    moment the ceiling is passed, so an oversized body is never fully buffered.
    """
    chunks: list[bytes] = []
    size = 0
    seen = 0
    try:
        async for chunk in request.stream():
            seen += 1
            if seen > MAX_SESSION_BODY_CHUNKS:
                return _OVERSIZED
            size += len(chunk)
            if size > MAX_SESSION_BODY_BYTES:
                return _OVERSIZED
            chunks.append(chunk)
    except Exception:
        return None
    if await request.is_disconnected():
        return None
    return b"".join(chunks)

#: Nothing loads, nothing frames, nothing submits. The only script permitted is the one
#: carrying this response's nonce, and the only host the page may reach is the identity
#: provider's token endpoint plus this origin.
_CSP = (
    "default-src 'none'; script-src 'nonce-{nonce}'; style-src 'nonce-{nonce}'; "
    "connect-src 'self' https://login.microsoftonline.com; img-src 'none'; "
    "base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
)

_SECURITY_HEADERS = {
    "Cache-Control": "no-store, private",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
}


def _safe_json(value: Any) -> str:
    """JSON for embedding inside a ``<script>`` block.

    ``</script>`` inside a string ends the block wherever the parser is, so the three
    characters that can start a tag or an entity are escaped into their unicode forms. The
    result is still valid JSON and still parses to the same value.
    """
    return (
        json.dumps(value)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )


def _page(nonce: str, body: str, *, status: int = 200) -> Response:
    return Response(
        content=(
            "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            "<title>CyberEye</title>"
            f"<style nonce=\"{nonce}\">"
            "body{background:#0b0f14;color:#c9d6e2;font:16px/1.6 system-ui,sans-serif;"
            "display:flex;min-height:100vh;align-items:center;justify-content:center;margin:0}"
            "main{max-width:32rem;padding:2rem;text-align:center}"
            "a{color:#7cc4ff}h1{font-size:1.4rem;margin:0 0 .5rem}"
            "</style></head>"
            f"<body><main>{body}</main></body></html>"
        ),
        status_code=status,
        media_type="text/html; charset=utf-8",
        headers={**_SECURITY_HEADERS, "Content-Security-Policy": _CSP.format(nonce=nonce)},
    )


def build_signin_router(
    *,
    settings: SecuritySettings,
    validator: TokenValidator,
    sessions: BrowserSessions,
) -> APIRouter:
    """Build the sign-in routes for a configured deployment.

    Called only when Entra is configured. A deployment without it mounts none of these, so
    there is no half-built sign-in surface for anyone to probe.
    """
    router = APIRouter()
    redirect_uri = settings.redirect_uri()

    @router.get("/auth/login")
    async def login(request: Request) -> Response:
        """Start a sign-in and send the browser to Entra.

        ``return_to`` is reduced to a same-origin path before it is stored, and it is stored
        rather than carried through the identity provider, so nothing an attacker puts in the
        query string can survive as a redirect target.
        """
        flow = new_flow(return_to=safe_return_path(request.query_params.get("return_to", "/")))
        try:
            await sessions.start_flow(flow, ttl=timedelta(seconds=DEFAULT_FLOW_TTL_SECONDS))
        except RecordStoreUnavailable:
            logger.error("auth.signin.flow_store_unavailable")
            return _page(
                secrets.token_urlsafe(16),
                "<h1>Sign-in is unavailable</h1><p>The service could not start a sign-in. "
                "Try again shortly.</p>",
                status=503,
            )
        response = RedirectResponse(
            authorize_url(_config_of(validator), redirect_uri=redirect_uri, flow=flow),
            status_code=303,
        )
        response.headers["Set-Cookie"] = set_cookie_header(
            FLOW_COOKIE, flow.flow_id, expires_at=None,
            path="/auth", max_age=DEFAULT_FLOW_TTL_SECONDS,
        )
        for key, value in _SECURITY_HEADERS.items():
            response.headers[key] = value
        return response

    @router.get("/auth/callback")
    async def callback(request: Request) -> Response:
        """Redeem the authorization code in the browser, then trade it for a session.

        Everything this page needs is embedded once, by the server, for this flow only. If
        the flow cookie, the state, or the code is missing or wrong, the page says so and
        offers a fresh sign-in; it never reveals which of the three was at fault.
        """
        nonce = secrets.token_urlsafe(16)
        error = request.query_params.get("error", "")
        if error:
            # Reported without echoing: the identity provider's error text is attacker-
            # influenceable through the request that produced it.
            logger.warning("auth.signin.provider_error", extra={"error_len": len(error)})
            return _page(nonce, _retry_body("Sign-in did not complete."), status=400)

        code = request.query_params.get("code", "")
        state = request.query_params.get("state", "")
        flow_id = read_cookie(dict(request.headers), FLOW_COOKIE)
        try:
            record = await sessions.claim_flow(flow_id, state)
        except RecordStoreUnavailable:
            logger.error("auth.signin.flow_store_unavailable")
            record = None
        if not code or record is None:
            return _page(nonce, _retry_body("This sign-in link is no longer valid."), status=400)

        config = _config_of(validator)
        payload = _safe_json({
            "tokenEndpoint": config.token_endpoint(),
            "clientId": config.client_id,
            "redirectUri": redirect_uri,
            "scope": " ".join(config.client_scopes()),
            "codeVerifier": record.get("code_verifier", ""),
            "returnTo": safe_return_path(record.get("return_to", "/")),
        })
        body = (
            "<h1>Signing you in\u2026</h1><p id=\"m\">Completing sign-in with Microsoft Entra ID.</p>"
            f"<script nonce=\"{nonce}\">{_CALLBACK_SCRIPT}\nrun({payload});</script>"
        )
        response = _page(nonce, body)
        # The flow is spent either way, so its cookie goes now rather than lingering as a
        # replayable name for a record that no longer exists.
        response.headers.append("Set-Cookie", clear_cookie_header(FLOW_COOKIE, path="/auth"))
        return response

    @router.post("/auth/session")
    async def create_session(request: Request) -> Response:
        """Validate an access token and return an opaque session cookie.

        Public by necessity \u2014 a caller with no session is exactly who uses it \u2014 but not
        unauthenticated: the token is validated by the same rules as any bearer token on any
        route, and a refusal here is the same shape as a refusal anywhere else.
        """
        if _content_type_of(request) != "application/json":
            return _bare(415)
        origin = (request.headers.get("origin") or "").rstrip("/")
        if origin != settings.public_origin:
            # This endpoint mints an ambient credential, so it accepts only same-origin
            # callers even though it consumes no ambient credential itself.
            logger.warning("auth.session.foreign_origin", extra={"origin_present": bool(origin)})
            return _bare(403)

        # Bounded before it is read, not after. This is the one route that must accept bytes
        # from a caller who has proved nothing, so an unbounded read here lets a stranger buy
        # memory with a request that was never going to be authorised.
        declared = request.headers.get("content-length", "").strip()
        if declared.isdigit() and int(declared) > MAX_SESSION_BODY_BYTES:
            return _bare(413)
        raw = await _read_bounded_body(request)
        if raw is _OVERSIZED:
            return _bare(413)
        if raw is None:
            # Disconnected, truncated, or too many chunks. Nothing to validate.
            return _bare(400)
        try:
            body = json.loads(raw)
        except ValueError:
            return _bare(400)
        token = body.get("access_token", "") if isinstance(body, dict) else ""
        if not isinstance(token, str) or not token:
            return _bare(400)

        try:
            verified = await validator.validate_token(token)
            session_id, expires_at = await sessions.create(verified)
        except AuthError:
            return _bare(401)
        except RecordStoreUnavailable:
            logger.error("auth.session.store_unavailable")
            return _bare(503)

        response = JSONResponse(
            {"ok": True, "expiresAt": expires_at.isoformat().replace("+00:00", "Z")},
            headers=dict(_SECURITY_HEADERS),
        )
        response.headers["Set-Cookie"] = set_cookie_header(
            SESSION_COOKIE, session_id, expires_at=expires_at, path="/",
            max_age=int((expires_at - _utcnow()).total_seconds()),
        )
        return response

    @router.get("/auth/signed-out")
    async def signed_out() -> Response:
        return _page(
            secrets.token_urlsafe(16),
            "<h1>Signed out</h1><p>Your CyberEye session has ended.</p>"
            "<p><a href=\"/auth/login\">Sign in again</a></p>",
        )

    @router.post("/auth/logout")
    async def logout(request: Request) -> Response:
        """Revoke this session here first, then name the identity provider's sign-out URL.

        Local revocation happens before anything else and does not depend on the browser
        following the second step: a sign-out that only ends the provider's session leaves
        this application's cookie live.
        """
        session_id = read_cookie(dict(request.headers), SESSION_COOKIE)
        try:
            await sessions.revoke(session_id)
        except RecordStoreUnavailable:
            logger.error("auth.session.revoke_failed")
            return _bare(503)
        response = JSONResponse(
            {"ok": True,
             "providerLogoutUrl": logout_url(
                 _config_of(validator),
                 post_logout_redirect_uri=f"{settings.public_origin}/auth/signed-out",
             )},
            headers=dict(_SECURITY_HEADERS),
        )
        response.headers["Set-Cookie"] = clear_cookie_header(SESSION_COOKIE, path="/")
        return response

    @router.get("/api/whoami")
    async def whoami(request: Request) -> Response:
        """Who the gate believes the caller is. Protected, like everything else.

        The canary both access paths are proved against: a signed developer key and a signed-in
        person hit the same route and get the same shape, which is what "one identity model"
        means in practice.
        """
        principal: Principal | None = request.scope.get("auth_principal")
        if principal is None:  # pragma: no cover - the gate refuses first
            return _bare(401)
        return JSONResponse(
            {
                "id": principal.id,
                "kind": principal.kind,
                "issuer": principal.issuer,
                "display": principal.display,
                "tenant_id": principal.tenant_id,
                "scopes": list(principal.scopes),
                "roles": list(principal.roles),
            },
            headers=dict(_SECURITY_HEADERS),
        )

    return router


def _retry_body(message: str) -> str:
    return f"<h1>{message}</h1><p><a href=\"/auth/login\">Start again</a></p>"


def _bare(status: int) -> Response:
    """A refusal with no body. Nothing to read, nothing to distinguish one cause from another."""
    return Response(status_code=status, headers=dict(_SECURITY_HEADERS))


def _config_of(validator: TokenValidator):
    return validator.config


def _utcnow():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)


#: Redeems the code and trades it for a session. Kept deliberately small and readable: it runs
#: on the one page an unauthenticated visitor can reach, so every line of it is public.
_CALLBACK_SCRIPT = """
async function run(c) {
  const p = new URLSearchParams(location.search);
  const note = document.getElementById('m');
  // The code is single-use, but leaving it in the address bar puts it in history and in the
  // next request's referrer. It is gone before the first network call.
  history.replaceState(null, '', location.pathname);
  try {
    const r = await fetch(c.tokenEndpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({
        client_id: c.clientId, grant_type: 'authorization_code', code: p.get('code') || '',
        redirect_uri: c.redirectUri, code_verifier: c.codeVerifier, scope: c.scope,
      }),
    });
    const t = await r.json();
    if (!r.ok || !t.access_token) throw new Error('token');
    const s = await fetch('/auth/session', {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ access_token: t.access_token }),
    });
    if (!s.ok) throw new Error('session');
    location.replace(c.returnTo);
  } catch (e) {
    note.textContent = 'Sign-in did not complete.';
    // `after` returns undefined, so the paragraph has to be built and inserted separately;
    // chaining off it threw before the retry link was ever attached, and the page then
    // offered a dead end instead of a way back in.
    const p = document.createElement('p');
    const a = document.createElement('a');
    a.href = '/auth/login'; a.textContent = 'Start again';
    p.appendChild(a);
    note.after(p);
  }
}
"""

__all__ = [
    "MAX_SESSION_BODY_BYTES",
    "MAX_SESSION_BODY_CHUNKS",
    "PUBLIC_ROUTES",
    "SIGN_IN_PATH",
    "build_signin_router",
]
