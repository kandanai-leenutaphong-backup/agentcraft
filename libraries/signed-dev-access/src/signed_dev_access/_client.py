from __future__ import annotations

import base64
import hashlib
import ipaddress
import math
import os
import re
import stat
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from http.client import HTTPConnection, HTTPSConnection
from pathlib import Path
from urllib.parse import urlsplit

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from ._middleware import (
    CONTEXT_HEADER,
    MAX_SIGNED_BODY_BYTES,
    SIGNATURE_HEADER,
    TIMESTAMP_HEADER,
)
from ._verifier import MAX_CONTEXT_CHARS, MAX_PATH_CHARS, MAX_SKEW_SECONDS, _SLUG, canonical_string

SIGNING_HEADERS = frozenset(header.lower() for header in (TIMESTAMP_HEADER, SIGNATURE_HEADER, CONTEXT_HEADER))


class SigningError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def load_private_key(path: str | os.PathLike[str]) -> Ed25519PrivateKey:
    try:
        location = Path(path)
    except (TypeError, ValueError):
        raise SigningError("invalid_key_path") from None
    if not location.is_absolute() or ".." in location.parts or not location.name:
        raise SigningError("invalid_key_path")
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "geteuid"):
        raise SigningError("private_file_checks_unavailable")
    directory = None
    descriptor = None
    try:
        directory = os.open(location.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        for part in (*location.parts[1:-1], None):
            for marker in (".git", ".hg", ".svn"):
                try:
                    os.stat(marker, dir_fd=directory, follow_symlinks=False)
                except FileNotFoundError:
                    continue
                raise SigningError("key_in_repository")
            if part is not None:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
                os.close(directory)
                directory = child
        parent = os.fstat(directory)
        if parent.st_uid != os.geteuid() or stat.S_IMODE(parent.st_mode) & 0o077:
            raise SigningError("unsafe_key_directory")
        descriptor = os.open(location.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.geteuid()
            or before.st_nlink != 1
            or stat.S_IMODE(before.st_mode) not in (0o400, 0o600)
        ):
            raise SigningError("unsafe_key_file")
        if before.st_size != 32:
            raise SigningError("invalid_private_key")
        raw = os.read(descriptor, 33)
        after = os.fstat(descriptor)
        if len(raw) != 32 or (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise SigningError("invalid_private_key")
        return Ed25519PrivateKey.from_private_bytes(raw)
    except SigningError:
        raise
    except (OSError, ValueError):
        raise SigningError("private_key_unavailable") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if directory is not None:
            os.close(directory)


def sign_headers(
    private_key: Ed25519PrivateKey,
    method: str,
    path_and_query: str,
    body: bytes = b"",
    context_slug: str = "",
    *,
    timestamp: datetime | None = None,
) -> dict[str, str]:
    if not isinstance(private_key, Ed25519PrivateKey):
        raise SigningError("invalid_private_key")
    if not isinstance(method, str) or re.fullmatch(r"[A-Za-z]{1,32}", method) is None:
        raise SigningError("invalid_method")
    if (
        not isinstance(path_and_query, str)
        or not path_and_query.startswith("/")
        or path_and_query.startswith("//")
        or len(path_and_query) > MAX_PATH_CHARS
        or any(ord(character) <= 32 or ord(character) >= 127 for character in path_and_query)
        or "#" in path_and_query
        or "\\" in path_and_query
        or re.search(r"%(?![0-9A-Fa-f]{2})", path_and_query)
    ):
        raise SigningError("invalid_path")
    parsed = urlsplit(path_and_query)
    if "?" in path_and_query and not parsed.query:
        raise SigningError("invalid_path")
    if not isinstance(body, bytes) or len(body) > MAX_SIGNED_BODY_BYTES:
        raise SigningError("invalid_body")
    if not isinstance(context_slug, str) or len(context_slug) > MAX_CONTEXT_CHARS:
        raise SigningError("invalid_context")
    slug = context_slug.strip().lower()
    if _SLUG.fullmatch(slug) is None:
        raise SigningError("invalid_context")
    moment = timestamp if timestamp is not None else datetime.now(timezone.utc)
    if not isinstance(moment, datetime) or moment.tzinfo is None or moment.utcoffset() is None:
        raise SigningError("invalid_timestamp")
    stamp = moment.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
    message = canonical_string(
        method=method,
        path_and_query=path_and_query,
        timestamp=stamp,
        context_slug=slug,
        body_sha256_hex=hashlib.sha256(body).hexdigest(),
    )
    headers = {
        TIMESTAMP_HEADER: stamp,
        SIGNATURE_HEADER: base64.b64encode(private_key.sign(message)).decode("ascii"),
    }
    if slug:
        headers[CONTEXT_HEADER] = slug
    return headers


def _url_parts(url: str):
    if (
        not isinstance(url, str)
        or any(ord(character) <= 32 or ord(character) >= 127 for character in url)
        or "\\" in url
        or "#" in url
    ):
        raise SigningError("invalid_url")
    try:
        parts = urlsplit(url)
        port = parts.port
        if (
            parts.scheme not in ("http", "https")
            or not parts.hostname
            or parts.username is not None
            or parts.password is not None
            or (port is not None and not 1 <= port <= 65535)
        ):
            raise ValueError
        return parts
    except ValueError:
        raise SigningError("invalid_url") from None


def _origin(parts) -> str:
    host = parts.hostname.lower()
    if ":" in host:
        host = f"[{host}]"
    port = parts.port
    suffix = f":{port}" if port is not None and port != (443 if parts.scheme == "https" else 80) else ""
    return f"{parts.scheme}://{host}{suffix}"


@dataclass(frozen=True, slots=True)
class SignedResponse:
    status: int
    body: bytes = field(default=b"", repr=False)

    def metadata(self) -> dict[str, int]:
        return {"status": self.status, "response_bytes": len(self.body)}


class RequestSigner:
    def __init__(
        self,
        private_key: Ed25519PrivateKey,
        *,
        origin: str,
        context_slug: str = "",
        allow_loopback_http: bool = False,
        allow_mutations: bool = False,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not isinstance(private_key, Ed25519PrivateKey):
            raise SigningError("invalid_private_key")
        parts = _url_parts(origin)
        if parts.path not in ("", "/") or parts.query or "?" in origin:
            raise SigningError("invalid_origin")
        if not isinstance(allow_loopback_http, bool) or not isinstance(allow_mutations, bool):
            raise SigningError("invalid_policy")
        if parts.scheme != "https":
            try:
                loopback = parts.hostname == "localhost" or ipaddress.ip_address(parts.hostname).is_loopback
            except ValueError:
                loopback = False
            if not allow_loopback_http or not loopback:
                raise SigningError("https_required")
        if not isinstance(context_slug, str) or len(context_slug) > MAX_CONTEXT_CHARS or _SLUG.fullmatch(context_slug.strip().lower()) is None:
            raise SigningError("invalid_context")
        self._private_key = private_key
        self._origin = _origin(parts)
        self._parts = parts
        self._context_slug = context_slug.strip().lower()
        self._allow_mutations = allow_mutations
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._last_timestamp: datetime | None = None
        self._lock = threading.Lock()

    @property
    def origin(self) -> str:
        return self._origin

    def matches(self, url: str) -> bool:
        return _origin(_url_parts(url)) == self._origin

    def headers_for(
        self,
        method: str,
        url: str,
        body: bytes = b"",
        *,
        headers: Mapping[str, str] | None = None,
    ) -> dict[str, str]:
        incoming = headers if headers is not None else {}
        if not isinstance(incoming, Mapping) or any(not isinstance(name, str) or not isinstance(value, str) for name, value in incoming.items()):
            raise SigningError("invalid_headers")
        outgoing = {name: value for name, value in incoming.items() if name.lower() not in SIGNING_HEADERS}
        parts = _url_parts(url)
        if _origin(parts) != self._origin:
            return outgoing
        if not isinstance(method, str) or re.fullmatch(r"[A-Za-z]{1,32}", method) is None:
            raise SigningError("invalid_method")
        if method.upper() not in ("GET", "HEAD", "OPTIONS") and not self._allow_mutations:
            raise SigningError("mutation_not_authorized")
        path = parts.path or "/"
        if "?" in url:
            path += "?" + parts.query
        with self._lock:
            moment = self._clock()
            if not isinstance(moment, datetime) or moment.tzinfo is None or moment.utcoffset() is None:
                raise SigningError("invalid_timestamp")
            moment = moment.astimezone(timezone.utc)
            stamp = max(moment, self._last_timestamp + timedelta(microseconds=1)) if self._last_timestamp else moment
            if (stamp - moment).total_seconds() > MAX_SKEW_SECONDS:
                raise SigningError("clock_stalled")
            signed = sign_headers(self._private_key, method, path, body, self._context_slug, timestamp=stamp)
            self._last_timestamp = stamp
        outgoing.update(signed)
        return outgoing

    def request(
        self,
        method: str,
        path_and_query: str,
        body: bytes = b"",
        *,
        content_type: str = "application/octet-stream",
        timeout_seconds: float = 30,
        max_response_bytes: int = 1_048_576,
        connection_factory=None,
    ) -> SignedResponse:
        if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float)) or not math.isfinite(timeout_seconds) or not 0 < timeout_seconds <= 300:
            raise SigningError("invalid_timeout")
        if isinstance(max_response_bytes, bool) or not isinstance(max_response_bytes, int) or not 1 <= max_response_bytes <= 16_777_216:
            raise SigningError("invalid_response_limit")
        if not isinstance(path_and_query, str) or not path_and_query.startswith("/"):
            raise SigningError("invalid_path")
        if not isinstance(content_type, str) or len(content_type) > 256 or any(ord(character) < 32 or ord(character) >= 127 for character in content_type):
            raise SigningError("invalid_content_type")
        headers = self.headers_for(method, self._origin + path_and_query, body)
        if body:
            headers["Content-Type"] = content_type
        factory = connection_factory or (HTTPSConnection if self._parts.scheme == "https" else HTTPConnection)
        connection = None
        try:
            deadline = time.monotonic() + timeout_seconds
            connection = factory(self._parts.hostname, port=self._parts.port, timeout=timeout_seconds)
            connection.set_debuglevel(0)
            connection.request(method.upper(), path_and_query, body=body, headers=headers)
            response = connection.getresponse()
            if not isinstance(response.status, int) or isinstance(response.status, bool) or not 100 <= response.status <= 599:
                raise SigningError("invalid_response")
            if 300 <= response.status < 400:
                raise SigningError("redirect_refused")
            if not 200 <= response.status < 300:
                return SignedResponse(response.status)
            result = bytearray()
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise SigningError("request_timeout")
                if connection.sock is not None:
                    connection.sock.settimeout(remaining)
                chunk = response.read1(min(65_536, max_response_bytes + 1 - len(result)))
                if not isinstance(chunk, bytes):
                    raise SigningError("invalid_response")
                if not chunk:
                    return SignedResponse(response.status, bytes(result))
                if len(result) + len(chunk) > max_response_bytes:
                    raise SigningError("response_limit")
                result.extend(chunk)
        except SigningError:
            raise
        except TimeoutError:
            raise SigningError("request_timeout") from None
        except Exception:
            raise SigningError("request_failed") from None
        finally:
            if connection is not None:
                try:
                    connection.close()
                except Exception:
                    raise SigningError("close_failed") from None