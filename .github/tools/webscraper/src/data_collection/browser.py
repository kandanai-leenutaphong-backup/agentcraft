from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from urllib.parse import urldefrag, urlsplit

import webres
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeout
from playwright.async_api import async_playwright

from .models import Budget, HTTPResponse, ScrapeFailure, ScrapeOptions, ScrapeResult
from .network import Transport


@dataclass(frozen=True, slots=True)
class BrowserSnapshot:
    html: str
    url: str
    status: int
    screenshot: bytes | None


def check_status(response: HTTPResponse) -> None:
    if response.status in {401, 403, 407, 451}:
        raise ScrapeFailure("access_denied", "Server denied access; no alternate access path was attempted", status=response.status)
    if response.status == 429:
        raise ScrapeFailure("rate_limited", "Server rate limit remained after permitted retries", status=429)
    if response.status >= 400:
        raise ScrapeFailure("http_status", f"Server returned HTTP {response.status}", status=response.status,
                            retryable=response.status in {408, 425, 500, 502, 503, 504} and "retry-after" not in response.headers)
    if response.status == 206:
        raise ScrapeFailure("incomplete_response", "Partial HTML is not a successful acquisition", status=206)
    if response.status >= 300:
        raise ScrapeFailure("http_status", "Redirect did not resolve to a document", status=response.status)


_DOM_SETTLE = """({quiet, maximum}) => new Promise(resolve => {
    let lastChange = performance.now();
    const started = lastChange;
    const observer = new MutationObserver(() => { lastChange = performance.now(); });
    observer.observe(document.documentElement, {subtree: true, childList: true, characterData: true, attributes: true});
    const timer = setInterval(() => {
        const now = performance.now();
        if (now - lastChange >= quiet || now - started >= maximum) {
            clearInterval(timer);
            observer.disconnect();
            resolve(now - lastChange >= quiet);
        }
    }, Math.min(100, quiet));
})"""


class BrowserRenderer:
    def __init__(self, options: ScrapeOptions, transport: Transport):
        self.options = options
        self.transport = transport
        self._slots = asyncio.Semaphore(options.browser_concurrency)
        self._launch_lock = asyncio.Lock()
        self._playwright = None
        self._browser = None

    async def close(self) -> None:
        if self._browser is not None:
            await self._browser.close()
            self._browser = None
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None

    async def _get_browser(self):
        async with self._launch_lock:
            if self._browser is None or not self._browser.is_connected():
                try:
                    if self._playwright is None:
                        self._playwright = await async_playwright().start()
                    self._browser = await self._playwright.chromium.launch(
                        headless=not self.options.headed,
                        executable_path=self.options.browser_executable,
                        args=["--force-webrtc-ip-handling-policy=disable_non_proxied_udp"],
                    )
                except PlaywrightError as error:
                    raise ScrapeFailure("browser_unavailable", "Chromium could not start; run setup.sh and check browser dependencies or the headed display") from error
            return self._browser

    async def render(self, url: str, initial: HTTPResponse | None, budget: Budget, result: ScrapeResult) -> BrowserSnapshot:
        async with self._slots:
            browser = await self._get_browser()
            context = await browser.new_context(
                viewport={"width": 1440, "height": 1000},
                user_agent=webres.USER_AGENT,
                service_workers="block",
                accept_downloads=False,
            )
            page = await context.new_page()
            active_routes: set[asyncio.Task] = set()
            cached = {urldefrag(initial.url)[0]: initial} if initial else {}
            fatal: list[ScrapeFailure] = []
            document_status: list[int] = []
            navigation_redirects: list[str] = []
            closing = False

            def blocked(reason: str) -> None:
                result.blocked_requests[reason] = result.blocked_requests.get(reason, 0) + 1

            async def route_request(route):
                task = asyncio.current_task()
                active_routes.add(task)
                request = route.request
                main_document = request.is_navigation_request() and request.frame == page.main_frame
                try:
                    if request.method not in {"GET", "HEAD"}:
                        raise ScrapeFailure("non_read_method", "Browser write requests are not permitted")
                    if request.resource_type == "media" or (
                        not self.options.screenshot and request.resource_type in {"image", "font"}
                    ):
                        blocked("performance_filter")
                        await route.abort()
                        return
                    response = cached.pop(urldefrag(request.url)[0], None)
                    if response is None:
                        response = await self.transport.request(
                            request.url, budget, result.attempts, stage="browser",
                            method=request.method, headers=request.headers,
                        )
                    check_status(response)
                    if urldefrag(response.url)[0] != urldefrag(request.url)[0]:
                        if main_document:
                            cached[urldefrag(response.url)[0]] = response
                            navigation_redirects.append(response.url)
                            await route.fulfill(
                                status=200,
                                headers={"content-type": "text/html", "content-security-policy": "default-src 'none'"},
                                body="<!doctype html><html><head></head><body></body></html>",
                            )
                            return
                        warning = "Redirected subresources were fulfilled at their requested URL; relative imports may differ"
                        if warning not in result.warnings:
                            result.warnings.append(warning)
                    if main_document:
                        document_status.append(response.status)
                    headers = {name: value for name, value in response.headers.items() if name.lower() not in {
                        "content-length", "content-encoding", "transfer-encoding", "connection",
                        "keep-alive", "set-cookie", "proxy-authenticate", "proxy-authorization", "trailer", "upgrade",
                    }}
                    await route.fulfill(status=response.status, headers=headers, body=response.body)
                except ScrapeFailure as error:
                    blocked(error.code)
                    if main_document or error.code in {"deadline", "request_budget", "byte_budget", "content_too_large"}:
                        fatal.append(error)
                    await route.abort()
                except PlaywrightError:
                    if not closing:
                        blocked("browser_request_error")
                finally:
                    active_routes.discard(task)

            async def close_websocket(connection):
                blocked("websocket")
                await connection.close()

            async def close_popup(popup):
                blocked("popup")
                await popup.close()

            async def navigate(target):
                for _redirect in range(12):
                    try:
                        await page.goto(target, wait_until="domcontentloaded",
                                        timeout=max(1, (budget.deadline - time.monotonic()) * 1000))
                    except PlaywrightError:
                        if not navigation_redirects:
                            raise
                    if not navigation_redirects:
                        return
                    target = navigation_redirects.pop()
                    navigation_redirects.clear()
                raise ScrapeFailure("redirect_limit", "Browser navigation exceeded its redirect limit")

            try:
                await context.route("**/*", route_request)
                await context.route_web_socket("**/*", close_websocket)
                page.on("popup", close_popup)
                page.on("dialog", lambda dialog: dialog.dismiss())
                page.set_default_timeout(min(15000, max(1, (budget.deadline - time.monotonic()) * 1000)))
                await navigate(initial.url if initial else url)
                for action in self.options.actions:
                    try:
                        if action.kind == "click":
                            await page.locator(action.selector).click()
                        elif action.kind == "wait":
                            await page.locator(action.selector).first.wait_for(state="visible")
                        else:
                            await page.mouse.wheel(0, action.pixels)
                            await page.evaluate(_DOM_SETTLE, {"quiet": self.options.settle_ms, "maximum": 5000})
                    except PlaywrightError:
                        if not navigation_redirects:
                            raise
                    if navigation_redirects:
                        await navigate(navigation_redirects.pop())
                if self.options.wait_selector:
                    await page.locator(self.options.wait_selector).first.wait_for(state="attached")
                else:
                    await page.wait_for_function("""() => {
                        const text = document.body?.innerText.trim() || '';
                        return (text.length > 0 && !/^(loading[. ]*|please wait[. ]*)$/i.test(text))
                            || !!document.querySelector('img, canvas, video, iframe');
                    }""")
                stable = await page.evaluate(_DOM_SETTLE, {"quiet": self.options.settle_ms, "maximum": 5000})
                if fatal:
                    raise fatal[0]
                if not stable:
                    result.warnings.append("DOM kept changing at the bounded settle limit; use a readiness selector")
                if urlsplit(page.url).scheme not in {"http", "https"} or not document_status:
                    raise ScrapeFailure("browser_navigation", "Browser did not finish on an acquired HTTP(S) document")
                html = await page.content()
                if len(html.encode("utf-8")) > self.options.max_bytes:
                    raise ScrapeFailure("content_too_large", "Rendered DOM exceeds max_bytes; nothing was truncated")
                screenshot = await page.screenshot(type="png", animations="disabled") if self.options.screenshot else None
                if fatal:
                    raise fatal[0]
                return BrowserSnapshot(html, page.url, document_status[-1], screenshot)
            except PlaywrightTimeout as error:
                if fatal:
                    raise fatal[0] from error
                raise ScrapeFailure("browser_timeout", "Browser navigation, action, or readiness condition timed out") from error
            except PlaywrightError as error:
                if fatal:
                    raise fatal[0] from error
                raise ScrapeFailure("browser_error", "Browser could not acquire a complete document") from error
            finally:
                closing = True
                for task in tuple(active_routes):
                    task.cancel()
                if active_routes:
                    await asyncio.gather(*active_routes, return_exceptions=True)
                await context.close()