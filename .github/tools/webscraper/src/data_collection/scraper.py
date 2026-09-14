from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Iterable

import webres

from .browser import BrowserRenderer, check_status
from .document import inspect_document
from .models import Budget, HTTPResponse, ScrapeFailure, ScrapeOptions, ScrapeResult
from .network import Transport


def html_response(response: HTTPResponse) -> None:
    content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    sniff = response.body.lstrip(b"\xef\xbb\xbf \r\n\t")[:256].lower()
    if content_type not in {"text/html", "application/xhtml+xml"} and not (
        content_type in {"", "text/plain", "application/octet-stream"}
        and sniff.startswith((b"<!doctype html", b"<html", b"<head", b"<body"))
    ):
        raise ScrapeFailure("not_html", "URL did not return an HTML document", status=response.status)


class Scraper:
    def __init__(self, options: ScrapeOptions | None = None):
        self.options = options or ScrapeOptions()
        self._transport = Transport(self.options)
        self._browser = BrowserRenderer(self.options, self._transport)
        self._slots = asyncio.Semaphore(self.options.concurrency)
        self._closed = False

    async def __aenter__(self) -> Scraper:
        if self._closed:
            raise RuntimeError("Scraper is closed")
        return self

    async def __aexit__(self, *_exception) -> None:
        await self.close()

    async def close(self) -> None:
        if not self._closed:
            self._closed = True
            try:
                await self._browser.close()
            finally:
                await self._transport.close()

    async def fetch(self, url: str) -> ScrapeResult:
        if self._closed:
            raise RuntimeError("Scraper is closed")
        async with self._slots:
            started = time.monotonic()
            budget = Budget(started + self.options.timeout)
            result = ScrapeResult(url=url, final_url=url, retrieved_at=webres.now_iso())
            try:
                async with asyncio.timeout(self.options.timeout):
                    initial = None
                    if self.options.mode != "browser":
                        try:
                            initial = await self._transport.request(url, budget, result.attempts)
                            result.status = initial.status
                            result.final_url = initial.url
                            check_status(initial)
                        except ScrapeFailure as error:
                            if self.options.mode == "http" or not error.retryable:
                                raise
                            result.warnings.append(f"HTTP path failed ({error.code}); attempted browser fallback")
                            initial = None
                        if initial:
                            html_response(initial)
                            document = inspect_document(initial.body, initial.headers.get("content-type", ""), self.options.wait_selector)
                            if document.access_barrier:
                                raise ScrapeFailure("access_barrier", "Server returned a verification or access-denial page")
                            requires_actions = self.options.actions or self.options.screenshot or self.options.headed
                            if self.options.mode == "http" or (not document.needs_browser and not requires_actions):
                                if self.options.mode == "http" and document.needs_browser:
                                    result.warnings.append("HTTP source may require rendering; browser mode was disabled")
                                result.html = document.html
                                result.title = document.title
                                result.ok = True
                            else:
                                result.source_html = document.html
                    if not result.ok:
                        result.method = "browser"
                        snapshot = await self._browser.render(url, initial, budget, result)
                        document = inspect_document(snapshot.html)
                        if document.access_barrier:
                            raise ScrapeFailure("access_barrier", "Browser reached a verification or access-denial page")
                        result.html = document.html
                        result.title = document.title
                        result.final_url = snapshot.url
                        result.status = snapshot.status
                        result.screenshot = snapshot.screenshot
                        result.ok = True
            except ScrapeFailure as error:
                result.error_code = error.code
                result.error = str(error)
                if error.status is not None:
                    result.status = error.status
            except TimeoutError:
                result.error_code = "deadline"
                result.error = "Acquisition exceeded its active time budget"
            except ValueError:
                result.error_code = "invalid_selector"
                result.error = "HTML readiness selector is invalid"
            result.elapsed_ms = round((time.monotonic() - started) * 1000)
            result.requests = budget.requests
            result.bytes_received = budget.bytes_received
            if result.blocked_requests:
                result.warnings.append("Some browser requests were blocked; inspect blocked_requests before treating the capture as complete")
            return result

    async def fetch_many(self, urls: Iterable[str]) -> AsyncIterator[ScrapeResult]:
        pending: set[asyncio.Task] = set()
        iterator = iter(urls)
        exhausted = False
        try:
            while pending or not exhausted:
                while not exhausted and len(pending) < self.options.concurrency:
                    try:
                        url = next(iterator)
                    except StopIteration:
                        exhausted = True
                    else:
                        pending.add(asyncio.create_task(self.fetch(url)))
                if pending:
                    done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
                    for task in done:
                        yield task.result()
        finally:
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)