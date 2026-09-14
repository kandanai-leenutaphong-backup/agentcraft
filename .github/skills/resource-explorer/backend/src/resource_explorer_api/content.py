"""Typing contents — deciding what a byte string should be rendered as.

WHY HERE AND NOT IN ``azdata``
------------------------------
``azdata`` reports the media type the service claimed and the bytes it
returned; it never decides what they *mean*. Sniffing is presentation, and
presentation belongs to whatever renders it. Pushing this down into the
library would make the next consumer inherit this component's idea of what a
``.csv`` looks like.

WHY THE CLAIM IS NOT TRUSTED ALONE
----------------------------------
Blob storage defaults an unset content type to
``application/octet-stream``, and a great many real blobs are uploaded that
way. A browser that showed a JSON config as "binary" because nobody set a
header would be technically correct and useless. So the claim is checked
first, the name second, and the bytes last — and any of the three can settle
it.

WHY BINARY STILL RETURNS SOMETHING
----------------------------------
An operator who opens a ``.png`` wants to see it; an operator who opens a
``.dll`` wants to know it is a ``.dll`` and roughly what is at the front of
it. A hex-and-ASCII preview answers the second question without pretending
the bytes are text, and the raw bytes travel alongside it so a client can
still offer a download.

The magic-number table is short on purpose. It covers what a browser can
render and what is common enough in a storage account to be worth naming;
everything else is honestly ``binary``.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass

from resource_explorer_api.settings import MAX_HEX_PREVIEW_BYTES, MAX_TEXT_CHARS

#: Media types a browser renders as an image. SVG is deliberately absent: it
#: is a script-bearing document, and rendering one from a storage account
#: inside the explorer's own origin would be a stored-XSS surface.
IMAGE_TYPES: tuple[str, ...] = (
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
    "image/bmp",
    "image/avif",
    "image/x-icon",
)

#: Leading bytes that settle the question when no header does.
MAGIC: tuple[tuple[bytes, str, str], ...] = (
    (b"\x89PNG\r\n\x1a\n", "image", "image/png"),
    (b"\xff\xd8\xff", "image", "image/jpeg"),
    (b"GIF87a", "image", "image/gif"),
    (b"GIF89a", "image", "image/gif"),
    (b"%PDF-", "binary", "application/pdf"),
    (b"PK\x03\x04", "binary", "application/zip"),
    (b"\x1f\x8b", "binary", "application/gzip"),
    (b"\x7fELF", "binary", "application/x-executable"),
)

#: Suffix -> (content kind, media type) when the service claimed nothing
#: useful. Lowercased; the longest match wins, which is why ``.tar.gz`` is
#: absent and ``.gz`` is caught by its magic number instead.
SUFFIX_TYPES: dict[str, tuple[str, str]] = {
    ".json": ("json", "application/json"),
    ".jsonl": ("text", "application/x-ndjson"),
    ".ndjson": ("text", "application/x-ndjson"),
    ".md": ("markdown", "text/markdown"),
    ".markdown": ("markdown", "text/markdown"),
    ".csv": ("csv", "text/csv"),
    ".tsv": ("csv", "text/tab-separated-values"),
    ".txt": ("text", "text/plain"),
    ".log": ("text", "text/plain"),
    ".yaml": ("text", "text/yaml"),
    ".yml": ("text", "text/yaml"),
    ".xml": ("text", "application/xml"),
    ".html": ("text", "text/plain"),
    ".css": ("text", "text/plain"),
    ".js": ("text", "text/plain"),
    ".ts": ("text", "text/plain"),
    ".py": ("text", "text/plain"),
    ".sh": ("text", "text/plain"),
    ".toml": ("text", "text/plain"),
    ".ini": ("text", "text/plain"),
    ".cfg": ("text", "text/plain"),
    ".sql": ("text", "text/plain"),
    ".png": ("image", "image/png"),
    ".jpg": ("image", "image/jpeg"),
    ".jpeg": ("image", "image/jpeg"),
    ".gif": ("image", "image/gif"),
    ".webp": ("image", "image/webp"),
    ".bmp": ("image", "image/bmp"),
    ".ico": ("image", "image/x-icon"),
}

#: A media type that tells the reader nothing. Present on most blobs whose
#: uploader never set one.
UNINFORMATIVE: frozenset[str] = frozenset(
    {"", "application/octet-stream", "binary/octet-stream"}
)

#: Control characters that never appear in text a human wrote. Tab, newline
#: and carriage return are excluded because they do.
_CONTROL = bytes(range(0, 9)) + bytes(range(11, 13)) + bytes(range(14, 32))


@dataclass(frozen=True, slots=True)
class TypedContent:
    """One byte string, classified and rendered.

    Exactly one of ``text`` and ``data_base64`` is populated for a readable
    object; ``binary`` populates both, because a preview and a download are
    different needs.
    """

    content_kind: str
    media_type: str
    text: str | None = None
    data_base64: str | None = None


def type_content(data: bytes, *, media_type: str, name: str = "") -> TypedContent:
    """Classify bytes by claimed type, then by name, then by the bytes."""
    claimed = _normalize(media_type)
    kind, resolved = _from_claim(claimed)
    if kind is None:
        kind, resolved = _from_name(name)
    if kind is None:
        kind, resolved = _from_bytes(data)
    if kind is None:
        kind, resolved = ("text", claimed or "text/plain") if _is_text(data) else ("binary", claimed or "application/octet-stream")

    if kind == "image":
        return TypedContent(
            content_kind="image",
            media_type=resolved,
            data_base64=base64.b64encode(data).decode("ascii"),
        )
    if kind == "binary":
        return TypedContent(
            content_kind="binary",
            media_type=resolved,
            text=hex_preview(data),
            data_base64=base64.b64encode(data).decode("ascii"),
        )

    decoded = _decode(data)
    if decoded is None:
        # Claimed or named as text, and it is not. The bytes win: a mojibake
        # pane is worse than an honest hex dump.
        return TypedContent(
            content_kind="binary",
            media_type=resolved,
            text=hex_preview(data),
            data_base64=base64.b64encode(data).decode("ascii"),
        )
    if kind == "json":
        pretty = _pretty_json(decoded)
        if pretty is None:
            # A truncated JSON blob is real text that no longer parses.
            return TypedContent(content_kind="text", media_type=resolved, text=_cap(decoded))
        return TypedContent(content_kind="json", media_type=resolved, text=_cap(pretty))
    return TypedContent(content_kind=kind, media_type=resolved, text=_cap(decoded))


def hex_preview(data: bytes, *, limit: int = MAX_HEX_PREVIEW_BYTES) -> str:
    """A ``xxd``-shaped preview: offset, hex, and the printable ASCII."""
    lines: list[str] = []
    window = data[:limit]
    for offset in range(0, len(window), 16):
        chunk = window[offset : offset + 16]
        hexed = " ".join(f"{byte:02x}" for byte in chunk)
        ascii_ = "".join(chr(byte) if 32 <= byte < 127 else "." for byte in chunk)
        lines.append(f"{offset:08x}  {hexed:<47}  {ascii_}")
    if len(data) > limit:
        lines.append(f"... {len(data) - limit} more bytes")
    return "\n".join(lines)


def _normalize(media_type: str) -> str:
    return str(media_type or "").split(";", 1)[0].strip().lower()


def _from_claim(claimed: str) -> tuple[str | None, str]:
    if claimed in UNINFORMATIVE:
        return None, claimed
    if claimed in IMAGE_TYPES:
        return "image", claimed
    if claimed.startswith("image/"):
        # An image type a browser may not render is still not text.
        return "binary", claimed
    if claimed in ("application/json", "text/json", "application/problem+json"):
        return "json", claimed
    if claimed in ("text/markdown", "text/x-markdown"):
        return "markdown", claimed
    if claimed in ("text/csv", "text/tab-separated-values"):
        return "csv", claimed
    if claimed.startswith("text/") or claimed.endswith("+json") or claimed.endswith("+xml"):
        return "text", claimed
    return None, claimed


def _from_name(name: str) -> tuple[str | None, str]:
    lowered = str(name or "").lower()
    for suffix, (kind, media_type) in SUFFIX_TYPES.items():
        if lowered.endswith(suffix):
            return kind, media_type
    return None, ""


def _from_bytes(data: bytes) -> tuple[str | None, str]:
    for prefix, kind, media_type in MAGIC:
        if data.startswith(prefix):
            return kind, media_type
    head = data.lstrip()[:1]
    if head in (b"{", b"[") and _pretty_json(_decode(data) or "") is not None:
        return "json", "application/json"
    return None, ""


def _decode(data: bytes) -> str | None:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _is_text(data: bytes) -> bool:
    if not data:
        return True
    if any(byte in _CONTROL for byte in data[:4096]):
        return False
    return _decode(data) is not None


def _pretty_json(text: str) -> str | None:
    try:
        return json.dumps(json.loads(text), indent=2, ensure_ascii=False)
    except (json.JSONDecodeError, ValueError, RecursionError):
        return None


def _cap(text: str) -> str:
    if len(text) <= MAX_TEXT_CHARS:
        return text
    return text[: MAX_TEXT_CHARS - 1] + "…"


__all__ = [
    "IMAGE_TYPES",
    "MAGIC",
    "SUFFIX_TYPES",
    "UNINFORMATIVE",
    "TypedContent",
    "hex_preview",
    "type_content",
]
