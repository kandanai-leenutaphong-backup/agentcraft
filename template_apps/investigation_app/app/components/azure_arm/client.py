"""Signed Azure Resource Manager REST over the standard library.

The control plane is the one Azure surface this repository still reaches by hand: Cosmos DB
for Gremlin has no Entra data plane, so an account key must be read from ARM at run time,
and a Gremlin graph must be created through ARM because an Azure Function has no `az`
binary. Three callers grew their own copy of that plumbing. This is the single copy.

``opener(request, timeout) -> (status, body_bytes)`` is the whole seam. Injecting one makes
every operation testable with no Azure account and no network.

Nothing here knows what a Cosmos account is. Resource semantics belong to the connector that
owns the datastore; only the transport lives here.
"""

from __future__ import annotations

import json
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Any

from .config import ArmConfig

#: Worth another attempt. Everything else is a fault the caller must see immediately.
RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})

#: Refresh a little before expiry rather than discovering it mid-request.
_TOKEN_SKEW_SECONDS = 300


class ArmError(RuntimeError):
    """A failed control-plane call, carrying the status and ARM's own message."""

    def __init__(self, status: int, message: str, *, body: Any = None) -> None:
        super().__init__(f"{status}: {message}")
        self.status = status
        self.message = message
        self.body = body


def resource_path(subscription: str, resource_group: str, provider: str,
                  *segments: str) -> str:
    """Build a provider resource path with every caller-supplied part percent-encoded.

    Encoding with ``safe=""`` is the control that stops a configured name containing a
    slash or a dot-segment from re-pointing the request at another resource.
    """
    required = {"subscription": subscription, "resource group": resource_group,
                "provider": provider}
    missing = [name for name, value in required.items() if not (value or "").strip()]
    if missing:
        raise ArmError(0, "unset: " + ", ".join(missing))
    if len(segments) % 2:
        raise ArmError(0, "segments must pair a resource type with a resource name")
    quote = lambda part: urllib.parse.quote(str(part), safe="")  # noqa: E731
    path = (f"/subscriptions/{quote(subscription)}"
            f"/resourceGroups/{quote(resource_group)}"
            f"/providers/{urllib.parse.quote(provider, safe='.')}")
    for index, segment in enumerate(segments):
        if not str(segment).strip():
            raise ArmError(0, f"empty path segment at position {index}")
        path += "/" + quote(segment)
    return path


class ArmClient:
    """Signs, sends, retries, and decodes. Holds no credential material on disk."""

    def __init__(
        self,
        config: ArmConfig | None = None,
        *,
        credential: Any | None = None,
        opener: Callable[[urllib.request.Request, float], tuple[int, bytes]] | None = None,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.config = config or ArmConfig()
        self._credential = credential
        self._opener = opener or _urlopen
        self._sleep = sleep
        self._monotonic = monotonic
        self._token: str = ""
        self._expires_on: float = 0.0

    @classmethod
    def from_env(cls, prefix: str = "ARM_", **kwargs: Any) -> ArmClient:
        """Resolve configuration from the environment at call time."""
        return cls(ArmConfig.from_env(prefix), **kwargs)

    def token(self) -> str:
        """A bearer token for the configured scope, cached until near expiry."""
        now = time.time()
        if self._token and now < self._expires_on - _TOKEN_SKEW_SECONDS:
            return self._token
        credential = self._credential
        if credential is None:
            from azure_llm_compat import azure_credential

            credential = self._credential = azure_credential()
        access = credential.get_token(self.config.scope)
        self._token = access.token
        self._expires_on = float(getattr(access, "expires_on", now + 3600))
        return self._token

    def request(self, method: str, path: str, *, body: Any = None,
                timeout: float | None = None, max_attempts: int | None = None,
                absent_ok: bool = False) -> tuple[int, Any]:
        """One signed call. Returns ``(status, decoded)``; an empty body decodes to ``{}``.

        ARM answers a bodyless POST such as `listKeys` only when it is sent a body at all,
        so a POST with nothing to say is sent an empty payload rather than ``None``.
        """
        if not path.startswith("/"):
            raise ArmError(0, f"ARM path must be absolute: {path!r}")
        url = f"{self.config.endpoint}{path}"
        payload = (json.dumps(body).encode("utf-8") if body is not None
                   else (b"" if method.upper() == "POST" else None))
        attempts = max_attempts if max_attempts is not None else self.config.max_attempts
        seconds = timeout if timeout is not None else self.config.timeout_seconds

        last: ArmError | None = None
        for attempt in range(attempts):
            request = urllib.request.Request(
                url, data=payload, method=method.upper(),
                headers={"Accept": "application/json", "Content-Type": "application/json"},
            )
            request.add_header("Authorization", f"Bearer {self.token()}")
            status, raw = self._opener(request, seconds)
            decoded = _decode(raw)
            if status == 404 and absent_ok:
                return 404, {}
            if 200 <= status < 300:
                return status, decoded
            last = ArmError(status, _message(decoded, status, method, path), body=decoded)
            if status not in RETRYABLE_STATUS or attempt == attempts - 1:
                raise last
            self._sleep(min(2.0**attempt, 30.0) * (0.5 + random.random() / 2))
        raise last if last is not None else ArmError(0, "no attempt was made")

    def get(self, path: str, **kwargs: Any) -> tuple[int, Any]:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> tuple[int, Any]:
        return self.request("POST", path, **kwargs)

    def put(self, path: str, **kwargs: Any) -> tuple[int, Any]:
        return self.request("PUT", path, **kwargs)

    def await_provisioned(self, path: str, *, wait_seconds: float = 300.0,
                          interval_seconds: float = 5.0) -> None:
        """Poll until the resource answers 200.

        ARM accepts a child-resource PUT and provisions it afterwards, so a 201 says the
        request was taken, not that the resource is usable.
        """
        deadline = self._monotonic() + wait_seconds
        while True:
            if self.get(path, absent_ok=True)[0] == 200:
                return
            if self._monotonic() >= deadline:
                raise ArmError(0, f"timed out after {wait_seconds:g}s waiting for "
                                  f"{path.split('?')[0]}")
            self._sleep(interval_seconds)

    def describe(self) -> dict[str, Any]:
        """Non-secret configuration. Makes no request."""
        return {"component": "azure_arm", **self.config.describe()}


def _urlopen(request: urllib.request.Request, timeout: float) -> tuple[int, bytes]:
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()
    except urllib.error.URLError as exc:
        raise ArmError(0, f"could not reach ARM: {exc.reason}") from exc


def _decode(raw: bytes) -> Any:
    if not raw:
        return {}
    try:
        return json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return {"raw": raw[:2000].decode("utf-8", "replace")}


def _message(decoded: Any, status: int, method: str, path: str) -> str:
    if isinstance(decoded, dict):
        error = decoded.get("error")
        if isinstance(error, dict) and error.get("message"):
            return str(error["message"])[:300]
        if decoded.get("message"):
            return str(decoded["message"])[:300]
    return f"ARM {method.upper()} {path.split('?')[0]} failed with status {status}"


__all__ = ["ArmClient", "ArmError", "RETRYABLE_STATUS", "resource_path"]
