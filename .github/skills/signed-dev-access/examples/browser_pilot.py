"""browser_pilot — sign every request a piloted browser makes, to ONE origin.

This is the piece that turns signed dev access into *remote piloting*: the
agent drives the real UI in a real browser, and every request the page issues
to the application — the HTML document, its assets, and its APIs — carries a
valid signature, so the application authenticates it exactly as it would a
human's session.

WHY STATIC HEADERS DO NOT WORK
------------------------------
The signature covers method, path+query, and body. A browser fires many
different requests, so a single set of extra headers is valid for at most
one of them; the rest fail verification and return a bare 401 that looks
like a logged-out session. Every request must be signed individually,
which means intercepting at the network layer.

WHY THE ORIGIN IS REQUIRED, AND A PATH PREFIX IS NOT ENOUGH
-----------------------------------------------------------
A page reaches out. Fonts, analytics, a CDN, an OAuth redirect, a
``fetch()`` a developer added last week to a partner API. Playwright's
``context.route("**/*")`` sees all of it, so an interceptor that decides
what to sign by *path* will happily attach the operator's signature to
``https://someone-elses-host/api/collect`` — a live credential, handed to
a third party, valid for the whole five-minute skew window.

Widening the path filter to ``/`` makes that strictly worse, so this
module does not offer it. The scope that actually matters is the
**origin**: it is required, and it is matched exactly on scheme, host and
port. Every request to anything else is forwarded with the signing headers
positively stripped.

Within the trusted origin the default is to sign everything, including
the HTML document and static assets. That is deliberate: when a whole
application sits behind signed access, an unsigned ``GET /`` is a 401 and
an unsigned ``GET /static/app.js`` is a 401 that renders as a blank page.
Narrow it with ``should_sign`` when only part of the surface is protected.

WHY CDP AND NOT ``context.route``
---------------------------------
Measured on Playwright 1.62 / Chromium 151, not recalled. The redirect and
streaming cases in ``tests/browser_smoke.py`` re-measure all three on every
run:

* ``route.continue_()`` does **not** fire the handler for the legs of a
  redirect chain. One handler call for ``GET /to-foreign``; the hop to the
  foreign host was never offered. Worse, the network stack **replays the
  headers** injected on the first leg, so the foreign host received them.
  A signature minted for the trusted origin arrives at whatever the
  application redirects to. No origin check inside the handler can prevent
  that, because the handler never runs.

* ``route.fetch(max_redirects=0)`` + ``route.fulfill`` closes that hole by
  stopping the chain where it can still be seen — but it buffers the whole
  response through Playwright's request context. Against an SSE endpoint
  emitting at t=0 and t=1.5s: first event at **1515 ms**, stream end at
  **1515 ms**. Nothing streams. A signed SSE or long-poll surface is not
  pilotable that way, and the escape hatch this module used to offer
  (``intercept_redirects=False``) had no effect other than reopening the
  credential leak above. An insecure switch is not a feature, so it is gone.

* CDP ``Fetch`` pauses at the network layer and hands the request back to
  the browser's own stack. Both redirect legs are offered to the handler,
  the foreign leg is stripped, a trusted→trusted leg is re-signed for its
  own path, and the same SSE endpoint delivers its first event at **35 ms**
  with the stream ending at **1521 ms**. Safe *and* streaming.

The cost is that this is **Chromium-only**, deliberately and explicitly:
:func:`install_request_signing` raises on any other engine rather than
silently signing nothing.

BODIES ARE READ AS BYTES, NEVER AS TEXT
---------------------------------------
CDP exposes a request body twice. ``request.postData`` is a *string* and is
lossy: a 256-byte body of ``0x00``–``0xFF`` came back 128 characters long,
which would be hashed into a signature over the wrong bytes and refused as
a bare 401. ``request.postDataEntries[].bytes`` is base64 and was
byte-exact for that body, and carried a 256 KiB body intact. This module
reads only the latter. When a body exists and no byte-exact copy is offered
— a streamed or file-backed upload — the request is **failed loudly**
rather than signed over a guess.

SERVICE WORKERS AND CACHE
-------------------------
A service worker can answer a ``fetch()`` from its own cache without the
request reaching the network, so nothing is signed and nothing is observed.
The HTTP cache does the same to a revisited asset. Use
:func:`new_piloted_context`, which blocks service workers, and have the
protected surface send ``Cache-Control: no-store`` — a piloted session
should re-prove access on every request rather than replay a cached 200.

WHAT THIS COSTS
---------------
Interception adds one signing operation per request. Ed25519 signing is
microseconds; it is not a meaningful cost next to page load.

LIMITS WORTH KNOWING BEFORE YOU RELY ON THIS
--------------------------------------------
* Chromium only. See above.
* One CDP session is attached per page. Pages created through the context
  are attached synchronously, before they can navigate. A page the
  *application* opens — ``window.open``, ``target="_blank"`` — is attached
  as soon as it is announced, which is after its first navigation is
  already in flight: that one request goes unsigned and reads as a 401,
  and everything the popup requests afterwards is signed.
* A cross-origin iframe runs in its own out-of-process target and is not
  intercepted — it is also never signed, so nothing leaks, but a request it
  makes to the trusted origin arrives unsigned and reads as a 401.
* Do not also install ``context.route`` over the same requests. Playwright
  drives routing through the same CDP domain and the two will fight.
* Verify the context header survives your ingress before relying on
  per-operator slugs -- see GOTCHAS.md G3. If it is stripped, sign with an
  empty slug and accept the shared default identity.

This module imports Playwright lazily, so the box has no browser
dependency unless you actually pilot a UI.
"""

from __future__ import annotations

import base64
import sys
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from dev_sign import sign_headers

# The headers the signer produces, lowercased. Named here so the cross-origin
# path can remove them positively rather than trust they were never added.
SIGNING_HEADERS = ("x-request-timestamp", "x-request-signature",
                   "x-request-context")

_DEFAULT_PORTS = {"http": "80", "https": "443"}


class BodyNotSignable(RuntimeError):
    """A request carries a body CDP will not hand back byte-exact.

    Signing over a lossy copy mints a well-formed signature over the wrong
    bytes, which the server refuses as an ordinary 401 — the most expensive
    failure to diagnose in this whole design. Raised so it fails visibly.
    """


def _path_and_query(url: str) -> str:
    """Extract exactly the string the server will reconstruct.

    Must match the raw wire path, not a decoded or normalised form
    (GOTCHAS.md G1). ``urlsplit`` does not percent-decode and the server
    rebuilds from ASGI ``raw_path``, so both sides see the same bytes.
    """
    parts = urlsplit(url)
    return f"{parts.path}?{parts.query}" if parts.query else parts.path


def normalise_origin(url: str) -> str:
    """Reduce a URL to ``scheme://host[:port]``, dropping the default port.

    ``https://app.example:443/x`` and ``https://app.example`` are the same
    origin and must compare equal, or the trusted origin matches nothing, the
    whole pilot runs unsigned, and the result looks like a broken login rather
    than a configuration mistake.
    """
    parts = urlsplit(url)
    if not parts.scheme or not parts.hostname:
        raise ValueError(f"not an absolute http(s) URL: {url!r}")
    scheme = parts.scheme.lower()
    host = parts.hostname.lower()
    port = str(parts.port) if parts.port else ""
    if port and port == _DEFAULT_PORTS.get(scheme):
        port = ""
    return f"{scheme}://{host}:{port}" if port else f"{scheme}://{host}"


def _strip_signing(headers: dict) -> dict:
    """Copy of ``headers`` with every signing header removed."""
    return {k: v for k, v in headers.items()
            if k.lower() not in SIGNING_HEADERS}


def request_body(cdp_request: dict) -> bytes:
    """Byte-exact body of a paused CDP request, or raise.

    Reads ``postDataEntries[].bytes`` only. ``postData`` is a lossy string —
    measured: a 256-byte binary body arrives as 128 characters — and must
    never reach the hash a signature is minted over.
    """
    if not cdp_request.get("hasPostData"):
        return b""
    entries = cdp_request.get("postDataEntries")
    if not entries:
        raise BodyNotSignable(
            "CDP reported a request body but offered no postDataEntries; "
            "streamed and file-backed uploads cannot be signed by this pilot")
    out = bytearray()
    for entry in entries:
        raw = entry.get("bytes")
        if raw is None:
            raise BodyNotSignable(
                "a postDataEntry carried no bytes; the body cannot be "
                "reproduced exactly and must not be signed")
        out += base64.b64decode(raw)
    return bytes(out)


def _require_chromium(context) -> None:
    browser = getattr(context, "browser", None)
    name = getattr(getattr(browser, "browser_type", None), "name", None)
    if name is not None and name != "chromium":
        raise RuntimeError(
            f"browser_pilot signs through the Chrome DevTools Protocol and "
            f"supports Chromium only; got {name!r}. Piloting under another "
            f"engine would silently sign nothing at all.")


def install_request_signing(
    context,
    *,
    origin: str,
    context_slug: str = "",
    should_sign: Callable[[str, str], bool] | None = None,
    on_request: Callable[[dict], None] | None = None,
) -> None:
    """Sign every request this context makes to ``origin``, and only that.

    Args:
        context: a Playwright Chromium ``BrowserContext`` (sync API).
        origin: the application's origin, e.g. ``"http://127.0.0.1:8080"``.
            Required, matched exactly after normalisation. Requests to any
            other origin are forwarded with signing headers stripped.
        context_slug: optional operator slug; leave empty if your ingress
            strips the context header.
        should_sign: optional ``(method, path_and_query) -> bool`` narrowing
            what is signed *within* the trusted origin. The default signs
            everything, because a protected surface protects its assets too.
        on_request: optional observer, called with
            ``{"url", "method", "origin", "signed"}`` per request, plus an
            ``"error"`` key when a request could not be signed. For evidence
            collection. It must not raise.

    Raises:
        ValueError: if ``origin`` is not an absolute http(s) URL.
        RuntimeError: if the context is not Chromium.

    Every leg of a redirect chain is offered separately and judged on its own
    URL, so a hop that leaves the trusted origin arrives stripped and a hop
    that stays is re-signed for the path it actually requests. Responses are
    never buffered, so a signed SSE or long-poll endpoint streams normally.
    """
    trusted = normalise_origin(origin)
    _require_chromium(context)

    def report(event: dict) -> None:
        if on_request is None:
            return
        try:
            on_request(event)
        except Exception:  # an observer must never break the pilot
            pass

    def wire(session) -> None:
        def paused(event: dict) -> None:
            request_id = event.get("requestId")
            request = event.get("request") or {}
            url = request.get("url", "")
            method = request.get("method", "GET")
            try:
                try:
                    request_origin = normalise_origin(url)
                except ValueError:
                    # data:, blob: and friends carry no credential anywhere.
                    session.send("Fetch.continueRequest",
                                 {"requestId": request_id})
                    return

                headers = _strip_signing(request.get("headers") or {})
                signed = False
                if request_origin == trusted:
                    path_q = _path_and_query(url)
                    if should_sign is None or should_sign(method, path_q):
                        headers.update(sign_headers(
                            method, path_q, request_body(request),
                            context_slug))
                        signed = True

                report({"url": url, "method": method,
                        "origin": request_origin, "signed": signed})
                session.send("Fetch.continueRequest", {
                    "requestId": request_id,
                    "headers": [{"name": k, "value": v}
                                for k, v in headers.items()]})
            except (Exception, SystemExit) as exc:
                # A handler that dies leaves the request paused forever, which
                # reads as a hung page. Fail it and say why, because the
                # alternative symptom is an unexplained 401. SystemExit is
                # caught too: dev_sign raises it when no signing key exists,
                # and it is not an Exception, so it would otherwise tear down
                # the whole run from inside an event callback.
                detail = f"{type(exc).__name__}: {exc}"
                report({"url": url, "method": method, "origin": "",
                        "signed": False, "error": detail})
                print(f"browser_pilot: {method} {url} failed: {detail}",
                      file=sys.stderr)
                try:
                    session.send("Fetch.failRequest",
                                 {"requestId": request_id,
                                  "errorReason": "Aborted"})
                except Exception:
                    pass

        session.on("Fetch.requestPaused", paused)
        session.send("Fetch.enable", {"patterns": [
            {"urlPattern": "*", "requestStage": "Request"}]})

    attached: set = set()

    def attach(page) -> None:
        if page in attached:
            return
        attached.add(page)
        wire(context.new_cdp_session(page))

    for page in context.pages:
        attach(page)

    # A page is a separate CDP target and needs its own session — measured: a
    # second page in the same context received no paused events from the
    # first page's session.
    #
    # Attaching from the context's "page" event is not enough on its own.
    # ``new_cdp_session`` suspends, so in the sync API the event handler yields
    # and ``new_page()`` returns to the caller *before* the session exists —
    # measured, as "handler entered, new_page returned, new_cdp_session
    # returned", with the first navigation going out unsigned and coming back
    # 401. Pages the caller creates are therefore attached synchronously here,
    # after ``new_page`` returns and before anything can navigate them.
    state = {"creating": False}
    create_page = context.new_page

    def new_page(*args, **kwargs):
        state["creating"] = True
        try:
            page = create_page(*args, **kwargs)
        finally:
            state["creating"] = False
        attach(page)
        return page

    context.new_page = new_page

    def on_page(page) -> None:
        if state["creating"]:
            return  # the wrapper above will attach it, in the right order
        # A page the application opened itself — window.open, target=_blank.
        # This attach lands after the popup's first navigation is already in
        # flight, so that one request goes unsigned and will read as a 401.
        # Everything the popup requests afterwards is signed.
        attach(page)

    context.on("page", on_page)


def new_piloted_context(browser, *, origin: str, context_slug: str = "",
                        should_sign: Callable[[str, str], bool] | None = None,
                        on_request: Callable[[dict], None] | None = None,
                        **context_kwargs):
    """Create a context that is already signing, with the silent traps closed.

    Blocks service workers, because a worker answering ``fetch()`` from its own
    cache never reaches the interceptor: the request is neither signed nor
    observed, and the pilot quietly stops proving anything.

    Any other ``browser.new_context`` keyword — ``viewport``, ``locale``,
    ``record_video_dir`` — passes straight through.
    """
    context_kwargs.setdefault("service_workers", "block")
    context = browser.new_context(**context_kwargs)
    install_request_signing(context, origin=origin, context_slug=context_slug,
                            should_sign=should_sign, on_request=on_request)
    return context


__all__ = ["install_request_signing", "new_piloted_context",
           "normalise_origin", "request_body", "BodyNotSignable",
           "SIGNING_HEADERS"]


# ---------------------------------------------------------------------
# Worked example. Requires: pip install playwright && playwright install
# chromium
#
# ``tests/browser_smoke.py`` is this example as an executable proof against a
# real local application. Run that first; adapt it second.
# ---------------------------------------------------------------------
#
#     from playwright.sync_api import sync_playwright
#
#     APP = "https://your-app.example.com"
#
#     with sync_playwright() as p:
#         browser = p.chromium.launch()
#         context = new_piloted_context(browser, origin=APP)
#
#         page = context.new_page()
#         response = page.goto(f"{APP}/")     # the document itself is signed
#         assert response.status == 200, response.status
#
#         # Pilot the UI as an operator would.
#         page.get_by_role("button", name="Run scan").click()
#         page.wait_for_selector("[data-testid=results]")
#
#         # Observe the RESULT, not a screenshot. The DOM is authoritative;
#         # screenshots can lag the live DOM by a full frame.
#         rows = page.eval_on_selector_all(
#             "[data-testid=results] tr", "els => els.length")
#         assert rows > 0, "scan produced no rows"
#
#         browser.close()
#
# Four habits that make piloting reliable:
#
#   1. Assert on DOM state via page.evaluate, never on a screenshot.
#   2. If a click times out on "visible, enabled and stable" while the
#      element is genuinely fine, a layout animation is failing the
#      stability check; diagnose before assuming a product bug.
#   3. Confirm side effects from the server (an API read-back, a log line)
#      rather than from the UI that triggered them.
#   4. A 401 on the *document* means the page never loaded, and every
#      assertion after it is meaningless. Check ``response.status`` from
#      ``page.goto`` before believing an empty DOM.
