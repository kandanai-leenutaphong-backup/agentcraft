"""Validators that teach — input checks whose rejection message is the fix.

WHY THIS EXISTS
---------------
A purpose-built tool narrows what the caller can express. That narrowing
only pays if the boundary is legible: every rejection is a turn spent, and
the rejection text is the sole feedback before the retry.

    "invalid input"                                   -> same mistake again
    "site must be a code like 'SITE_A' (letters,
     digits, underscore, hyphen), got 'North Yard
     substation'. Use the code from find_sites."      -> repaired next call

The second costs one turn. The first costs the run. So a validator here
returns a :class:`Rejection` carrying three fields — parameter, problem,
accepted — and the decorator renders them into the refusal envelope. The
``accepted`` field is mandatory by construction; a validator cannot be
written that rejects without saying what would work.

The second job is the boring one: keeping caller-supplied text out of a
query. Every value that reaches a query language is length-bounded,
character-classed and quote-escaped here, once, rather than by eight
copies of a regex that drift apart.

DOMAIN-BLIND BY CONSTRUCTION
----------------------------
Validators are factories parameterised by pattern, length and vocabulary.
Nothing here knows what a site, an asset or a case is.

DEPENDENCIES
------------
Standard library only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Sequence

# A value that clears this is safe to interpolate into a single-quoted
# string literal after escape_quotes. Deliberately narrow: forward slash and
# dot are excluded because they are path and namespace separators in several
# query languages. Use `label()` when a value legitimately contains them.
_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_\-\s]+$")

# Wider class for free-form labels: adds slash, dot, pipe and comma.
_LABEL_RE = re.compile(r"^[A-Za-z0-9_/\-\.\s\|,]+$")

_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                      r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


@dataclass(frozen=True)
class Rejection:
    """Why a value was refused, and what would be accepted instead.

    Not an exception: a refusal is an expected outcome of an interface used
    by a fallible caller, and raising would make the common case the
    exceptional path.
    """

    parameter: str
    problem: str
    accepted: str


class Validator:
    """A named check: ``(value, parameter) -> cleaned value or Rejection``.

    Wraps a plain function so the accepted-form description can be attached
    and reused in the generated parameter documentation. The caller is told
    the same rule before it calls and after it gets it wrong, which is what
    stops the two from drifting.
    """

    def __init__(self, fn: Callable[[Any, str], Any], accepted: str) -> None:
        self._fn = fn
        self.accepted = accepted

    def __call__(self, value: Any, parameter: str) -> Any:
        return self._fn(value, parameter)


def escape_quotes(value: str) -> str:
    """SQL-style ``'`` -> ``''`` escape. Idempotent on escaped input."""
    return value.replace("'", "''")


def identifier(*, max_len: int = 64, example: str = "SITE_A") -> Validator:
    """A code-shaped token: letters, digits, underscore, hyphen, space.

    Output is quote-escaped, so a call site can interpolate it directly
    into a single-quoted literal.
    """
    accepted = (
        f"a code of letters, digits, underscore, hyphen or space "
        f"(for example {example!r}), at most {max_len} characters"
    )

    def _check(value: Any, parameter: str) -> Any:
        text = str(value or "").strip()
        if not text:
            return Rejection(parameter, "value is empty", accepted)
        if len(text) > max_len:
            return Rejection(
                parameter, f"value is {len(text)} characters", accepted
            )
        if not _IDENTIFIER_RE.match(text):
            return Rejection(
                parameter,
                f"value contains unsupported characters: {text[:60]!r}",
                accepted,
            )
        return escape_quotes(text)

    return Validator(_check, accepted)


def label(*, max_len: int = 200) -> Validator:
    """A free-form label: identifier characters plus ``/ . | ,``."""
    accepted = (
        f"a label of letters, digits and the punctuation _ - / . | , "
        f"at most {max_len} characters"
    )

    def _check(value: Any, parameter: str) -> Any:
        text = str(value or "").strip()
        if not text:
            return Rejection(parameter, "value is empty", accepted)
        if len(text) > max_len:
            return Rejection(parameter, f"value is {len(text)} characters", accepted)
        if not _LABEL_RE.match(text):
            return Rejection(
                parameter,
                f"value contains unsupported characters: {text[:60]!r}",
                accepted,
            )
        return escape_quotes(text)

    return Validator(_check, accepted)


def uuid(*, example: str = "3f2504e0-4f89-41d3-9a0c-0305e82c3301") -> Validator:
    """A UUID-shaped identifier."""
    accepted = f"a UUID, for example {example!r}"

    def _check(value: Any, parameter: str) -> Any:
        text = str(value or "").strip()
        if not text:
            return Rejection(parameter, "value is empty", accepted)
        if not _UUID_RE.match(text):
            return Rejection(parameter, f"value is not a UUID: {text[:60]!r}", accepted)
        return text

    return Validator(_check, accepted)


def one_of(options: Sequence[str], *, case_sensitive: bool = False) -> Validator:
    """A closed vocabulary.

    The highest-value validator in this module. A free-text parameter that
    is really an enum is the single most common cause of a repaired-then-
    repeated call: the caller invents a plausible synonym, gets an empty
    result, and cannot tell whether the value or the data was wrong.
    Enumerating collapses that to one refusal listing every legal value.
    """
    allowed = list(options)
    accepted = "one of: " + ", ".join(repr(o) for o in allowed)
    index = {o if case_sensitive else o.lower(): o for o in allowed}

    def _check(value: Any, parameter: str) -> Any:
        text = str(value or "").strip()
        if not text:
            return Rejection(parameter, "value is empty", accepted)
        hit = index.get(text if case_sensitive else text.lower())
        if hit is None:
            return Rejection(parameter, f"unknown value {text!r}", accepted)
        return hit

    return Validator(_check, accepted)


def timestamp(*, example: str = "2026-04-15T10:00:00") -> Validator:
    """An ISO 8601 timestamp, returned normalised.

    Accepts a trailing ``Z`` because callers write it constantly and
    refusing costs a turn to teach a distinction nobody cares about.
    """
    accepted = f"an ISO 8601 timestamp, for example {example!r}"

    def _check(value: Any, parameter: str) -> Any:
        text = str(value or "").strip()
        if not text:
            return Rejection(parameter, "value is empty", accepted)
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return Rejection(
                parameter, f"value is not an ISO 8601 timestamp: {text[:60]!r}", accepted
            )
        return parsed.isoformat()

    return Validator(_check, accepted)


def integer_range(low: int, high: int) -> Validator:
    """An integer within an inclusive range."""
    accepted = f"a whole number from {low} to {high}"

    def _check(value: Any, parameter: str) -> Any:
        try:
            number = int(value)
        except (TypeError, ValueError):
            return Rejection(parameter, f"value is not a number: {value!r}", accepted)
        if not low <= number <= high:
            return Rejection(parameter, f"value {number} is out of range", accepted)
        return number

    return Validator(_check, accepted)


def bounded_list(item: Validator, *, cap: int, min_items: int = 1) -> Validator:
    """A list of validated items, with a hard cap.

    The cap is the point. An uncapped list parameter is how one tool call
    becomes a hundred backend queries, and the caller has no way to know it
    did something expensive. The refusal states the cap, so the caller
    batches instead of guessing.
    """
    accepted = f"a list of {min_items} to {cap} items, each {item.accepted}"

    def _check(value: Any, parameter: str) -> Any:
        if value is None or isinstance(value, (str, bytes)):
            return Rejection(parameter, "value is not a list", accepted)
        try:
            values = list(value)
        except TypeError:
            return Rejection(parameter, "value is not a list", accepted)
        if len(values) < min_items:
            return Rejection(parameter, f"list has {len(values)} items", accepted)
        if len(values) > cap:
            return Rejection(
                parameter, f"list has {len(values)} items, over the cap of {cap}", accepted
            )
        cleaned = []
        for position, element in enumerate(values):
            result = item(element, f"{parameter}[{position}]")
            if isinstance(result, Rejection):
                return result
            cleaned.append(result)
        return cleaned

    return Validator(_check, accepted)


def time_window(
    start_param: str = "start",
    end_param: str = "end",
    *,
    max_hours: float | None = None,
) -> Callable[[dict], Rejection | None]:
    """A cross-parameter check: end after start, span within a cap.

    Separate from the per-parameter validators because it cannot be
    expressed as one: both values are individually valid and jointly wrong.
    A reversed window is the classic silent failure — every query is
    syntactically fine and every result is empty, and nothing says why
    (GOTCHAS.md G14).
    """

    def _check(arguments: dict) -> Rejection | None:
        raw_start = arguments.get(start_param)
        raw_end = arguments.get(end_param)
        if not raw_start or not raw_end:
            return None
        try:
            start = datetime.fromisoformat(str(raw_start).replace("Z", "+00:00"))
            end = datetime.fromisoformat(str(raw_end).replace("Z", "+00:00"))
        except ValueError:
            return None  # already reported by the per-parameter validator
        if end <= start:
            return Rejection(
                end_param,
                f"{end_param} ({raw_end}) is not after {start_param} ({raw_start})",
                f"{end_param} must be later than {start_param}",
            )
        if max_hours is not None:
            hours = (end - start).total_seconds() / 3600
            if hours > max_hours:
                return Rejection(
                    end_param,
                    f"the window spans {hours:.1f} hours",
                    f"a window of at most {max_hours} hours; narrow it and call again",
                )
        return None

    return _check


__all__ = [
    "Rejection",
    "Validator",
    "bounded_list",
    "escape_quotes",
    "identifier",
    "integer_range",
    "label",
    "one_of",
    "time_window",
    "timestamp",
    "uuid",
]
