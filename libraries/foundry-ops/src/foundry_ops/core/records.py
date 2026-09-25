"""Immutable evidence records: intent before mutation, no overwrite, digest pins, safe summaries."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from .errors import ReadbackError, RefusedError, UnresolvedIntentError

RECORD_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,199}")
SENSITIVE_KEYS = frozenset({"authorization", "credential", "credentials", "sas_uri", "api_key", "headers",
                            "reasoning", "token", "password", "secret"})
_SECRET_ASSIGNMENT = re.compile(r"(?i)(sig|token|api[_-]?key|authorization|password|secret)\s*[=:]\s*[^\s,;&]+")
_BEARER = re.compile(r"(?i)(Bearer\s+)[^\s&]+")
_JWT = re.compile(r"eyJ[A-Za-z0-9_.-]+")
_URL = re.compile(r"https?://[^\s\"<>]+", re.IGNORECASE)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str | os.PathLike[str]) -> str:
    return sha256_hex(Path(path).read_bytes())


def pin(path: str | os.PathLike[str], *, root: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    source = Path(path)
    data = source.read_bytes()
    shown = source.resolve().relative_to(Path(root).resolve()) if root is not None else source
    return {"path": shown.as_posix(), "sha256": sha256_hex(data), "bytes": len(data)}


def encode_json(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def utc_stamp(now: datetime | None = None) -> str:
    return (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%S%fZ")


def to_plain(value: Any) -> Any:
    """Convert Azure (`as_dict`) and OpenAI (`model_dump`) models to JSON-shaped values."""
    if hasattr(value, "as_dict"):
        value = value.as_dict()
    elif hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    if isinstance(value, Mapping):
        return {key: to_plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_plain(item) for item in value]
    return value


def redact_text(text: str) -> str:
    text = _JWT.sub("[REDACTED]", text)
    text = _BEARER.sub(r"\1[REDACTED]", text)
    return _SECRET_ASSIGNMENT.sub(r"\1=[REDACTED]", text)


def _clean_url(match: re.Match[str]) -> str:
    try:
        parsed = urlsplit(match[0])
        return urlunsplit((parsed.scheme, parsed.netloc.rsplit("@", 1)[-1], parsed.path, "", ""))
    except ValueError:
        return "[invalid-url-redacted]"


def sanitize(value: Any, *, drop_keys: frozenset[str] = SENSITIVE_KEYS) -> Any:
    """Drop credential-shaped keys; strip userinfo, query and fragment from every URL in strings."""
    if isinstance(value, Mapping):
        return {key: sanitize(item, drop_keys=drop_keys) for key, item in value.items()
                if str(key).lower() not in drop_keys}
    if isinstance(value, (list, tuple)):
        return [sanitize(item, drop_keys=drop_keys) for item in value]
    if isinstance(value, str):
        return _URL.sub(_clean_url, value)
    return value


def error_summary(error: BaseException, *, limit: int = 4000) -> dict[str, Any]:
    """Bounded, redacted error shape for receipts; provider body fields are a fixed allowlist."""
    detail = getattr(error, "error", None)
    message = getattr(detail, "message", None) or str(error)
    summary: dict[str, Any] = {
        "type": type(error).__name__,
        "status_code": getattr(error, "status_code", None),
        "code": getattr(detail, "code", None) or getattr(error, "code", None),
        "request_id": getattr(error, "request_id", None),
        "reason": redact_text(sanitize(str(message)))[:limit],
    }
    response = getattr(error, "response", None)
    if response is not None and hasattr(response, "json"):
        try:
            body = response.json()
            if isinstance(body, dict) and isinstance(body.get("error"), dict):
                body = body["error"]
        except (ValueError, AttributeError, TypeError):
            body = None
        if isinstance(body, dict):
            detail_fields = _bounded_tree(sanitize({key: body.get(key) for key in
                                                    ("code", "message", "type", "param", "title", "detail", "traceId")}),
                                          limit)
            detail_fields.update({key: _bounded_tree(sanitize(body[key]), limit) for key in ("errors", "details")
                                  if body.get(key) is not None})
            summary["provider_detail"] = detail_fields
    return summary


def _bounded_tree(value: Any, limit: int, depth: int = 0) -> Any:
    if depth > 5:
        return "[depth-truncated]"
    if isinstance(value, Mapping):
        return {key: _bounded_tree(item, limit, depth + 1) for key, item in list(value.items())[:50]}
    if isinstance(value, (list, tuple)):
        return [_bounded_tree(item, limit, depth + 1) for item in value[:20]]
    if isinstance(value, str):
        return redact_text(value)[:limit]
    return value


def _contained(path: str | os.PathLike[str], root: str | os.PathLike[str]) -> Path:
    candidate = Path(path)
    if candidate.is_symlink() or not candidate.resolve().is_relative_to(Path(root).resolve()):
        raise RefusedError("foreign_path", "path must be a non-symlink inside its owning root")
    return candidate.resolve()


def read_pinned(path: str | os.PathLike[str], *, root: str | os.PathLike[str],
                expected_sha256: str | None = None) -> Any:
    source = _contained(path, root)
    data = source.read_bytes()
    if expected_sha256 is not None and sha256_hex(data) != expected_sha256:
        raise RefusedError("digest_mismatch", "pinned record digest mismatch")
    return json.loads(data)


def read_receipt(path: str | os.PathLike[str], *, root: str | os.PathLike[str], action: str,
                 expected_sha256: str | None = None, expect: Mapping[str, Any] | None = None) -> Any:
    """Return `result` of an owned, complete receipt for `action`; `expect` pins top-level fields."""
    receipt = read_pinned(path, root=root, expected_sha256=expected_sha256)
    if not isinstance(receipt, dict) or receipt.get("action") != action or receipt.get("status") != "complete":
        raise RefusedError("receipt_state", "wrong receipt action or status")
    drifted = sorted(key for key, value in (expect or {}).items() if receipt.get(key) != value)
    if drifted:
        raise RefusedError("receipt_field", "receipt field drift: " + ", ".join(drifted))
    return receipt.get("result")


class EvidenceLedger:
    """Exclusive-create JSON records in one owned directory. Nothing is overwritten or deleted."""

    def __init__(self, directory: str | os.PathLike[str]) -> None:
        path = Path(directory)
        if path.is_symlink() or not path.is_dir():
            raise RefusedError("foreign_path", "evidence directory must be an existing non-symlink directory")
        self.directory = path.resolve()

    def path(self, name: str) -> Path:
        if not RECORD_NAME.fullmatch(name):
            raise RefusedError("record_name", "record name must be one safe path component")
        target = self.directory / name
        if target.is_symlink():
            raise RefusedError("foreign_path", "symlink record refused")
        return target

    def exists(self, name: str) -> bool:
        return self.path(name).exists()

    def read(self, name: str) -> Any:
        return json.loads(self.path(name).read_bytes())

    def retain_bytes(self, name: str, payload: bytes, *, allow_identical: bool = False) -> dict[str, Any]:
        target = self.path(name)
        if target.exists():
            if not (allow_identical and target.read_bytes() == payload):
                raise RefusedError("record_exists", f"immutable record exists: {name}")
        else:
            with target.open("xb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
        if target.read_bytes() != payload:
            raise ReadbackError("record_readback", f"record readback mismatch: {name}")
        return {"name": name, "path": str(target), "sha256": sha256_hex(payload), "bytes": len(payload)}

    def retain(self, name: str, value: Any, *, allow_identical: bool = False) -> dict[str, Any]:
        return self.retain_bytes(name, encode_json(value), allow_identical=allow_identical)

    def intent(self, name: str, request: Any, *, context: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """Write `<name>-intent.json` before the mutation it describes; an existing intent is unresolved."""
        record = name + "-intent.json"
        if self.exists(record):
            raise UnresolvedIntentError("unresolved_intent",
                                        f"unresolved intent: {record} exists; reconcile by read-back, never replay")
        payload = {**(context or {}), "request": request, "recorded_at": datetime.now(timezone.utc).isoformat()}
        return self.retain(record, payload)

    def once(self, name: str, request: Any, action: Callable[[], Any], *,
             context: Mapping[str, Any] | None = None) -> Any:
        """Run `action` at most once: reuse `<name>-result.json`, refuse a dangling intent, else intent->act->result."""
        result = name + "-result.json"
        if self.exists(result):
            return self.read(result)
        self.intent(name, request, context=context)
        value = action()
        self.retain(result, value)
        return value

    def list(self, pattern: str = "*") -> list[str]:
        """Sorted names of retained regular files matching one-component glob `pattern`; symlinks excluded."""
        if not pattern or "/" in pattern or "\\" in pattern or ".." in pattern:
            raise RefusedError("record_pattern", "record pattern must be one path component")
        return sorted(path.name for path in self.directory.glob(pattern)
                      if path.is_file() and not path.is_symlink() and RECORD_NAME.fullmatch(path.name))
