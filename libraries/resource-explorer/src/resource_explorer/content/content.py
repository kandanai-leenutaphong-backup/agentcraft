"""Content plane — one bounded read of one thing's *contents*.

WHY THIS EXISTS
---------------
The discover plane answers "what is here". It cannot answer "what does it
say". A browsable estate that stops at names is a directory listing with no
``cat``, and the operator's next question after every expansion is the one
it refuses.

This plane is the other half. It reads one addressable item — a document, a
table sample, a graph element — and returns bytes or rows, bounded, with the
same six statuses the discover plane uses. It shares that vocabulary
deliberately: a forbidden table and a forbidden index are the same operator
problem, and a second enum would make them look different.

WHAT IT DELIBERATELY DOES NOT DO
--------------------------------
It does not decide what a byte string *means*. Sniffing bytes into text,
JSON, CSV or an image is presentation, and presentation belongs to whatever
renders it. This plane reports the media type the service claimed and the
bytes it returned; nothing here parses them.

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
``normalize_sample``/``RowSample`` — a bounded row sample and what was cut
from it. ``normalize_rows`` is the same thing with the notes dropped.

WHAT A SAMPLE MAY NOT DO
------------------------
It may not silently alter a value. Bounds make a sample lossy, and a lossy
sample says so: in ``RowSample.notes``, in ``truncated``, and inside the one
cell that was shortened. ``sanitize_detail`` is an *error* formatter and is
never applied to data — running it over rows rewrites URLs the operator asked
to see and returns them as if they were original.

DEPENDENCIES
------------
Standard library, plus the discover plane's status vocabulary and failure
classifier.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from .discover import (
    DiscoveryStatus,
    classify_discovery_failure,
    collected_now,
)
from .envelope import sanitize_detail

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
DEFAULT_MAX_CELL_CHARS = 4000

#: A row bound alone does not bound a sample: a hundred rows of a thousand
#: columns is a hundred thousand cells. Wider than any table a browser pane
#: renders, and wide enough that a real one is never cut.
DEFAULT_MAX_COLUMNS = 512

#: Appended to a cell the bound shortened, so a copied value cannot be
#: mistaken for the whole one.
_CLIPPED = "… [{count} more characters not shown]"


@dataclass(frozen=True, slots=True)
class ContentBounds:
    """How much work one content read may cost.

    Clamped rather than validated, for the same reason
    :class:`~.discover.DiscoveryBounds` is: a caller that computed ``0``
    from a query string should get one row, not an exception out of a plane
    whose whole contract is that failure is a value.

    ``max_bytes`` bounds the *serialized sample*, which a row bound alone
    cannot: a reader passes it to :func:`normalize_sample`, which stops
    adding rows when the budget is spent and says so.
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
    #: Every way this payload is less than what the source holds, in the words
    #: a reader is shown. Empty means nothing was cut.
    notes: tuple[str, ...] = ()

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


@dataclass(frozen=True, slots=True)
class RowSample:
    """A bounded row sample, and every way it is less than the source.

    ``truncated`` is true when *anything* was left out — more rows existed,
    the byte budget stopped the sample early, or a column was dropped. What
    exactly was cut is in ``notes``, in the words a reader is shown, because
    "truncated" alone does not say whether to widen the bound or narrow the
    query.
    """

    rows: tuple[dict[str, Any], ...] = ()
    columns: tuple[str, ...] = ()
    truncated: bool = False
    notes: tuple[str, ...] = ()
    #: The serialized size of ``rows``, in UTF-8 bytes. What the byte budget
    #: was spent on, not the size of the source.
    size_bytes: int = 0


def normalize_sample(
    rows: Sequence[Mapping[str, Any]],
    *,
    max_rows: int,
    max_bytes: int = DEFAULT_MAX_BYTES,
    max_columns: int = DEFAULT_MAX_COLUMNS,
    max_cell_chars: int = DEFAULT_MAX_CELL_CHARS,
) -> RowSample:
    """Bound a row sample in rows, columns, cell length and serialized bytes.

    Column order is the order keys were first seen, not sorted: a document
    sample whose columns reshuffle between reads is unreadable, and the
    service's own field order is the one the operator recognises.

    Values are *not* rewritten. A URL, a JSON blob and a control character in
    a row are what the source holds, and this returns them as text. The only
    change a bound may make to a value is to shorten it, and a shortened cell
    carries the marker that says so.

    The byte budget is measured on the serialized sample, so a hundred narrow
    rows and one thousand-column row are bounded by the same number. One row
    is always returned when one exists, even if it alone exceeds the budget;
    the alternative is an empty preview of a source that does hold something.
    """
    max_rows = max(1, int(max_rows))
    max_bytes = max(1, int(max_bytes))
    max_columns = max(1, int(max_columns))
    max_cell_chars = max(1, int(max_cell_chars))

    columns: list[str] = []
    seen: set[str] = set()
    kept: list[dict[str, Any]] = []
    dropped_columns: set[str] = set()
    clipped_cells = 0
    used = 0
    over_budget = False

    more_rows = len(rows) > max_rows
    for row in list(rows)[:max_rows]:
        clean: dict[str, Any] = {}
        for key, value in (row or {}).items():
            name = str(key)
            if name not in seen:
                if len(columns) >= max_columns:
                    dropped_columns.add(name)
                    continue
                seen.add(name)
                columns.append(name)
            cell, clipped = _cell(value, max_cell_chars)
            clipped_cells += int(clipped)
            clean[name] = cell
        cost = _serialized_bytes(clean)
        if kept and used + cost > max_bytes:
            over_budget = True
            break
        used += cost
        kept.append(clean)

    notes: list[str] = []
    if more_rows:
        notes.append(f"the source holds more than the {max_rows}-row sample limit")
    if over_budget:
        notes.append(
            f"the sample stopped at {len(kept)} row(s) to stay within "
            f"{max_bytes} bytes; the rest of the page was not read into it"
        )
    if dropped_columns:
        notes.append(
            f"{len(dropped_columns)} column(s) beyond the first {max_columns} "
            "are not shown"
        )
    if clipped_cells:
        notes.append(
            f"{clipped_cells} cell(s) longer than {max_cell_chars} characters "
            "were shortened, and each says so where it was cut"
        )

    return RowSample(
        rows=tuple(kept),
        columns=tuple(columns),
        truncated=bool(notes),
        notes=tuple(notes),
        size_bytes=used,
    )


def normalize_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    max_rows: int,
    max_bytes: int = DEFAULT_MAX_BYTES,
    max_columns: int = DEFAULT_MAX_COLUMNS,
    max_cell_chars: int = DEFAULT_MAX_CELL_CHARS,
) -> tuple[tuple[dict[str, Any], ...], tuple[str, ...], bool]:
    """:func:`normalize_sample` with the notes dropped. Kept for callers that
    only need the three values."""
    sample = normalize_sample(
        rows,
        max_rows=max_rows,
        max_bytes=max_bytes,
        max_columns=max_columns,
        max_cell_chars=max_cell_chars,
    )
    return sample.rows, sample.columns, sample.truncated


def _serialized_bytes(row: Mapping[str, Any]) -> int:
    """What one normalized row costs on the wire, in UTF-8 bytes."""
    try:
        return len(json.dumps(row, ensure_ascii=False, default=str).encode("utf-8"))
    except (TypeError, ValueError):
        return len(str(row).encode("utf-8", errors="replace"))


def _cell(value: Any, max_chars: int) -> tuple[Any, bool]:
    """Coerce one cell to something JSON-renderable and bounded.

    Returns the cell and whether it was shortened. Nothing else about the
    value changes: this is data, not an error message.
    """
    if value is None or isinstance(value, (bool, int, float)):
        return value, False
    if isinstance(value, (bytes, bytearray)):
        return f"<{len(value)} bytes>", False
    if isinstance(value, (list, tuple, dict)):
        try:
            text = json.dumps(value, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            text = str(value)
    else:
        text = str(value)
    if len(text) <= max_chars:
        return text, False
    return text[:max_chars] + _CLIPPED.format(count=len(text) - max_chars), True


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
    "DEFAULT_MAX_CELL_CHARS",
    "DEFAULT_MAX_COLUMNS",
    "DEFAULT_MAX_ROWS",
    "ContentBounds",
    "ContentForm",
    "ContentPayload",
    "ContentResult",
    "RowSample",
    "bounded_content",
    "content_failure",
    "normalize_rows",
    "normalize_sample",
]
