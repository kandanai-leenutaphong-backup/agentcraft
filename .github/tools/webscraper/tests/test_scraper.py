import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from data_collection import ScrapeOptions, Scraper
from data_collection.browser import BrowserSnapshot
from data_collection.models import HTTPResponse, ScrapeFailure


class ScraperTests(unittest.IsolatedAsyncioTestCase):
    async def test_static_html_never_launches_browser(self):
        async with Scraper() as scraper:
            with patch.object(scraper._transport, "request", new_callable=AsyncMock, return_value=HTTPResponse("https://example.test/final", 200, {"content-type": "text/html"}, b"<h1>Hello</h1>")), patch.object(scraper._browser, "render", new_callable=AsyncMock) as browser:
                result = await scraper.fetch("https://example.test")
            self.assertTrue(result.ok)
            self.assertEqual(result.method, "http")
            self.assertEqual(result.final_url, "https://example.test/final")
            browser.assert_not_awaited()

    async def test_javascript_shell_uses_browser_and_retains_source(self):
        response = HTTPResponse("https://example.test", 200, {"content-type": "text/html"}, b'<div id="root"></div><script src="app.js"></script>')
        async with Scraper() as scraper:
            with patch.object(scraper._transport, "request", new_callable=AsyncMock, return_value=response), patch.object(scraper._browser, "render", new_callable=AsyncMock, return_value=BrowserSnapshot("<main>Rendered</main>", response.url, 200, None)) as browser:
                result = await scraper.fetch(response.url)
            self.assertTrue(result.ok)
            self.assertEqual(result.method, "browser")
            self.assertIn("Rendered", result.html)
            self.assertIn("app.js", result.source_html)
            self.assertIs(browser.call_args.args[1], response)

    async def test_transient_failure_attempts_browser(self):
        async with Scraper() as scraper:
            with patch.object(scraper._transport, "request", new_callable=AsyncMock, side_effect=ScrapeFailure("network_error", "fixture", retryable=True)), patch.object(scraper._browser, "render", new_callable=AsyncMock, return_value=BrowserSnapshot("<main>Recovered</main>", "https://example.test", 200, None)):
                result = await scraper.fetch("https://example.test")
            self.assertTrue(result.ok)
            self.assertEqual(result.method, "browser")

    async def test_denials_limits_and_non_html_never_use_browser(self):
        for status, headers, body, code in (
            (403, {}, b"", "access_denied"), (429, {}, b"", "rate_limited"),
            (404, {}, b"", "http_status"), (206, {}, b"", "incomplete_response"),
            (200, {"content-type": "application/pdf"}, b"%PDF", "not_html"),
            (200, {"content-type": "text/html"}, b"<title>Just a moment...</title>", "access_barrier"),
        ):
            with self.subTest(status=status, code=code):
                async with Scraper() as scraper:
                    with patch.object(scraper._transport, "request", new_callable=AsyncMock, return_value=HTTPResponse("https://example.test", status, headers, body)), patch.object(scraper._browser, "render", new_callable=AsyncMock) as browser:
                        result = await scraper.fetch("https://example.test")
                    self.assertFalse(result.ok)
                    self.assertEqual(result.error_code, code)
                    browser.assert_not_awaited()

    async def test_deadline_is_a_failure_not_partial_success(self):
        async def blocked_request(*_args, **_kwargs):
            await asyncio.Event().wait()

        async with Scraper(ScrapeOptions(timeout=0.02)) as scraper:
            with patch.object(scraper._transport, "request", side_effect=blocked_request):
                result = await scraper.fetch("https://example.test")
        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "deadline")

    async def test_batch_streams_results_and_preserves_duplicates(self):
        response = HTTPResponse("https://example.test", 200, {"content-type": "text/html"}, b"<p>complete</p>")
        async with Scraper() as scraper:
            with patch.object(scraper._transport, "request", new_callable=AsyncMock, return_value=response):
                results = [result async for result in scraper.fetch_many([response.url] * 9)]
        self.assertEqual(len(results), 9)
        self.assertTrue(all(result.ok for result in results))


if __name__ == "__main__":
    unittest.main()