"""Validator, spec and lint edge cases.

The selftest covers the main paths. These are the cases that were argued
about, got wrong once, or would be quietly dropped by a rewrite.

Run: ``python3 -m pytest tests/ -q``
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from toolshape import (
    CallRecord,
    MemorySink,
    Param,
    Rejection,
    ToolSpec,
    aggregate,
    bounded_list,
    classify,
    identifier,
    integer_range,
    lint,
    one_of,
    purpose_built,
    set_sink,
    table,
    time_window,
    timestamp,
    turn,
)
from toolshape._envelope import DUPLICATE, EMPTY, ERROR, MISSING, PRODUCTIVE, REFUSED


# ── Validators ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "value", ["SITE_A", "site a", "Site-A", "A1", "  SITE_A  "]
)
def test_identifier_accepts_code_shapes(value):
    assert not isinstance(identifier()(value, "site"), Rejection)


@pytest.mark.parametrize(
    "value", ["", "   ", "SITE/A", "SITE.A", "site'; DROP", "SITE|A", None]
)
def test_identifier_rejects_everything_else(value):
    assert isinstance(identifier()(value, "site"), Rejection)


def test_every_rejection_states_an_accepted_form():
    # The field that stops a refusal being a dead end (GOTCHAS.md G11).
    rejections = [
        identifier()("", "a"),
        one_of(("x",))("y", "b"),
        timestamp()("nope", "c"),
        integer_range(1, 2)(9, "d"),
        bounded_list(identifier(), cap=1)(["a", "b"], "e"),
    ]
    for rejection in rejections:
        assert isinstance(rejection, Rejection)
        assert rejection.accepted.strip()
        assert rejection.parameter


def test_one_of_lists_every_option_in_the_refusal():
    rejection = one_of(("trip", "alarm", "notice"))("fault", "kind")
    for option in ("trip", "alarm", "notice"):
        assert repr(option) in rejection.accepted


def test_one_of_returns_the_canonical_member():
    assert one_of(("Trip",))("trip", "kind") == "Trip"


def test_one_of_case_sensitive_mode():
    assert isinstance(one_of(("Trip",), case_sensitive=True)("trip", "k"), Rejection)


def test_bounded_list_names_the_offending_position():
    rejection = bounded_list(identifier(), cap=5)(["OK", "bad/value"], "sites")
    assert rejection.parameter == "sites[1]"


def test_bounded_list_rejects_a_bare_string():
    # A string is iterable, so without the guard "ABC" becomes ["A","B","C"].
    assert isinstance(bounded_list(identifier(), cap=5)("ABC", "sites"), Rejection)


def test_timestamp_accepts_trailing_z():
    assert timestamp()("2026-04-15T10:00:00Z", "start").startswith("2026-04-15T10:00:00")


def test_time_window_stays_silent_when_a_bound_is_unparseable():
    # The per-parameter validator already reported it; two refusals for one
    # mistake is worse than one.
    check = time_window()
    assert check({"start": "nonsense", "end": "2026-04-15T10:00:00"}) is None


def test_time_window_catches_the_reversed_pair(): 
    # Individually valid, jointly wrong (GOTCHAS.md G14).
    check = time_window()
    rejection = check({"start": "2026-04-15T11:00:00", "end": "2026-04-15T10:00:00"})
    assert isinstance(rejection, Rejection)


# ── Spec ─────────────────────────────────────────────────────────────────────

SPEC = ToolSpec(
    name="t",
    purpose="Return things.",
    call_when="Whenever you need things. Use the code from list_things.",
    params=[
        Param("a", "A code from list_things.", validator=identifier()),
        Param("b", "Optional kind, one of the listed values.",
              validator=one_of(("x", "y")), required=False),
    ],
    dedupe_on=("a", "b"),
)


def test_only_the_first_failure_is_reported():
    rejection = SPEC.validate({"a": "bad/value", "b": "nope"})
    assert rejection.parameter == "a"


def test_optional_absent_uses_the_default():
    assert SPEC.validate({"a": "OK"})["b"] is None


def test_optional_present_is_still_validated():
    assert isinstance(SPEC.validate({"a": "OK", "b": "nope"}), Rejection)


def test_blank_string_counts_as_absent():
    assert isinstance(SPEC.validate({"a": "   "}), Rejection)


def test_unknown_arguments_survive():
    assert SPEC.validate({"a": "OK", "injected": 1})["injected"] == 1


def test_dedupe_key_is_case_and_whitespace_insensitive():
    assert SPEC.dedupe_key({"a": " OK ", "b": "X"}) == SPEC.dedupe_key({"a": "ok", "b": "x"})


def test_description_contains_all_three_sections():
    text = SPEC.description()
    assert "Return things." in text
    assert "When to call:" in text
    assert "Returns:" in text


# ── Classification ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "payload,expected",
    [
        ('{"rows": [{"a": 1}]}', PRODUCTIVE),
        ('{"rows": []}', EMPTY),
        ('{"summary": {"total_rows": 0}}', EMPTY),
        ('{"summary": {"total_rows": 3}}', PRODUCTIVE),
        ('{"error": true, "detail": "x"}', ERROR),
        ('{"refused": true}', REFUSED),
        ('{"duplicate": true}', DUPLICATE),
        ("[]", EMPTY),
        ("[1]", PRODUCTIVE),
        ("plain text", PRODUCTIVE),
        ("", EMPTY),
        (None, MISSING),
        (..., PRODUCTIVE),
        (42, PRODUCTIVE),
    ],
)
def test_classification(payload, expected):
    assert classify(payload) == expected


def test_empty_result_still_declares_its_columns():
    payload = json.loads(table(["a", "b"], [], scope={"x": 1}))
    assert payload["columns"] == ["a", "b"]
    assert payload["scope"]["row_count"] == 0


# ── Decorator ────────────────────────────────────────────────────────────────


@purpose_built(SPEC)
def sample(a: str, b: str | None = None):
    return [{"a": a}]


def test_repeat_is_suppressed_only_inside_a_turn():
    sink = MemorySink()
    previous = set_sink(sink)
    try:
        sample(a="OK")
        sample(a="OK")
        assert [r.result_class for r in sink.records] == [PRODUCTIVE, PRODUCTIVE]

        sink.clear()
        with turn(run_id="r", case_id="c"):
            sample(a="OK")
            sample(a="OK")
        assert [r.result_class for r in sink.records] == [PRODUCTIVE, DUPLICATE]
    finally:
        set_sink(previous)


def test_max_calls_allows_a_second_call():
    spec = ToolSpec(
        name="twice",
        purpose="p",
        call_when="Whenever you need it, from the listing.",
        params=[Param("a", "A code from the listing.", validator=identifier())],
        dedupe_on=("a",),
        max_calls=2,
    )

    @purpose_built(spec)
    def twice(a: str):
        return [{"a": a}]

    sink = MemorySink()
    previous = set_sink(sink)
    try:
        with turn(run_id="r", case_id="c"):
            twice(a="OK")
            twice(a="OK")
            twice(a="OK")
        assert [r.result_class for r in sink.records] == [
            PRODUCTIVE, PRODUCTIVE, DUPLICATE
        ]
    finally:
        set_sink(previous)


def test_a_tool_never_raises():
    @purpose_built(
        ToolSpec(name="boom", purpose="p",
                 call_when="Whenever you need it, from the listing.",
                 params=[Param("a", "A code from the listing.",
                               validator=identifier())],
                 dedupe_on=("a",))
    )
    def boom(a: str):
        raise RuntimeError("backend gone")

    payload = json.loads(boom(a="OK"))
    assert payload["error"] is True


# ── Meter ────────────────────────────────────────────────────────────────────


def _rec(tool, cls, run="r1", case="c1", detail=""):
    return CallRecord(tool=tool, result_class=cls, run_id=run, case_id=case, detail=detail)


def test_refusals_are_turn_cost_not_waste():
    # The finding that changed the design (GOTCHAS.md G13).
    report = aggregate([_rec("t", REFUSED, f"r{i}", f"c{i}") for i in range(4)]
                       + [_rec("t", PRODUCTIVE, f"r{i}", f"c{i}") for i in range(4)])
    stat = report.tools[0]
    assert stat.unproductive_rate() == 0.0
    assert stat.turn_cost_rate() == 0.5
    assert not stat.signal.startswith("review")


def test_missing_is_not_empty():
    report = aggregate([_rec("t", MISSING), _rec("t", EMPTY)])
    stat = report.tools[0]
    assert stat.classes[MISSING] == 1
    assert stat.classes[EMPTY] == 1


def test_single_run_still_aggregates_without_a_run_id():
    report = aggregate([CallRecord(tool="t", result_class=PRODUCTIVE, case_id="c1")])
    assert report.tools[0].runs_using == 1


def test_thin_control_arm_is_not_evidence():
    from toolshape import Outcome

    report = aggregate(
        [_rec("t", ERROR, "r1", "c1"), _rec("t", ERROR, "r2", "c2")],
        [Outcome("c1", {"g": "pass"}), Outcome("c2", {"g": "pass"})],
    )
    assert report.tools[0].signal.startswith("review")


def test_refusal_hotspot_names_the_parameter():
    report = aggregate([_rec("t", REFUSED, detail="site") for _ in range(3)])
    assert report.tools[0].refusal_params.most_common(1)[0] == ("site", 3)


# ── Lint ─────────────────────────────────────────────────────────────────────


def test_well_shaped_spec_lints_clean():
    assert lint([SPEC]) == []


def test_dedupe_key_must_be_a_parameter():
    bad = ToolSpec(name="x", purpose="p",
                   call_when="Whenever you need it, from the listing.",
                   params=[Param("a", "A code from the listing.")],
                   dedupe_on=("missing",))
    assert any("not a parameter" in f.message for f in lint([bad]) if f.level == "error")


def test_duplicate_tool_names_are_an_error():
    findings = lint([SPEC, SPEC])
    assert any("duplicate tool name" in f.message for f in findings)
