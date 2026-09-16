"""Document-key schema of the existing MITRE index."""

import hashlib
import re


def safe_key(value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:8]
    return f"{re.sub(r'[^A-Za-z0-9_\-=]', '_', value)[:100]}-{digest}"