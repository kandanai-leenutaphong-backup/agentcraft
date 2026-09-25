"""Reproducible, scoped Hosted Agents experiment using existing resources."""

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
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
import time
import tomllib
import unittest
import uuid

from composition import ROOT, load_spec
from foundry_ops.build import az_json, resolve_image, submit_build, wait_build
from foundry_ops.core import (DEFAULT_KEYWORDS, EvidenceLedger, UnresolvedIntentError, VerificationError,
                              load_run_manifest, records, safe_identifier, series_directory, to_plain)
from foundry_ops.core import sha256_hex as digest
from foundry_ops.hosting import (agent_responses_url, anonymous_probe, check_active_version, check_identity, hosted,
                                 require_refusal)
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
    constitution = REPO / "agentcraft_projects/foundry-official-integration-20260922/constitution/constitution.yaml"
    run = load_run_manifest(path, expected_sha256=expected_sha256, action=action, allowed_root=DEPLOY / "env",
                            pins={"target_sha256": DEPLOY / "env/target.json", "constitution_sha256": constitution})
    target = json.loads((DEPLOY / "env/target.json").read_text())
    target.update(agent_name=run.agent, image_repository=run.agent)
    directory = series_directory(DEPLOY / "records", run.series)
    run.bind(EvidenceLedger(directory))
    TARGET, RECORDS, RUN_MANIFEST = target, directory, run.value
    return {"series": run.series, "manifest_sha256": expected_sha256, "target": target, "live": False}


def ledger():
    return EvidenceLedger(RECORDS)


def cli(arguments):
    return az_json(arguments, events=OBSERVATIONS, runner=subprocess.run)


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
    expect = {"target": TARGET, **({"source_sha256": manifest()["sha256"]} if current else {})}
    return records.read_receipt(path, root=RECORDS, action=action, expect=expect)


@contextmanager
def project_client():
    from azure.ai.projects import AIProjectClient
    from azure.identity import AzureCliCredential
    with AzureCliCredential(tenant_id=TARGET["tenant_id"], process_timeout=30) as credential, AIProjectClient(
        endpoint=TARGET["project_endpoint"], credential=credential, retry_total=0,
        connection_timeout=15, read_timeout=150,
    ) as project:
        yield project


def finish_build(source, retained, run_id, request_tag=None):
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
    run = wait_build(cli, subscription=TARGET["subscription_id"], registry=TARGET["registry_name"], run_id=run_id)
    image = resolve_image(cli, run, subscription=TARGET["subscription_id"], registry=TARGET["registry_name"],
                          registry_host=TARGET["registry_host"], repository=TARGET["image_repository"],
                          tag=request_tag or source["sha256"])
    return {"image": image, "source": source, "archive": str(retained.relative_to(ROOT)),
            "archive_sha256": digest(retained.read_bytes()), "acr_run": run}


def build_overlap():
    preflight()
    local_checks()
    source = manifest()
    request = RUN_MANIFEST["build_overlap"]
    tags = request["tags"]
    if (source["sha256"] != request["source_sha256"] or len(tags) != 2 or len(set(tags)) != 2
            or not all(re.fullmatch(r"gap-[a-z0-9-]{1,100}", tag) for tag in tags)):
        raise ValueError("overlap requires frozen source and two distinct request tags")
    original = ROOT / request["archive"]
    if (original.is_symlink() or not original.resolve().is_relative_to(DEPLOY / "records")
            or digest(original.read_bytes()) != request["archive_sha256"]):
        raise ValueError("overlap archive identity mismatch")
    retained = RECORDS / "overlap-source.tar.gz"
    accepted, results, failures = [], [], []
    with tempfile.TemporaryDirectory(prefix="foundry-overlap-") as directory:
        context = Path(directory)
        with tarfile.open(original) as bundle:
            if set(bundle.getnames()) != set(source["files"]) | {"app/source-manifest.json"}:
                raise ValueError("overlap archive member mismatch")
            if json.loads(bundle.extractfile("app/source-manifest.json").read()) != source:
                raise ValueError("overlap archive manifest mismatch")
            for name in bundle.getnames():
                member = bundle.getmember(name)
                destination = context / name
                if not member.isfile() or not destination.resolve().is_relative_to(context):
                    raise ValueError("unsafe overlap archive member")
                content = bundle.extractfile(member).read()
                if name in source["files"] and digest(content) != source["files"][name]:
                    raise ValueError("overlap archive bytes mismatch")
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(content)
        ledger().intent("build-overlap", request)
        ledger().retain_bytes(retained.name, original.read_bytes())
        for tag in tags:
            command = ["acr", "build", "--subscription", TARGET["subscription_id"],
                       "--registry", TARGET["registry_name"], "--platform", "linux/amd64",
                       "--image", TARGET["image_repository"] + ":" + tag,
                       "--file", str(context / "Dockerfile"), "--no-logs", "--no-wait",
                       "--timeout", "900", "--query", "{runId:runId}", str(context)]
            submitted_at = datetime.now(timezone.utc).isoformat()
            ledger().intent("build-" + tag, {"command": command, "tag": tag, "source": source,
                            "archive_sha256": request["archive_sha256"], "submitted_at": submitted_at})
            try:
                queued = cli(command)
                run_id = queued.get("runId") if isinstance(queued, dict) else None
                if not isinstance(run_id, str) or not run_id.isalnum():
                    raise RuntimeError("build outcome unknown; reconcile, never resubmit")
                identity = {"tag": tag, "run_id": run_id, "submitted_at": submitted_at,
                            "returned_at": datetime.now(timezone.utc).isoformat(),
                            "source_sha256": source["sha256"], "archive_sha256": request["archive_sha256"]}
                accepted.append(identity)
                ledger().intent("build-" + tag + "-accepted", identity)
            except Exception as error:
                failures.append({"tag": tag, "error": str(error)})
                break
        for identity in accepted:
            try:
                result = dict(finish_build(source, retained, identity["run_id"], identity["tag"]), request=identity)
                ledger().intent("build-" + identity["tag"] + "-terminal", result)
                results.append(result)
            except Exception as error:
                failures.append({"run_id": identity["run_id"], "error": str(error)})
    overlap = 0.0
    if len(results) == 2 and len({item["acr_run"]["runId"] for item in results}) == 2:
        starts = [datetime.fromisoformat(item["acr_run"]["startTime"].replace("Z", "+00:00")) for item in results]
        finishes = [datetime.fromisoformat(item["acr_run"]["finishTime"].replace("Z", "+00:00")) for item in results]
        overlap = (min(finishes) - max(starts)).total_seconds()
    evidence = {"builds": results, "failures": failures, "overlap_seconds": overlap,
                "association": "direct queued run identity; no inventory association", "deployment_writes": 0}
    OBSERVATIONS.append(evidence)
    if failures or overlap <= 0:
        raise RuntimeError("overlapping successful builds not proved; inspect retained terminal results")
    return evidence


def build(recover_run=None, archive_path=None):
    preflight()
    local_checks()
    source = manifest()
    if recover_run:
        if not recover_run.isalnum() or not archive_path:
            raise ValueError("recovery requires run id and archive")
        return finish_build(source, archive_path, recover_run)
    tag = TARGET["image_repository"] + ":" + source["sha256"]
    # submit_build resumes from its run record; a rerun here must refuse and recover via --run-id/--archive.
    if ledger().exists("build-" + source["sha256"] + "-intent.json"):
        raise UnresolvedIntentError("unresolved_intent", "build intent exists; recover with --run-id and --archive")
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
        ledger().retain_bytes(retained.name, archive.read_bytes())
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
        run_id = submit_build(cli, ledger(), key=source["sha256"], subscription=TARGET["subscription_id"],
                              registry=TARGET["registry_name"], image=tag, context_dir=context,
                              context={"archive": str(retained.relative_to(ROOT)),
                                       "archive_sha256": digest(retained.read_bytes())})
        return finish_build(source, retained, run_id)


def deploy(build_receipt, previous_receipt=None):
    preflight()
    built = read_receipt(build_receipt, "build")
    previous = None
    if previous_receipt:
        previous = read_receipt(previous_receipt, "deploy", current=False)
        if previous.get("agent") != TARGET["agent_name"]:
            raise ValueError("foreign agent receipt refused")
        check_version(previous)
    metadata = {"experiment": "foundry-hosted-tool-proof", "source_sha256": built["source"]["sha256"],
                "config_sha256": built["source"]["files"]["app/configuration.yaml"]}
    with project_client() as project:
        deployed = hosted.deploy_version(
            project, ledger(), key=TARGET["agent_name"] + "-" + built["source"]["sha256"],
            agent_name=TARGET["agent_name"], definition=hosted.hosted_definition(built["image"]), metadata=metadata,
            previous_version=previous["version"] if previous else None,
            previous_image=previous["image"] if previous else None)
    return {**built, **deployed, "endpoint": TARGET["project_endpoint"] + "/agents/" + TARGET["agent_name"]
            + "/endpoint/protocols/openai/responses"}


def check_version(deployed):
    if deployed.get("agent", TARGET["agent_name"]) != TARGET["agent_name"]:
        raise ValueError("foreign agent deployment")
    with project_client() as project:
        actual = to_plain(project.agents.get_version(agent_name=TARGET["agent_name"], agent_version=deployed["version"]))
    definition = deployed["definition"]
    return check_active_version(actual, version=deployed["version"], image=definition["container_configuration"]["image"],
                                metadata=deployed.get("metadata"), definition=definition)


def verify_response(response, nonce, deployed, tool_name="nonce_digest"):
    text = "".join(content.get("text", "") for item in response.get("output", [])
                   if item.get("type") == "message" for content in item.get("content", [])
                   if content.get("type") == "output_text")
    envelope = json.loads(text)
    validate_events(envelope["tool_events"], TOOLS[tool_name](nonce), tool_name)
    if envelope.get("requested_tool", "nonce_digest") != tool_name:
        raise ValueError("requested tool identity mismatch")
    check_identity(envelope, {"nonce": nonce, "source_sha256": deployed["source"]["sha256"],
                              "config_sha256": deployed["source"]["files"]["app/configuration.yaml"],
                              "agent_name": TARGET["agent_name"], "agent_version": deployed["version"]},
                   what="loaded source/config/version identity")
    return envelope


def invoke(deployment_receipt, tool_name="nonce_digest"):
    preflight()
    deployed = read_receipt(deployment_receipt, "deploy")
    check_version(deployed)
    nonce = digest((RUN_MANIFEST["series"] + ":" + deployed["version"] + ":" + tool_name).encode())[:32] if RUN_MANIFEST else uuid.uuid4().hex
    OBSERVATIONS.append({"operation": "proof_request", "nonce": nonce, "tool": tool_name})
    refusal = require_refusal(anonymous_probe(agent_responses_url(TARGET["project_endpoint"], TARGET["agent_name"]),
                                              payload={"input": nonce, "store": False}, timeout=150))
    with project_client() as project, project.get_openai_client(agent_name=deployed["agent"], max_retries=0, timeout=150) as client:
        reply = hosted.invoke(client, ledger(), key=nonce, agent_name=deployed["agent"], version=deployed["version"],
                              input=json.dumps({"tool": tool_name, "nonce": nonce}))
    response = reply["response"]
    if response.get("status") != "completed":
        raise RuntimeError("remote invocation incomplete; retrieve retained response ID")
    envelope = verify_response(response, nonce, deployed, tool_name)
    return {"deployed": deployed, "nonce": nonce, "response_id": response["id"],
            "anonymous_status": refusal, "envelope": envelope, "tool": tool_name,
            "response_output": response.get("output"), "response_metadata": response.get("metadata")}


def ownership_probe(deployment_receipt):
    deployed = read_receipt(deployment_receipt, "deploy")
    actual = check_version(deployed)
    foreign = dict(deployed, agent="agentcraft-hosted-tool-proof")
    try:
        check_version(foreign)
    except ValueError as error:
        if str(error) != "foreign agent deployment":
            raise
    else:
        raise ValueError("foreign ownership guard accepted")
    return {"owned_version": actual, "foreign_agent": foreign["agent"], "refused": True,
            "scope": "caller-side ownership guard with real owned deployment; no foreign principal credential used"}


def cancellation_probe(deployment_receipt, streaming=False, during_work=False):
    deployed = read_receipt(deployment_receipt, "deploy")
    check_version(deployed)
    key = ("work-v" if during_work else "stream-v" if streaming else "v") + deployed["version"]
    prefix = "cancel-" + key
    nonce = digest((RUN_MANIFEST["series"] + ":" + prefix).encode())[:32]
    with project_client() as project, project.get_openai_client(agent_name=deployed["agent"], max_retries=0, timeout=150) as client:
        # Resumes retained accepted identities (current or pre-foundry_ops shape) without a new create.
        try:
            result = hosted.cancel_response(
                client, ledger(), key=key, agent_name=deployed["agent"], version=deployed["version"],
                input=json.dumps({"tool": "nonce_reverse", "nonce": nonce}), stream=streaming, record_prefix=prefix,
                cancel_on="response.content_part.added" if during_work else "response.created")
        except VerificationError:
            response_id = hosted.accepted_response_id(ledger(), prefix)
            OBSERVATIONS.append({"operation": "cancel_readback", "response": to_plain(client.responses.retrieve(response_id))})
            raise
    OBSERVATIONS.append({"operation": "cancel_readback", "attempts": result["readback_attempts"], "response": result["readback"]})
    return {**result, "deployed": deployed, "completed_output_absent": True, "handler_cleanup_logs": "pending"}


def verify(invocation_receipt):
    preflight()
    invocation = read_receipt(invocation_receipt, "invoke")
    version = check_version(invocation["deployed"])
    response_id = invocation["response_id"]
    if not isinstance(response_id, str) or not response_id.replace("_", "").isalnum():
        raise ValueError("invalid response id")
    with project_client() as project, project.get_openai_client(agent_name=TARGET["agent_name"], max_retries=0, timeout=150) as client:
        response = client.responses.retrieve(response_id).model_dump(mode="json")
    OBSERVATIONS.append({"operation": "stored_response", "response": response})
    if response.get("status") != "completed":
        raise RuntimeError("persisted response incomplete")
    if "response_output" in invocation and (response.get("output") != invocation["response_output"]
            or (response.get("metadata") if response.get("metadata") is not None else {})
            != (invocation["response_metadata"] if invocation["response_metadata"] is not None else {})):
        raise ValueError("persisted response text/metadata differs")
    envelope = verify_response(response, invocation["nonce"], invocation["deployed"], invocation.get("tool", "nonce_digest"))
    if envelope != invocation["envelope"]:
        raise ValueError("persisted response differs")
    return {"version": version, "response_id": response_id, "readback": True, "tool_evidence": envelope,
            "anonymous_status": invocation["anonymous_status"]}


def inspect_agent(session_id=None):
    preflight()
    with project_client() as project:
        results = {"agent": {"http_status": 200, "result": to_plain(project.agents.get(agent_name=TARGET["agent_name"]))},
                   "versions": {"http_status": 200, "result": {"data": hosted.list_versions(project, TARGET["agent_name"])}},
                   "sessions": {"http_status": 200, "result": {"data": hosted.list_sessions(project, TARGET["agent_name"])}}}
        if session_id:
            results["exact_session"] = {"http_status": 200, "result": to_plain(project.agents.get_session(
                agent_name=TARGET["agent_name"], session_id=safe_identifier(session_id, "session id")))}
    return results


def logs(deployment_receipt, session_id):
    deployed = read_receipt(deployment_receipt, "deploy", current=False)
    with project_client() as project:
        return hosted.session_log_excerpt(project, agent_name=TARGET["agent_name"], agent_version=deployed["version"],
                                          session_id=session_id, keywords=(*DEFAULT_KEYWORDS, "cancellation_settled"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("test", "install", "grant-pull", "preflight", "build", "build-overlap", "deploy", "invoke", "verify", "inspect", "logs", "manifest-check"))
    parser.add_argument("--receipt")
    parser.add_argument("--previous", help="explicit prior owned deployment receipt for a new version")
    parser.add_argument("--run-id", help="recover an already submitted build, never resubmit")
    parser.add_argument("--archive", help="retained matching source archive for build recovery")
    parser.add_argument("--session", help="exact owned session for bounded exception diagnostics")
    parser.add_argument("--tool", choices=tuple(TOOLS), default="nonce_digest")
    parser.add_argument("--probe", choices=("cancellation", "cancellation-stream", "cancellation-work", "foreign-owner"))
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
               "build-overlap": build_overlap,
                   "deploy": lambda: deploy(args.receipt, args.previous),
                   "invoke": lambda: cancellation_probe(args.receipt, args.probe != "cancellation", args.probe == "cancellation-work") if args.probe in {"cancellation", "cancellation-stream", "cancellation-work"} else
                       ownership_probe(args.receipt) if args.probe == "foreign-owner" else invoke(args.receipt, args.tool),
                   "verify": lambda: verify(args.receipt), "logs": lambda: logs(args.receipt, args.session)}
        receipt["result"] = actions[args.action]()
        receipt["status"] = "complete"
    except Exception as error:
        receipt["error"] = str(error) if isinstance(error, (ValueError, RuntimeError)) else type(error).__name__
    receipt.update(seconds=time.monotonic() - started, observations=OBSERVATIONS)
    destination = RECORDS / f"{stamp}-{args.action}.json"
    ledger().retain(destination.name, receipt)
    print(json.dumps({"status": receipt["status"], "receipt": str(destination.relative_to(REPO)),
                      "seconds": receipt["seconds"], "error": receipt.get("error")}))
    return 0 if receipt["status"] == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())