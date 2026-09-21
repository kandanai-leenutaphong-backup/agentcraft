from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
import time

from resource_group import DeploymentError, ResourceGroupDeployment, Target, azure_cli, permits

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "demonstration_project/agentcraft_projects/overseer-self-optimization"
CONSTITUTION_SHA256 = "070cadee2c44731d1b984dafc906a6bba2f2797de1bd2530474ef5777b8c0e37"
BEFORE = "20260920T113042393167Z-public-deployment-current-before"
BEFORE_SHA256 = "19b39d6753bc9d398bf869546f0ea802256def357b919d23b9554e00b05403c2"
PROVIDERS = ("Microsoft.App", "Microsoft.ContainerRegistry", "Microsoft.ManagedIdentity",
             "Microsoft.DocumentDB", "Microsoft.Search", "Microsoft.Storage", "Microsoft.KeyVault")
NAME_KEYS = {"app", "environment", "registry", "identity", "cosmos", "gremlin", "search", "storage", "vault"}
REQUIRED_ACTIONS = (
    "Microsoft.Resources/deployments/write", "Microsoft.Authorization/roleAssignments/write",
    "Microsoft.App/containerApps/write", "Microsoft.App/managedEnvironments/write",
    "Microsoft.ContainerRegistry/registries/write", "Microsoft.ManagedIdentity/userAssignedIdentities/write",
    "Microsoft.DocumentDB/databaseAccounts/write", "Microsoft.Search/searchServices/write",
    "Microsoft.Storage/storageAccounts/write", "Microsoft.KeyVault/vaults/write",
)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise DeploymentError(f"Duplicate configuration field: {key}")
        result[key] = value
    return result


def load_config(path: Path) -> dict:
    config = json.loads(path.read_text(), object_pairs_hook=unique_object)
    expected = {"schema_version", "tenant_id", "subscription_id", "cloud", "location",
                "resource_group", "names", "model_account", "model_deployment", "package_sha256"}
    if not isinstance(config, dict) or set(config) != expected:
        raise DeploymentError("Unknown or missing configuration fields; credentials are not configuration.")
    pinned = {"schema_version": 1, "tenant_id": "c79ab2bb-79cb-47f1-b4da-b6852fe45ff7",
              "subscription_id": "67255afe-8670-4401-a1b8-df6ca63a3516", "cloud": "AzureCloud",
              "location": "australiaeast", "resource_group": "rg-agentcraft-dev",
              "model_account": "han-primary-foundry-resource", "model_deployment": "gpt-5.6-luna",
              "package_sha256": "c9a96ffcdc3775b89685bac82f9941140b8dc2e724ce5f94442a838ab52e8e12"}
    if any(config[key] != value for key, value in pinned.items()):
        raise DeploymentError("Configuration differs from the assigned target/model/package.")
    if not isinstance(config["names"], dict) or set(config["names"]) != NAME_KEYS:
        raise DeploymentError("Resource names must match the explicit inventory.")
    for key, name in config["names"].items():
        pattern = r"[a-z][a-z0-9]{4,22}" if key in {"storage", "registry"} else r"[a-z][a-z0-9-]{2,30}"
        if not isinstance(name, str) or not re.fullmatch(pattern, name):
            raise DeploymentError(f"Invalid non-secret resource name: {key}")
    return config


def verify_pins() -> dict:
    pins = {"constitution/constitution.yaml": CONSTITUTION_SHA256,
            f"records/v2/{BEFORE}/record.json": BEFORE_SHA256}
    for relative, expected in pins.items():
        if hashlib.sha256((PROJECT / relative).read_bytes()).hexdigest() != expected:
            raise DeploymentError(f"Pinned source changed: {relative}")
    return pins


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def save_json(path: Path, value: dict) -> None:
    payload = json.dumps(value, indent=2, sort_keys=True) + "\n"
    with path.open("x", encoding="utf-8") as handle:
        handle.write(payload)
    if path.read_text() != payload:
        raise DeploymentError("Evidence read-back mismatch.")


class InvestigationDeployment:
    def __init__(self, config: dict, cli=azure_cli):
        self.config = config
        self.cli = cli
        self.target = Target(config["subscription_id"], config["tenant_id"], config["resource_group"],
                             config["location"], config["cloud"], "investigation-app",
                             "public-investigation", "public-licensed-only")
        self.group = ResourceGroupDeployment(self.target, cli)

    def preflight(self) -> dict:
        target = self.target
        account = self.group.preflight("write")
        present = self.group.exists()
        existing = self.group.snapshot() if present else None
        scope = target.resource_id if present else f"/subscriptions/{target.subscription_id}"
        permissions = self.cli("rest", "--method", "get", "--url",
            f"https://management.azure.com{scope}/providers/Microsoft.Authorization/permissions?api-version=2022-04-01",
            "--query", "value[].{actions:actions,notActions:notActions}")
        if not isinstance(permissions, list):
            raise DeploymentError("Reported deployment permissions unknown.")
        missing = [action for action in REQUIRED_ACTIONS if not permits(permissions, action)]
        if missing:
            raise DeploymentError("Missing reported scoped actions: " + ", ".join(missing))
        providers = self.cli("provider", "list", "--subscription", target.subscription_id,
                             "--query", "[].{namespace:namespace,state:registrationState}")
        if not isinstance(providers, list):
            raise DeploymentError("Provider state unknown.")
        states = {item["namespace"]: item["state"] for item in providers}
        unavailable = [name for name in PROVIDERS if states.get(name) != "Registered"]
        if unavailable:
            raise DeploymentError("Required providers not registered; no automatic registration: " + ", ".join(unavailable))
        policies = self.cli("policy", "assignment", "list", "--scope", scope,
            "--disable-scope-strict-match", "--subscription", target.subscription_id,
            "--query", "[].{id:id,name:name,scope:scope,enforcementMode:enforcementMode,policyDefinitionId:policyDefinitionId}")
        locks = self.cli("rest", "--method", "get", "--url",
            f"https://management.azure.com{scope}/providers/Microsoft.Authorization/locks?api-version=2016-09-01",
            "--query", "value[].{id:id,level:properties.level}")
        if not isinstance(locks, list) or locks:
            raise DeploymentError("Target lock status unknown or locked; no lock mutation permitted.")
        accounts = self.cli("cognitiveservices", "account", "list", "--subscription", target.subscription_id,
            "--query", "[?name=='han-primary-foundry-resource'].{id:id,name:name,resourceGroup:resourceGroup,kind:kind}")
        if not isinstance(accounts, list) or len(accounts) != 1:
            raise DeploymentError("Exact authorized model account not uniquely available; no substitution.")
        model = self.cli("cognitiveservices", "account", "deployment", "show", "--subscription", target.subscription_id,
            "--resource-group", accounts[0]["resourceGroup"], "--name", self.config["model_account"],
            "--deployment-name", self.config["model_deployment"],
            "--query", "{id:id,name:name,sku:sku,model:properties.model,state:properties.provisioningState}")
        if not isinstance(model, dict) or model.get("name") != self.config["model_deployment"] or model.get("state") != "Succeeded":
            raise DeploymentError("Exact authorized model deployment not ready; no substitution.")
        directory_policy = self.cli("rest", "--method", "get", "--url",
            "https://graph.microsoft.com/v1.0/policies/authorizationPolicy?$select=id,defaultUserRolePermissions",
            "--query", "{id:id,allowedToCreateApps:defaultUserRolePermissions.allowedToCreateApps}")
        return {"status": "blocked", "account": account, "group_present": present, "existing": existing,
                "providers": {name: states[name] for name in PROVIDERS}, "policies": policies,
                "locks": locks, "model": model, "directory_policy": directory_policy,
                "reported_deployment_actions": list(REQUIRED_ACTIONS), "actual_cost": "unknown",
                "blockers": ["App graph credential binding requires checkpoint before Key Vault-reference extension.",
                             "Authoring storage hard-link/locking/SQLite durability is not verified.",
                             "Name/quota/provider validation and exact Entra registration permissions remain unverified.",
                             "No production signed caller provisioned or trusted by this runner."],
                "cloud_mutations": 0, "effective_access_complete": False}


def main() -> int:
    parser = argparse.ArgumentParser(description="Investigation deployment preflight; no resources provisioned until release gates pass.")
    parser.add_argument("action", choices=("preflight",))
    parser.add_argument("--config", type=Path, default=ROOT / "deploy/env/agentcraft-dev.json")
    parser.add_argument("--evidence", type=Path, required=True)
    options = parser.parse_args()
    evidence = options.evidence.resolve()
    if evidence.parent.parent != PROJECT / "results" or evidence.name != "evidence" or not re.fullmatch(
            r"\d{8}T\d{6}Z-public-investigation-deployment", evidence.parent.name):
        parser.error("Evidence must be a new project results/<UTC>-public-investigation-deployment/evidence directory.")
    evidence.mkdir(parents=True, exist_ok=True)
    invocation = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    result = {"kind": "deployment-primary-evidence", "started_at": utc(), "action": options.action,
              "commands": [], "cloud_mutations": 0, "max_effort": "requested; runtime unverified"}
    start = time.monotonic()

    def logged_cli(*arguments):
        command = {"argv": ["az", *arguments, "--only-show-errors", "--output", "json"], "started_at": utc()}
        command_start = time.monotonic()
        try:
            output = azure_cli(*arguments)
            command.update(status="complete", output=output)
            return output
        except DeploymentError as error:
            command.update(status="failed", error=str(error))
            raise
        finally:
            command.update(finished_at=utc(), elapsed_seconds=time.monotonic() - command_start)
            result["commands"].append(command)
            save_json(evidence / f"{invocation}-{len(result['commands']):03d}-command.json", command)

    try:
        result["pins"] = verify_pins()
        config = load_config(options.config)
        result["config_sha256"] = hashlib.sha256(options.config.read_bytes()).hexdigest()
        result.update(InvestigationDeployment(config, logged_cli).preflight())
    except (DeploymentError, OSError, ValueError, TypeError, KeyError) as error:
        result.update(status="blocked", error=str(error))
    result.update(finished_at=utc(), elapsed_seconds=time.monotonic() - start)
    destination = evidence / f"{invocation}-preflight.json"
    save_json(destination, result)
    print(json.dumps({"status": result["status"], "evidence": str(destination),
                      "error": result.get("error"), "blockers": result.get("blockers", [])}, indent=2))
    return 2 if result["status"] == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())