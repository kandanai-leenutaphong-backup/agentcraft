from __future__ import annotations

import os

from fastapi.testclient import TestClient

for key in (
    "WEB_IQ_API_KEY",
    "WORK_IQ_TENANT_ID",
    "WORK_IQ_CLIENT_ID",
    "WORK_IQ_REFRESH_TOKEN",
    "WORK_IQ_USER_UPN",
):
    os.environ.pop(key, None)

from agent import app as app_module


client = TestClient(app_module.app)


def test_reprobe_returns_502_on_unexpected_exception(monkeypatch):
    scenario_id = "scenario-01-clear-disruption"

    def boom(card, scenario):
        raise RuntimeError("ontology missing node")

    monkeypatch.setattr(app_module, "refresh_evidence", boom)

    response = client.post(f"/incidents/{scenario_id}/reprobe")

    assert response.status_code == 502
    assert response.json()["detail"] == "could not refresh incident evidence: ontology missing node"


def test_simulate_returns_502_without_partial_state_update(monkeypatch):
    scenario_id = "sim-test-partial-update"
    scenario = {"id": scenario_id}

    monkeypatch.setattr(app_module, "simulate_new_disruption", lambda: scenario)
    monkeypatch.setattr(app_module, "build_incident", lambda _, **__: (_ for _ in ()).throw(RuntimeError("bad ontology")))

    response = client.post("/incidents/simulate")

    assert response.status_code == 502
    assert response.json()["detail"] == "could not simulate a new disruption: bad ontology"
    assert scenario_id not in app_module._cards
    assert scenario_id not in app_module._scenarios_by_id
