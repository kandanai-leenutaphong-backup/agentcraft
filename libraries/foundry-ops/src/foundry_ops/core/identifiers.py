"""Identifier and version-label guards shared by hosting, evaluation and optimization."""

from __future__ import annotations

import re
from typing import Any

from .errors import RefusedError

IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")


def safe_identifier(value: Any, what: str = "identifier") -> str:
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        raise RefusedError("identifier", f"unsafe {what}")
    return value


def validate_version_label(value: Any, limit: int = 50, *, what: str = "version", code: str = "version_label") -> str:
    """Non-empty string of at most `limit` characters; Foundry registrations reject longer labels late."""
    if not isinstance(value, str) or not value or len(value) > limit:
        raise RefusedError(code, f"{what} must be 1-{limit} characters")
    return value
