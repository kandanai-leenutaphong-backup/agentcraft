import asyncio
import json
import unittest
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from azdata import (
    ConnectorConfig, HttpRequest, HttpResponse, Limits, Policy, ReadRequest, RecordKey,
    ResourceAddress, connect,
)
from azdata.sdk import Transport


class Response:
    def __init__(self, payload=b'{"id":"one"}', status=200, headers=None):
        self.payload = payload
        self.status_code = status
        self.headers = headers or {}
        self.closed = False
        self.read = False

    async def iter_bytes(self):
        self.read = True
        yield self.payload

    async def close(self):
        self.closed = True


class Credential:
    def get_token(self, scope):
        return SimpleNamespace(token="fixture-token", expires_on=2**31)


class TransportTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.config = ConnectorConfig("https://unit.search.windows.net", ResourceAddress({"index": "fixture"}), ("unit.search.windows.net",))

    async def test_redirect_handler_never_reissues_bearer_token(self):
        calls = []
        class RedirectTransport:
            async def request(self, request):
                calls.append(request)
                return HttpResponse(302, headers={"location": "https://untrusted.example"})
        client = connect("search", self.config, credential=Credential(), policy=Policy(principal="fixture"), transport=RedirectTransport())
        result = await client.read(ReadRequest(keys=(RecordKey({"id": "one"}),)))
        self.assertEqual(result.status, "failed")
        self.assertEqual(len(calls), 1)

    async def test_http_transport_does_not_read_error_bodies(self):
        response = Response(b"private-provider-error", 403)
        with patch("azdata.sdk.AioHttpTransport") as factory:
            factory.return_value.send = AsyncMock(return_value=response)
            factory.return_value.close = AsyncMock()
            async with connect("search", self.config, credential=Credential(), policy=Policy(principal="fixture")) as client:
                result = await client.read(ReadRequest(keys=(RecordKey({"id": "one"}),)))
        self.assertEqual(result.status, "denied")
        self.assertFalse(response.read)
        self.assertTrue(response.closed)
        self.assertNotIn("private", repr(result))

    async def test_default_transport_binds_timeout_headers_and_json(self):
        with patch("azdata.sdk.AioHttpTransport") as factory:
            factory.return_value.send = AsyncMock(return_value=Response())
            factory.return_value.close = AsyncMock()
            async with connect("search", self.config, credential=Credential(), policy=Policy(principal="fixture")) as client:
                result = await client.read(ReadRequest(keys=(RecordKey({"id": "one"}),), limits=Limits(timeout_seconds=2)))
            request = factory.return_value.send.call_args.args[0]
            self.assertEqual(request.headers["Authorization"], "Bearer fixture-token")
            self.assertLessEqual(factory.return_value.send.call_args.kwargs["read_timeout"], 2.0)
            self.assertFalse(factory.return_value.send.call_args.kwargs["allow_redirects"])
        self.assertEqual(result.items[0].content.data["id"], "one")

    async def test_response_cap_and_malformed_json_are_bounded_faults(self):
        for payload, cap, code in ((b"x" * 200, 100, "response_too_large"), (b"not json", 100, "invalid_provider_json")):
            with self.subTest(code=code), patch("azdata.sdk.AioHttpTransport") as factory:
                response = Response(payload)
                factory.return_value.send = AsyncMock(return_value=response)
                factory.return_value.close = AsyncMock()
                async with connect("search", self.config, credential=Credential(), policy=Policy(principal="fixture")) as client:
                    result = await client.read(ReadRequest(keys=(RecordKey({"id": "one"}),), limits=Limits(max_output_bytes=cap)))
                self.assertEqual(result.errors[0].code, code)
                self.assertTrue(response.closed)

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
        with patch("time.time", return_value=1000):
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

        with patch("azdata.sdk.AioHttpTransport") as factory:
            factory.return_value.send = AsyncMock(return_value=Response())
            factory.return_value.close = AsyncMock()
            credential = SimpleNamespace(get_token=lambda scope: SimpleNamespace(token="fixture", expires_on=2**31))
            connector = connect("search", self.config, credential=credential, policy=Policy(principal="fixture"))
            await connector.read(ReadRequest(keys=(RecordKey({"id": "one"}),)))
            await connector.aclose()
            await connector.aclose()
            factory.return_value.close.assert_awaited_once()

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