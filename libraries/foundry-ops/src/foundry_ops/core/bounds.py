"""Bounded polling and bounded enumeration for eventually consistent read-back."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
import time
from typing import Any, Generic, TypeVar

from .errors import BoundExceededError, VerificationError
from .records import to_plain

T = TypeVar("T")


@dataclass(frozen=True)
class PollResult(Generic[T]):
    value: T
    settled: bool
    attempts: int
    seconds: float


def poll_until(read: Callable[[], T], done: Callable[[T], bool], *, interval: float, attempts: int | None = None,
               seconds: float | None = None, abort: Callable[[T], str | None] | None = None,
               sleep: Callable[[float], None] = time.sleep,
               clock: Callable[[], float] = time.monotonic) -> PollResult[T]:
    """Read until `done`, at most `attempts` reads and/or `seconds` elapsed. Unsettled is returned, not raised.

    At least one bound is required. `abort(value)` returning a reason raises `VerificationError` immediately.
    """
    if attempts is None and seconds is None:
        raise ValueError("poll requires an attempt or time bound")
    if (attempts is not None and attempts < 1) or interval < 0 or (seconds is not None and seconds <= 0):
        raise ValueError("poll bounds must be positive")
    started = clock()
    deadline = None if seconds is None else started + seconds
    attempt = 0
    while True:
        attempt += 1
        value = read()
        reason = abort(value) if abort else None
        if reason:
            raise VerificationError("poll_aborted", reason)
        if done(value):
            return PollResult(value, True, attempt, clock() - started)
        remaining = None if deadline is None else deadline - clock()
        if (attempts is not None and attempt >= attempts) or (remaining is not None and remaining <= 0):
            return PollResult(value, False, attempt, clock() - started)
        sleep(interval if remaining is None else min(interval, remaining))


def collect_bounded(items: Iterable[Any], *, max_items: int, seconds: float,
                    convert: Callable[[Any], Any] = to_plain,
                    clock: Callable[[], float] = time.monotonic) -> list[Any]:
    """Materialize an SDK pager; refuse rather than truncate when the item or time bound is reached."""
    deadline = clock() + seconds
    values: list[Any] = []
    for item in items:
        if len(values) >= max_items or clock() >= deadline:
            raise BoundExceededError("enumeration_bound", "enumeration bound exceeded")
        values.append(convert(item))
    return values
