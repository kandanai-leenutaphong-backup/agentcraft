from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tarfile
import tempfile
import sys
import time
import uuid

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
    text = re.sub(r"[A-Za-z0-9+/=_-]{64,}",
                  lambda match: match.group() if re.fullmatch(r"[a-f0-9]{64}", match.group()) else "[redacted]", text)
    return text[:6000]


def release_cli(*arguments):
    try:
        completed = subprocess.run(["az", *arguments, "--only-show-errors", "--output", "json"],
                                   capture_output=True, text=True, timeout=1200)
    except subprocess.TimeoutExpired:
        raise DeploymentError("Azure operation timed out; outcome unknown, read back before retrying") from None
    if completed.returncode:
        raise DeploymentError(safe_diagnostic(completed.stderr))
    if arguments[:3] == ("acr", "task", "logs"):
        return {"log_tail": safe_diagnostic(completed.stdout[-6000:]), "full_log_bytes": len(completed.stdout.encode())}
    if arguments[:4] == ("containerapp", "job", "logs", "show") or arguments[:2] == ("containerapp", "exec"):
        return {"output": safe_diagnostic(completed.stdout[-6000:])}
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

    def registration(self):
        self.group.preflight("read")
        self.group.snapshot()
        domain = self.cli("containerapp", "env", "show", "--subscription", self.target.subscription_id,
            "--resource-group", self.target.resource_group, "--name", self.config["names"]["environment"],
            "--query", "properties.defaultDomain")
        if not isinstance(domain, str) or not re.fullmatch(r"[a-z0-9.-]+\.azurecontainerapps\.io", domain):
            raise DeploymentError("Owned environment domain unavailable")
        origin = f"https://{self.config['names']['app']}.{domain}"
        owner = self.cli("rest", "--method", "get", "--url", "https://graph.microsoft.com/v1.0/me?$select=id", "--query", "id")
        if not isinstance(owner, str) or not re.fullmatch(r"[a-f0-9-]{36}", owner):
            raise DeploymentError("Current human owner identity unavailable")
        display = "agentcraft-investigation-rg-agentcraft-dev"
        applications = self.cli("rest", "--method", "get", "--url",
            f"https://graph.microsoft.com/v1.0/applications?$filter=displayName eq '{display}'&$select=id,appId,signInAudience,tags",
            "--query", "value")
        if not isinstance(applications, list) or len(applications) > 1:
            raise DeploymentError("Registration name ownership ambiguous")
        if applications:
            application = applications[0]
            owners = self.cli("rest", "--method", "get", "--url",
                f"https://graph.microsoft.com/v1.0/applications/{application['id']}/owners?$select=id", "--query", "value[].id")
            if owner not in owners or application.get("tags") != ["agentcraft-rg-agentcraft-dev"] or application.get("signInAudience") != "AzureADMyOrg":
                raise DeploymentError("Existing registration ownership/audience differs; no adoption")
        else:
            application = self.cli("rest", "--method", "post", "--url", "https://graph.microsoft.com/v1.0/applications",
                "--body", json.dumps({"displayName": display, "signInAudience": "AzureADMyOrg",
                    "tags": ["agentcraft-rg-agentcraft-dev"], "requiredResourceAccess": [],
                    "owners@odata.bind": [f"https://graph.microsoft.com/v1.0/directoryObjects/{owner}"],
                    "spa": {"redirectUris": [origin + "/auth/callback"]},
                    "web": {"implicitGrantSettings": {"enableAccessTokenIssuance": False, "enableIdTokenIssuance": False}}}),
                "--query", "{id:id,appId:appId}")
        scope = {"id": str(uuid.uuid5(uuid.NAMESPACE_URL, application["appId"] + "/access_as_user")),
                 "value": "access_as_user", "type": "User", "isEnabled": True,
                 "adminConsentDisplayName": "Access Investigation", "adminConsentDescription": "Access the owner-authorized Investigation application.",
                 "userConsentDisplayName": "Access Investigation", "userConsentDescription": "Access your Investigation application."}
        desired = {"identifierUris": [f"api://{application['appId']}"],
                   "api": {"requestedAccessTokenVersion": 2, "oauth2PermissionScopes": [scope]},
                   "spa": {"redirectUris": [origin + "/auth/callback"]}}
        self.cli("rest", "--method", "patch", "--url", f"https://graph.microsoft.com/v1.0/applications/{application['id']}",
                 "--body", json.dumps(desired))
        observed = self.cli("rest", "--method", "get", "--url",
            f"https://graph.microsoft.com/v1.0/applications/{application['id']}?$select=id,appId,signInAudience,spa,api,web,requiredResourceAccess,identifierUris")
        if (observed.get("signInAudience") != "AzureADMyOrg" or observed.get("requiredResourceAccess") != []
                or observed.get("spa", {}).get("redirectUris") != desired["spa"]["redirectUris"]
                or observed.get("api", {}).get("requestedAccessTokenVersion") != 2
                or observed.get("api", {}).get("oauth2PermissionScopes") != [scope]):
            raise DeploymentError("Registration security readback mismatch")
        return {"status": "registration-configured", "registration": observed,
                "runtime": {"client_id": application["appId"], "application_object_id": application["id"],
                            "owner_object_id": owner, "origin": origin}, "human_signin": "not_verified",
                "cloud_mutations": "registration create/patch; see receipts"}

    def build(self, receipt_path, invocation):
        self.group.preflight("read")
        self.group.snapshot()
        receipt = json.loads(receipt_path.read_text())
        context = receipt["build_context"]
        archive = Path(context["archive"])
        if not archive.resolve().is_relative_to(PROJECT / "results") or hashlib.sha256(archive.read_bytes()).hexdigest() != context["sha256"]:
            raise DeploymentError("Build archive digest/path mismatch")
        with tempfile.TemporaryDirectory(prefix="agentcraft-build-") as directory:
            with tarfile.open(archive, "r:gz") as source:
                if set(source.getnames()) != set(context["entries"]):
                    raise DeploymentError("Build archive members changed")
                for member in source:
                    if not member.isfile() or member.name.startswith("/") or ".." in Path(member.name).parts:
                        raise DeploymentError("Unsafe build member")
                    if hashlib.sha256(source.extractfile(member).read()).hexdigest() != context["entries"][member.name]["sha256"]:
                        raise DeploymentError("Build member digest changed")
                source.extractall(directory, filter="data")
            tag = "investigation:" + invocation.lower()
            build = self.cli("acr", "build", "--subscription", self.target.subscription_id,
                "--registry", self.config["names"]["registry"], "--image", tag,
                "--file", "deploy/Dockerfile.investigation", "--no-logs", directory)
        image = self.cli("acr", "repository", "show", "--subscription", self.target.subscription_id,
            "--name", self.config["names"]["registry"], "--image", tag, "--query", "{digest:digest,name:name}")
        if not isinstance(image, dict) or not re.fullmatch(r"sha256:[a-f0-9]{64}", image.get("digest", "")):
            raise DeploymentError("Built image digest unknown")
        return {"status": "image-built", "build": build, "tag": tag, "image": f"{self.config['names']['registry']}.azurecr.io/investigation@{image['digest']}",
                "archive_sha256": context["sha256"], "cloud_mutations": "ACR image build"}

    def private_release(self, build_receipt):
        self.group.preflight("write")
        self.group.snapshot()
        release = json.loads(build_receipt.read_text())
        image = release.get("image", "")
        if release.get("status") != "image-built" or not re.fullmatch(
                re.escape(self.config["names"]["registry"]) + r"\.azurecr\.io/investigation@sha256:[a-f0-9]{64}", image):
            raise DeploymentError("Owned immutable image receipt required")
        runtime = self.config.get("runtime", {})
        if set(runtime) != {"client_id", "application_object_id", "owner_object_id", "origin", "public_key", "fingerprint"}:
            raise DeploymentError("Complete single-tenant registration and unique signer required")
        template = ROOT / "deploy/infra/investigation-app.bicep"
        parameters = {"location": self.target.location, "names": self.config["names"], "tags": self.target.tags,
                      "runtimeConfig": runtime, "tenantId": self.target.tenant_id,
                      "subscriptionId": self.target.subscription_id, "image": image, "external": "false"}
        arguments = tuple(f"{key}={json.dumps(value) if isinstance(value, dict) else value}" for key, value in parameters.items())
        common = ("--subscription", self.target.subscription_id, "--resource-group", self.target.resource_group,
                  "--name", "investigation-private-app", "--template-file", str(template), "--parameters", *arguments)
        self.cli("deployment", "group", "validate", *common, "--query", "{state:properties.provisioningState,error:properties.error}")
        observed = self.cli("deployment", "group", "create", *common,
            "--query", "{state:properties.provisioningState,outputs:properties.outputs}")
        if observed.get("state") != "Succeeded":
            raise DeploymentError("Private app deployment not succeeded")
        return {"status": "private-app-deployed", "image": image, "deployment": observed,
                "runtime": self.app_status(), "cloud_mutations": "private app and job; see receipts"}

    def app_status(self):
        return self.cli("containerapp", "show", "--subscription", self.target.subscription_id,
            "--resource-group", self.target.resource_group, "--name", self.config["names"]["app"],
            "--query", "{id:id,state:properties.provisioningState,revision:properties.latestRevisionName,readyRevision:properties.latestReadyRevisionName,ingress:properties.configuration.ingress,identity:identity,registries:properties.configuration.registries,secrets:properties.configuration.secrets[].{name:name,keyVaultUrl:keyVaultUrl,identity:identity},scale:properties.template.scale,containers:properties.template.containers[].{name:name,image:image,env:env},traffic:properties.configuration.ingress.traffic}")

    def model_grant(self):
        self.group.preflight("write")
        principal = self.cli("identity", "show", "--subscription", self.target.subscription_id,
            "--resource-group", self.target.resource_group, "--name", self.config["names"]["identity"], "--query", "principalId")
        scope = f"/subscriptions/{self.target.subscription_id}/resourceGroups/personal-llm/providers/Microsoft.CognitiveServices/accounts/{self.config['model_account']}"
        role = "5e0bd9bd-7b93-4f28-af87-19fc36ad61bd"
        existing = self.cli("role", "assignment", "list", "--subscription", self.target.subscription_id,
            "--assignee", principal, "--scope", scope, "--query", "[].{id:id,principalId:principalId,scope:scope,roleDefinitionId:roleDefinitionId}")
        matched = [item for item in existing if item["scope"].lower() == scope.lower() and item["roleDefinitionId"].endswith("/" + role)]
        if not matched:
            self.cli("role", "assignment", "create", "--subscription", self.target.subscription_id,
                "--assignee-object-id", principal, "--assignee-principal-type", "ServicePrincipal", "--scope", scope,
                "--role", role, "--name", str(uuid.uuid5(uuid.NAMESPACE_URL, scope + principal + role)),
                "--query", "{id:id,principalId:principalId,scope:scope,roleDefinitionId:roleDefinitionId}")
        readback = self.cli("role", "assignment", "list", "--subscription", self.target.subscription_id,
            "--assignee", principal, "--scope", scope, "--query", "[].{id:id,principalId:principalId,scope:scope,roleDefinitionId:roleDefinitionId}")
        verified = [item for item in readback if item["scope"].lower() == scope.lower() and item["principalId"] == principal and item["roleDefinitionId"].endswith("/" + role)]
        if len(verified) != 1:
            raise DeploymentError("Exact model role readback failed")
        return {"status": "model-grant-verified", "grant": verified[0], "model_modified": False,
                "cloud_mutations": int(not matched)}

    def open_ingress(self, private_receipt, ingestion_receipt):
        self.group.preflight("write")
        private = json.loads(private_receipt.read_text())
        ingestion = json.loads(ingestion_receipt.read_text())
        observations = [json.loads(line) for line in private.get("probe", {}).get("output", "").splitlines() if line.startswith("{")]
        if (private.get("status") != "private-verified" or not observations or observations[-1].get("status") != "verified"
                or not {"state", "tables", "anonymous"}.issubset(observations[-1])):
            raise DeploymentError("Complete private acceptance receipt required")
        passes = []
        for line in ingestion.get("logs", {}).get("output", "").splitlines():
            if "{\"status\"" in line:
                item = json.loads(line[line.index('{"status"'):])
                if "stores" in item:
                    passes.append(item)
        if ([item.get("pass") for item in passes] != [1, 2] or any(item.get("status") != "verified"
                or item.get("package_sha256") != self.config["package_sha256"] for item in passes)
                or passes[0]["stores"] != passes[1]["stores"] or passes[0]["graph"] != passes[1]["graph"]):
            raise DeploymentError("Two matching real ingestion readbacks required")
        runtime = self.app_status()
        if runtime["revision"] != runtime["readyRevision"] or runtime["containers"] != private["runtime"]["containers"]:
            raise DeploymentError("Current ready app differs from private accepted artifact")
        self.cli("containerapp", "ingress", "enable", "--subscription", self.target.subscription_id,
            "--resource-group", self.target.resource_group, "--name", self.config["names"]["app"],
            "--type", "external", "--target-port", "8080", "--transport", "auto", "--allow-insecure", "false")
        observed = self.app_status()
        if observed["ingress"].get("external") is not True or observed["ingress"].get("allowInsecure") is not False:
            raise DeploymentError("Protected ingress readback mismatch")
        return observed

    def close_ingress(self):
        self.cli("containerapp", "ingress", "disable", "--subscription", self.target.subscription_id,
            "--resource-group", self.target.resource_group, "--name", self.config["names"]["app"])
        return self.app_status()

    def inventory(self):
        self.group.preflight("read")
        snapshot = self.group.snapshot()
        names = self.config["names"]
        common = ("--subscription", self.target.subscription_id, "--resource-group", self.target.resource_group)
        accounts = {}
        for kind in ("cosmos", "gremlin"):
            account = self.cli("cosmosdb", "show", *common, "--name", names[kind],
                "--query", "{id:id,name:name,state:provisioningState,kind:kind,capabilities:capabilities,locations:locations,disableLocalAuth:disableLocalAuth,publicNetworkAccess:publicNetworkAccess,consistency:consistencyPolicy}")
            if not any(item["name"] == "EnableServerless" for item in account["capabilities"]):
                raise DeploymentError("Serverless account configuration drift")
            if kind == "cosmos" and account.get("disableLocalAuth") is not True:
                raise DeploymentError("NoSQL local authentication drift")
            accounts[kind] = account
        registry = self.cli("acr", "show", *common, "--name", names["registry"],
            "--query", "{id:id,sku:sku,adminUserEnabled:adminUserEnabled,loginServer:loginServer}")
        search = self.cli("search", "service", "show", *common, "--name", names["search"],
            "--query", "{id:id,sku:sku,replicas:replicaCount,partitions:partitionCount,disableLocalAuth:disableLocalAuth,status:status}")
        storage = self.cli("storage", "account", "show", *common, "--name", names["storage"],
            "--query", "{id:id,sku:sku,allowSharedKeyAccess:allowSharedKeyAccess,allowBlobPublicAccess:allowBlobPublicAccess,minimumTlsVersion:minimumTlsVersion}")
        vault = self.cli("keyvault", "show", *common, "--name", names["vault"],
            "--query", "{id:id,sku:properties.sku,rbac:properties.enableRbacAuthorization,purgeProtection:properties.enablePurgeProtection,softDelete:properties.enableSoftDelete}")
        if registry["sku"]["name"] != "Basic" or registry["adminUserEnabled"] is not False:
            raise DeploymentError("Registry security/SKU drift")
        if search["sku"]["name"].lower() != "basic" or search["disableLocalAuth"] is not True:
            raise DeploymentError("Search security/SKU drift")
        if storage["allowSharedKeyAccess"] is not False or storage["allowBlobPublicAccess"] is not False:
            raise DeploymentError("Storage authentication drift")
        if not all(vault[key] is True for key in ("rbac", "purgeProtection", "softDelete")):
            raise DeploymentError("Key Vault protection drift")
        identity = self.cli("identity", "show", *common, "--name", names["identity"],
            "--query", "{id:id,principalId:principalId,clientId:clientId}")
        roles = self.cli("role", "assignment", "list", "--subscription", self.target.subscription_id,
            "--assignee", identity["principalId"], "--all", "--query", "[].{id:id,scope:scope,roleDefinitionId:roleDefinitionId,principalId:principalId}")
        allowed = {"7f951dda-4ed3-4680-a7ca-43fe172d538d", "4633458b-17de-408a-b874-0445c86b69e6",
                   "1407120a-92aa-4202-b7e9-c0e197c71c8f", "0a9a7e1f-b9d0-4cc4-a60d-0319b160aaa3", "5e0bd9bd-7b93-4f28-af87-19fc36ad61bd"}
        if any(item["roleDefinitionId"].split("/")[-1] not in allowed for item in roles):
            raise DeploymentError("Unexpected runtime Azure role; no automatic removal")
        cosmos_roles = self.cli("cosmosdb", "sql", "role", "assignment", "list", *common, "--account-name", names["cosmos"],
            "--query", "[].{id:id,scope:scope,roleDefinitionId:roleDefinitionId,principalId:principalId}")
        runtime = self.app_status()
        if runtime["scale"]["maxReplicas"] != 1 or runtime["ingress"]["allowInsecure"] or not runtime["readyRevision"]:
            raise DeploymentError("App readiness/scale/HTTPS drift")
        return {"status": "inventory-verified", "inventory": snapshot, "accounts": accounts,
                "registry": registry, "search": search, "storage": storage, "vault": vault,
                "runtime_identity": identity, "runtime_roles": roles, "cosmos_roles": cosmos_roles,
                "runtime": runtime, "actual_cost": "unknown; retail/billing API not queried", "cloud_mutations": 0}

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
        owned = {item["name"] for item in self.group.snapshot()["resources"]} if self.group.exists() else set()
        availability = {}
        for key in ("cosmos", "gremlin"):
            if names[key] in owned:
                availability[key] = "existing-owned"
                continue
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
            if names[key] in owned:
                availability[key] = "existing-owned"
                continue
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
        return {"status": "preflight-read", "account": account, "group_present": present, "existing": existing,
                "providers": {name: states[name] for name in PROVIDERS}, "policies": policies,
                "locks": locks, "model": model, "directory_policy": directory_policy,
                "reported_deployment_actions": list(REQUIRED_ACTIONS), "actual_cost": "unknown",
                "limits": ["Reported permissions are not proof of effective access; actual provider/data acceptance is separate.",
                           "Interactive human sign-in and exact cost are not established by preflight."],
                "cloud_mutations": 0, "effective_access_complete": False}


def main() -> int:
    parser = argparse.ArgumentParser(description="Investigation deployment preflight; no resources provisioned until release gates pass.")
    parser.add_argument("action", choices=("plan", "preflight", "constraints", "check", "capture", "validate-infra", "provision-infra", "status", "inventory", "package", "signer", "register", "build", "build-status", "private-release", "private-verify", "graph-probe", "app-status", "model-grant", "ingest", "ingest-status", "ingest-logs", "browser-setup", "browser", "restart-verify", "release", "verify", "seal"))
    parser.add_argument("--acceptance-receipt", type=Path)
    parser.add_argument("--private-receipt", type=Path)
    parser.add_argument("--ingestion-receipt", type=Path)
    parser.add_argument("--model", action="store_true")
    parser.add_argument("--profile-write", action="store_true")
    parser.add_argument("--build-receipt", type=Path)
    parser.add_argument("--execution")
    parser.add_argument("--run-id")
    parser.add_argument("--package-receipt", type=Path)
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
        if arguments[:2] in {("group", "create"), ("acr", "build")} or arguments[:3] == ("deployment", "group", "create") or arguments[:3] in {("rest", "--method", "post"), ("rest", "--method", "patch")}:
            result["cloud_mutations"] = "submitted; inspect command readbacks"
            save_json(evidence / f"{invocation}-{len(result['commands']) + 1:03d}-submitted.json", command)
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
        if options.action == "browser-setup":
            target = Path.home() / ".local/state/agentcraft/rg-agentcraft-dev/browser-runtime"
            command = [str(options.python.absolute()), "-m", "pip", "install", "--disable-pip-version-check",
                       "--target", str(target), "playwright==1.55.0"]
            completed = subprocess.run(command, capture_output=True, text=True, timeout=180)
            result.update(status="browser-ready" if completed.returncode == 0 else "blocked", argv=command,
                          exit_code=completed.returncode, output=safe_diagnostic(completed.stdout + completed.stderr),
                          runtime_path=str(target), virtualenv_created=False)
        elif options.action == "plan":
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
            elif options.action == "inventory":
                result.update(deployment.inventory())
            elif options.action == "browser":
                from investigation_verify import browser_probe
                deployment.group.preflight("read")
                result.update(status="browser-verified", browser=browser_probe(options.config, evidence))
            elif options.action == "restart-verify":
                from investigation_verify import restart_probe
                deployment.group.preflight("write")
                if options.acceptance_receipt is None:
                    raise DeploymentError("Exact prior --acceptance-receipt required")
                result.update(status="restart-verified", restart=restart_probe(config, options.acceptance_receipt, logged_cli),
                              cloud_mutations="owned application revision restarted")
            elif options.action in {"release", "verify"}:
                from investigation_verify import external_probe
                if options.action == "release":
                    if options.private_receipt is None or options.ingestion_receipt is None:
                        raise DeploymentError("Private and ingestion acceptance receipts required")
                    result["runtime"] = deployment.open_ingress(options.private_receipt, options.ingestion_receipt)
                    result["cloud_mutations"] = "external ingress enabled after private gates"
                else:
                    deployment.group.preflight("read")
                try:
                    def progress(item):
                        save_json(evidence / f"{invocation}-request-{uuid.uuid4().hex}.json", {"observed_at": utc(), **item})
                    result.update(status="external-verified", acceptance=external_probe(options.config, model=options.model,
                                  profile_write=options.profile_write, progress=progress),
                                  url=config["runtime"]["origin"])
                except Exception as error:
                    result["failed_check_type"] = type(error).__name__
                    result["closed_ingress"] = deployment.close_ingress()
                    raise DeploymentError("External acceptance failed; ingress closed; inspect request receipts") from None
            elif options.action == "model-grant":
                result.update(deployment.model_grant())
            elif options.action == "private-release":
                if options.build_receipt is None:
                    raise DeploymentError("Exact --build-receipt required")
                result.update(deployment.private_release(options.build_receipt))
            elif options.action == "app-status":
                deployment.group.preflight("read")
                result.update(status="app-read-back", runtime=deployment.app_status())
            elif options.action == "private-verify":
                deployment.group.preflight("read")
                runtime = deployment.app_status()
                if runtime["ingress"]["external"] or runtime["revision"] != runtime["readyRevision"]:
                    raise DeploymentError("Private ready revision required")
                probe = logged_cli("containerapp", "exec", "--subscription", config["subscription_id"],
                    "--resource-group", config["resource_group"], "--name", config["names"]["app"],
                    "--container", "app", "--command", "python /workspace/deploy/investigation_verify.py private")
                observations = [json.loads(line) for line in probe["output"].splitlines() if line.startswith("{")]
                if not observations or observations[-1].get("status") != "verified" or not {"state", "tables", "anonymous"}.issubset(observations[-1]):
                    raise DeploymentError("Private state/auth probe did not verify")
                result.update(status="private-verified", probe=probe, observation=observations[-1], runtime=runtime)
            elif options.action == "graph-probe":
                deployment.group.preflight("read")
                code = "import asyncio,json,logging\nlogging.disable(logging.CRITICAL)\nfrom app.cybereye.backend.main import app,lifespan\nasync def probe():\n async with lifespan(app):\n  print(json.dumps(await app.state.graph.status()))\nasyncio.run(probe())"
                probe = logged_cli("containerapp", "exec", "--subscription", config["subscription_id"],
                    "--resource-group", config["resource_group"], "--name", config["names"]["app"],
                    "--container", "app", "--command", "python -c exec(bytes.fromhex('" + code.encode().hex() + "'))")
                result.update(status="graph-read-back", probe=probe)
            elif options.action in {"ingest", "ingest-status", "ingest-logs"}:
                deployment.group.preflight("write" if options.action == "ingest" else "read")
                common = ("--subscription", config["subscription_id"], "--resource-group", config["resource_group"],
                          "--name", "agentcraft-dev-ingest")
                if options.action == "ingest":
                    result.update(status="ingestion-submitted", execution=logged_cli("containerapp", "job", "start", *common,
                        "--query", "{name:name,id:id}"), cloud_mutations="ingestion job execution; outcome pending")
                elif options.action == "ingest-status":
                    result.update(status="ingestion-read-back", executions=logged_cli("containerapp", "job", "execution", "list", *common,
                        "--query", "[].{name:name,status:properties.status,start:properties.startTime,end:properties.endTime}"))
                else:
                    if not options.execution or not re.fullmatch(r"agentcraft-dev-ingest-[a-z0-9]+", options.execution):
                        raise DeploymentError("Exact owned --execution required")
                    result.update(status="ingestion-logs-read", logs=logged_cli("containerapp", "job", "logs", "show", *common,
                        "--execution", options.execution, "--container", "ingest", "--tail", "30", "--format", "text"))
            elif options.action == "build-status":
                deployment.group.preflight("read")
                if not options.run_id or not re.fullmatch(r"[a-z0-9]{1,30}", options.run_id):
                    raise DeploymentError("Exact ACR --run-id required")
                common = ("--registry", config["names"]["registry"], "--run-id", options.run_id,
                          "--subscription", config["subscription_id"])
                result.update(status="build-read-back",
                    build=logged_cli("acr", "task", "show-run", *common, "--query", "{id:runId,status:status,finishTime:finishTime}"),
                    logs=logged_cli("acr", "task", "logs", *common))
            elif options.action == "register":
                result.update(deployment.registration())
                config.setdefault("runtime", {}).update(result["runtime"])
                options.config.write_text(json.dumps(config, indent=2) + "\n")
                if load_config(options.config) != config:
                    raise DeploymentError("Registration config readback mismatch")
            elif options.action == "build":
                if options.package_receipt is None:
                    raise DeploymentError("Build requires exact --package-receipt")
                result.update(deployment.build(options.package_receipt, invocation))
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