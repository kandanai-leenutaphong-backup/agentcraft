from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time

from resource_group import DeploymentError, ResourceGroupDeployment, Target, azure_cli, permits

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "demonstration_project/agentcraft_projects/overseer-self-optimization"
CONSTITUTION_SHA256 = "070cadee2c44731d1b984dafc906a6bba2f2797de1bd2530474ef5777b8c0e37"
BEFORE = "20260920T113042393167Z-public-deployment-current-before"
BEFORE_SHA256 = "19b39d6753bc9d398bf869546f0ea802256def357b919d23b9554e00b05403c2"
RUNTIME_RECEIPT = "records/capture/20260920T115843866Z-public-runtime/receipt.json"
RUNTIME_RECEIPT_SHA256 = "5d0df3ef022cae283cd7059eaffd113637fde02f20e266c1c2fabe1fbc1b6436"
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
    if not isinstance(config, dict) or set(config) - {"runtime"} != expected:
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
    runtime = config.get("runtime", {})
    if not isinstance(runtime, dict) or set(runtime) - {"public_key", "fingerprint", "client_id", "application_object_id", "owner_object_id", "origin"}:
        raise DeploymentError("Runtime configuration contains unknown or credential fields")
    for key, value in runtime.items():
        if not isinstance(value, str) or not value or any(ord(character) < 32 for character in value):
            raise DeploymentError("Invalid non-secret runtime field")
        if key.endswith("_id") and not re.fullmatch(r"[a-f0-9-]{36}", value):
            raise DeploymentError("Runtime identity must be a GUID")
    return config


def verify_pins() -> dict:
    pins = {"constitution/constitution.yaml": CONSTITUTION_SHA256,
            f"records/v2/{BEFORE}/record.json": BEFORE_SHA256,
            RUNTIME_RECEIPT: RUNTIME_RECEIPT_SHA256}
    for relative, expected in pins.items():
        if hashlib.sha256((PROJECT / relative).read_bytes()).hexdigest() != expected:
            raise DeploymentError(f"Pinned source changed: {relative}")
    receipt = json.loads((PROJECT / RUNTIME_RECEIPT).read_text())
    for item in [*receipt["records"], *receipt["prestate_files"]]:
        if hashlib.sha256((PROJECT / item["path"]).read_bytes()).hexdigest() != item["sha256"]:
            raise DeploymentError(f"Recovery snapshot changed: {item['path']}")
    return pins


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def save_json(path: Path, value: dict) -> None:
    payload = json.dumps(value, indent=2, sort_keys=True) + "\n"
    with path.open("x", encoding="utf-8") as handle:
        handle.write(payload)
    if path.read_text() != payload:
        raise DeploymentError("Evidence read-back mismatch.")


def safe_diagnostic(text: str) -> str:
    text = re.sub(r"(?i)(authorization|token|password|secret|accountkey|signature)\s*[:=]\s*[^\s,;]+",
                  r"\1=[redacted]", text)
    text = re.sub(r"[A-Za-z0-9+/=_-]{64,}", "[redacted]", text)
    return text[:6000]


def release_cli(*arguments):
    try:
        completed = subprocess.run(["az", *arguments, "--only-show-errors", "--output", "json"],
                                   capture_output=True, text=True, timeout=1200)
    except subprocess.TimeoutExpired:
        raise DeploymentError("Azure operation timed out; outcome unknown, read back before retrying") from None
    if completed.returncode:
        raise DeploymentError(safe_diagnostic(completed.stderr))
    return json.loads(completed.stdout) if completed.stdout.strip() else None


class InvestigationDeployment:
    def __init__(self, config: dict, cli=azure_cli):
        self.config = config
        self.cli = cli
        self.target = Target(config["subscription_id"], config["tenant_id"], config["resource_group"],
                             config["location"], config["cloud"], "investigation-app",
                             "public-investigation", "public-licensed-only")
        self.group = ResourceGroupDeployment(self.target, cli)

    def status(self):
        account = self.group.preflight("read")
        if not self.group.exists():
            return {"status": "group-absent", "account": account, "cloud_mutations": 0}
        inventory = self.group.snapshot()
        deployments = self.cli("deployment", "group", "list", "--subscription", self.target.subscription_id,
            "--resource-group", self.target.resource_group,
            "--query", "[].{name:name,state:properties.provisioningState,timestamp:properties.timestamp,error:properties.error}")
        operations = self.cli("deployment", "operation", "group", "list", "--subscription", self.target.subscription_id,
            "--resource-group", self.target.resource_group, "--name", "investigation-infra",
            "--query", "[].{id:operationId,target:properties.targetResource,state:properties.provisioningState,status:properties.statusCode,error:properties.statusMessage.error}")
        return {"status": "read-back", "account": account, "inventory": inventory,
                "deployments": deployments, "operations": operations, "cloud_mutations": 0, "actual_cost": "unknown"}

    def infrastructure(self, *, apply: bool = False) -> dict:
        self.preflight()
        self.policy_details()
        group = self.group.run("create", self.target.resource_id)
        template = ROOT / "deploy/infra/investigation.bicep"
        parameters = {"location": self.target.location, "names": self.config["names"],
                      "tags": self.target.tags}
        arguments = tuple(f"{key}={json.dumps(value) if isinstance(value, dict) else value}"
                          for key, value in parameters.items())
        validation = self.cli("deployment", "group", "validate", "--subscription", self.target.subscription_id,
                              "--resource-group", self.target.resource_group, "--name", "investigation-infra-validation",
                              "--template-file", str(template), "--parameters", *arguments,
                              "--query", "{state:properties.provisioningState,error:properties.error}")
        if not isinstance(validation, dict) or validation.get("error"):
            raise DeploymentError("Infrastructure provider validation failed or returned an unknown result")
        if not apply:
            return {"status": "provider-validated", "group": group, "validation": validation,
                    "cloud_mutations": int(group["action"] == "created"), "paid_services_submitted": False}
        deployment = self.cli("deployment", "group", "create", "--subscription", self.target.subscription_id,
                              "--resource-group", self.target.resource_group, "--name", "investigation-infra",
                              "--template-file", str(template), "--parameters", *arguments,
                              "--query", "{state:properties.provisioningState,outputs:properties.outputs}")
        if not isinstance(deployment, dict) or deployment.get("state") != "Succeeded":
            raise DeploymentError("Infrastructure outcome not Succeeded; read back before retrying")
        return {"status": "infrastructure-provisioned", "deployment": deployment,
                "inventory": self.group.snapshot(), "cloud_mutations": "see command receipts",
                "application_deployed": False, "actual_cost": "unknown"}

    def policy_details(self) -> dict:
        scope = f"/subscriptions/{self.target.subscription_id}"
        assignments = self.cli("policy", "assignment", "list", "--scope", scope,
            "--disable-scope-strict-match", "--subscription", self.target.subscription_id,
            "--query", "[].{id:id,policyDefinitionId:policyDefinitionId,parameters:parameters,enforcementMode:enforcementMode}")
        definitions = []
        for assignment in assignments:
            identifier = assignment["policyDefinitionId"]
            if not identifier.startswith("/providers/Microsoft.Authorization/") and not identifier.startswith(scope + "/"):
                raise DeploymentError("Policy definition scope requires explicit review")
            definitions.append(self.cli("rest", "--method", "get", "--url",
                f"https://management.azure.com{identifier}?api-version=2023-04-01",
                "--query", "{id:id,properties:properties}"))
        denies = self.cli("rest", "--method", "get", "--url",
            f"https://management.azure.com{scope}/providers/Microsoft.Authorization/denyAssignments?api-version=2022-04-01",
            "--query", "value[].{id:id,scope:properties.scope,permissions:properties.permissions}")
        if not isinstance(denies, list):
            raise DeploymentError("Deny assignments unknown; review required")
        target = self.target.resource_id.lower()
        relevant = []
        for denial in denies:
            denied_scope = str(denial.get("scope", "")).lower().rstrip("/")
            if not denied_scope or target == denied_scope or target.startswith(denied_scope + "/") or denied_scope.startswith(target + "/"):
                relevant.append(denial)
        if relevant:
            raise DeploymentError("Deny assignments affect target or have unknown scope; review required")
        return {"assignments": assignments, "definitions": definitions, "deny_assignments": relevant,
                "unrelated_denials": len(denies)}

    def constraints(self) -> dict:
        subscription = self.target.subscription_id
        names = self.config["names"]
        availability = {}
        for key in ("cosmos", "gremlin"):
            available = self.cli("cosmosdb", "check-name-exists", "--name", names[key],
                                 "--subscription", subscription)
            if type(available) is not bool or available:
                raise DeploymentError(f"Cosmos account name unavailable or unknown: {names[key]}")
            availability[key] = True
        for key, arguments in (
            ("registry", ("acr", "check-name")),
            ("storage", ("storage", "account", "check-name")),
            ("vault", ("keyvault", "check-name")),
        ):
            result = self.cli(*arguments, "--name", names[key], "--subscription", subscription,
                              "--query", "{available:nameAvailable,reason:reason}")
            if not isinstance(result, dict) or result.get("available") is not True:
                raise DeploymentError(f"Resource name unavailable or unknown: {names[key]}")
            availability[key] = result
        regions = {}
        for provider, resource in (("Microsoft.DocumentDB", "databaseAccounts"),
                                   ("Microsoft.Search", "searchServices"),
                                   ("Microsoft.App", "managedEnvironments")):
            result = self.cli("provider", "show", "--namespace", provider, "--subscription", subscription,
                              "--query", f"resourceTypes[?resourceType=='{resource}'].locations | [0]")
            if not isinstance(result, list) or not any(
                    name.lower().replace(" ", "") == self.target.location for name in result):
                raise DeploymentError(f"Target region not listed for {provider}/{resource}")
            regions[provider] = result
        return {"name_availability": availability, "provider_regions": regions,
                "sku_quota_effective_access": "Requires exact provider validation; not inferred from locations"}

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
                "blockers": ["Runtime implementation and live verification remain incomplete.",
                             "Authoring storage hard-link/locking/SQLite durability is not verified.",
                             "Name/quota/provider validation and exact Entra registration permissions remain unverified.",
                             "No production signed caller provisioned or trusted by this runner."],
                "cloud_mutations": 0, "effective_access_complete": False}


def main() -> int:
    parser = argparse.ArgumentParser(description="Investigation deployment preflight; no resources provisioned until release gates pass.")
    parser.add_argument("action", choices=("plan", "preflight", "constraints", "check", "capture", "validate-infra", "provision-infra", "status", "package", "signer", "seal"))
    parser.add_argument("--source", action="append", default=[])
    parser.add_argument("--python", type=Path, default=Path(sys.executable))
    parser.add_argument("--config", type=Path, default=ROOT / "deploy/env/agentcraft-dev.json")
    parser.add_argument("--evidence", type=Path, required=True)
    options = parser.parse_args()
    evidence = options.evidence.resolve()
    if evidence.parent.parent != PROJECT / "results" or evidence.name != "evidence" or not re.fullmatch(
            r"\d{8}T\d{6}Z-public-investigation-(?:deployment|release)", evidence.parent.name):
        parser.error("Evidence must be a new project results/<UTC>-public-investigation-deployment/evidence directory.")
    evidence.mkdir(parents=True, exist_ok=True)
    invocation = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    result = {"kind": "deployment-primary-evidence", "started_at": utc(), "action": options.action,
              "commands": [], "cloud_mutations": 0, "max_effort": "requested; runtime unverified"}
    start = time.monotonic()

    def logged_cli(*arguments):
        command = {"argv": ["az", *arguments, "--only-show-errors", "--output", "json"], "started_at": utc()}
        command_start = time.monotonic()
        if arguments[:2] == ("group", "create") or arguments[:3] == ("deployment", "group", "create"):
            result["cloud_mutations"] = "submitted; inspect command readbacks"
        try:
            output = release_cli(*arguments)
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
        result["source_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        template = ROOT / "deploy/infra/investigation.bicep"
        if template.exists():
            result["infra_sha256"] = hashlib.sha256(template.read_bytes()).hexdigest()
        if options.action == "plan":
            result.update(status="planned", target=config, private_first=True,
                          services={"cosmos": "serverless", "gremlin": "serverless", "search": "basic",
                                    "registry": "Basic", "storage": "Standard_LRS", "vault": "standard",
                                    "app": "Consumption; max one replica"}, actual_cost="unknown")
        elif options.action == "package":
            from investigation_evidence import build_context
            result.update(status="packaged", build_context=build_context(ROOT, evidence / f"{invocation}-source.tar.gz"))
        elif options.action == "seal":
            from investigation_evidence import seal_sources
            receipt = json.loads((PROJECT / RUNTIME_RECEIPT).read_text())
            result.update(status="sealed", manifest=seal_sources(ROOT, PROJECT, evidence, receipt))
        elif options.action == "signer":
            from investigation_evidence import provision_signer
            signer = provision_signer()
            runtime = config.setdefault("runtime", {})
            if runtime.get("public_key", signer["public_key"]) != signer["public_key"]:
                raise DeploymentError("Configured public signer differs; no automatic rotation")
            runtime.update(public_key=signer["public_key"], fingerprint=signer["fingerprint"])
            options.config.write_text(json.dumps(config, indent=2) + "\n")
            if load_config(options.config) != config:
                raise DeploymentError("Signer public configuration readback mismatch")
            result.update(status="signer-provisioned", signer={key: value for key, value in signer.items() if key != "public_key"})
        elif options.action == "capture":
            sources = []
            for relative in options.source:
                source = ROOT / relative
                if source.resolve() != source or not any(source.is_relative_to(ROOT / prefix) for prefix in (
                        "deploy", "template_apps/investigation_app/app/cybereye",
                        "libraries/modular-agents/modules/agent-config-build")):
                    raise DeploymentError("Capture source outside named owners or symlinked")
                item = {"path": relative, "exists": source.exists(), "observed_at": utc()}
                if source.exists():
                    payload = source.read_bytes()
                    if source.suffix not in {".py", ".bicep", ".md", ".json", ".toml", ".lock", ".sh"}:
                        raise DeploymentError("Capture requires an explicit text source type")
                    if re.search(rb"-----BEGIN (?:[A-Z0-9]+ )?PRIVATE KEY-----", payload):
                        raise DeploymentError("Private material refused")
                    item["sha256"] = hashlib.sha256(payload).hexdigest()
                    retained = evidence / f"{invocation}-source-{len(sources):03d}-{source.name}"
                    with retained.open("xb") as output:
                        output.write(payload)
                    if retained.read_bytes() != payload:
                        raise DeploymentError("Source capture readback mismatch")
                    item["snapshot"] = str(retained.relative_to(PROJECT))
                sources.append(item)
            result.update(status="captured", sources=sources)
        elif options.action == "check":
            argv = [str(options.python.absolute()), "-B", "-m", "pytest",
                "app/cybereye/tests/test_async_graph.py", "-q", "-p", "no:cacheprovider"]
            completed = subprocess.run(argv, cwd=ROOT / "template_apps/investigation_app",
                           capture_output=True, text=True, timeout=120)
            result.update(status="passed" if completed.returncode == 0 else "blocked",
                  argv=argv, exit_code=completed.returncode,
                  stdout=completed.stdout, stderr=completed.stderr)
        else:
            deployment = InvestigationDeployment(config, logged_cli)
            if options.action == "status":
                result.update(deployment.status())
            elif options.action in {"validate-infra", "provision-infra"}:
                result.update(deployment.infrastructure(apply=options.action == "provision-infra"))
            else:
                result.update(deployment.preflight())
            if options.action == "constraints":
                result.update(deployment.constraints())
                result["status"] = "constraints-read"
    except (DeploymentError, OSError, ValueError, TypeError, KeyError) as error:
        result.update(status="blocked", error=str(error))
    result.update(finished_at=utc(), elapsed_seconds=time.monotonic() - start)
    destination = evidence / f"{invocation}-{options.action}.json"
    save_json(destination, result)
    print(json.dumps({"status": result["status"], "evidence": str(destination),
                      "error": result.get("error"), "blockers": result.get("blockers", [])}, indent=2))
    return 2 if result["status"] == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())