from __future__ import annotations

import gzip
import json
import os
import struct
import tempfile
import threading
import unittest
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import webres

from data_collection import BrowserAction, ScrapeOptions, Scraper


_APP = b"""<!doctype html><html><head><title>Acquisition fixture</title>
<style>body{font:20px sans-serif;margin:48px;background:#edf4f1;color:#153c35}
main{max-width:850px}button{font:inherit;padding:12px;background:#176e5b;color:white;border:0}
.space{height:1000px}#detail{padding:24px;background:#fff}</style></head>
<body><main id="root"></main><script src="/app.js"></script></body></html>"""

_SCRIPT = b"""fetch('/api/data').then(response => response.json()).then(data => {
    const previous = localStorage.getItem('seen');
    localStorage.setItem('seen', 'yes');
    document.querySelector('#root').innerHTML = '<h1>' + data.title + '</h1>'
        + '<p id="isolation">' + (previous ? 'leaked' : 'fresh context') + '</p>'
        + '<button id="more">Load details</button><div class="space"></div><div id="bottom">Bottom</div>';
    document.querySelector('#more').onclick = () => fetch('/api/details').then(response => response.json()).then(details => {
        document.querySelector('#more').insertAdjacentHTML('afterend', '<p id="detail">' + details.text + '</p>');
    });
    fetch('/private').catch(() => {});
    fetch('/write', {method: 'POST', body: 'not allowed'}).catch(() => {});
    fetch('http://127.0.0.1:9/private').catch(() => {});
    new WebSocket('ws://fixture.test/socket');
});"""


class FixtureHandler(BaseHTTPRequestHandler):
    hits = Counter()
    lock = threading.Lock()

    def log_message(self, *_args):
        pass

    def do_POST(self):
        with self.lock:
            self.hits["POST"] += 1
        self.send_error(500)

    def do_GET(self):
        with self.lock:
            self.hits[self.path] += 1
        headers = {}
        status = 200
        content_type = "text/html; charset=utf-8"
        if self.path == "/robots.txt":
            content_type = "text/plain"
            payload = b"User-agent: *\nAllow: /\nDisallow: /private\n"
        elif self.path in {"/app", "/nested/app"}:
            payload = gzip.compress(_APP)
            headers["Content-Encoding"] = "gzip"
        elif self.path == "/app.js":
            content_type = "application/javascript"
            payload = _SCRIPT
        elif self.path in {"/api/data", "/api/details"}:
            content_type = "application/json"
            payload = json.dumps({"title": "Rendered HTML acquired", "text": "Details loaded by a real browser click"}).encode()
        elif self.path == "/redirect":
            status = 302
            headers["Location"] = "/nested/app"
            payload = b""
        elif self.path == "/denied":
            status = 403
            payload = b"<h1>Forbidden</h1>"
        else:
            payload = b"<!doctype html><html><head><title>Static fixture</title></head><body><h1>Static HTML acquired</h1></body></html>"
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        for name, value in headers.items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(payload)


class BrowserTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), FixtureHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.origin = f"http://fixture.test:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    async def asyncSetUp(self):
        original = webres.public_addresses

        def fixture_addresses(host, port=443):
            return ["127.0.0.1"] if host == "fixture.test" else original(host, port)

        resolver = patch.object(webres, "public_addresses", side_effect=fixture_addresses)
        throttle = patch.object(webres, "throttle")
        resolver.start()
        throttle.start()
        self.addCleanup(resolver.stop)
        self.addCleanup(throttle.stop)
        FixtureHandler.hits.clear()
        webres._robots_cache.clear()

    async def test_real_http_static_fast_path(self):
        async with Scraper() as scraper:
            result = await scraper.fetch(self.origin + "/static")
            self.assertTrue(result.ok, result.error)
            self.assertEqual(result.method, "http")
            self.assertIn("Static HTML acquired", result.html)
            self.assertIsNone(scraper._browser._browser)

    async def test_real_browser_fallback_computer_use_and_request_refusals(self):
        options = ScrapeOptions(
            wait_selector="#detail", screenshot=True, settle_ms=100,
            actions=(BrowserAction("wait", "#more"), BrowserAction("scroll", pixels=1000), BrowserAction("click", "#more")),
        )
        async with Scraper(options) as scraper:
            result = await scraper.fetch(self.origin + "/app")
        self.assertTrue(result.ok, f"{result.error_code}: {result.error}")
        self.assertEqual(result.method, "browser")
        self.assertIn("Details loaded by a real browser click", result.html)
        self.assertIn("fresh context", result.html)
        self.assertEqual(FixtureHandler.hits["/app"], 1)
        self.assertEqual(FixtureHandler.hits["/api/details"], 1)
        self.assertEqual(FixtureHandler.hits["/private"], 0)
        self.assertEqual(FixtureHandler.hits["POST"], 0)
        self.assertGreater(result.blocked_requests.get("non_read_method", 0), 0)
        self.assertGreater(result.blocked_requests.get("url_refused", 0), 0)
        self.assertGreater(result.blocked_requests.get("robots_disallowed", 0), 0)
        self.assertGreater(result.blocked_requests.get("websocket", 0), 0)
        self.assertEqual(result.screenshot[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(struct.unpack(">II", result.screenshot[16:24]), (1440, 1000))
        evidence_root = Path(os.environ.get("WEBSCRAPER_STATE_HOME", tempfile.gettempdir()))
        evidence = evidence_root / "webscraper-tests" / "browser-evidence.png"
        evidence.parent.mkdir(parents=True, exist_ok=True)
        evidence.write_bytes(result.screenshot)

    async def test_browser_redirect_and_context_isolation(self):
        async with Scraper(ScrapeOptions(mode="browser", wait_selector="#more", settle_ms=100)) as scraper:
            first = await scraper.fetch(self.origin + "/redirect")
            browser = scraper._browser._browser
            second = await scraper.fetch(self.origin + "/app")
            self.assertIs(scraper._browser._browser, browser)
        self.assertTrue(first.ok, first.error)
        self.assertTrue(second.ok, second.error)
        self.assertEqual(first.final_url, self.origin + "/nested/app")
        self.assertIn("fresh context", first.html)
        self.assertIn("fresh context", second.html)

    async def test_readiness_and_wait_actions_accept_multiple_matches(self):
        options = ScrapeOptions(
            mode="browser", wait_selector="main > *", settle_ms=100,
            actions=(BrowserAction("wait", "main > *"),),
        )
        async with Scraper(options) as scraper:
            result = await scraper.fetch(self.origin + "/app")
        self.assertTrue(result.ok, f"{result.error_code}: {result.error}")
        self.assertIn("Rendered HTML acquired", result.html)
        self.assertIn("fresh context", result.html)

    async def test_browser_denied_document_is_not_success(self):
        async with Scraper(ScrapeOptions(mode="browser", settle_ms=100)) as scraper:
            result = await scraper.fetch(self.origin + "/denied")
        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "access_denied")
        self.assertEqual(FixtureHandler.hits["/denied"], 1)


if __name__ == "__main__":
    unittest.main()