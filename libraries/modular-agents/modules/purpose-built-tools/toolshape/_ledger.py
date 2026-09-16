"""Turn-scoped call ledger and the call-record sink.

WHY THIS EXISTS
---------------
Two jobs, both about the same event: a tool call happening.

**Suppressing repeats.** A caller that receives an empty result frequently
re-issues the identical call, because an empty table looks like a failed
attempt. The second call costs a turn, returns the same nothing, and often
triggers a third. The ledger recognises the repeat and answers from the
transcript with a result that says so explicitly.

The ledger is per-turn and lives in a :class:`contextvars.ContextVar`, so
concurrent turns cannot see each other's calls and nothing has to be
threaded through every tool signature. It is opt-in: with no ledger set —
a direct invocation, a unit test, a script — calls proceed unguarded.

**Recording what happened.** Every call appends a :class:`CallRecord` to
whichever sink is installed. Those records are the entire input to the
weight meter, which is what makes the hill-climbing half possible: without
per-call outcomes there is nothing to measure, and tool design stays a
matter of taste.

The record deliberately holds no argument *values*, only the tool name,
the outcome class and the timing. Arguments are caller data and would turn
an analysis artefact into a data-handling problem.

DEPENDENCIES
------------
Standard library only.
"""

from __future__ import annotations

import contextvars
import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterator, Protocol

_ledger: contextvars.ContextVar[dict[tuple, int] | None] = contextvars.ContextVar(
    "toolshape_ledger", default=None
)
_context: contextvars.ContextVar[dict[str, str] | None] = contextvars.ContextVar(
    "toolshape_context", default=None
)


@dataclass
class CallRecord:
    """One observed tool call.

    Args:
        tool: Tool name.
        result_class: One of the classes in ``_envelope``.
        ms: Wall-clock duration.
        run_id: Groups calls made during one attempt at one task.
        case_id: Groups runs of the same task, so repeated attempts can be
            aggregated and outcome-associated.
        split: Free-form partition label, e.g. ``train`` / ``held_out``.
            The meter reports per split without knowing what they mean.
        detail: Short reason for a refusal or error. Never argument values.
    """

    tool: str
    result_class: str
    ms: float = 0.0
    run_id: str = ""
    case_id: str = ""
    split: str = ""
    detail: str = ""
    ts: float = field(default_factory=time.time)

    def to_json(self) -> str:
        return json.dumps(asdict(self))


class RecordSink(Protocol):
    """Anything that accepts call records."""

    def record(self, entry: CallRecord) -> None: ...


class MemorySink:
    """Collects records in a list. The default in tests and short scripts."""

    def __init__(self) -> None:
        self.records: list[CallRecord] = []

    def record(self, entry: CallRecord) -> None:
        self.records.append(entry)

    def clear(self) -> None:
        self.records.clear()


class JsonlSink:
    """Appends one JSON object per line. The default in a deployed process.

    Append-only and flushed per record: a run that crashes mid-way still
    leaves the calls it made, which is usually the run worth analysing.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, entry: CallRecord) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(entry.to_json() + "\n")


class NullSink:
    """Discards records. The default when nothing is installed."""

    def record(self, entry: CallRecord) -> None:
        return None


_sink: RecordSink = NullSink()


def set_sink(sink: RecordSink) -> RecordSink:
    """Install the process-wide record sink; returns the previous one."""
    global _sink
    previous, _sink = _sink, sink
    return previous


def get_sink() -> RecordSink:
    """Return the installed record sink.

    Exported so a test can assert which sink is active without reaching into
    module state, and so a caller can restore it after temporarily swapping it.
    """
    return _sink


def emit(entry: CallRecord) -> None:
    """Send a record to the installed sink, stamped with the turn context.

    A sink failure is swallowed: measurement must never take down the
    thing being measured.
    """
    context = _context.get(None) or {}
    entry.run_id = entry.run_id or context.get("run_id", "")
    entry.case_id = entry.case_id or context.get("case_id", "")
    entry.split = entry.split or context.get("split", "")
    try:
        _sink.record(entry)
    except Exception:
        return None


def begin_turn(
    *, run_id: str = "", case_id: str = "", split: str = ""
) -> tuple[contextvars.Token, contextvars.Token]:
    """Start a turn: a fresh ledger plus the labels stamped on its records.

    Returns the tokens :func:`end_turn` needs. Prefer :func:`turn`.
    """
    return (
        _ledger.set({}),
        _context.set({"run_id": run_id, "case_id": case_id, "split": split}),
    )


def end_turn(tokens: tuple[contextvars.Token, contextvars.Token]) -> None:
    """Restore the previous ledger and context."""
    ledger_token, context_token = tokens
    _ledger.reset(ledger_token)
    _context.reset(context_token)


class turn:
    """Context manager form of :func:`begin_turn` / :func:`end_turn`.

    Usage::

        with turn(run_id="r1", case_id="c1", split="train"):
            await find_alarms(site="SITE_A", start=..., end=...)
    """

    def __init__(self, *, run_id: str = "", case_id: str = "", split: str = "") -> None:
        self._kwargs = {"run_id": run_id, "case_id": case_id, "split": split}
        self._tokens: tuple[contextvars.Token, contextvars.Token] | None = None

    def __enter__(self) -> "turn":
        self._tokens = begin_turn(**self._kwargs)
        return self

    def __exit__(self, *exc: Any) -> bool:
        if self._tokens is not None:
            end_turn(self._tokens)
            self._tokens = None
        return False


def record_call_once(tool: str, key: tuple, *, max_calls: int = 1) -> bool:
    """Count this call and report whether the per-turn limit is exceeded.

    Returns False when no ledger is set, so a tool called outside a turn
    behaves exactly as if the guard were absent.
    """
    ledger = _ledger.get(None)
    if ledger is None:
        return False
    entry = (tool, *key)
    seen = ledger.get(entry, 0)
    ledger[entry] = seen + 1
    return seen >= max_calls


def read_records(path: str | Path) -> Iterator[CallRecord]:
    """Read a JSONL record file. Malformed lines are skipped, not fatal.

    A truncated final line is the normal state of a file being appended to
    by a process that is still running, and the analysis should still run.
    """
    known = set(CallRecord.__dataclass_fields__)
    with Path(path).open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except ValueError:
                continue
            if not isinstance(payload, dict) or "tool" not in payload:
                continue
            yield CallRecord(**{k: v for k, v in payload.items() if k in known})


__all__ = [
    "CallRecord",
    "JsonlSink",
    "MemorySink",
    "NullSink",
    "RecordSink",
    "begin_turn",
    "emit",
    "end_turn",
    "get_sink",
    "read_records",
    "record_call_once",
    "set_sink",
    "turn",
]
