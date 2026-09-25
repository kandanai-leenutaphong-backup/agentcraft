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
  GET  /dashboard                idle interactive portal: no incident/activity fetch on load;
                                  live-IQ calls require an explicit user action
  POST /auth/device/start        begin an in-app device-code sign-in for a given IQ scope
                                  ("search" for Foundry IQ, "fabric" for Fabric IQ) so consent
                                  can be granted without a separate CLI/terminal step
  POST /auth/device/poll         single non-blocking poll of a pending device-code sign-in
  POST /fabric/run-notebook      trigger a real Fabric notebook run (load_ontology_into_lakehouse)
                                  to populate live Lakehouse Delta tables; requires the
                                  Item.Execute.All scope (reconnect Fabric IQ if 403)
  POST /fabric/job-status        poll a previously started Fabric notebook job by status URL
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

from agent.reasoning import (apply_decision, build_incident, refresh_evidence, simulate_new_disruption,
                              run_fabric_notebook, poll_fabric_notebook_job)  # noqa: E402
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


@app.get("/debug/mi-status")
def debug_mi_status():
    """Diagnostic-only endpoint: reports whether the user-assigned managed identity (scg-uami)
    can mint tokens for each resource, without exposing the tokens themselves. Safe to leave
    in place (no secrets returned) but only intended for verifying the managed-identity wiring."""
    import os as _os
    import urllib.request as _ur
    import urllib.error as _ue
    import json as _json

    identity_endpoint = _os.environ.get("IDENTITY_ENDPOINT")
    identity_header = _os.environ.get("IDENTITY_HEADER")
    client_id = _os.environ.get("UAMI_CLIENT_ID")
    configured = bool(identity_endpoint and identity_header and client_id)
    result = {
        "UAMI_CLIENT_ID_set": bool(client_id),
        "IDENTITY_ENDPOINT_set": bool(identity_endpoint),
        "IDENTITY_HEADER_set": bool(identity_header),
    }
    for label, resource in [
        ("fabric", "https://api.fabric.microsoft.com"),
        ("search", "https://search.azure.com"),
        ("graph", "https://graph.microsoft.com"),
    ]:
        entry: dict = {}
        if not configured:
            entry = {"ok": False, "error": "identity endpoint/header/client id not all set"}
        else:
            params = f"api-version=2019-08-01&resource={resource}&client_id={client_id}"
            req = _ur.Request(
                f"{identity_endpoint}?{params}",
                headers={"x-identity-header": identity_header},
            )
            try:
                with _ur.urlopen(req, timeout=10) as resp:
                    body = _json.loads(resp.read())
                entry = {"ok": "access_token" in body, "expires_in": body.get("expires_in")}
            except _ue.HTTPError as exc:
                entry = {"ok": False, "http_status": exc.code, "detail": exc.read().decode(errors="replace")[:300]}
            except Exception as exc:
                entry = {"ok": False, "error": str(exc)[:200]}
        result[label] = entry
    return result


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
    try:
        refresh_evidence(card, _scenarios_by_id[scenario_id])
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(502, f"could not refresh incident evidence: {exc}")
    return card.to_dict()


@app.post("/incidents/simulate")
def simulate():
    """Generates a brand-new disruption on demand, deriving its blast radius live from the
    ontology graph (not one of the four fixed canned scenarios), then runs the full four-source
    reasoning pass against it. Demonstrates the agent framework operating on novel input."""
    try:
        scenario = simulate_new_disruption()
        card = build_incident(scenario)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(502, f"could not simulate a new disruption: {exc}")
    _scenarios_by_id[scenario["id"]] = scenario
    _cards[scenario["id"]] = card
    return card.to_dict()


_DEVICE_SCOPES = {
    "search": "https://search.azure.com/user_impersonation offline_access",
    "fabric": "https://api.fabric.microsoft.com/Workspace.Read.All "
              "https://api.fabric.microsoft.com/Item.ReadWrite.All "
              "https://api.fabric.microsoft.com/Item.Execute.All offline_access",
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


@app.post("/fabric/run-notebook")
def fabric_run_notebook():
    """Trigger a real, on-demand run of the load_ontology_into_lakehouse notebook so the
    Fabric Lakehouse gets populated with real Delta tables (shipments/suppliers/etc.)
    instead of staying empty. Requires Item.Execute.All; if the cached token predates that
    scope, returns needs_reconsent=True so the dashboard can prompt reconnecting Fabric IQ."""
    try:
        result = run_fabric_notebook()
    except Exception as exc:
        raise HTTPException(502, f"could not start notebook run: {exc}")
    return result


class FabricJobStatusQuery(BaseModel):
    job_status_url: str


@app.post("/fabric/job-status")
def fabric_job_status(body: FabricJobStatusQuery):
    """Single non-blocking poll of a Fabric notebook job's status (Running/Completed/Failed/
    etc.) by the job_status_url returned from /fabric/run-notebook."""
    try:
        return poll_fabric_notebook_job(body.job_status_url)
    except Exception as exc:
        raise HTTPException(502, f"could not poll job status: {exc}")


_CHAT_HELP = (
    "I am a deterministic command console, not an LLM. I can inspect incidents and run "
    "explicit commands. Reading status or explanations uses the evidence already on file.\n\n"
    "Choose an incident by its list number (1, 01, first), scenario number (scenario 2), "
    "full id, or distinctive words (clear, cascading, insufficient, no action).\n\n"
    "- list / status: every incident and its approval state\n"
    "- explain <incident>: hypothesis and the evidence it is derived from\n"
    "- reprobe <incident>: re-run all four live IQ probes now\n"
    "- approve <incident> / reject <incident>: your explicit decision, only while Requires Approval\n"
    "- simulate: generate a new disruption from the live ontology graph\n"
    "- help: show these commands"
)


def _scenario_candidates(text_l: str) -> list[str]:
    """Resolve references without guessing between multiple or unknown explicit targets."""
    remaining = text_l.lower()
    ids = list(_cards)
    matches = set()
    for sid in ids:
        pattern = rf"(?<![\w-]){re.escape(sid.lower())}(?![\w-])"
        if re.search(pattern, remaining):
            matches.add(sid)
            remaining = re.sub(pattern, " ", remaining)

    # Remove explicit ids first so their generic words cannot match other incidents.
    if re.search(r"\bscenario-\d+-[\w-]+", remaining):
        return []
    for match in re.finditer(r"\bscenario[-\s]*(\d+)\b", remaining):
        number = int(match.group(1))
        targets = [
            sid for sid in ids
            if re.match(rf"scenario-0*{number}(?:-|$)", sid)
        ]
        if not targets:
            return []
        matches.update(targets)
    remaining = re.sub(r"\bscenario[-\s]*\d+\b", " ", remaining)
    ordinals = dict(zip(
        ("first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth", "tenth"),
        range(1, 11),
    ))
    words = re.findall(r"[a-z]+|\d+(?:st|nd|rd|th)?", remaining)
    for word in words:
        number = ordinals.get(word)
        if re.fullmatch(r"\d+(?:st|nd|rd|th)?", word):
            number = int(re.match(r"\d+", word).group())
        if number is not None:
            if not 1 <= number <= len(ids):
                return []
            matches.add(ids[number - 1])
    for sid in ids:
        keywords = set(re.findall(r"[a-z]+", sid.lower())) - {"scenario"}
        if any(len(word) >= 3 and any(key.startswith(word) for key in keywords) for word in words):
            matches.add(sid)
    return [sid for sid in ids if sid in matches]


def _match_scenario_id(text_l: str) -> Optional[str]:
    candidates = _scenario_candidates(text_l)
    return candidates[0] if len(candidates) == 1 else None


def _chat_reply(reply: str, *, action_taken: bool = False,
                scenario_id: Optional[str] = None, suggestions: Optional[list[str]] = None) -> dict:
    if suggestions is None:
        suggestions = (
            [f"explain {scenario_id}", f"reprobe {scenario_id}", "list"]
            if scenario_id else ["list", "explain first", "help"]
        )
    if len(suggestions) < 2:
        suggestions = suggestions + [command for command in ("list", "help") if command not in suggestions]
    return {"reply": reply, "action_taken": action_taken, "scenario_id": scenario_id,
            "suggestions": suggestions[:5]}


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
    else:
        cites.append("Foundry IQ: no policy documents on file")
    web = d["web_iq_evidence"]
    web_data = web.get("data") or {}
    if web.get("mocked"):
        cites.append("Web IQ: fallback scenario evidence, not a live search result")
    elif web_data.get("query"):
        cites.append(f"Web IQ: search \"{web_data['query']}\"")
    else:
        cites.append("Web IQ: no search query recorded; inspect the retrieved evidence")
    wk = d["work_iq_evidence"]["data"]
    if wk:
        cites.append("Work IQ: organizational/collaboration context on file for this account")
    else:
        cites.append("Work IQ: no organizational context on file")
    return cites


def _handle_chat_command(message: str) -> dict:
    """Deterministic, rule-based command console (no LLM configured): maps a short set of
    intents onto the same functions the dashboard's buttons call, so a human can drive the
    agent by typing. Every consequential action requires one unambiguous incident and
    'Requires Approval' state; nothing here auto-approves."""
    text = message.strip()
    text_l = text.lower()
    if not text:
        return _chat_reply("Type a command, or 'help' for the list.")
    if text_l in ("help", "?", "commands"):
        return _chat_reply(_CHAT_HELP)
    if re.fullmatch(r"(?:please\s+)?(?:simulate|new disruption)[.!]?", text_l):
        scenario = simulate_new_disruption()
        _scenarios_by_id[scenario["id"]] = scenario
        card = build_incident(scenario)
        _cards[scenario["id"]] = card
        return _chat_reply(f"Simulated new disruption {scenario['id']}:\n\n{card.hypothesis}",
                           action_taken=True, scenario_id=scenario["id"])
    if re.fullmatch(r"(?:please\s+)?(?:list|status|incidents|list incidents|show incidents)[.!]?", text_l):
        lines = [f"- {i}. {sid}: {c.state} (confidence {c.confidence})"
                 for i, (sid, c) in enumerate(_cards.items(), 1)]
        return _chat_reply("Incidents on file:\n\n" + "\n".join(lines) if lines else "No incidents loaded.",
                           suggestions=[f"explain {sid}" for sid in list(_cards)[:4]] + ["help"])

    scenario_id = _match_scenario_id(text_l)
    if not scenario_id:
        candidates = _scenario_candidates(text_l)
        heading = ("That matches more than one incident." if candidates
                   else "I couldn't identify one incident from that reference.")
        choices = candidates or list(_cards)
        return _chat_reply(
            heading + " No action was taken. Choose one incident with its id or list number:\n\n"
            + ("\n".join(f"- {sid}" for sid in choices) or "No incidents loaded."),
            suggestions=[f"explain {sid}" for sid in choices[:4]] + ["list"],
        )
    card = _cards[scenario_id]

    command = re.match(r"^(?:please\s+)?(reprobe|refresh|approve|reject)\b", text_l)
    action = command.group(1) if command else None
    if action and (len(re.findall(r"\b(?:reprobe|refresh|approve|reject|simulate)\b", text_l)) > 1
                   or re.search(r"\b(?:not|never|don't|dont)\b", text_l)):
        return _chat_reply("No action was taken. Send one positive command at a time, such as "
                           "'approve <incident>' or 'reject <incident>'.", scenario_id=scenario_id)
    if action in ("reprobe", "refresh"):
        refresh_evidence(card, _scenarios_by_id[scenario_id])
        return _chat_reply(f"Re-probed all four live IQ sources for {scenario_id}. State: {card.state}.",
                           action_taken=True, scenario_id=scenario_id)
    if action in ("approve", "reject"):
        if card.state != "Requires Approval":
            return _chat_reply(f"{scenario_id} is in state '{card.state}', not awaiting approval.",
                               scenario_id=scenario_id)
        decision = "approved" if action == "approve" else "rejected"
        apply_decision(card, decision)
        result = f" Execution result: {card.execution_result or 'pending'}." if action == "approve" else ""
        return _chat_reply(f"{decision.capitalize()} {scenario_id}.{result}",
                           action_taken=True, scenario_id=scenario_id)
    if re.search(r"\b(?:explain|why|root cause|rca)\b", text_l):
        cites = "\n- ".join(_citations_for(card))
        suggestions = ([f"approve {scenario_id}", f"reject {scenario_id}"]
                       if card.state == "Requires Approval" else [])
        return _chat_reply(
            f"Root-cause hypothesis for {scenario_id}:\n\n{card.hypothesis}\n\n"
            f"State: {card.state}. Confidence: {card.confidence}.\n\nDerived from:\n- {cites}",
            scenario_id=scenario_id, suggestions=suggestions + [f"reprobe {scenario_id}", "list"],
        )
    return _chat_reply(
        f"{scenario_id} is currently '{card.state}'.\n\n"
        "Use an explain suggestion for the root-cause trace. Actions must start with "
        "'approve', 'reject', or 'reprobe' followed by one incident reference.",
        scenario_id=scenario_id,
    )


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
