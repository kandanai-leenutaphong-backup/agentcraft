"""Read-only live preflight for the agent-package E2E. Azure CLI + SDK reads only; no write, no inference.

Run from repository root with the existing interpreter and an existing `az login`:
    python3 -B agentcraft_projects/foundry-agent-package-e2e-20260924/records/preflight/readonly_probe.py
Writes one new receipt `<UTC>-readonly-probe.json` beside this script (exclusive create, read-back).
The only local state change is `az account set --subscription` to the target file's subscription.
"""

import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path.insert(0, str(REPO / "libraries/foundry-ops/src"))

from foundry_ops.build import az_json  # noqa: E402
from foundry_ops.core import EvidenceLedger, error_summary, sanitize, sha256_file, to_plain, utc_stamp  # noqa: E402

TARGET_PATH = REPO / "testbeds/foundry-hosted-agents/deploy/env/target.json"
O_MANIFEST = REPO / "testbeds/foundry-agent optimization/deploy/env/migration-o-v3.json"
PROPOSED = {
    "agent_name": "agentcraft-pkg-e2e-parcel",
    "image_repository": "agentcraft-pkg-e2e-parcel",
    "evaluator_name": "agentcraft-pkg-e2e-parcel-exact",
    "name_prefix": "agentcraft-pkg-e2e",
    "optimizer_model_candidates": ["agentcraft-iris-optimizer-gpt54"],
    "runtime_model": "gpt-5.6-luna",
    "judge_model": "gpt-5.6-luna",
}
RELEVANT_ROLES = {"AcrPull", "AcrPush", "Owner", "Contributor", "Reader", "User Access Administrator",
                  "Azure AI User", "Azure AI Developer", "Azure AI Project Manager", "Azure AI Account Owner",
                  "Cognitive Services User", "Cognitive Services Contributor", "Cognitive Services OpenAI User",
                  "Cognitive Services OpenAI Contributor", "Role Based Access Control Administrator"}
MAX_ITEMS = 1000
EVENTS = []


def az(*arguments, timeout=120.0):
    events = []
    try:
        return az_json(list(arguments), timeout=timeout, events=events)
    finally:
        # Command, exit code, timing and redacted diagnostic only; outputs are summarised by each check.
        EVENTS.extend({key: value for key, value in event.items() if key != "result"} for event in events)


def check(name, results, function):
    started = time.monotonic()
    try:
        results[name] = {"status": "ok", "value": function()}
    except Exception as error:  # noqa: BLE001 - every failure is retained as an observation
        results[name] = {"status": "error", "error": error_summary(error)}
    results[name]["seconds"] = round(time.monotonic() - started, 3)


def bounded(iterable):
    items = []
    for item in iterable:
        if len(items) >= MAX_ITEMS:
            raise RuntimeError(f"more than {MAX_ITEMS} items; refusing truncation")
        items.append(to_plain(item))
    return items


def roles(assignments, principal_ids=None):
    keep = []
    for item in assignments:
        if principal_ids is not None and item.get("principalId") not in principal_ids:
            continue
        keep.append({key: item.get(key) for key in ("roleDefinitionName", "principalId", "principalType", "scope")})
    return sorted(keep, key=lambda item: (item["scope"] or "", item["roleDefinitionName"] or ""))


def main():
    target = json.loads(TARGET_PATH.read_text())
    o_manifest = json.loads(O_MANIFEST.read_text())
    optimizer_candidates = sorted({*PROPOSED["optimizer_model_candidates"], o_manifest["optimizer_model"]})
    account_rg = target["model_resource_group"]
    account = target["model_account"]
    account_id = target["project_id"].split("/projects/")[0]
    registry_rg = target["registry_id"].split("/resourceGroups/")[1].split("/")[0]
    results = {}
    observed = {}

    check("az_account_set", results, lambda: az("account", "set", "--subscription", target["subscription_id"]))

    def account_show():
        value = az("account", "show", "--query", "{id:id, tenantId:tenantId, cloud:environmentName, userType:user.type}")
        if value["id"] != target["subscription_id"] or value["tenantId"] != target["tenant_id"]:
            raise RuntimeError("active subscription/tenant differs from target file")
        return value
    check("caller_account", results, account_show)

    def caller_object_id():
        value = az("ad", "signed-in-user", "show", "--query", "{id:id, userType:userType}")
        observed["caller_oid"] = value["id"]
        return value
    check("caller_principal", results, caller_object_id)

    def foundry_account():
        value = az("cognitiveservices", "account", "show", "-n", account, "-g", account_rg, "--query",
                   "{id:id, kind:kind, sku:sku.name, location:location, endpoint:properties.endpoint, "
                   "customSubDomainName:properties.customSubDomainName, publicNetworkAccess:properties.publicNetworkAccess, "
                   "disableLocalAuth:properties.disableLocalAuth, allowProjectManagement:properties.allowProjectManagement, "
                   "provisioningState:properties.provisioningState, identityType:identity.type, principalId:identity.principalId}")
        if value["id"].lower() != account_id.lower():
            raise RuntimeError("account id differs from target file")
        return value
    check("foundry_account", results, foundry_account)

    def foundry_project():
        value = az("resource", "show", "--ids", target["project_id"], "--api-version", "2025-06-01", "--query",
                   "{id:id, name:name, location:location, provisioningState:properties.provisioningState, "
                   "endpoints:properties.endpoints, identityType:identity.type, principalId:identity.principalId}")
        observed["project_principal"] = value.get("principalId")
        return value
    check("foundry_project", results, foundry_project)

    def arm_deployments():
        value = az("cognitiveservices", "account", "deployment", "list", "-n", account, "-g", account_rg, "--query",
                   "[].{name:name, model:properties.model.name, version:properties.model.version, "
                   "format:properties.model.format, sku:sku.name, capacity:sku.capacity, "
                   "provisioningState:properties.provisioningState, versionUpgradeOption:properties.versionUpgradeOption}")
        names = {item["name"] for item in value}
        observed["deployment_names"] = names
        return {"deployments": sorted(value, key=lambda item: item["name"]),
                "runtime_model_present": PROPOSED["runtime_model"] in names,
                "judge_model_present": PROPOSED["judge_model"] in names,
                "optimizer_candidates": {name: name in names for name in optimizer_candidates}}
    check("model_deployments_arm", results, arm_deployments)

    def registry():
        value = az("acr", "show", "-n", target["registry_name"], "-g", registry_rg, "--query",
                   "{id:id, loginServer:loginServer, sku:sku.name, adminUserEnabled:adminUserEnabled, "
                   "anonymousPullEnabled:anonymousPullEnabled, publicNetworkAccess:publicNetworkAccess, "
                   "provisioningState:provisioningState, location:location}")
        if value["loginServer"] != target["registry_host"] or value["id"].lower() != target["registry_id"].lower():
            raise RuntimeError("registry differs from target file")
        return value
    check("registry", results, registry)

    def repositories():
        value = az("acr", "repository", "list", "-n", target["registry_name"])
        tags = None
        if PROPOSED["image_repository"] in value:
            tags = az("acr", "repository", "show-tags", "-n", target["registry_name"],
                      "--repository", PROPOSED["image_repository"])
        return {"repositories": sorted(value), "proposed_repository_exists": PROPOSED["image_repository"] in value,
                "proposed_repository_tags": tags}
    check("registry_repositories", results, repositories)

    def registry_roles():
        value = roles(az("role", "assignment", "list", "--scope", target["registry_id"], "--include-inherited"))
        project_principal = observed.get("project_principal")
        return {"assignments": [item for item in value if item["roleDefinitionName"] in RELEVANT_ROLES],
                "project_principal_acrpull": any(item["principalId"] == project_principal
                                                 and item["roleDefinitionName"] == "AcrPull" for item in value),
                "caller_acr_build_capable": any(item["principalId"] == observed.get("caller_oid")
                                                and item["roleDefinitionName"] in {"Owner", "Contributor", "AcrPush"}
                                                for item in value)}
    check("registry_role_assignments", results, registry_roles)

    def project_principal_registry_roles():
        principal = observed["project_principal"]
        value = roles(az("role", "assignment", "list", "--assignee", principal, "--scope", target["registry_id"],
                         "--include-inherited"))
        return {"principal": principal, "assignments": value,
                "acrpull": any(item["roleDefinitionName"] == "AcrPull" for item in value)}
    check("project_principal_registry_roles", results, project_principal_registry_roles)

    def account_roles():
        principals = {observed.get("project_principal"), observed.get("caller_oid")} - {None}
        value = roles(az("role", "assignment", "list", "--scope", target["project_id"], "--include-inherited"),
                      principals)
        return {"assignments": value}
    check("project_scope_role_assignments", results, account_roles)

    def caller_roles():
        oid = observed["caller_oid"]
        try:
            value = az("role", "assignment", "list", "--assignee", oid, "--all", "--include-inherited",
                       "--include-groups", timeout=180.0)
            groups = True
        except RuntimeError:
            value = az("role", "assignment", "list", "--assignee", oid, "--all", "--include-inherited", timeout=180.0)
            groups = False
        scopes = (f"/subscriptions/{target['subscription_id']}".lower(),)
        value = [item for item in roles(value) if (item["scope"] or "").lower().startswith(scopes)]
        return {"include_groups": groups, "assignments": value}
    check("caller_role_assignments", results, caller_roles)

    def anonymous_gateway():
        import httpx
        response = httpx.get(target["project_endpoint"] + "/agents", params={"api-version": "v1"},
                             timeout=30.0, follow_redirects=False)
        return {"status": response.status_code, "refused": response.status_code in (401, 403)}
    check("anonymous_project_endpoint", results, anonymous_gateway)

    sdk_reads(target, results)
    names = []
    if results.get("agents", {}).get("status") == "ok":
        names = [item["name"] for item in results["agents"]["value"]]
    receipt = {
        "schema_version": 1,
        "action": "readonly-probe",
        "status": "complete" if all(item["status"] == "ok" for item in results.values()) else "partial",
        "writes": "none (Azure); local az CLI active-subscription selection only",
        "target": {"path": TARGET_PATH.relative_to(REPO).as_posix(), "sha256": sha256_file(TARGET_PATH),
                   "subscription_id": target["subscription_id"], "tenant_id": target["tenant_id"],
                   "project_endpoint": target["project_endpoint"], "registry_host": target["registry_host"]},
        "probe_source": {"path": Path(__file__).resolve().relative_to(REPO).as_posix(), "sha256": sha256_file(__file__)},
        "proposed_names": PROPOSED,
        "collisions": {"agent_name_taken": PROPOSED["agent_name"] in names,
                       "prefix_agents": sorted(name for name in names if name.startswith(PROPOSED["name_prefix"]))},
        "checks": results,
        "az_events": EVENTS,
        "finished_at": utc_stamp(),
    }
    ledger = EvidenceLedger(HERE)
    retained = ledger.retain(f"{receipt['finished_at']}-readonly-probe.json", sanitize(receipt))
    print(json.dumps({"receipt": retained, "status": receipt["status"],
                      "failed_checks": sorted(name for name, item in results.items() if item["status"] != "ok")}))


def sdk_reads(target, results):
    from azure.ai.projects import AIProjectClient
    from azure.identity import AzureCliCredential

    with AzureCliCredential(tenant_id=target["tenant_id"], process_timeout=60) as credential, AIProjectClient(
            endpoint=target["project_endpoint"], credential=credential, allow_preview=True, retry_total=0) as project:

        def agents():
            summary = []
            for item in bounded(project.agents.list()):
                latest = (item.get("versions") or {}).get("latest") or {}
                definition = latest.get("definition") or {}
                summary.append({"name": item.get("name"), "latest_version": latest.get("version"),
                                "latest_status": latest.get("status"), "kind": definition.get("kind"),
                                "image": definition.get("image"), "created_at": latest.get("created_at")})
            return sorted(summary, key=lambda item: item["name"] or "")
        check("agents", results, agents)

        def deployments():
            return sorted(({"name": item.get("name"), "type": item.get("type"), "model_name": item.get("modelName") or item.get("model_name"),
                            "model_version": item.get("modelVersion") or item.get("model_version"),
                            "model_publisher": item.get("modelPublisher") or item.get("model_publisher"),
                            "capabilities": item.get("capabilities"), "sku": item.get("sku")}
                           for item in bounded(project.deployments.list())), key=lambda item: item["name"] or "")
        check("model_deployments_sdk", results, deployments)

        def evaluators():
            items = bounded(project.beta.evaluators.list(type="all", limit=200))
            summary = sorted(({"name": item.get("name"), "version": item.get("version"),
                               "type": item.get("evaluator_type") or item.get("type"),
                               "categories": item.get("categories")} for item in items),
                             key=lambda item: item["name"] or "")
            return {"count": len(summary),
                    "tool_related": [item for item in summary if "tool" in (item["name"] or "").lower()],
                    "builtin_names": sorted(item["name"] for item in summary if (item["name"] or "").startswith("builtin.")),
                    "custom_names": sorted(item["name"] for item in summary if not (item["name"] or "").startswith("builtin."))}
        check("evaluators", results, evaluators)

        def optimization_jobs():
            items = bounded(project.beta.agents.list_optimization_jobs())
            return sorted(({"id": item.get("id"), "status": item.get("status"),
                            "agent": ((item.get("inputs") or {}).get("agent") or {}).get("name"),
                            "created_at": item.get("created_at")} for item in items), key=lambda item: item["id"] or "")
        check("optimization_jobs", results, optimization_jobs)

        def connections():
            return sorted(({"name": item.get("name"), "type": item.get("type"), "is_default": item.get("isDefault", item.get("is_default")),
                            "target": item.get("target")} for item in bounded(project.connections.list())),
                          key=lambda item: item["name"] or "")
        check("connections", results, connections)

        def datasets():
            return sorted({item.get("name") for item in bounded(project.datasets.list())} - {None})
        check("datasets", results, datasets)

        def evals():
            client = project.get_openai_client()
            names = []
            for item in client.evals.list(limit=100):
                if len(names) >= MAX_ITEMS:
                    raise RuntimeError("eval listing exceeds bound")
                names.append(item.name)
            return {"count": len(names), "prefix_matches": sorted(name for name in names if name and "pkg-e2e" in name)}
        check("evals", results, evals)


if __name__ == "__main__":
    main()
