from __future__ import annotations

import asyncio
import inspect
import json
import math
import time
import urllib.error
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass, field
from email.utils import formatdate
from typing import Any, Protocol
from urllib.parse import quote

from .contracts import ConnectorConfig, Limits, plain


class OperationFault(Exception):
    def __init__(self, status: str, code: str) -> None:
        super().__init__(code)
        self.status = status
        self.code = code


@dataclass(frozen=True)
class HttpRequest:
    method: str
    url: str = field(repr=False)
    headers: Mapping[str, str] = field(repr=False)
    body: Any = field(repr=False)
    timeout_seconds: float
    max_response_bytes: int


@dataclass(frozen=True)
class HttpResponse:
    status: int
    body: Any = field(default=None, repr=False)
    headers: Mapping[str, str] = field(default_factory=dict)


class AsyncTransport(Protocol):
    async def request(self, request: HttpRequest) -> HttpResponse: ...


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        return None


class HttpTransport:
    async def request(self, request: HttpRequest) -> HttpResponse:
        return await asyncio.to_thread(self._request, request)

    @staticmethod
    def _request(request: HttpRequest) -> HttpResponse:
        payload = None if request.body is None else json.dumps(plain(request.body), allow_nan=False).encode()
        native = urllib.request.Request(request.url, data=payload, headers=dict(request.headers), method=request.method)
        opener = urllib.request.build_opener(_NoRedirect())
        try:
            response = opener.open(native, timeout=request.timeout_seconds)
        except urllib.error.HTTPError as error:
            response = error
        except urllib.error.URLError:
            raise OperationFault("unknown", "transport_unavailable") from None
        with response:
            status = response.code
            headers = {name.lower(): value for name, value in response.headers.items()}
            if not 200 <= status < 300:
                return HttpResponse(status, headers=headers)
            raw = response.read(request.max_response_bytes + 1)
        if len(raw) > request.max_response_bytes:
            raise OperationFault("unknown", "response_too_large")
        try:
            body = json.loads(raw) if raw else None
        except (ValueError, UnicodeDecodeError):
            raise OperationFault("unknown", "invalid_provider_json") from None
        return HttpResponse(status, body, headers)

    async def aclose(self) -> None:
        return None


class Session:
    def __init__(self, service: str, config: ConnectorConfig, credential: Any,
                 transport: AsyncTransport | None, concurrency: int) -> None:
        self.service = service
        self.config = config
        self.credential = credential
        self.transport = transport if transport is not None else HttpTransport()
        self.owned_transport = transport is None
        self.gate = asyncio.Semaphore(concurrency)
        self._token_lock = asyncio.Lock()
        self._token = ""
        self._expires = 0.0
        self.closed = False

    async def token(self) -> str:
        async with self._token_lock:
            if self._token and self._expires > time.time() + 300:
                return self._token
            scope = self.config.scope or ("https://search.azure.com/.default" if self.service == "search"
                                          else "https://cosmos.azure.com/.default")
            try:
                method = self.credential.get_token
                access = await method(scope) if inspect.iscoroutinefunction(method) else await asyncio.to_thread(method, scope)
                if inspect.isawaitable(access):
                    access = await access
                token = access.token
                expires = access.expires_on
                if not isinstance(token, str) or not token or "\n" in token or "\r" in token:
                    raise ValueError()
                if type(expires) not in (int, float) or not math.isfinite(expires) or expires <= time.time():
                    raise ValueError()
            except Exception:
                raise OperationFault("denied", "credential_unavailable") from None
            self._token, self._expires = token, expires
            return token

    async def aclose(self) -> None:
        self.closed = True
        if self.owned_transport:
            await self.transport.aclose()


class CallContext:
    def __init__(self, session: Session, limits: Limits) -> None:
        self.session = session
        self.limits = limits
        self.started = time.monotonic()
        self.deadline = self.started + limits.timeout_seconds
        self.attempts = 0

    async def call(self, method: str, path: str, *, body: Any = None,
                   headers: Mapping[str, str] | None = None, mutation: bool = False) -> HttpResponse:
        attempts = 1 if mutation else self.limits.max_attempts
        for attempt in range(attempts):
            remaining = self.deadline - time.monotonic()
            if remaining <= 0:
                raise OperationFault("failed", "deadline_before_request")
            submitted = False
            try:
                async with asyncio.timeout(remaining), self.session.gate:
                    if self.session.closed:
                        raise OperationFault("failed", "connector_closed")
                    token = await self.session.token()
                    outgoing = {"Accept": "application/json", "Content-Type": "application/json"}
                    outgoing.update(headers or {})
                    if self.session.service == "cosmos":
                        outgoing.update({"Authorization": quote(f"type=aad&ver=1.0&sig={token}", safe=""),
                                         "x-ms-date": formatdate(usegmt=True), "x-ms-version": "2018-12-31"})
                    else:
                        outgoing["Authorization"] = f"Bearer {token}"
                    request = HttpRequest(method, self.session.config.endpoint + path, outgoing, body,
                                          max(0.001, self.deadline - time.monotonic()), self.limits.max_output_bytes)
                    self.attempts += 1
                    submitted = True
                    response = await self.session.transport.request(request)
                if not isinstance(response, HttpResponse) or type(response.status) is not int:
                    raise OperationFault("unknown", "invalid_provider_response")
                if response.status in (429, 502, 503, 504) and attempt + 1 < attempts:
                    retry_after = response.headers.get("retry-after", "0")
                    try:
                        delay = max(float(retry_after), 0.01)
                        if not math.isfinite(delay):
                            delay = 0.01
                    except (ValueError, TypeError):
                        delay = 0.01
                    if delay >= self.deadline - time.monotonic():
                        return response
                    await asyncio.sleep(delay)
                    continue
                return response
            except TimeoutError:
                raise OperationFault("unknown" if mutation and submitted else "failed", "deadline_exceeded") from None
            except OSError:
                raise OperationFault("unknown" if mutation and submitted else "failed", "transport_unavailable") from None
        raise AssertionError("empty attempt budget")


def check_response(response: HttpResponse, *, mutation: bool = False) -> None:
    if 200 <= response.status < 300:
        return
    status, code = {
        400: ("invalid", "provider_invalid"), 401: ("denied", "provider_denied"),
        403: ("denied", "provider_denied"), 404: ("not_found", "record_not_found"),
        409: ("conflict", "already_exists"), 412: ("conflict", "version_conflict"),
        422: ("invalid", "provider_invalid"), 429: ("failed", "rate_limited"),
    }.get(response.status, ("unknown" if mutation else "failed", "provider_failure"))
    raise OperationFault(status, code)