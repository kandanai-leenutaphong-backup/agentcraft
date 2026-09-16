"""selftest — proves the box works here, with no test framework installed.

Run: ``python3 tests/selftest.py``. Exits non-zero on any failure.

Covers both halves and, critically, the seam between them: tools built with
the shaping half are driven through a scripted caller and scored by the
measuring half, and the scores are asserted. Testing either half alone
would prove nothing about the contract they share — which is exactly where
a rewrite would drift.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import sys
import tempfile
from concurrent.futures import CancelledError as FutureCancelledError
from pathlib import Path
from unittest import TestCase

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# The decorator logs every caught exception; the tests provoke several.
logging.getLogger("toolshape").setLevel(logging.CRITICAL)

from toolshape import (  # noqa: E402
    CallRecord,
    JsonlSink,
    MemorySink,
    Outcome,
    Param,
    Rejection,
    ToolSpec,
    aggregate,
    bounded_list,
    catalogue,
    classify,
    duplicate,
    escape_quotes,
    failure,
    identifier,
    integer_range,
    is_unproductive,
    json_schema,
    lint,
    one_of,
    purpose_built,
    read_records,
    refusal,
    render_markdown,
    sanitize_detail,
    set_sink,
    specs_in,
    table,
    time_window,
    timestamp,
    turn,
    uuid,
)
from toolshape._envelope import (  # noqa: E402
    DUPLICATE,
    EMPTY,
    ERROR,
    MISSING,
    PRODUCTIVE,
    REFUSED,
    RESULT_CLASSES,
)

_FAILURES: list[str] = []
_SENSITIVE_PARTS = (
    "G3PrivateFailureType",
    "credential=g3-not-a-real-token",
    "prompt=g3-private-prompt",
    "path=/private/g3/input.txt",
    "response=g3-private-response",
    "https://g3-private.invalid/payload",
)
_SAFE_FAILURE = {
    "error": True,
    "detail": "tool_failed",
    "code": "tool_failed",
    "category": "failed",
    "action": "inspect_tool_and_read_back_effects",
    "effect": "unknown",
    "retry": "read_back_first",
}


def check(label: str, condition: bool) -> None:
    if condition:
        print(f"  ok   {label}")
    else:
        print(f"  FAIL {label}")
        _FAILURES.append(label)


def section(title: str) -> None:
    print(title)


# ── Envelope ─────────────────────────────────────────────────────────────────


def test_envelope() -> None:
    section("envelope")
    payload = json.loads(table(["a", "b"], [{"a": 1, "b": 2}], scope={"site": "S"}))
    check("table carries columns, rows and scope", payload["columns"] == ["a", "b"])
    check("row_count is added automatically", payload["scope"]["row_count"] == 1)

    empty = json.loads(table(["a"], [], scope={"site": "S"}))
    check("an empty result still declares its columns", empty["columns"] == ["a"])
    check("and still carries scope", empty["scope"]["site"] == "S")

    rejected = json.loads(refusal("site", "value is empty", "a code like 'SITE_A'"))
    check("a refusal names the parameter", rejected["parameter"] == "site")
    check("and what would be accepted", "SITE_A" in rejected["accepted"])

    sensitive = " ".join(_SENSITIVE_PARTS)
    failed = json.loads(failure(sensitive, exc=ValueError(sensitive)))
    check("a failure returns fixed safe machine metadata", failed == _SAFE_FAILURE)
    check("failure metadata excludes arbitrary detail without an exception",
          json.loads(failure(sensitive)) == _SAFE_FAILURE)

    class UnprintableFailure(Exception):
        def __str__(self) -> str:
            raise AssertionError("exception text must not be inspected")

    check("failure never formats an exception",
          json.loads(failure(sensitive, exc=UnprintableFailure())) == _SAFE_FAILURE)
    check("detail is capped", len(sanitize_detail("x" * 900)) == 500)

    repeat = json.loads(duplicate("find_events", {"site": "S"}))
    check("a duplicate says so explicitly", repeat["duplicate"] is True)
    check(
        "and tells the caller not to retry",
        "do not repeat" in repeat["detail"],
    )

    check("classify: rows present", classify(table(["a"], [{"a": 1}])) == PRODUCTIVE)
    check("classify: rows empty", classify(table(["a"], [])) == EMPTY)
    check("classify: error envelope", classify(failure("x")) == ERROR)
    check("classify: refusal", classify(refusal("p", "q", "r")) == REFUSED)
    check("classify: duplicate", classify(duplicate("t")) == DUPLICATE)
    check("classify: nothing delivered", classify(None) == MISSING)
    check("classify: serialized absence", classify("null") == MISSING)
    check("classify: explicit missing envelope", classify('{"missing": true}') == MISSING)
    check("classify: truncated payload is productive", classify(...) == PRODUCTIVE)
    check("classify: bare empty list", classify("[]") == EMPTY)
    check("classify: non-json text", classify("some text") == PRODUCTIVE)

    check("refusals are not unproductive", is_unproductive(REFUSED) is False)
    check("duplicates are not unproductive", is_unproductive(DUPLICATE) is False)
    check("errors are", is_unproductive(ERROR) is True)


# ── Validators ───────────────────────────────────────────────────────────────


def test_validators() -> None:
    section("validators")
    site = identifier(max_len=8, example="SITE_A")
    check("accepts a code", site("SITE_A", "site") == "SITE_A")
    check("trims whitespace", site("  SITE_A  ", "site") == "SITE_A")

    too_long = site("SITE_A_VERY_LONG", "site")
    check("rejects an over-long value", isinstance(too_long, Rejection))
    check("names the parameter", too_long.parameter == "site")
    check("states the accepted form", "at most 8" in too_long.accepted)

    bad_chars = site("North Yard (33kV)", "site")
    check("rejects unsupported characters", isinstance(bad_chars, Rejection))
    check("empty is rejected", isinstance(site("", "site"), Rejection))
    check("a quote is rejected by the character class",
          isinstance(identifier()("O'Hara", "s"), Rejection))
    check("the escape helper is still available for built query text",
          escape_quotes("O'Hara") == "O''Hara")

    kind = one_of(("trip", "alarm"))
    check("enum accepts a member", kind("trip", "kind") == "trip")
    check("enum is case-insensitive by default", kind("TRIP", "kind") == "trip")
    unknown = kind("fault", "kind")
    check("enum rejects a non-member", isinstance(unknown, Rejection))
    check("and lists every legal value", "'trip'" in unknown.accepted and "'alarm'" in unknown.accepted)

    when = timestamp()
    check("timestamp normalises", when("2026-04-15T10:00:00Z", "start").startswith("2026-04-15T10:00:00"))
    check("timestamp rejects prose", isinstance(when("last tuesday", "start"), Rejection))

    ranged = integer_range(1, 10)
    check("range accepts", ranged("5", "n") == 5)
    check("range rejects out of bounds", isinstance(ranged(99, "n"), Rejection))
    check("range rejects non-numbers", isinstance(ranged("many", "n"), Rejection))

    listed = bounded_list(identifier(), cap=3)
    check("bounded list accepts", listed(["A", "B"], "items") == ["A", "B"])
    over = listed(["A", "B", "C", "D"], "items")
    check("bounded list enforces the cap", isinstance(over, Rejection))
    check("and states the cap", "cap of 3" in over.problem or "3 items" in over.accepted)
    check("a string is not a list", isinstance(listed("A", "items"), Rejection))
    inner = listed(["A", "!!"], "items")
    check("an invalid item is reported by position", isinstance(inner, Rejection) and "[1]" in inner.parameter)

    check("uuid accepts", uuid()("3f2504e0-4f89-41d3-9a0c-0305e82c3301", "id") is not None)
    check("uuid rejects a code", isinstance(uuid()("SITE_A", "id"), Rejection))

    window = time_window(max_hours=2)
    check("window accepts an ordered pair", window({"start": "2026-04-15T10:00:00", "end": "2026-04-15T11:00:00"}) is None)
    reversed_window = window({"start": "2026-04-15T11:00:00", "end": "2026-04-15T10:00:00"})
    check("window rejects a reversed pair", isinstance(reversed_window, Rejection))
    too_wide = window({"start": "2026-04-15T10:00:00", "end": "2026-04-15T20:00:00"})
    check("window enforces the span cap", isinstance(too_wide, Rejection))
    check("window ignores an absent pair", window({"start": ""}) is None)


# ── Spec ─────────────────────────────────────────────────────────────────────

DEMO = ToolSpec(
    name="find_events",
    purpose="Return events at one site inside a window.",
    call_when="Whenever you need events for a site. Use the code from list_sites.",
    params=[
        Param("site", "Site code from list_sites.", validator=identifier(max_len=8)),
        Param("start", "Window start from the incident time.", validator=timestamp()),
        Param("end", "Window end from the incident time.", validator=timestamp()),
        Param("kind", "One of the listed kinds.", validator=one_of(("trip", "alarm")), required=False),
    ],
    dedupe_on=("site", "start", "end", "kind"),
    cross_checks=(time_window(max_hours=48),),
)

WINDOW = {"start": "2026-04-15T09:00:00", "end": "2026-04-15T11:00:00"}


def test_spec() -> None:
    section("spec")
    description = DEMO.description()
    check("description states the purpose", "Return events" in description)
    check("description states when to call", "When to call:" in description)
    check("description states the return shape", "Returns:" in description)

    cleaned = DEMO.validate({"site": "SITE_A", **WINDOW})
    check("validates and normalises", cleaned["site"] == "SITE_A")
    check("an absent optional becomes its default", cleaned["kind"] is None)

    missing = DEMO.validate({**WINDOW})
    check("a missing required parameter is refused", isinstance(missing, Rejection))
    check("naming the parameter", missing.parameter == "site")

    crossed = DEMO.validate({"site": "SITE_A", "start": WINDOW["end"], "end": WINDOW["start"]})
    check("cross-checks run after per-parameter checks", isinstance(crossed, Rejection))

    check(
        "unknown arguments pass through",
        DEMO.validate({"site": "SITE_A", **WINDOW, "sdk_id": "x"})["sdk_id"] == "x",
    )

    key_a = DEMO.dedupe_key({"site": "SITE_A", **WINDOW, "kind": None})
    key_b = DEMO.dedupe_key({"site": "site_a", **WINDOW, "kind": None})
    check("dedupe key ignores case", key_a == key_b)
    check("scope echoes the identifying arguments", DEMO.scope_of({"site": "SITE_A"})["site"] == "SITE_A")

    param = DEMO.param("site")
    check("param description carries the accepted form", "Accepts" in param.describe())
    check("optional params say so", "Optional." in DEMO.param("kind").describe())


# ── Decorator ────────────────────────────────────────────────────────────────

_CALLS: list[dict] = []


@purpose_built(DEMO)
def find_events(site: str, start: str, end: str, kind: str | None = None):
    _CALLS.append({"site": site, "kind": kind})
    if site == "MISSING":
        return None
    if site == "EMPTY":
        return ["site", "at"], []
    if site == "BOOM":
        raise RuntimeError("backend exploded")
    return ["site", "at"], [{"site": site, "at": start}]


ASYNC_SPEC = ToolSpec(
    name="find_async",
    purpose="Async variant.",
    call_when="When the backend is async. Use the code from list_sites.",
    params=[Param("site", "Site code from list_sites.", validator=identifier())],
    dedupe_on=("site",),
)


@purpose_built(ASYNC_SPEC)
async def find_async(site: str):
    if site == "MISSING":
        return None
    if site == "EMPTY":
        return []
    return [{"site": site}]


def test_decorator() -> None:
    section("decorator")
    _CALLS.clear()
    payload = json.loads(find_events(site="SITE_A", **WINDOW))
    check("wraps rows into the table shape", payload["rows"][0]["site"] == "SITE_A")
    check("populates scope from dedupe_on", payload["scope"]["site"] == "SITE_A")

    refused = json.loads(find_events(site="THIS_IS_TOO_LONG", **WINDOW))
    check("refuses invalid input", refused["refused"] is True)
    check("without calling the body", len(_CALLS) == 1)

    broken = json.loads(find_events(site="BOOM", **WINDOW))
    check("an exception becomes a failure envelope", broken["error"] is True)
    check("without tool or exception payload in detail", broken == _SAFE_FAILURE)

    nothing = json.loads(find_events(site="EMPTY", **WINDOW))
    check("an empty result keeps its columns", nothing["columns"] == ["site", "at"])
    check("explicit empty rows remain empty", classify(nothing) == EMPTY)

    missing = find_events(site="MISSING", **WINDOW)
    check("absent output has no fabricated rows or count", json.loads(missing) == {"missing": True})
    check("absent sync output classifies as missing", classify(missing) == MISSING)

    check("positional arguments validate identically",
          json.loads(find_events("SITE_A", WINDOW["start"], WINDOW["end"]))["rows"])

    check("the spec is attached for discovery", find_events.__toolspec__ is DEMO)
    check("the docstring is generated from the spec", "When to call:" in find_events.__doc__)

    async def _async_case() -> None:
        result = json.loads(await find_async(site="SITE_A"))
        check("async tools are wrapped too", result["rows"][0]["site"] == "SITE_A")
        missing = await find_async(site="MISSING")
        empty = json.loads(await find_async(site="EMPTY"))
        check("absent async output has no fabricated count", json.loads(missing) == {"missing": True})
        check("absent async output classifies as missing", classify(missing) == MISSING)
        check("async empty rows report a real zero count",
              classify(empty) == EMPTY and empty["scope"]["row_count"] == 0)

    asyncio.run(_async_case())

    check("specs_in discovers decorated tools",
          {s.name for s in specs_in(sys.modules[__name__])} >= {"find_events", "find_async"})


def test_failure_safety() -> None:
    section("failure privacy and exception policy")
    spec = ToolSpec(name="failing_tool", purpose="Test failure handling.",
                    call_when="Offline failure check.", params=[])
    private_failure = type("G3PrivateFailureType", (RuntimeError,), {})
    sink = MemorySink()
    previous = set_sink(sink)
    try:
        for error_type in (private_failure, TypeError):
            error = error_type(" ".join(_SENSITIVE_PARTS))

            @purpose_built(spec)
            def sync_failure():
                raise error

            @purpose_built(spec)
            async def async_failure():
                raise error

            for mode in ("sync", "async"):
                label = f"{mode} {error_type.__name__}"
                with TestCase().assertLogs("toolshape", level="WARNING") as captured:
                    payload = (sync_failure() if mode == "sync"
                               else asyncio.run(async_failure()))
                check(f"{label}: fixed bounded failure metadata",
                      json.loads(payload) == _SAFE_FAILURE and len(payload) <= 500)
                check(f"{label}: error is not an empty or successful result",
                      classify(payload) == ERROR)
                observed = payload + repr(captured.output) + repr(sink.records)
                check(f"{label}: no exception payload or type in output, logs or ledger",
                      all(part not in observed for part in (*_SENSITIVE_PARTS, "TypeError")))
                check(f"{label}: logs retain no traceback or stack",
                      len(captured.records) == 1 and all(
                          record.exc_info is None and record.stack_info is None
                          for record in captured.records))
        check("failure ledger retains stable machine codes only",
              len(sink.records) == 4 and all(
                  record.result_class == ERROR and record.detail == "tool_failed"
                  for record in sink.records))

        @purpose_built(spec)
        def malformed_result():
            return ["site"], None

        with TestCase().assertRaises(TypeError):
            malformed_result()
        check("result-shaping programming errors still propagate", len(sink.records) == 4)
    finally:
        set_sink(previous)


def test_control_exceptions() -> None:
    section("control exceptions")
    spec = ToolSpec(name="interrupted_tool", purpose="Test control propagation.",
                    call_when="Offline cancellation check.", params=[])
    sink = MemorySink()
    previous = set_sink(sink)
    try:
        for control_type in (asyncio.CancelledError, FutureCancelledError,
                             KeyboardInterrupt, SystemExit):
            control = control_type()

            @purpose_built(spec)
            def sync_control():
                raise control

            @purpose_built(spec)
            async def async_control():
                raise control

            async def check_async_control():
                with TestCase().assertRaises(control_type) as caught:
                    await async_control()
                return caught.exception

            with TestCase().assertNoLogs("toolshape", level="DEBUG"):
                with TestCase().assertRaises(control_type) as caught:
                    sync_control()
                check(f"sync {control_type.__module__}.{control_type.__name__} propagates",
                      caught.exception is control)
                check(f"async {control_type.__module__}.{control_type.__name__} propagates",
                      asyncio.run(check_async_control()) is control)
        check("control exceptions emit no failure or success record", not sink.records)
    finally:
        set_sink(previous)


# ── Ledger ───────────────────────────────────────────────────────────────────


def test_ledger() -> None:
    section("ledger and recording")
    sink = MemorySink()
    previous = set_sink(sink)
    try:
        # No turn set: the guard is inert, so a direct call is never suppressed.
        find_events(site="SITE_A", **WINDOW)
        find_events(site="SITE_A", **WINDOW)
        classes = [r.result_class for r in sink.records]
        check("outside a turn no call is suppressed", classes == [PRODUCTIVE, PRODUCTIVE])

        sink.clear()
        with turn(run_id="r1", case_id="c1", split="train"):
            find_events(site="SITE_A", **WINDOW)
            find_events(site="SITE_A", **WINDOW)
            find_events(site="SITE_B", **WINDOW)
        classes = [r.result_class for r in sink.records]
        check("a repeat within a turn is suppressed", classes == [PRODUCTIVE, DUPLICATE, PRODUCTIVE])
        check("records carry the run label", sink.records[0].run_id == "r1")
        check("records carry the case label", sink.records[0].case_id == "c1")
        check("records carry the split", sink.records[0].split == "train")
        check("records carry no argument values",
              all("SITE_A" not in r.detail for r in sink.records))

        sink.clear()
        with turn(run_id="r2", case_id="c2"):
            find_events(site="SITE_A", **WINDOW)
        check("a new turn resets the ledger", sink.records[0].result_class == PRODUCTIVE)

        sink.clear()
        with turn(run_id="r3", case_id="c3"):
            find_events(site="TOO_LONG_FOR_THIS", **WINDOW)
        check("a refusal records the parameter", sink.records[0].detail == "site")

        sink.clear()
        find_events(site="MISSING", **WINDOW)
        find_events(site="EMPTY", **WINDOW)
        asyncio.run(find_async(site="MISSING"))
        asyncio.run(find_async(site="EMPTY"))
        check("ledger separates sync and async absence from empty results",
              [record.result_class for record in sink.records] == [MISSING, EMPTY, MISSING, EMPTY])
    finally:
        set_sink(previous)


def test_jsonl_roundtrip() -> None:
    section("record file")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "calls.jsonl"
        sink = JsonlSink(path)
        previous = set_sink(sink)
        try:
            with turn(run_id="r1", case_id="c1", split="train"):
                find_events(site="SITE_A", **WINDOW)
                find_events(site="BOOM", **WINDOW)
        finally:
            set_sink(previous)

        # A partial final line is the normal state of a file being appended to.
        with path.open("a", encoding="utf-8") as handle:
            handle.write('{"tool": "trunc')

        records = list(read_records(path))
        check("records survive the round trip", len(records) == 2)
        check("classes survive", [r.result_class for r in records] == [PRODUCTIVE, ERROR])
        check("a truncated final line is skipped, not fatal", True)


# ── Weight meter ─────────────────────────────────────────────────────────────


def _records(spec: list[tuple[str, str, str, str]]) -> list[CallRecord]:
    """(tool, class, run, case) tuples -> records."""
    return [
        CallRecord(tool=t, result_class=c, run_id=r, case_id=case)
        for t, c, r, case in spec
    ]


def test_stats() -> None:
    section("weight meter")
    records = _records(
        [("good", PRODUCTIVE, "r1", "c1"), ("good", PRODUCTIVE, "r2", "c2")]
        + [("noisy", ERROR, f"r{i}", f"c{i}") for i in (1, 2)]
        + [("noisy", PRODUCTIVE, "r1", "c1")]
    )
    report = aggregate(records)
    stats = {t.name: t for t in report.tools}

    check("counts calls", stats["good"].total_calls == 2)
    check("counts runs using", stats["good"].runs_using == 2)
    check("computes the error rate", round(stats["noisy"].error_rate(), 2) == 0.67)
    check("a clean tool is not flagged", stats["good"].signal == "ok")
    check("a failing tool is flagged", stats["noisy"].signal.startswith("review"))
    check("with a reason naming the rate", "error rate" in stats["noisy"].reason)
    check("candidates are listed", [c.name for c in report.candidates()] == ["noisy"])

    # A refusal-heavy but otherwise working tool must NOT be flagged: its
    # guardrails are doing their job (the finding that changed this design).
    refusing = aggregate(
        _records([("picky", REFUSED, f"r{i}", f"c{i}") for i in range(1, 5)]
                 + [("picky", PRODUCTIVE, f"r{i}", f"c{i}") for i in range(1, 5)])
    )
    picky = refusing.tools[0]
    check("a 50% refusal rate does not flag a cull", picky.signal == "ok")
    check("but is reported as an advisory", "refusal rate" in picky.reason)
    check("and is excluded from unproductive", picky.unproductive_rate() == 0.0)
    check("while counting toward turn cost", picky.turn_cost_rate() == 0.5)

    # Duplicates are advisory in the same way.
    repeating = aggregate(
        _records([("chatty", DUPLICATE, "r1", "c1"), ("chatty", PRODUCTIVE, "r1", "c1")])
    )
    check("a duplicate rate is advisory", repeating.tools[0].signal == "ok")
    check("with the scope-block hint", "scope block" in repeating.tools[0].reason)

    # Refusal hotspots name the failing parameter.
    hotspot = aggregate(
        [CallRecord(tool="t", result_class=REFUSED, detail="site", run_id="r1", case_id="c1")] * 3
    )
    check("refusal hotspots name the parameter",
          hotspot.tools[0].refusal_params.most_common(1)[0] == ("site", 3))


def test_association() -> None:
    section("outcome association")
    records = _records(
        [("helper", PRODUCTIVE, "r1", "c1"), ("helper", PRODUCTIVE, "r2", "c2")]
        + [("other", PRODUCTIVE, "r3", "c3"), ("other", PRODUCTIVE, "r4", "c4")]
    )
    outcomes = [
        Outcome("c1", {"answer": "pass"}),
        Outcome("c2", {"answer": "pass"}),
        Outcome("c3", {"answer": "fail"}),
        Outcome("c4", {"answer": "fail"}),
    ]
    report = aggregate(records, outcomes)
    helper = next(t for t in report.tools if t.name == "helper")
    check("used arm rate computed", helper.association["answer"]["used_rate"] == 1.0)
    check("unused arm rate computed", helper.association["answer"]["unused_rate"] == 0.0)
    check("a positively associated tool reads strong", helper.signal == "strong")

    # A noisy but positively associated tool must be fixed, not culled — the
    # finding that a 44% error tool was still load-bearing.
    noisy_useful = aggregate(
        _records(
            [("raw", ERROR, "r1", "c1"), ("raw", ERROR, "r2", "c2"), ("raw", PRODUCTIVE, "r3", "c3")]
            + [("shaped", PRODUCTIVE, "r4", "c4"), ("shaped", PRODUCTIVE, "r5", "c5")]
        ),
        [
            Outcome("c1", {"answer": "pass"}),
            Outcome("c2", {"answer": "pass"}),
            Outcome("c3", {"answer": "pass"}),
            Outcome("c4", {"answer": "fail"}),
            Outcome("c5", {"answer": "fail"}),
        ],
    )
    raw = next(t for t in noisy_useful.tools if t.name == "raw")
    check("noisy but associated is not a cull candidate", raw.signal == "noisy but associated")
    check("and says fix, do not cull", "fix, do not cull" in raw.reason)

    # A thin control arm must not count as evidence.
    thin = aggregate(
        _records([("t", ERROR, "r1", "c1"), ("t", ERROR, "r2", "c2")]),
        [Outcome("c1", {"answer": "pass"}), Outcome("c2", {"answer": "pass"})],
    )
    check("no control arm means no association claim",
          thin.tools[0].signal.startswith("review"))

    # Cases with an outcome but no recorded call still form the control arm.
    with_control = aggregate(
        _records([("t", PRODUCTIVE, "r1", "c1")]),
        [Outcome("c1", {"answer": "pass"}), Outcome("c2", {"answer": "fail"}),
         Outcome("c3", {"answer": "fail"})],
    )
    check("uncalled cases join the unused arm",
          with_control.tools[0].association["answer"]["unused_n"] == 2)


def test_render() -> None:
    section("report rendering")
    report = aggregate(
        _records([("noisy", ERROR, "r1", "c1"), ("noisy", ERROR, "r2", "c2")])
    )
    markdown = render_markdown(report, title="Weights")
    check("renders a title", markdown.startswith("# Weights"))
    check("renders the table header", "| tool | calls |" in markdown)
    check("lists candidates", "Review / cull candidates" in markdown)
    check("states that a flag is a hypothesis", "hypothesis" in markdown)
    check("points at the ablation protocol", "ablation" in markdown)

    payload = report.to_dict()
    check("serialises", payload["tools"][0]["name"] == "noisy")
    check("names review candidates in json", payload["review_candidates"] == ["noisy"])
    check("json is serialisable", isinstance(json.dumps(payload), str))


# ── Catalogue and lint ───────────────────────────────────────────────────────


def test_catalogue_and_lint() -> None:
    section("catalogue and lint")
    page = catalogue([DEMO])
    check("renders the surface table", "| `find_events` |" in page)
    check("renders per-parameter detail", "`site`" in page)

    schema = json_schema(DEMO)
    check("json schema names required params", schema["parameters"]["required"] == ["site", "start", "end"])
    check("json schema carries the description", "When to call:" in schema["description"])

    check("a well-shaped tool lints clean", lint([DEMO]) == [])

    sloppy = ToolSpec(
        name="thing",
        purpose="",
        call_when="use it",
        params=[Param("x", "")],
        dedupe_on=("nope",),
    )
    findings = lint([sloppy])
    messages = [f.message for f in findings]
    levels = {f.level for f in findings}
    check("a missing purpose is an error", any("no purpose" in m for m in messages))
    check("a short call_when is an error", any("call_when" in m for m in messages))
    check("an undescribed parameter is an error", any("no description" in m for m in messages))
    check("a dedupe key that is not a parameter is an error",
          any("not a parameter" in m for m in messages))
    check("errors are levelled", "error" in levels)

    wide = lint([DEMO] * 1 + [sloppy] * 9, max_tools=3)
    check("an over-wide surface warns", any("exceeds" in f.message for f in wide))

    unvalidated = ToolSpec(
        name="raw",
        purpose="Run a query.",
        call_when="When you want to write the query yourself, from scratch.",
        params=[Param("query", "The query text.")],
        dedupe_on=("query",),
    )
    warnings = [f.message for f in lint([unvalidated]) if f.level == "warn"]
    check("an unvalidated parameter warns", any("no validator" in m for m in warnings))
    check("an undocumented value source warns", any("where its value comes from" in m for m in warnings))


# ── Round trip: the two halves against each other ────────────────────────────


def test_round_trip() -> None:
    section("round trip (shaping half scored by measuring half)")
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))
    import promote_raw_query as worked  # noqa: E402

    sink = worked.drive()
    stats = worked.summarise(sink)
    raw, shaped = stats["run_query"], stats["find_events"]

    check("the raw surface errors", raw["counts"].get("error", 0) == 4)
    check("the shaped surface does not", shaped["counts"].get("error", 0) == 0)
    check("both reach the same answers",
          raw["counts"]["productive"] == shaped["counts"]["productive"] == 3)
    check("the shaped surface takes fewer calls",
          shaped["total_calls"] < raw["total_calls"])
    check("the raw surface is flagged", raw["signal"].startswith("review"))
    check("the shaped surface is not", not shaped["signal"].startswith("review"))
    check("every shaped failure is a refusal that teaches",
          shaped["counts"].get("refused", 0) == 3)
    check("and the refusals name their parameters",
          {p for p, _ in shaped["top_refused_parameters"]} == {"site", "kind", "end"})


# ── Azure examples ───────────────────────────────────────────────────────────

_AZURE_EXAMPLES = (
    "graph_gremlin",
    "telemetry_kql",
    "knowledge_search",
    "ontology_gql",
    "documents_cosmos",
)


def _load_azure(name: str):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples" / "azure"))
    return __import__(name)


def test_azure_examples() -> None:
    section("azure examples")
    for name in _AZURE_EXAMPLES:
        module = _load_azure(name)
        payloads = module.demo()
        if asyncio.iscoroutine(payloads):
            payloads = asyncio.run(payloads)

        classes = [classify(p) for p in payloads]
        check(f"{name}: every call returns a JSON string",
              all(isinstance(p, str) for p in payloads))
        check(f"{name}: every result classifies", all(c in RESULT_CLASSES for c in classes))
        check(f"{name}: produces a usable result", PRODUCTIVE in classes)
        check(f"{name}: refuses at least one bad call", REFUSED in classes)

        # Every declared archetype must be a real renderer key, or the tool
        # ships with no card (GOTCHAS.md G18).
        check(f"{name}: declares an archetype per tool",
              set(module.ARCHETYPES) == {s.name for s in specs_in(module)})

        for payload, result_class in zip(payloads, classes):
            if result_class != PRODUCTIVE:
                continue
            parsed = json.loads(payload)
            if "rows" in parsed:
                check(f"{name}: tables carry scope", "scope" in parsed)

    gremlin = _load_azure("graph_gremlin")
    summary = json.loads(gremlin.graph_summary(node_id="site-1"))
    check("gremlin: graph shape carries nodes and edges",
          "nodes" in summary and "edges" in summary)

    kql = _load_azure("telemetry_kql")
    metrics = json.loads(
        kql.summarise_metric(site="SITE_A", start=kql.WINDOW[0],
                             end=kql.WINDOW[1], aggregation="avg")
    )
    check("kql: metric shape carries metrics", isinstance(metrics["metrics"], list))

    search = _load_azure("knowledge_search")
    hits = json.loads(search.search_knowledge(question="how do I isolate a pump",
                                              index="procedures"))
    check("search: hits carry title, source, score and text",
          set(hits["results"][0]) == {"title", "source", "score", "text"})
    check("search: hit text is capped",
          all(len(h["text"]) <= search.TEXT_CAP for h in hits["results"]))

    gql = _load_azure("ontology_gql")
    check("gql: a 200 carrying a query error becomes an error envelope",
          classify(gql.query_ontology(entity="WorkOrder")) == ERROR)

    cosmos = _load_azure("documents_cosmos")
    listing = json.loads(asyncio.run(cosmos.list_documents()))
    check("cosmos: listing returns metadata only",
          all(set(row) == set(cosmos.LIST_COLUMNS) for row in listing["rows"]))
    check("cosmos: listing never returns bodies",
          all("body" not in row for row in listing["rows"]))


# ── Renderer contract ────────────────────────────────────────────────────────


def test_renderer_contract() -> None:
    section("renderer contract")
    root = Path(__file__).resolve().parent.parent
    archetype_dir = root / "renderers" / "archetypes"
    registry = (archetype_dir / "index.ts").read_text(encoding="utf-8")

    declared = set(re.findall(r'^\s*\w+\s*=\s*"([a-z]+)",\s*$', registry, re.M))
    check("the registry declares archetypes", len(declared) >= 7)

    # A key with no component is a tool with no card.
    for key in sorted(declared):
        component = archetype_dir / f"{key.capitalize()}Renderer.tsx"
        check(f"archetype {key!r} has a component", component.is_file())
        check(f"archetype {key!r} is wired into the registry",
              f"{key.capitalize()}Renderer" in registry)

    contract = (root / "CONTRACT.md").read_text(encoding="utf-8")
    for key in sorted(declared):
        check(f"archetype {key!r} is documented in CONTRACT.md", f"`{key}`" in contract)

    # Every archetype an example claims must exist, and every archetype that
    # exists should be reachable from an example or it is undemonstrated.
    used: set[str] = set()
    for name in _AZURE_EXAMPLES:
        module = _load_azure(name)
        for tool, archetype in module.ARCHETYPES.items():
            check(f"{name}.{tool} maps to a real archetype", archetype in declared)
            used.add(archetype)
    check("the worked examples exercise most archetypes", len(used) >= 4)

    # Every renderer must handle all three envelope states identically, which
    # it can only do by routing through the shared helper.
    for component in sorted(archetype_dir.glob("*Renderer.tsx")):
        source = component.read_text(encoding="utf-8")
        check(f"{component.name} routes envelope states through the shared helper",
              "renderEnvelopeState" in source)
        check(f"{component.name} never dumps raw JSON",
              "ArchetypeUnresolved" in source)

    card = (root / "renderers" / "ToolResultCard.tsx").read_text(encoding="utf-8")
    for state in ("error", "refusal", "duplicate"):
        check(f"the card distinguishes the {state} state",
              f'data-tool-card="{state if state != "refusal" else "refused"}"' in card)


# ── Runner ───────────────────────────────────────────────────────────────────


def main() -> int:
    test_envelope()
    test_validators()
    test_spec()
    test_decorator()
    test_failure_safety()
    test_control_exceptions()
    test_ledger()
    test_jsonl_roundtrip()
    test_stats()
    test_association()
    test_render()
    test_catalogue_and_lint()
    test_round_trip()
    test_azure_examples()
    test_renderer_contract()

    print()
    if _FAILURES:
        print(f"FAILED: {len(_FAILURES)} check(s)")
        for failure_label in _FAILURES:
            print(f"  - {failure_label}")
        return 1
    print("selftest passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
