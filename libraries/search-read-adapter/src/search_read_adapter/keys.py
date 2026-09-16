"""Stable lookup-key encoding retained for existing indexed documents."""

import hashlib
import re

_UNSAFE_KEY = re.compile(r"[^A-Za-z0-9_\-=]")


def safe_key(value: str) -> str:
    """Return the existing deterministic document key without changing indexed identity."""
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:8]
    return f"{_UNSAFE_KEY.sub('_', value)[:100]}-{digest}"
