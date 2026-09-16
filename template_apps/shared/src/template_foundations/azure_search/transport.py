"""Authenticated JSON transport with token caching and bounded retries.

``opener(request, timeout) -> (status, body_bytes)`` is the whole seam. Injecting
one makes every operation in this component testable with no Azure account and
no network.
"""

from __future__ import annotations

import json
import random
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

from .config import SEARCH_SCOPE
from search_read_adapter import SearchError

#: Only these are worth another attempt. Everything else is a fault the caller must see.
RETRYABLE_STATUS = frozenset({429, 502, 503, 504})

#: Refresh a little before expiry rather than discovering it mid-request.
_TOKEN_SKEW_SECONDS = 300


class Transport:
    """Signs, sends, retries, and decodes. Holds no credential material on disk."""

    def __init__(
        self,
        *,
        credential: Any | None = None,
        scope: str = SEARCH_SCOPE,
        opener: Callable[[urllib.request.Request, float], tuple[int, bytes]] | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._credential = credential
        self._scope = scope
        self._opener = opener or _urlopen
        self._sleep = sleep
        self._token: str = ""
        self._expires_on: float = 0.0

    def token(self) -> str:
        """A bearer token for the configured scope, cached until near expiry."""
        now = time.time()
        if self._token and now < self._expires_on - _TOKEN_SKEW_SECONDS:
            return self._token
        credential = self._credential
        if credential is None:
            from azure_llm_compat import azure_credential

            credential = self._credential = azure_credential()
        access = credential.get_token(self._scope)
        self._token = access.token
        self._expires_on = float(getattr(access, "expires_on", now + 3600))
        return self._token

    def request(
        self,
        method: str,
        url: str,
        *,
        body: Any = None,
        timeout: float = 60.0,
        max_attempts: int = 4,
        absent_ok: bool = False,
    ) -> Any:
        """One signed call. Returns the decoded body, or ``None`` for 204 and allowed 404."""
        payload = None if body is None else json.dumps(body).encode("utf-8")
        headers = {"Accept": "application/json"}
        if payload is not None:
            headers["Content-Type"] = "application/json"

        last: SearchError | None = None
        for attempt in range(max_attempts):
            request = urllib.request.Request(url, data=payload, method=method, headers=dict(headers))
            request.add_header("Authorization", f"Bearer {self.token()}")
            status, raw = self._opener(request, timeout)
            decoded = _decode(raw)

            if status == 404 and absent_ok:
                return None
            if 200 <= status < 300:
                # 207 is partial success: the caller must inspect every entry.
                return decoded
            message = _message(decoded, status)
            last = SearchError(status, message, body=decoded)
            if status not in RETRYABLE_STATUS or attempt == max_attempts - 1:
                raise last
            self._sleep(_delay(decoded, attempt))
        raise last if last is not None else SearchError(0, "no attempt was made")


def _urlopen(request: urllib.request.Request, timeout: float) -> tuple[int, bytes]:
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()
    except urllib.error.URLError as exc:
        raise SearchError(0, f"could not reach the service: {exc.reason}") from exc


def _decode(raw: bytes) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return {"raw": raw[:2000].decode("utf-8", "replace")}


def _message(decoded: Any, status: int) -> str:
    if isinstance(decoded, dict):
        error = decoded.get("error")
        if isinstance(error, dict) and error.get("message"):
            return str(error["message"])
        if decoded.get("message"):
            return str(decoded["message"])
    return f"request failed with status {status}"


def _delay(decoded: Any, attempt: int) -> float:
    if isinstance(decoded, dict):
        error = decoded.get("error")
        if isinstance(error, dict) and isinstance(error.get("retryAfterSeconds"), (int, float)):
            return float(error["retryAfterSeconds"])
    return min(2.0**attempt, 30.0) * (0.5 + random.random() / 2)
