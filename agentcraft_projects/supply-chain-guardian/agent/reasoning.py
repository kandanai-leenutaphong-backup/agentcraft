"""Correlation/reasoning agent for supply-chain-guardian.

Deterministic rule-based reasoning (no live LLM call configured yet) that composes evidence
from the four IQ sources into a root-cause hypothesis, business-impact estimate and mitigation
recommendation, then applies the mandatory approval-gate state machine. Live Web IQ is called
when a network probe is permitted; Fabric IQ, and Foundry IQ / Work IQ (until real access is
granted), use their explicitly-labelled mock fallbacks per the constitution.

State machine: Monitoring -> Issue Detected -> Investigating -> Recommendation Ready ->
Requires Approval -> Approved -> Executed, with Rejected as an alternate terminal state.
Nothing in this module executes a consequential action; `apply_decision` is the only function
that can move a card past Requires Approval, and only given an explicit external decision.
"""
from __future__ import annotations

import json
import os
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
DATASET = ROOT / "dataset"

STATES = [
    "Monitoring",
    "Issue Detected",
    "Investigating",
    "Recommendation Ready",
    "Requires Approval",
    "Approved",
    "Executed",
    "Rejected",
]

CONSEQUENTIAL_ACTIONS = {
    "expedite_material",
    "notify_production_planning",
    "notify_customer",
}


@dataclass
class Evidence:
    fabric_iq: dict
    web_iq: Optional[dict]
    foundry_iq: list
    work_iq: Optional[dict]
    web_iq_live: bool
    foundry_iq_live: bool
    work_iq_live: bool
    fabric_iq_live: bool = False
    foundry_iq_live_probe: Optional[dict] = None
    work_iq_live_probe: Optional[dict] = None
    fabric_iq_live_probe: Optional[dict] = None


@dataclass
class IncidentCard:
    scenario_id: str
    disruption_trigger: str
    blast_radius: dict
    evidence: Evidence
    hypothesis: str
    business_impact: str
    recommended_mitigation: str
    confidence: float
    evidence_completeness: float
    consequential_actions: list
    state: str = "Monitoring"
    execution_result: Optional[str] = None
    email_receipt: Optional[dict] = None
    evidence_refreshed_at: Optional[str] = None
    trace: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "scenario_id": self.scenario_id,
            "disruption_trigger": self.disruption_trigger,
            "blast_radius": self.blast_radius,
            "fabric_iq_evidence": {"mocked": not self.evidence.fabric_iq_live, "data": self.evidence.fabric_iq,
                                    "live_probe": self.evidence.fabric_iq_live_probe},
            "web_iq_evidence": {"mocked": not self.evidence.web_iq_live, "data": self.evidence.web_iq},
            "foundry_iq_evidence": {"mocked": not self.evidence.foundry_iq_live, "data": self.evidence.foundry_iq,
                                     "live_probe": self.evidence.foundry_iq_live_probe},
            "work_iq_evidence": {"mocked": not self.evidence.work_iq_live, "data": self.evidence.work_iq,
                                  "live_probe": self.evidence.work_iq_live_probe},
            "root_cause_hypothesis": self.hypothesis,
            "estimated_business_impact": self.business_impact,
            "recommended_mitigation": self.recommended_mitigation,
            "confidence": self.confidence,
            "evidence_completeness": self.evidence_completeness,
            "consequential_actions": self.consequential_actions,
            "approval_state": self.state,
            "execution_result": self.execution_result,
            "email_receipt": self.email_receipt,
            "evidence_refreshed_at": self.evidence_refreshed_at,
            "trace": self.trace,
        }


def _load(name: str):
    with open(DATASET / name, encoding="utf-8") as f:
        return json.load(f)


FOUNDRY_IQ_ENDPOINT = "https://aiworkshop-search-rmsgmwk472oxi.search.windows.net"
FOUNDRY_IQ_INDEX = "all-iq-demo-policies"
SEARCH_SCOPE = "https://search.azure.com/user_impersonation offline_access"
FABRIC_SCOPE = "https://api.fabric.microsoft.com/Workspace.Read.All https://api.fabric.microsoft.com/Item.ReadWrite.All offline_access"
FABRIC_WORKSPACE_ID = "50afe17c-5fe1-4a9f-89b3-f3298f741c9c"
FABRIC_LAKEHOUSE_ID = "af6a52e2-0878-4a06-a0ce-94b9b9dc1e58"
_RETRY_DELAY_SECONDS = 0.5


def _is_retryable_probe_error(exc: Exception) -> bool:
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code == 429 or 500 <= exc.code < 600
    return isinstance(exc, (urllib.error.URLError, TimeoutError, socket.timeout, ConnectionError))


def _load_json_with_single_retry(req: urllib.request.Request, timeout: int) -> dict:
    last_error = None
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read())
        except Exception as exc:
            last_error = exc
            if attempt == 1 or not _is_retryable_probe_error(exc):
                raise
            time.sleep(_RETRY_DELAY_SECONDS)
    raise last_error  # pragma: no cover


def live_foundry_iq_probe(query: str) -> Optional[dict]:
    """Live, read-only query against the real Foundry IQ (Azure AI Search) index, Entra
    ID-authenticated. Returns {"live": False, ...} on auth/network failure so callers always
    have a safe fallback path. The connection is real; the index observed 2026-09-25 held only generic
    corporate policy docs (Expense/Vendor Contract/Incident Response), not supply-chain content,
    so this is surfaced as supplementary live evidence, not the mitigation's grounding source.
    Always returns the exact REST request issued (method/url/body) and the raw response, so
    the UI can show precisely what was searched for and what came back. Retries once after
    0.5s for transient timeout/connection/429/5xx failures only."""
    try:
        from agent.iq_auth import get_token, auth_header
    except ImportError:
        from iq_auth import get_token, auth_header  # type: ignore
    search_url = f"{FOUNDRY_IQ_ENDPOINT}/indexes('{FOUNDRY_IQ_INDEX}')/docs/search?api-version=2024-07-01"
    request_meta = {"method": "POST", "url": search_url, "body": {"search": query, "top": 3}}
    token = get_token(SEARCH_SCOPE)
    if not token:
        return {"live": False, "error": "no token (not configured or scope not consented)", "request": request_meta}
    try:
        headers = auth_header(token)
        headers["content-type"] = "application/json"
        req = urllib.request.Request(
            search_url,
            data=json.dumps({"search": query, "top": 3}).encode(),
            headers=headers,
            method="POST",
        )
        body = _load_json_with_single_retry(req, timeout=20)
        docs = [{"id": d.get("id"), "title": d.get("title"), "category": d.get("category")}
                for d in body.get("value", [])]
        return {"live": True, "index": FOUNDRY_IQ_INDEX, "query": query, "matches": docs,
                "relevance_note": "Index currently holds generic corporate policies, not supply-chain-specific content.",
                "request": request_meta, "raw_response": body}
    except Exception as exc:  # network/auth failure -> caller falls back to mock only
        return {"live": False, "error": str(exc)[:200], "request": request_meta}


def live_fabric_iq_probe() -> dict:
    """Live, read-only check against the real Fabric IQ workspace/Lakehouse (MCAPS tenant).
    Lists actual items and, once the load_ontology_into_lakehouse notebook has been run,
    real Delta table data becomes readable. Falls back to {"live": False} on any auth/network
    failure so callers always have a safe path. Always returns the exact Fabric REST request
    issued (method/url) and the raw response, so the UI can show precisely which workspace
    call was made and what it returned. Retries once after 0.5s for transient
    timeout/connection/429/5xx failures only."""
    try:
        from agent.iq_auth import get_token, auth_header
    except ImportError:
        from iq_auth import get_token, auth_header  # type: ignore
    items_url = f"https://api.fabric.microsoft.com/v1/workspaces/{FABRIC_WORKSPACE_ID}/items"
    request_meta = {"method": "GET", "url": items_url}
    token = get_token(FABRIC_SCOPE)
    if not token:
        return {"live": False, "error": "no token (not configured or scope not consented)", "request": request_meta}
    try:
        req = urllib.request.Request(items_url, headers=auth_header(token))
        body = _load_json_with_single_retry(req, timeout=20)
        items = [{"id": i.get("id"), "type": i.get("type"), "name": i.get("displayName")}
                 for i in body.get("value", [])]
        return {"live": True, "workspace_id": FABRIC_WORKSPACE_ID, "items": items,
                "note": "Real Fabric workspace/Lakehouse/Notebook; Delta tables populate once "
                        "the notebook is run (one-time manual step, no run-notebook API available).",
                "request": request_meta, "raw_response": body}
    except Exception as exc:
        return {"live": False, "error": str(exc)[:200], "request": request_meta}


def _foundry_iq_lookup(policy_ids: list) -> list:
    # Mocked policy library remains the grounding source for mitigation citations: the real
    # index (queried live, see live_foundry_iq_probe) does not hold supply-chain-specific
    # content as of 2026-09-25. Explicitly labelled as mocked.
    library = {p["id"]: p for p in _load("foundry_iq_policy_library.mock.json")}
    return [library[pid] for pid in policy_ids if pid in library]


def _work_iq_lookup(scenario_id: str, fallback: dict) -> Optional[dict]:
    # Stakeholder/org-context fields remain the mocked, explicitly-labelled fallback (synthetic
    # labels only, per constitution). See work_iq_live_probe on the card for live mail evidence.
    return fallback


def live_work_iq_probe() -> Optional[dict]:
    """Live, read-only probe against the real Work IQ (Microsoft Graph mail), delegated
    consent via device-code sign-in (no client secret). Returns None if not configured so
    callers always have a safe mocked fallback path."""
    try:
        from agent.work_iq import live_recent_mail
    except ImportError:
        from work_iq import live_recent_mail  # type: ignore
    result = live_recent_mail(top=5)
    return result


def _approved_alternate_supplier_ids() -> list:
    suppliers = _load("ontology.json")["suppliers"]
    return [s["id"] for s in suppliers if s.get("approved_alternate")]


def _ts() -> str:
    import datetime
    return datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"


def simulate_new_disruption() -> dict:
    """Builds a fresh, on-demand disruption scenario by deriving a real blast radius from the
    ontology graph (shipment -> material -> plants -> production orders -> skus -> customers),
    rather than replaying one of the four fixed canned scenarios. Demonstrates the reasoning
    engine operating on novel input, not just pre-scripted cases."""
    import random

    onto = _load("ontology.json")
    shipment = random.choice(onto["shipments"])
    material_id = shipment["material_id"]
    supplier_id = shipment["supplier_id"]
    supplier = next(s for s in onto["suppliers"] if s["id"] == supplier_id)

    affected_plants = [p for p in onto["plants"] if material_id in p.get("material_ids", [])]
    plant_ids = [p["id"] for p in affected_plants]
    affected_pos = [po for po in onto["production_orders"] if po["plant_id"] in plant_ids]
    sku_ids = sorted({po["sku_id"] for po in affected_pos})
    affected_skus = [s for s in onto["skus"] if s["id"] in sku_ids]
    customer_ids = sorted({cid for s in affected_skus for cid in s.get("customer_ids", [])})
    strategic = any(c["tier"] == "strategic" for c in onto["customers"] if c["id"] in customer_ids)
    min_days_on_hand = min([p["inventory_days_on_hand"] for p in affected_plants], default=999)
    eta_days_late = random.randint(3, 12)

    alt_supplier_ids = [s["id"] for s in onto["suppliers"] if s.get("approved_alternate") and s["id"] != supplier_id]
    foundry_ids = ["POLICY-CONTINUITY"]
    if alt_supplier_ids:
        foundry_ids.append("POLICY-ALT-SUPPLIER")
    if eta_days_late >= 7:
        foundry_ids.append("POLICY-EXPEDITE")

    scenario_id = f"sim-{shipment['id']}-{int(random.random() * 100000):05d}"
    return {
        "id": scenario_id,
        "kind": "simulated_live_disruption",
        "trigger": f"Live simulation: shipment {shipment['id']} ({material_id}) delayed "
                   f"{eta_days_late} days from {supplier['name']} ({supplier['region']}).",
        "blast_radius": {
            "shipment_id": shipment["id"],
            "material_id": material_id,
            "affected_plants": plant_ids,
            "affected_production_orders": [po["id"] for po in affected_pos],
            "affected_skus": sku_ids,
            "affected_customers": customer_ids,
            "strategic_customer_impact": strategic,
            "min_inventory_days_on_hand": min_days_on_hand,
        },
        "foundry_iq_evidence": foundry_ids,
        "work_iq_evidence": {
            "responsible_stakeholders": ["Production Planning Lead", "Procurement Manager"],
            "recent_notes": [f"Auto-generated simulation: no prior ops note on record for supplier {supplier['name']}."],
        },
        "web_iq_evidence": None,
        "expected_recommendation_mentions": alt_supplier_ids + plant_ids,
        "expected_requires_approval": True,
    }


def build_incident(scenario: dict) -> IncidentCard:
    trace = []

    def log(source: str, action: str, detail: str) -> None:
        trace.append({"ts": _ts(), "source": source, "action": action, "detail": detail})

    blast_radius = scenario["blast_radius"]
    log("Fabric IQ", "read_business_kpi", f"Blast-radius snapshot for shipment {blast_radius['shipment_id']} / "
        f"material {blast_radius['material_id']}: {len(blast_radius['affected_plants'])} plant(s), "
        f"{len(blast_radius['affected_skus'])} SKU(s) affected.")

    foundry_evidence = _foundry_iq_lookup(scenario["foundry_iq_evidence"])
    log("Foundry IQ", "lookup_policy_library", f"Matched {len(foundry_evidence)} governed policy doc(s) "
        f"({', '.join(p['id'] for p in foundry_evidence) or 'none'}) from the approved policy library.")

    work_evidence = _work_iq_lookup(scenario["id"], scenario["work_iq_evidence"])
    log("Work IQ", "lookup_org_context", "Retrieved organizational/collaboration context for this account "
        f"({'found' if work_evidence else 'none found'}).")

    try:
        from agent.web_iq import live_web_search
    except ImportError:
        from web_iq import live_web_search  # type: ignore
    web_query = f"{blast_radius['material_id']} supplier shipment delay {blast_radius.get('shipment_id', '')}".strip()
    log("Web IQ", "live_search_call", f"Calling live web search: query=\"{web_query}\"")
    live_web = live_web_search(web_query)
    if live_web.get("mocked"):
        # Live call unavailable/unconfigured/no-results: fall back to the scenario's canned
        # snapshot but say so explicitly rather than presenting it as live.
        web_evidence = dict(scenario["web_iq_evidence"] or {})
        web_evidence["live_attempt_failed_reason"] = live_web.get("reason", "unknown")
        web_evidence["request"] = live_web.get("request")  # keep the attempted request visible even on fallback
        web_iq_live = False
        log("Web IQ", "live_search_result", f"Live call did not return usable results "
            f"({live_web.get('reason', 'unknown')}); using labelled fallback snapshot.")
    else:
        web_evidence = live_web
        web_iq_live = True
        log("Web IQ", "live_search_result", f"Live call returned {live_web['result_count']} result(s); "
            f"top: \"{live_web['headline']}\"")

    kind = scenario["kind"]
    if kind in ("clear_disruption", "cascading_disruption"):
        alt_suppliers = [p for p in foundry_evidence if p["id"] == "POLICY-ALT-SUPPLIER"]
        alt_supplier_ids = _approved_alternate_supplier_ids() if alt_suppliers else []
        hypothesis = (
            f"Shipment {blast_radius['shipment_id']} delay for material {blast_radius['material_id']} "
            f"is disrupting production at {', '.join(blast_radius['affected_plants'])}"
            + (f"; external signal indicates the underlying logistics issue may persist ({web_evidence['headline']})."
               if web_evidence else ".")
        )
        mitigation = (
            f"Expedite material from approved alternate supplier(s) {', '.join(alt_supplier_ids)} "
            f"and notify Production Planning at {', '.join(blast_radius['affected_plants'])}."
            if alt_suppliers else
            "No approved alternate supplier on file; escalate to Procurement for manual sourcing decision."
        )
        actions = ["expedite_material", "notify_production_planning"] if alt_suppliers else ["notify_production_planning"]
        if blast_radius.get("strategic_customer_impact"):
            actions.append("notify_customer")
        confidence = 0.9 if (foundry_evidence and web_evidence) else 0.65
        completeness = sum(bool(x) for x in (blast_radius, web_evidence, foundry_evidence, work_evidence)) / 4
        impact = (
            f"{len(blast_radius['affected_production_orders'])} production order(s), "
            f"{len(blast_radius['affected_skus'])} SKU(s), "
            f"{len(blast_radius['affected_customers'])} customer(s) at risk"
            + (" (includes strategic-tier customer)" if blast_radius.get("strategic_customer_impact") else "")
        )
    else:  # no_action_needed / insufficient_evidence
        hypothesis = (
            f"Shipment {blast_radius['shipment_id']} shows no confirmed disruption signal "
            "requiring action at this time."
        )
        mitigation = "No mitigation recommended; continue monitoring."
        actions = []
        confidence = 0.55
        completeness = sum(bool(x) for x in (blast_radius, web_evidence, foundry_evidence, work_evidence)) / 4
        impact = "No material production/customer risk identified at current inventory levels."

    log("Agent", "correlate_evidence", f"Correlated Fabric+Foundry+Work+Web evidence into hypothesis "
        f"(confidence={confidence}, evidence_completeness={round(completeness, 2)}).")

    log("Foundry IQ", "live_index_call", "Calling live Azure AI Search index (real Entra-authenticated call).")
    live_probe = live_foundry_iq_probe(f"{blast_radius['material_id']} supplier procurement continuity")
    if live_probe and live_probe.get("live"):
        log("Foundry IQ", "live_index_result", f"{len(live_probe['matches'])} match(es) returned from real index.")
    else:
        log("Foundry IQ", "live_index_result", f"Live call did not succeed: {(live_probe or {}).get('error')}")

    log("Work IQ", "live_mail_call", "Calling live Microsoft Graph mail read (real delegated token).")
    work_live_probe = live_work_iq_probe()
    if work_live_probe and work_live_probe.get("mocked") is False:
        log("Work IQ", "live_mail_result", f"{len(work_live_probe['messages'])} live inbox message(s) read.")
    else:
        log("Work IQ", "live_mail_result", f"Live call did not succeed: {(work_live_probe or {}).get('reason')}")

    log("Fabric IQ", "live_workspace_call", "Calling live Fabric REST API against the real MCAPS workspace.")
    fabric_live_probe = live_fabric_iq_probe()
    if fabric_live_probe and fabric_live_probe.get("live"):
        log("Fabric IQ", "live_workspace_result", f"{len(fabric_live_probe['items'])} real item(s) found in workspace.")
    else:
        log("Fabric IQ", "live_workspace_result", f"Live call did not succeed: {(fabric_live_probe or {}).get('error')}")

    evidence = Evidence(
        fabric_iq=blast_radius,
        web_iq=web_evidence,
        foundry_iq=foundry_evidence,
        work_iq=work_evidence,
        web_iq_live=web_iq_live,
        foundry_iq_live=bool(live_probe and live_probe.get("live")),
        work_iq_live=bool(work_live_probe and work_live_probe.get("mocked") is False),
        fabric_iq_live=bool(fabric_live_probe and fabric_live_probe.get("live")),
        foundry_iq_live_probe=live_probe,
        work_iq_live_probe=work_live_probe,
        fabric_iq_live_probe=fabric_live_probe,
    )

    card = IncidentCard(
        scenario_id=scenario["id"],
        disruption_trigger=scenario["trigger"],
        blast_radius=blast_radius,
        evidence=evidence,
        hypothesis=hypothesis,
        business_impact=impact,
        recommended_mitigation=mitigation,
        confidence=confidence,
        evidence_completeness=round(completeness, 2),
        consequential_actions=actions,
        trace=trace,
    )

    # Deterministic state progression through investigation; halts before any consequential action.
    card.state = "Issue Detected"
    card.state = "Investigating"
    card.state = "Recommendation Ready"
    if actions:
        card.state = "Requires Approval"
    else:
        card.state = "Monitoring"
    import datetime
    card.evidence_refreshed_at = datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    return card


def refresh_evidence(card: IncidentCard, scenario: dict) -> IncidentCard:
    """Re-run all four live IQ probes for an already-built card, in place, without touching
    its approval state or decision history. This is what makes the agent 'continuously
    monitor' rather than snapshot evidence once at container startup: each call hits Web IQ,
    Work IQ, Foundry IQ and Fabric IQ again and updates `evidence_refreshed_at`. Trace entries
    accumulate (most recent last) so the portal can show a running investigation history,
    capped at the most recent 40 entries per incident."""
    fresh = build_incident(scenario)
    card.evidence = fresh.evidence
    card.evidence_refreshed_at = fresh.evidence_refreshed_at
    card.trace = (card.trace + fresh.trace)[-40:]
    return card


def apply_decision(card: IncidentCard, decision: str) -> IncidentCard:
    """The only function allowed to move a card past Requires Approval. `decision` must be an
    explicit external signal ('approved' or 'rejected'); this module never calls it itself."""
    if card.state != "Requires Approval":
        return card
    card.trace.append({"ts": _ts(), "source": "Human", "action": "decision",
                        "detail": f"Reviewer decision received: {decision}"})
    if decision == "approved":
        card.state = "Approved"
        card.state = "Executed"
        card.execution_result = f"Executed (simulated): {card.recommended_mitigation}"
        if any(a.startswith("notify") for a in card.consequential_actions):
            try:
                from agent.work_iq import send_escalation_email
            except ImportError:
                from work_iq import send_escalation_email  # type: ignore
            subject = f"[Supply Chain Guardian] {card.scenario_id}: mitigation approved"
            body = (
                f"Trigger: {card.disruption_trigger}\n\n"
                f"Root-cause hypothesis: {card.hypothesis}\n\n"
                f"Business impact: {card.business_impact}\n\n"
                f"Approved mitigation: {card.recommended_mitigation}\n\n"
                "This is a live notification sent by the agent via Microsoft Graph (Work IQ) "
                "after explicit human approval. No action was auto-executed without approval."
            )
            card.trace.append({"ts": _ts(), "source": "Work IQ", "action": "send_email",
                                "detail": f"Sending live escalation email: \"{subject}\""})
            card.email_receipt = send_escalation_email(card.scenario_id, subject, body)
            card.trace.append({"ts": _ts(), "source": "Work IQ", "action": "send_email_result",
                                "detail": ("Live email sent." if card.email_receipt.get("sent")
                                           else f"Send failed: {card.email_receipt.get('reason') or card.email_receipt.get('error')}")})
    elif decision == "rejected":
        card.state = "Rejected"
        card.execution_result = "Rejected by reviewer; no action taken."
    return card


def run_all() -> list:
    scenarios = _load("scenarios.json")
    return [build_incident(s) for s in scenarios]


if __name__ == "__main__":
    cards = run_all()
    print(json.dumps([c.to_dict() for c in cards], indent=2))
