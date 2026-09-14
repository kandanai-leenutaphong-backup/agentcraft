from __future__ import annotations

import asyncio
import gzip
import http.client
import io
import random
import ssl
import time
import urllib.error
import urllib.request
import zlib
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from functools import partial

import webres
from protego import Protego

from .models import Attempt, Budget, HTTPResponse, ScrapeFailure, ScrapeOptions


class RobotsRules:
    def __init__(self, text: str):
        self._rules = Protego.parse(text)

    def can_fetch(self, user_agent: str, url: str) -> bool:
        return self._rules.can_fetch(url, user_agent)

    def crawl_delay(self, user_agent: str):
        return self._rules.crawl_delay(user_agent)

    def request_rate(self, user_agent: str):
        return self._rules.request_rate(user_agent)


def retry_after_seconds(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        if value.strip().isdigit():
            return float(int(value.strip()))
        date = parsedate_to_datetime(value)
        if date.tzinfo is None:
            date = date.replace(tzinfo=timezone.utc)
        return max(0.0, (date - datetime.now(timezone.utc)).total_seconds())
    except (ValueError, TypeError, OverflowError):
        return None


def decode_entity(raw: bytes, encoding: str, limit: int) -> bytes:
    try:
        if encoding in {"", "identity"}:
            payload = raw
        elif encoding in {"gzip", "x-gzip"}:
            with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream:
                payload = stream.read(limit + 1)
        elif encoding == "deflate":
            try:
                decoder = zlib.decompressobj()
                payload = decoder.decompress(raw, limit + 1)
            except zlib.error:
                decoder = zlib.decompressobj(-zlib.MAX_WBITS)
                payload = decoder.decompress(raw, limit + 1)
            if len(payload) <= limit and (not decoder.eof or decoder.unused_data):
                raise ScrapeFailure("content_decode", "Incomplete or malformed deflate response")
        else:
            raise ScrapeFailure("content_decode", "Server returned an unsupported content encoding")
    except (OSError, EOFError, zlib.error) as error:
        raise ScrapeFailure("content_decode", "Compressed response was malformed or incomplete") from error
    if len(payload) > limit:
        raise ScrapeFailure("content_too_large", "Decoded response exceeds max_bytes; nothing was truncated")
    return payload


def request_sync(
    url: str,
    *,
    options: ScrapeOptions,
    deadline: float,
    method: str = "GET",
    headers: dict[str, str] | None = None,
) -> HTTPResponse:
    request_headers = {
        "User-Agent": webres.USER_AGENT,
        "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5",
        "Accept-Encoding": "gzip, deflate",
        "Accept-Language": "en",
    }
    request_headers.update({name: value for name, value in (headers or {}).items()
                            if name.lower() in {"accept", "accept-language", "origin", "referer"}})
    try:
        request = urllib.request.Request(url, method=method, headers=request_headers)
        try:
            response = webres.open_public(request, timeout=options.request_timeout, deadline=deadline, robots_parser=RobotsRules)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            response_headers = {name.lower(): value for name, value in response.headers.items()}
            length = response_headers.get("content-length", "")
            if length.isdigit() and int(length) > options.max_bytes:
                raise ScrapeFailure("content_too_large", "Response exceeds max_bytes; nothing was truncated")
            chunks = []
            received = 0
            while True:
                if time.monotonic() >= deadline:
                    raise ScrapeFailure("deadline", "Acquisition deadline exceeded")
                chunk = response.read(min(65536, options.max_bytes + 1 - received))
                if not chunk:
                    break
                received += len(chunk)
                if received > options.max_bytes:
                    raise ScrapeFailure("content_too_large", "Response exceeds max_bytes; nothing was truncated")
                chunks.append(chunk)
            if method != "HEAD" and length.isdigit() and received != int(length):
                raise ScrapeFailure("incomplete_response", "Response ended before Content-Length", retryable=True)
            payload = decode_entity(b"".join(chunks), response_headers.get("content-encoding", "").lower(), options.max_bytes)
            return HTTPResponse(response.geturl(), response.status, response_headers, payload)
    except webres.RobotsDisallowed as error:
        raise ScrapeFailure("robots_disallowed", "robots.txt denied or could not authorize this request") from error
    except webres.AcquisitionError as error:
        raise ScrapeFailure("url_refused", "Public-URL policy refused the address, method, or redirect") from error
    except (ValueError, UnicodeError) as error:
        raise ScrapeFailure("invalid_url", "URL, host, or port is invalid") from error
    except (urllib.error.URLError, OSError, http.client.HTTPException) as error:
        reason = error.reason if isinstance(error, urllib.error.URLError) else error
        if isinstance(reason, ssl.SSLCertVerificationError):
            raise ScrapeFailure("tls_verification", "Server TLS certificate verification failed") from error
        if time.monotonic() >= deadline:
            raise ScrapeFailure("deadline", "Acquisition deadline exceeded") from error
        raise ScrapeFailure("network_error", f"HTTP transport failed ({type(reason).__name__})", retryable=True) from error


class Transport:
    def __init__(self, options: ScrapeOptions):
        self.options = options
        self._workers = ThreadPoolExecutor(max_workers=options.http_workers, thread_name_prefix="html-fetch")

    async def close(self) -> None:
        await asyncio.to_thread(self._workers.shutdown, wait=True, cancel_futures=True)

    async def request(
        self,
        url: str,
        budget: Budget,
        attempts: list[Attempt],
        *,
        stage: str = "http",
        method: str = "GET",
        headers: dict[str, str] | None = None,
    ) -> HTTPResponse:
        for retry in range(self.options.retries + 1):
            if time.monotonic() >= budget.deadline:
                raise ScrapeFailure("deadline", "Acquisition deadline exceeded")
            if budget.requests >= self.options.max_requests:
                raise ScrapeFailure("request_budget", "Acquisition reached max_requests")
            budget.requests += 1
            started = time.monotonic()
            try:
                response = await asyncio.get_running_loop().run_in_executor(
                    self._workers,
                    partial(request_sync, url, options=self.options, deadline=budget.deadline, method=method, headers=headers),
                )
                budget.bytes_received += len(response.body)
                if budget.bytes_received > self.options.max_total_bytes:
                    raise ScrapeFailure("byte_budget", "Acquisition reached max_total_bytes")
            except ScrapeFailure as error:
                attempts.append(Attempt(stage, error.status, round((time.monotonic() - started) * 1000), error.code))
                if not error.retryable or retry == self.options.retries:
                    raise
                response = None
            else:
                attempts.append(Attempt(stage, response.status, round((time.monotonic() - started) * 1000)))
                if response.status not in {408, 425, 429, 500, 502, 503, 504} or retry == self.options.retries:
                    return response
            delay = retry_after_seconds(response.headers.get("retry-after")) if response else None
            delay = max(delay or 0, random.uniform(0.25, 0.75) * 2 ** retry)
            if time.monotonic() + delay >= budget.deadline:
                code = "retry_after" if response and response.headers.get("retry-after") else "deadline"
                raise ScrapeFailure(code, "Required retry delay exceeds remaining acquisition budget",
                                    status=response.status if response else None)
            await asyncio.sleep(delay)
        raise AssertionError("retry loop did not return")