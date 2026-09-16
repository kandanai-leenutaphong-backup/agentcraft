import copy
import json
import stat

import pytest

from app.cybereye.tests.replay_baseline import assemble, evidence_plan, replay_scan, rule_plan, write_private


WINDOW = {"start": "2026-08-13T02:30:00Z", "end": "2026-08-13T03:40:00Z"}
CONFIGURATION = {"version": "fixture-v1", "max_window_seconds": 172800,
    "rule_sets": [{"id": "fixture", "name": "Fixture", "enabled": True, "rules": [
        {"id": "fixture_rule", "name": "Fixture rule", "enabled": True,
         "query": "EventsUnified | where source_time between (start .. end)",
         "parameters": {"threshold": 1, "score": 25, "role": "anchor", "confidence": "medium"},
         "processing": {"kind": "entity_groups", "max_rows": 100}},
    ]}]}


def observed_rules():
    plan = rule_plan({"run_id": "fixture", "target": {"service": "adx", "database": "Fixture"}},
                     CONFIGURATION, WINDOW, 99)
    plan["cases"][0]["expected"] = {
        "columns": ["host", "principal", "event_count", "first_seen", "last_seen", "evidence_ids"],
        "rows": [["fixture-host", "fixture-user", 1,
                  {"type": "datetime", "value": "2026-08-13T03:00:00+00:00"},
                  {"type": "datetime", "value": "2026-08-13T03:00:00+00:00"}, ["row-1"]]],
        "truncated": False,
    }
    return plan


def test_native_observations_compose_scan_and_complete_evidence_without_library_io(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("candidate must not establish its own baseline")

    monkeypatch.setattr("azdata.connect", refuse)
    rules = observed_rules()
    plan = evidence_plan(rules, CONFIGURATION, WINDOW, 99)
    assert len(plan["cases"]) == 1
    assert "row-1" not in plan["cases"][0]["expression"]
    assert plan["cases"][0]["parameters"] == {"rid0": "row-1"}
    plan["cases"][0]["expected"] = {"columns": ["resource_id"], "rows": [["row-1"]], "truncated": False}
    baseline = assemble(rules, plan, CONFIGURATION, WINDOW, 99)
    assert baseline["scan"]["summary"]["situations"] == 1
    situation = baseline["scan"]["situations"][0]
    assert situation["first_seen"] == "2026-08-13T03:00:00Z"
    assert baseline["evidence"][situation["situation_id"]]["rows"] == [["row-1"]]
    assert baseline["evidence"][situation["situation_id"]]["max_rows"] == 99


@pytest.mark.parametrize("change", ["window", "query", "missing", "parameter"])
def test_changed_or_unobserved_native_rules_refuse(change):
    rules = observed_rules()
    window = copy.deepcopy(WINDOW)
    if change == "window":
        window["end"] = "2026-08-13T03:30:00Z"
    elif change == "query":
        rules["cases"][0]["expression"] += " | take 1"
    elif change == "parameter":
        rules["cases"][0]["parameters"]["rule_threshold"] = 2
    else:
        rules["cases"][0]["expected"] = None
    with pytest.raises(ValueError):
        replay_scan(rules, CONFIGURATION, window, 99)


def test_native_evidence_requires_correct_target_and_observed_query():
    rules = observed_rules()
    evidence = evidence_plan(rules, CONFIGURATION, WINDOW, 99)
    with pytest.raises(ValueError):
        assemble(rules, evidence, CONFIGURATION, WINDOW, 99)
    evidence["target"]["database"] = "Other"
    with pytest.raises(ValueError, match="target mismatch"):
        assemble(rules, evidence, CONFIGURATION, WINDOW, 99)


def test_private_baselines_are_exclusive_and_refuse_checkout_paths(tmp_path):
    output = tmp_path / "private.json"
    write_private(output, {"fixture": True})
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert json.loads(output.read_text()) == {"fixture": True}
    with pytest.raises(FileExistsError):
        write_private(output, {"fixture": False})
    (tmp_path / ".git").mkdir()
    with pytest.raises(ValueError, match="outside a checkout"):
        write_private(tmp_path / "tracked.json", {})