"""Reproducible, scoped Hosted Agents experiment using existing resources."""

import argparse
import codecs
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import importlib.util
import io
import json
import os
import re
import site
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
from main import TOOLS, validate_events
from proof_tools import nonce_digest

DEPLOY = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
RECORDS = DEPLOY / "records"
TARGET = json.loads((DEPLOY / "env/target.json").read_text())
OBSERVATIONS = []
PROJECT_PRINCIPAL = "d9cd20e0-1a11-4046-9469-1057ca18396e"
PULL_ROLE = "7f951dda-4ed3-4680-a7ca-43fe172d538d"
RUN_MANIFEST = None


def configure_run(path, expected_sha256, action):
    global TARGET, RECORDS, RUN_MANIFEST
    path = Path(path).resolve()
    if not path.is_relative_to(DEPLOY / "env") or digest(path.read_bytes()) != expected_sha256:
        raise ValueError("run manifest path/digest mismatch")
    value = json.loads(path.read_text())
    if (value.get("schema_version") != 1 or value.get("purpose") != "migration-development"
            or action not in value.get("actions", []) or not re.fullmatch(r"migration-[a-z0-9-]+", value.get("series", ""))
            or not re.fullmatch(r"agentcraft-migration-[a-z0-9-]+", value.get("agent", ""))
            or value.get("target_sha256") != digest((DEPLOY / "env/target.json").read_bytes())):
        raise ValueError("foreign or historical manifest")
    constitution = REPO / "agentcraft_projects/foundry-official-integration-20260922/constitution/constitution.yaml"
    if value.get("constitution_sha256") != digest(constitution.read_bytes()):
        raise ValueError("constitution pin mismatch")
    target = json.loads((DEPLOY / "env/target.json").read_text())
    target.update(agent_name=value["agent"], image_repository=value["agent"])
    directory = DEPLOY / "records" / value["series"]
    if directory.is_symlink() or not directory.resolve().is_relative_to(DEPLOY / "records"):
        raise ValueError("foreign evidence root")
    directory.mkdir(exist_ok=True)
    retained = directory / "run-manifest.json"
    if retained.exists() and retained.read_bytes() != path.read_bytes():
        raise ValueError("run manifest changed after binding")
    if not retained.exists():
        with retained.open("xb") as stream:
            stream.write(path.read_bytes())
    TARGET, RECORDS, RUN_MANIFEST = target, directory, value
    return {"series": value["series"], "manifest_sha256": expected_sha256, "target": target, "live": False}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def cli(arguments):
    started = time.monotonic()
    result = subprocess.run(["az", *arguments, "-o", "json"], capture_output=True, text=True, timeout=180)
    OBSERVATIONS.append({"command": ["az", *arguments], "exit_code": result.returncode,
                         "seconds": time.monotonic() - started})
    if result.returncode:
        OBSERVATIONS[-1]["diagnostic"] = result.stderr
        raise RuntimeError("Azure CLI refused command; inspect retained diagnostic")
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
    for relative in ("Dockerfile", "requirements.txt", "runtime-requirements.lock", "dependency-manifest.json"):
        files[relative] = DEPLOY / relative
    dependencies = json.loads((DEPLOY / "dependency-manifest.json").read_text())
    for name, expected in dependencies["wheels"].items():
        path = DEPLOY / "wheelhouse" / name
        if path.is_symlink() or not path.resolve().is_relative_to(DEPLOY / "wheelhouse") or digest(path.read_bytes()) != expected:
            raise ValueError("locked wheel identity mismatch")
        files["wheelhouse/" + name] = path
    if digest((DEPLOY / "runtime-requirements.lock").read_bytes()) != dependencies["runtime_lock_sha256"]:
        raise ValueError("runtime lock identity mismatch")
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


def install(target=None, reviewed_lock=None, dry_run=False):
    from packaging.requirements import Requirement

    lock = DEPLOY / "host-requirements.lock"
    if target is None or reviewed_lock != digest(lock.read_bytes()):
        raise RuntimeError("dependency installation requires reviewed uv profile and explicit target")
    destination = Path(target)
    expected = Path(site.getusersitepackages())
    if (not destination.is_dir() or destination.is_symlink() or destination.resolve() != expected.resolve()
            or not os.access(destination, os.W_OK) or str(expected) not in sys.path
            or any(sys.path.index(path) < sys.path.index(str(expected))
                   for path in site.getsitepackages() if path in sys.path)):
        raise ValueError("existing user-site containment/import order refused")
    requirements = [Requirement(line.split(" --hash=", 1)[0].strip())
                    for line in lock.read_text().replace("\\\n", " ").splitlines()
                    if line.strip() and not line.lstrip().startswith("#")]
    if not dry_run:
        installed = {distribution.metadata["Name"].lower().replace("_", "-"): distribution.version
                     for distribution in importlib.metadata.distributions(path=[str(destination)])}
        for requirement in requirements:
            version = installed.get(requirement.name.lower().replace("_", "-"))
            if version is None or not requirement.specifier.contains(version, prereleases=True):
                raise RuntimeError("package replacement/addition requires exact recovery review: " + requirement.name)
    command = ["uv", "--no-config", "pip", "install", "--python", sys.executable,
               "--no-python-downloads", "--no-build-isolation", "--only-binary", ":all:",
               "--require-hashes", "--no-index", "--find-links", str(DEPLOY / "wheelhouse"),
               "--target", str(destination), "-r", str(lock)]
    for arguments in ([*command, "--dry-run"],) if dry_run else ([*command, "--dry-run"], command):
        result = subprocess.run(arguments, capture_output=True, text=True, timeout=600)
        OBSERVATIONS.append({"command": arguments, "exit_code": result.returncode,
                             "output": result.stdout, "error": result.stderr})
        if result.returncode:
            raise RuntimeError("locked uv install failed; inspect retained diagnostics")
    return {"dry_run": dry_run, "lock_sha256": reviewed_lock, "target": str(destination),
            "dependencies": prerequisites()}


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


@contextmanager
def project_client():
    from azure.ai.projects import AIProjectClient
    from azure.identity import AzureCliCredential
    with AzureCliCredential(tenant_id=TARGET["tenant_id"], process_timeout=30) as credential, AIProjectClient(
        endpoint=TARGET["project_endpoint"], credential=credential, retry_total=0,
        connection_timeout=15, read_timeout=150,
    ) as project:
        yield project


def mutation_intent(name, request):
    path = RECORDS / (name + "-intent.json")
    if path.parent.resolve() != RECORDS.resolve() or path.is_symlink():
        raise ValueError("foreign mutation intent")
    with path.open("xb") as stream:
        stream.write((json.dumps(request, sort_keys=True, allow_nan=False) + "\n").encode())
    return path


def anonymous_probe(nonce):
    import httpx
    url = TARGET["project_endpoint"] + "/agents/" + TARGET["agent_name"] + "/endpoint/protocols/openai/responses?api-version=v1"
    with httpx.Client(timeout=150, follow_redirects=False) as client:
        response = client.post(url, json={"input": nonce, "store": False})
    OBSERVATIONS.append({"operation": "anonymous_probe", "http_status": response.status_code})
    return response.status_code


def finish_build(source, retained, run_id):
    retained = Path(retained).resolve()
    if not retained.is_relative_to(RECORDS.resolve()):
        raise ValueError("archive outside records")
    with tarfile.open(retained) as bundle:
        if set(bundle.getnames()) != set(source["files"]) | {"app/source-manifest.json"}:
            raise ValueError("archive member mismatch")
        for name, expected in source["files"].items():
            member = bundle.getmember(name)
            if not member.isfile() or digest(bundle.extractfile(member).read()) != expected:
                raise ValueError("archive bytes mismatch")
        if json.loads(bundle.extractfile("app/source-manifest.json").read()) != source:
            raise ValueError("archive manifest mismatch")
    deadline = time.monotonic() + 900
    while True:
        run = cli(["acr", "task", "show-run", "--subscription", TARGET["subscription_id"],
                   "--registry", TARGET["registry_name"], "--run-id", run_id,
                   "--query", "{runId:runId,status:status,outputImages:outputImages,startTime:startTime,finishTime:finishTime}"])
        if run["status"] == "Succeeded":
            break
        if run["status"] not in {"Queued", "Started", "Running"} or time.monotonic() >= deadline:
            raise RuntimeError(f"ACR run {run_id}: {run['status']}; inspect before retry")
        threading.Event().wait(min(10, max(0, deadline - time.monotonic())))
    images = [image for image in run["outputImages"] if image["registry"] == TARGET["registry_host"]
              and image["repository"] == TARGET["image_repository"] and image["tag"] == source["sha256"]]
    if len(images) != 1:
        raise ValueError("ACR run output does not match pinned source tag")
    image = cli(["acr", "repository", "show", "--subscription", TARGET["subscription_id"], "--name", TARGET["registry_name"],
                 "--image", TARGET["image_repository"] + ":" + source["sha256"], "--query", "{digest:digest,name:name}"])
    if image["digest"] != images[0]["digest"]:
        raise ValueError("ACR output digest drift")
    return {"image": TARGET["registry_host"] + "/" + TARGET["image_repository"] + "@" + image["digest"],
            "source": source, "archive": str(retained.relative_to(ROOT)), "archive_sha256": digest(retained.read_bytes()),
            "acr_run": run}


def build(recover_run=None, archive_path=None):
    preflight()
    local_checks()
    source = manifest()
    if recover_run:
        if not recover_run.isalnum() or not archive_path:
            raise ValueError("recovery requires run id and archive")
        return finish_build(source, archive_path, recover_run)
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
        retained = RECORDS / ("source-" + source["sha256"] + "-" + uuid.uuid4().hex + ".tar.gz")
        retained.write_bytes(archive.read_bytes())
        context = Path(directory) / "context"
        with tarfile.open(archive) as bundle:
            for name, expected in source["files"].items():
                content = bundle.extractfile(name).read()
                if digest(content) != expected:
                    raise ValueError("source changed during packaging")
                destination = context / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(content)
            (context / "app/source-manifest.json").write_bytes(bundle.extractfile("app/source-manifest.json").read())
        mutation_intent("build-" + source["sha256"], {"tag": tag, "archive": str(retained.relative_to(ROOT)),
                                                    "archive_sha256": digest(retained.read_bytes())})
        queued = cli(["acr", "build", "--subscription", TARGET["subscription_id"], "--registry", TARGET["registry_name"],
                      "--platform", "linux/amd64", "--image", tag, "--file", str(context / "Dockerfile"), "--no-logs",
                      "--no-wait", "--timeout", "900", "--query", "{runId:runId}", str(context)])
        run_id = queued.get("runId") if isinstance(queued, dict) else None
        if not isinstance(run_id, str) or not run_id.isalnum():
            raise RuntimeError("build outcome unknown; reconcile retained source/tag, never resubmit")
        OBSERVATIONS.append({"operation": "build_identity", "run_id": run_id, "archive": str(retained.relative_to(ROOT))})
        mutation_intent("build-" + source["sha256"] + "-accepted", {"run_id": run_id, "archive": str(retained.relative_to(ROOT))})
        return finish_build(source, retained, run_id)


def deploy(build_receipt, previous_receipt=None):
    from azure.core.exceptions import ResourceNotFoundError
    from azure.ai.projects.models import HostedAgentDefinition
    preflight()
    built = read_receipt(build_receipt, "build")
    agent_path = "/agents/" + TARGET["agent_name"]
    with project_client() as project:
        try:
            existing = project.agents.get(agent_name=TARGET["agent_name"]).as_dict()
        except ResourceNotFoundError:
            existing = None
    previous = None
    if existing is not None:
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
    elif previous_receipt:
        raise ValueError("previous owned agent missing")
    definition = {"kind": "hosted", "container_configuration": {"image": built["image"]},
                  "cpu": "1", "memory": "2Gi",
                  "protocol_versions": [{"protocol": "responses", "version": "2.0.0"}]}
    metadata = {"experiment": "foundry-hosted-tool-proof", "source_sha256": built["source"]["sha256"],
                "config_sha256": built["source"]["files"]["app/configuration.yaml"]}
    request = {"agent_name": TARGET["agent_name"], "definition": definition, "metadata": metadata}
    mutation_intent("deploy-" + TARGET["agent_name"] + "-" + built["source"]["sha256"], request)
    with project_client() as project:
        created = project.agents.create_version(agent_name=TARGET["agent_name"],
            definition=HostedAgentDefinition(definition), metadata=metadata).as_dict()
    OBSERVATIONS.append({"operation": "create_hosted_agent", "result": created})
    version = str(created.get("version") or "")
    if not version.isdigit():
        raise RuntimeError("create accepted but version unknown; read back before any retry")
    deployed = {**built, "agent": TARGET["agent_name"], "version": version, "definition": definition, "metadata": metadata,
            "endpoint": TARGET["project_endpoint"] + agent_path + "/endpoint/protocols/openai/responses"}
    OBSERVATIONS.append({"operation": "accepted_deployment", "deployed": deployed})
    deadline = time.monotonic() + 300
    while True:
        with project_client() as project:
            state = project.agents.get_version(agent_name=TARGET["agent_name"], agent_version=version).as_dict()
        if state.get("status") not in {"creating", "active"}:
            raise RuntimeError("version not ready; retained state requires inspection")
        if state["status"] == "active":
            deployed["readback"] = check_version(deployed)
            return deployed
        if time.monotonic() >= deadline:
            raise RuntimeError("readiness deadline exceeded; inspect accepted version before retry")
        threading.Event().wait(min(5, max(0, deadline - time.monotonic())))


def check_version(deployed):
    if deployed.get("agent", TARGET["agent_name"]) != TARGET["agent_name"]:
        raise ValueError("foreign agent deployment")
    with project_client() as project:
        version = project.agents.get_version(agent_name=TARGET["agent_name"], agent_version=deployed["version"]).as_dict()
    actual = version.get("definition", {})
    expected = deployed["definition"]
    matches = (all(actual.get(key) == expected[key] for key in ("kind", "cpu", "memory", "protocol_versions"))
               and actual.get("container_configuration", {}).get("image") == expected["container_configuration"]["image"])
    if deployed.get("metadata") and any(version.get("metadata", {}).get(key) != value
                                        for key, value in deployed["metadata"].items()):
        matches = False
    if str(version.get("version")) != deployed["version"] or version.get("status") != "active" or not matches:
        OBSERVATIONS.append({"operation": "version_readback", "state": version.get("status")})
        raise RuntimeError("exact version definition not active; inspect status, do not redeploy")
    return {"version": deployed["version"], "state": version["status"], "definition": version["definition"]}


def verify_response(response, nonce, deployed, tool_name="nonce_digest"):
    text = "".join(content.get("text", "") for item in response.get("output", [])
                   if item.get("type") == "message" for content in item.get("content", [])
                   if content.get("type") == "output_text")
    envelope = json.loads(text)
    validate_events(envelope["tool_events"], TOOLS[tool_name](nonce), tool_name)
    if envelope.get("requested_tool", "nonce_digest") != tool_name:
        raise ValueError("requested tool identity mismatch")
    if (envelope.get("nonce") != nonce or envelope.get("source_sha256") != deployed["source"]["sha256"]
            or envelope.get("config_sha256") != deployed["source"]["files"]["app/configuration.yaml"]
            or envelope.get("agent_name") != TARGET["agent_name"] or str(envelope.get("agent_version")) != deployed["version"]):
        raise ValueError("loaded source/config/version identity mismatch")
    return envelope


def invoke(deployment_receipt, tool_name="nonce_digest"):
    preflight()
    deployed = read_receipt(deployment_receipt, "deploy")
    check_version(deployed)
    nonce = digest((RUN_MANIFEST["series"] + ":" + tool_name).encode())[:32] if RUN_MANIFEST else uuid.uuid4().hex
    proof_input = json.dumps({"tool": tool_name, "nonce": nonce})
    OBSERVATIONS.append({"operation": "proof_request", "nonce": nonce, "tool": tool_name})
    refusal = anonymous_probe(nonce)
    if refusal not in (401, 403):
        raise RuntimeError(f"anonymous refusal not proved: HTTP {refusal}")
    request = {"input": proof_input, "store": True, "stream": False,
               "extra_body": {"agent_reference": {"type": "agent_reference", "name": deployed["agent"], "version": deployed["version"]}}}
    mutation_intent("invoke-" + nonce, request)
    with project_client() as project, project.get_openai_client(agent_name=deployed["agent"], max_retries=0, timeout=150) as client:
        response = client.responses.create(**request).model_dump(mode="json")
    OBSERVATIONS.append({"operation": "proof_response", "response": response})
    if response.get("status") != "completed":
        raise RuntimeError("remote invocation incomplete; retrieve retained response ID")
    envelope = verify_response(response, nonce, deployed, tool_name)
    return {"deployed": deployed, "nonce": nonce, "response_id": response["id"],
            "anonymous_status": refusal, "envelope": envelope, "tool": tool_name,
            "response_output": response.get("output"), "response_metadata": response.get("metadata")}


def verify(invocation_receipt):
    preflight()
    invocation = read_receipt(invocation_receipt, "invoke")
    version = check_version(invocation["deployed"])
    response_id = invocation["response_id"]
    if not isinstance(response_id, str) or not response_id.replace("_", "").isalnum():
        raise ValueError("invalid response id")
    with project_client() as project, project.get_openai_client(agent_name=TARGET["agent_name"], max_retries=0, timeout=150) as client:
        response = client.responses.retrieve(response_id).model_dump(mode="json")
    if response.get("status") != "completed":
        raise RuntimeError("persisted response incomplete")
    if "response_output" in invocation and (response.get("output") != invocation["response_output"]
            or response.get("metadata") != invocation["response_metadata"]):
        raise ValueError("persisted response text/metadata differs")
    envelope = verify_response(response, invocation["nonce"], invocation["deployed"], invocation.get("tool", "nonce_digest"))
    if envelope != invocation["envelope"]:
        raise ValueError("persisted response differs")
    return {"version": version, "response_id": response_id, "readback": True, "tool_evidence": envelope,
            "anonymous_status": invocation["anonymous_status"]}


def inspect_agent(session_id=None):
    preflight()
    with project_client() as project:
        results = {"agent": {"http_status": 200, "result": project.agents.get(agent_name=TARGET["agent_name"]).as_dict()}}
        for label, operation in (("versions", project.agents.list_versions), ("sessions", project.agents.list_sessions)):
            values = []
            deadline = time.monotonic() + 60
            for value in operation(agent_name=TARGET["agent_name"], limit=100):
                if len(values) >= 1000 or time.monotonic() >= deadline:
                    raise ValueError("inspection bound exceeded")
                values.append(value.as_dict())
            results[label] = {"http_status": 200, "result": {"data": values}}
        if session_id:
            if not session_id.isalnum():
                raise ValueError("invalid session id")
            results["exact_session"] = {"http_status": 200, "result": project.agents.get_session(
                agent_name=TARGET["agent_name"], session_id=session_id).as_dict()}
    return results


def log_messages(chunks, max_bytes=262144, max_events=100):
    decoder = codecs.getincrementaldecoder("utf-8")("strict")
    pending, data, total, events = "", [], 0, 0
    for chunk in chunks:
        total += len(chunk)
        if total > max_bytes:
            raise ValueError("log byte bound exceeded")
        pending += decoder.decode(chunk)
        while "\n" in pending:
            line, pending = pending.split("\n", 1)
            line = line.removesuffix("\r")
            if line.startswith("data:"):
                data.append(line[5:].lstrip(" "))
            elif not line and data:
                events += 1
                if events > max_events:
                    raise ValueError("log event bound exceeded")
                try:
                    value = json.loads("\n".join(data))
                except ValueError:
                    value = None
                data = []
                if isinstance(value, dict) and isinstance(value.get("message"), str):
                    yield value["message"]
    decoder.decode(b"", final=True)


def logs(deployment_receipt, session_id):
    from azure.ai.projects import AIProjectClient
    from azure.identity import AzureCliCredential

    deployed = read_receipt(deployment_receipt, "deploy", current=False)
    if not session_id or not session_id.isalnum():
        raise ValueError("invalid session id")
    with project_client() as project:
        session = project.agents.get_session(agent_name=TARGET["agent_name"], session_id=session_id).as_dict()
    if session.get("version_indicator", {}).get("agent_version") != deployed["version"]:
        raise ValueError("session version mismatch")
    lines = []
    deadline = time.monotonic() + 20
    with AzureCliCredential(tenant_id=TARGET["tenant_id"]) as credential, AIProjectClient(
        TARGET["project_endpoint"], credential, retry_total=0
    ) as client:
        try:
            stream = client.agents.get_session_log_stream(
                agent_name=TARGET["agent_name"], agent_version=deployed["version"], session_id=session_id,
                connection_timeout=10, read_timeout=5,
            )
            for message in log_messages(stream):
                if any(word in message for word in ("Error", "Exception", "Traceback", "denied", "failed")):
                    message = re.sub(r"eyJ[A-Za-z0-9_.-]+", "[REDACTED]", message)
                    message = re.sub(r"(?i)(Bearer\s+|sig=|token=|secret=)[^\s&]+", r"\1[REDACTED]", message)
                    lines.append(message[:2000])
                if time.monotonic() >= deadline or len(lines) >= 100:
                    break
        except Exception as error:
            OBSERVATIONS.append({"operation": "bounded_session_logs", "termination": type(error).__name__})
    return {"session_id": session_id, "version": deployed["version"], "exception_lines": lines,
            "coverage": "bounded exception-filtered console stream; not full log"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("test", "install", "grant-pull", "preflight", "build", "deploy", "invoke", "verify", "inspect", "logs", "manifest-check"))
    parser.add_argument("--receipt")
    parser.add_argument("--previous", help="explicit prior owned deployment receipt for a new version")
    parser.add_argument("--run-id", help="recover an already submitted build, never resubmit")
    parser.add_argument("--archive", help="retained matching source archive for build recovery")
    parser.add_argument("--session", help="exact owned session for bounded exception diagnostics")
    parser.add_argument("--tool", choices=tuple(TOOLS), default="nonce_digest")
    parser.add_argument("--target", help="explicit existing writable user-site for locked install")
    parser.add_argument("--reviewed-lock", help="reviewed host-requirements.lock SHA-256")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--manifest")
    parser.add_argument("--manifest-sha256")
    args = parser.parse_args()
    if args.action not in ("test", "install") or args.manifest:
        if not args.manifest or not args.manifest_sha256:
            parser.error("live actions require --manifest and --manifest-sha256; historical defaults cannot mutate")
        binding = configure_run(args.manifest, args.manifest_sha256, args.action)
    if args.action in {"deploy", "invoke", "verify", "logs"} and not args.receipt:
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
        actions = {"test": local_checks, "install": lambda: install(args.target, args.reviewed_lock, args.dry_run), "grant-pull": grant_pull, "preflight": preflight,
             "manifest-check": lambda: binding,
               "inspect": lambda: inspect_agent(args.session),
               "build": lambda: build(args.run_id, args.archive),
                   "deploy": lambda: deploy(args.receipt, args.previous), "invoke": lambda: invoke(args.receipt, args.tool),
                   "verify": lambda: verify(args.receipt), "logs": lambda: logs(args.receipt, args.session)}
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