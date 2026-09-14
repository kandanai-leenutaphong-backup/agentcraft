"""Transport invariants: activation gate, pass-through, replay, body replay.

These cover the properties that make the middleware safe to leave mounted:
it must be invisible when not addressed, and identical to no-auth when it
refuses.
"""

from __future__ import annotations

import base64
import hashlib
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from devauth import (
    ReplayCache,
    SignedRequestASGIMiddleware,
    install_signed_request_auth,
)


def _ts(offset: float = 0.0) -> str:
    return (datetime.now(timezone.utc)
            + timedelta(seconds=offset)).isoformat().replace("+00:00", "Z")


def _sign(key, method, path, ts, slug="", body=b"") -> str:
    canonical = (
        f"{method.upper()}\n{path}\n{ts}\n{slug.strip().lower()}\n"
        f"{hashlib.sha256(body).hexdigest()}"
    ).encode("ascii")
    return base64.b64encode(key.sign(canonical)).decode("ascii")


@pytest.fixture
def keypair():
    key = Ed25519PrivateKey.generate()
    return key, base64.b64encode(
        key.public_key().public_bytes_raw()).decode("ascii")


class Harness:
    """Minimal ASGI driver: records status and whether the app was reached."""

    def __init__(self, pub: str):
        self.reached = False
        self.body_seen: bytes | None = None
        self.principal = None
        self.mw = SignedRequestASGIMiddleware(
            self._inner,
            public_key_b64=pub,
            identity_factory=self._factory,
            replay_cache=ReplayCache(ttl_seconds=300.0),
        )

    def _factory(self, slug: str) -> str:
        self.principal = f"user:{slug or 'default'}"
        return self.principal

    async def _inner(self, scope, receive, send):
        self.reached = True
        message = await receive()
        self.body_seen = message.get("body")
        await send({"type": "http.response.start", "status": 200,
                    "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    async def call(self, method="GET", raw_path=b"/a", headers=None,
                   query=b"", body=b"", path=None) -> int:
        sent = []

        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}

        async def send(message):
            sent.append(message)

        scope = {"type": "http", "method": method, "raw_path": raw_path,
                 "path": path or raw_path.decode("latin-1"),
                 "query_string": query, "headers": headers or []}
        await self.mw(scope, receive, send)
        return next(m["status"] for m in sent
                    if m["type"] == "http.response.start")


def _headers(key, method, path, ts=None, slug=None, body=b""):
    ts = ts or _ts()
    hdrs = [(b"x-request-timestamp", ts.encode()),
            (b"x-request-signature",
             _sign(key, method, path, ts, slug or "", body).encode())]
    if slug:
        hdrs.append((b"x-request-context", slug.encode()))
    return hdrs


@pytest.mark.asyncio
async def test_signed_request_reaches_app_with_principal(keypair):
    key, pub = keypair
    h = Harness(pub)
    assert await h.call(headers=_headers(key, "GET", "/a")) == 200
    assert h.reached and h.principal == "user:default"


@pytest.mark.asyncio
async def test_unsigned_request_passes_through_untouched(keypair):
    """No signing headers means the primary auth path must see the request."""
    _, pub = keypair
    h = Harness(pub)
    assert await h.call(headers=[]) == 200
    assert h.reached and h.principal is None


@pytest.mark.asyncio
async def test_bad_signature_returns_bare_401(keypair):
    _, pub = keypair
    h = Harness(pub)
    hdrs = [(b"x-request-timestamp", _ts().encode()),
            (b"x-request-signature", b"AAAA")]
    assert await h.call(headers=hdrs) == 401
    assert h.reached is False


@pytest.mark.asyncio
async def test_raw_path_used_not_decoded_path(keypair):
    """G1: the client signs the encoded path it actually sent."""
    key, pub = keypair
    encoded = "/api/topology/A%0AB"
    h = Harness(pub)
    status = await h.call(raw_path=encoded.encode("latin-1"),
                          path="/api/topology/A\nB",
                          headers=_headers(key, "GET", encoded))
    assert status == 200


@pytest.mark.asyncio
async def test_query_string_participates_in_signature(keypair):
    key, pub = keypair
    h = Harness(pub)
    status = await h.call(raw_path=b"/a", query=b"limit=10",
                          headers=_headers(key, "GET", "/a?limit=10"))
    assert status == 200


@pytest.mark.asyncio
async def test_body_is_hashed_and_replayed_downstream(keypair):
    key, pub = keypair
    body = b'{"content":"hi"}'
    h = Harness(pub)
    status = await h.call(method="POST", raw_path=b"/chat", body=body,
                          headers=_headers(key, "POST", "/chat", body=body))
    assert status == 200
    assert h.body_seen == body


@pytest.mark.asyncio
async def test_context_slug_reaches_identity_factory(keypair):
    key, pub = keypair
    h = Harness(pub)
    status = await h.call(headers=_headers(key, "GET", "/a", slug="alice"))
    assert status == 200 and h.principal == "user:alice"


@pytest.mark.asyncio
async def test_replayed_signature_rejected(keypair):
    """G5: no nonce in the signing material, so the cache is the defence."""
    key, pub = keypair
    h = Harness(pub)
    hdrs = _headers(key, "GET", "/a")
    assert await h.call(headers=hdrs) == 200
    h.reached = False
    assert await h.call(headers=hdrs) == 401
    assert h.reached is False


def test_replay_cache_rejects_second_use():
    cache = ReplayCache(ttl_seconds=300.0)
    assert cache.check_and_record("s") is True
    assert cache.check_and_record("s") is False
    assert cache.check_and_record("other") is True


class _FakeApp:
    def __init__(self):
        self.mounted = []

    def add_middleware(self, cls, **kwargs):
        self.mounted.append((cls, kwargs))


def test_empty_key_mounts_nothing(keypair):
    """G11: the off switch lives here, not in the middleware class."""
    app = _FakeApp()
    assert install_signed_request_auth(
        app, public_key_b64="", identity_factory=lambda s: s) is False
    assert app.mounted == []


def test_configured_key_mounts_once(keypair):
    _, pub = keypair
    app = _FakeApp()
    assert install_signed_request_auth(
        app, public_key_b64=pub, identity_factory=lambda s: s) is True
    assert len(app.mounted) == 1
    assert app.mounted[0][1]["public_key_b64"] == pub


def test_key_whitespace_stripped_at_mount(keypair):
    _, pub = keypair
    app = _FakeApp()
    install_signed_request_auth(app, public_key_b64=f"\n {pub} \n",
                                identity_factory=lambda s: s)
    assert app.mounted[0][1]["public_key_b64"] == pub
