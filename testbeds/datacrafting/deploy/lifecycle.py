from datetime import datetime, timezone
from pathlib import Path
from hashlib import sha256
from time import monotonic
import argparse
import fnmatch
import json
import re
import shutil
import subprocess
import sys
from uuid import UUID, uuid4
import zipfile

from azure.core import PipelineClient
from azure.core.pipeline.policies import BearerTokenCredentialPolicy, RequestIdPolicy, RetryPolicy
from azure.core.polling import LROPoller
from azure.core.polling.base_polling import LROBasePolling, OperationResourcePolling
from azure.core.rest import HttpRequest
from azure.identity import AzureCliCredential


ROOT = Path(__file__).resolve().parent
TARGET_PATH = ROOT / "env" / "experiment.json"
FROZEN_SUBSCRIPTION = "67255afe-8670-4401-a1b8-df6ca63a3516"
FROZEN_TENANT = "c79ab2bb-79cb-47f1-b4da-b6852fe45ff7"
FROZEN_GROUP = "rg-agentcraft-datacrafting-20260916"
CLI_CLIENT_ID = "04b07795-8ddb-461a-bbee-02f9e1bf7b46"
GRAPH = "https://graph.microsoft.com/v1.0"
ARM = "https://management.azure.com"
IDENTITY_PATH = ROOT / "env" / "identity.json"
sys.path.insert(0, str(ROOT.parent / "azure-extraction"))
CONFIG_KEYS = {
    "subscription_id", "tenant_id", "cloud", "resource_group", "owner", "location", "operator_principal_id",
    "api_display_name", "api_scope_id", "network_name", "private_endpoint_name", "storage_name", "function_name",
    "identity_name", "plan_name", "document_intelligence_name", "content_understanding_name", "logs_name",
}


def command(argv: list[str]) -> object:
    result = subprocess.run(argv, capture_output=True, text=True, check=False)
    if result.returncode:
        record("command-refusal", {"argv": argv, "exit_code": result.returncode, "stderr": result.stderr, "stdout": result.stdout})
        raise RuntimeError(f"Command failed ({result.returncode}): {' '.join(argv)}\n{result.stderr[-5000:]}")
    return json.loads(result.stdout) if result.stdout.strip() else None


def validate_target(config: dict) -> dict:
    if set(config) != CONFIG_KEYS:
        raise RuntimeError("Unknown, missing, or credential-shaped target fields are refused")
    if (config["subscription_id"], config["tenant_id"], config["resource_group"], config["cloud"]) != (
        FROZEN_SUBSCRIPTION, FROZEN_TENANT, FROZEN_GROUP, "AzureCloud"
    ):
        raise RuntimeError("Target differs from the authorized experiment")
    for key, value in config.items():
        if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9-]{1,90}", value):
            raise RuntimeError(f"Unsafe target value: {key}")
    for key in ("subscription_id", "tenant_id", "operator_principal_id", "api_scope_id"):
        if str(UUID(config[key])) != config[key]:
            raise RuntimeError(f"Noncanonical identity: {key}")
    if config["owner"] != "agentcraft-datacrafting-20260916" or config["location"] != "eastus":
        raise RuntimeError("Ownership or verified location changed")
    return config


def target() -> dict:
    return validate_target(json.loads(TARGET_PATH.read_text()))


def azure(config: dict, *arguments: str) -> object:
    return command(["az", *arguments, "--subscription", config["subscription_id"], "--only-show-errors", "-o", "json"])


def current_account(config: dict) -> dict:
    account = command(["az", "account", "show", "--query", "{subscriptionId:id,tenantId:tenantId,state:state,cloud:environmentName}", "-o", "json"])
    if account != {"subscriptionId": config["subscription_id"], "tenantId": config["tenant_id"], "state": "Enabled", "cloud": config["cloud"]}:
        raise RuntimeError("Active CLI account mismatch; shared account will not be switched")
    return account


def record(name: str, value: object) -> Path:
    directory = ROOT / "records"
    directory.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    path = directory / f"{stamp}-{name}.json"
    with path.open("x") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")
    print(path.relative_to(ROOT.parent))
    return path


def save_state(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def group_id(config: dict) -> str:
    return f"/subscriptions/{config['subscription_id']}/resourceGroups/{config['resource_group']}"


def assert_group_owned(config: dict, group: dict) -> None:
    if group.get("id", "").lower() != group_id(config).lower() or (group.get("tags") or {}).get("owner") != config["owner"]:
        raise RuntimeError("Existing resource group is not owned by this experiment")


def expected_resources(config: dict) -> dict[str, str]:
    return {
        "microsoft.managedidentity/userassignedidentities": config["identity_name"],
        "microsoft.network/virtualnetworks": config["network_name"],
        "microsoft.network/privateendpoints": config["private_endpoint_name"],
        "microsoft.network/privatednszones": "privatelink.blob.core.windows.net",
        "microsoft.network/privatednszones/virtualnetworklinks": "privatelink.blob.core.windows.net/datacrafting-network",
        "microsoft.storage/storageaccounts": config["storage_name"],
        "microsoft.web/serverfarms": config["plan_name"],
        "microsoft.web/sites": config["function_name"],
        "microsoft.operationalinsights/workspaces": config["logs_name"],
    }


def assert_resources_owned(config: dict, resources: list) -> None:
    expected = expected_resources(config)
    for resource in resources:
        resource_type = resource["type"].lower()
        if not resource["id"].lower().startswith(group_id(config).lower() + "/providers/"):
            raise RuntimeError("Resource escaped the authorized group")
        if resource_type == "microsoft.cognitiveservices/accounts":
            known = resource["name"] in {config["document_intelligence_name"], config["content_understanding_name"]}
        elif resource_type == "microsoft.network/networkinterfaces":
            known = resource.get("properties", {}).get("privateEndpoint", {}).get("id", "").lower() == (
                group_id(config) + "/providers/Microsoft.Network/privateEndpoints/" + config["private_endpoint_name"]
            ).lower()
        else:
            known = expected.get(resource_type) == resource["name"]
        if not known or (resource_type != "microsoft.network/networkinterfaces" and resource.get("tags", {}).get("owner") != config["owner"]):
            raise RuntimeError(f"Unknown or unowned resource: {resource['id']}")


def existing_resources(config: dict) -> list:
    if not azure(config, "group", "exists", "--name", config["resource_group"]):
        return []
    assert_group_owned(config, azure(config, "group", "show", "--name", config["resource_group"]))
    resources = azure(config, "resource", "list", "--resource-group", config["resource_group"])
    for resource in resources:
        if resource["type"].lower() == "microsoft.network/networkinterfaces":
            full = azure(config, "resource", "show", "--ids", resource["id"], "--api-version", "2024-05-01")
            resource["properties"] = full["properties"]
    assert_resources_owned(config, resources)
    return resources


def assert_reference_host_dependencies(config: dict, group: dict, resources: list) -> dict:
    validate_target(config)
    assert_group_owned(config, group)
    expected = expected_resources(config) | {"microsoft.cognitiveservices/accounts": config["content_understanding_name"]}
    prefix = group_id(config) + "/providers/"
    required = {}
    for resource_type, name in expected.items():
        namespace, *types = resource_type.split("/")
        suffix = "/".join(part for pair in zip(types, name.split("/"), strict=True) for part in pair)
        required[(prefix + namespace + "/" + suffix).lower()] = (resource_type, name)
    seen = set()
    validated = []
    untouched = []
    for resource in resources:
        resource_id = resource.get("id", "").lower()
        if not resource_id.startswith(prefix.lower()):
            raise RuntimeError("Reference-host inventory escaped the authorized group")
        if resource_id in seen:
            raise RuntimeError(f"Duplicate reference-host inventory resource: {resource['id']}")
        seen.add(resource_id)
        identity = (resource.get("type", "").lower(), resource.get("name"))
        if resource_id in required:
            if identity != required[resource_id] or (resource.get("tags") or {}).get("owner") != config["owner"]:
                raise RuntimeError(f"Mismatched or unowned reference-host dependency: {resource['id']}")
            validated.append(resource["id"])
        elif identity in required.values():
            raise RuntimeError(f"Reference-host dependency ID mismatch: {resource['id']}")
        else:
            untouched.append({"resource_id": resource["id"], "type": resource.get("type"), "name": resource.get("name"),
                "owner_tag": (resource.get("tags") or {}).get("owner"), "status": "observed-not-owned/unmodified",
                "ownership_scope": "outside reference-host release", "deletion_authorized": False})
    missing = sorted(set(required) - seen)
    if missing:
        raise RuntimeError("Missing exact reference-host dependencies: " + ", ".join(missing))
    return {"scope": "exact-reference-host-dependencies", "required_resource_ids": validated,
        "observed_not_owned": untouched, "whole_group_lifecycle_ownership_validated": False, "deletion_authorized": False,
        "release_mutation_set": [{"resource_id": prefix + "Microsoft.Web/sites/" + config["function_name"],
                                  "operation": "publish-function-package-only"}]}


def rest(config: dict, method: str, url: str, body: dict | None = None) -> object:
    arguments = ["rest", "--method", method, "--url", url]
    if body is not None:
        arguments.extend(["--body", json.dumps(body)])
    return azure(config, *arguments)


def preflight(config: dict) -> dict:
    validate_target(config)
    evidence = {"observed_at": datetime.now(timezone.utc).isoformat(), "account": current_account(config), "cloud_mutations": []}
    evidence["resources"] = existing_resources(config)
    evidence["providers"] = {namespace: azure(config, "provider", "show", "--namespace", namespace, "--query", "registrationState")
        for namespace in ("Microsoft.Web", "Microsoft.Storage", "Microsoft.ManagedIdentity", "Microsoft.CognitiveServices", "Microsoft.Network", "Microsoft.App", "Microsoft.OperationalInsights", "Microsoft.Insights")}
    if any(state != "Registered" for state in evidence["providers"].values()):
        record("provider-registration-refusal", evidence)
        raise RuntimeError("A required provider is not registered; registration must be explicitly recorded before apply")
    evidence["skus"] = {kind: azure(config, "cognitiveservices", "account", "list-skus", "--kind", kind, "--location", config["location"])
        for kind in ("AIServices",)}
    for kind, skus in evidence["skus"].items():
        if not any(item.get("name") == "S0" or item.get("sku", {}).get("name") == "S0" for item in skus):
            record("preflight-refusal", evidence)
            raise RuntimeError(f"S0 not reported available for {kind} in {config['location']}")
    evidence["runtimes"] = azure(config, "functionapp", "list-flexconsumption-runtimes", "--location", config["location"], "--runtime", "python")
    if "3.12" not in json.dumps(evidence["runtimes"]):
        raise RuntimeError("Python 3.12 Flex runtime unavailable in the frozen region")
    permissions_url = f"{ARM}/subscriptions/{config['subscription_id']}/providers/Microsoft.Authorization/permissions?api-version=2022-04-01"
    evidence["permissions"] = rest(config, "GET", permissions_url)
    permissions = evidence["permissions"].get("value", [])
    for required in ("Microsoft.Resources/subscriptions/resourceGroups/write", "Microsoft.Resources/deployments/write", "Microsoft.Authorization/roleAssignments/write"):
        if not any(any(fnmatch.fnmatchcase(required.lower(), action.lower()) for action in item.get("actions", []))
                   and not any(fnmatch.fnmatchcase(required.lower(), denied.lower()) for denied in item.get("notActions", [])) for item in permissions):
            raise RuntimeError(f"Required permission not observed: {required}")
    if not evidence["resources"]:
        evidence["storage_name"] = azure(config, "storage", "account", "check-name", "--name", config["storage_name"])
        if not evidence["storage_name"]["nameAvailable"]:
            raise RuntimeError("Storage name collision")
        evidence["function_name"] = rest(config, "POST", f"{ARM}/subscriptions/{config['subscription_id']}/providers/Microsoft.Web/checknameavailability?api-version=2024-04-01",
            {"name": config["function_name"], "type": "Microsoft.Web/sites", "isFqdn": False})
        if not evidence["function_name"]["nameAvailable"]:
            raise RuntimeError("Function name collision")
    evidence["application_candidates"] = rest(config, "GET", f"{GRAPH}/applications?$filter=displayName%20eq%20'{config['api_display_name']}'&$select=id,appId,displayName,tags")
    candidates = evidence["application_candidates"].get("value", [])
    if candidates:
        owned = json.loads(IDENTITY_PATH.read_text()) if IDENTITY_PATH.exists() else {}
        if len(candidates) != 1 or candidates[0]["id"] != owned.get("application_object_id") or config["owner"] not in candidates[0].get("tags", []):
            raise RuntimeError("Unknown existing Entra application; adoption refused")
    record("preflight", evidence)
    print("PASS: frozen target, ownership, registered providers, S0 SKUs, Python 3.12, permissions, and name checks")
    return evidence


def parameters(config: dict) -> Path:
    identity = json.loads(IDENTITY_PATH.read_text()) if IDENTITY_PATH.exists() else {}
    activate = False
    if any(resource["type"].lower() == "microsoft.web/sites" for resource in existing_resources(config)):
        site_id = group_id(config) + "/providers/Microsoft.Web/sites/" + config["function_name"]
        site = rest(config, "GET", f"{ARM}{site_id}?api-version=2024-04-01")
        activate = site["properties"].get("enabled") is True and site["properties"].get("publicNetworkAccess") == "Enabled"
        if activate:
            validate_auth(config, identity, rest(config, "GET", f"{ARM}{site_id}/config/authsettingsV2?api-version=2024-04-01"))
    build = ROOT / "build"
    build.mkdir(exist_ok=True)
    path = build / "parameters.json"
    save_state(path, {"$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentParameters.json#", "contentVersion": "1.0.0.0",
        "parameters": {"target": {"value": config}, "apiClientId": {"value": identity.get("api_client_id", "11111111-1111-4111-8111-111111111111")}, "activate": {"value": activate}}})
    return path


def plan(config: dict) -> dict:
    compile_template()
    preflight(config)
    result = azure(config, "deployment", "sub", "what-if", "--name", "datacrafting-20260916", "--location", config["location"],
        "--template-file", str(ROOT / "infra" / "main.bicep"), "--parameters", "@" + str(parameters(config)), "--no-pretty-print")
    record("what-if", result)
    print("PASS: native what-if completed; no resource creation requested")
    return result


def configure_caller(config: dict) -> dict:
    compile_template()
    preflight(config)
    if IDENTITY_PATH.exists():
        state = json.loads(IDENTITY_PATH.read_text())
        application = rest(config, "GET", f"{GRAPH}/applications/{state['application_object_id']}")
        if application["appId"] != state["api_client_id"] or config["owner"] not in application.get("tags", []):
            raise RuntimeError("Existing application identity differs from owned ledger")
    else:
        payload = {
            "displayName": config["api_display_name"], "signInAudience": "AzureADMyOrg", "tags": [config["owner"]],
            "notes": "Two authorized datacrafting PDFs; secret-free API registration owned by experiment lifecycle.",
            "api": {"requestedAccessTokenVersion": 2, "oauth2PermissionScopes": [{
                "id": config["api_scope_id"], "value": "access_as_user", "type": "User", "isEnabled": True,
                "adminConsentDisplayName": "Call the datacrafting PDF experiment", "adminConsentDescription": "Call only this experiment's authenticated extraction functions.",
                "userConsentDisplayName": "Call the datacrafting PDF experiment", "userConsentDescription": "Call only this experiment's authenticated extraction functions."
            }], "preAuthorizedApplications": [{"appId": CLI_CLIENT_ID, "delegatedPermissionIds": [config["api_scope_id"]]}]},
        }
        record("application-create-intent", {"target": config["api_display_name"], "payload": payload})
        application = rest(config, "POST", f"{GRAPH}/applications", payload)
        state = {"owner": config["owner"], "tenant_id": config["tenant_id"], "application_object_id": application["id"], "api_client_id": application["appId"]}
        save_state(IDENTITY_PATH, state)
    application = rest(config, "GET", f"{GRAPH}/applications/{state['application_object_id']}")
    expected_uri = f"api://{state['api_client_id']}"
    if application.get("identifierUris") != [expected_uri]:
        if application.get("identifierUris"):
            raise RuntimeError("Unexpected identifier URI on owned API")
        rest(config, "PATCH", f"{GRAPH}/applications/{state['application_object_id']}", {"identifierUris": [expected_uri]})
    service_principals = rest(config, "GET", f"{GRAPH}/servicePrincipals?$filter=appId%20eq%20'{state['api_client_id']}'&$select=id,appId,tags")["value"]
    if not service_principals:
        service_principal = rest(config, "POST", f"{GRAPH}/servicePrincipals", {"appId": state["api_client_id"], "tags": [config["owner"]]})
    elif len(service_principals) == 1:
        service_principal = service_principals[0]
    else:
        raise RuntimeError("Ambiguous dedicated API service principal")
    state["service_principal_id"] = service_principal["id"]
    save_state(IDENTITY_PATH, state)
    application = rest(config, "GET", f"{GRAPH}/applications/{state['application_object_id']}?$select=id,appId,identifierUris,api,signInAudience,tags,passwordCredentials,keyCredentials")
    if application["identifierUris"] != [expected_uri] or application["api"]["requestedAccessTokenVersion"] != 2 or application["passwordCredentials"] or application["keyCredentials"]:
        raise RuntimeError("Dedicated API registration readback failed")
    record("caller-registration", {"state": state, "application": application})
    print("PASS: experiment-owned secret-free Entra API registration read back")
    return state


def check_caller(config: dict) -> dict:
    from azure.identity import AzureCliCredential
    from azure_extraction.auth import JwtGate

    current_account(config)
    identity = json.loads(IDENTITY_PATH.read_text())
    credential = AzureCliCredential(subscription=config["subscription_id"], process_timeout=30)
    token = credential.get_token(f"api://{identity['api_client_id']}/.default")
    claims = JwtGate(config["tenant_id"], config["operator_principal_id"], identity["api_client_id"]).authenticate("Bearer " + token.token)
    evidence = {"observed_at": datetime.now(timezone.utc).isoformat(), "tenant_id": claims["tid"], "principal_id": claims["oid"],
                "audience": claims["aud"], "issuer": claims["iss"], "client_id": claims["azp"], "scope": claims["scp"],
                "signature_verified": True, "credential_values_recorded": False}
    record("caller-token-check", evidence)
    print("PASS: operator Entra token has verified signature, experiment audience, tenant, principal, client, and scope")
    return evidence


def apply(config: dict) -> None:
    if not IDENTITY_PATH.exists():
        raise RuntimeError("Run configure-caller after a successful plan before applying resources")
    check_caller(config)
    plan(config)
    result = azure(config, "deployment", "sub", "create", "--name", "datacrafting-20260916", "--location", config["location"],
        "--template-file", str(ROOT / "infra" / "main.bicep"), "--parameters", "@" + str(parameters(config)))
    record("deployment", result)
    resources = existing_resources(config)
    record("resource-readback", {"group": azure(config, "group", "show", "--name", config["resource_group"]), "resources": resources})
    print("PASS: deployment returned and owned resource inventory read back; live extraction remains unverified")


def validate_auth(config: dict, identity: dict, auth: dict) -> None:
    properties = auth["properties"]
    provider = properties["identityProviders"]["azureActiveDirectory"]
    policy = provider["validation"]["defaultAuthorizationPolicy"]
    if (
        properties["platform"].get("enabled") is not True
        or properties["globalValidation"].get("requireAuthentication") is not True
        or properties["globalValidation"].get("unauthenticatedClientAction") != "Return401"
        or properties["globalValidation"].get("excludedPaths")
        or provider.get("enabled") is not True
        or provider["registration"]["clientId"] != identity["api_client_id"]
        or provider["registration"]["openIdIssuer"] != f"https://login.microsoftonline.com/{config['tenant_id']}/v2.0"
        or policy["allowedPrincipals"]["identities"] != [config["operator_principal_id"]]
        or policy["allowedApplications"] != [CLI_CLIENT_ID]
        or properties["login"]["tokenStore"].get("enabled") is not False
    ):
        raise RuntimeError("Native Entra authentication/authorization readback failed; activation refused")


def readback(config: dict) -> dict:
    current_account(config)
    group = azure(config, "group", "show", "--name", config["resource_group"])
    resources = azure(config, "resource", "list", "--resource-group", config["resource_group"])
    inventory = {"observed_at": datetime.now(timezone.utc).isoformat(), "group": group, "resources": resources,
                 "cloud_mutations": []}
    try:
        dependency_validation = assert_reference_host_dependencies(config, group, resources)
    except RuntimeError as error:
        record("reference-host-inventory-refusal", inventory | {"refusal": str(error)})
        raise
    record("reference-host-inventory", inventory | {"validation": dependency_validation})
    identity = json.loads(IDENTITY_PATH.read_text())
    prefix = group_id(config) + "/providers/"
    site_id = prefix + "Microsoft.Web/sites/" + config["function_name"]
    site = rest(config, "GET", f"{ARM}{site_id}?api-version=2024-04-01")
    auth = rest(config, "GET", f"{ARM}{site_id}/config/authsettingsV2?api-version=2024-04-01")
    validate_auth(config, identity, auth)
    workload = rest(config, "GET", f"{ARM}{prefix}Microsoft.ManagedIdentity/userAssignedIdentities/{config['identity_name']}?api-version=2023-01-31")
    workload_principal = workload["properties"]["principalId"]
    storage = rest(config, "GET", f"{ARM}{prefix}Microsoft.Storage/storageAccounts/{config['storage_name']}?api-version=2023-05-01")
    if storage["properties"].get("allowSharedKeyAccess") is not False or storage["properties"].get("publicNetworkAccess") != "Disabled" or storage["properties"].get("allowBlobPublicAccess") is not False:
        raise RuntimeError("Storage identity/network policy readback failed")
    service_accounts = {}
    assignments = []
    expected_grants = [(storage["id"], "b7e6dc6d-f1e8-4753-8033-0f276bb0955b")]
    for kind, name in (("cu", config["content_understanding_name"]),):
        service = rest(config, "GET", f"{ARM}{prefix}Microsoft.CognitiveServices/accounts/{name}?api-version=2025-06-01")
        if service["properties"].get("disableLocalAuth") is not True or service["sku"]["name"] != "S0":
            raise RuntimeError("Native service identity/SKU readback failed")
        service_accounts[kind] = service
        expected_grants.append((service["id"], "a97b65f3-24c7-4388-baec-2e87135dc908"))
    for scope, role_id in expected_grants:
        roles = azure(config, "role", "assignment", "list", "--scope", scope)
        owned_roles = [role for role in roles if role["scope"].lower() == scope.lower() and role["principalId"] == workload_principal]
        if len(owned_roles) != 1 or not owned_roles[0]["roleDefinitionId"].lower().endswith("/" + role_id):
            raise RuntimeError("Missing or excess workload role assignments at exact resource scope")
        assignments.extend(owned_roles)
    if workload["id"] not in site["identity"]["userAssignedIdentities"]:
        raise RuntimeError("Function is not assigned the expected workload identity")
    function_config = site["properties"]["functionAppConfig"]
    if function_config["deployment"]["storage"]["authentication"].get("type") != "UserAssignedIdentity":
        raise RuntimeError("Function deployment storage is not identity-authenticated")
    if function_config["scaleAndConcurrency"].get("alwaysReady"):
        raise RuntimeError("Unexpected always-ready instances")
    policies = {policy: rest(config, "GET", f"{ARM}{site_id}/basicPublishingCredentialsPolicies/{policy}?api-version=2024-04-01") for policy in ("scm", "ftp")}
    if any(policy["properties"]["allow"] is not False for policy in policies.values()):
        raise RuntimeError("Basic publishing credentials unexpectedly enabled")
    hostname = site["properties"]["defaultHostName"]
    if not hostname.startswith(config["function_name"]) or not hostname.endswith(".azurewebsites.net"):
        raise RuntimeError("Unexpected Function hostname")
    runtime = {key: value for key, value in config.items() if key != "document_intelligence_name"} | {
        "api_client_id": identity["api_client_id"], "function_host": hostname, "function_endpoint": "https://" + hostname,
        "cu_host": config["content_understanding_name"] + ".services.ai.azure.com",
        "workload_client_id": workload["properties"]["clientId"], "workload_principal_id": workload_principal,
        "function_id": site_id,
        "scm_host": next(host for host in site["properties"]["enabledHostNames"] if ".scm." in host),
    }
    save_state(ROOT / "env" / "runtime.json", runtime)
    evidence = {"observed_at": datetime.now(timezone.utc).isoformat(), "resources": resources, "site": site,
                "group": group, "reference_host_validation": dependency_validation,
                "auth": auth, "storage": storage, "workload_identity": workload, "service_accounts": service_accounts,
                "retired_allocations": [{"resource_id": resource["id"], "name": resource["name"],
                    "status": "retired-but-still-allocated", "runtime_dependency": False,
                    "deletion_authorization": "separate scoped operator approval required"}
                    for resource in resources if resource["type"].lower() == "microsoft.cognitiveservices/accounts"
                    and resource["name"] == config["document_intelligence_name"]],
                "role_assignments": assignments, "publishing_policies": policies, "configured_cost": {
                    "functions": "FC1, 512 MB, maximum 40 instances, HTTP concurrency 1, no always-ready instances",
                    "storage": "Standard_LRS, private blob endpoint", "document_intelligence": "retired; allocation inventory above; no teardown executed",
                    "content_understanding": "S0; no model deployments", "ongoing_cost_usd": "unknown"}}
    record("security-readback", evidence)
    print("PASS: exact Entra gate, CU/storage MI assignments, CU S0, private/keyless storage, and disabled basic publishing read back")
    return runtime


def run_tool(argv: list[str]) -> None:
    result = subprocess.run(argv, text=True, check=False)
    if result.returncode:
        raise RuntimeError(f"Local tool failed with exit {result.returncode}: {' '.join(argv)}")


def offline(test_pattern: str | None = None) -> None:
    from verify_results import verify_documentation

    run_tool(["uv", "run", "--frozen", "--project", str(ROOT.parent / "azure-extraction"), "python", "-m", "unittest", "discover",
              "-s", str(ROOT.parent / "azure-extraction" / "tests"), "-p", test_pattern or "test*.py", "-v"])
    if test_pattern:
        record("offline-targeted-verification", {"tests": "passed", "test_pattern": test_pattern, "cloud_mutations": []})
        print("PASS: focused offline tests; no cloud calls")
        return
    for method in ("content-understanding",):
        run_tool(["uv", "run", "--frozen", "--project", str(ROOT.parent / method), "python", str(ROOT.parent / method / "pipeline.py"), "--help"])
    documentation = verify_documentation(ROOT.parent)
    record("offline-verification", {"tests": "passed", "isolated_method_entrypoints": "passed", "documentation": documentation,
                                    "live_teardown_executed": False})
    print("PASS: offline tests, isolated CU entry point, skill name and local documentation links")


def cached_runtime(config: dict) -> dict:
    from azure_extraction.contracts import validate_endpoint

    validate_target(config)
    runtime = json.loads((ROOT / "env" / "runtime.json").read_text())
    if any(runtime.get(key) != value for key, value in config.items() if key != "document_intelligence_name"):
        raise RuntimeError("Cached runtime differs from the frozen owner target")
    if {"di_host", "document_intelligence_name"} & set(runtime):
        raise RuntimeError("Cached runtime still contains retired DI targets")
    identity = json.loads(IDENTITY_PATH.read_text())
    if runtime.get("api_client_id") != identity["api_client_id"]:
        raise RuntimeError("Cached runtime differs from the owned caller identity")
    if runtime.get("cu_host") != config["content_understanding_name"] + ".services.ai.azure.com" or runtime.get("function_id") != group_id(config) + "/providers/Microsoft.Web/sites/" + config["function_name"]:
        raise RuntimeError("Cached runtime service targets differ from the owned resources")
    if runtime.get("function_host") != config["function_name"] + ".azurewebsites.net" or runtime.get("scm_host") != config["function_name"] + ".scm.azurewebsites.net":
        raise RuntimeError("Cached Function/SCM hosts differ from the owned resources")
    validate_endpoint(runtime["function_endpoint"], runtime["function_host"])
    return runtime


def build_release(config: dict, local_only: bool = False) -> Path:
    runtime = cached_runtime(config) if local_only else readback(config)
    build = ROOT / "build" / ("release-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    package = build / "package"
    package.mkdir(parents=True)
    shared = ROOT.parent / "azure-extraction"
    requirements = package / "requirements.txt"
    run_tool(["uv", "export", "--frozen", "--project", str(shared), "--no-dev", "--no-emit-project", "--output-file", str(requirements), "--quiet"])
    run_tool(["uv", "pip", "install", "--python", sys.executable, "--target", str(package / ".python_packages" / "lib" / "site-packages"),
              "--requirements", str(requirements)])
    shutil.copyfile(shared / "function_app.py", package / "handler.py")
    shutil.copyfile(shared / "host.json", package / "host.json")
    bindings = json.loads((shared / "function-bindings.json").read_text())
    for name, binding in bindings.items():
        folder = package / name
        folder.mkdir()
        shutil.copyfile(shared / "function_entry.py", folder / "__init__.py")
        save_state(folder / "function.json", {"scriptFile": "__init__.py", "entryPoint": "main", "bindings": [
            {"type": "httpTrigger", "direction": "in", "name": "request", "authLevel": "anonymous", **binding},
            {"type": "http", "direction": "out", "name": "$return"},
        ]})
    code = package / "azure_extraction"
    code.mkdir()
    for source in (shared / "azure_extraction").glob("*.py"):
        shutil.copyfile(source, code / source.name)
    save_state(package / "experiment.json", runtime)
    manifest = json.loads((ROOT.parent / "source_data" / "manifest.json").read_text())
    save_state(package / "input-manifest.json", {"schema_version": 1, "documents": [
        {key: document[key] for key in ("id", "file", "sha256", "bytes")} for document in manifest["documents"]]})
    archive_path = build / "function.zip"
    with zipfile.ZipFile(archive_path, "x", zipfile.ZIP_DEFLATED) as archive:
        for source in sorted(package.rglob("*")):
            if source.is_file() and "__pycache__" not in source.parts and source.suffix != ".pyc":
                archive.write(source, source.relative_to(package))
        if any(name.lower().endswith(".pdf") for name in archive.namelist()):
            raise RuntimeError("Function package unexpectedly contains PDF binary duplicates")
    record("release-package", {"path": str(archive_path.relative_to(ROOT)), "bytes": archive_path.stat().st_size,
        "sha256": sha256(archive_path.read_bytes()).hexdigest(), "lock_sha256": sha256((shared / "uv.lock").read_bytes()).hexdigest(),
        "native_api": "SCM /api/publish?RemoteBuild=false", "dependency_install": "uv pip install from frozen uv export", "pdfs_in_package": 0,
        "local_only": local_only, "fresh_cloud_security_readback": not local_only, "release_requires_fresh_readback": True})
    save_state(ROOT / "build" / "release.json", {"archive": str(archive_path)})
    print("PASS: uv-locked Function ZIP built locally; no source PDFs packaged")
    return archive_path


class ScmOperation(OperationResourcePolling):
    def __init__(self, status_url: str):
        super().__init__()
        self.status_url = status_url

    def can_poll(self, pipeline_response):
        return True

    def set_initial_status(self, pipeline_response):
        return "InProgress"

    def get_polling_url(self):
        return self.status_url

    def get_final_get_url(self, pipeline_response):
        return None

    def get_status(self, pipeline_response):
        status = pipeline_response.http_response.json().get("status")
        if status not in {0, 1, 2, 3, 4}:
            raise RuntimeError("Unknown native SCM deployment state")
        return {0: "InProgress", 1: "InProgress", 2: "InProgress", 3: "Failed", 4: "Succeeded"}[status]


class ScmPolling(LROBasePolling):
    def __init__(self, status_url: str):
        super().__init__(timeout=5, lro_algorithms=[ScmOperation(status_url)])
        self.expected_url = status_url
        self.deadline = monotonic() + 900
        self.last_payload = None

    def request_status(self, status_link):
        if status_link != self.expected_url or monotonic() >= self.deadline:
            raise RuntimeError("SCM polling target or bounded deadline refused")
        result = super().request_status(status_link)
        self.last_payload = result.http_response.json()
        return result


def management_client(config: dict, endpoint: str) -> PipelineClient:
    return PipelineClient(base_url=endpoint, policies=[RequestIdPolicy(), RetryPolicy(retry_total=0),
        BearerTokenCredentialPolicy(AzureCliCredential(subscription=config["subscription_id"], process_timeout=30), "https://management.azure.com/.default")],
        connection_timeout=15, read_timeout=180)


def release(config: dict) -> None:
    check_package()
    runtime = readback(config)
    if not (ROOT / "build" / "release.json").exists():
        raise RuntimeError("Run build before publishing")
    archive = Path(json.loads((ROOT / "build" / "release.json").read_text())["archive"]).resolve()
    if not archive.is_relative_to((ROOT / "build").resolve()) or archive.name != "function.zip":
        raise RuntimeError("Release package path escaped its owned build root")
    site_url = f"{ARM}{runtime['function_id']}?api-version=2024-04-01"
    site = rest(config, "GET", site_url)
    if not site["properties"]["enabled"] or site["properties"].get("publicNetworkAccess") != "Enabled":
        raise RuntimeError("CU-only release requires the existing active Function; ingress/activation changes need separate operator authorization")
    endpoint = "https://" + runtime["scm_host"]
    client = management_client(config, endpoint)
    pending_path = ROOT / "build" / "pending-release.json"
    package_hash = sha256(archive.read_bytes()).hexdigest()
    if pending_path.exists():
        pending = json.loads(pending_path.read_text())
        if pending["status_url"] != endpoint + "/api/deployments/" + pending["deployment_id"] or not re.fullmatch(r"[a-zA-Z0-9-]{8,100}", pending["deployment_id"]):
            raise RuntimeError("Recorded deployment escaped the frozen SCM target")
        response = client.send_request(HttpRequest("GET", pending["status_url"]))
        observed = response.json() if response.status_code == 200 else {"http_status": response.status_code}
        record("prior-publish-readback", pending | {"native_status": observed})
        if response.status_code != 200 or response.json().get("status") in {0, 1, 2}:
            raise RuntimeError("Prior release is unconfirmed or still active; no duplicate publish")
        if observed.get("status") == 4 and pending["package_sha256"] == package_hash:
            save_state(ROOT / "build" / "published.json", pending | {"status": "succeeded"})
            print("PASS: existing native SCM deployment read back complete; identical package not republished")
            return
    record("publish-intent", {"scm_endpoint": endpoint, "package_sha256": package_hash, "remote_build": False, "authentication": "Entra ARM bearer"})
    initial = client.send_request(HttpRequest("POST", endpoint + "/api/publish?RemoteBuild=false&Deployer=agentcraft_uv",
        headers={"Content-Type": "application/zip", "Cache-Control": "no-cache"}, content=archive.read_bytes()), _return_pipeline_response=True)
    response = initial.http_response
    if response.status_code != 202:
        record("publish-refusal", {"status_code": response.status_code, "body": response.text()[:8000]})
        raise RuntimeError(f"Native SCM publish returned HTTP {response.status_code}; inspect before retrying")
    try:
        body = response.json()
    except ValueError:
        body = response.text()
    deployment_id = body.get("deploymentId", body.get("id")) if isinstance(body, dict) else body
    if not isinstance(deployment_id, str) or not re.fullmatch(r"[a-zA-Z0-9-]{8,100}", deployment_id):
        record("publish-unconfirmed", {"status_code": response.status_code, "body": body})
        raise RuntimeError("Native SCM returned an unexpected deployment identifier")
    status_url = endpoint + "/api/deployments/" + deployment_id
    pending = {"deployment_id": deployment_id, "status_url": status_url, "package_sha256": package_hash}
    save_state(pending_path, pending)
    polling = ScmPolling(status_url)
    poller = LROPoller(client, initial, lambda result: result.http_response.json(), polling)
    try:
        result = poller.result()
    finally:
        record("publish-status", pending | {"native_status": polling.last_payload})
    if result.get("status") != 4:
        raise RuntimeError("Native SCM deployment did not complete successfully")
    save_state(ROOT / "build" / "published.json", pending | {"status": "succeeded"})
    print("PASS: native SCM deployment completed using Entra bearer and the local uv bundle")


def verify_access(config: dict) -> dict:
    from azure_extraction.client import function_client
    from azure_extraction.contracts import METHODS
    import requests

    runtime = readback(config)
    client = function_client(runtime)
    endpoint = runtime["function_endpoint"]
    positive = client.send_request(HttpRequest("GET", endpoint + "/api/health"))
    evidence = {"observed_at": datetime.now(timezone.utc).isoformat(), "function_endpoint": endpoint, "positive_status": positive.status_code, "denials": []}
    if positive.status_code != 200:
        evidence["positive_body"] = positive.text()[:6000]
        record("access-refusal", evidence)
        raise RuntimeError(f"Authenticated function health returned HTTP {positive.status_code}")
    health = positive.json()
    if health.get("caller_principal_id") != config["operator_principal_id"] or health.get("workload_client_id") != runtime["workload_client_id"] or health.get("execution") != "azure-function" or health.get("methods") != METHODS:
        raise RuntimeError("Authenticated function identity response differs from frozen caller/workload identities")
    if "no-store" not in positive.headers.get("Cache-Control", "") or "private" not in positive.headers.get("Cache-Control", ""):
        raise RuntimeError("Authenticated response is missing confidential cache controls")
    evidence["positive"] = health
    functions = rest(config, "GET", f"{ARM}{runtime['function_id']}/functions?api-version=2024-04-01")
    names = sorted(function["name"].rsplit("/", 1)[-1] for function in functions["value"])
    if names != ["ContentUnderstanding", "ExtractionHealth", "ExtractionStatus"]:
        raise RuntimeError("Live Function inventory is not exactly CU, status and health")
    evidence["function_names"] = names
    for path, headers, label in (
        ("/api/health", {}, "anonymous"),
        ("/api/health", {"X-MS-CLIENT-PRINCIPAL-ID": config["operator_principal_id"], "X-MS-CLIENT-PRINCIPAL": "forged"}, "forged-principal-headers"),
        ("/api/health", {"Authorization": "Bearer invalid.signature.token"}, "forged-bearer"),
        ("/host.json", {}, "anonymous-host-file"),
        ("/unknown", {}, "anonymous-unknown-path"),
    ):
        denied = requests.get(endpoint + path, headers=headers, timeout=120, allow_redirects=False)
        evidence["denials"].append({"case": label, "path": path, "status": denied.status_code})
        if denied.status_code not in {401, 403}:
            record("access-refusal", evidence)
            raise RuntimeError(f"Unauthorized path did not refuse: {label}, HTTP {denied.status_code}")
    arm_credential = AzureCliCredential(subscription=config["subscription_id"], process_timeout=30)
    wrong_audience = arm_credential.get_token("https://management.azure.com/.default")
    denied = requests.get(endpoint + "/api/health", headers={"Authorization": "Bearer " + wrong_audience.token}, timeout=120, allow_redirects=False)
    evidence["denials"].append({"case": "valid-entra-wrong-audience", "status": denied.status_code})
    if denied.status_code not in {401, 403}:
        raise RuntimeError("Valid ARM token was incorrectly accepted as a Function API token")
    for method in ("content-understanding",):
        job_id = str(uuid4())
        denied = client.send_request(HttpRequest("POST", f"{endpoint}/api/extract/{method}/murray/{job_id}",
            headers={"Content-Type": "application/pdf"}, content=b"%PDF-invalid-input-refusal-probe"))
        missing = client.send_request(HttpRequest("GET", f"{endpoint}/api/jobs/{job_id}"))
        evidence["denials"].append({"case": "invalid-input-" + method, "status": denied.status_code, "job_readback_status": missing.status_code})
        if denied.status_code != 403 or missing.status_code != 404:
            raise RuntimeError("Invalid input was accepted or created a cloud job")
    for method in ("document-intelligence-read", "document-intelligence-layout", "pymupdf", "markitdown"):
        job_id = str(uuid4())
        denied = client.send_request(HttpRequest("POST", f"{endpoint}/api/extract/{method}/murray/{job_id}",
            headers={"Content-Type": "application/pdf"}, content=b"%PDF-invalid-input-refusal-probe"))
        missing = client.send_request(HttpRequest("GET", f"{endpoint}/api/jobs/{job_id}"))
        evidence["denials"].append({"case": "retired-route-" + method, "status": denied.status_code,
                                   "job_readback_status": missing.status_code})
        if denied.status_code != 404 or missing.status_code != 404:
            record("access-refusal", evidence)
            raise RuntimeError("A retired extraction route is still bound or created a cloud job")
    denied = client.send_request(HttpRequest("GET", endpoint + "/api/health?target=https%3A%2F%2Fexample.invalid"))
    evidence["denials"].append({"case": "request-target-injection", "status": denied.status_code})
    if denied.status_code != 403:
        raise RuntimeError("Request-supplied target was not refused")
    record("access-verification", evidence)
    print("PASS: exact CU bindings, caller/workload identity, retired-route absence and live anonymous/forged/invalid-input denials")
    return evidence


def diagnose(config: dict) -> dict:
    current_account(config)
    runtime = json.loads((ROOT / "env" / "runtime.json").read_text())
    endpoint = "https://" + runtime["scm_host"]
    client = management_client(config, endpoint)
    evidence = {"observed_at": datetime.now(timezone.utc).isoformat(),
                "functions": rest(config, "GET", f"{ARM}{runtime['function_id']}/functions?api-version=2024-04-01")}
    for label, suffix in (
        ("host_status", "/hostruntime/admin/host/status?api-version=2024-04-01"),
        ("runtime_functions", "/hostruntime/admin/functions?api-version=2024-04-01"),
        ("mounted_content", "/hostruntime/admin/vfs/?api-version=2024-04-01"),
        ("mounted_host_config", "/hostruntime/admin/vfs/host.json?api-version=2024-04-01"),
        ("diagnostic_categories", "/providers/Microsoft.Insights/diagnosticSettingsCategories?api-version=2021-05-01-preview"),
    ):
        try:
            evidence[label] = rest(config, "GET", f"{ARM}{runtime['function_id']}{suffix}")
        except RuntimeError as error:
            evidence[label] = {"refusal": str(error)}
    pending = json.loads((ROOT / "build" / "pending-release.json").read_text())
    if pending["status_url"] != endpoint + "/api/deployments/" + pending["deployment_id"]:
        raise RuntimeError("Deployment diagnostic target mismatch")
    for label, path in (("deployment", pending["status_url"]), ("deployment_log", pending["status_url"] + "/log"),
                        ("host_logs", endpoint + "/api/vfs/LogFiles/Application/Functions/Host/")):
        response = client.send_request(HttpRequest("GET", path))
        try:
            body = response.json()
        except ValueError:
            body = response.text()[:8000]
        evidence[label] = {"status_code": response.status_code, "body": body}
    for entry in evidence["deployment_log"].get("body", []) if isinstance(evidence["deployment_log"].get("body"), list) else []:
        detail = entry.get("details_url", "")
        if detail and detail.startswith(pending["status_url"] + "/log/"):
            response = client.send_request(HttpRequest("GET", detail))
            entry["details"] = response.json() if response.status_code == 200 else {"status_code": response.status_code}
    record("runtime-diagnostic", evidence)
    print(json.dumps(evidence, indent=2))
    return evidence


def sync_functions(config: dict) -> None:
    current_account(config)
    runtime = readback(config)
    result = rest(config, "POST", f"{ARM}{runtime['function_id']}/syncfunctiontriggers?api-version=2024-04-01")
    observed = rest(config, "GET", f"{ARM}{runtime['function_id']}/functions?api-version=2024-04-01")
    record("function-trigger-sync", {"response": result, "functions": observed})
    print(json.dumps(observed, indent=2))


def check_package() -> None:
    archive = Path(json.loads((ROOT / "build" / "release.json").read_text())["archive"]).resolve()
    package = archive.parent / "package"
    if not package.is_relative_to((ROOT / "build").resolve()) or archive.name != "function.zip":
        raise RuntimeError("Package check escaped the owned build root")
    shared = ROOT.parent / "azure-extraction"
    expected = json.loads((shared / "function-bindings.json").read_text())
    if set(expected) != {"ContentUnderstanding", "ExtractionStatus", "ExtractionHealth"}:
        raise RuntimeError("Source bindings are not CU-only")
    with zipfile.ZipFile(archive) as bundle:
        bindings = {name.split("/")[0]: json.loads(bundle.read(name)) for name in bundle.namelist()
                    if len(name.split("/")) == 2 and name.endswith("/function.json")}
        if set(bindings) != set(expected):
            raise RuntimeError("Release ZIP contains missing or retired Function bindings")
        for name, binding in expected.items():
            triggers = [item for item in bindings[name]["bindings"] if item["type"] == "httpTrigger"]
            if len(triggers) != 1 or any(triggers[0].get(key) != value for key, value in binding.items()):
                raise RuntimeError("Release ZIP routes differ from the CU-only bindings")
        sources = {"handler.py": shared / "function_app.py", **{
            "azure_extraction/" + source.name: source for source in (shared / "azure_extraction").glob("*.py")}}
        for name, source in sources.items():
            if bundle.read(name) != source.read_bytes() or (package / name).read_bytes() != source.read_bytes():
                raise RuntimeError("Release ZIP or staged code differs from current verified CU source")
        if {"di_host", "document_intelligence_name"} & set(json.loads(bundle.read("experiment.json"))):
            raise RuntimeError("Retired DI configuration leaked into the runtime package")
    script = (
        "import sys,json; from pathlib import Path; package=Path(sys.argv[1]); "
        "sys.path=[str(package),str(package/'.python_packages/lib/site-packages')]+[entry for entry in sys.path if 'site-packages' not in entry]; "
        "import handler; from azure_extraction.contracts import METHODS; assert callable(handler.extract); "
        "assert METHODS=={'content-understanding':'prebuilt-layout'}; "
        "functions={path.parent.name:json.loads(path.read_text()) for path in package.glob('*/function.json')}; "
        "assert set(functions)=={'ContentUnderstanding','ExtractionStatus','ExtractionHealth'}; print(json.dumps(functions))"
    )
    result = subprocess.run(["uv", "run", "--frozen", "--project", str(ROOT.parent / "azure-extraction"), "python", "-I", "-c", script, str(package)],
                            capture_output=True, text=True, check=False)
    if result.returncode:
        record("package-check-refusal", {"stderr": result.stderr, "stdout": result.stdout})
        raise RuntimeError("The exact staged package failed isolated Function indexing")
    record("package-check", {"package": str(package.relative_to(ROOT)), "functions": json.loads(result.stdout)})
    print("PASS: exact release ZIP matches current CU source; three Function bindings import with only bundled dependencies")


def restart(config: dict) -> None:
    runtime = readback(config)
    record("restart-intent", {"resource_id": runtime["function_id"], "reason": "Capture live worker discovery failure with native diagnostics enabled"})
    result = rest(config, "POST", f"{ARM}{runtime['function_id']}/restart?api-version=2024-04-01")
    status = rest(config, "GET", f"{ARM}{runtime['function_id']}/hostruntime/admin/host/status?api-version=2024-04-01")
    record("restart-readback", {"response": result, "host_status": status})
    print(json.dumps(status, indent=2))


def query_logs(config: dict) -> dict:
    current_account(config)
    workspace_id = group_id(config) + "/providers/Microsoft.OperationalInsights/workspaces/" + config["logs_name"]
    workspace = rest(config, "GET", f"{ARM}{workspace_id}?api-version=2023-09-01")
    if workspace.get("tags", {}).get("owner") != config["owner"]:
        raise RuntimeError("Log workspace is not owned by this experiment")
    client = PipelineClient(base_url="https://api.loganalytics.azure.com", policies=[RequestIdPolicy(), RetryPolicy(retry_total=0),
        BearerTokenCredentialPolicy(AzureCliCredential(subscription=config["subscription_id"], process_timeout=30), "https://api.loganalytics.io/.default")],
        connection_timeout=15, read_timeout=90)
    query = "FunctionAppLogs | where TimeGenerated > ago(2h) | project TimeGenerated, Level, Category, Message, ExceptionDetails | order by TimeGenerated desc | take 40"
    response = client.send_request(HttpRequest("POST", f"https://api.loganalytics.azure.com/v1/workspaces/{workspace['properties']['customerId']}/query", json={"query": query}))
    evidence = {"observed_at": datetime.now(timezone.utc).isoformat(), "workspace_id": workspace_id,
                "workspace_settings": workspace["properties"], "http_status": response.status_code, "query": query, "result": response.json()}
    record("runtime-logs", evidence)
    print(json.dumps(evidence, indent=2))
    if response.status_code != 200:
        raise RuntimeError("Native log query refused; no log evidence inferred")
    return evidence


def run_extractions(config: dict, method: str, document_id: str) -> None:
    from azure_extraction.contracts import documents_from_manifest, require_method

    require_method(method)
    current_account(config)
    documents = documents_from_manifest(json.loads((ROOT.parent / "source_data" / "manifest.json").read_text()))
    methods = [method]
    selected_documents = list(documents) if document_id == "all" else [document_id]
    outcomes = []
    for selected_method in methods:
        for selected_document in selected_documents:
            document = documents[selected_document]
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            method_root = ROOT.parent / selected_method
            output = method_root / "results" / document.id / stamp
            argv = ["uv", "run", "--frozen", "--project", str(method_root), "python", str(method_root / "pipeline.py"),
                    "--input", str(ROOT.parent / "source_data" / document.file), "--output", str(output)]
            result = subprocess.run(argv, text=True, check=False)
            receipt_path = output / "receipt.json"
            receipt = json.loads(receipt_path.read_text()) if receipt_path.exists() else None
            outcome = {"method": selected_method, "document_id": document.id, "exit_code": result.returncode,
                       "receipt": str(receipt_path.relative_to(ROOT.parent)), "status": receipt.get("status") if receipt else "missing",
                       "elapsed_seconds": receipt.get("elapsed_seconds") if receipt else None}
            record("extraction", outcome)
            outcomes.append(outcome)
    record("batch", {"outcomes": outcomes})
    print(json.dumps(outcomes, indent=2))
    if any(outcome["status"] != "succeeded" or outcome["exit_code"] != 0 for outcome in outcomes):
        raise RuntimeError("One or more function extractions failed; exact receipts retained and no fallback used")


def check_job(config: dict, job_id: str) -> dict:
    from azure_extraction.client import function_client
    from azure_extraction.provider import canonical_job_id

    canonical_job_id(job_id)
    current_account(config)
    runtime = json.loads((ROOT / "env" / "runtime.json").read_text())
    client = function_client(runtime)
    response = client.send_request(HttpRequest("GET", runtime["function_endpoint"] + "/api/jobs/" + job_id))
    body = response.json()
    evidence = {"observed_at": datetime.now(timezone.utc).isoformat(), "job_id": job_id,
                "http_status": response.status_code, "body": {key: value for key, value in body.items() if key not in {"native", "text", "markdown"}}}
    record("job-readback", evidence)
    print(json.dumps(evidence, indent=2))
    return evidence


def verify_results() -> dict:
    from verify_results import verify_all

    evidence = verify_all(ROOT.parent)
    record("results-verification", evidence)
    print(json.dumps(evidence, indent=2))
    return evidence


def verify(config: dict) -> None:
    from azure_extraction.client import function_client
    from verify_results import verify_all, verify_receipt
    from azure_extraction.contracts import documents_from_manifest

    access = verify_access(config)
    summary = verify_all(ROOT.parent)
    runtime = json.loads((ROOT / "env" / "runtime.json").read_text())
    client = function_client(runtime)
    documents = documents_from_manifest(json.loads((ROOT.parent / "source_data" / "manifest.json").read_text()))
    persisted = []
    for result in summary["results"]:
        path = ROOT.parent / result["receipt"]
        checked = verify_receipt(path, documents[result["document_id"]], result["method"])
        invocation = json.loads((path.parent / "invocation.json").read_text())
        job_id = invocation["job_id"]
        response = client.send_request(HttpRequest("GET", runtime["function_endpoint"] + "/api/jobs/" + job_id))
        body = response.json()
        if response.status_code != 200 or body.get("status") != "Succeeded" or body.get("native") != checked["native"] or body.get("text") != checked["text"] or body.get("markdown") != checked["markdown"]:
            raise RuntimeError("Persisted Function job differs from the local receipt/native artifacts")
        persisted.append({"job_id": job_id, "receipt": result["receipt"], "http_status": response.status_code,
                          "complete_native_equal": True, "text_equal": True, "markdown_equal": True,
                          "function_elapsed_seconds": body["elapsed_seconds"]})
    original = next(result for result in summary["results"] if result["document_id"] == "murray")
    directory = (ROOT.parent / original["receipt"]).parent
    job_id = json.loads((directory / "invocation.json").read_text())["job_id"]
    payload = (ROOT.parent / "source_data" / documents["murray"].file).read_bytes()
    replay = client.send_request(HttpRequest("POST", f"{runtime['function_endpoint']}/api/extract/content-understanding/murray/{job_id}",
        headers={"Content-Type": "application/pdf"}, content=payload))
    original_function = json.loads((directory / "function.json").read_text())
    if replay.status_code != 200 or replay.json().get("started_at") != original_function["started_at"] or replay.json().get("completed_at") != original_function["completed_at"]:
        raise RuntimeError("Completed-job idempotency replay changed execution timing")
    conflict = client.send_request(HttpRequest("POST", f"{runtime['function_endpoint']}/api/extract/content-understanding/yallourn/{job_id}",
        headers={"Content-Type": "application/pdf"}, content=(ROOT.parent / "source_data" / documents["yallourn"].file).read_bytes()))
    if conflict.status_code != 409:
        raise RuntimeError("Conflicting document reused an existing extraction job id")
    after = client.send_request(HttpRequest("GET", runtime["function_endpoint"] + "/api/jobs/" + job_id))
    if after.status_code != 200 or after.json().get("native") != json.loads((directory / "native.json").read_text()):
        raise RuntimeError("Conflicting replay changed persisted native evidence")
    model_deployments = rest(config, "GET", f"{ARM}{group_id(config)}/providers/Microsoft.CognitiveServices/accounts/{config['content_understanding_name']}/deployments?api-version=2025-06-01")
    if model_deployments.get("value"):
        raise RuntimeError("Unexpected model capacity exists in the native-layout-only CU account")
    evidence = summary | {"access": access, "persisted_jobs": persisted,
        "idempotency": {"job_id": job_id, "same_input_status": replay.status_code, "original_timestamps_preserved": True,
                        "conflicting_document_status": conflict.status_code, "original_native_preserved": True},
        "content_understanding_model_deployments": model_deployments["value"]}
    record("acceptance", evidence)
    print("PASS: two CU receipts, immutable inputs, full persisted native readback, live denials and idempotency; no CU model capacity")


def teardown(config: dict, confirmation: str) -> None:
    if confirmation != group_id(config):
        raise RuntimeError("Teardown requires --confirm-group with the exact authorized experiment resource id")
    current_account(config)
    resources = existing_resources(config)
    if azure(config, "group", "exists", "--name", config["resource_group"]):
        locks = azure(config, "lock", "list", "--resource-group", config["resource_group"])
        if locks:
            raise RuntimeError("Resource locks exist; teardown will not remove them")
    identity = json.loads(IDENTITY_PATH.read_text()) if IDENTITY_PATH.exists() else None
    applications = []
    service_principals = []
    if identity:
        if identity.get("owner") != config["owner"] or identity.get("tenant_id") != config["tenant_id"]:
            raise RuntimeError("Caller identity ledger is not owned by this experiment")
        applications = rest(config, "GET", f"{GRAPH}/applications?$filter=appId%20eq%20'{identity['api_client_id']}'&$select=id,appId,tags")["value"]
        service_principals = rest(config, "GET", f"{GRAPH}/servicePrincipals?$filter=appId%20eq%20'{identity['api_client_id']}'&$select=id,appId,tags")["value"]
        if applications and (len(applications) != 1 or applications[0]["id"] != identity["application_object_id"] or config["owner"] not in applications[0].get("tags", [])):
            raise RuntimeError("Entra application ownership differs from the exact ledger")
        if service_principals and (len(service_principals) != 1 or service_principals[0]["id"] != identity["service_principal_id"] or config["owner"] not in service_principals[0].get("tags", [])):
            raise RuntimeError("Entra service-principal ownership differs from the exact ledger")
    record("teardown-intent", {"resource_group_id": confirmation, "resources": resources, "applications": applications, "service_principals": service_principals})
    if azure(config, "group", "exists", "--name", config["resource_group"]):
        azure(config, "group", "delete", "--name", config["resource_group"], "--yes")
    if azure(config, "group", "exists", "--name", config["resource_group"]):
        raise RuntimeError("Group deletion is not confirmed; no absence claimed")
    for service_principal in service_principals:
        rest(config, "DELETE", f"{GRAPH}/servicePrincipals/{service_principal['id']}")
    for application in applications:
        rest(config, "DELETE", f"{GRAPH}/applications/{application['id']}")
    if identity:
        for collection in ("applications", "servicePrincipals"):
            observed = rest(config, "GET", f"{GRAPH}/{collection}?$filter=appId%20eq%20'{identity['api_client_id']}'&$select=id")
            if observed["value"]:
                raise RuntimeError(f"Owned {collection} deletion not confirmed")
    record("teardown-readback", {"resource_group_absent": True, "dedicated_caller_identity_absent": True,
                                  "local_receipts_preserved": True, "arm_deployment_history_retained": True})
    print("PASS: exact owned group and dedicated caller identity absent; local receipts and ARM history retained")


def inspect(config: dict) -> dict:
    evidence = {"observed_at": datetime.now(timezone.utc).isoformat(), "account": current_account(config), "cloud_mutations": []}
    evidence["group_exists"] = azure(config, "group", "exists", "--name", config["resource_group"])
    if evidence["group_exists"]:
        group = azure(config, "group", "show", "--name", config["resource_group"])
        if group.get("tags", {}).get("owner") != config["owner"]:
            record("collision", group)
            raise RuntimeError("Existing resource group is not owned by this experiment")
        evidence["group"] = group
        evidence["resources"] = azure(config, "resource", "list", "--resource-group", config["resource_group"])
    evidence["providers"] = {}
    for namespace in ("Microsoft.Web", "Microsoft.Storage", "Microsoft.ManagedIdentity", "Microsoft.CognitiveServices"):
        evidence["providers"][namespace] = azure(
            config, "provider", "show", "--namespace", namespace,
            "--query", "{registrationState:registrationState,types:resourceTypes[?resourceType=='accounts' || resourceType=='sites' || resourceType=='serverfarms' || resourceType=='storageAccounts'].{type:resourceType,locations:locations}}"
        )
    evidence["storage_name"] = azure(config, "storage", "account", "check-name", "--name", config["storage_name"])
    evidence["flex_locations"] = azure(config, "functionapp", "list-flexconsumption-locations")
    try:
        evidence["operator"] = command(["az", "ad", "signed-in-user", "show", "--query", "{id:id}", "--only-show-errors", "-o", "json"])
    except RuntimeError as error:
        evidence["operator_read_refusal"] = str(error)
    record("inspection", evidence)
    print(json.dumps(evidence, indent=2))
    return evidence


def research() -> None:
    from urllib.parse import urlsplit
    from azure_extraction.contracts import artifact_path

    references = ROOT / "references"
    manifest = json.loads((references / "manifest.json").read_text())
    verified = []
    for entry in manifest["entries"]:
        source = urlsplit(entry["source_url"])
        path = (references / artifact_path(entry["artefact"])).resolve()
        if source.scheme != "https" or source.netloc != "learn.microsoft.com" or not path.is_relative_to(references.resolve()):
            raise RuntimeError("Reference source or artifact escaped its approved provenance bounds")
        content = path.read_bytes()
        if sha256(content).hexdigest() != entry["sha256"] or len(content) != entry["bytes"] or entry["status"] != 200:
            raise RuntimeError("Cached official reference no longer matches its acquisition record")
        verified.append({"source_url": entry["source_url"], "artefact": entry["artefact"], "sha256": entry["sha256"]})
    if len(verified) != manifest["count"]:
        raise RuntimeError("Reference catalogue count mismatch")
    record("reference-verification", {"artifacts_verified": len(verified), "artifacts": verified,
        "network_refresh": False, "binding_reference": "references/python-bindings.md"})
    print(f"PASS: {len(verified)} cached official artifacts match provenance; offline verification, no web refresh")


def compile_template() -> None:
    build = ROOT / "build"
    build.mkdir(exist_ok=True)
    command(["az", "bicep", "build", "--file", str(ROOT / "infra" / "main.bicep"), "--outfile", str(build / "main.json")])
    print("PASS: Bicep compiled")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("inspect", "research", "compile", "offline", "preflight", "plan", "configure-caller", "check-caller", "apply", "readback", "build", "release", "verify-access", "diagnose", "sync-functions", "check-package", "restart", "logs", "run", "check-job", "verify-results", "verify", "teardown"))
    parser.add_argument("--method", choices=("content-understanding",), default="content-understanding")
    parser.add_argument("--document", choices=("all", "yallourn", "murray"), default="all")
    parser.add_argument("--job-id")
    parser.add_argument("--confirm-group")
    parser.add_argument("--local-only", action="store_true", help="Build from validated cached targets; no cloud call or release authority")
    parser.add_argument("--test-pattern", help="Run one existing offline test file through this entry point")
    args = parser.parse_args()
    if args.local_only and args.action != "build":
        parser.error("--local-only applies only to build; release always requires fresh cloud readback")
    if args.test_pattern is not None and (args.action != "offline" or not re.fullmatch(r"test_[a-z0-9_]+\.py", args.test_pattern)
            or not (ROOT.parent / "azure-extraction" / "tests" / args.test_pattern).is_file()):
        parser.error("--test-pattern requires offline and one existing test_*.py filename")
    if args.action == "inspect":
        inspect(target())
    elif args.action == "compile":
        compile_template()
    elif args.action == "offline":
        offline(args.test_pattern)
    elif args.action == "preflight":
        preflight(target())
    elif args.action == "plan":
        plan(target())
    elif args.action == "configure-caller":
        configure_caller(target())
    elif args.action == "check-caller":
        check_caller(target())
    elif args.action == "apply":
        apply(target())
    elif args.action == "readback":
        readback(target())
    elif args.action == "build":
        build_release(target(), local_only=args.local_only)
    elif args.action == "release":
        release(target())
    elif args.action == "verify-access":
        verify_access(target())
    elif args.action == "diagnose":
        diagnose(target())
    elif args.action == "sync-functions":
        sync_functions(target())
    elif args.action == "check-package":
        check_package()
    elif args.action == "restart":
        restart(target())
    elif args.action == "logs":
        query_logs(target())
    elif args.action == "run":
        run_extractions(target(), args.method, args.document)
    elif args.action == "check-job":
        if not args.job_id:
            parser.error("--job-id is required for check-job")
        check_job(target(), args.job_id)
    elif args.action == "verify-results":
        verify_results()
    elif args.action == "verify":
        verify(target())
    elif args.action == "teardown":
        teardown(target(), args.confirm_group)
    else:
        research()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        record("refusal", {"observed_at": datetime.now(timezone.utc).isoformat(), "type": type(error).__name__, "message": str(error)[:6000]})
        sys.exit(1)