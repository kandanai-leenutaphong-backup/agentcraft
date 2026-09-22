"""Reproducible, scoped Hosted Agents experiment using existing resources."""

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import tomllib
import unittest
import uuid

from composition import ROOT, load_spec
from main import validate_events
from proof_tools import nonce_digest

DEPLOY = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
RECORDS = DEPLOY / "records"
TARGET = json.loads((DEPLOY / "env/target.json").read_text())
OBSERVATIONS = []
PROJECT_PRINCIPAL = "d9cd20e0-1a11-4046-9469-1057ca18396e"
PULL_ROLE = "7f951dda-4ed3-4680-a7ca-43fe172d538d"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def cli(arguments):
    started = time.monotonic()
    result = subprocess.run(["az", *arguments, "-o", "json"], capture_output=True, text=True, timeout=180)
    OBSERVATIONS.append({"command": ["az", *arguments], "exit_code": result.returncode,
                         "seconds": time.monotonic() - started})
    if result.returncode:
        raise RuntimeError("Azure CLI refused command; inspect target permissions (stderr not retained)")
    output = json.loads(result.stdout or "null")
    OBSERVATIONS[-1]["result"] = output
    return output


def source_inputs():
    files = {}
    for relative in ("main.py", "composition.py", "proof_tools.py", "configuration.yaml", "prompts/proof.md", "deploy/compatibility.py"):
        path = ROOT / relative
        if path.is_symlink() or not path.resolve().is_relative_to(ROOT):
            raise ValueError("unsafe application source")
        files["app/" + relative] = path
    for relative in ("Dockerfile", "requirements.txt"):
        files[relative] = DEPLOY / relative
    packages = {
        "framework-core": ("src/agentcraft_core",),
        "llm-interface": ("src/llm_interface",),
        "modular-agents": ("modules/agent-config-build/agentconfig", "modules/purpose-built-tools/toolshape",
                           "modules/foundry-hosted-agents/hostedagents"),
    }
    for library, roots in packages.items():
        base = REPO / "libraries" / library
        selected = [base / name for name in ("pyproject.toml", "README.md", "LICENSE")]
        if library == "modular-agents":
            selected.extend(base / name for name in ("CONTRACT.md", "PROVENANCE.md"))
        for root in roots:
            selected.extend(path for path in (base / root).rglob("*") if path.is_file()
                            and (path.suffix == ".py" or path.name in {"py.typed", "requirements.txt"}))
        for path in selected:
            if path.is_symlink() or not path.resolve().is_relative_to(base.resolve()):
                raise ValueError("unsafe build source")
            files[f"libraries/{library}/{path.relative_to(base).as_posix()}"] = path
    return files


def manifest():
    files = {name: digest(path.read_bytes()) for name, path in sorted(source_inputs().items())}
    return {"files": files, "sha256": digest(json.dumps(files, sort_keys=True).encode())}


def local_checks():
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"))
    output = io.StringIO()
    started = time.monotonic()
    result = unittest.TextTestRunner(stream=output, verbosity=2).run(suite)
    evidence = {"tests": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
                "seconds": time.monotonic() - started, "output": output.getvalue(),
                "source": manifest(), "config_model": load_spec().model}
    if not result.wasSuccessful():
        OBSERVATIONS.append(evidence)
        raise RuntimeError("offline tests failed")
    return evidence


def prerequisites():
    from packaging.requirements import Requirement

    requirements = []
    for library in ("framework-core", "llm-interface", "modular-agents"):
        project = tomllib.loads((REPO / "libraries" / library / "pyproject.toml").read_text())["project"]
        requirements.extend(project.get("dependencies", []))
        if library == "llm-interface":
            requirements.extend(project["optional-dependencies"]["foundry"])
    requirements.extend((DEPLOY / "requirements.txt").read_text().splitlines())
    local = {"agentcraft-core", "llm-interface"}
    observed, gaps = {}, []
    for text in requirements:
        requirement = Requirement(text)
        if requirement.name in local:
            continue
        try:
            version = importlib.metadata.version(requirement.name)
        except importlib.metadata.PackageNotFoundError:
            version = None
        observed[requirement.name] = version
        if version is None or not requirement.specifier.contains(version, prereleases=True):
            gaps.append(f"requires {text}; installed {version}")
    origins = {}
    for module in ("agentconfig", "llm_interface", "agent_framework", "azure.ai.projects", "azure.ai.agentserver.responses"):
        try:
            spec = importlib.util.find_spec(module)
            origins[module] = None if spec is None else spec.origin
        except ModuleNotFoundError:
            origins[module] = None
    return {"python": sys.executable, "version": sys.version, "packages": observed,
            "origins": origins, "gaps": gaps}


def install():
    before = prerequisites()
    OBSERVATIONS.append({"operation": "dependencies_before", "result": before})
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="foundry-install-") as directory:
        staging = Path(directory)
        for name, path in source_inputs().items():
            if name.startswith("libraries/"):
                destination = staging / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(path.read_bytes())
        command = [sys.executable, "-m", "pip", "install", "--user", "--break-system-packages",
                   str(staging / "libraries/framework-core"),
                   str(staging / "libraries/llm-interface") + "[foundry]",
                   str(staging / "libraries/modular-agents"), "-r", str(DEPLOY / "requirements.txt")]
        result = subprocess.run(command, capture_output=True, text=True, timeout=600)
    OBSERVATIONS.append({"command": command, "exit_code": result.returncode,
                         "seconds": time.monotonic() - started,
                         "output": result.stdout, "error": result.stderr})
    if result.returncode:
        raise RuntimeError("dependency installation failed; inspect retained pip diagnostics")
    after = prerequisites()
    if after["gaps"]:
        OBSERVATIONS.append(after)
        raise RuntimeError("installed dependencies still fail declared requirements")
    return after


def preflight(allow_missing_pull=False):
    dependencies = prerequisites()
    subscription = TARGET["subscription_id"]
    account = cli(["account", "show", "--query", "{subscriptionId:id,tenantId:tenantId,cloud:environmentName}"])
    if account != {"subscriptionId": subscription, "tenantId": TARGET["tenant_id"], "cloud": TARGET["cloud"]}:
        raise ValueError("active Azure account mismatch; no automatic account switch")
    project = cli(["resource", "show", "--ids", TARGET["project_id"], "--api-version", "2025-06-01",
                   "--query", "{id:id,location:location,identity:identity,endpoints:properties.endpoints,state:properties.provisioningState}"])
    registry = cli(["acr", "show", "--subscription", subscription, "--name", TARGET["registry_name"],
                    "--query", "{id:id,loginServer:loginServer,publicNetworkAccess:publicNetworkAccess,roleAssignmentMode:roleAssignmentMode}"])
    assignments = cli(["role", "assignment", "list", "--subscription", subscription, "--scope", TARGET["registry_id"],
                       "--include-inherited", "--query",
                       f"[?principalId=='{project['identity']['principalId']}'].{{role:roleDefinitionName,scope:scope,condition:condition}}"])
    model = cli(["cognitiveservices", "account", "deployment", "list", "--subscription", subscription,
                 "--resource-group", TARGET["model_resource_group"], "--name", TARGET["model_account"], "--query",
                 f"[?name=='{TARGET['model_deployment']}'].{{name:name,model:properties.model,state:properties.provisioningState}}"])
    gaps = list(dependencies["gaps"])
    if project.get("state") != "Succeeded" or TARGET["project_endpoint"] not in project.get("endpoints", {}).values():
        gaps.append("project endpoint/state mismatch")
    if registry.get("id", "").lower() != TARGET["registry_id"].lower() or registry.get("loginServer") != TARGET["registry_host"]:
        gaps.append("registry identity mismatch")
    if registry.get("publicNetworkAccess") != "Enabled":
        gaps.append("registry networking requires explicit compatibility verification; no network changes authorized")
    if project["identity"]["principalId"] != PROJECT_PRINCIPAL:
        gaps.append("project principal changed; grant target mismatch")
    if registry.get("roleAssignmentMode") != "LegacyRegistryPermissions":
        gaps.append("registry mode changed; AcrPull semantics not applicable")
    if not allow_missing_pull and not any(role["role"] == "AcrPull" and not role.get("condition") for role in assignments):
        gaps.append("project identity lacks observed unconditional AcrPull; run authorized grant-pull")
    if len(model) != 1 or model[0]["state"] != "Succeeded" or load_spec().model != TARGET["model_deployment"]:
        gaps.append("configured model not ready or configuration mismatch")
    evidence = {"dependencies": dependencies, "project": project, "registry": registry,
                "project_registry_roles": assignments, "model": model, "gaps": gaps,
                "effort": "unsupported: host exposes no effort-setting control", "source": manifest()}
    OBSERVATIONS.append(evidence)
    if gaps:
        raise RuntimeError("preflight blocked: " + "; ".join(gaps))
    return evidence


def grant_pull():
    before = preflight(allow_missing_pull=True)
    definitions = cli(["role", "definition", "list", "--name", PULL_ROLE,
                       "--subscription", TARGET["subscription_id"],
                       "--query", "[].{name:roleName,id:name,permissions:permissions}"])
    permissions = [
        {key: value for key, value in permission.items()
         if not (key in {"condition", "conditionVersion"} and value is None)}
        for definition in definitions for permission in definition["permissions"]
    ]
    if (len(definitions) != 1 or definitions[0]["id"] != PULL_ROLE
            or definitions[0]["name"] != "AcrPull"
            or permissions != [{"actions": ["Microsoft.ContainerRegistry/registries/pull/read"],
                                                  "notActions": [], "dataActions": [], "notDataActions": []}]):
        raise ValueError("AcrPull definition differs from approved least-privilege semantics")
    exact = [role for role in before["project_registry_roles"]
             if role["scope"].lower() == TARGET["registry_id"].lower()
             and role["role"] == "AcrPull" and not role.get("condition")]
    if not exact:
        cli(["role", "assignment", "create", "--subscription", TARGET["subscription_id"],
             "--assignee-object-id", PROJECT_PRINCIPAL, "--assignee-principal-type", "ServicePrincipal",
             "--role", PULL_ROLE, "--scope", TARGET["registry_id"],
             "--name", str(uuid.uuid5(uuid.NAMESPACE_URL, TARGET["registry_id"] + PROJECT_PRINCIPAL + PULL_ROLE)),
             "--query", "{id:id,principalId:principalId,roleDefinitionId:roleDefinitionId,scope:scope,condition:condition}"])
    after = cli(["role", "assignment", "list", "--subscription", TARGET["subscription_id"],
                 "--scope", TARGET["registry_id"], "--query",
                 f"[?principalId=='{PROJECT_PRINCIPAL}'].{{id:id,principalId:principalId,roleDefinitionId:roleDefinitionId,scope:scope,condition:condition}}"])
    if not any(role["scope"].lower() == TARGET["registry_id"].lower()
               and role["roleDefinitionId"].split("/")[-1] == PULL_ROLE
               and role["principalId"] == PROJECT_PRINCIPAL and not role.get("condition") for role in after):
        raise RuntimeError("exact pull assignment readback missing; inspect before retry")
    return {"created": not bool(exact), "role_definition": definitions, "readback": after}


def read_receipt(path, action, current=True):
    resolved = Path(path).resolve()
    if not resolved.is_relative_to(RECORDS.resolve()) or Path(path).is_symlink():
        raise ValueError("receipt must be inside this testbed's records directory")
    receipt = json.loads(resolved.read_text())
    if receipt["action"] != action or receipt["status"] != "complete" or receipt["target"] != TARGET:
        raise ValueError("wrong receipt action, status or target")
    if current and receipt["source_sha256"] != manifest()["sha256"]:
        raise ValueError("source changed after receipt; rerun affected stages")
    return receipt["result"]


def api(method, suffix, body=None, anonymous=False):
    import httpx
    from azure.identity import AzureCliCredential

    if not suffix.startswith("/agents") or ".." in suffix or "?" in suffix or "#" in suffix:
        raise ValueError("invalid scoped API route")
    url = TARGET["project_endpoint"] + suffix + "?api-version=v1"
    headers = {"Content-Type": "application/json"}
    if not anonymous:
        with AzureCliCredential(tenant_id=TARGET["tenant_id"], process_timeout=30) as credential:
            headers["Authorization"] = "Bearer " + credential.get_token("https://ai.azure.com/.default").token
    observation = {"operation": "api", "method": method, "path": suffix, "anonymous": anonymous,
                   "outcome": "unknown", "started_at": datetime.now(timezone.utc).isoformat()}
    OBSERVATIONS.append(observation)
    with httpx.Client(timeout=150, follow_redirects=False) as client:
        response = client.request(method, url, json=body, headers=headers)
    observation.update(http_status=response.status_code, outcome="returned",
                       request_id=response.headers.get("apim-request-id"))
    if response.is_success:
        output = response.json()
        observation["result"] = output
        return response.status_code, output
    try:
        error = response.json().get("error", {})
        observation["error_code"] = error.get("code") if isinstance(error, dict) else None
    except ValueError:
        observation["error_code"] = "non_json_response"
    return response.status_code, {"error": "HTTP request refused", "error_code": observation.get("error_code"),
                                  "request_id": response.headers.get("apim-request-id")}


def build():
    preflight()
    local_checks()
    source = manifest()
    tag = TARGET["image_repository"] + ":" + source["sha256"]
    with tempfile.TemporaryDirectory(prefix="foundry-proof-") as directory:
        archive = Path(directory) / "source.tar.gz"
        with tarfile.open(archive, "w:gz") as bundle:
            for name, path in source_inputs().items():
                bundle.add(path, arcname=name, recursive=False)
            raw = json.dumps(source, sort_keys=True).encode()
            entry = tarfile.TarInfo("app/source-manifest.json")
            entry.size = len(raw)
            bundle.addfile(entry, io.BytesIO(raw))
        retained = RECORDS / ("source-" + source["sha256"] + ".tar.gz")
        if retained.exists():
            raise ValueError("source archive already exists; inspect prior build before retry")
        retained.write_bytes(archive.read_bytes())
        with tarfile.open(archive) as bundle:
            for name, expected in source["files"].items():
                if digest(bundle.extractfile(name).read()) != expected:
                    raise ValueError("source changed during packaging")
        cli(["acr", "build", "--subscription", TARGET["subscription_id"], "--registry", TARGET["registry_name"],
             "--platform", "linux/amd64", "--image", tag, "--file", "Dockerfile", "--no-logs", str(archive)])
    image = cli(["acr", "repository", "show", "--subscription", TARGET["subscription_id"], "--name", TARGET["registry_name"],
                 "--image", tag, "--query", "{digest:digest,name:name}"])
    return {"image": TARGET["registry_host"] + "/" + TARGET["image_repository"] + "@" + image["digest"],
            "source": source, "archive": str(retained.relative_to(ROOT)), "archive_sha256": digest(retained.read_bytes())}


def deploy(build_receipt, previous_receipt=None):
    preflight()
    built = read_receipt(build_receipt, "build")
    agent_path = "/agents/" + TARGET["agent_name"]
    status, existing = api("GET", agent_path)
    previous = None
    if status == 200:
        if not previous_receipt:
            raise ValueError("agent already exists; explicit owned previous deployment receipt required")
        previous = read_receipt(previous_receipt, "deploy", current=False)
        if previous.get("agent") != TARGET["agent_name"]:
            raise ValueError("foreign agent receipt refused")
        check_version(previous)
        if existing.get("versions", {}).get("latest", {}).get("version") != previous["version"]:
            raise ValueError("latest version drift; no overwrite")
        if previous["image"] == built["image"]:
            raise ValueError("new version requires a distinct immutable image")
    elif status != 404:
        raise RuntimeError(f"agent existence unknown: HTTP {status}")
    elif previous_receipt:
        raise ValueError("previous owned agent missing")
    definition = {"kind": "hosted", "container_configuration": {"image": built["image"]},
                  "cpu": "1", "memory": "2Gi",
                  "protocol_versions": [{"protocol": "responses", "version": "2.0.0"}]}
    metadata = {"experiment": "foundry-hosted-tool-proof", "source_sha256": built["source"]["sha256"],
                "config_sha256": built["source"]["files"]["app/configuration.yaml"]}
    body = {"definition": definition, "metadata": metadata}
    if previous is None:
        body["name"] = TARGET["agent_name"]
    status, created = api("POST", agent_path + "/versions" if previous else "/agents", body)
    OBSERVATIONS.append({"operation": "create_hosted_agent", "http_status": status,
                         "name": TARGET["agent_name"], "version": created.get("version")})
    if status not in (200, 201, 202):
        raise RuntimeError(f"create refused: HTTP {status}; no automatic retry")
    version = str(created.get("version") or created.get("versions", {}).get("latest", {}).get("version") or "")
    if not version.isdigit():
        raise RuntimeError("create accepted but version unknown; read back before any retry")
    deployed = {**built, "agent": TARGET["agent_name"], "version": version, "definition": definition, "metadata": metadata,
            "endpoint": TARGET["project_endpoint"] + agent_path + "/endpoint/protocols/openai/responses"}
    OBSERVATIONS.append({"operation": "accepted_deployment", "deployed": deployed})
    deadline = time.monotonic() + 300
    while True:
        status, state = api("GET", f"{agent_path}/versions/{version}")
        if status != 200 or state.get("status") not in {"creating", "active"}:
            raise RuntimeError("version not ready; retained state requires inspection")
        if state["status"] == "active":
            deployed["readback"] = check_version(deployed)
            return deployed
        if time.monotonic() >= deadline:
            raise RuntimeError("readiness deadline exceeded; inspect accepted version before retry")
        threading.Event().wait(min(5, max(0, deadline - time.monotonic())))


def check_version(deployed):
    status, version = api("GET", f"/agents/{TARGET['agent_name']}/versions/{deployed['version']}")
    actual = version.get("definition", {})
    expected = deployed["definition"]
    matches = (all(actual.get(key) == expected[key] for key in ("kind", "cpu", "memory", "protocol_versions"))
               and actual.get("container_configuration", {}).get("image") == expected["container_configuration"]["image"])
    if deployed.get("metadata") and any(version.get("metadata", {}).get(key) != value
                                        for key, value in deployed["metadata"].items()):
        matches = False
    if status != 200 or version.get("status") != "active" or not matches:
        OBSERVATIONS.append({"operation": "version_readback", "http_status": status, "state": version.get("status")})
        raise RuntimeError("exact version definition not active; inspect status, do not redeploy")
    return {"version": deployed["version"], "state": version["status"], "definition": version["definition"]}


def verify_response(response, nonce, deployed):
    text = "".join(content.get("text", "") for item in response.get("output", [])
                   if item.get("type") == "message" for content in item.get("content", [])
                   if content.get("type") == "output_text")
    envelope = json.loads(text)
    validate_events(envelope["tool_events"], nonce_digest(nonce))
    if (envelope.get("nonce") != nonce or envelope.get("source_sha256") != deployed["source"]["sha256"]
            or envelope.get("config_sha256") != deployed["source"]["files"]["app/configuration.yaml"]
            or envelope.get("agent_name") != TARGET["agent_name"] or str(envelope.get("agent_version")) != deployed["version"]):
        raise ValueError("loaded source/config/version identity mismatch")
    return envelope


def invoke(deployment_receipt):
    preflight()
    deployed = read_receipt(deployment_receipt, "deploy")
    check_version(deployed)
    path = f"/agents/{TARGET['agent_name']}/endpoint/protocols/openai/responses"
    nonce = uuid.uuid4().hex
    refusal, _ = api("POST", path, {"input": nonce}, anonymous=True)
    if refusal not in (401, 403):
        raise RuntimeError(f"anonymous refusal not proved: HTTP {refusal}")
    status, response = api("POST", path, {"input": nonce, "store": True, "stream": False})
    if status != 200 or response.get("status") != "completed":
        raise RuntimeError(f"remote invocation incomplete: HTTP {status}")
    envelope = verify_response(response, nonce, deployed)
    return {"deployed": deployed, "nonce": nonce, "response_id": response["id"],
            "anonymous_status": refusal, "envelope": envelope}


def verify(invocation_receipt):
    preflight()
    invocation = read_receipt(invocation_receipt, "invoke")
    version = check_version(invocation["deployed"])
    response_id = invocation["response_id"]
    if not isinstance(response_id, str) or not response_id.replace("_", "").isalnum():
        raise ValueError("invalid response id")
    status, response = api("GET", f"/agents/{TARGET['agent_name']}/endpoint/protocols/openai/responses/{response_id}")
    if status != 200:
        raise RuntimeError(f"persisted response readback refused: HTTP {status}")
    envelope = verify_response(response, invocation["nonce"], invocation["deployed"])
    if envelope != invocation["envelope"]:
        raise ValueError("persisted response differs")
    return {"version": version, "response_id": response_id, "readback": True, "tool_evidence": envelope,
            "anonymous_status": invocation["anonymous_status"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("test", "install", "grant-pull", "preflight", "build", "deploy", "invoke", "verify"))
    parser.add_argument("--receipt")
    parser.add_argument("--previous", help="explicit prior owned deployment receipt for a new version")
    args = parser.parse_args()
    if args.action in {"deploy", "invoke", "verify"} and not args.receipt:
        parser.error("this action requires --receipt from preceding stage")
    if RECORDS.is_symlink() or not RECORDS.resolve().is_relative_to(ROOT):
        raise ValueError("records directory must not be a symlink")
    RECORDS.mkdir(exist_ok=True)
    started = time.monotonic()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    receipt = {"action": args.action, "started_at": stamp, "target": TARGET,
               "source_sha256": manifest()["sha256"], "status": "blocked", "result": None,
               "procedure_files": {str(path.relative_to(ROOT)): digest(path.read_bytes())
                                   for path in [Path(__file__), DEPLOY / "deploy.sh", DEPLOY / "env/target.json",
                                                *sorted((ROOT / "tests").glob("*.py"))]}}
    try:
        actions = {"test": local_checks, "install": install, "grant-pull": grant_pull, "preflight": preflight, "build": build,
                   "deploy": lambda: deploy(args.receipt, args.previous), "invoke": lambda: invoke(args.receipt),
                   "verify": lambda: verify(args.receipt)}
        receipt["result"] = actions[args.action]()
        receipt["status"] = "complete"
    except Exception as error:
        receipt["error"] = str(error) if isinstance(error, (ValueError, RuntimeError)) else type(error).__name__
    receipt.update(seconds=time.monotonic() - started, observations=OBSERVATIONS)
    destination = RECORDS / f"{stamp}-{args.action}.json"
    with destination.open("x") as output:
        json.dump(receipt, output, indent=2, sort_keys=True)
        output.write("\n")
    print(json.dumps({"status": receipt["status"], "receipt": str(destination.relative_to(REPO)),
                      "seconds": receipt["seconds"], "error": receipt.get("error")}))
    return 0 if receipt["status"] == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())