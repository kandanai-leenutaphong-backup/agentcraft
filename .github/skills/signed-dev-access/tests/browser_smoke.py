#!/usr/bin/env python3
"""browser_smoke — pilot a real application in a real Chromium, and prove it.

WHAT THIS IS FOR
----------------
``selftest.py`` and the pytest suite prove the crypto and the middleware
offline, in-process. They cannot prove the thing the box actually claims: that
an agent can drive a *whole deployed application* — document, assets and APIs —
through a real browser, with every request individually signed, without handing
its credential to anybody else.

That claim needs a browser, so this file is separate and **opt-in**. It is not
imported by the offline suites, and it is not a pytest module: an absent
Playwright must fail loudly here rather than vanish as a skipped test that reads
green.

WHAT IT PROVES, AND HOW
-----------------------
It stands up two origins on ephemeral ports:

  * the **application**, composing ``entraauth`` (bearer tokens, ownership) with
    ``devauth`` (signed requests) through ``examples/entra_composition.py``;
  * a **spy origin**, an unrelated third party that records every header it is
    sent and is never trusted by the pilot.

Then it drives the application in Chromium and checks, among others:

  * the protected HTML document and its CSS/JS assets load, signed — not the
    ``/api``-only signing that leaves a real app blank;
  * a UI button performs a POST that changes server state, confirmed by an
    independent server-side read-back rather than by the UI that caused it;
  * the same button pressed repeatedly keeps working, which is what a
    second-granularity timestamp would break by colliding with the replay guard;
  * a page ``fetch()`` to the spy origin, and a redirect that *lands* on the spy
    origin, arrive there with no signing headers at all;
  * a signature captured from a real browser request, replayed exactly, is
    refused;
  * anonymous, forged, tampered and expired requests are all refused;
  * a genuine Entra bearer token works over the same routes, with the same
    ownership rules, against locally minted issuer keys.

NO CLOUD. NO TENANT. Nothing here reaches the network: both servers are on
127.0.0.1, the Entra key set is minted in-process, and the operator key lives in
a temporary directory that is deleted on the way out. ``~/.devauth`` is never
read or written.

RUN IT
------
    python3 -m pip install '.[browser]' /explicit/path/to/azure-access-management/compatibility/api-auth
    python3 -m playwright install chromium
    python3 tests/browser_smoke.py --out /tmp/pilot-evidence

Exit code 0 means every check passed. The run writes ``result.json`` plus a
desktop and a mobile screenshot into ``--out``.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import shutil
import socket
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import Request

_ROOT = Path(__file__).resolve().parents[1]

# dev_sign resolves its key directory at import time, so the redirect to a
# temporary key has to happen before the import below. A smoke test must never
# touch the operator's real ~/.devauth.
_KEY_DIR = Path(tempfile.mkdtemp(prefix="devauth-smoke-"))
os.environ["DEVAUTH_KEY_DIR"] = str(_KEY_DIR)

for _p in (_ROOT, _ROOT / "examples", _ROOT / "scripts"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import dev_sign  # noqa: E402
import entra_composition  # noqa: E402
from browser_pilot import SIGNING_HEADERS, new_piloted_context  # noqa: E402

import entraauth as ea  # noqa: E402

TENANT = "11111111-2222-3333-4444-555555555555"
CLIENT_ID = "66666666-7777-8888-9999-000000000000"
ISSUER = f"https://login.microsoftonline.com/{TENANT}/v2.0"
KID = "smoke-key-1"

DESKTOP = {"width": 1440, "height": 900}
MOBILE = {"width": 390, "height": 844}

# Gap between the two server-sent events. Long enough that "the first event
# arrived while the stream was still open" cannot be a scheduling accident,
# short enough not to pad the run.
STREAM_GAP_SECONDS = 1.5

_RESULTS: list[dict] = []


def check(label: str, ok: bool, detail: str = "") -> bool:
    _RESULTS.append({"check": label, "ok": bool(ok), "detail": detail})
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + (f"   [{detail}]" if detail else ""))
    return bool(ok)


# ── a local Entra, minted in-process ─────────────────────────────────────────


class FakeEntra:
    """Publishes a key set and mints tokens, exactly like the real endpoint."""

    def __init__(self) -> None:
        from cryptography.hazmat.primitives.asymmetric import rsa

        self.private_key = rsa.generate_private_key(public_exponent=65537,
                                                    key_size=2048)
        numbers = self.private_key.public_key().public_numbers()

        def b64(value: int) -> str:
            raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
            return base64.urlsafe_b64encode(raw).decode().rstrip("=")

        self.document = {"keys": [{"kty": "RSA", "kid": KID, "use": "sig",
                                   "n": b64(numbers.n), "e": b64(numbers.e)}]}

    async def fetcher(self, _url: str) -> dict:
        return self.document

    def token(self, **overrides) -> str:
        import jwt as pyjwt

        now = int(time.time())
        claims = {"iss": ISSUER, "aud": CLIENT_ID, "tid": TENANT,
                  "oid": "entra-user-1", "preferred_username": "person@example.test",
                  "name": "Test Person", "iat": now, "nbf": now, "exp": now + 3600,
                  "scp": "access_as_user", "idtyp": "user"}
        claims.update(overrides)
        claims = {k: v for k, v in claims.items() if v is not None}
        return pyjwt.encode(claims, self.private_key, algorithm="RS256",
                            headers={"kid": KID})


# ── the application under pilot ──────────────────────────────────────────────


PAGE = """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Signed pilot demo</title>
<link rel="stylesheet" href="/static/app.css">
</head><body>
<h1>Signed pilot demo</h1>
<p>Caller: <span data-testid="who">…</span></p>
<p>Records: <strong data-testid="records-count">…</strong></p>
<ul data-testid="records"></ul>
<button data-testid="add">Add record</button>
<button data-testid="probe-other">Read someone else's record</button>
<button data-testid="probe-spy">Call the other origin</button>
<button data-testid="probe-stream">Open a stream</button>
<button data-testid="probe-echo">Send an awkward path</button>
<button data-testid="probe-burst">Fire eight identical reads</button>
<p>Other record status: <span data-testid="other-status">…</span></p>
<p>Spy status: <span data-testid="spy-status">…</span></p>
<p>Stream status: <span data-testid="stream-status">…</span></p>
<p>Echo status: <span data-testid="echo-status">…</span></p>
<p>Burst status: <span data-testid="burst-status">…</span></p>
<a data-testid="offsite" href="/go-offsite">Leave via redirect</a>
<script src="/static/app.js"></script>
</body></html>
"""

# The awkward path is the G1 case driven through a real browser: encoded
# space, plus and apostrophe in the path, and an encoded space, plus and
# newline in the query. The signature covers the raw wire string, so any
# normalisation between signing and sending turns into a bare 401.
#
# The newline is deliberately in the query and not in a path segment.
# Starlette compiles ``{token:path}`` to ``(?P<token>.*)`` without DOTALL, so
# a decoded newline matches no route and returns 404 before authentication is
# ever consulted — a routing limit, not a signing one, and one that would
# otherwise read as a signature failure.
ECHO_PATH = "/api/echo/a%20b%2Bc%27d?q=%20%2B&nl=%0A&x=1"

APP_JS = """
const SPY = "__SPY_ORIGIN__";
const OTHER = "__OTHER_RECORD__";
const ECHO = "__ECHO_PATH__";
async function refresh() {
  const r = await fetch("/api/records");
  const data = await r.json();
  document.querySelector("[data-testid=records-count]").textContent = data.count;
  document.querySelector("[data-testid=records]").innerHTML =
    Object.keys(data.records).map(k => `<li data-testid="row">${k}</li>`).join("");
}
async function whoami() {
  const r = await fetch("/api/me");
  const me = await r.json();
  document.querySelector("[data-testid=who]").textContent = me.id;
}
document.querySelector("[data-testid=add]").addEventListener("click", async () => {
  await fetch("/api/records", {method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({title: "made in the browser"})});
  await refresh();
});
document.querySelector("[data-testid=probe-other]").addEventListener("click", async () => {
  const r = await fetch("/api/records/" + OTHER);
  document.querySelector("[data-testid=other-status]").textContent = r.status;
});
document.querySelector("[data-testid=probe-spy]").addEventListener("click", async () => {
  try {
    const r = await fetch(SPY + "/spy/from-page");
    document.querySelector("[data-testid=spy-status]").textContent = r.status;
  } catch (e) {
    document.querySelector("[data-testid=spy-status]").textContent = "blocked: " + e.message;
  }
});
document.querySelector("[data-testid=probe-stream]").addEventListener("click", () => {
  const t0 = performance.now();
  window.__stream = {first: null, end: null};
  const es = new EventSource("/api/stream");
  es.onmessage = (e) => {
    if (window.__stream.first === null) window.__stream.first = performance.now() - t0;
    if (e.data === "done") {
      window.__stream.end = performance.now() - t0;
      es.close();
      document.querySelector("[data-testid=stream-status]").textContent = "done";
    }
  };
  es.onerror = () => {
    es.close();
    document.querySelector("[data-testid=stream-status]").textContent = "error";
  };
});
document.querySelector("[data-testid=probe-echo]").addEventListener("click", async () => {
  const r = await fetch(ECHO);
  let seen = "";
  try { seen = (await r.json()).path_and_query || ""; } catch (e) { seen = ""; }
  window.__echo = {status: r.status, path_and_query: seen};
  document.querySelector("[data-testid=echo-status]").textContent = r.status;
});
document.querySelector("[data-testid=probe-burst]").addEventListener("click", async () => {
  const rs = await Promise.all(Array.from({length: 8}, () => fetch("/api/me")));
  window.__burst = rs.map(r => r.status);
  document.querySelector("[data-testid=burst-status]").textContent =
    window.__burst.join(",");
});
whoami(); refresh();
"""

APP_CSS = "body{font-family:system-ui;margin:2rem;max-width:40rem}button{margin:.25rem}"


class WireRecorder:
    """Records what the server actually received, and adds ``no-store``.

    Two jobs, both structural rather than incidental.

    The signing headers the pilot injects are applied inside the browser's
    network stack, *after* the point Playwright's ``Request`` object is
    built — measured: a request whose signature the server verified showed
    no signing header at all on ``request.all_headers()``. So the only
    honest place to capture a real browser signature, and the only place a
    replay test can source one from, is the server that received it.

    Pure ASGI on purpose. ``BaseHTTPMiddleware`` sits between the endpoint
    and the transport and would make the streaming measurement below prove
    nothing about the middleware under test.
    """

    def __init__(self, app, *, sink: list) -> None:
        self._app = app
        self._sink = sink

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        headers = {k.decode("latin-1").lower(): v.decode("latin-1")
                   for k, v in scope.get("headers", [])}
        raw_path = scope.get("raw_path")
        path_q = (raw_path.decode("latin-1")
                  if isinstance(raw_path, (bytes, bytearray))
                  else scope.get("path", ""))
        qs = scope.get("query_string") or b""
        if qs:
            path_q = f"{path_q}?{qs.decode('latin-1')}"
        entry = {"method": scope.get("method", ""), "path_and_query": path_q,
                 "signing_headers": {k: v for k, v in headers.items()
                                     if k in SIGNING_HEADERS},
                 "status": None}
        self._sink.append(entry)

        async def send_wrapper(message) -> None:
            if message["type"] == "http.response.start":
                entry["status"] = message["status"]
                message = dict(message)
                message["headers"] = [*message.get("headers", []),
                                      (b"cache-control", b"no-store, private")]
            await send(message)

        await self._app(scope, receive, send_wrapper)


def build_app(entra: FakeEntra, records: dict, config: dict, public_key_b64: str,
              wire: list):
    """Compose the application. The only place either auth path is wired."""
    from fastapi import Depends, FastAPI
    from fastapi.responses import (HTMLResponse, RedirectResponse, Response,
                                   StreamingResponse)

    app = FastAPI(title="signed pilot demo")

    auth = ea.AuthConfig(enabled=True, tenant_id=TENANT, client_id=CLIENT_ID)
    validator = ea.install_auth(app, auth, fetcher=entra.fetcher)
    current = ea.principal_dependency(validator)
    policy = ea.OwnershipPolicy()

    # The composition seam under test: signed requests land on the scope key
    # entraauth reads, carrying an entraauth Principal.
    mounted = entra_composition.install(app, public_key_b64=public_key_b64)
    config["signed_access_mounted"] = mounted

    # Added last, so it is outermost and sees the request exactly as it
    # arrived — before the signed middleware buffers and replays the body.
    app.add_middleware(WireRecorder, sink=wire)

    @app.get("/", response_class=HTMLResponse)
    async def index(_p: ea.Principal = Depends(current)) -> HTMLResponse:
        return HTMLResponse(PAGE)

    @app.get("/static/app.css")
    async def css(_p: ea.Principal = Depends(current)) -> Response:
        return Response(APP_CSS, media_type="text/css")

    @app.get("/static/app.js")
    async def js(_p: ea.Principal = Depends(current)) -> Response:
        body = (APP_JS.replace("__SPY_ORIGIN__", config["spy_origin"])
                      .replace("__OTHER_RECORD__", config["other_record"])
                      .replace("__ECHO_PATH__", ECHO_PATH))
        return Response(body, media_type="application/javascript")

    @app.get("/api/me")
    async def me(principal: ea.Principal = Depends(current)) -> dict:
        return {"id": principal.id, "kind": principal.kind,
                "kind_certain": principal.kind_certain,
                "proven": not principal.is_developer,
                "scopes": list(principal.scopes), "roles": list(principal.roles)}

    @app.get("/api/records")
    async def list_records(principal: ea.Principal = Depends(current)) -> dict:
        visible = {k: v for k, v in records.items()
                   if policy.can_read(v["owner_id"], principal)}
        return {"records": visible, "count": len(visible)}

    @app.get("/api/records/{record_id}")
    async def get_record(record_id: str,
                         principal: ea.Principal = Depends(current)) -> dict:
        record = records.get(record_id)
        if record is None:
            raise ea.NotFoundError(resource_id=record_id)
        policy.assert_readable(record["owner_id"], principal, record_id)
        return record

    @app.post("/api/records")
    async def create_record(body: dict,
                            principal: ea.Principal = Depends(current)) -> dict:
        record_id = f"{principal.id}-{len(records)}"
        records[record_id] = {"owner_id": principal.id,
                              "title": str(body.get("title", "untitled"))}
        return {"created": record_id}

    @app.get("/api/echo/{token:path}")
    async def echo(request: Request,
                   _p: ea.Principal = Depends(current)) -> dict:
        # Hand back the raw wire string the server reconstructed, so the test
        # can compare it against exactly what the pilot signed.
        raw = request.scope.get("raw_path")
        path_q = (raw.decode("latin-1") if isinstance(raw, (bytes, bytearray))
                  else request.scope.get("path", ""))
        qs = request.scope.get("query_string") or b""
        if qs:
            path_q = f"{path_q}?{qs.decode('latin-1')}"
        return {"path_and_query": path_q}

    @app.get("/api/stream")
    async def stream(_p: ea.Principal = Depends(current)) -> StreamingResponse:
        # The signed middleware buffers the request body but must never
        # buffer the response; STREAM_GAP_SECONDS separates the two events
        # far enough that a buffered pipeline is unmistakable in the timings.
        async def events():
            yield b"data: first\n\n"
            await asyncio.sleep(STREAM_GAP_SECONDS)
            yield b"data: done\n\n"

        return StreamingResponse(events(), media_type="text/event-stream")

    @app.get("/go-offsite")
    async def go_offsite(_p: ea.Principal = Depends(current)) -> RedirectResponse:
        # A redirect that leaves the trusted origin. The browser replays request
        # headers across a redirect, so this is where a signature escapes if the
        # interceptor filters by path instead of by origin.
        return RedirectResponse(config["spy_origin"] + "/spy/redirected",
                                status_code=307)

    @app.get("/go-home")
    async def go_home(_p: ea.Principal = Depends(current)) -> RedirectResponse:
        # The other half of the redirect story, and the half a header-replaying
        # interceptor fails: the hop stays on the trusted origin, so it must be
        # re-signed for its OWN path. A signature minted for /go-home is not
        # valid for /api/me, and arrives as a bare 401.
        return RedirectResponse("/api/me", status_code=307)

    return app


class SpyApp:
    """An unrelated origin. Records exactly what it was sent, trusts nothing."""

    def __init__(self) -> None:
        self.seen: list[dict] = []
        self.origin = ""

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            return
        headers = {k.decode("latin-1").lower(): v.decode("latin-1")
                   for k, v in scope.get("headers", [])}
        self.seen.append({"path": scope.get("path", ""),
                          "method": scope.get("method", ""),
                          "headers": headers})
        body = b'{"spy":"reached"}'
        await send({"type": "http.response.start", "status": 200, "headers": [
            (b"content-type", b"application/json"),
            (b"access-control-allow-origin", b"*"),
            (b"cache-control", b"no-store"),
            (b"content-length", str(len(body)).encode()),
        ]})
        await send({"type": "http.response.body", "body": body})

    def signing_headers_seen(self) -> list[str]:
        from browser_pilot import SIGNING_HEADERS

        return sorted({name for entry in self.seen for name in entry["headers"]
                       if name in SIGNING_HEADERS})


# ── servers on pre-bound sockets ─────────────────────────────────────────────


class LocalServer:
    """A uvicorn server on an already-listening socket.

    Binding before the thread starts is what removes the readiness race: the
    port is accepting connections from the moment it exists, so a client can
    connect immediately and there is nothing to poll or sleep on.
    """

    def __init__(self, app, *, lifespan: str = "auto") -> None:
        import uvicorn

        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(128)
        self.port = self._sock.getsockname()[1]
        self.origin = f"http://127.0.0.1:{self.port}"
        config = uvicorn.Config(app, log_level="warning", lifespan=lifespan,
                                access_log=False)
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(
            target=self._server.run, kwargs={"sockets": [self._sock]},
            name=f"smoke-{self.port}", daemon=True)

    def start(self) -> "LocalServer":
        self._thread.start()
        return self

    def stop(self) -> bool:
        """Ask the server to exit and wait for the thread. True when it left."""
        self._server.should_exit = True
        self._thread.join(timeout=15)
        stopped = not self._thread.is_alive()
        try:
            self._sock.close()
        except OSError:
            pass
        return stopped


# ── direct HTTP, for the probes a browser cannot express ─────────────────────


def http(method: str, url: str, headers: dict | None = None,
         body: bytes | None = None) -> tuple[int, str]:
    request = urllib.request.Request(url, data=body, method=method,
                                     headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")


def signed(method: str, origin: str, path_q: str, slug: str = "",
           body: bytes = b"") -> tuple[int, str]:
    headers = dev_sign.sign_headers(method, path_q, body, slug)
    if body:
        headers["Content-Type"] = "application/json"
    return http(method, origin + path_q, headers, body or None)


def hostile_headers(*, method: str, path_q: str, body: bytes = b"",
                    slug: str = "", key=None, ts: str | None = None) -> dict:
    """Mint signing headers with one ingredient deliberately wrong.

    Uses dev_sign's own canonical string so a hostile case can never pass or
    fail because the test drifted from the wire contract.
    """
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    signing_key = key or Ed25519PrivateKey.generate()
    stamp = ts or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    message = dev_sign._canonical(method=method, path_and_query=path_q, ts=stamp,
                                  context_slug=slug, body=body)
    out = {"X-Request-Timestamp": stamp,
           "X-Request-Signature": base64.b64encode(
               signing_key.sign(message)).decode("ascii")}
    if slug:
        out["X-Request-Context"] = slug
    return out


# ── the pilot ────────────────────────────────────────────────────────────────


def pilot(app_origin: str, spy: SpyApp, wire: list, out_dir: Path,
          headed: bool) -> dict:
    """Drive the application in Chromium. Returns the observation record."""
    from playwright.sync_api import sync_playwright

    observed: list[dict] = []
    shots: dict[str, str] = {}
    console: list[str] = []
    failures: list[dict] = []

    def signed_wire(path_prefix: str) -> list[dict]:
        """Requests the SERVER received carrying signing headers.

        The only trustworthy source for a real browser signature: the pilot
        injects headers below the layer Playwright models, so
        ``request.all_headers()`` never shows them.
        """
        return [e for e in wire
                if e["path_and_query"].startswith(path_prefix)
                and e["signing_headers"].get("x-request-signature")]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not headed)
        try:
            context = new_piloted_context(
                browser, origin=app_origin, context_slug="alice",
                on_request=observed.append, viewport=DESKTOP)

            page = context.new_page()
            # A cross-origin fetch that never arrives, or an interceptor that
            # dies mid-flight, otherwise shows up only as an empty DOM. Keep
            # the browser's own reason.
            page.on("console", lambda m: console.append(f"{m.type}: {m.text}")
                    if m.type in ("error", "warning") else None)
            page.on("requestfailed", lambda r: failures.append(
                {"url": r.url, "failure": r.failure or ""}))

            print("\nreal browser, real application")
            response = page.goto(f"{app_origin}/", wait_until="networkidle")
            check("protected HTML document loads", response.status == 200,
                  f"status={response.status}")
            check("the caller is the signed identity",
                  page.text_content("[data-testid=who]") == "devkey-alice",
                  page.text_content("[data-testid=who]") or "")

            styled = page.eval_on_selector(
                "body", "el => getComputedStyle(el).maxWidth")
            check("protected CSS asset applied", styled == "640px", styled)
            check("protected JS asset ran",
                  page.text_content("[data-testid=records-count]") not in (None, "…"),
                  page.text_content("[data-testid=records-count]") or "")

            signed_paths = {o["url"].replace(app_origin, "")
                            for o in observed if o["signed"]}
            check("the document itself was signed", "/" in signed_paths)
            check("the CSS asset was signed", "/static/app.css" in signed_paths)
            check("the JS asset was signed", "/static/app.js" in signed_paths)

            print("\nrepeated ordinary operations")
            before = int(page.text_content("[data-testid=records-count]"))
            for _ in range(3):
                page.click("[data-testid=add]")
                page.wait_for_function(
                    "([n]) => document.querySelector('[data-testid=records-count]')"
                    ".textContent !== String(n)", arg=[before])
                before = int(page.text_content("[data-testid=records-count]"))
            after = int(page.text_content("[data-testid=records-count]"))
            check("three consecutive POSTs all succeeded", after >= 3,
                  f"count={after}")

            # Eight byte-identical GETs inside one second. A second-precision
            # timestamp makes their canonical strings identical, so the replay
            # guard eats seven of them (G12).
            page.click("[data-testid=probe-burst]")
            page.wait_for_function("() => window.__burst !== undefined")
            burst = page.evaluate("() => window.__burst")
            check("eight identical reads in the same second all succeeded",
                  burst == [200] * 8, str(burst))
            burst_wire = signed_wire("/api/me")
            burst_sigs = {e["signing_headers"]["x-request-signature"]
                          for e in burst_wire}
            check("each carried a distinct signature",
                  len(burst_sigs) == len(burst_wire),
                  f"{len(burst_sigs)} distinct of {len(burst_wire)}")

            print("\nownership holds through the UI")
            page.click("[data-testid=probe-other]")
            page.wait_for_function(
                "() => document.querySelector('[data-testid=other-status]')"
                ".textContent !== '…'")
            other = page.text_content("[data-testid=other-status]")
            check("another identity's record is 404, not 403", other == "404", other)

            print("\nthe raw path is what gets signed")
            page.click("[data-testid=probe-echo]")
            page.wait_for_function("() => window.__echo !== undefined")
            echo = page.evaluate("() => window.__echo")
            check("a percent-encoded path and query verifies",
                  echo.get("status") == 200, str(echo.get("status")))
            signed_echo = next((o for o in observed
                                if "/api/echo/" in o["url"] and o["signed"]), None)
            pilot_signed_path = (signed_echo["url"].replace(app_origin, "")
                                 if signed_echo else "")
            check("the server reconstructed exactly the string the pilot signed",
                  bool(pilot_signed_path)
                  and echo.get("path_and_query") == pilot_signed_path,
                  f"signed={pilot_signed_path!r} server={echo.get('path_and_query')!r}")

            print("\na signed stream still streams")
            page.click("[data-testid=probe-stream]")
            page.wait_for_function(
                "() => window.__stream && window.__stream.end !== null",
                timeout=30000)
            stream = page.evaluate("() => window.__stream")
            first_ms, end_ms = stream.get("first"), stream.get("end")
            gap_ms = STREAM_GAP_SECONDS * 1000
            check("the first event arrived before the stream finished",
                  first_ms is not None and end_ms is not None
                  and (end_ms - first_ms) > gap_ms * 0.6,
                  f"first={first_ms:.0f}ms end={end_ms:.0f}ms")
            check("and it arrived promptly, not at completion",
                  first_ms is not None and first_ms < gap_ms * 0.5,
                  f"first={first_ms:.0f}ms")
            check("the stream request was signed",
                  bool(signed_wire("/api/stream")))

            print("\nthe signature never leaves the trusted origin")
            page.click("[data-testid=probe-spy]")
            page.wait_for_function(
                "() => document.querySelector('[data-testid=spy-status]')"
                ".textContent !== '…'")
            check("the page did reach the other origin",
                  any(e["path"] == "/spy/from-page" for e in spy.seen),
                  page.text_content("[data-testid=spy-status]") or "")

            shots["desktop"] = str(out_dir / "desktop.png")
            page.screenshot(path=shots["desktop"], full_page=True)

            print("\nredirects, both directions")
            home = page.goto(f"{app_origin}/go-home",
                             wait_until="domcontentloaded")
            check("a redirect that stays on the trusted origin still verifies",
                  home.status == 200, f"status={home.status}")
            check("and lands where it said it would",
                  home.url == f"{app_origin}/api/me", home.url)
            hop_out = signed_wire("/go-home")
            hop_in = signed_wire("/api/me")
            check("both legs of the same-origin redirect were signed",
                  bool(hop_out) and len(hop_in) > len(burst_wire),
                  f"{len(hop_out)} out, {len(hop_in) - len(burst_wire)} in")
            check("the second leg was re-signed, not replayed",
                  bool(hop_out) and bool(hop_in)
                  and hop_out[-1]["signing_headers"]["x-request-signature"]
                  != hop_in[-1]["signing_headers"]["x-request-signature"])

            redirected = page.goto(f"{app_origin}/go-offsite",
                                   wait_until="domcontentloaded")
            check("a redirect off-origin is followed",
                  redirected.url.startswith(spy.origin),
                  redirected.url)
            check("the redirected request reached the other origin",
                  any(e["path"] == "/spy/redirected" for e in spy.seen))

            leaked = spy.signing_headers_seen()
            check("no signing header ever reached the other origin",
                  leaked == [], ", ".join(leaked) or "none")
            cross = [o for o in observed if o["origin"] != app_origin]
            check("every cross-origin request was forwarded unsigned",
                  bool(cross) and all(not o["signed"] for o in cross),
                  f"{len(cross)} cross-origin requests")

            print("\na captured browser signature is single-use")
            capture = signed_wire("/api/records")
            check("a real browser signature was captured", bool(capture),
                  f"{len(capture)} signed requests recorded server-side")
            if capture:
                entry = capture[-1]
                replay = {k: v for k, v in entry["signing_headers"].items()}
                status, _ = http("GET", app_origin + entry["path_and_query"],
                                 replay)
                check("replaying it exactly is refused", status == 401,
                      f"status={status}")
                status, _ = http("GET", f"{app_origin}/api/me", replay)
                check("and it is worthless on any other path", status == 401,
                      f"status={status}")

            errored = [o for o in observed if o.get("error")]
            check("the pilot signed every request without error",
                  not errored, "; ".join(o["error"] for o in errored[:3]))
            # The stream is closed from the page once the last event arrives,
            # which Chromium reports as an aborted request. That one is the
            # test's own doing; anything else is not.
            unexpected = [f for f in failures
                          if not ("/api/stream" in f["url"]
                                  and "ERR_ABORTED" in f["failure"])]
            check("no request failed at the network layer, bar the closed stream",
                  not unexpected,
                  "; ".join(f"{f['url']} {f['failure']}" for f in unexpected[:3]))

            mobile = new_piloted_context(
                browser, origin=app_origin, context_slug="alice",
                viewport=MOBILE, is_mobile=True, has_touch=True,
                device_scale_factor=3)
            mobile_page = mobile.new_page()
            mobile_response = mobile_page.goto(f"{app_origin}/",
                                               wait_until="networkidle")
            check("the same pilot works at mobile width",
                  mobile_response.status == 200, f"status={mobile_response.status}")
            shots["mobile"] = str(out_dir / "mobile.png")
            mobile_page.screenshot(path=shots["mobile"], full_page=True)
            mobile.close()
            context.close()
        finally:
            browser.close()

    return {"observed": observed, "screenshots": shots,
            "console": console, "request_failures": failures,
            "stream_timings_ms": stream,
            "signed_request_count": sum(1 for o in observed if o["signed"]),
            "unsigned_request_count": sum(1 for o in observed
                                          if not o["signed"])}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default=None,
                        help="directory for result.json and screenshots")
    parser.add_argument("--headed", action="store_true",
                        help="show the browser window")
    args = parser.parse_args()

    out_dir = Path(args.out) if args.out else Path(
        tempfile.mkdtemp(prefix="pilot-evidence-"))
    out_dir.mkdir(parents=True, exist_ok=True)

    print("signed-dev-access browser smoke")
    print(f"  key dir     {_KEY_DIR}")
    print(f"  evidence    {out_dir}")

    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except ImportError:
        print("\nPlaywright is not installed. This test needs a real browser:\n"
              "    pip install playwright && python3 -m playwright install chromium\n"
              "It is deliberately not a skipped pytest case: an absent browser "
              "must not read as a passing browser proof.", file=sys.stderr)
        return 2

    public_key = dev_sign.cmd_init(argparse.Namespace(force=True))
    if public_key != 0:
        print("could not create a signing key", file=sys.stderr)
        return 2
    public_key_b64 = dev_sign._public_b64(dev_sign._load_private_key())

    entra = FakeEntra()
    records = {
        "alice-seed": {"owner_id": "devkey-alice", "title": "Alice's seed record"},
        "bob-seed": {"owner_id": "devkey-bob", "title": "Bob's record"},
        "entra-seed": {"owner_id": "entra-user-1", "title": "A real user's record"},
    }
    config: dict = {"other_record": "bob-seed"}

    spy_app = SpyApp()
    spy_server = LocalServer(spy_app, lifespan="off")
    spy_app.origin = spy_server.origin
    config["spy_origin"] = spy_server.origin

    # What the server actually received, in arrival order. The pilot's
    # signatures are applied below the layer Playwright models, so this is the
    # only place a real browser signature can be read back from.
    wire: list[dict] = []
    app = build_app(entra, records, config, public_key_b64, wire)
    app_server = LocalServer(app)

    spy_server.start()
    app_server.start()
    origin = app_server.origin
    print(f"  application {origin}")
    print(f"  other origin {spy_server.origin}")

    try:
        check("signed access mounted", config["signed_access_mounted"] is True)

        print("\nrefusals, before any browser is involved")
        status, _ = http("GET", f"{origin}/api/records")
        check("anonymous is refused", status == 401, f"status={status}")
        status, _ = http("GET", f"{origin}/")
        check("the document is protected too", status == 401, f"status={status}")

        status, _ = http("GET", f"{origin}/api/records",
                         hostile_headers(method="GET", path_q="/api/records"))
        check("a forged signature is refused", status == 401, f"status={status}")

        real_key = dev_sign._load_private_key()
        status, _ = http("GET", f"{origin}/api/records",
                         hostile_headers(method="GET", path_q="/api/other",
                                         key=real_key))
        check("a signature minted for another path is refused", status == 401,
              f"status={status}")

        stale = (datetime.now(timezone.utc) - timedelta(minutes=10)).strftime(
            "%Y-%m-%dT%H:%M:%S.%fZ")
        status, _ = http("GET", f"{origin}/api/records",
                         hostile_headers(method="GET", path_q="/api/records",
                                         key=real_key, ts=stale))
        check("an expired signature is refused", status == 401, f"status={status}")

        tampered = dev_sign.sign_headers("POST", "/api/records", b'{"title":"a"}',
                                         "alice")
        tampered["Content-Type"] = "application/json"
        status, _ = http("POST", f"{origin}/api/records", tampered,
                         b'{"title":"substituted"}')
        check("a substituted body is refused", status == 401, f"status={status}")

        print("\nsigned access, over the wire")
        status, body = http("GET", f"{origin}/api/me",
                            dev_sign.sign_headers("GET", "/api/me", b"", "alice"))
        payload = json.loads(body) if status == 200 else {}
        check("a signed request is accepted", status == 200, f"status={status}")
        check("it becomes the composed principal",
              payload.get("id") == "devkey-alice", str(payload.get("id")))
        check("marked service, not a proven human",
              payload.get("kind") == "service", str(payload.get("kind")))
        check("granted no scopes", payload.get("scopes") == [], str(payload.get("scopes")))
        check("granted no roles", payload.get("roles") == [], str(payload.get("roles")))

        status, _ = signed("GET", origin, "/api/records/alice-seed", "alice")
        check("the signed identity reads its own record", status == 200,
              f"status={status}")
        status, _ = signed("GET", origin, "/api/records/bob-seed", "alice")
        check("and gets 404 for another identity's", status == 404, f"status={status}")

        print("\nthe Entra path, on the same routes")
        bearer = {"Authorization": f"Bearer {entra.token()}"}
        status, body = http("GET", f"{origin}/api/me", bearer)
        payload = json.loads(body) if status == 200 else {}
        check("a real token is accepted", status == 200, f"status={status}")
        check("it is a user, stated by idtyp", payload.get("kind") == "user",
              str(payload.get("kind")))
        check("and the statement is certain", payload.get("kind_certain") is True)
        status, _ = http("GET", f"{origin}/api/records/entra-seed", bearer)
        check("the token owner reads its own record", status == 200, f"status={status}")
        status, _ = http("GET", f"{origin}/api/records/alice-seed", bearer)
        check("and gets 404 for the signed identity's", status == 404, f"status={status}")

        forged_bearer = {"Authorization": "Bearer " + entra.token()[:-6] + "AAAAAA"}
        status, _ = http("GET", f"{origin}/api/me", forged_bearer)
        check("a forged token is refused", status == 401, f"status={status}")

        seeded = len(records)
        browser_evidence = pilot(origin, spy_app, wire, out_dir, args.headed)

        print("\nserver-side read-back, independent of the UI")
        status, body = http("GET", f"{origin}/api/records",
                            dev_sign.sign_headers("GET", "/api/records", b"", "alice"))
        readback = json.loads(body) if status == 200 else {"records": {}}
        created = [k for k, v in readback["records"].items()
                   if v["title"] == "made in the browser"]
        check("the browser's POSTs are present server-side", len(created) == 3,
              f"{len(created)} created, store grew {len(records) - seeded}")
        check("every created record is owned by the signed identity",
              all(readback["records"][k]["owner_id"] == "devkey-alice"
                  for k in created))
    finally:
        app_stopped = app_server.stop()
        spy_stopped = spy_server.stop()

    check("the application server stopped cleanly", app_stopped)
    check("the other-origin server stopped cleanly", spy_stopped)

    passed = sum(1 for r in _RESULTS if r["ok"])
    failed = len(_RESULTS) - passed

    artifact = {
        "test": "signed-dev-access browser smoke",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "app_origin": origin,
        "other_origin": spy_server.origin,
        "passed": passed,
        "failed": failed,
        "checks": _RESULTS,
        "browser": browser_evidence,
        "other_origin_requests": [
            {"path": e["path"], "method": e["method"],
             "signing_headers": sorted(
                 k for k in e["headers"]
                 if k.startswith("x-request-"))} for e in spy_app.seen],
        # Signature values are omitted: they are single-use and already spent,
        # but an artifact is not the place to publish credentials.
        "server_received": [
            {"method": e["method"], "path_and_query": e["path_and_query"],
             "status": e["status"],
             "signed": bool(e["signing_headers"].get("x-request-signature"))}
            for e in wire],
    }
    (out_dir / "result.json").write_text(json.dumps(artifact, indent=2))

    print(f"\n{passed} passed, {failed} failed")
    print(f"artifact  {out_dir / 'result.json'}")
    for name, path in browser_evidence["screenshots"].items():
        print(f"screenshot {name:8} {path}")
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    finally:
        # The operator key is temporary and never leaves this run.
        shutil.rmtree(_KEY_DIR, ignore_errors=True)
