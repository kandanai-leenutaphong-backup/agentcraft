from __future__ import annotations

import base64
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from signed_dev_access import (
    BodyNotSignable,
    RequestSigner,
    SIGNATURE_HEADER,
    TIMESTAMP_HEADER,
    SigningError,
    install_request_signing,
    new_piloted_context,
    request_body,
    verify,
)


class Session:
    def __init__(self):
        self.handlers = {}
        self.commands = []
        self.detached = 0

    def on(self, name, handler):
        self.handlers[name] = handler

    def remove_listener(self, name, handler):
        assert self.handlers.pop(name) == handler

    def send(self, method, parameters=None):
        self.commands.append((method, parameters))

    def detach(self):
        self.detached += 1

    def pause(self, request):
        self.handlers["Fetch.requestPaused"]({"requestId": "fixture-request", "request": request})
        return self.commands[-1]


class Context:
    def __init__(self, engine="chromium"):
        self.browser = SimpleNamespace(browser_type=SimpleNamespace(name=engine))
        self.pages = []
        self.handlers = {}
        self.sessions = {}
        self.closed = 0

    def new_page(self):
        page = object()
        self.pages.append(page)
        if "page" in self.handlers:
            self.handlers["page"](page)
        return page

    def new_cdp_session(self, page):
        assert page not in self.sessions or self.sessions[page].detached == 1
        session = Session()
        self.sessions[page] = session
        return session

    def on(self, name, handler):
        self.handlers[name] = handler

    def remove_listener(self, name, handler):
        assert self.handlers.pop(name) == handler

    def close(self):
        self.closed += 1


@pytest.fixture
def signer():
    return RequestSigner(Ed25519PrivateKey.generate(), origin="https://app.invalid", allow_mutations=True)


def header_mapping(parameters):
    return {header["name"]: header["value"] for header in parameters["headers"]}


def test_cdp_signs_every_leg_and_strips_foreign_redirect_material(capsys):
    private_key = Ed25519PrivateKey.generate()
    signer = RequestSigner(private_key, origin="https://app.invalid")
    context = Context()
    pilot = install_request_signing(context, signer=signer)
    page = context.new_page()
    session = context.sessions[page]
    first_method, first = session.pause({"url": "https://app.invalid/first", "method": "GET", "headers": {"Accept": "text/plain"}})
    original = header_mapping(first)
    next_method, second = session.pause({"url": "https://app.invalid/next?q=x%26y", "method": "GET", "headers": original})
    renewed = header_mapping(second)
    assert first_method == next_method == "Fetch.continueRequest"
    assert renewed[SIGNATURE_HEADER] != original[SIGNATURE_HEADER]
    assert verify(
        public_key_b64=base64.b64encode(private_key.public_key().public_bytes_raw()).decode("ascii"),
        method="GET", path_and_query="/next?q=x%26y", ts=renewed[TIMESTAMP_HEADER],
        sig_b64=renewed[SIGNATURE_HEADER], body=b"",
    ).ok
    foreign_method, foreign = session.pause({"url": "https://foreign.invalid/collect", "method": "POST", "headers": renewed, "hasPostData": True})
    assert foreign_method == "Fetch.continueRequest"
    assert header_mapping(foreign) == {"Accept": "text/plain"}
    assert all(method not in {"Fetch.getResponseBody", "Fetch.fulfillRequest"} for method, parameters in session.commands)
    pilot.close()
    pilot.close()
    assert session.detached == 1 and context.closed == 0 and not context.handlers
    assert capsys.readouterr() == ("", "")


def test_cdp_binary_body_is_exact_and_lossy_body_aborts(signer, capsys):
    context = Context()
    with install_request_signing(context, signer=signer) as pilot:
        page = context.new_page()
        session = context.sessions[page]
        payload = bytes(range(256))
        request = {"url": "https://app.invalid/binary", "method": "POST", "hasPostData": True, "postData": "lossy", "postDataEntries": [{"bytes": base64.b64encode(payload).decode("ascii")}], "headers": {}}
        assert request_body(request) == payload
        assert session.pause(request)[0] == "Fetch.continueRequest"
        request.pop("postDataEntries")
        assert session.pause(request) == ("Fetch.failRequest", {"requestId": "fixture-request", "errorReason": "Aborted"})
        assert pilot.failure_count == 1 and pilot.last_error == "body_not_signable"
    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize("paused_request", [
    {"hasPostData": True},
    {"postData": "text-only"},
    {"hasPostData": True, "postDataEntries": []},
    {"hasPostData": True, "postDataEntries": [{}]},
    {"hasPostData": True, "postDataEntries": [{"bytes": "%%%"}]},
    {"hasPostData": True, "postDataEntries": [{"bytes": ""}] * 4097},
    {"hasPostData": True, "postDataEntries": [{"bytes": base64.b64encode(b"x" * 1_048_577).decode("ascii")}]},
])
def test_unknown_or_oversized_bodies_refuse(paused_request):
    with pytest.raises(BodyNotSignable, match="^body_not_signable$"):
        request_body(paused_request)


def test_narrowing_and_unexpected_errors_never_emit_credentials(signer, capsys):
    context = Context()
    with install_request_signing(context, signer=signer, should_sign=lambda method, path: False) as pilot:
        page = context.new_page()
        session = context.sessions[page]
        _, parameters = session.pause({"url": "https://app.invalid/no-sign", "headers": {SIGNATURE_HEADER: "stale"}})
        assert header_mapping(parameters) == {}
    with install_request_signing(context, signer=signer, should_sign=lambda method, path: "not-a-bool") as pilot:
        page = context.new_page()
        assert context.sessions[page].pause({"url": "https://app.invalid/"})[0] == "Fetch.failRequest"
        assert pilot.last_error == "request_refused"
    assert capsys.readouterr() == ("", "")


def test_other_engines_duplicate_installation_and_unsafe_context_options_refuse(signer):
    with pytest.raises(SigningError, match="^chromium_required$"):
        install_request_signing(Context("firefox"), signer=signer)
    context = Context()
    pilot = install_request_signing(context, signer=signer)
    with pytest.raises(SigningError, match="^signing_already_installed$"):
        install_request_signing(context, signer=signer)
    pilot.close()
    browser = SimpleNamespace(browser_type=SimpleNamespace(name="chromium"), new_context=lambda **options: pytest.fail("must refuse before context creation"))
    for options in ({"service_workers": "allow"}, {"record_har_path": "capture.har"}, {"storage_state": {"cookies": ["private"]}}):
        with pytest.raises(SigningError):
            new_piloted_context(browser, signer=signer, **options)


def test_owned_context_blocks_service_workers_and_closes_once(signer):
    context = Context()
    recorded = []

    def create_context(**options):
        recorded.append(options)
        return context

    browser = SimpleNamespace(browser_type=SimpleNamespace(name="chromium"), new_context=create_context)
    pilot = new_piloted_context(browser, signer=signer)
    original_new_page = pilot._original_new_page
    pilot.context.new_page()
    pilot.close()
    pilot.close()
    assert recorded == [{"service_workers": "block"}]
    assert context.closed == 1 and context.new_page == original_new_page


def test_owned_context_setup_failure_closes_once(signer, capsys):
    context = Context()
    context.new_page()
    context.new_cdp_session = Mock(side_effect=RuntimeError("private-protocol-detail"))
    browser = SimpleNamespace(browser_type=SimpleNamespace(name="chromium"), new_context=lambda **options: context)
    with pytest.raises(SigningError, match="^browser_setup_failed$"):
        new_piloted_context(browser, signer=signer)
    assert context.closed == 1
    assert getattr(context, "_agentcraft_signing", None) is None
    assert capsys.readouterr() == ("", "")


def test_owned_context_close_failure_is_payload_free_and_not_retried(signer, capsys):
    context = Context()
    context.close = Mock(side_effect=RuntimeError("private-protocol-detail"))
    browser = SimpleNamespace(browser_type=SimpleNamespace(name="chromium"), new_context=lambda **options: context)
    pilot = new_piloted_context(browser, signer=signer)
    with pytest.raises(SigningError, match="^browser_close_failed$") as caught:
        pilot.close()
    assert caught.value.__cause__ is None
    assert caught.value.__suppress_context__
    pilot.close()
    context.close.assert_called_once()
    assert pilot.last_error == "browser_close_failed"
    assert capsys.readouterr() == ("", "")