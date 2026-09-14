"""Content plane — one bounded read of one thing's *contents*.

WHY THIS EXISTS
---------------
The discover plane answers "what is here". It cannot answer "what does it
say". A browsable estate that stops at names is a directory listing with no
``cat``, and the operator's next question after every expansion is the one
it refuses.

This plane is the other half. It reads one addressable item — a blob, a
document, a table sample, a resource's own ARM JSON — and returns bytes or
rows, bounded, with the same six statuses the discover plane uses. It shares
that vocabulary deliberately: a forbidden blob and a forbidden container are
the same operator problem, and a second enum would make them look different.

WHAT IT DELIBERATELY DOES NOT DO
--------------------------------
It does not decide what a byte string *means*. Sniffing a blob into text,
JSON, CSV, markdown or an image is presentation, and presentation belongs to
whatever renders it. This plane reports the media type the service claimed
and the bytes it returned; nothing here parses them.

It does not stream. Every read is capped in bytes and in rows before it
starts, and a capped read says so in ``truncated`` rather than pretending it
returned everything. A plane that can return a gigabyte has no bound at all.

PUBLIC SURFACE
--------------
``ContentBounds``  — how much one read may cost.
``ContentPayload`` — bytes or rows, plus the true size behind them.
``ContentResult``  — one read's outcome. Never an exception, always a status.
``bounded_content``— the wrapper that enforces the contract.
``content_failure``— a result carrying only a status.

DEPENDENCIES
------------
Standard library, plus the discover plane's status vocabulary and failure
classifier.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from azdata.core.discover import (
    DiscoveryStatus,
    classify_discovery_failure,
    collected_now,
)
from azdata.core.envelope import sanitize_detail

#: What came back. ``bytes`` is an opaque octet stream with a claimed media
#: type; ``rows`` is a tabular or document sample; ``none`` is a read that
#: found nothing to return.
ContentForm = Literal["bytes", "rows", "none"]

#: A ceiling on one read, applied before the read starts. One megabyte is
#: the largest thing a browser pane can usefully hold at once, and a hundred
#: rows is the largest sample a human scans without paging.
DEFAULT_MAX_BYTES = 1_048_576
DEFAULT_MAX_ROWS = 100
DEFAULT_CONTENT_TIMEOUT_SECS = 20.0

#: Row values are rendered. Anything longer is a payload, not a cell, and one
#: long value multiplies across a hundred rows.
_CELL_VALUE_CAP = 4000


@dataclass(frozen=True, slots=True)
class ContentBounds:
    """How much work one content read may cost.

    Clamped rather than validated, for the same reason
    :class:`~azdata.core.discover.DiscoveryBounds` is: a caller that computed
    ``0`` from a query string should get one row, not an exception out of a
    plane whose whole contract is that failure is a value.
    """

    max_bytes: int = DEFAULT_MAX_BYTES
    max_rows: int = DEFAULT_MAX_ROWS
    timeout_secs: float = DEFAULT_CONTENT_TIMEOUT_SECS

    def __post_init__(self) -> None:
        object.__setattr__(self, "max_bytes", max(1, int(self.max_bytes)))
        object.__setattr__(self, "max_rows", max(1, int(self.max_rows)))
        timeout = float(self.timeout_secs)
        object.__setattr__(self, "timeout_secs", timeout if timeout > 0 else 0.001)


@dataclass(frozen=True, slots=True)
class ContentPayload:
    """What one read returned.

    ``size_bytes`` is the size of the *underlying* object, not of ``data``.
    They differ exactly when the read was capped, which is the one case a
    reader most needs to be told about.
    """

    form: ContentForm = "none"
    media_type: str = ""
    data: bytes = b""
    rows: tuple[Mapping[str, Any], ...] = ()
    columns: tuple[str, ...] = ()
    size_bytes: int = 0

    @property
    def is_empty(self) -> bool:
        return self.form == "none" or (not self.data and not self.rows)


@dataclass(frozen=True, slots=True)
class ContentResult:
    """One content read's outcome. Never an exception, always a status."""

    service: str
    kind: str
    status: DiscoveryStatus
    payload: ContentPayload = field(default_factory=ContentPayload)
    truncated: bool = False
    detail: str = ""
    collected_at: str = ""


def content_failure(
    *,
    service: str,
    kind: str,
    status: DiscoveryStatus,
    detail: str,
) -> ContentResult:
    """A result carrying only a status. The shape of every unreadable item."""
    return ContentResult(
        service=service,
        kind=kind,
        status=status,
        payload=ContentPayload(),
        truncated=False,
        detail=sanitize_detail(detail),
        collected_at=collected_now(),
    )


def normalize_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    max_rows: int,
) -> tuple[tuple[dict[str, Any], ...], tuple[str, ...], bool]:
    """Cap a row sample and derive its column order from first appearance.

    Column order is the order keys were first seen, not sorted: a document
    sample whose columns reshuffle between reads is unreadable, and the
    service's own field order is the one the operator recognises.
    """
    columns: list[str] = []
    seen: set[str] = set()
    capped: list[dict[str, Any]] = []
    truncated = len(rows) > max_rows
    for row in list(rows)[:max_rows]:
        clean: dict[str, Any] = {}
        for key, value in (row or {}).items():
            name = str(key)
            if name not in seen:
                seen.add(name)
                columns.append(name)
            clean[name] = _cell(value)
        capped.append(clean)
    return tuple(capped), tuple(columns), truncated


def _cell(value: Any) -> Any:
    """Coerce one cell to something JSON-renderable and bounded."""
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        return value
    if isinstance(value, (bytes, bytearray)):
        return f"<{len(value)} bytes>"
    if isinstance(value, (list, tuple, dict)):
        text = sanitize_detail(str(value))
        return text[:_CELL_VALUE_CAP]
    return sanitize_detail(str(value))[:_CELL_VALUE_CAP]


async def bounded_content(
    *,
    service: str,
    kind: str,
    bounds: ContentBounds,
    fetch: Callable[[], tuple[ContentPayload, bool]],
) -> ContentResult:
    """Run one blocking content read under the plane's contract.

    ``fetch`` is synchronous and may block: every SDK and REST client used
    here is, and reading a megabyte on the event loop stalls every other
    request. It returns ``(payload, truncated)``; the truncation flag is the
    reader's, because only the reader knows whether it stopped early.

    The thread returns its exception as a value rather than raising, so a
    ``TimeoutError`` reaching ``wait_for`` unambiguously means the budget was
    exceeded and not that a socket timed out inside the SDK.
    """

    def _run() -> tuple[tuple[ContentPayload, bool] | None, BaseException | None]:
        try:
            return fetch(), None
        except Exception as exc:  # noqa: BLE001 - boundary: failure is a status
            return None, exc

    try:
        answer, error = await asyncio.wait_for(
            asyncio.to_thread(_run), bounds.timeout_secs
        )
    except (asyncio.TimeoutError, TimeoutError):
        return content_failure(
            service=service,
            kind=kind,
            status="unreachable",
            detail=f"content read exceeded {bounds.timeout_secs}s",
        )
    except Exception as exc:  # noqa: BLE001 - to_thread itself can fail
        status, detail = classify_discovery_failure(exc)
        return content_failure(service=service, kind=kind, status=status, detail=detail)

    if error is not None:
        status, detail = classify_discovery_failure(error)
        return content_failure(service=service, kind=kind, status=status, detail=detail)

    payload, truncated = answer or (ContentPayload(), False)
    return ContentResult(
        service=service,
        kind=kind,
        status="empty" if payload.is_empty else "ok",
        payload=payload,
        truncated=truncated,
        detail="",
        collected_at=collected_now(),
    )


__all__ = [
    "DEFAULT_CONTENT_TIMEOUT_SECS",
    "DEFAULT_MAX_BYTES",
    "DEFAULT_MAX_ROWS",
    "ContentBounds",
    "ContentForm",
    "ContentPayload",
    "ContentResult",
    "bounded_content",
    "content_failure",
    "normalize_rows",
]
