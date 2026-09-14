"""selftest — proves the box works with no test framework installed.

Run: ``python3 tests/selftest.py``. Exits non-zero on any failure.

Exists because the first question about a copied folder is "does this
actually work here", and the answer must not require installing a test
runner first. Covers the same invariants as the pytest suites, minus the
edge cases.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from devauth import (
    ReplayCache,
    SignedRequestASGIMiddleware,
    install_signed_request_auth,
    verify,
)

_FAILURES: list[str] = []


def check(label: str, condition: bool) -> None:
    if condition:
        print(f"  ok   {label}")
    else:
        print(f"  FAIL {label}")
        _FAILURES.append(label)


def _now(offset_seconds: float = 0.0) -> str:
    ts = datetime.now(timezone.utc) + timedelta(seconds=offset_seconds)
    return ts.isoformat().replace("+00:00", "Z")


def _sign(key: Ed25519PrivateKey, method: str, path: str, ts: str,
          slug: str = "", body: bytes = b"") -> str:
    canonical = (
        f"{method.upper()}\n{path}\n{ts}\n{slug.strip().lower()}\n"
        f"{hashlib.sha256(body).hexdigest()}"
    ).encode("ascii")
    return base64.b64encode(key.sign(canonical)).decode("ascii")


def main() -> int:
    key = Ed25519PrivateKey.generate()
    pub = base64.b64encode(
        key.public_key().public_bytes_raw()
    ).decode("ascii")

    print("verifier")
    ts = _now()
    sig = _sign(key, "GET", "/api/sessions", ts)
    r = verify(public_key_b64=pub, method="GET", path_and_query="/api/sessions",
               ts=ts, sig_b64=sig, body=b"")
    check("valid signature accepted", r.ok)

    r = verify(public_key_b64=pub, method="POST", path_and_query="/api/sessions",
               ts=ts, sig_b64=sig, body=b"")
    check("tampered method rejected", not r.ok)

    r = verify(public_key_b64=pub, method="GET", path_and_query="/api/admin",
               ts=ts, sig_b64=sig, body=b"")
    check("tampered path rejected", not r.ok)

    r = verify(public_key_b64=pub, method="GET", path_and_query="/api/sessions",
               ts=ts, sig_b64=sig, body=b"x")
    check("tampered body rejected", not r.ok)

    stale = _now(-600)
    r = verify(public_key_b64=pub, method="GET", path_and_query="/api/sessions",
               ts=stale, sig_b64=_sign(key, "GET", "/api/sessions", stale),
               body=b"")
    check("stale timestamp rejected", not r.ok)

    future = _now(600)
    r = verify(public_key_b64=pub, method="GET", path_and_query="/api/sessions",
               ts=future, sig_b64=_sign(key, "GET", "/api/sessions", future),
               body=b"")
    check("future timestamp rejected", not r.ok)

    other = Ed25519PrivateKey.generate()
    r = verify(public_key_b64=pub, method="GET", path_and_query="/api/sessions",
               ts=ts, sig_b64=_sign(other, "GET", "/api/sessions", ts), body=b"")
    check("wrong key rejected", not r.ok)

    r = verify(public_key_b64="", method="GET", path_and_query="/api/sessions",
               ts=ts, sig_b64=sig, body=b"")
    check("empty public key rejected", not r.ok)

    ts2 = _now()
    bad_slug = "probe/../admin"
    r = verify(public_key_b64=pub, method="GET", path_and_query="/x", ts=ts2,
               sig_b64=_sign(key, "GET", "/x", ts2, bad_slug), body=b"",
               user_slug=bad_slug)
    check("path-traversal slug rejected (G4)", not r.ok)

    ts3 = _now()
    r = verify(public_key_b64=pub, method="GET", path_and_query="/x", ts=ts3,
               sig_b64=_sign(key, "GET", "/x", ts3, "Alice"), body=b"",
               user_slug="Alice")
    check("slug normalised to lowercase", r.ok and r.user_slug == "alice")

    r = verify(public_key_b64=pub, method="GET", path_and_query="/api/sessions",
               ts=ts, sig_b64=sig, body=b"")
    check("no reason code leaks on failure", not hasattr(r, "reason"))

    print("replay cache")
    cache = ReplayCache(ttl_seconds=300.0)
    check("first use accepted", cache.check_and_record("sig-a") is True)
    check("second use rejected (G5)", cache.check_and_record("sig-a") is False)
    check("distinct signature accepted", cache.check_and_record("sig-b") is True)

    print("middleware")
    asyncio.run(_middleware_checks(key, pub))

    print()
    if _FAILURES:
        print(f"FAILED: {len(_FAILURES)} check(s)")
        for f in _FAILURES:
            print(f"  - {f}")
        return 1
    print("all checks passed")
    return 0


async def _call(mw, scope: dict, body: bytes = b"") -> tuple[int, bool]:
    """Drive the middleware once; return (status, inner_app_reached)."""
    sent: list[dict] = []
    reached = False

    async def receive() -> dict:
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message: dict) -> None:
        sent.append(message)

    async def inner(scope_, receive_, send_) -> None:
        nonlocal reached
        reached = True
        await receive_()  # prove the body is replayable
        await send_({"type": "http.response.start", "status": 200,
                     "headers": []})
        await send_({"type": "http.response.body", "body": b"ok"})

    mw._app = inner
    await mw(scope, receive, send)
    status = next((m["status"] for m in sent if m["type"] ==
                   "http.response.start"), 0)
    return status, reached


async def _middleware_checks(key: Ed25519PrivateKey, pub: str) -> None:
    seen: dict[str, object] = {}

    def factory(slug: str) -> str:
        principal = f"user:{slug or 'default'}"
        seen["principal"] = principal
        return principal

    def build(pk: str):
        return SignedRequestASGIMiddleware(
            None, public_key_b64=pk, identity_factory=factory,
            replay_cache=ReplayCache(ttl_seconds=300.0))

    def scope(method: str, raw_path: bytes, headers: list, query: bytes = b""):
        return {"type": "http", "method": method, "raw_path": raw_path,
                "path": raw_path.decode("latin-1"), "query_string": query,
                "headers": headers}

    ts = _now()
    sig = _sign(key, "GET", "/api/sessions", ts)
    hdrs = [(b"x-request-timestamp", ts.encode()),
            (b"x-request-signature", sig.encode())]
    status, reached = await _call(build(pub), scope("GET", b"/api/sessions", hdrs))
    check("signed request reaches app", status == 200 and reached)
    check("principal attached via factory", seen.get("principal") == "user:default")

    status, reached = await _call(build(pub),
                                  scope("GET", b"/api/sessions", []))
    check("unsigned request passes through untouched", status == 200 and reached)

    bad = [(b"x-request-timestamp", ts.encode()),
           (b"x-request-signature", b"AAAA")]
    status, reached = await _call(build(pub), scope("GET", b"/api/sessions", bad))
    check("bad signature -> 401, app never reached", status == 401 and not reached)

    # The empty-key off switch lives in install_signed_request_auth, NOT in the
    # middleware class -- see GOTCHAS.md G11.
    class _FakeApp:
        def __init__(self) -> None:
            self.mounted: list[tuple] = []

        def add_middleware(self, cls, **kwargs) -> None:
            self.mounted.append((cls, kwargs))

    off = _FakeApp()
    mounted_off = install_signed_request_auth(
        off, public_key_b64="", identity_factory=factory)
    check("empty key -> nothing mounted",
          mounted_off is False and off.mounted == [])

    on = _FakeApp()
    mounted_on = install_signed_request_auth(
        on, public_key_b64=pub, identity_factory=factory)
    check("configured key -> mounted once",
          mounted_on is True and len(on.mounted) == 1)

    ws = _FakeApp()
    install_signed_request_auth(
        ws, public_key_b64=f"  {pub}  ", identity_factory=factory)
    check("key whitespace stripped at mount",
          bool(ws.mounted) and ws.mounted[0][1]["public_key_b64"] == pub)

    # G1: raw_path carries the encoded form the client signed.
    encoded = "/api/topology/A%0AB"
    ts_g1 = _now()
    hdrs_g1 = [(b"x-request-timestamp", ts_g1.encode()),
               (b"x-request-signature",
                _sign(key, "GET", encoded, ts_g1).encode())]
    sc = {"type": "http", "method": "GET", "raw_path": encoded.encode("latin-1"),
          "path": "/api/topology/A\nB", "query_string": b"", "headers": hdrs_g1}
    status, reached = await _call(build(pub), sc)
    check("percent-encoded path verifies via raw_path (G1)",
          status == 200 and reached)

    # Query string participates in the signature.
    ts_q = _now()
    hdrs_q = [(b"x-request-timestamp", ts_q.encode()),
              (b"x-request-signature",
               _sign(key, "GET", "/api/sessions?limit=10", ts_q).encode())]
    sc = scope("GET", b"/api/sessions", hdrs_q, query=b"limit=10")
    status, reached = await _call(build(pub), sc)
    check("query string included in canonical string", status == 200 and reached)

    # Body is hashed, and replayed to the inner app.
    body = b'{"content":"hi"}'
    ts_b = _now()
    hdrs_b = [(b"x-request-timestamp", ts_b.encode()),
              (b"x-request-signature",
               _sign(key, "POST", "/api/chat", ts_b, body=body).encode())]
    status, reached = await _call(build(pub), scope("POST", b"/api/chat", hdrs_b),
                                  body=body)
    check("signed POST body verifies and replays", status == 200 and reached)

    # Replay rejection across two calls sharing one cache.
    mw = build(pub)
    ts_r = _now()
    sig_r = _sign(key, "GET", "/api/sessions", ts_r)
    hdrs_r = [(b"x-request-timestamp", ts_r.encode()),
              (b"x-request-signature", sig_r.encode())]
    s1, _ = await _call(mw, scope("GET", b"/api/sessions", hdrs_r))
    s2, r2 = await _call(mw, scope("GET", b"/api/sessions", hdrs_r))
    check("replayed signature -> 401 (G5)", s1 == 200 and s2 == 401 and not r2)


if __name__ == "__main__":
    raise SystemExit(main())
