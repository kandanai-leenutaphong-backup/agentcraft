"""Pure-ASGI middleware that authenticates Ed25519-signed requests.

Pure ASGI, never ``BaseHTTPMiddleware``: that class buffers the response body, which would
turn every server-sent-event stream in the application into one delayed blob. Here the
response stream is untouched — only request headers are inspected, the request body is read
once and replayed through a fresh ``receive``, and the second and later ``receive`` calls
delegate to the real transport so a genuine ``http.disconnect`` still reaches the framework.

The domain seam: this module owns crypto, transport and replay rejection, and knows nothing
about the consuming application's identity type. On success it calls the injected
``identity_factory(slug)`` and attaches the result to ``scope[scope_key]``. It never imports
a principal class.

No logger is imported. Success and failure are both silent; the only externally observable
signal is the status code, and every failure is a bare 401 with no body and no header that
distinguishes it from a request that never attempted authentication.
"""

from __future__ import annotations

from typing import Callable

from ._replay import ReplayLedger, claim_or_deny
from ._verifier import verify

#: Header names deliberately resemble ordinary API request signing. Nothing in them says
#: "dev", "key" or "bypass", so captured traffic teaches an observer nothing.
TIMESTAMP_HEADER = "X-Request-Timestamp"
SIGNATURE_HEADER = "X-Request-Signature"
CONTEXT_HEADER = "X-Request-Context"

_TS = TIMESTAMP_HEADER.lower().encode("ascii")
_SIG = SIGNATURE_HEADER.lower().encode("ascii")
_CTX = CONTEXT_HEADER.lower().encode("ascii")

#: ASGI scope key the verified principal is attached under. It is the same key the primary
#: authorization gate reads, so signed access and any later token path converge on one
#: principal model rather than authenticating twice.
DEFAULT_SCOPE_KEY = "auth_principal"

#: Ceiling on a signed request body. The body must be buffered whole to be hashed, so without
#: a cap an unauthenticated caller can buy unbounded memory with an unverified request.
MAX_SIGNED_BODY_BYTES = 1_048_576

#: Ceiling on body chunks. A malformed chunked stream of empty chunks never reaches the byte
#: cap and would otherwise loop forever.
MAX_SIGNED_BODY_CHUNKS = 4096


class _DuplicateHeader(Exception):
    """A signing header appeared more than once."""


def _single(headers: list[tuple[bytes, bytes]], name: bytes) -> str:
    """Return the one value of ``name``, ``""`` when absent.

    Raises:
        _DuplicateHeader: When the header appears more than once. Proxies disagree about
            which duplicate wins, so a request whose signed material is ambiguous is refused
            rather than resolved by guessing.
    """
    found: str | None = None
    for key, value in headers:
        if key.lower() != name:
            continue
        if found is not None:
            raise _DuplicateHeader
        try:
            found = value.decode("latin-1")
        except Exception:
            found = ""
    return found or ""


def _path_and_query(scope: dict) -> str:
    """Rebuild the path exactly as it travelled on the wire.

    ASGI exposes ``raw_path`` (the original, still percent-encoded bytes) and ``path`` (the
    decoded form). The client signed what it sent, so a server that rebuilds from ``path``
    re-encodes differently and every percent-encoded path fails verification.
    """
    raw = scope.get("raw_path")
    path = raw.decode("latin-1") if isinstance(raw, (bytes, bytearray)) else scope.get("path", "")
    query = scope.get("query_string") or b""
    return f"{path}?{query.decode('latin-1')}" if query else path


async def _send_401(send: Callable) -> None:
    """Bare 401: no body, no reason, no ``WWW-Authenticate``, no cacheable copy."""
    await send({
        "type": "http.response.start",
        "status": 401,
        "headers": [
            (b"content-length", b"0"),
            (b"cache-control", b"no-store, private"),
        ],
    })
    await send({"type": "http.response.body", "body": b"", "more_body": False})


class SignedRequestASGIMiddleware:
    """Authenticates signed requests; leaves every other request exactly as it found it.

    A request carrying both signing headers is a signed attempt and is either authenticated or
    refused here. A request carrying neither passes through unchanged — this middleware grants
    access, it never denies it on behalf of the application, and the authorization gate behind
    it is what refuses an anonymous caller.

    Args:
        app: The next ASGI callable.
        public_key_b64: Ed25519 public key, base64 of 32 raw bytes, captured at construction.
        identity_factory: Maps a verified, normalised slug to the consumer's principal.
            Called only after signature *and* replay checks pass.
        replay_ledger: Shared atomic claim-once store. Required: there is no default, because
            a per-process default is a security-wide loophole that nobody would notice.
        scope_key: Where the principal is attached.
        max_body_bytes: Ceiling on the buffered request body.
    """

    def __init__(
        self,
        app: Callable,
        *,
        public_key_b64: str,
        identity_factory: Callable[[str], object],
        replay_ledger: ReplayLedger,
        scope_key: str = DEFAULT_SCOPE_KEY,
        max_body_bytes: int = MAX_SIGNED_BODY_BYTES,
    ) -> None:
        if not (public_key_b64 or "").strip():
            raise ValueError("public_key_b64 is required; mount via install_signed_request_auth")
        if replay_ledger is None:
            raise ValueError("replay_ledger is required")
        self._app = app
        self._public_key = public_key_b64.strip()
        self._identity_factory = identity_factory
        self._ledger = replay_ledger
        self._scope_key = scope_key
        self._max_body_bytes = max_body_bytes

    async def __call__(self, scope: dict, receive: Callable, send: Callable) -> None:
        if scope.get("type") != "http":
            await self._app(scope, receive, send)
            return

        headers: list[tuple[bytes, bytes]] = scope.get("headers", [])
        try:
            timestamp = _single(headers, _TS)
            signature = _single(headers, _SIG)
            context = _single(headers, _CTX)
        except _DuplicateHeader:
            await _send_401(send)
            return

        if not timestamp or not signature:
            await self._app(scope, receive, send)
            return

        body = await self._read_body(receive)
        if body is None:
            await _send_401(send)
            return

        result = verify(
            public_key_b64=self._public_key,
            method=scope.get("method", ""),
            path_and_query=_path_and_query(scope),
            ts=timestamp,
            sig_b64=signature,
            body=body,
            user_slug=context,
        )
        if not result.ok or result.expires_at is None:
            await _send_401(send)
            return

        if not await claim_or_deny(self._ledger, result.replay_key, result.expires_at):
            await _send_401(send)
            return

        scope[self._scope_key] = self._identity_factory(result.user_slug)

        replayed = False

        async def replay_receive() -> dict:
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        await self._app(scope, replay_receive, send)

    async def _read_body(self, receive: Callable) -> bytes | None:
        """Buffer the whole body, or ``None`` when it must not be verified."""
        chunks: list[bytes] = []
        size = 0
        for _ in range(MAX_SIGNED_BODY_CHUNKS):
            message = await receive()
            if message.get("type") != "http.request":
                return None
            chunk = message.get("body") or b""
            size += len(chunk)
            if size > self._max_body_bytes:
                return None
            chunks.append(chunk)
            if not message.get("more_body", False):
                return b"".join(chunks)
        return None


def install_signed_request_auth(
    app,
    *,
    public_key_b64: str,
    identity_factory: Callable[[str], object],
    replay_ledger: ReplayLedger,
    scope_key: str = DEFAULT_SCOPE_KEY,
    max_body_bytes: int = MAX_SIGNED_BODY_BYTES,
) -> bool:
    """Mount the middleware, or decline. Returns whether it was mounted.

    An absent public key means the middleware is not added to the ASGI stack at all, so the
    deployment has no signed authorizing path and its stack is identical to a build without
    this component. Revocation is clearing one environment variable; the primary
    authentication path is untouched either way.
    """
    key = (public_key_b64 or "").strip()
    if not key:
        return False
    if replay_ledger is None:
        raise ValueError("replay_ledger is required when a public key is configured")
    app.add_middleware(
        SignedRequestASGIMiddleware,
        public_key_b64=key,
        identity_factory=identity_factory,
        replay_ledger=replay_ledger,
        scope_key=scope_key,
        max_body_bytes=max_body_bytes,
    )
    return True
