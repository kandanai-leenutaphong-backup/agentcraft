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
  GET  /dashboard                interactive live portal: loads once when opened; nothing
                                  auto-refreshes in the background (no polling loop, no
                                  always-running probe thread) so live-IQ calls only happen
                                  when you actually open the app or click Refresh/Re-probe
  POST /auth/device/start        begin an in-app device-code sign-in for a given IQ scope
                                  ("search" for Foundry IQ, "fabric" for Fabric IQ) so consent
                                  can be granted without a separate CLI/terminal step
  POST /auth/device/poll         single non-blocking poll of a pending device-code sign-in
  POST /chat                     rule-based agent console: type a command ("list", "explain
                                  <id>", "reprobe <id>", "approve/reject <id>", "simulate",
                                  "help") and it calls the same functions the dashboard buttons
                                  use. Not an LLM; a deterministic intent parser only.
"""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path
from typing import Literal, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.reasoning import apply_decision, build_incident, refresh_evidence, simulate_new_disruption  # noqa: E402
from agent import iq_auth  # noqa: E402
from agent.dashboard import INTERACTIVE_PAGE  # noqa: E402
import json  # noqa: E402

app = FastAPI(title="Supply Chain Guardian", version="0.1.0")

_scenarios = json.load(open(ROOT / "dataset" / "scenarios.json", encoding="utf-8"))
_scenarios_by_id = {s["id"]: s for s in _scenarios}
_cards = {s["id"]: build_incident(s) for s in _scenarios}

_REFRESH_THROTTLE_SECONDS = 20  # guards against burning live-IQ quota on rapid repeat opens
_last_open_refresh = 0.0


def _refresh_open_incidents_on_demand() -> None:
    """No background thread, no fixed-interval polling: this only runs synchronously when a
    human actually opens/refreshes the app (called from GET /incidents), so live-IQ calls (and
    their cost/quota) are incurred only on real usage, not continuously in an idle container."""
    global _last_open_refresh
    now = time.time()
    if now - _last_open_refresh < _REFRESH_THROTTLE_SECONDS:
        return
    _last_open_refresh = now
    for scenario_id, card in list(_cards.items()):
        if card.state in ("Executed", "Rejected"):
            continue  # decision already made; stop re-probing a closed incident
        try:
            refresh_evidence(card, _scenarios_by_id[scenario_id])
        except Exception:
            pass  # never let a probe failure break the incidents endpoint


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
    _refresh_open_incidents_on_demand()
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


_DEVICE_SCOPES = {
    "search": "https://search.azure.com/user_impersonation offline_access",
    "fabric": "https://api.fabric.microsoft.com/Workspace.Read.All "
              "https://api.fabric.microsoft.com/Item.ReadWrite.All offline_access",
}


class DeviceStart(BaseModel):
    target: Literal["search", "fabric"]


class DevicePoll(BaseModel):
    device_code: str


@app.post("/auth/device/start")
def auth_device_start(body: DeviceStart):
    """Begin an in-app device-code sign-in for Foundry IQ ('search') or Fabric IQ ('fabric').
    AAD only allows a single resource per device-code request, so these are separate flows;
    the dashboard shows one button per source. Returns the code the user types in at
    login.microsoft.com/device plus the device_code the dashboard will poll against."""
    try:
        flow = iq_auth.start_device_code(_DEVICE_SCOPES[body.target])
    except Exception as exc:
        raise HTTPException(502, f"could not start device-code sign-in: {exc}")
    return {
        "verification_uri": flow.get("verification_uri", "https://login.microsoft.com/device"),
        "user_code": flow["user_code"],
        "device_code": flow["device_code"],
        "expires_in": flow.get("expires_in", 900),
        "interval": flow.get("interval", 5),
    }


@app.post("/auth/device/poll")
def auth_device_poll(body: DevicePoll):
    """Single non-blocking poll of a pending sign-in. The dashboard calls this every few
    seconds (only while a human has an auth panel open) until it reports success/error."""
    return iq_auth.poll_device_code(body.device_code)


_CHAT_HELP = (
    "Commands (type an incident id or a distinctive word from it):\n"
    "- list / status — every incident and its approval state\n"
    "- explain <incident> — root-cause hypothesis with exactly which evidence it's derived from\n"
    "- reprobe <incident> — re-run all four live IQ probes right now\n"
    "- approve <incident> / reject <incident> — apply a human decision (only path past approval gate)\n"
    "- simulate — generate a brand-new disruption from the live ontology graph\n"
    "- help — show this message"
)


def _match_scenario_id(text_l: str) -> Optional[str]:
    """Best-effort match of a scenario id mentioned in free text: exact id, 'scenario-NN',
    or falls back to None (caller asks the human to be specific rather than guessing)."""
    for sid in _cards:
        if sid in text_l:
            return sid
    m = re.search(r"scenario[-\s]?(\d+)", text_l)
    if m:
        num = m.group(1).zfill(2)
        for sid in _cards:
            if f"scenario-{num}" in sid:
                return sid
    return None


def _citations_for(card) -> list:
    """The exact evidence records the hypothesis was derived from, one line per IQ source,
    naming the real transaction/document identifiers (not just 'trust me')."""
    d = card.to_dict()
    br = d["blast_radius"]
    cites = [f"Fabric IQ: shipment {br.get('shipment_id', '?')} / material {br.get('material_id', '?')} "
              f"(blast radius: {len(br.get('affected_plants', []))} plant(s), {len(br.get('affected_skus', []))} SKU(s))"]
    fdy = d["foundry_iq_evidence"]["data"] or []
    if fdy:
        cites.append(f"Foundry IQ: governed policy doc(s) {', '.join(p['id'] for p in fdy)}")
    query = f"{br.get('material_id', '')} supplier shipment delay {br.get('shipment_id', '')}".strip()
    cites.append(f"Web IQ: live search \"{query}\"")
    wk = d["work_iq_evidence"]["data"]
    if wk:
        cites.append("Work IQ: organizational/collaboration context on file for this account")
    return cites


def _handle_chat_command(message: str) -> dict:
    """Deterministic, rule-based command console (no LLM configured): maps a short set of
    intents onto the same functions the dashboard's buttons call, so a human can drive the
    agent by typing. Every consequential action still requires the incident to explicitly
    be named and in 'Requires Approval' state; nothing here auto-approves."""
    text = message.strip()
    text_l = text.lower()
    if not text:
        return {"reply": "Type a command, or 'help' for the list.", "action_taken": False, "scenario_id": None}
    if text_l in ("help", "?", "commands"):
        return {"reply": _CHAT_HELP, "action_taken": False, "scenario_id": None}
    if "simulate" in text_l or "new disruption" in text_l:
        scenario = simulate_new_disruption()
        _scenarios_by_id[scenario["id"]] = scenario
        card = build_incident(scenario)
        _cards[scenario["id"]] = card
        return {"reply": f"Simulated new disruption {scenario['id']}: {card.hypothesis}",
                "action_taken": True, "scenario_id": scenario["id"]}
    if text_l.startswith("list") or text_l.startswith("status") or ("incidents" in text_l and "explain" not in text_l):
        lines = [f"{sid}: {c.state} (confidence {c.confidence})" for sid, c in _cards.items()]
        return {"reply": "\n".join(lines) or "No incidents loaded.", "action_taken": False, "scenario_id": None}

    scenario_id = _match_scenario_id(text_l)
    if not scenario_id:
        return {"reply": "I couldn't find a matching incident in that message. Name it exactly "
                          "(e.g. 'explain scenario-01-clear-disruption') or type 'list' to see all ids.",
                "action_taken": False, "scenario_id": None}
    card = _cards[scenario_id]

    if "reprobe" in text_l or "refresh" in text_l:
        refresh_evidence(card, _scenarios_by_id[scenario_id])
        return {"reply": f"Re-probed all four live IQ sources for {scenario_id}. State: {card.state}.",
                "action_taken": True, "scenario_id": scenario_id}
    if "approve" in text_l:
        if card.state != "Requires Approval":
            return {"reply": f"{scenario_id} is in state '{card.state}', not awaiting approval.",
                    "action_taken": False, "scenario_id": scenario_id}
        apply_decision(card, "approved")
        return {"reply": f"Approved {scenario_id}. Execution result: {card.execution_result or 'pending'}.",
                "action_taken": True, "scenario_id": scenario_id}
    if "reject" in text_l:
        if card.state != "Requires Approval":
            return {"reply": f"{scenario_id} is in state '{card.state}', not awaiting approval.",
                    "action_taken": False, "scenario_id": scenario_id}
        apply_decision(card, "rejected")
        return {"reply": f"Rejected {scenario_id}.", "action_taken": True, "scenario_id": scenario_id}
    if "explain" in text_l or "why" in text_l or "root cause" in text_l or "rca" in text_l:
        cites = "\n- ".join(_citations_for(card))
        return {"reply": f"Root-cause hypothesis for {scenario_id}:\n{card.hypothesis}\n\nDerived from:\n- {cites}",
                "action_taken": False, "scenario_id": scenario_id}
    return {"reply": f"{scenario_id} is currently '{card.state}'. Try 'explain {scenario_id}' for the full "
                      "root-cause trace, or 'help' for commands.",
            "action_taken": False, "scenario_id": scenario_id}


class ChatMessage(BaseModel):
    message: str


@app.post("/chat")
def chat(body: ChatMessage):
    return _handle_chat_command(body.message)


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
    # Explicit no-cache: without this, browsers can silently keep serving a stale cached copy
    # of this page's inline JS (e.g. an old auto-polling version) after a redeploy.
    headers = {"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"}
    return HTMLResponse(content=INTERACTIVE_PAGE, headers=headers)
