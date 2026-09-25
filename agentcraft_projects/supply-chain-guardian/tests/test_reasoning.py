from __future__ import annotations

import copy
import json
import urllib.error
from pathlib import Path

import pytest

from agent import iq_auth, reasoning, web_iq, work_iq

ROOT = Path(__file__).resolve().parent.parent
SCENARIOS = json.loads((ROOT / "dataset" / "scenarios.json").read_text(encoding="utf-8"))
SCENARIOS_BY_ID = {scenario["id"]: scenario for scenario in SCENARIOS}


class DummyResponse:
    def __init__(self, payload: dict, status: int = 200):
        self._payload = json.dumps(payload).encode()
        self.status = status

    def read(self) -> bytes:
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


@pytest.fixture(autouse=True)
def clear_live_iq_env(monkeypatch: pytest.MonkeyPatch):
    for key in (
        "WEB_IQ_API_KEY",
        "WORK_IQ_TENANT_ID",
        "WORK_IQ_CLIENT_ID",
        "WORK_IQ_REFRESH_TOKEN",
        "WORK_IQ_USER_UPN",
    ):
        monkeypatch.delenv(key, raising=False)
    iq_auth._CACHE.clear()


def test_build_incident_sets_expected_approval_state_by_scenario_kind():
    expected_states = {
        "clear_disruption": "Requires Approval",
        "cascading_disruption": "Requires Approval",
        "no_action_needed": "Monitoring",
        "insufficient_evidence": "Monitoring",
    }

    for scenario in SCENARIOS:
        card = reasoning.build_incident(scenario)
        assert card.state == expected_states[scenario["kind"]]
        assert (card.state == "Requires Approval") is scenario["expected_requires_approval"]


def test_refresh_evidence_does_not_mutate_card_when_rebuild_fails(monkeypatch: pytest.MonkeyPatch):
    scenario = SCENARIOS_BY_ID["scenario-01-clear-disruption"]
    card = reasoning.build_incident(scenario)
    original = copy.deepcopy(card.to_dict())

    def boom(_: dict):
        raise RuntimeError("malformed ontology")

    monkeypatch.setattr(reasoning, "build_incident", boom)

    with pytest.raises(RuntimeError, match="malformed ontology"):
        reasoning.refresh_evidence(card, scenario)

    assert card.to_dict() == original


def test_apply_decision_refuses_when_not_waiting_for_approval():
    card = reasoning.build_incident(SCENARIOS_BY_ID["scenario-03-no-action-needed"])
    original_state = card.state
    original_trace = list(card.trace)

    returned = reasoning.apply_decision(card, "approved")

    assert returned is card
    assert card.state == original_state == "Monitoring"
    assert card.execution_result is None
    assert card.trace == original_trace


def test_apply_decision_refuses_double_apply():
    card = reasoning.build_incident(SCENARIOS_BY_ID["scenario-01-clear-disruption"])

    reasoning.apply_decision(card, "approved")
    first_state = card.state
    first_result = card.execution_result
    first_trace = list(card.trace)

    reasoning.apply_decision(card, "rejected")

    assert first_state == "Executed"
    assert card.state == "Executed"
    assert card.execution_result == first_result
    assert card.trace == first_trace


def test_live_probes_without_configuration_return_graceful_fallbacks():
    web_result = web_iq.live_web_search("delay")
    work_result = work_iq.live_recent_mail()
    foundry_result = reasoning.live_foundry_iq_probe("delay")
    fabric_result = reasoning.live_fabric_iq_probe()

    assert web_result["mocked"] is True
    assert web_result["request"]["body"]["query"] == "delay"

    assert work_result["mocked"] is True
    assert work_result["request"]["method"] == "GET"

    assert foundry_result["live"] is False
    assert foundry_result["request"]["body"]["search"] == "delay"

    assert fabric_result["live"] is False
    assert fabric_result["request"]["method"] == "GET"


@pytest.mark.parametrize("case", ["web", "work", "foundry", "fabric"])
def test_live_probe_retries_once_then_succeeds(monkeypatch: pytest.MonkeyPatch, case: str):
    calls = {"count": 0}

    def fake_urlopen(req, timeout=0):
        calls["count"] += 1
        if calls["count"] == 1:
            raise urllib.error.URLError("timed out")
        payloads = {
            "web": {"webResults": [{"title": "Delay update", "url": "https://example.test/delay"}]},
            "work": {"value": [{"subject": "Ops alert", "from": {"emailAddress": {"address": "ops@example.test"}}, "receivedDateTime": "2026-09-25T00:00:00Z"}]},
            "foundry": {"value": [{"id": "POLICY-1", "title": "Continuity", "category": "policy"}]},
            "fabric": {"value": [{"id": "item-1", "type": "Lakehouse", "displayName": "Supply Chain"}]},
        }
        return DummyResponse(payloads[case])

    monkeypatch.setattr(web_iq.time, "sleep", lambda _: None)
    monkeypatch.setattr(work_iq.time, "sleep", lambda _: None)
    monkeypatch.setattr(reasoning.time, "sleep", lambda _: None)

    if case == "web":
        monkeypatch.setenv("WEB_IQ_API_KEY", "test-key")
        monkeypatch.setattr(web_iq.urllib.request, "urlopen", fake_urlopen)
        result = web_iq.live_web_search("delay")
        assert result["mocked"] is False
    elif case == "work":
        monkeypatch.setattr(work_iq, "_get_access_token", lambda: "token")
        monkeypatch.setattr(work_iq.urllib.request, "urlopen", fake_urlopen)
        result = work_iq.live_recent_mail()
        assert result["mocked"] is False
    elif case == "foundry":
        monkeypatch.setattr(iq_auth, "get_token", lambda scope: "token")
        monkeypatch.setattr(reasoning.urllib.request, "urlopen", fake_urlopen)
        result = reasoning.live_foundry_iq_probe("delay")
        assert result["live"] is True
    else:
        monkeypatch.setattr(iq_auth, "get_token", lambda scope: "token")
        monkeypatch.setattr(reasoning.urllib.request, "urlopen", fake_urlopen)
        result = reasoning.live_fabric_iq_probe()
        assert result["live"] is True

    assert calls["count"] == 2


@pytest.mark.parametrize("case", ["web", "work", "foundry", "fabric"])
def test_live_probe_retries_once_then_returns_graceful_failure(monkeypatch: pytest.MonkeyPatch, case: str):
    calls = {"count": 0}

    def always_fail(req, timeout=0):
        calls["count"] += 1
        raise urllib.error.URLError("connection reset")

    monkeypatch.setattr(web_iq.time, "sleep", lambda _: None)
    monkeypatch.setattr(work_iq.time, "sleep", lambda _: None)
    monkeypatch.setattr(reasoning.time, "sleep", lambda _: None)

    if case == "web":
        monkeypatch.setenv("WEB_IQ_API_KEY", "test-key")
        monkeypatch.setattr(web_iq.urllib.request, "urlopen", always_fail)
        result = web_iq.live_web_search("delay")
        assert result["mocked"] is True
        assert "live call failed" in result["reason"]
    elif case == "work":
        monkeypatch.setattr(work_iq, "_get_access_token", lambda: "token")
        monkeypatch.setattr(work_iq.urllib.request, "urlopen", always_fail)
        result = work_iq.live_recent_mail()
        assert result["mocked"] is True
        assert "live call failed" in result["reason"]
    elif case == "foundry":
        monkeypatch.setattr(iq_auth, "get_token", lambda scope: "token")
        monkeypatch.setattr(reasoning.urllib.request, "urlopen", always_fail)
        result = reasoning.live_foundry_iq_probe("delay")
        assert result["live"] is False
        assert "connection reset" in result["error"]
    else:
        monkeypatch.setattr(iq_auth, "get_token", lambda scope: "token")
        monkeypatch.setattr(reasoning.urllib.request, "urlopen", always_fail)
        result = reasoning.live_fabric_iq_probe()
        assert result["live"] is False
        assert "connection reset" in result["error"]

    assert "request" in result
    assert calls["count"] == 2
