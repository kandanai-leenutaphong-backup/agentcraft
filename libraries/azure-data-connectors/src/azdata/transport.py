from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol


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