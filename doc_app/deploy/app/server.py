"""Static writeup server with two mutually exclusive auth paths.

1. Entra (production): Container Apps built-in auth performs the OIDC flow and
   injects ``X-MS-CLIENT-PRINCIPAL-*``. Platform auth is set to allow anonymous
   through so this process can also honour path 2; this process, not the
   platform, is what refuses unauthenticated readers.

2. Ed25519 signed requests (iteration/agent testing): wire shape copied from
   gridiq AUTODEV section 4.2 so one signing CLI works against both. The server
   holds only the PUBLIC verifier; the private key never leaves the operator.
   Unset ``DEV_PUBLIC_KEY_ED25519`` and this path does not exist.
"""

from __future__ import annotations

import base64
import hashlib
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import PlainTextResponse, RedirectResponse, Response
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

CONTENT_ROOT = Path(os.environ.get("CONTENT_ROOT", "/app/site"))
MAX_SKEW_SECONDS = 300
MAX_SESSION_HOURS = 12
SESSION_COOKIE = "dev_session"
PUBLIC_PATHS = {"/healthz"}

SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'none'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
        "script-src 'self'; "
        "font-src 'self'; connect-src 'self'; media-src 'self'; "
        "base-uri 'none'; form-action 'none'; "
        "frame-ancestors 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "X-Frame-Options": "DENY",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    # Confidential content must not outlive the session in a browser cache.
    "Cache-Control": "no-store, private",
}


def _verifier() -> Ed25519PublicKey | None:
    raw = os.environ.get("DEV_PUBLIC_KEY_ED25519", "").strip()
    if not raw:
        return None
    try:
        return Ed25519PublicKey.from_public_bytes(base64.b64decode(raw))
    except Exception:
        return None


VERIFIER = _verifier()

# Bounded replay window: a captured signature cannot be reused inside the skew
# window it was already spent in.
_SEEN: dict[str, float] = {}


def _reap(now: float) -> None:
    for sig, seen_at in list(_SEEN.items()):
        if now - seen_at > MAX_SKEW_SECONDS:
            _SEEN.pop(sig, None)


def _entra_authenticated(request) -> bool:
    return bool(
        request.headers.get("x-ms-client-principal-id")
        or request.headers.get("x-ms-client-principal-name")
    )


async def _signature_ok(request) -> bool:
    """Verify METHOD\\npath?query\\nts\\nslug\\nsha256_hex(body)."""
    if VERIFIER is None:
        return False

    ts = request.headers.get("x-request-timestamp", "")
    sig_b64 = request.headers.get("x-request-signature", "")
    if not ts or not sig_b64:
        return False

    try:
        stamped = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return False
    if stamped.tzinfo is None:
        stamped = stamped.replace(tzinfo=timezone.utc)
    now = time.time()
    if abs(now - stamped.timestamp()) > MAX_SKEW_SECONDS:
        return False

    _reap(now)
    if sig_b64 in _SEEN:
        return False

    body = await request.body()
    path = request.url.path
    if request.url.query:
        path = f"{path}?{request.url.query}"
    slug = request.headers.get("x-request-context", "")
    canonical = "\n".join(
        [request.method, path, ts, slug, hashlib.sha256(body).hexdigest()]
    ).encode()

    try:
        VERIFIER.verify(base64.b64decode(sig_b64), canonical)
    except (InvalidSignature, ValueError, TypeError):
        return False

    _SEEN[sig_b64] = now
    return True


def _session_ok(request) -> bool:
    """Verify a browser session cookie: base64(expiry) '.' base64(signature).

    Signed by the same operator key over ``SESSION\\n<expiry>``. Stateless, so it
    survives replica scaling, and bounded by an expiry inside the signed string
    — a captured cookie dies on its own.
    """
    if VERIFIER is None:
        return False
    raw = request.cookies.get(SESSION_COOKIE, "")
    if not raw or "." not in raw:
        return False

    exp_b64, sig_b64 = raw.split(".", 1)
    try:
        expiry = base64.urlsafe_b64decode(exp_b64).decode()
        stamped = datetime.fromisoformat(expiry.replace("Z", "+00:00"))
        VERIFIER.verify(
            base64.urlsafe_b64decode(sig_b64), f"SESSION\n{expiry}".encode()
        )
    except (InvalidSignature, ValueError, TypeError):
        return False

    if stamped.tzinfo is None:
        stamped = stamped.replace(tzinfo=timezone.utc)
    remaining = stamped.timestamp() - time.time()
    return 0 < remaining <= MAX_SESSION_HOURS * 3600


class Gate(BaseHTTPMiddleware):
    """Default deny. Entra principal, a valid signature, or a signed session."""

    async def dispatch(self, request, call_next):
        path = request.url.path

        if path in PUBLIC_PATHS:
            return PlainTextResponse("ok\n")

        allowed = (
            _entra_authenticated(request)
            or _session_ok(request)
            or await _signature_ok(request)
        )
        if not allowed:
            # Browsers get the sign-in page; everything else gets a bare 401
            # with no diagnostic detail.
            accept = request.headers.get("accept", "")
            if request.method in {"GET", "HEAD"} and "text/html" in accept:
                target = f"/.auth/login/aad?post_login_redirect_uri={path}"
                return RedirectResponse(target, status_code=302)
            return Response(status_code=401)

        response = await call_next(request)
        for header, value in SECURITY_HEADERS.items():
            response.headers[header] = value
        return response


async def whoami(request):
    """Echo the platform-injected principal. Inbound copies are stripped by the
    platform, so this cannot be spoofed by the caller."""
    return JSONResponse(
        {
            "name": request.headers.get("x-ms-client-principal-name")
            or request.headers.get("x-ms-client-principal-id")
        }
    )


app = Starlette(
    routes=[
        Route("/api/me", whoami),
        Mount("/", app=StaticFiles(directory=str(CONTENT_ROOT), html=True)),
    ],
    middleware=[],
)
app.add_middleware(Gate)
