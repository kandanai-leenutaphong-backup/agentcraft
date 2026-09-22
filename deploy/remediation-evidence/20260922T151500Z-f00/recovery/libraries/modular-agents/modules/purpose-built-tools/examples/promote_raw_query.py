"""The whole argument in one runnable file: raw query versus purpose-built.

Two tools over the *same* backend and the *same* ten intents.

    run_query(query)                    the caller authors the query
    find_events(site, start, end, kind) the caller states the intent

Then the weight meter over both, so the difference is a number rather than
an opinion.

Run it::

    python3 examples/promote_raw_query.py

This is also the round-trip test between the box's two halves: the tools
are built with the shaping half and scored by the measuring half, and the
selftest asserts the outcome does not change.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# The wrapper logs every caught tool exception, which is right for a library
# and noise for a demo whose whole point is that failures are caught.
logging.getLogger("toolshape").setLevel(logging.CRITICAL)

from toolshape import (
    MemorySink,
    Outcome,
    Param,
    ToolSpec,
    aggregate,
    identifier,
    one_of,
    render_markdown,
    set_sink,
    time_window,
    timestamp,
    turn,
    purpose_built,
)

# ── A backend with a small, strict query language ────────────────────────────

_ROWS = [
    {"site": "SITE_A", "at": "2026-04-15T10:01:00", "kind": "trip", "detail": "breaker"},
    {"site": "SITE_A", "at": "2026-04-15T10:04:00", "kind": "alarm", "detail": "voltage"},
    {"site": "SITE_B", "at": "2026-04-15T10:02:00", "kind": "alarm", "detail": "current"},
]

_KINDS = ("trip", "alarm", "notice")


class Backend:
    """Toy store. Accepts `SELECT site FROM events WHERE ...` and nothing else.

    It raises on anything malformed, exactly like the real thing: a query
    language is unforgiving, and every rejection is a wasted turn.
    """

    def __init__(self) -> None:
        self.queries: list[str] = []

    def query(self, text: str) -> list[dict]:
        self.queries.append(text)
        cleaned = " ".join(text.split())
        if not cleaned.upper().startswith("SELECT * FROM EVENTS WHERE SITE = "):
            raise SyntaxError(
                "expected: SELECT * FROM events WHERE site = '<code>' "
                "[AND kind = '<kind>']"
            )
        rest = cleaned[len("SELECT * FROM events WHERE site = "):]
        parts = [p.strip() for p in rest.split(" AND ")]
        site = parts[0].strip("'\"")
        kind = None
        for clause in parts[1:]:
            if clause.lower().startswith("kind ="):
                kind = clause.split("=", 1)[1].strip().strip("'\"")
            else:
                raise SyntaxError(f"unknown clause: {clause}")
        return [
            row
            for row in _ROWS
            if row["site"] == site and (kind is None or row["kind"] == kind)
        ]


BACKEND = Backend()


# ── Tool 1: the raw surface. The caller authors the query. ───────────────────

RUN_QUERY = ToolSpec(
    name="run_query",
    purpose="Run a query against the event store and return matching rows.",
    call_when="When you need event records and can write the query yourself.",
    params=[
        Param(
            "query",
            "The query to run, as returned by no other tool — you write it.",
            required=True,
        )
    ],
    returns="A table: {columns, rows, scope}.",
    dedupe_on=("query",),
)


@purpose_built(RUN_QUERY)
def run_query(query: str) -> list[dict]:
    """Deliberately unvalidatable: any string is a syntactically possible query.

    This is the shape being argued against. The wrapper still records and
    still envelopes the failure — that is what makes the comparison fair.
    """
    return BACKEND.query(query)


# ── Tool 2: the purpose-built surface. The caller states the intent. ─────────

FIND_EVENTS = ToolSpec(
    name="find_events",
    purpose="Return events at one site inside a time window, newest last.",
    call_when=(
        "Whenever you need event records for a site. Call this instead of "
        "writing a query. Use the site code returned by the site listing."
    ),
    params=[
        Param(
            "site",
            "Site code, as returned by the site listing.",
            validator=identifier(max_len=16, example="SITE_A"),
        ),
        Param("start", "Window start, from the incident time.", validator=timestamp()),
        Param("end", "Window end, from the incident time.", validator=timestamp()),
        Param(
            "kind",
            "Restrict to one event kind, one of the values listed.",
            validator=one_of(_KINDS),
            required=False,
        ),
    ],
    returns="A table with columns site, at, kind, detail.",
    dedupe_on=("site", "start", "end", "kind"),
    cross_checks=(time_window(max_hours=48),),
    replaces="run_query",
)


@purpose_built(FIND_EVENTS)
def find_events(site: str, start: str, end: str, kind: str | None = None):
    """The query is now code. There is no syntax for the caller to get wrong."""
    clause = f" AND kind = '{kind}'" if kind else ""
    rows = BACKEND.query(f"SELECT * FROM events WHERE site = '{site}'{clause}")
    inside = [row for row in rows if start <= row["at"] <= end]
    return ["site", "at", "kind", "detail"], inside


# ── Ten intents, expressed both ways ─────────────────────────────────────────

WINDOW = ("2026-04-15T09:30:00", "2026-04-15T11:00:00")

# What a caller actually emits against a raw surface: some correct, some
# plausible-but-wrong syntax, one prose site name, one invented clause.
RAW_ATTEMPTS = [
    "SELECT * FROM events WHERE site = 'SITE_A'",
    "SELECT * FROM events WHERE site = 'SITE_A' AND kind = 'trip'",
    "select site, at from events where site='SITE_A'",          # column list
    "SELECT * FROM events WHERE site = 'SITE_A' AND at > '2026-04-15'",  # clause
    "SELECT * FROM events WHERE site LIKE '%SITE_A%'",           # operator
    "SELECT * FROM events WHERE site = 'North Yard'",            # prose name
    "SELECT * FROM events WHERE site = 'SITE_B' AND kind = 'fault'",  # bad kind
    "SELECT * FROM events WHERE site = 'SITE_B'",
    "SELECT * FROM events WHERE site = 'SITE_A'",                # repeat
    "SHOW events FOR SITE_A",                                    # invented
]

# The same three questions through the shaped tool. The five syntax variants
# cannot be expressed at all, so they never happen. What remains is the two
# genuine mistakes — a prose site name and an invented event kind — each
# refused with the fix, then repaired on the next call.
SHAPED_ATTEMPTS = [
    {"site": "North Yard substation", "start": WINDOW[0], "end": WINDOW[1]},  # refused
    {"site": "SITE_A", "start": WINDOW[0], "end": WINDOW[1]},                 # repaired
    {"site": "SITE_A", "start": WINDOW[0], "end": WINDOW[1], "kind": "trip"},
    {"site": "SITE_B", "start": WINDOW[0], "end": WINDOW[1], "kind": "fault"},  # refused
    {"site": "SITE_B", "start": WINDOW[0], "end": WINDOW[1], "kind": "alarm"},  # repaired
    {"site": "SITE_A", "start": WINDOW[1], "end": WINDOW[0]},                 # refused
]


def drive() -> MemorySink:
    """Run both surfaces under recording and return the collected records."""
    sink = MemorySink()
    previous = set_sink(sink)
    try:
        with turn(run_id="raw-1", case_id="incident-1", split="train"):
            for attempt in RAW_ATTEMPTS:
                run_query(query=attempt)
        with turn(run_id="shaped-1", case_id="incident-2", split="train"):
            for attempt in SHAPED_ATTEMPTS:
                find_events(**attempt)
    finally:
        set_sink(previous)
    return sink


def summarise(sink: MemorySink) -> dict[str, dict]:
    """Per-tool rates, for the assertions in tests/selftest.py."""
    report = aggregate(
        sink.records,
        outcomes=[
            # The shaped run reached an answer; the raw run did not.
            Outcome("incident-1", {"answer": "fail"}, "train"),
            Outcome("incident-2", {"answer": "pass"}, "train"),
        ],
    )
    return {tool.name: tool.to_dict(report.total_runs, report.total_cases)
            for tool in report.tools}


def main() -> int:
    sink = drive()
    stats = summarise(sink)

    print("A refusal is the interface teaching the caller:\n")
    print(" ", find_events(site="North Yard substation",
                           start=WINDOW[0], end=WINDOW[1]))
    print("\nA raw failure is not:\n")
    print(" ", run_query(query="SHOW events FOR SITE_A"))

    print("\n" + "=" * 72)
    print(f"{'':<14}{'calls':>7}{'errors':>8}{'refused':>9}{'answers':>9}")
    for name in ("run_query", "find_events"):
        row = stats[name]
        counts = row["counts"]
        print(
            f"{name:<14}{row['total_calls']:>7}"
            f"{counts.get('error', 0):>8}"
            f"{counts.get('refused', 0):>9}"
            f"{counts.get('productive', 0):>9}"
        )
    print("=" * 72)
    print(
        "\nSame backend, same three questions. The raw surface spends four\n"
        "calls on syntax the caller had to author, and each failure teaches\n"
        "it nothing. The shaped surface cannot express those mistakes at all;\n"
        "its three refusals each name the fix and are repaired on the next\n"
        "call. Fewer calls, no errors, same answers.\n"
    )

    report = aggregate(sink.records, outcomes=[
        Outcome("incident-1", {"answer": "fail"}, "train"),
        Outcome("incident-2", {"answer": "pass"}, "train"),
    ])
    print(render_markdown(report, title="Tool weight — worked example"))
    print(
        "Read the signal column with care: one run per case is far too little\n"
        "evidence to act on. The protocol asks for at least three runs per\n"
        "case before a flag means anything (GOTCHAS.md G3)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
