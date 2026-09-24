"""Read-only cloud settlement for the exact F08 resources."""

import argparse
from datetime import datetime, timezone
import inspect
import json
from pathlib import Path
import subprocess
import time

import evidence

ROOT, OUT = evidence.ROOT, evidence.OUT
HOST = ROOT / "testbeds/foundry-hosted-agents/deploy/records"
OPT = ROOT / "testbeds/foundry-agent optimization/deploy/evidence"
TARGET = json.loads((ROOT / "testbeds/foundry-hosted-agents/deploy/env/target.json").read_text())


def read(path):
    return json.loads(path.read_text())


def expected_versions():
    versions = []
    for filename in ("20260922T060202403083Z-verify.json", "20260922T060615632239Z-verify.json"):
        value = read(HOST / filename)["result"]["version"]
        versions.append({"agent": "agentcraft-hosted-tool-proof", "version": value["version"],
                         "definition": value["definition"], "protected": True})
    for deployed in (read(OPT / "demonstration-decision.json")["restore"],
                     read(OPT / "demonstration-result.json")["deployment"]):
        versions.append({"agent": deployed["agent"], "version": deployed["version"],
                         "definition": deployed["actual"]["definition"],
                         "metadata": deployed["actual"]["metadata"], "protected": True})
    deployed = read(HOST / "migration-h-v1/20260922T183120213195Z-deploy.json")["result"]
    versions.append({"agent": deployed["agent"], "version": deployed["version"],
                     "definition": deployed["definition"], "metadata": deployed["metadata"], "protected": False})
    comparison = read(OPT / "migration-o-v3/candidate-validation-metrics.json")
    for candidate in comparison["candidates"]:
        deployed = candidate["deployment"]
        versions.append({"agent": deployed["agent"], "version": deployed["version"],
                         "definition": deployed["actual"]["definition"],
                         "metadata": deployed["actual"]["metadata"], "protected": False})
    return versions


def definition(value):
    result = dict(value)
    if result.get("container_protocol_versions") == []:
        result.pop("container_protocol_versions")
    return result


def local():
    versions = expected_versions()
    assert len(versions) == 8
    assert len({(value["agent"], value["version"]) for value in versions}) == 8
    for value in versions:
        assert "@sha256:" in value["definition"]["container_configuration"]["image"]
    assert read(OPT / "migration-o-v3/candidate-validation-metrics.json")["complete_independent_validation"]
    assert read(ROOT / "testbeds/foundry-agent-evaluation/deploy/records/migration-e-v1/20260922T181808468298Z-verify.json")["result"]["accepted"]
    return {"expected_versions": versions, "local_receipts_valid": True}


def live():
    from azure.ai.projects import AIProjectClient
    from azure.identity import AzureCliCredential

    result = local()
    result.update(start=evidence.clock(), versions=[], jobs=[], builds=[], responses=[], inventories={},
                  costs="unknown", packages="unchanged", workers=[], destructive_actions=[],
                  auth_changes=[], heldout_operations=[], pending_operations=[])
    account = subprocess.run(["az", "account", "show", "--query",
        "{subscriptionId:id,tenantId:tenantId,cloud:environmentName}", "-o", "json"],
        capture_output=True, text=True, check=True, timeout=30)
    if json.loads(account.stdout) != {"subscriptionId": TARGET["subscription_id"], "tenantId": TARGET["tenant_id"], "cloud": TARGET["cloud"]}:
        raise ValueError("active account changed")
    started = time.monotonic()
    with AzureCliCredential(tenant_id=TARGET["tenant_id"], process_timeout=30) as credential, AIProjectClient(
        TARGET["project_endpoint"], credential, allow_preview=True, retry_total=0, connection_timeout=15, read_timeout=60
    ) as project:
        result["public_signatures"] = {name: str(inspect.signature(getattr(project.agents, name)))
            for name in ("create_version", "get_version", "get_session_log_stream")}
        result["public_signatures"]["begin_create_optimization_job"] = str(inspect.signature(project.beta.agents.begin_create_optimization_job))
        for expected in result["expected_versions"]:
            actual = project.agents.get_version(expected["agent"], expected["version"]).as_dict()
            if actual.get("status") != "active" or definition(actual["definition"]) != definition(expected["definition"]):
                raise ValueError("protected/final version definition drift: " + expected["agent"] + ":" + expected["version"])
            if "metadata" in expected and any(actual.get("metadata", {}).get(key) != value for key, value in expected["metadata"].items()):
                raise ValueError("version metadata drift")
            result["versions"].append({"agent": expected["agent"], "version": expected["version"],
                "status": actual["status"], "definition": actual["definition"], "metadata": actual.get("metadata"),
                "protected": expected["protected"], "matched": True})
        for series in ("migration-o-v1", "migration-o-v2", "migration-o-v3"):
            identity = read(OPT / series / (series + "-optimizer-job-identity.json"))
            job = project.beta.agents.get_optimization_job(identity["job_id"]).as_dict()
            if job["status"] not in {"succeeded", "failed", "cancelled", "canceled", "completed"}:
                result["pending_operations"].append(identity)
            result["jobs"].append({"series": series, "identity": identity, "job": job})
        for agent in ("agentcraft-migration-tool-proof-v1", "agentcraft-migration-iris-v1"):
            versions = [value.as_dict() for value in project.agents.list_versions(agent_name=agent, limit=100)]
            sessions = [value.as_dict() for value in project.agents.list_sessions(agent_name=agent, limit=100)]
            result["inventories"][agent] = {"versions": versions, "sessions": sessions,
                "retention": "Retained intentionally; no teardown authorized; active/idle sessions are not unresolved creates."}
        with project.get_openai_client(agent_name="agentcraft-migration-tool-proof-v1", max_retries=0, timeout=60) as client:
            for path in sorted((HOST / "migration-h-v1").glob("cancel*-accepted-intent.json")):
                identity = read(path)
                response = client.responses.retrieve(identity["response_id"]).model_dump(mode="json")
                result["responses"].append({"intent": str(path.relative_to(ROOT)), "id": response["id"],
                    "status": response["status"], "output_count": len(response.get("output") or [])})
                if response["status"] not in {"completed", "cancelled", "failed", "incomplete"}:
                    result["pending_operations"].append({"response_id": response["id"]})
    builds = {}
    for path in (HOST / "migration-h-v1").glob("*-build.json"):
        value = read(path)
        if value["status"] == "complete":
            built = value["result"]
            builds[built["acr_run"]["runId"]] = built["image"]
    for path in (OPT / "migration-o-v1").glob("build-*-result.json"):
        built = read(path)
        builds[built["run"]["runId"]] = built["image"]
    for run_id, image in builds.items():
        command = ["az", "acr", "task", "show-run", "--subscription", TARGET["subscription_id"],
            "--registry", TARGET["registry_name"], "--run-id", run_id,
            "--query", "{runId:runId,status:status,outputImages:outputImages}", "-o", "json"]
        observed = subprocess.run(command, capture_output=True, text=True, check=True, timeout=60)
        actual = json.loads(observed.stdout)
        if actual["status"] != "Succeeded" or not any(image.endswith("@" + item["digest"]) for item in actual["outputImages"]):
            raise ValueError("build status/digest drift")
        result["builds"].append({"command": command, "image": image, "readback": actual})
    result["seconds"] = time.monotonic() - started
    result["end"] = evidence.clock()
    result["settled"] = not result["pending_operations"]
    result["limitations"] = ["No cloud rollback performed.", "No separate foreign-principal credential test.",
        "Cancellation terminal readback is live; joined task/client closure is tested locally, provider cleanup log marker not recovered.",
        "Hard-kill response durability remains unsupported by current host configuration."]
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("local", "live"))
    args = parser.parse_args()
    value = local() if args.action == "local" else live()
    name = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-settlement-" + args.action + ".json"
    reference = evidence.PREVIOUS.save(name, value)
    print(json.dumps({"receipt": reference, "settled": value.get("settled"), "versions": len(value.get("versions", []))}))