"""Idempotent live prerequisites G1 + G6 for the agent-package E2E (spec 20260924_FOUNDRY_AGENT_PACKAGE_E2E.md).

G1: `AcrPull` for the Foundry project managed identity, scoped to registry `agentcraftdev67255` only.
G6: model deployment `agentcraft-pkg-e2e-optimizer-gpt54`, gpt-5.4 `2026-03-05`, GlobalStandard 100
    (same SKU/capacity/format as proven `agentcraft-iris-optimizer-gpt54`,
    testbeds/foundry-agent optimization/deploy/evidence/optimizer-model-intent.json).

Run from repository root with the existing interpreter and an existing `az login`:
    python3 -B agentcraft_projects/foundry-agent-package-e2e-20260924/records/prereqs/prereqs.py
Read-before-write: a resource already present with the expected properties is not touched; a present
resource with different properties is refused, never modified. `<gate>-intent.json` is written before each
mutation; an intent whose resource is absent on rerun is unresolved and refused. No deletion, no other role.
Writes one receipt `<UTC>-prereqs.json` beside this script (exclusive create, read-back).
"""

import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path.insert(0, str(REPO / "libraries/foundry-ops/src"))

from foundry_ops.build import az_json  # noqa: E402
from foundry_ops.core import EvidenceLedger, error_summary, sanitize, sha256_file, utc_stamp  # noqa: E402

TARGET_PATH = REPO / "testbeds/foundry-hosted-agents/deploy/env/target.json"
PROVEN_PATH = REPO / "testbeds/foundry-agent optimization/deploy/evidence/optimizer-model-intent.json"
PRINCIPAL = "d9cd20e0-1a11-4046-9469-1057ca18396e"
ROLE = "AcrPull"
DEPLOYMENT = {"name": "agentcraft-pkg-e2e-optimizer-gpt54",
              "model": {"format": "OpenAI", "name": "gpt-5.4", "version": "2026-03-05"},
              "sku": "GlobalStandard", "capacity": 100}
POLL_DEADLINE_SECONDS = 600.0
POLL_INTERVAL_SECONDS = 15.0
ROLE_READBACK_ATTEMPTS = 8
EVENTS = []


class Blocked(RuntimeError):
    """Precondition refused; nothing mutated for this gate."""


def az(*arguments, timeout=120.0):
    events = []
    try:
        return az_json(list(arguments), timeout=timeout, events=events)
    finally:
        EVENTS.extend({key: value for key, value in event.items() if key != "result"} for event in events)


def verify_target(target):
    az("account", "set", "--subscription", target["subscription_id"])
    value = az("account", "show", "--query", "{id:id, tenantId:tenantId}")
    if value["id"] != target["subscription_id"] or value["tenantId"] != target["tenant_id"]:
        raise Blocked(f"active subscription/tenant {value} differs from target file")
    project = az("resource", "show", "--ids", target["project_id"], "--api-version", "2025-06-01",
                 "--query", "{id:id, principalId:identity.principalId}")
    if project["principalId"] != PRINCIPAL:
        raise Blocked("project managed identity differs from authorized principal")
    return {"subscription_id": value["id"], "tenant_id": value["tenantId"], "project_principal": project["principalId"]}


def acrpull_at_exact_scope(scope):
    items = az("role", "assignment", "list", "--assignee", PRINCIPAL, "--scope", scope, "--role", ROLE)
    return [{key: item.get(key) for key in ("id", "roleDefinitionName", "principalId", "principalType", "scope")}
            for item in items
            if item.get("principalId") == PRINCIPAL and item.get("roleDefinitionName") == ROLE
            and (item.get("scope") or "").lower() == scope.lower()]


def gate_g1(ledger, target):
    scope = target["registry_id"]
    before = acrpull_at_exact_scope(scope)
    if before:
        return {"outcome": "pre-existing", "readback": before}
    intent = "g1-acrpull"
    if ledger.exists(intent + "-intent.json"):
        raise Blocked("unresolved g1 intent and no assignment at scope; reconcile manually, never replay")
    ledger.intent(intent, {"role": ROLE, "assignee_object_id": PRINCIPAL, "principal_type": "ServicePrincipal",
                           "scope": scope})
    created = az("role", "assignment", "create", "--assignee-object-id", PRINCIPAL,
                 "--assignee-principal-type", "ServicePrincipal", "--role", ROLE, "--scope", scope)
    for attempt in range(ROLE_READBACK_ATTEMPTS):
        after = acrpull_at_exact_scope(scope)
        if after:
            return {"outcome": "new", "created_id": created.get("id"), "readback": after, "readback_attempts": attempt + 1}
        time.sleep(POLL_INTERVAL_SECONDS)
    raise RuntimeError("role assignment create returned but exact-scope read-back found no AcrPull")


def deployment_summary(item):
    properties = item.get("properties") or {}
    model = properties.get("model") or {}
    sku = item.get("sku") or {}
    return {"id": item.get("id"), "name": item.get("name"), "provisioningState": properties.get("provisioningState"),
            "model": {"format": model.get("format"), "name": model.get("name"), "version": model.get("version")},
            "sku": sku.get("name"), "capacity": sku.get("capacity"),
            "versionUpgradeOption": properties.get("versionUpgradeOption")}


def matches(summary):
    return (summary["model"] == DEPLOYMENT["model"] and summary["sku"] == DEPLOYMENT["sku"]
            and summary["capacity"] == DEPLOYMENT["capacity"])


def availability(base, location):
    wanted = DEPLOYMENT["model"]
    models = [item.get("model", item) for item in az("cognitiveservices", "account", "list-models", *base, timeout=180.0)]
    family = [item for item in models if item.get("name") == wanted["name"] and item.get("format") == wanted["format"]]
    versions = sorted({
        (item.get("version"), tuple(sorted(sku.get("name") for sku in item.get("skus") or [])), item.get("lifecycleStatus"))
        for item in family})
    report = {"available_versions": [{"version": v, "skus": list(s), "lifecycleStatus": l} for v, s, l in versions]}
    exact = [item for item in family if item.get("version") == wanted["version"]]
    sku = next((sku for item in exact for sku in item.get("skus") or [] if sku.get("name") == DEPLOYMENT["sku"]), None)
    if sku is None:
        report["refusal"] = (f"{wanted['name']} {wanted['version']} with SKU {DEPLOYMENT['sku']} not offered by account "
                             f"in {location}; no substitution")
        return report
    report["sku_capacity"] = sku.get("capacity")
    usage_name = sku.get("usageName")
    report["usage_name"] = usage_name
    usage = [item for item in az("cognitiveservices", "usage", "list", "-l", location)
             if usage_name and (item.get("name") or {}).get("value") == usage_name]
    if not usage:
        report["quota"] = "unknown: usage entry not found; create response decides"
        return report
    current, limit = usage[0].get("currentValue"), usage[0].get("limit")
    report["quota"] = {"current": current, "limit": limit}
    if current is not None and limit is not None and limit - current < DEPLOYMENT["capacity"]:
        report["refusal"] = f"quota {usage_name} free {limit - current} < {DEPLOYMENT['capacity']}; no substitution"
    return report


def gate_g6(ledger, target):
    base = ["-g", target["model_resource_group"], "-n", target["model_account"]]
    name = DEPLOYMENT["name"]
    location = az("cognitiveservices", "account", "show", *base, "--query", "location")
    existing = [deployment_summary(item) for item in az("cognitiveservices", "account", "deployment", "list", *base)
                if item.get("name") == name]
    if existing:
        if not matches(existing[0]):
            raise Blocked(f"deployment {name} exists with different properties {existing[0]}; not modified")
        if existing[0]["provisioningState"] == "Succeeded":
            return {"outcome": "pre-existing", "readback": existing[0]}
        return {"outcome": "pre-existing-provisioning", **poll(base, name, time.monotonic())}
    intent = "g6-optimizer-deployment"
    if ledger.exists(intent + "-intent.json"):
        raise Blocked("unresolved g6 intent and deployment absent; reconcile manually, never replay")
    report = availability(base, location)
    if "refusal" in report:
        raise Blocked(json.dumps(report, sort_keys=True))
    ledger.intent(intent, {**DEPLOYMENT, "account": target["model_account"],
                           "resource_group": target["model_resource_group"], "location": location,
                           "proven_source": {"path": PROVEN_PATH.relative_to(REPO).as_posix(),
                                             "sha256": sha256_file(PROVEN_PATH)}})
    started = time.monotonic()
    create_error = None
    try:
        az("cognitiveservices", "account", "deployment", "create", *base, "--deployment-name", name,
           "--model-name", DEPLOYMENT["model"]["name"], "--model-version", DEPLOYMENT["model"]["version"],
           "--model-format", DEPLOYMENT["model"]["format"], "--sku-name", DEPLOYMENT["sku"],
           "--sku-capacity", str(DEPLOYMENT["capacity"]), timeout=POLL_DEADLINE_SECONDS)
    except subprocess.TimeoutExpired as error:
        create_error = error_summary(error)
    return {"outcome": "new", "availability": report, "create_timeout": create_error, **poll(base, name, started)}


def poll(base, name, started):
    polls = 0
    while True:
        polls += 1
        summary = deployment_summary(az("cognitiveservices", "account", "deployment", "show", *base,
                                        "--deployment-name", name))
        state = summary["provisioningState"]
        if state == "Succeeded":
            if not matches(summary):
                raise RuntimeError(f"deployment read-back mismatch {summary}")
            return {"readback": summary, "polls": polls, "seconds": round(time.monotonic() - started, 3)}
        if state in {"Failed", "Canceled"}:
            raise RuntimeError(f"deployment provisioning {state}: {summary}")
        if time.monotonic() - started > POLL_DEADLINE_SECONDS:
            raise RuntimeError(f"deployment not Succeeded within {POLL_DEADLINE_SECONDS}s: {summary}")
        time.sleep(POLL_INTERVAL_SECONDS)


def run_gate(name, gates, function, *arguments):
    started = time.monotonic()
    mark = len(EVENTS)
    try:
        gates[name] = {"status": "ok", **function(*arguments)}
    except Blocked as error:
        gates[name] = {"status": "blocked", "reason": str(error)}
    except Exception as error:  # noqa: BLE001 - every failure is retained with its CLI diagnostic
        gates[name] = {"status": "error", "error": error_summary(error),
                       "diagnostics": [event["diagnostic"] for event in EVENTS[mark:] if "diagnostic" in event]}
    gates[name]["seconds"] = round(time.monotonic() - started, 3)


def main():
    target = json.loads(TARGET_PATH.read_text())
    ledger = EvidenceLedger(HERE)
    gates = {}
    run_gate("target", gates, verify_target, target)
    if gates["target"]["status"] == "ok":
        run_gate("G1", gates, gate_g1, ledger, target)
        run_gate("G6", gates, gate_g6, ledger, target)
    receipt = {
        "schema_version": 1,
        "action": "prereqs-g1-g6",
        "status": "complete" if all(item["status"] == "ok" for item in gates.values()) and len(gates) == 3 else "incomplete",
        "authorized_writes": {"G1": {"role": ROLE, "principal": PRINCIPAL, "scope": target["registry_id"]},
                              "G6": {**DEPLOYMENT, "account": target["model_account"],
                                     "resource_group": target["model_resource_group"]}},
        "target": {"path": TARGET_PATH.relative_to(REPO).as_posix(), "sha256": sha256_file(TARGET_PATH)},
        "script": {"path": Path(__file__).resolve().relative_to(REPO).as_posix(), "sha256": sha256_file(__file__)},
        "gates": gates,
        "az_events": EVENTS,
        "finished_at": utc_stamp(),
    }
    retained = ledger.retain(f"{receipt['finished_at']}-prereqs.json", sanitize(receipt))
    print(json.dumps({"receipt": retained["path"], "status": receipt["status"],
                      "gates": {name: {key: item.get(key) for key in ("status", "outcome", "readback", "reason", "diagnostics")}
                                for name, item in gates.items()}}, indent=1))
    return 0 if receipt["status"] == "complete" else 1


if __name__ == "__main__":
    sys.exit(main())
