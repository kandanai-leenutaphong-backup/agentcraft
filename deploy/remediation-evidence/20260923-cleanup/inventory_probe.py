"""Read-only inventory probes; outputs are exclusive files beside this script."""

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import inspect
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from urllib.parse import urlsplit, urlunsplit


ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]
SUBSCRIPTION = "67255afe-8670-4401-a1b8-df6ca63a3516"
TENANT = "c79ab2bb-79cb-47f1-b4da-b6852fe45ff7"
ENDPOINT = "https://han-primary-foundry-resource.services.ai.azure.com/api/projects/han-primary-foundry"
STAMP = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
PROJECT_ID = f"/subscriptions/{SUBSCRIPTION}/resourceGroups/personal-llm/providers/Microsoft.CognitiveServices/accounts/han-primary-foundry-resource/projects/han-primary-foundry"
REGISTRY_ID = f"/subscriptions/{SUBSCRIPTION}/resourceGroups/rg-agentcraft-dev/providers/Microsoft.ContainerRegistry/registries/agentcraftdev67255"
LAST_CHECK = time.monotonic()
os.environ.update(PYTHONDONTWRITEBYTECODE="1", AZURE_CORE_COLLECT_TELEMETRY="false",
                  AZURE_LOGGING_ENABLE_LOG_FILE="false", AZURE_EXTENSION_USE_DYNAMIC_INSTALL="no")
sys.dont_write_bytecode = True


def safe(value):
    if hasattr(value, "as_dict"):
        value = value.as_dict()
    elif hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    if isinstance(value, dict):
        return {key: "<redacted>" if key.lower() in {
            "access_token", "token", "secret", "client_secret", "authorization", "credential", "credentials",
            "sas_uri", "sasuri", "connectionstring", "connection_string", "password", "apikey", "api_key"
        } else safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [safe(item) for item in value]
    if isinstance(value, str) and value.startswith(("https://", "http://")):
        parsed = urlsplit(value)
        if parsed.query and any(part.startswith(("sig=", "token=", "se=", "sv=")) for part in parsed.query.split("&")):
            return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "<redacted>", ""))
    return value


def retain(label, value):
    destination = ROOT / (STAMP + "-" + label + ".json")
    if destination.parent != ROOT or destination.is_symlink():
        raise ValueError("evidence destination escapes authorized root")
    payload = (json.dumps(safe(value), indent=2, sort_keys=True, default=str, allow_nan=False) + "\n").encode()
    with destination.open("xb") as output:
        output.write(payload)
    if destination.read_bytes() != payload:
        raise RuntimeError("evidence readback mismatch")
    print(json.dumps({"path": str(destination.relative_to(REPO)), "sha256": hashlib.sha256(payload).hexdigest()}), flush=True)
    clock_check()
    return destination


def clock_check():
    global LAST_CHECK
    if time.monotonic() - LAST_CHECK >= 45:
        subprocess.run([sys.executable, "-B", str(REPO / ".github/tools/oplog.py"), "check", "--run",
                        "r-20260923T081652Z", "--log", str(ROOT / "inventory-worker-oplog.jsonl")], check=True)
        LAST_CHECK = time.monotonic()


def cli(label, arguments):
    if "--subscription" not in arguments:
        raise ValueError("explicit subscription required")
    started = time.monotonic()
    result = subprocess.run(["az", *arguments, "--output", "json"], capture_output=True, text=True, timeout=90)
    try:
        output = json.loads(result.stdout)
    except ValueError:
        output = result.stdout
    value = {"observed_at": datetime.now(timezone.utc).isoformat(), "command": ["az", *arguments],
             "exit_code": result.returncode, "seconds": time.monotonic() - started,
             "result": output, "stderr": result.stderr}
    retain(label, value)
    return value


def observe(label, operation, function):
    started = time.monotonic()
    value = {"observed_at": datetime.now(timezone.utc).isoformat(), "operation": operation}
    try:
        value.update(status="complete", result=safe(function()))
    except Exception as error:
        value.update(status="error", error_type=type(error).__name__, http_status=getattr(error, "status_code", None),
                     message=str(error))
    value["seconds"] = time.monotonic() - started
    retain(label, value)
    return value


def rows(iterator, maximum=10000):
    result = []
    for item in iterator:
        if len(result) >= maximum:
            raise ValueError("inventory exceeded explicit item bound; completeness not established")
        result.append(safe(item))
    return result


def arm():
    common = ["--subscription", SUBSCRIPTION]
    cli("target", ["account", "show", *common, "--query", "{id:id,tenantId:tenantId,state:state,cloud:environmentName}"])
    cli("project", ["resource", "show", "--ids", PROJECT_ID, "--api-version", "2025-06-01", *common])
    cli("foundry-account", ["cognitiveservices", "account", "show", "--name", "han-primary-foundry-resource",
                           "--resource-group", "personal-llm", *common])
    cli("model-deployments", ["cognitiveservices", "account", "deployment", "list", "--name", "han-primary-foundry-resource",
                             "--resource-group", "personal-llm", *common])
    cli("registry", ["acr", "show", "--name", "agentcraftdev67255", "--resource-group", "rg-agentcraft-dev", *common])
    cli("registry-roles", ["role", "assignment", "list", "--scope", REGISTRY_ID, "--include-inherited", "--all",
                           "--fill-principal-name", "false", *common])
    cli("project-roles", ["role", "assignment", "list", "--scope", PROJECT_ID, "--include-inherited", "--all",
                          "--fill-principal-name", "false", *common])
    for group in ("personal-llm", "rg-agentcraft-dev"):
        cli("group-" + group, ["group", "show", "--name", group, *common])
        cli("resources-" + group, ["resource", "list", "--resource-group", group, *common,
            "--query", "[].{id:id,name:name,type:type,location:location,kind:kind,tags:tags,managedBy:managedBy}"])
        cli("locks-" + group, ["lock", "list", "--resource-group", group, *common])


def acr():
    common = ["--subscription", SUBSCRIPTION]
    listed = cli("acr-repositories", ["acr", "repository", "list", "--name", "agentcraftdev67255", *common])
    if listed["exit_code"] == 0:
        for repository in listed["result"]:
            slug = repository.replace("/", "_")
            cli("acr-tags-" + slug, ["acr", "repository", "show-tags", "--name", "agentcraftdev67255",
                                   "--repository", repository, "--detail", *common])
            cli("acr-manifests-" + slug, ["acr", "manifest", "list-metadata", "--registry", "agentcraftdev67255",
                                        "--name", repository, *common])
    cli("acr-runs", ["acr", "task", "list-runs", "--registry", "agentcraftdev67255", "--top", "1000", *common])
    cli("acr-tasks", ["acr", "task", "list", "--registry", "agentcraftdev67255", *common])


def foundry(action):
    from azure.ai.projects import AIProjectClient
    from azure.identity import AzureCliCredential

    with AzureCliCredential(subscription=SUBSCRIPTION, process_timeout=30) as credential:
        with AIProjectClient(endpoint=ENDPOINT, credential=credential, allow_preview=True, retry_total=0,
                             connection_timeout=10, read_timeout=30) as project:
            if action == "foundry-agents":
                listed = observe("agents", "project.agents.list(limit=100)", lambda: rows(project.agents.list(limit=100)))
                for agent in listed.get("result", []):
                    name = agent["name"]
                    observe("versions-" + name, "project.agents.list_versions(" + name + ", include_drafts=True)",
                            lambda: rows(project.agents.list_versions(name, limit=100, include_drafts=True)))
                    observe("sessions-" + name, "project.agents.list_sessions(" + name + ")",
                            lambda: rows(project.agents.list_sessions(name, limit=100)))
            elif action == "foundry-assets":
                listed = observe("datasets", "project.datasets.list()", lambda: rows(project.datasets.list()))
                for dataset in listed.get("result", []):
                    name = dataset["name"]
                    observe("dataset-versions-" + name, "project.datasets.list_versions(" + name + ")",
                            lambda: rows(project.datasets.list_versions(name)))
                listed = observe("custom-evaluators", "project.beta.evaluators.list(type='custom')",
                                 lambda: rows(project.beta.evaluators.list(type="custom", limit=100)))
                for evaluator in listed.get("result", []):
                    name = evaluator["name"]
                    observe("evaluator-versions-" + name, "project.beta.evaluators.list_versions(" + name + ")",
                            lambda: rows(project.beta.evaluators.list_versions(name, type="custom", limit=100)))
                observe("builtin-coherence", "project.beta.evaluators.get_version('builtin.coherence', '12')",
                        lambda: project.beta.evaluators.get_version("builtin.coherence", "12"))
                observe("connections", "project.connections.list()", lambda: rows(project.connections.list()))
                observe("evaluator-generation-jobs", "project.beta.evaluators.list_generation_jobs()",
                        lambda: rows(project.beta.evaluators.list_generation_jobs(limit=100)))
            elif action == "foundry-jobs":
                listed = observe("optimization-jobs", "project.beta.agents.list_optimization_jobs(limit=100)",
                                 lambda: rows(project.beta.agents.list_optimization_jobs(limit=100)))
                for job in listed.get("result", []):
                    identifier = job["id"]
                    observe("job-" + identifier, "project.beta.agents.get_optimization_job(" + identifier + ")",
                            lambda: project.beta.agents.get_optimization_job(identifier))
            elif action == "foundry-evals":
                with project.get_openai_client(max_retries=0, timeout=30) as client:
                    listed = observe("evals", "client.evals.list(limit=100)", lambda: rows(client.evals.list(limit=100)))
                    for evaluation in listed.get("result", []):
                        identifier = evaluation["id"]
                        observe("eval-runs-" + identifier, "client.evals.runs.list(eval_id=" + identifier + ")",
                                lambda: rows(client.evals.runs.list(eval_id=identifier, limit=100)))
                    observe("openai-containers", "client.containers.list(limit=100)", lambda: rows(client.containers.list(limit=100)))
                    observe("openai-files", "client.files.list(limit=100)", lambda: rows(client.files.list(limit=100)))
                    observe("openai-vector-stores", "client.vector_stores.list(limit=100)", lambda: rows(client.vector_stores.list(limit=100)))


def surfaces():
    from azure.ai.projects import AIProjectClient
    from azure.identity import AzureCliCredential

    packages = {}
    for name in ("azure-ai-projects", "azure-identity", "azure-storage-blob", "openai", "azure-cli"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    result = {"packages": packages, "endpoint": ENDPOINT, "subscription": SUBSCRIPTION, "operations": {}}
    with AzureCliCredential(subscription=SUBSCRIPTION, process_timeout=30) as credential:
        with AIProjectClient(endpoint=ENDPOINT, credential=credential, allow_preview=True, retry_total=0,
                             connection_timeout=10, read_timeout=30) as project:
            owners = {name: getattr(project, name) for name in ("agents", "datasets", "deployments", "connections")}
            result["missing_top_level_surfaces"] = [name for name in ("evaluators",) if not hasattr(project, name)]
            for name in ("agents", "evaluators", "evaluation_rules", "evaluation_taxonomies"):
                if hasattr(project.beta, name):
                    owners["beta." + name] = getattr(project.beta, name)
            from openai import OpenAI
            openai_client = OpenAI(api_key="inspection-only-not-used-for-requests")
            owners.update({"openai." + name: owner for name, owner in {
                "evals": openai_client.evals, "evals.runs": openai_client.evals.runs,
                "responses": openai_client.responses, "containers": openai_client.containers,
                "files": openai_client.files, "vector_stores": openai_client.vector_stores,
                "conversations": openai_client.conversations}.items()})
            for name, owner in owners.items():
                result["operations"][name] = {}
                for method_name in dir(owner):
                    if method_name.startswith(("list", "get", "delete", "stop", "cancel", "begin_", "retrieve")):
                        method = getattr(owner, method_name)
                        if callable(method):
                            result["operations"][name][method_name] = {"signature": str(inspect.signature(method)),
                                "documentation": inspect.getdoc(method), "source": inspect.getsourcefile(inspect.unwrap(method)),
                                "line": inspect.getsourcelines(inspect.unwrap(method))[1]}
            openai_client.close()
    retain("sdk-surfaces", result)


def summary(suffixes):
    suffixes = suffixes or ["agents", "optimization-jobs", "model-deployments", "datasets", "custom-evaluators",
                            "evals", "registry-roles", "resources-rg-agentcraft-dev", "resources-personal-llm"]
    result = []
    for suffix in suffixes:
        for path in sorted(ROOT.glob("*-" + suffix + ".json")):
            value = json.loads(path.read_text())
            items = value.get("result")
            fields = ("id", "name", "version", "status", "state", "kind", "type", "created_at", "createdAt", "agent_name",
                      "agentName", "roleDefinitionId", "principalId", "scope", "version_indicator", "containers")
            simplified = []
            for item in items if isinstance(items, list) else [items]:
                if isinstance(item, dict):
                    selected = {key: item[key] for key in fields if key in item}
                    for key in ("properties", "definition"):
                        if isinstance(item.get(key), dict):
                            selected[key] = {field: item[key][field] for field in
                                             ("provisioningState", "model", "kind", "image", "container", "agent_version") if field in item[key]}
                    simplified.append(selected or item)
                else:
                    simplified.append(item)
            entry = {"source": str(path.relative_to(REPO)), "status": value.get("status", value.get("exit_code")),
                     "error": value.get("message", value.get("stderr")), "count": len(items) if isinstance(items, list) else None,
                     "items": simplified}
            result.append(entry)
    retain("summary", result)
    print(json.dumps(result, indent=2))


def local():
    prefixes = [REPO / "testbeds" / name for name in ("foundry-hosted-agents", "foundry-agent-evaluation", "foundry-agent optimization")]
    prefixes.append(REPO / "agentcraft_projects/foundry-official-integration-20260922")
    processes = []
    failures = []
    for directory in Path("/proc").iterdir():
        if not directory.name.isdigit() or int(directory.name) == os.getpid():
            continue
        try:
            command = (directory / "cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace").strip()
            cwd = (directory / "cwd").resolve(strict=True)
            matches = [str(prefix.relative_to(REPO)) for prefix in prefixes
                       if cwd.is_relative_to(prefix) or str(prefix.relative_to(REPO)) in command]
            if matches:
                status = (directory / "status").read_text().splitlines()
                selected = {line.split(":", 1)[0]: line.split(":", 1)[1].strip() for line in status
                            if line.startswith(("Name:", "State:", "PPid:", "Uid:"))}
                processes.append({"pid": int(directory.name), "command": command, "cwd": str(cwd), "status": selected,
                                  "matching_scope": matches})
        except PermissionError:
            failures.append({"pid": int(directory.name), "reason": "permission denied"})
        except (FileNotFoundError, ProcessLookupError):
            continue
    retain("local-processes", {"observed_at": datetime.now(timezone.utc).isoformat(), "processes": processes,
                               "inaccessible": failures, "excludes": "inventory process itself; exited processes cannot be enumerated"})
    print(json.dumps({"matched": len(processes), "inaccessible": len(failures)}))


def provenance():
    roots = [REPO / "testbeds/foundry-hosted-agents/deploy/records", REPO / "testbeds/foundry-agent-evaluation/deploy/records",
             REPO / "testbeds/foundry-agent optimization/deploy/evidence",
             REPO / "agentcraft_projects/foundry-official-integration-20260922/records"]
    fields = {"id", "name", "agent", "agent_id", "agent_name", "agent_version", "job_id", "operation_id", "eval_id", "run_id",
              "response_id", "configuration_id", "candidate_id", "blob_uri", "data_uri", "dataUri", "pending_upload_id",
              "pendingUploadId", "storage_account_arm_id", "storageAccountArmId", "repository", "tag", "digest", "image",
              "resource_id", "model_deployment", "optimizer_model", "version", "created", "created_by", "eval_run_id",
              "agent_session_id", "session_id", "container_id", "agent_guid", "principal_id", "client_id", "blueprint_id",
              "dataset_id", "datasetId", "runId"}
    skip = {"output", "outputs", "input", "instructions", "code_text", "ground_truth", "labels", "sample", "content", "dataset_items"}
    identities = {}
    files = []
    for root in roots:
        for path in sorted(root.rglob("*.json")):
            if set(path.relative_to(root).parts) & {"artifacts", "development", "candidate", "dataset"}:
                continue
            text = path.read_text()
            try:
                value = json.loads(text)
            except ValueError:
                continue
            lines = text.splitlines()
            relative = str(path.relative_to(REPO))
            files.append({"path": relative, "sha256": hashlib.sha256(text.encode()).hexdigest(),
                          "action": value.get("action") if isinstance(value, dict) else None,
                          "status": value.get("status") if isinstance(value, dict) else None})

            def walk(item, pointer=""):
                if isinstance(item, dict):
                    for key, child in item.items():
                        if key in skip:
                            continue
                        if key in fields and isinstance(child, str) and child and len(child) < 2048:
                            cleaned = safe(child)
                            needle = json.dumps(child, ensure_ascii=False)
                            line = next((number for number, content in enumerate(lines, 1) if needle in content), None)
                            identities.setdefault(cleaned, []).append({"path": relative, "line": line,
                                "pointer": pointer + "/" + key, "action": value.get("action") if isinstance(value, dict) else None,
                                "status": value.get("status") if isinstance(value, dict) else None})
                        walk(child, pointer + "/" + key)
                elif isinstance(item, list):
                    for position, child in enumerate(item):
                        walk(child, pointer + "/" + str(position))

            walk(value)
    retain("receipt-identity-index", {"files": files, "identities": identities,
                                      "warning": "A reference is not creation proof; classify using the owning operation and its successful receipt."})
    print(json.dumps({"receipts": len(files), "distinct_identity_values": len(identities)}))


def supplementary():
    from azure.ai.projects import AIProjectClient
    from azure.identity import AzureCliCredential
    from azure.storage.blob import BlobClient

    index = json.loads(sorted(ROOT.glob("*-receipt-identity-index.json"))[-1].read_text())["identities"]
    principals = {"d9cd20e0-1a11-4046-9469-1057ca18396e"}
    for path in ROOT.glob("*-versions-agentcraft*.json"):
        for version in json.loads(path.read_text()).get("result", []):
            for key in ("instance_identity", "blueprint"):
                principal = version.get(key, {}).get("principal_id")
                if principal:
                    principals.add(principal)
    query = "[?contains([" + ",".join("'" + principal + "'" for principal in sorted(principals)) + "], principalId)]"
    cli("experiment-principal-roles", ["role", "assignment", "list", "--all", "--fill-principal-name", "false",
        "--subscription", SUBSCRIPTION, "--query", query])
    with AzureCliCredential(subscription=SUBSCRIPTION, process_timeout=20) as credential:
        with AIProjectClient(endpoint=ENDPOINT, credential=credential, allow_preview=True, retry_total=0,
                             connection_timeout=10, read_timeout=20) as project:
            with project.get_openai_client(max_retries=0, timeout=12) as client:
                listed = set()
                for path in ROOT.glob("*-evals.json"):
                    listed.update(item["id"] for item in json.loads(path.read_text()).get("result", []))
                missing = sorted(key for key in index if re.fullmatch(r"eval_[a-z0-9]+", key) and key not in listed)
                for identifier in missing:
                    actual = observe("referenced-eval-" + identifier, "client.evals.retrieve(" + identifier + ")",
                                     lambda: client.evals.retrieve(identifier))
                    if actual["status"] == "complete":
                        observe("eval-runs-" + identifier, "client.evals.runs.list(eval_id=" + identifier + ")",
                                lambda: rows(client.evals.runs.list(eval_id=identifier, limit=100)))
            blobs = {}
            for path in (REPO / "testbeds/foundry-agent-evaluation/deploy/records").rglob("*blob-uploaded.json"):
                data = json.loads(path.read_text())
                uri = data.get("data_uri")
                if uri:
                    blobs[uri] = str(path.relative_to(REPO))
            for position, (uri, source) in enumerate(sorted(blobs.items()), 1):
                parsed = urlsplit(uri)
                if parsed.scheme != "https" or not parsed.hostname.endswith(".blob.core.windows.net") or parsed.query:
                    raise ValueError("unexpected blob URI; no arbitrary destination request")
                with BlobClient.from_blob_url(uri, credential=credential, retry_total=0, connection_timeout=8, read_timeout=12) as blob:
                    observe("blob-properties-" + str(position), "BlobClient.get_blob_properties(" + uri + ") from " + source,
                            lambda: dict(blob.get_blob_properties()))
    retain("blob-probe-scope", {"blobs": blobs, "credentials_fetched": False,
                              "constraint": "Entra metadata reads only; no SAS retrieval or provider-subscription ARM access"})


def blob_cli():
    scope = json.loads(sorted(ROOT.glob("*-blob-probe-scope.json"))[-1].read_text())
    for position, uri in enumerate(sorted(scope["blobs"]), 1):
        parsed = urlsplit(uri)
        container, blob_name = parsed.path.lstrip("/").split("/", 1)
        cli("blob-cli-properties-" + str(position), ["storage", "blob", "show", "--account-name", parsed.hostname.split(".")[0],
            "--container-name", container, "--name", blob_name, "--auth-mode", "login", "--subscription", SUBSCRIPTION,
            "--query", "{name:name,deleted:deleted,snapshot:snapshot,versionId:versionId,properties:properties,metadata:metadata}"])


def responses(limit=None):
    from azure.ai.projects import AIProjectClient
    from azure.identity import AzureCliCredential

    index = json.loads(sorted(ROOT.glob("*-receipt-identity-index.json"))[-1].read_text())["identities"]
    identifiers = sorted(identifier for identifier, references in index.items()
                         if any(reference["pointer"].endswith("/response_id") for reference in references)
                         and re.fullmatch(r"(?:caresp|resp)_[A-Za-z0-9_-]+", identifier))
    if limit is not None:
        identifiers = identifiers[:limit]
    grouped = {}
    for identifier in identifiers:
        owners = set()
        for reference in index[identifier]:
            path = reference["path"]
            if path.startswith("testbeds/foundry-agent optimization/deploy/evidence/"):
                owners.add("agentcraft-migration-iris-v1" if "/evidence/migration-" in path else "agentcraft-iris-optimization")
            elif path.startswith(("testbeds/foundry-hosted-agents/", "testbeds/foundry-agent-evaluation/")):
                owners.add("agentcraft-migration-tool-proof-v1" if "/records/migration-" in path else "agentcraft-hosted-tool-proof")
        if len(owners) != 1:
            raise ValueError("response has ambiguous owning agent: " + identifier)
        grouped.setdefault(owners.pop(), []).append(identifier)
    observations = []
    with AzureCliCredential(subscription=SUBSCRIPTION, process_timeout=20) as credential:
        with AIProjectClient(endpoint=ENDPOINT, credential=credential, allow_preview=True, retry_total=0) as project:
            for owner, owned_ids in grouped.items():
                with project.get_openai_client(agent_name=owner, max_retries=0, timeout=12) as client:
                    for identifier in owned_ids:
                        started = time.monotonic()
                        observation = {"id": identifier, "agent_name": owner, "observed_at": datetime.now(timezone.utc).isoformat(),
                                       "operation": "project.get_openai_client(agent_name=" + owner + ").responses.retrieve(" + identifier + ")"}
                        try:
                            result = client.responses.retrieve(identifier)
                            observation.update(status="complete", result={key: getattr(result, key, None) for key in
                                ("id", "status", "created_at", "model", "metadata", "background", "error", "incomplete_details")})
                        except Exception as error:
                            observation.update(status="error", http_status=getattr(error, "status_code", None),
                                               error_type=type(error).__name__, message=str(error)[:2000])
                        observation["seconds"] = time.monotonic() - started
                        observations.append(observation)
                        clock_check()
    retain("stored-responses" if limit is None else "response-probe", {"requested": len(identifiers), "observations": observations,
                                "scope": "Only IDs retained by the named testbeds; response contents not retained"})
    print(json.dumps({"responses": len(observations), "successful_reads": sum(item["status"] == "complete" for item in observations)}))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("surfaces", "arm", "acr", "foundry-agents", "foundry-assets", "foundry-jobs", "foundry-evals", "summary", "local", "provenance", "supplementary", "blob-cli", "responses"))
    parser.add_argument("--suffix", action="append")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    if args.action == "surfaces":
        surfaces()
    elif args.action == "arm":
        arm()
    elif args.action == "acr":
        acr()
    elif args.action == "summary":
        summary(args.suffix)
    elif args.action == "local":
        local()
    elif args.action == "provenance":
        provenance()
    elif args.action == "supplementary":
        supplementary()
    elif args.action == "blob-cli":
        blob_cli()
    elif args.action == "responses":
        responses(args.limit)
    else:
        foundry(args.action)


if __name__ == "__main__":
    main()