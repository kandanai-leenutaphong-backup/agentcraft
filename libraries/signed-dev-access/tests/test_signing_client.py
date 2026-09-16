from __future__ import annotations

import base64
import io
import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from signed_dev_access import (
    CONTEXT_HEADER,
    MAX_SIGNED_BODY_BYTES,
    RequestSigner,
    SIGNATURE_HEADER,
    TIMESTAMP_HEADER,
    SigningError,
    canonical_string,
    load_private_key,
    sign_headers,
    verify,
)


@pytest.fixture
def private_key():
    return Ed25519PrivateKey.generate()


def check_signature(private_key, headers, *, method="POST", path="/api/a%2Fb?q=x%26y", body=b""):
    return verify(
        public_key_b64=base64.b64encode(private_key.public_key().public_bytes_raw()).decode("ascii"),
        method=method,
        path_and_query=path,
        ts=headers[TIMESTAMP_HEADER],
        sig_b64=headers[SIGNATURE_HEADER],
        body=body,
        user_slug=headers.get(CONTEXT_HEADER, ""),
    )


def test_signer_uses_canonical_bytes_and_verifies_binary_body(private_key):
    body = bytes(range(256))
    with patch("signed_dev_access._client.canonical_string", wraps=canonical_string) as canonical:
        headers = sign_headers(private_key, "post", "/api/a%2Fb?q=x%26y", body, " Operator_1 ")
    assert canonical.call_count == 1
    result = check_signature(private_key, headers, body=body)
    assert result.ok and result.user_slug == "operator_1"
    assert not check_signature(private_key, headers, body=body + b"changed").ok
    assert not check_signature(private_key, headers, body=body, path="/api/a/b?q=x%26y").ok
    assert not check_signature(private_key, headers, body=body, method="GET").ok


def test_empty_context_and_utc_microseconds(private_key):
    moment = datetime.now(timezone(timedelta(hours=2)))
    headers = sign_headers(private_key, "POST", "/api/a%2Fb?q=x%26y", timestamp=moment)
    assert CONTEXT_HEADER not in headers
    assert headers[TIMESTAMP_HEADER].endswith("Z")
    assert len(headers[TIMESTAMP_HEADER].split(".")[1]) == 7
    assert check_signature(private_key, headers).ok


@pytest.mark.parametrize("path", ["https://foreign.invalid/", "//foreign.invalid/", "relative", "/x\nheader", "/x#fragment", "/x\\y", "/bad%2", "/?", "/nonascii\u00e9", "/" + "a" * 8192])
def test_malformed_paths_refuse_before_signing(private_key, path):
    with patch("signed_dev_access._client.canonical_string") as canonical:
        with pytest.raises(SigningError, match="^invalid_path$"):
            sign_headers(private_key, "GET", path)
    canonical.assert_not_called()


@pytest.mark.parametrize("method", ["", "GET\r\nX-Evil", "G ET", "a" * 33, None])
def test_invalid_method_has_payload_free_error(private_key, method):
    with pytest.raises(SigningError, match="^invalid_method$"):
        sign_headers(private_key, method, "/")


@pytest.mark.parametrize("context", ["other/user", "a" * 65, "x\nheader", "\u00e9", None])
def test_invalid_context_refuses(private_key, context):
    with pytest.raises(SigningError, match="^invalid_context$"):
        sign_headers(private_key, "GET", "/", context_slug=context)


def test_body_and_naive_timestamp_bounds_refuse(private_key):
    with pytest.raises(SigningError, match="^invalid_body$"):
        sign_headers(private_key, "POST", "/", b"x" * (MAX_SIGNED_BODY_BYTES + 1))
    with pytest.raises(SigningError, match="^invalid_body$"):
        sign_headers(private_key, "POST", "/", bytearray(b"mutable"))
    with pytest.raises(SigningError, match="^invalid_timestamp$"):
        sign_headers(private_key, "GET", "/", timestamp=datetime(2026, 1, 1))


def private_file(tmp_path, private_key):
    directory = tmp_path / "operator-private"
    directory.mkdir(mode=0o700)
    path = directory / "signing-key"
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(private_key.private_bytes_raw())
    return path


def test_load_private_key_is_explicit_and_emits_no_material(tmp_path, private_key, capsys):
    path = private_file(tmp_path, private_key)
    loaded = load_private_key(path)
    assert loaded.public_key().public_bytes_raw() == private_key.public_key().public_bytes_raw()
    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize("mode", [0o644, 0o640, 0o660, 0o700])
def test_private_file_permissions_refuse(tmp_path, private_key, mode):
    path = private_file(tmp_path, private_key)
    path.chmod(mode)
    with pytest.raises(SigningError, match="^unsafe_key_file$"):
        load_private_key(path)


def test_private_directory_and_repository_paths_refuse(tmp_path, private_key):
    path = private_file(tmp_path, private_key)
    path.parent.chmod(0o755)
    with pytest.raises(SigningError, match="^unsafe_key_directory$"):
        load_private_key(path)
    path.parent.chmod(0o700)
    (tmp_path / ".git").write_text("gitdir: elsewhere", encoding="ascii")
    with pytest.raises(SigningError, match="^key_in_repository$"):
        load_private_key(path)


def test_private_symlinks_and_hardlinks_refuse(tmp_path, private_key):
    path = private_file(tmp_path, private_key)
    link = path.with_name("link")
    link.symlink_to(path)
    with pytest.raises(SigningError, match="^private_key_unavailable$"):
        load_private_key(link)
    alias = tmp_path / "alias"
    alias.symlink_to(path.parent, target_is_directory=True)
    with pytest.raises(SigningError, match="^private_key_unavailable$"):
        load_private_key(alias / path.name)
    os.link(path, path.with_name("hardlink"))
    with pytest.raises(SigningError, match="^unsafe_key_file$"):
        load_private_key(path)


def test_bad_private_files_have_payload_free_errors(tmp_path, private_key):
    path = private_file(tmp_path, private_key)
    path.write_bytes(b"not-a-private-key")
    with pytest.raises(SigningError, match="^invalid_private_key$"):
        load_private_key(path)
    with pytest.raises(SigningError, match="^invalid_key_path$"):
        load_private_key("relative-key")
    with pytest.raises(SigningError, match="^private_key_unavailable$"):
        load_private_key(path.with_name("missing-key"))


def test_one_origin_only_and_foreign_headers_are_positively_stripped(private_key):
    signer = RequestSigner(private_key, origin="https://APP.invalid:443/")
    old = {"x-REQUEST-signature": "old", TIMESTAMP_HEADER: "old", CONTEXT_HEADER: "old", "Accept": "application/json"}
    current = signer.headers_for("GET", "https://app.invalid/api/a%2Fb?q=x%26y", headers=old)
    assert check_signature(private_key, current, method="GET").ok
    assert signer.headers_for("GET", "https://foreign.invalid/api/a%2Fb", headers=current) == {"Accept": "application/json"}
    assert signer.headers_for("GET", "https://app.invalid:444/api", headers=current) == {"Accept": "application/json"}
    assert signer.origin == "https://app.invalid"


def test_parallel_identical_requests_get_distinct_verifiable_signatures(private_key):
    moment = datetime.now(timezone.utc)
    signer = RequestSigner(private_key, origin="https://app.invalid", clock=lambda: moment)
    with ThreadPoolExecutor(max_workers=8) as executor:
        headers = list(executor.map(lambda unused: signer.headers_for("GET", "https://app.invalid/api/a%2Fb?q=x%26y"), range(24)))
    assert len({item[SIGNATURE_HEADER] for item in headers}) == 24
    assert all(check_signature(private_key, item, method="GET").ok for item in headers)


@pytest.mark.parametrize("origin", ["https://user:password@app.invalid", "https://app.invalid/prefix", "https://app.invalid?scope=other", "http://foreign.invalid", "https://app.invalid/#", "https://app.invalid\n", "file:///private/key"])
def test_invalid_or_insecure_origin_refuses(private_key, origin):
    with pytest.raises(SigningError):
        RequestSigner(private_key, origin=origin)


def test_loopback_http_and_mutations_need_explicit_local_policy(private_key):
    with pytest.raises(SigningError, match="^https_required$"):
        RequestSigner(private_key, origin="http://127.0.0.1:8000")
    RequestSigner(private_key, origin="http://127.0.0.1:8000", allow_loopback_http=True)
    with pytest.raises(SigningError, match="^https_required$"):
        RequestSigner(private_key, origin="http://foreign.invalid", allow_loopback_http=True)
    signer = RequestSigner(private_key, origin="https://app.invalid")
    with pytest.raises(SigningError, match="^mutation_not_authorized$"):
        signer.headers_for("POST", "https://app.invalid/api")


class FakeResponse(io.BytesIO):
    def __init__(self, status=200, body=b"response"):
        super().__init__(body)
        self.status = status
        self.reads = 0

    def read1(self, count):
        self.reads += 1
        return super().read(count)


class FakeConnection:
    def __init__(self, response):
        self.response = response
        self.calls = []
        self.closed = 0
        self.sock = None
        self.debuglevel = 1

    def set_debuglevel(self, level):
        self.debuglevel = level

    def request(self, method, path, *, body, headers):
        self.calls.append((method, path, body, headers))

    def getresponse(self):
        return self.response

    def close(self):
        self.closed += 1


def test_http_request_signs_raw_bytes_and_closes_without_printing(private_key, capsys):
    connection = FakeConnection(FakeResponse(body=b"private response"))
    signer = RequestSigner(private_key, origin="https://app.invalid", allow_mutations=True)
    payload = bytes(range(256))
    result = signer.request("POST", "/api/a%2Fb?q=x%26y", payload, connection_factory=lambda *args, **kwargs: connection)
    method, path, body, headers = connection.calls[0]
    assert check_signature(private_key, headers, method=method, path=path, body=body).ok
    assert body == payload
    assert result.body == b"private response"
    assert "private response" not in repr(result)
    assert result.metadata() == {"status": 200, "response_bytes": 16}
    assert connection.closed == 1 and connection.debuglevel == 0
    assert capsys.readouterr() == ("", "")


def test_redirects_refuse_and_error_bodies_are_not_read(private_key):
    signer = RequestSigner(private_key, origin="https://app.invalid")
    redirect = FakeConnection(FakeResponse(302, b"do-not-read"))
    with pytest.raises(SigningError, match="^redirect_refused$"):
        signer.request("GET", "/", connection_factory=lambda *args, **kwargs: redirect)
    assert len(redirect.calls) == 1 and redirect.response.reads == 0 and redirect.closed == 1
    denied = FakeConnection(FakeResponse(403, b"do-not-read"))
    result = signer.request("GET", "/", connection_factory=lambda *args, **kwargs: denied)
    assert result.status == 403 and result.body == b""
    assert denied.response.reads == 0 and denied.closed == 1


def test_response_limits_and_transport_failures_are_safe_and_close(private_key):
    signer = RequestSigner(private_key, origin="https://app.invalid")
    connection = FakeConnection(FakeResponse(body=b"x" * 40))
    with pytest.raises(SigningError, match="^response_limit$"):
        signer.request("GET", "/", max_response_bytes=32, connection_factory=lambda *args, **kwargs: connection)
    assert connection.closed == 1
    connection.request = Mock(side_effect=OSError("private-detail"))
    with pytest.raises(SigningError, match="^request_failed$"):
        signer.request("GET", "/", connection_factory=lambda *args, **kwargs: connection)
    assert connection.closed == 2


def test_cli_requires_send_and_never_emits_key_headers_or_response(tmp_path, private_key, capsys):
    from signed_dev_access.__main__ import main

    path = private_file(tmp_path, private_key)
    arguments = ["request", "GET", "/api/a%2Fb?q=x%26y", "--origin", "https://app.invalid", "--key-file", str(path)]
    connection = FakeConnection(FakeResponse(body=b"private-response-content"))
    with patch("signed_dev_access._client.HTTPSConnection", return_value=connection) as factory:
        assert main(arguments) == 0
        factory.assert_not_called()
        assert json.loads(capsys.readouterr().out) == {"sent": False}
        assert main([*arguments, "--send"]) == 0
    output = capsys.readouterr()
    assert json.loads(output.out) == {"status": 200, "response_bytes": 24}
    assert output.err == ""
    headers = connection.calls[0][3]
    assert check_signature(private_key, headers, method="GET").ok
    assert headers[SIGNATURE_HEADER] not in output.out
    assert "private-response-content" not in output.out
    assert main([*arguments, "--timeout", "private-argument"]) == 2
    assert json.loads(capsys.readouterr().out) == {"ok": False, "code": "invalid_arguments"}


def test_key_owner_refuses_before_read(tmp_path, private_key, monkeypatch):
    path = private_file(tmp_path, private_key)
    owner = os.geteuid()
    monkeypatch.setattr(os, "geteuid", lambda: owner + 1)
    with pytest.raises(SigningError, match="^unsafe_key_directory$"):
        load_private_key(path)


def test_request_deadline_closes_without_retry(private_key):
    connection = FakeConnection(FakeResponse())
    signer = RequestSigner(private_key, origin="https://app.invalid")
    with patch("signed_dev_access._client.time.monotonic", side_effect=[0, 2]):
        with pytest.raises(SigningError, match="^request_timeout$"):
            signer.request("GET", "/", timeout_seconds=1, connection_factory=lambda *args, **kwargs: connection)
    assert connection.closed == 1 and len(connection.calls) == 1
    assert connection.response.reads == 0


def test_cli_rejects_the_signing_key_as_a_request_body(tmp_path, private_key, capsys):
    from signed_dev_access.__main__ import main

    path = private_file(tmp_path, private_key)
    arguments = ["request", "POST", "/", "--origin", "https://app.invalid", "--key-file", str(path), "--body-file", str(path), "--allow-mutation", "--send"]
    with patch("signed_dev_access.RequestSigner.request") as request:
        assert main(arguments) == 2
        request.assert_not_called()
    assert json.loads(capsys.readouterr().out) == {"ok": False, "code": "key_as_body_refused"}