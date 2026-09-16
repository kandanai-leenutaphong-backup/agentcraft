"""Tool result contract — the shapes a purpose-built tool is allowed to return.

WHY THIS EXISTS
---------------
A tool result is read by a language model, so its shape is an interface
under exactly the same obligations as a UI. Four requirements, none of
which an ad-hoc ``json.dumps`` satisfies:

**One tabular shape.** ``{columns, rows, scope}`` for every tool that
returns records. A caller that has learned to read one tool has learned to
read all of them, and a renderer written once works for all of them.

**A refusal that teaches.** When input is rejected, the result names the
parameter, what was wrong, and what would be accepted. That text is the
only feedback the caller gets before its retry, so it is training signal.
A generic "invalid request" guarantees the same mistake twice.

**Scope, always.** ``scope`` echoes what the tool actually did — which
site, which window, how many records. Without it the caller cannot tell
"no matching records" from "wrong parameters", and it re-calls the tool to
find out. Half of all duplicate calls are a missing scope block.

**Emptiness that is legible.** ``rows: []`` with a populated scope means
the question was answered and the answer is nothing. That is a different
event from an error, and the weight meter counts them separately.

DOMAIN-BLIND BY CONSTRUCTION
----------------------------
Column names and scope keys are supplied by the caller. Nothing here
knows what a row means.

DEPENDENCIES
------------
Standard library only.
"""

from __future__ import annotations

import json
import re
from typing import Any, Final, Sequence

# Cap on caller-visible detail text. Long SDK exceptions carry stack context
# that helps nobody downstream and costs a model real context window.
_DETAIL_CAP: Final[int] = 500

# Backend exceptions routinely embed service endpoints. Stripping URL-shaped
# tokens keeps deployment topology out of a transcript, a log aggregator, or
# whatever the model says next.
_URL_PATTERN: Final[re.Pattern[str]] = re.compile(r"https?://\S+")

# Result classes. These are the vocabulary of the weight meter as well as the
# envelope, deliberately: how a result is classified and how it is built must
# be the same definition, or the meter measures a shape that does not exist.
PRODUCTIVE: Final[str] = "productive"
ERROR: Final[str] = "error"
EMPTY: Final[str] = "empty"
REFUSED: Final[str] = "refused"
DUPLICATE: Final[str] = "duplicate"
MISSING: Final[str] = "missing"

RESULT_CLASSES: Final[tuple[str, ...]] = (
    PRODUCTIVE, ERROR, EMPTY, REFUSED, DUPLICATE, MISSING,
)

# Classes that mean the call returned no usable information. Deliberately
# excludes REFUSED and DUPLICATE: both cost a turn, but both hand the caller
# a specific, actionable next step, and lumping them in here flags a tool for
# culling because its guardrails are working (GOTCHAS.md G13).
UNPRODUCTIVE_CLASSES: Final[tuple[str, ...]] = (ERROR, EMPTY, MISSING)

# Everything that consumed a turn without producing data. The wider measure,
# reported alongside but never used to decide a cull.
TURN_COST_CLASSES: Final[tuple[str, ...]] = UNPRODUCTIVE_CLASSES + (REFUSED, DUPLICATE)


def sanitize_detail(detail: Any) -> str:
    """Cap and URL-strip a caller-visible message."""
    text = detail if isinstance(detail, str) else str(detail)
    return _URL_PATTERN.sub("<redacted-url>", text)[:_DETAIL_CAP]


def table(
    columns: Sequence[str],
    rows: Sequence[dict],
    *,
    scope: dict | None = None,
    note: str = "",
) -> str:
    """The success shape: ``{columns, rows, scope}`` as a JSON string.

    Args:
        columns: Column order. Explicit rather than derived from the first
            row, so an empty result still tells the caller what it would
            have received — which is what stops the speculative re-call.
        rows: One dict per record, keyed by column name.
        scope: What the tool actually did. Always populated in practice;
            ``row_count`` is added automatically.
        note: Optional one-line hint, e.g. that a cap truncated the result.
    """
    payload: dict[str, Any] = {
        "columns": list(columns),
        "rows": list(rows),
        "scope": {**(scope or {}), "row_count": len(rows)},
    }
    if note:
        payload["note"] = note
    return json.dumps(payload, default=str)


def refusal(parameter: str, problem: str, accepted: str) -> str:
    """The teaching shape: what was wrong and what would work.

    Three fields rather than one message because the caller is a language
    model and the reliable repair is a template, not prose. ``accepted``
    is mandatory: a refusal that does not say what would be accepted is a
    dead end that costs a turn (GOTCHAS.md G11).
    """
    return json.dumps(
        {
            "refused": True,
            "parameter": parameter,
            "problem": sanitize_detail(problem),
            "accepted": sanitize_detail(accepted),
        }
    )


def failure(detail: str, *, exc: BaseException | None = None) -> str:
    """The failure shape. The tool could not answer; the caller learned nothing."""
    if exc is not None:
        detail = f"{detail}: {type(exc).__name__}: {exc}" if detail else (
            f"{type(exc).__name__}: {exc}"
        )
    return json.dumps({"error": True, "detail": sanitize_detail(detail)})


def duplicate(tool_name: str, scope: dict | None = None) -> str:
    """The repeat shape: this exact call already ran this turn.

    Returned as a normal result rather than an error because it is not a
    failure — the answer exists, above, in the transcript. The message says
    so explicitly, since a caller that reads "error" will simply try again.
    """
    return json.dumps(
        {
            "duplicate": True,
            "tool": tool_name,
            "scope": scope or {},
            "detail": (
                f"{tool_name} already ran with these arguments in this turn. "
                "Reuse the earlier result; do not repeat the call. If the "
                "earlier result was empty, that is the answer."
            ),
        }
    )


def classify(payload: Any) -> str:
    """Classify one tool result. Accepts a JSON string or a decoded object.

    The single definition of what "unproductive" means, shared by the
    envelope and the weight meter.

    * ``Ellipsis`` — a truncated payload. **Productive**: truncation only
      happens to results too large to transmit, which are by definition
      non-empty (GOTCHAS.md G8).
    * ``None`` — no result was delivered at all: ``missing``, which is
      distinct from an empty answer (GOTCHAS.md G7).
    """
    if payload is Ellipsis:
        return PRODUCTIVE
    if payload is None:
        return MISSING

    value = payload
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            # Non-JSON text is still information the caller can use.
            return PRODUCTIVE if value.strip() else EMPTY

    if isinstance(value, dict):
        if value.get("error"):
            return ERROR
        if value.get("refused"):
            return REFUSED
        if value.get("duplicate"):
            return DUPLICATE
        rows = value.get("rows")
        if isinstance(rows, list) and not rows:
            return EMPTY
        summary = value.get("summary")
        if isinstance(summary, dict) and summary.get("total_rows") == 0:
            return EMPTY
        return PRODUCTIVE
    if isinstance(value, list):
        return EMPTY if not value else PRODUCTIVE
    return PRODUCTIVE


def is_unproductive(result_class: str) -> bool:
    """True when the call consumed a turn without delivering information."""
    return result_class in UNPRODUCTIVE_CLASSES


__all__ = [
    "DUPLICATE",
    "EMPTY",
    "ERROR",
    "MISSING",
    "PRODUCTIVE",
    "REFUSED",
    "RESULT_CLASSES",
    "TURN_COST_CLASSES",
    "UNPRODUCTIVE_CLASSES",
    "classify",
    "duplicate",
    "failure",
    "is_unproductive",
    "refusal",
    "sanitize_detail",
    "table",
]
