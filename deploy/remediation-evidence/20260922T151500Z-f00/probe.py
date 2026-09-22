"""Bounded F00 observations; writes only new primary evidence beside this file."""

import argparse
import ast
from contextlib import ExitStack
from datetime import datetime, timezone
import importlib
import importlib.metadata as metadata
import inspect
import json
import os
from pathlib import Path
import platform
import re
import site
import subprocess
import sys
import sysconfig
import tarfile
import tempfile
import time

from capture import OUT, ROOT, ROOTS, pin, save, sha


def command(arguments, timeout=120):
    started = time.monotonic()
    result = subprocess.run(arguments, cwd=ROOT, capture_output=True, text=True, timeout=timeout,
                            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    return {"argv": arguments, "returncode": result.returncode, "stdout": result.stdout,
            "stderr": result.stderr, "seconds": time.monotonic() - started}


def environment():
    locations = set(site.getsitepackages() + [site.getusersitepackages(), sysconfig.get_path("purelib"), sysconfig.get_path("platlib")])
    facts = {"python": sys.executable, "resolved_python": str(Path(sys.executable).resolve()),
             "version": sys.version, "prefix": sys.prefix, "base_prefix": sys.base_prefix,
             "enable_user_site": site.ENABLE_USER_SITE, "sys_path": sys.path,
             "locations": [{"path": path, "exists": Path(path).is_dir(), "writable": os.access(path, os.W_OK),
                            "sys_path_index": sys.path.index(path) if path in sys.path else None} for path in sorted(locations)],
             "externally_managed": str(Path(sysconfig.get_path("stdlib")) / "EXTERNALLY-MANAGED"),
             "externally_managed_exists": (Path(sysconfig.get_path("stdlib")) / "EXTERNALLY-MANAGED").exists(),
             "user_site_authority": "Historical H user-site install approved; F00 grants no install. Future explicit --target decision requires containment and dependency closure review."}
    facts["commands"] = [command(["uv", "--version"]), command(["uv", "pip", "list", "--python", "/usr/bin/python3", "--format", "json"]),
                         command(["uv", "pip", "check", "--python", "/usr/bin/python3"])]
    inventory = facts["commands"][1]
    facts["package_count"] = len(json.loads(inventory["stdout"])) if inventory["returncode"] == 0 else None
    facts["selected_distributions"] = []
    for distribution in metadata.distributions():
        name = distribution.metadata.get("Name", "")
        if name.startswith(("azure-ai-", "agent-framework", "azure-mgmt-containerregistry")) or name in {"openai", "azure-core", "azure-identity", "azure-storage-blob", "azure-containerregistry", "modular-agents", "llm-interface", "agentcraft-core", "setuptools", "wheel"}:
            facts["selected_distributions"].append({"name": name, "version": distribution.version,
                "location": str(distribution.locate_file("")), "requires": distribution.requires,
                "license": distribution.metadata.get("License-Expression") or distribution.metadata.get("License"),
                "project_urls": distribution.metadata.get_all("Project-URL")})
    return facts


def sdk():
    selections = {
        "azure.ai.projects": {"AIProjectClient": ["get_openai_client"]},
        "azure.ai.projects.operations": {
            "AgentsOperations": ["create_version", "create", "get", "get_version", "list_versions", "list_sessions", "get_session", "get_session_log_stream", "stop_session", "delete_session", "delete_version", "create_version_from_code"],
            "BetaAgentsOperations": ["begin_create_optimization_job", "get_optimization_job", "list_optimization_jobs"],
            "DatasetsOperations": ["upload_file", "pending_upload", "create_or_update", "get", "get_credentials"],
            "BetaEvaluatorsOperations": ["create_version", "get_version"]},
        "azure.ai.projects.models": {name: [] for name in ["AgentOptimizationJob", "AgentOptimizationJobInputs", "AgentOptimizationJobResult", "HostedAgentDefinition", "ContainerConfiguration", "CodeConfiguration", "EvaluatorVersion", "TestingCriterionAzureAIEvaluator", "TargetCompletionEvalRunDataSource", "AzureAIAgentTargetParam"]},
        "azure.ai.agentserver.optimization": {"load_config": [], "CandidateConfig": []},
        "azure.ai.agentserver.responses": {"ResponsesAgentServerHost": [], "TextResponse": []},
        "agent_framework_foundry_hosting": {"ResponsesHostServer": []},
        "azure.ai.agentserver.agentframework": {},
        "azure.mgmt.containerregistrytasks": {},
        "azure.containerregistry": {"ContainerRegistryClient": ["get_manifest_properties"]},
        "azure.storage.blob": {"ContainerClient": ["from_container_url", "upload_blob"]},
        "openai.resources.responses": {"Responses": ["create", "retrieve", "cancel", "delete"]},
        "openai.resources.evals": {"Evals": ["create", "retrieve"]},
        "openai.resources.evals.runs": {"Runs": ["create", "retrieve", "list"]},
        "openai.resources.evals.runs.output_items": {"OutputItems": ["list", "retrieve"]},
        "agentconfig": {"load_agent_config": [], "load_instructions": [], "build_spec": [], "resolve_tools": []}, "llm_interface": {"connect": [], "AgentBinding": ["run"]},
    }
    facts = []
    for module_name, symbols in selections.items():
        record = {"module": module_name, "symbols": []}
        try:
            module = importlib.import_module(module_name)
            record["origin"] = getattr(module, "__file__", None)
            for symbol, methods in symbols.items():
                for expression in [symbol, *[symbol + "." + method for method in methods]]:
                    item = {"symbol": expression}
                    try:
                        value = module
                        for component in expression.split("."):
                            value = getattr(value, component)
                        item["runtime_wrapper_origin"] = inspect.getsourcefile(value)
                        implementation = inspect.unwrap(value)
                        source = inspect.getsourcefile(implementation)
                        item["origin"] = source
                        if source:
                            item["source_sha256"] = sha(Path(source).read_bytes())
                            item["line"] = inspect.getsourcelines(implementation)[1]
                        item["annotations"] = {key: str(annotation) for key, annotation in getattr(value, "__annotations__", {}).items()}
                        item["signature"] = str(inspect.signature(value))
                    except Exception as error:
                        item["error_type"] = type(error).__name__
                        item["error"] = str(error)
                    record["symbols"].append(item)
        except Exception as error:
            record["error_type"] = type(error).__name__
            record["error"] = str(error)
        facts.append(record)
    return {"python": sys.executable, "facts": facts, "network": "not_requested", "editor_interpreter": "unverified"}


def inventory():
    capture = json.loads((OUT / "capture.json").read_text())
    paths = [ROOT / item["path"] for item in capture["source"] if any(item["path"].startswith(root + "/") for root in ROOTS[:3])]
    entries = []
    for path in paths:
        relative = str(path.relative_to(ROOT))
        if "tests" in path.parts:
            continue
        source = path.read_text()
        item = {"path": relative, "lines": len(source.splitlines()), "bytes": path.stat().st_size,
                "production": path.suffix in {".py", ".sh"} or path.name == "Dockerfile"}
        if path.suffix == ".py":
            tree = ast.parse(source)
            item["functions"] = [{"name": node.name, "line": node.lineno, "end_line": node.end_lineno}
                                 for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
            item["imports"] = [{"line": node.lineno, "text": ast.get_source_segment(source, node)}
                               for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))]
        entries.append(item)
    production = [item for item in entries if item["production"]]
    arguments = [str(path.relative_to(ROOT)) for path in paths if "tests" not in path.parts]
    patterns = {
        "auth_http_candidates": r"Authorization|Bearer|httpx\.(get|post|Client)|client\.request\(|api\(\"|requests\.|send_request\(|HttpRequest\(",
        "dependency_sites": r"pip|uv (pip|build|add|remove|lock|sync|run)|--no-deps|--break-system-packages",
        "removal_callers": r"register.existing|optimizer.operation|optimize.retry.rejected|restore.sdk|install.loader|observe.validation|observe.holdout|SERIES|collect_candidates|def api\(",
        "cli_actions": r"add_argument\(|choices=|actions =|case |exec python|exec /usr/bin/python",
    }
    searches = {name: command(["rg", "-n", pattern, *arguments]) for name, pattern in patterns.items()}
    searches["removal_callers_with_tests"] = command(["rg", "-n", patterns["removal_callers"], *[str(path.relative_to(ROOT)) for path in paths]])
    return {"count_policy": "H/E/O captured active files; excludes tests, evidence, datasets, installed packages. Python AST counts all sync/async function definitions including nested/class methods; production files Python/shell/Dockerfile. HTTP/dependency matches are candidate sites for human classification, not inferred call counts.",
            "production_files": len(production), "production_lines": sum(item["lines"] for item in production),
            "custom_functions": sum(len(item.get("functions", [])) for item in production),
            "active_non_test_files": len(entries), "active_non_test_lines": sum(item["lines"] for item in entries),
            "files": entries, "rg": searches}


def load_owner(alias):
    root = ROOT / ROOTS[{"H": 0, "E": 1, "O": 2}[alias]]
    if alias == "H":
        sys.path[:0] = [str(root), str(ROOT / "libraries/modular-agents/modules/agent-config-build"),
                        str(ROOT / "libraries/llm-interface/src"), str(ROOT / "libraries/framework-core/src")]
    sys.path.insert(0, str(root / "deploy"))
    return importlib.import_module("prepare" if alias == "O" else "experiment")


def baseline(alias):
    platform.platform()
    scratch = OUT / ("scratch-" + alias)
    scratch.mkdir(exist_ok=True)
    tempfile.tempdir = str(scratch)
    def audit(event, arguments):
        if event in {"socket.connect", "socket.getaddrinfo", "subprocess.Popen"}:
            raise RuntimeError("F00 offline gate refuses network and subprocess dispatch")
        if event == "open" and isinstance(arguments[0], (str, bytes)):
            path = Path(os.fsdecode(arguments[0])).resolve()
            if "private" in path.parts and "dataset" in path.parts:
                raise RuntimeError("F00 raw private dataset read refused")
            mode, flags = arguments[1:3]
            writing = (isinstance(mode, str) and any(value in mode for value in "wax+")) or (isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT))
            if writing and not path.is_relative_to(OUT):
                raise RuntimeError("F00 write outside evidence refused")
    sys.addaudithook(audit)
    owner = load_owner(alias)
    function = {"H": "local_checks", "E": "local_validate", "O": "tests"}[alias]
    return {"equivalent_command": ["bash", ROOTS[{"H": 0, "E": 1, "O": 2}[alias]] + "/deploy/deploy.sh", "validate" if alias == "E" else "test"],
            "actual_invocation": owner.__file__ + "::" + function,
            "deviation": "CLI receipt writers are outside assigned writable paths; exact offline callable invoked without main, results retained here. Network/subprocess/private-data reads refused.",
            "result": getattr(owner, function)()}


def cloud():
    owner = load_owner("H")
    result = owner.preflight()
    caller = owner.cli(["account", "show", "--query", "{subscriptionId:id,tenantId:tenantId,cloud:environmentName,principalType:user.type,principalName:user.name}"])
    principal = owner.cli(["ad", "signed-in-user", "show", "--query", "{id:id,userPrincipalName:userPrincipalName}"])
    return {"preflight": result, "caller": caller, "principal": principal, "observations": owner.OBSERVATIONS,
            "cloud_mutation": False, "service_calls": "owner.preflight and owner.cli GET/list only; no shared context switch"}


def supplement():
    user_site = site.getusersitepackages()
    user_inventory = command(["uv", "pip", "list", "--python", "/usr/bin/python3", "--target", user_site, "--format", "json", "--strict", "--offline"])
    installed = json.loads(user_inventory["stdout"])
    result = {"user_site_command": user_inventory, "user_site_package_count": len(installed),
              "user_site_resolved": str(Path(user_site).resolve()), "user_site_is_symlink": Path(user_site).is_symlink(),
              "user_site_under_home": Path(user_site).resolve().is_relative_to(Path.home().resolve()),
              "uv_check_limitation": "--python /usr/bin/python3 checks zero packages. Explicit --target list --strict observes user-site; pip check has no --target option in uv 0.9.30.",
              "system_site_commands": [command(["uv", "pip", "list", "--python", "/usr/bin/python3", "--target", path, "--format", "json", "--strict", "--offline"]) for path in site.getsitepackages() if Path(path).is_dir()],
              "accepted_archives": [], "accepted_receipts": []}
    names = ["testbeds/foundry-hosted-agents/deploy/records/20260922T055856660275Z-build.json",
             "testbeds/foundry-hosted-agents/deploy/records/20260922T060314845976Z-build.json",
             "testbeds/foundry-hosted-agents/deploy/records/20260922T060615632239Z-verify.json",
             "testbeds/foundry-hosted-agents/deploy/records/20260922T060717524554Z-verify.json",
             "testbeds/foundry-agent-evaluation/deploy/records/approved-decision.json",
             "testbeds/foundry-agent-evaluation/deploy/records/20260922T075756325970Z-closeout.json",
             "testbeds/foundry-agent optimization/deploy/evidence/demonstration-result.json"]
    for name in names:
        path = ROOT / name
        document = json.loads(path.read_text())
        result["accepted_receipts"].append({**pin(path), "status": document.get("status"), "action": document.get("action"),
            "top_level_fields": sorted(document), "actual": document.get("actual"),
            "pins": document.get("pins"), "image": document.get("image")})
        if name.endswith("-build.json"):
            built = document["result"]
            archive = ROOT / ROOTS[0] / built["archive"]
            identity = {**pin(archive), "expected_sha256": built["archive_sha256"], "image": built["image"], "source": built["source"], "library_members": []}
            with tarfile.open(archive) as bundle:
                for member in bundle.getmembers():
                    if member.name.startswith("libraries/") and member.isfile():
                        digest = sha(bundle.extractfile(member).read())
                        current = ROOT / member.name
                        identity["library_members"].append({"path": member.name, "sha256": digest,
                            "current_source_equal": current.is_file() and sha(current.read_bytes()) == digest})
            result["accepted_archives"].append(identity)
    return result


def compatibility():
    from packaging.requirements import Requirement
    from packaging.utils import canonicalize_name

    supplement = json.loads((OUT / "supplement.json").read_text())["result"]
    inventories = [supplement["user_site_command"], *supplement["system_site_commands"]]
    names = {canonicalize_name(item["name"]) for inventory in inventories for item in json.loads(inventory["stdout"])}
    conflicts, missing, failures = [], [], []
    for name in sorted(names):
        try:
            distribution = metadata.distribution(name)
            for raw in distribution.requires or []:
                requirement = Requirement(raw)
                if requirement.marker and not requirement.marker.evaluate({"extra": ""}):
                    continue
                try:
                    installed = metadata.distribution(requirement.name)
                except metadata.PackageNotFoundError:
                    missing.append({"consumer": name, "requires": raw})
                    continue
                if not requirement.specifier.contains(installed.version, prereleases=True):
                    conflicts.append({"consumer": name, "consumer_version": distribution.version,
                        "requires": raw, "installed": installed.version, "origin": str(installed.locate_file(""))})
        except Exception as error:
            failures.append({"name": name, "error_type": type(error).__name__})
    return {"inventory_owner": "uv pip list explicit existing targets; compatibility checks use packaging.Requirement against actual interpreter importlib.metadata precedence",
            "unique_uv_names": len(names), "conflicts": conflicts, "missing": missing, "metadata_failures": failures,
            "scope": "base requirements only; optional extras require F01 selected profile resolution; no install or repair",
            "selected_versions": {name: metadata.version(name) for name in ["azure-ai-projects", "openai", "azure-ai-agentserver-core", "azure-ai-agentserver-responses", "azure-ai-agentserver-optimization", "agent-framework-core", "agent-framework-foundry", "agent-framework-openai", "agent-framework", "azure-ai-agentserver-agentframework", "azure-identity", "azure-core", "azure-storage-blob", "setuptools", "wheel"]}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("environment", "sdk", "inventory", "baseline-H", "baseline-E", "baseline-O", "cloud", "supplement", "compatibility"))
    args = parser.parse_args()
    started = time.monotonic()
    receipt = {"action": args.action, "started_at": datetime.now(timezone.utc).isoformat(), "status": "failed", "source": pin(Path(__file__))}
    try:
        function = (lambda: baseline(args.action[-1])) if args.action.startswith("baseline-") else globals()[args.action]
        receipt["result"] = function()
        receipt["status"] = "complete"
    except Exception as error:
        receipt["error_type"] = type(error).__name__
        receipt["error"] = str(error)
        owner = sys.modules.get("experiment") or sys.modules.get("prepare")
        if owner is not None:
            receipt["owner_observations"] = getattr(owner, "OBSERVATIONS", getattr(owner, "EVENTS", []))
    receipt["seconds"] = time.monotonic() - started
    receipt["finished_at"] = datetime.now(timezone.utc).isoformat()
    name = args.action + ".json"
    if (OUT / name).exists():
        name = args.action + "-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + ".json"
    reference = save(name, receipt)
    print(json.dumps({"status": receipt["status"], "receipt": reference, "seconds": receipt["seconds"], "error_type": receipt.get("error_type")}))
    return 0 if receipt["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())