#!/usr/bin/env python3
"""transport_offline.py — the two live backends, exercised without a network.

    python3 tests/transport_offline.py

Both live transports used to be untested on the grounds that they talk to
Azure. They do not: one builds an argument vector and reads a subprocess
result, the other builds a request and reads an ``http.client`` response. Both
seams are injectable, so both are testable, and the review found real defects in
each — a fabricated HTTP status on one, a token attached to any URL a response
body named on the other.

Nothing here opens a socket. ``AzureCliTransport`` gets a fake ``runner``;
``TokenCredentialTransport`` gets a fake ``opener`` and a credential that counts
how many times it was asked for a token. Counting that is the point: the
security property is not "the bad request failed", it is "no token was ever
minted for it".
"""

from __future__ import annotations

import io
import subprocess
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from azaccess import (  # noqa: E402
    AZURE_PUBLIC_CLOUD,
    AZURE_US_GOVERNMENT,
    AuthenticationError,
    AuthorizationRefused,
    AzureCliTransport,
    TokenCredentialTransport,
    TransportError,
    UNKNOWN_STATUS,
    cloud_by_name,
    status_from_cli_error,
)
from azaccess.endpoints import origin_of, require_same_origin  # noqa: E402

_FAILURES: list[str] = []
_CHECKS = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global _CHECKS
    _CHECKS += 1
    if condition:
        print(f"ok   {name}")
    else:
        print(f"FAIL {name}{(' — ' + detail) if detail else ''}")
        _FAILURES.append(name)


def refuses(name: str, fn, *expected) -> None:
    try:
        fn()
    except expected:
        check(name, True)
        return
    except Exception as exc:
        check(name, False, f"raised {type(exc).__name__}: {exc}")
        return
    check(name, False, "no refusal raised")


class CountingCredential:
    """Counts token requests, because 'zero' is the assertion that matters."""

    def __init__(self) -> None:
        self.tokens = 0

    def get_token(self, scope: str):
        self.tokens += 1
        return types.SimpleNamespace(token="not-a-real-token", expires_on=0)


class FakeHttpResponse:
    def __init__(self, status: int = 200, payload: bytes = b"{}",
                 headers: dict[str, str] | None = None) -> None:
        self.status = status
        self._payload = payload
        self.headers = types.SimpleNamespace(items=lambda: list((headers or {}).items()))

    def read(self) -> bytes:
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def opener_for(*responses):
    """An opener that records requests and answers a scripted sequence."""
    sent: list = []
    queue = list(responses)

    def opener(request, timeout=None):
        sent.append(request)
        answer = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(answer, Exception):
            raise answer
        return answer

    opener.sent = sent  # type: ignore[attr-defined]
    return opener


def runner_for(returncode: int = 0, stdout: str = "{}", stderr: str = "",
               raises: Exception | None = None):
    seen: list[list[str]] = []

    def runner(argv):
        seen.append(list(argv))
        if raises is not None:
            raise raises
        return types.SimpleNamespace(returncode=returncode, stdout=stdout,
                                     stderr=stderr)

    runner.seen = seen  # type: ignore[attr-defined]
    return runner


# ------------------------------------------------------- credential transport


def test_token_never_leaves_the_configured_cloud() -> None:
    credential = CountingCredential()
    opener = opener_for(FakeHttpResponse(200, b'{"value":[]}'))
    transport = TokenCredentialTransport(lambda: credential, opener=opener)

    transport.request("GET", "https://management.azure.com/subscriptions/x?api-version=1")
    check("one in-cloud request mints one token and sends once",
          credential.tokens == 1 and len(opener.sent) == 1)

    for url, label in (
        ("https://evil.example/steal", "an unrelated host"),
        ("http://management.azure.com/x", "plain http"),
        ("https://management.azure.com@evil.example/x", "userinfo"),
        ("https://graph.microsoft.com/v1.0/me", "the right cloud, wrong audience"),
        ("https://management.azure.com/x#f", "a fragment"),
    ):
        refuses(f"{label} is refused", lambda u=url: transport.request("GET", u),
                AuthorizationRefused)
    check("no refused request minted a token",
          credential.tokens == 1, f"tokens={credential.tokens}")
    check("no refused request reached the network",
          len(opener.sent) == 1, f"sends={len(opener.sent)}")


def test_the_authorization_header_is_never_forwarded_by_a_redirect() -> None:
    credential = CountingCredential()
    redirect = urlerror_http(302, {"Location": "https://evil.example/steal"})
    transport = TokenCredentialTransport(
        lambda: credential, opener=opener_for(redirect))
    refuses("a redirect is refused rather than followed with the token",
            lambda: transport.request(
                "GET", "https://management.azure.com/x"),
            AuthorizationRefused)

    from azaccess.transport import _RefuseRedirects

    handler = _RefuseRedirects()
    check("the default opener's redirect handler follows nothing",
          handler.redirect_request(None, None, 302, "Found", {},
                                   "https://evil.example/steal") is None)


def test_http_errors_are_data_and_network_errors_are_not() -> None:
    credential = CountingCredential()
    forbidden = urlerror_http(403, {}, b'{"error":{"code":"AuthorizationFailed"}}')
    transport = TokenCredentialTransport(
        lambda: credential, opener=opener_for(forbidden))
    response = transport.request("GET", "https://management.azure.com/x")
    check("a 403 is returned as data, not raised",
          response.status == 403 and not response.ok)

    from urllib import error as urlerror

    unreachable = TokenCredentialTransport(
        lambda: credential,
        opener=opener_for(urlerror.URLError("name or service not known")))
    refuses("a network failure is a TransportError",
            lambda: unreachable.request("GET", "https://management.azure.com/x"),
            TransportError)

    accepted = TokenCredentialTransport(
        lambda: credential,
        opener=opener_for(FakeHttpResponse(
            202, b"", {"Azure-AsyncOperation": "https://management.azure.com/op"})))
    lro = accepted.request("PUT", "https://management.azure.com/x", json_body={})
    check("202 and its poll header are both readable off the wire",
          lro.status == 202
          and lro.header("azure-asyncoperation") == "https://management.azure.com/op"
          and lro.status_exact)


def test_a_broken_credential_is_an_authentication_error() -> None:
    class Broken:
        def get_token(self, scope):
            raise RuntimeError("AADSTS700016: application not found")

    transport = TokenCredentialTransport(Broken, opener=opener_for(FakeHttpResponse()))
    refuses("a credential that will not issue is an AuthenticationError",
            lambda: transport.request("GET", "https://management.azure.com/x"),
            AuthenticationError)


def test_sovereign_clouds_are_configuration() -> None:
    credential = CountingCredential()
    opener = opener_for(FakeHttpResponse(200, b'{"value":[]}'))
    gov = TokenCredentialTransport(
        lambda: credential, cloud=AZURE_US_GOVERNMENT, opener=opener)
    gov.request("GET", "https://management.usgovcloudapi.net/subscriptions/x")
    check("a US Government transport reaches its own ARM host",
          len(opener.sent) == 1)
    refuses("and refuses the public cloud's host",
            lambda: gov.request("GET", "https://management.azure.com/x"),
            AuthorizationRefused)
    check("clouds are looked up by name, not hardcoded",
          cloud_by_name("AzureCloud") is AZURE_PUBLIC_CLOUD)

    custom = AZURE_PUBLIC_CLOUD.with_hosts("analytics.kusto.windows.net")
    check("a caller can add one named host without wildcarding",
          "analytics.kusto.windows.net" in custom.hosts()
          and "evil.example" not in custom.hosts())


# ---------------------------------------------------------------- cli backend


def test_cli_reads_only_and_reports_status_honestly() -> None:
    runner = runner_for(stdout='{"value":[{"id":"x"}]}')
    cli = AzureCliTransport(runner=runner)
    response = cli.request("GET", "https://management.azure.com/x?api-version=1")
    check("a CLI read parses its body",
          response.body == {"value": [{"id": "x"}]})
    check("and flags the status as inferred rather than read",
          response.status == 200 and response.status_exact is False)
    check("the argument vector is a list, never a shell string",
          isinstance(runner.seen[0], list) and "rest" in runner.seen[0])
    check("the URL is passed as one argument, unquoted and unconcatenated",
          runner.seen[0][runner.seen[0].index("--url") + 1]
          == "https://management.azure.com/x?api-version=1")

    refuses("a mutation is refused, because its status cannot be read",
            lambda: cli.request("PUT", "https://management.azure.com/x",
                                json_body={"a": 1}),
            AuthorizationRefused)
    refuses("an off-cloud read is refused before anything is spawned",
            lambda: cli.request("GET", "https://evil.example/x"),
            AuthorizationRefused)
    check("nothing was spawned for the refused calls", len(runner.seen) == 1)


def test_cli_failures_are_classified_not_guessed() -> None:
    auth = AzureCliTransport(
        runner=runner_for(returncode=1, stderr="ERROR: AADSTS50076: MFA required"))
    refuses("an AADSTS failure is an AuthenticationError",
            lambda: auth.request("GET", "https://management.azure.com/x"),
            AuthenticationError)

    unknown = AzureCliTransport(runner=runner_for(
        returncode=1, stderr="Operation failed on rg-409: unexpected"))
    response = unknown.request("GET", "https://management.azure.com/x")
    check("a digit inside a resource name is not a status",
          response.status == UNKNOWN_STATUS and response.status_exact is False)

    structured = AzureCliTransport(runner=runner_for(
        returncode=1, stderr='{"error":{"code":"AuthorizationFailed"}}'))
    check("a structured ARM error code maps to its documented status",
          structured.request("GET", "https://management.azure.com/x").status == 403)

    missing = AzureCliTransport(runner=runner_for(raises=FileNotFoundError("az")))
    refuses("a missing az binary is a TransportError naming the fix",
            lambda: missing.request("GET", "https://management.azure.com/x"),
            TransportError)

    timeout = AzureCliTransport(runner=runner_for(
        raises=subprocess.TimeoutExpired(cmd="az", timeout=1.0)))
    refuses("a CLI timeout is a TransportError",
            lambda: timeout.request("GET", "https://management.azure.com/x"),
            TransportError)

    garbage = AzureCliTransport(runner=runner_for(stdout="<html>proxy error</html>"))
    body = garbage.request("GET", "https://management.azure.com/x").body
    check("a non-JSON body is kept as raw text, not silently emptied",
          "raw" in body)

    check("status classification never invents 599 from nothing",
          status_from_cli_error("something went wrong") == UNKNOWN_STATUS)


def test_origin_helpers() -> None:
    check("origin ignores path and query",
          origin_of("https://management.azure.com/a/b?c=d")
          == "https://management.azure.com")
    check("origin keeps an explicit port, because it is part of the origin",
          origin_of("https://management.azure.com:8443/a")
          == "https://management.azure.com:8443")
    refuses("a same-origin check refuses a different port",
            lambda: require_same_origin("https://management.azure.com:8443/p2",
                                        "https://management.azure.com",
                                        what="page"),
            AuthorizationRefused)


def urlerror_http(code: int, headers: dict, payload: bytes = b"{}"):
    from urllib import error as urlerror

    return urlerror.HTTPError(
        url="https://management.azure.com/x", code=code, msg="err",
        hdrs=_Headers(headers), fp=io.BytesIO(payload),
    )


class _Headers(dict):
    def items(self):  # HTTPError.headers is used through .items()
        return list(super().items())


def main() -> int:
    for test in (
        test_token_never_leaves_the_configured_cloud,
        test_the_authorization_header_is_never_forwarded_by_a_redirect,
        test_http_errors_are_data_and_network_errors_are_not,
        test_a_broken_credential_is_an_authentication_error,
        test_sovereign_clouds_are_configuration,
        test_cli_reads_only_and_reports_status_honestly,
        test_cli_failures_are_classified_not_guessed,
        test_origin_helpers,
    ):
        try:
            test()
        except Exception as exc:
            check(f"{test.__name__} raised {type(exc).__name__}", False, str(exc))
    print()
    if _FAILURES:
        print(f"FAILED: {len(_FAILURES)} of {_CHECKS} checks — {_FAILURES[:5]}")
        return 1
    print(f"PASSED: {_CHECKS} checks, 0 failures")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
