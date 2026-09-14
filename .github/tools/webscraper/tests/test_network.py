import gzip
import time
import unittest
import zlib
from unittest.mock import AsyncMock, patch

from data_collection.models import Budget, HTTPResponse, ScrapeFailure, ScrapeOptions
from data_collection.network import Transport, decode_entity, retry_after_seconds


class EncodingTests(unittest.TestCase):
    def test_supported_compression_and_concatenated_gzip(self):
        payload = b"<html>complete</html>"
        self.assertEqual(decode_entity(gzip.compress(payload), "gzip", 100), payload)
        self.assertEqual(decode_entity(zlib.compress(payload), "deflate", 100), payload)
        self.assertEqual(decode_entity(zlib.compress(payload)[2:-4], "deflate", 100), payload)
        self.assertEqual(decode_entity(gzip.compress(b"one") + gzip.compress(b"two"), "gzip", 100), b"onetwo")

    def test_decompression_bomb_refuses_without_truncation(self):
        for encoding, compressor in (("gzip", gzip.compress), ("deflate", zlib.compress)):
            with self.subTest(encoding=encoding), self.assertRaises(ScrapeFailure) as raised:
                decode_entity(compressor(b"x" * 10000), encoding, 100)
            self.assertEqual(raised.exception.code, "content_too_large")

    def test_truncated_compression_refuses(self):
        for encoding, compressor in (("gzip", gzip.compress), ("deflate", zlib.compress)):
            with self.subTest(encoding=encoding), self.assertRaises(ScrapeFailure) as raised:
                decode_entity(compressor(b"hello")[:-4], encoding, 100)
            self.assertEqual(raised.exception.code, "content_decode")

    def test_retry_after_numbers_dates_and_invalid_values(self):
        self.assertEqual(retry_after_seconds("120"), 120)
        self.assertEqual(retry_after_seconds("Wed, 21 Oct 2015 07:28:00 GMT"), 0)
        self.assertIsNone(retry_after_seconds("not a date"))

    def test_options_refuse_invalid_budgets(self):
        for values in ({"timeout": float("nan")}, {"retries": -1}, {"max_requests": 0}, {"mode": "stealth"}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                ScrapeOptions(**values)


class RetryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.transport = Transport(ScrapeOptions())
        self.addAsyncCleanup(self.transport.close)
        self.budget = Budget(time.monotonic() + 60)

    async def test_transient_http_failure_retries(self):
        responses = [HTTPResponse("https://example.test", 503, {}, b""), HTTPResponse("https://example.test", 200, {}, b"ok")]
        attempts = []
        with patch("data_collection.network.request_sync", side_effect=responses) as request, patch("data_collection.network.asyncio.sleep", new_callable=AsyncMock):
            response = await self.transport.request("https://example.test", self.budget, attempts)
        self.assertEqual(response.status, 200)
        self.assertEqual(request.call_count, 2)
        self.assertEqual([attempt.status for attempt in attempts], [503, 200])

    async def test_access_denial_is_not_retried(self):
        with patch("data_collection.network.request_sync", return_value=HTTPResponse("https://example.test", 403, {}, b"")) as request:
            response = await self.transport.request("https://example.test", self.budget, [])
        self.assertEqual(response.status, 403)
        self.assertEqual(request.call_count, 1)

    async def test_retry_after_longer_than_budget_refuses(self):
        with patch("data_collection.network.request_sync", return_value=HTTPResponse("https://example.test", 429, {"retry-after": "3600"}, b"")) as request:
            with self.assertRaises(ScrapeFailure) as raised:
                await self.transport.request("https://example.test", self.budget, [])
        self.assertEqual(raised.exception.code, "retry_after")
        self.assertEqual(request.call_count, 1)

    async def test_retry_wait_honors_retry_after(self):
        responses = [HTTPResponse("https://example.test", 503, {"retry-after": "7"}, b""), HTTPResponse("https://example.test", 200, {}, b"ok")]
        with patch("data_collection.network.request_sync", side_effect=responses), patch("data_collection.network.asyncio.sleep", new_callable=AsyncMock) as pause:
            await self.transport.request("https://example.test", self.budget, [])
        pause.assert_awaited_once_with(7)

    async def test_request_and_byte_budgets_refuse(self):
        self.budget.requests = self.transport.options.max_requests
        with self.assertRaises(ScrapeFailure) as raised:
            await self.transport.request("https://example.test", self.budget, [])
        self.assertEqual(raised.exception.code, "request_budget")
        self.budget.requests = 0
        self.budget.bytes_received = self.transport.options.max_total_bytes
        with patch("data_collection.network.request_sync", return_value=HTTPResponse("https://example.test", 200, {}, b"more")):
            with self.assertRaises(ScrapeFailure) as raised:
                await self.transport.request("https://example.test", self.budget, [])
        self.assertEqual(raised.exception.code, "byte_budget")


if __name__ == "__main__":
    unittest.main()