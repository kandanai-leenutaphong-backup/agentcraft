from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal


class ScrapeFailure(RuntimeError):
    def __init__(self, code: str, message: str, *, status: int | None = None, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.status = status
        self.retryable = retryable


@dataclass(frozen=True, slots=True)
class BrowserAction:
    kind: Literal["click", "wait", "scroll"]
    selector: str | None = None
    pixels: int = 720

    def __post_init__(self) -> None:
        if self.kind not in {"click", "wait", "scroll"}:
            raise ValueError("action kind must be click, wait, or scroll")
        if self.kind in {"click", "wait"} and (not isinstance(self.selector, str) or not self.selector.strip()):
            raise ValueError("click and wait actions require a selector")
        if type(self.pixels) is not int or not 0 < abs(self.pixels) <= 5000:
            raise ValueError("scroll pixels must be a nonzero integer between -5000 and 5000")


@dataclass(frozen=True, slots=True)
class ScrapeOptions:
    mode: Literal["auto", "http", "browser"] = "auto"
    timeout: float = 90
    request_timeout: float = 20
    retries: int = 2
    concurrency: int = 4
    http_workers: int = 8
    browser_concurrency: int = 2
    max_bytes: int = 16 * 1024 * 1024
    max_total_bytes: int = 64 * 1024 * 1024
    max_requests: int = 80
    wait_selector: str | None = None
    settle_ms: int = 800
    actions: tuple[BrowserAction, ...] = ()
    screenshot: bool = False
    headed: bool = False
    browser_executable: str | None = None

    def __post_init__(self) -> None:
        if self.mode not in {"auto", "http", "browser"}:
            raise ValueError("mode must be auto, http, or browser")
        for name, maximum in (("timeout", 600), ("request_timeout", 120)):
            value = getattr(self, name)
            if not isinstance(value, (float, int)) or not math.isfinite(value) or not 0 < value <= maximum:
                raise ValueError(f"{name} must be finite, positive, and at most {maximum}")
        for name, minimum, maximum in (
            ("retries", 0, 5), ("concurrency", 1, 32), ("http_workers", 1, 32),
            ("browser_concurrency", 1, 8), ("max_bytes", 1, 16 * 1024 * 1024),
            ("max_total_bytes", 1, 256 * 1024 * 1024), ("max_requests", 1, 500),
            ("settle_ms", 100, 5000),
        ):
            value = getattr(self, name)
            if type(value) is not int or not minimum <= value <= maximum:
                raise ValueError(f"{name} must be an integer between {minimum} and {maximum}")
        if len(self.actions) > 30 or any(not isinstance(action, BrowserAction) for action in self.actions):
            raise ValueError("actions must contain at most 30 BrowserAction values")
        if self.mode == "http" and (self.actions or self.screenshot or self.headed):
            raise ValueError("actions, screenshots, and headed mode require auto or browser mode")
        if self.wait_selector is not None and (not isinstance(self.wait_selector, str) or not self.wait_selector.strip()):
            raise ValueError("wait_selector must be a nonempty CSS selector")


@dataclass(frozen=True, slots=True)
class HTTPResponse:
    url: str
    status: int
    headers: dict[str, str]
    body: bytes


@dataclass(frozen=True, slots=True)
class Attempt:
    stage: str
    status: int | None
    elapsed_ms: int
    error: str | None = None


@dataclass(slots=True)
class Budget:
    deadline: float
    requests: int = 0
    bytes_received: int = 0


@dataclass(slots=True)
class ScrapeResult:
    url: str
    ok: bool = False
    final_url: str = ""
    method: str = "http"
    status: int | None = None
    html: str = ""
    source_html: str | None = None
    title: str = ""
    retrieved_at: str = ""
    elapsed_ms: int = 0
    requests: int = 0
    bytes_received: int = 0
    attempts: list[Attempt] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    blocked_requests: dict[str, int] = field(default_factory=dict)
    error_code: str | None = None
    error: str | None = None
    screenshot: bytes | None = field(default=None, repr=False)