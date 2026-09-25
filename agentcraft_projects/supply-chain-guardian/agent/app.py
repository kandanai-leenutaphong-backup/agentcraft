"""FastAPI wrapper exposing the supply-chain-guardian agent for Container Apps hosting.

Endpoints:
  GET  /healthz                  liveness probe
  GET  /incidents                run all scenarios, return incident cards (mocked Work/Fabric IQ,
                                  live Web IQ from stored scenario evidence, optional live Foundry IQ)
  POST /incidents/{id}/decision  apply an explicit human decision ("approved"|"rejected") to move
                                  a card past Requires Approval. This is the ONLY way a
                                  consequential action can execute; nothing here auto-approves.
  POST /incidents/{id}/reprobe   re-run all four live IQ probes for one incident on demand
  POST /incidents/simulate       generate a brand-new disruption from the live ontology graph
                                  (not a canned scenario) and run the full reasoning pass on it
  GET  /activity                 merged, time-ordered feed of every IQ call/decision across all
                                  incidents, tagged by scenario_id
  GET  /dashboard                interactive live portal: fetches /incidents, lets you Approve/
                                  Reject in real time, auto-refreshes every 8s
"""
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.reasoning import apply_decision, build_incident, refresh_evidence, simulate_new_disruption  # noqa: E402
from agent.dashboard import INTERACTIVE_PAGE  # noqa: E402
import json  # noqa: E402

app = FastAPI(title="Supply Chain Guardian", version="0.1.0")

_scenarios = json.load(open(ROOT / "dataset" / "scenarios.json", encoding="utf-8"))
_scenarios_by_id = {s["id"]: s for s in _scenarios}
_cards = {s["id"]: build_incident(s) for s in _scenarios}


def _background_monitor(interval_seconds: int = 60) -> None:
    """Always-running loop: periodically re-probes Web IQ / Work IQ / Foundry IQ / Fabric IQ
    for every open incident so the portal reflects fresh live evidence over time, not a
    one-shot snapshot taken at container startup."""
    while True:
        time.sleep(interval_seconds)
        for scenario_id, card in list(_cards.items()):
            if card.state in ("Executed", "Rejected"):
                continue  # decision already made; stop re-probing a closed incident
            try:
                refresh_evidence(card, _scenarios_by_id[scenario_id])
            except Exception:
                pass  # never let a background probe failure crash the monitor loop


threading.Thread(target=_background_monitor, daemon=True).start()


class Decision(BaseModel):
    decision: Literal["approved", "rejected"]


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/dashboard")


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/incidents")
def list_incidents():
    return [c.to_dict() for c in _cards.values()]


@app.get("/incidents/{scenario_id}")
def get_incident(scenario_id: str):
    card = _cards.get(scenario_id)
    if not card:
        raise HTTPException(404, "scenario not found")
    return card.to_dict()


@app.post("/incidents/{scenario_id}/decision")
def decide(scenario_id: str, body: Decision):
    card = _cards.get(scenario_id)
    if not card:
        raise HTTPException(404, "scenario not found")
    if card.state != "Requires Approval":
        raise HTTPException(409, f"incident is in state '{card.state}', not awaiting approval")
    apply_decision(card, body.decision)
    return card.to_dict()


@app.post("/incidents/{scenario_id}/reprobe")
def reprobe(scenario_id: str):
    """On-demand: re-run all four live IQ probes right now, bypassing the 60s background
    cadence. Lets a human watching the portal trigger a fresh live check immediately."""
    card = _cards.get(scenario_id)
    if not card:
        raise HTTPException(404, "scenario not found")
    refresh_evidence(card, _scenarios_by_id[scenario_id])
    return card.to_dict()


@app.post("/incidents/simulate")
def simulate():
    """Generates a brand-new disruption on demand, deriving its blast radius live from the
    ontology graph (not one of the four fixed canned scenarios), then runs the full four-source
    reasoning pass against it. Demonstrates the agent framework operating on novel input."""
    scenario = simulate_new_disruption()
    _scenarios_by_id[scenario["id"]] = scenario
    card = build_incident(scenario)
    _cards[scenario["id"]] = card
    return card.to_dict()


@app.get("/activity")
def activity(limit: int = 60):
    """Merged, time-ordered feed of every IQ-source call and agent/human decision across all
    incidents (each entry tagged with its scenario_id). This is the cross-incident 'what is
    the agent actually doing right now' console the portal renders at the top."""
    events = []
    for scenario_id, card in _cards.items():
        for entry in card.trace:
            events.append({**entry, "scenario_id": scenario_id})
    events.sort(key=lambda e: e["ts"])
    return events[-limit:]


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    return INTERACTIVE_PAGE
