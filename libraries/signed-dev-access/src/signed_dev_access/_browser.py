from __future__ import annotations

import base64
from collections.abc import Callable
from typing import Any

from ._client import RequestSigner, SigningError, _strip_signing_headers, _url_parts
from ._middleware import MAX_SIGNED_BODY_BYTES, MAX_SIGNED_BODY_CHUNKS


class BodyNotSignable(SigningError):
    def __init__(self) -> None:
        super().__init__("body_not_signable")


def request_body(request: dict[str, Any]) -> bytes:
    entries = request.get("postDataEntries")
    if not request.get("hasPostData") and entries is None and "postData" not in request:
        return b""
    if not isinstance(entries, list) or not entries or len(entries) > MAX_SIGNED_BODY_CHUNKS:
        raise BodyNotSignable()
    result = bytearray()
    for entry in entries:
        raw = entry.get("bytes") if isinstance(entry, dict) else None
        if not isinstance(raw, str) or len(raw) > ((MAX_SIGNED_BODY_BYTES + 2) // 3) * 4:
            raise BodyNotSignable()
        try:
            chunk = base64.b64decode(raw, validate=True)
        except (ValueError, TypeError):
            raise BodyNotSignable() from None
        if len(result) + len(chunk) > MAX_SIGNED_BODY_BYTES:
            raise BodyNotSignable()
        result.extend(chunk)
    return bytes(result)


class BrowserSigning:
    def __init__(
        self,
        context: Any,
        signer: RequestSigner,
        *,
        should_sign: Callable[[str, str], bool] | None = None,
        owns_context: bool = False,
    ) -> None:
        browser = getattr(context, "browser", None)
        if getattr(getattr(browser, "browser_type", None), "name", None) != "chromium":
            raise SigningError("chromium_required")
        if not isinstance(signer, RequestSigner):
            raise SigningError("invalid_signer")
        if getattr(context, "_agentcraft_signing", None) is not None:
            raise SigningError("signing_already_installed")
        if len(context.pages) > 64:
            raise SigningError("page_limit")
        self.context = context
        self._signer = signer
        self._should_sign = should_sign
        self._owns_context = owns_context
        self._sessions: dict[Any, tuple[Any, Callable]] = {}
        self._closed = False
        self._creating = False
        self._original_new_page = context.new_page
        self.failure_count = 0
        self.last_error = ""

        def new_page(*args, **kwargs):
            if self._closed:
                raise SigningError("browser_signing_closed")
            self._creating = True
            try:
                page = self._original_new_page(*args, **kwargs)
            finally:
                self._creating = False
            self._attach(page)
            return page

        def on_page(page):
            if not self._creating and not self._closed:
                self._attach(page)

        self._new_page = new_page
        self._on_page = on_page
        context._agentcraft_signing = self
        try:
            for page in context.pages:
                self._attach(page)
            context.new_page = new_page
            context.on("page", on_page)
        except Exception:
            self.close()
            raise SigningError("browser_setup_failed") from None

    def _attach(self, page: Any) -> None:
        if page in self._sessions:
            return
        if len(self._sessions) >= 64:
            raise SigningError("page_limit")
        session = self.context.new_cdp_session(page)

        def paused(event):
            request_id = event.get("requestId")
            request = event.get("request") or {}
            try:
                url = request.get("url", "")
                method = request.get("method", "GET")
                parts = _url_parts(url)
                path = parts.path or "/"
                if "?" in url:
                    path += "?" + parts.query
                enabled = self._signer.matches(url)
                if enabled and self._should_sign is not None:
                    enabled = self._should_sign(method, path)
                    if not isinstance(enabled, bool):
                        raise SigningError("invalid_signing_decision")
                if enabled:
                    headers = self._signer.headers_for(method, url, request_body(request), headers=request.get("headers"))
                else:
                    headers = _strip_signing_headers(request.get("headers"))
                session.send("Fetch.continueRequest", {
                    "requestId": request_id,
                    "headers": [{"name": name, "value": value} for name, value in headers.items()],
                })
            except (Exception, SystemExit) as error:
                self.failure_count += 1
                self.last_error = "body_not_signable" if isinstance(error, BodyNotSignable) else "request_refused"
                try:
                    session.send("Fetch.failRequest", {"requestId": request_id, "errorReason": "Aborted"})
                except Exception:
                    pass

        self._sessions[page] = (session, paused)
        session.on("Fetch.requestPaused", paused)
        session.send("Fetch.enable", {"patterns": [{"urlPattern": "*", "requestStage": "Request"}]})

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if getattr(self.context, "new_page", None) is self._new_page:
            self.context.new_page = self._original_new_page
        if getattr(self.context, "_agentcraft_signing", None) is self:
            del self.context._agentcraft_signing
        try:
            self.context.remove_listener("page", self._on_page)
        except Exception:
            pass
        for session, paused in self._sessions.values():
            for action in (
                lambda: session.remove_listener("Fetch.requestPaused", paused),
                lambda: session.send("Fetch.disable"),
                session.detach,
            ):
                try:
                    action()
                except Exception:
                    self.failure_count += 1
                    self.last_error = "browser_close_failed"
        self._sessions.clear()
        if self._owns_context:
            try:
                self.context.close()
            except Exception:
                self.failure_count += 1
                self.last_error = "browser_close_failed"
                raise SigningError("browser_close_failed") from None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def install_request_signing(context: Any, *, signer: RequestSigner, should_sign=None) -> BrowserSigning:
    return BrowserSigning(context, signer, should_sign=should_sign)


def new_piloted_context(browser: Any, *, signer: RequestSigner, should_sign=None, **options) -> BrowserSigning:
    if getattr(getattr(browser, "browser_type", None), "name", None) != "chromium":
        raise SigningError("chromium_required")
    if options.get("service_workers", "block") != "block":
        raise SigningError("service_workers_must_be_blocked")
    if any(options.get(name) for name in ("record_har_path", "storage_state", "http_credentials")):
        raise SigningError("credential_recording_or_reuse_refused")
    options["service_workers"] = "block"
    context = browser.new_context(**options)
    try:
        pilot = BrowserSigning(context, signer, should_sign=should_sign)
    except Exception:
        try:
            context.close()
        except Exception:
            raise SigningError("browser_close_failed") from None
        raise SigningError("browser_setup_failed") from None
    pilot._owns_context = True
    return pilot