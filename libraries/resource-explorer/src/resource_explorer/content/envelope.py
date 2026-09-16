"""Result envelope — the one shape every connector returns on failure.

WHY THIS EXISTS
---------------
Twenty call sites open-coding ``json.dumps({"error": True, ...})`` drift
within a month: some cap the detail, some paste the raw SDK exception, some
prepend the exception class. The caller then parses error strings with
regexes, and a leaked endpoint URL in an exception message publishes your
deployment topology to whatever consumes the output — an LLM context, a log
aggregator, a browser.

One chokepoint: cap the detail, strip URLs, serialise.

Two failure shapes, deliberately distinct:

* ``error``    — the call failed; the caller learned nothing.
* ``degraded`` — an answer exists at reduced fidelity (circuit breaker open,
  a paid ranker unavailable). A caller can proceed and should not treat the
  run as failed.

Collapsing them loses the only distinction a retry policy cares about.

One success shape, for the write and provisioning planes only:

* ``ok`` — a mutation completed. Read paths keep their own service-shaped
  payloads, because a caller projecting search hits should not have to
  unwrap an operation envelope first. A mutation has no natural payload,
  so it gets one.

DEPENDENCIES
------------
Standard library only.
"""

from __future__ import annotations

import json
import re
from typing import Any, Final

# Operator-visible cap. Long SDK exceptions carry stack context that helps
# nobody downstream and costs an LLM caller real context window.
_DETAIL_CAP: Final[int] = 500

# Azure SDK exceptions routinely embed the full service endpoint. Only
# URL-shaped tokens are removed; bare identifiers survive because a caller
# legitimately needs to reason about them.
_URL_PATTERN: Final[re.Pattern[str]] = re.compile(r"https?://\S+")


def sanitize_detail(detail: str) -> str:
    """Cap and URL-strip a caller-visible detail string."""
    if not isinstance(detail, str):
        # Callers hand us exceptions by accident; coerce so json.dumps
        # cannot raise from inside an error path.
        detail = str(detail)
    detail = _URL_PATTERN.sub("<redacted-url>", detail)
    return detail[:_DETAIL_CAP]


def error_envelope(detail: str, *, exc: BaseException | None = None) -> str:
    """``{"error": true, "detail": "..."}`` as a JSON string.

    Args:
        detail: What failed, in operator language.
        exc: Optional exception appended as ``"<detail>: <Type>: <msg>"``.
    """
    if exc is not None:
        detail = f"{detail}: {type(exc).__name__}: {exc}" if detail else (
            f"{type(exc).__name__}: {exc}"
        )
    return json.dumps({"error": True, "detail": sanitize_detail(detail)})


def degraded_envelope(detail: str) -> str:
    """``{"degraded": true, "detail": "..."}`` as a JSON string."""
    return json.dumps({"degraded": True, "detail": sanitize_detail(detail)})


def success_envelope(operation: str, **fields: Any) -> str:
    """``{"ok": true, "operation": "...", ...}`` as a JSON string.

    Args:
        operation: The mutation performed, e.g. ``"upload"`` or ``"ensure"``.
        fields: Operation-specific keys, merged after ``operation`` so key
            order stays stable for anything diffing the output.

    Serialisation falls back to ``str`` so an unexpected SDK type in a
    result cannot raise from inside the success path.
    """
    return json.dumps({"ok": True, "operation": operation, **fields}, default=str)


def is_error(payload: str) -> bool:
    """True when ``payload`` is an error envelope. Never raises on garbage."""
    return _flag_is_true(payload, "error")


def is_ok(payload: str) -> bool:
    """True when ``payload`` is a success envelope. Never raises on garbage."""
    return _flag_is_true(payload, "ok")


def _flag_is_true(payload: str, key: str) -> bool:
    try:
        parsed = json.loads(payload)
    except (TypeError, ValueError):
        return False
    return isinstance(parsed, dict) and parsed.get(key) is True


__all__ = [
    "degraded_envelope",
    "error_envelope",
    "is_error",
    "is_ok",
    "sanitize_detail",
    "success_envelope",
]
