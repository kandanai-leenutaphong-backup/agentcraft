"""Bounded server-sent-event log parsing for hosted-agent session log streams."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
import codecs
import json
import time
from typing import Any

from .errors import BoundExceededError
from .records import redact_text

DEFAULT_KEYWORDS = ("Error", "Exception", "Traceback", "denied", "failed")


def log_messages(chunks: Iterable[bytes], max_bytes: int = 262144, max_events: int = 100) -> Iterator[str]:
    """Yield `message` strings from SSE `data:` events; strict UTF-8 across chunk splits; refuse past bounds."""
    decoder = codecs.getincrementaldecoder("utf-8")("strict")
    pending, data, total, events = "", [], 0, 0
    for chunk in chunks:
        total += len(chunk)
        if total > max_bytes:
            raise BoundExceededError("log_bytes", "log byte bound exceeded")
        pending += decoder.decode(chunk)
        while "\n" in pending:
            line, pending = pending.split("\n", 1)
            line = line.removesuffix("\r")
            if line.startswith("data:"):
                data.append(line[5:].lstrip(" "))
            elif not line and data:
                events += 1
                if events > max_events:
                    raise BoundExceededError("log_events", "log event bound exceeded")
                try:
                    value = json.loads("\n".join(data))
                except ValueError:
                    value = None
                data = []
                if isinstance(value, dict) and isinstance(value.get("message"), str):
                    yield value["message"]
    decoder.decode(b"", final=True)


def redact(message: str, *, limit: int = 2000) -> str:
    return redact_text(message)[:limit]


def exception_lines(chunks: Iterable[bytes], *, keywords: tuple[str, ...] = DEFAULT_KEYWORDS,
                    max_lines: int = 100, seconds: float = 20.0, max_bytes: int = 1048576,
                    max_events: int = 1000, clock: Callable[[], float] = time.monotonic) -> dict[str, Any]:
    """Keyword-filtered, redacted excerpt. Stream end, bound or transport error all end the excerpt, recorded."""
    lines: list[str] = []
    termination, reason = "end", None
    deadline = clock() + seconds
    try:
        for message in log_messages(chunks, max_bytes=max_bytes, max_events=max_events):
            if any(word in message for word in keywords):
                lines.append(redact(message))
            if len(lines) >= max_lines or clock() >= deadline:
                termination = "bound"
                break
    except Exception as error:  # a live stream normally ends by read timeout
        termination = type(error).__name__
        reason = redact(str(error), limit=500) if isinstance(error, ValueError) else None
    return {"lines": lines, "termination": termination, "reason": reason,
            "coverage": "bounded keyword-filtered excerpt; not the full log"}
