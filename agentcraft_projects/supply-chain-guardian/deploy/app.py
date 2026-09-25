"""FastAPI wrapper exposing the supply-chain-guardian agent for Container Apps hosting.

Endpoints:
  GET  /healthz                  liveness probe
  GET  /incidents                run all scenarios, return incident cards (mocked Work/Fabric IQ,
                                  live Web IQ from stored scenario evidence, optional live Foundry IQ)
  POST /incidents/{id}/decision  apply an explicit human decision ("approved"|"rejected") to move
                                  a card past Requires Approval. This is the ONLY way a
                                  consequential action can execute; nothing here auto-approves.
  GET  /dashboard                interactive live portal: fetches /incidents, lets you Approve/
                                  Reject in real time, auto-refreshes every 8s
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.reasoning import run_all, apply_decision, build_incident  # noqa: E402
from agent.dashboard import INTERACTIVE_PAGE  # noqa: E402
import json  # noqa: E402

app = FastAPI(title="Supply Chain Guardian", version="0.1.0")

_scenarios = json.load(open(ROOT / "dataset" / "scenarios.json", encoding="utf-8"))
_cards = {s["id"]: build_incident(s) for s in _scenarios}


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


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    return INTERACTIVE_PAGE
