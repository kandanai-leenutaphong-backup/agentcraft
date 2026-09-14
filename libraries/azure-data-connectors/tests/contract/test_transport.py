import asyncio
import io
import json
import unittest
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import HTTPError

from azdata import (
    ConnectorConfig, HttpRequest, HttpResponse, Limits, Policy, ReadRequest, RecordKey,
    ResourceAddress, connect,
)
from azdata.transport import HttpTransport, OperationFault, _NoRedirect


class Response(io.BytesIO):
    def __init__(self, payload=b'{"id":"one"}', status=200, headers=None):
        super().__init__(payload)
        self.code = status
        self.headers = headers or {}


class TransportTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.config = ConnectorConfig("https://unit.search.windows.net", ResourceAddress({"index": "fixture"}), ("unit.search.windows.net",))

    def test_redirect_handler_never_reissues_bearer_token(self):
        self.assertIsNone(_NoRedirect().redirect_request(None, None, 302, "redirect", {}, "https://untrusted.example"))

    async def test_http_transport_does_not_read_error_bodies(self):
        payload = Response(b"private-provider-error")
        error = HTTPError("https://unit.search.windows.net", 403, "private", {}, payload)
        with patch("azdata.transport.urllib.request.build_opener") as opener:
            opener.return_value.open.side_effect = error
            response = await HttpTransport().request(HttpRequest("GET", self.config.endpoint, {}, None, 1.0, 100))
        self.assertEqual(response.status, 403)
        self.assertIsNone(response.body)
        self.assertTrue(payload.closed)
        self.assertNotIn("private", repr(response))

    async def test_default_transport_binds_timeout_headers_and_json(self):
        response = Response(b'{"value":[]}')
        with patch("azdata.transport.urllib.request.build_opener") as opener:
            opener.return_value.open.return_value = response
            result = await HttpTransport().request(HttpRequest("POST", self.config.endpoint, {"Authorization": "Bearer fixture"}, {"search": "*"}, 2.0, 100))
            request = opener.return_value.open.call_args.args[0]
            self.assertEqual(json.loads(request.data), {"search": "*"})
            self.assertEqual(request.get_header("Authorization"), "Bearer fixture")
            self.assertEqual(opener.return_value.open.call_args.kwargs["timeout"], 2.0)
        self.assertEqual(result.body, {"value": []})

    async def test_response_cap_and_malformed_json_are_bounded_faults(self):
        for payload, cap, code in ((b"x" * 200, 100, "response_too_large"), (b"not json", 100, "invalid_provider_json")):
            with self.subTest(code=code), patch("azdata.transport.urllib.request.build_opener") as opener:
                opener.return_value.open.return_value = Response(payload)
                with self.assertRaises(OperationFault) as raised:
                    await HttpTransport().request(HttpRequest("GET", self.config.endpoint, {}, None, 1.0, cap))
                self.assertEqual(raised.exception.code, code)

    async def test_refreshes_expiring_tokens_and_preserves_borrowed_lifetime(self):
        class Credential:
            calls = 0

            def get_token(self, scope):
                self.calls += 1
                return SimpleNamespace(token=f"fixture-{self.calls}", expires_on=1200 if self.calls == 1 else 9999)

            def close(self):
                raise AssertionError("borrowed credential must remain open")

        class Transport:
            def __init__(self):
                self.headers = []

            async def request(self, request):
                self.headers.append(request.headers["Authorization"])
                return HttpResponse(200, {"id": "one"})

            async def aclose(self):
                raise AssertionError("borrowed transport must remain open")

        credential, transport = Credential(), Transport()
        connector = connect("search", self.config, credential=credential, policy=Policy(principal="fixture"), transport=transport)
        with patch("azdata.transport.time.time", return_value=1000):
            for _ in range(3):
                self.assertEqual((await connector.read(ReadRequest(keys=(RecordKey({"id": "one"}),)))).status, "success")
        self.assertEqual(credential.calls, 2)
        self.assertEqual(transport.headers, ["Bearer fixture-1", "Bearer fixture-2", "Bearer fixture-2"])
        await connector.aclose()
        await connector.aclose()

    async def test_retry_after_cannot_be_shortened_below_provider_hint(self):
        class Credential:
            def get_token(self, scope):
                return SimpleNamespace(token="fixture", expires_on=2**31)

        class Transport:
            calls = 0

            async def request(self, request):
                self.calls += 1
                return HttpResponse(429, headers={"retry-after": "3600"})

        transport = Transport()
        connector = connect("search", self.config, credential=Credential(), transport=transport,
                            policy=Policy(principal="fixture", limits=Limits(timeout_seconds=1, max_attempts=3)))
        result = await connector.read(ReadRequest(keys=(RecordKey({"id": "one"}),)))
        self.assertEqual(result.status, "failed")
        self.assertEqual(transport.calls, 1)

    async def test_safe_read_retries_are_bounded(self):
        class Credential:
            def get_token(self, scope):
                return SimpleNamespace(token="fixture", expires_on=2**31)

        class Transport:
            calls = 0

            async def request(self, request):
                self.calls += 1
                return HttpResponse(503) if self.calls == 1 else HttpResponse(200, {"id": "one"})

        transport = Transport()
        connector = connect("search", self.config, credential=Credential(), transport=transport,
                            policy=Policy(principal="fixture", limits=Limits(max_attempts=2)))
        result = await connector.read(ReadRequest(keys=(RecordKey({"id": "one"}),)))
        self.assertEqual(result.status, "success")
        self.assertEqual(transport.calls, 2)

    async def test_owned_transport_closes_once(self):
        class Credential:
            def get_token(self, scope):
                raise AssertionError("not needed")

        with patch("azdata.transport.HttpTransport.aclose") as closer:
            connector = connect("search", self.config, credential=Credential(), policy=Policy(principal="fixture"))
            await connector.aclose()
            await connector.aclose()
            closer.assert_awaited_once()

    async def test_concurrency_limit_is_applied_without_changing_authority(self):
        entered, release = asyncio.Event(), asyncio.Event()

        class Credential:
            def get_token(self, scope):
                return SimpleNamespace(token="fixture", expires_on=2**31)

        class Transport:
            active = 0
            maximum = 0

            async def request(self, request):
                self.active += 1
                self.maximum = max(self.maximum, self.active)
                entered.set()
                await release.wait()
                self.active -= 1
                return HttpResponse(200, {"id": "one"})

        transport = Transport()
        connector = connect("search", self.config, credential=Credential(), transport=transport,
                            policy=Policy(principal="fixture", max_concurrency=1))
        request = ReadRequest(keys=(RecordKey({"id": "one"}),))
        first = asyncio.create_task(connector.read(request))
        await entered.wait()
        second = asyncio.create_task(connector.read(replace(request, request_id="second")))
        release.set()
        results = await asyncio.gather(first, second)
        self.assertEqual([result.status for result in results], ["success", "success"])
        self.assertEqual(transport.maximum, 1)


if __name__ == "__main__":
    unittest.main()