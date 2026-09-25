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
    work_iq_org_probe: Optional[dict] = None


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
    hypothesis_source: str = "rule_based"
    rule_based_hypothesis: Optional[str] = None

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
                                  "live_probe": self.evidence.work_iq_live_probe,
                                  "org_probe": self.evidence.work_iq_org_probe},
            "root_cause_hypothesis": self.hypothesis,
            "hypothesis_source": self.hypothesis_source,
            "rule_based_hypothesis": self.rule_based_hypothesis,
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


FOUNDRY_AGENT_PROJECT_ENDPOINT = os.environ.get("FOUNDRY_PROJECT_ENDPOINT")
FOUNDRY_AGENT_NAME = os.environ.get("FOUNDRY_AGENT_NAME", "supply-chain-rca-agent")


def _extract_responses_text(body: dict) -> str:
    """Pull the assistant's plain-text answer out of an OpenAI Responses API payload
    (`{"output": [{"type": "message", "content": [{"type": "output_text", "text": ...}]}]}`).
    Returns "" if the shape doesn't match, so callers can treat that as a failed call."""
    chunks = []
    for item in body.get("output", []) or []:
        if item.get("type") != "message":
            continue
        for part in item.get("content", []) or []:
            if part.get("type") in ("output_text", "text") and part.get("text"):
                chunks.append(part["text"])
    return "\n".join(chunks).strip()


def live_foundry_agent_rca(prompt: str) -> dict:
    """Invoke the live, tool-calling Foundry-hosted RCA agent (Microsoft Agent Framework;
    see foundry-agent/supply-chain-rca-agent) with a plain-text prompt describing the
    disruption. The agent independently calls the same live Fabric/Foundry/Work/Web IQ
    tools this app exposes at /tools/* and returns a genuine LLM-reasoned root-cause
    hypothesis, blast radius, and cited mitigation - no scenario JSON or rule-based string
    templates involved. Returns {"mocked": True, ...} on any auth/config/network/quota
    failure so callers always have a safe deterministic fallback path; never raises."""
    try:
        from agent.iq_auth import get_managed_identity_token
    except ImportError:
        from iq_auth import get_managed_identity_token  # type: ignore
    if not FOUNDRY_AGENT_PROJECT_ENDPOINT:
        return {"mocked": True, "reason": "FOUNDRY_PROJECT_ENDPOINT not configured"}
    # Foundry's hosted-agent "responses" data plane requires the https://ai.azure.com audience
    # specifically (confirmed empirically: https://cognitiveservices.azure.com tokens get a
    # bare 403 even for the resource owner) - not the classic Cognitive Services audience used
    # by the other IQ probes in this module.
    token = get_managed_identity_token("https://ai.azure.com")
    if not token:
        return {"mocked": True, "reason": "no managed-identity token for the Foundry project "
                                           "(agent invocation is managed-identity only, no delegated fallback)"}
    url = (f"{FOUNDRY_AGENT_PROJECT_ENDPOINT}/agents/{FOUNDRY_AGENT_NAME}/endpoint/"
           f"protocols/openai/responses?api-version=v1")
    request_meta = {"method": "POST", "url": url, "body": {"input": prompt}}
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps({"input": prompt, "store": False}).encode(),
            headers={"Authorization": f"Bearer {token}", "content-type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=90) as resp:
            body = json.loads(resp.read())
    except Exception as exc:
        return {"mocked": True, "reason": f"live agent call failed: {exc}"[:300], "request": request_meta}

    text = _extract_responses_text(body)
    if not text:
        return {"mocked": True, "reason": "agent returned no text output", "request": request_meta,
                 "raw_response": body}
    return {"mocked": False, "text": text, "auth_source": "managed_identity", "request": request_meta,
             "raw_response": body}


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
        from agent.iq_auth import get_live_token, auth_header
    except ImportError:
        from iq_auth import get_live_token, auth_header  # type: ignore
    search_url = f"{FOUNDRY_IQ_ENDPOINT}/indexes('{FOUNDRY_IQ_INDEX}')/docs/search?api-version=2024-07-01"
    request_meta = {"method": "POST", "url": search_url, "body": {"search": query, "top": 3}}
    # AI Search only accepts "https://search.azure.com" as a managed-identity token audience
    # (no path suffix); the delegated fallback still needs the full scope string.
    token, token_source = get_live_token("https://search.azure.com", SEARCH_SCOPE)
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
                "auth_source": token_source,
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
        from agent.iq_auth import get_live_token, auth_header
    except ImportError:
        from iq_auth import get_live_token, auth_header  # type: ignore
    items_url = f"https://api.fabric.microsoft.com/v1/workspaces/{FABRIC_WORKSPACE_ID}/items"
    request_meta = {"method": "GET", "url": items_url}
    token, token_source = get_live_token("https://api.fabric.microsoft.com", FABRIC_SCOPE)
    if not token:
        return {"live": False, "error": "no token (not configured or scope not consented)", "request": request_meta}
    try:
        req = urllib.request.Request(items_url, headers=auth_header(token))
        body = _load_json_with_single_retry(req, timeout=20)
        items = [{"id": i.get("id"), "type": i.get("type"), "name": i.get("displayName")}
                 for i in body.get("value", [])]
        result = {"live": True, "workspace_id": FABRIC_WORKSPACE_ID, "items": items,
                  "auth_source": token_source,
                  "note": "Real Fabric workspace/Lakehouse/Notebook; Delta tables populate once "
                          "the notebook is run (one-time step, triggerable in-app via "
                          "'Load real Lakehouse data' after granting the Execute scope).",
                  "request": request_meta, "raw_response": body}
        # Second real call: list the actual Delta tables inside the Lakehouse item, so the
        # UI shows genuine business-data table names (e.g. shipments/suppliers) rather than
        # just workspace item metadata, once the load_ontology_into_lakehouse notebook has run.
        lakehouse = next((i for i in items if i.get("type") == "Lakehouse"), None)
        if lakehouse and lakehouse.get("id"):
            tables_url = (f"https://api.fabric.microsoft.com/v1/workspaces/{FABRIC_WORKSPACE_ID}"
                          f"/lakehouses/{lakehouse['id']}/tables")
            tables_request_meta = {"method": "GET", "url": tables_url}
            try:
                tables_req = urllib.request.Request(tables_url, headers=auth_header(token))
                tables_body = _load_json_with_single_retry(tables_req, timeout=20)
                tables = [{"name": t.get("name"), "format": t.get("format")}
                          for t in tables_body.get("data", [])]
                result["lakehouse_tables"] = tables
                result["lakehouse_tables_request"] = tables_request_meta
                result["lakehouse_tables_raw_response"] = tables_body
            except Exception as tables_exc:
                # Non-fatal: keep the workspace-items result live, just note the tables call
                # could not be completed (e.g. notebook hasn't been run yet, no tables exist).
                result["lakehouse_tables_error"] = str(tables_exc)[:200]
                result["lakehouse_tables_request"] = tables_request_meta
        return result
    except Exception as exc:
        return {"live": False, "error": str(exc)[:200], "request": request_meta}


FABRIC_NOTEBOOK_ID = "7398c354-4365-427b-9b09-6404d298a186"  # load_ontology_into_lakehouse


def run_fabric_notebook() -> dict:
    """Trigger a real, on-demand run of the load_ontology_into_lakehouse notebook via the
    Fabric REST Job Scheduler API. Requires the Item.Execute.All delegated scope (in
    addition to Workspace.Read.All/Item.ReadWrite.All), which must be granted via a fresh
    in-app device-code consent -- if the cached token predates that scope, Fabric returns
    403 InsufficientScopes and the caller should prompt the user to reconnect. Returns a
    dict with the job instance id/location (for polling) or an error; never raises."""
    try:
        from agent.iq_auth import get_live_token, auth_header
    except ImportError:
        from iq_auth import get_live_token, auth_header  # type: ignore
    url = (f"https://api.fabric.microsoft.com/v1/workspaces/{FABRIC_WORKSPACE_ID}"
           f"/items/{FABRIC_NOTEBOOK_ID}/jobs/instances?jobType=RunNotebook")
    request_meta = {"method": "POST", "url": url, "body": {}}
    token, token_source = get_live_token("https://api.fabric.microsoft.com", FABRIC_SCOPE)
    if not token:
        return {"started": False, "error": "no token (not configured or scope not consented)",
                "request": request_meta}
    headers = auth_header(token)
    headers["content-type"] = "application/json"
    req = urllib.request.Request(url, data=b"{}", headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            location = resp.headers.get("Location")
            return {"started": True, "status_code": resp.status, "job_status_url": location,
                    "auth_source": token_source, "request": request_meta}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")[:500]
        needs_reconsent = exc.code == 403 and "InsufficientScopes" in body
        return {"started": False, "error": f"HTTP {exc.code}: {body}",
                "needs_reconsent": needs_reconsent, "request": request_meta}
    except Exception as exc:
        return {"started": False, "error": str(exc)[:200], "request": request_meta}


def poll_fabric_notebook_job(job_status_url: str) -> dict:
    """Single non-blocking poll of a previously started Fabric notebook job's status URL.
    Returns the raw job status payload (status is one of NotStarted/Running/Completed/
    Failed/Deduped/Cancelled per the Fabric Job Scheduler API) or an error dict."""
    try:
        from agent.iq_auth import get_live_token, auth_header
    except ImportError:
        from iq_auth import get_live_token, auth_header  # type: ignore
    token, _ = get_live_token("https://api.fabric.microsoft.com", FABRIC_SCOPE)
    if not token:
        return {"error": "no token (not configured or scope not consented)"}
    req = urllib.request.Request(job_status_url, headers=auth_header(token))
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except Exception as exc:
        return {"error": str(exc)[:200]}


def _foundry_iq_lookup(policy_ids: list) -> list:
    # Mocked policy library remains the grounding source for mitigation citations: the real
    # index (queried live, see live_foundry_iq_probe) does not hold supply-chain-specific
    # content as of 2026-09-25. Explicitly labelled as mocked.
    library = {p["id"]: p for p in _load("foundry_iq_policy_library.mock.json")}
    return [library[pid] for pid in policy_ids if pid in library]


def _work_iq_lookup(scenario_id: str, fallback: dict) -> tuple:
    """Real organizational/collaboration context via Microsoft Graph (manager + direct
    reports for the signed-in Work IQ account), replacing the previously-mocked stakeholder
    snapshot. Falls back to the scenario's mocked snapshot only if the live call is not
    configured or fails. Returns (data, live: bool, live_probe: dict|None)."""
    try:
        from agent.work_iq import live_org_context
    except ImportError:
        from work_iq import live_org_context  # type: ignore
    probe = live_org_context()
    if probe and probe.get("mocked") is False:
        # Only expose fields Microsoft Graph actually returned (manager/direct reports).
        # The scenario's synthetic "recent ops notes" have no live Graph equivalent, so they
        # are intentionally omitted here rather than mixed into a "live" result.
        data = {
            "manager": probe.get("manager"),
            "direct_reports": probe.get("direct_reports"),
            "found": probe.get("found"),
        }
        return data, True, probe
    return fallback, False, probe


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


def build_incident(scenario: dict, include_live_agent_rca: bool = False) -> IncidentCard:
    """Build an incident card from a scenario. `include_live_agent_rca` is opt-in (default
    False) so process-startup card population stays fast and doesn't burn LLM quota; the
    live Foundry-hosted RCA agent call is only made from an explicit user action
    (refresh_evidence / /incidents/{id}/reprobe, or a freshly-simulated disruption)."""
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

    work_evidence, work_org_live, work_org_probe = _work_iq_lookup(scenario["id"], scenario["work_iq_evidence"])
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

    hypothesis_source = "rule_based"
    rule_based_hypothesis = hypothesis
    if include_live_agent_rca and kind in ("clear_disruption", "cascading_disruption"):
        agent_prompt = (
            f"Disruption trigger: {scenario['trigger']}\n"
            f"Shipment: {blast_radius.get('shipment_id')}, Material: {blast_radius.get('material_id')}\n"
            f"Plants on file per the ontology snapshot: {', '.join(blast_radius.get('affected_plants', []))}\n\n"
            "Investigate this disruption using your live tools (Fabric, policy search, org "
            "context, mail, web) and give me a root-cause hypothesis, business impact / blast "
            "radius, a cited mitigation, and your confidence."
        )
        log("Agent", "foundry_agent_rca_call", "Calling the live Foundry-hosted RCA agent "
            "(Microsoft Agent Framework, managed-identity authenticated) for real LLM reasoning "
            "grounded in live tool calls.")
        agent_result = live_foundry_agent_rca(agent_prompt)
        if not agent_result.get("mocked"):
            hypothesis = agent_result["text"]
            hypothesis_source = "foundry_agent"
            log("Agent", "foundry_agent_rca_result", "Live agent returned a tool-grounded RCA "
                "narrative; replacing the rule-based template as the incident's hypothesis.")
        else:
            log("Agent", "foundry_agent_rca_result", f"Live agent call unavailable "
                f"({agent_result.get('reason')}); keeping the rule-based hypothesis, labelled as such.")

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
        work_iq_live=bool(work_live_probe and work_live_probe.get("mocked") is False) or work_org_live,
        fabric_iq_live=bool(fabric_live_probe and fabric_live_probe.get("live")),
        foundry_iq_live_probe=live_probe,
        work_iq_live_probe=work_live_probe,
        fabric_iq_live_probe=fabric_live_probe,
        work_iq_org_probe=work_org_probe,
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
        hypothesis_source=hypothesis_source,
        rule_based_hypothesis=rule_based_hypothesis,
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
    capped at the most recent 40 entries per incident. This is also the one path (an explicit
    user 'reprobe') that invokes the live Foundry-hosted RCA agent, refreshing the incident's
    hypothesis/impact/mitigation narrative with a real LLM tool-calling pass rather than the
    rule-based template."""
    fresh = build_incident(scenario, include_live_agent_rca=True)
    card.evidence = fresh.evidence
    card.evidence_refreshed_at = fresh.evidence_refreshed_at
    card.trace = (card.trace + fresh.trace)[-40:]
    card.hypothesis = fresh.hypothesis
    card.hypothesis_source = fresh.hypothesis_source
    card.rule_based_hypothesis = fresh.rule_based_hypothesis
    card.business_impact = fresh.business_impact
    card.recommended_mitigation = fresh.recommended_mitigation
    card.confidence = fresh.confidence
    card.evidence_completeness = fresh.evidence_completeness
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
