"""Non-authoritative, read-only metadata preflight. Never installs or mutates Azure."""

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[6]
SUBSCRIPTION = "67255afe-8670-4401-a1b8-df6ca63a3516"
TENANT = "c79ab2bb-79cb-47f1-b4da-b6852fe45ff7"
GROUP = "rg-agentcraft-dev"
PIN = "b2b59aebc22e8205f66586ca18d8c0aa8efcd60ab05465816806606ed04487ff"
APP = "template_apps/investigation_app"
PROJECT = "demonstration_project/agentcraft_projects/overseer-self-optimization"
SNAPSHOTS = [
    f"{PROJECT}/constitution/constitution.yaml",
    ".github/agents/local-dev-test-subject.agent.md",
    "deploy/deploy.sh", "deploy/resource_group.py", "deploy/README.md",
    "deploy/tests/test_resource_group.py", "deploy/tests/test_writeup.py",
    f"{APP}/deploy/deploy.sh", f"{APP}/deploy/cloud.py", f"{APP}/deploy/README.md",
    f"{APP}/deploy/tests/test_cloud.py", f"{APP}/deploy/env/investigation-isolated.json",
    f"{APP}/pyproject.toml", f"{APP}/uv.lock",
    f"{APP}/app/cybereye/frontend/package.json",
    f"{APP}/app/cybereye/frontend/package-lock.json",
    f"{APP}/app/cybereye/backend/main.py", f"{APP}/app/cybereye/backend/config.py",
    f"{APP}/app/cybereye/backend/data/graph_binding.py",
    f"{APP}/app/cybereye/backend/data/adx.py",
    f"{APP}/app/cybereye/backend/agents/profiles.py",
    f"{APP}/app/cybereye/backend/agents/editor.py",
    f"{APP}/app/cybereye/backend/security/config.py",
    f"{APP}/app/cybereye/backend/security/composition.py",
    f"{APP}/app/cybereye/control/situation_detector.json",
    "libraries/azure-data-connectors/CONTRACT.md", "libraries/capabilities.json",
]


def now():
    return datetime.now(timezone.utc).isoformat()


def invoke(label, arguments, cwd=ROOT):
    import os

    started = now()
    environment = dict(os.environ, AZURE_CORE_COLLECT_TELEMETRY="no",
                       AZURE_EXTENSION_USE_DYNAMIC_INSTALL="no", PYTHONDONTWRITEBYTECODE="1")
    try:
        result = subprocess.run(arguments, cwd=cwd, env=environment, capture_output=True,
                                text=True, timeout=25, check=False)
        try:
            output = json.loads(result.stdout)
        except json.JSONDecodeError:
            output = result.stdout[:24000]
        return {"label": label, "argv": arguments, "started_at": started,
                "finished_at": now(), "exit_code": result.returncode,
                "stdout": output, "stderr": result.stderr[:4000],
                "stdout_truncated": not isinstance(output, (dict, list)) and len(result.stdout) > 24000}
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"label": label, "argv": arguments, "started_at": started,
                "finished_at": now(), "exit_code": None, "failure": type(error).__name__}


def azure(label, arguments, query=None):
    command = ["az", *arguments]
    if query:
        command.extend(["--query", query])
    command.extend(["--output", "json", "--only-show-errors"])
    return invoke(label, command)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--azure", action="store_true", help="Bounded non-secret Azure control-plane GETs")
    arguments = parser.parse_args()
    result = {"kind": "non-authoritative-read-only-preflight", "observed_at": now(),
              "root": str(ROOT), "effective_effort": "unverified", "commands": [],
              "resources_changed": [], "model_calls": 0, "workers": []}
    result["snapshots_needed"] = [
        {"path": relative, "exists": (ROOT / relative).is_file(),
         "sha256": hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
         if (ROOT / relative).is_file() else None} for relative in SNAPSHOTS]
    result["constitution_pin_matches"] = result["snapshots_needed"][0]["sha256"] == PIN
    result["tools"] = {name: shutil.which(name) for name in ("az", "python3", "node", "npm", "uv", "docker")}
    result["system_distributions"] = {}
    for package in ("fastapi", "azure-identity", "azure-cosmos", "azure-data-tables",
                    "azdata", "llm-interface", "entra-auth", "signed-dev-access", "pytest"):
        try:
            result["system_distributions"][package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            result["system_distributions"][package] = None
    result["app_dockerfiles"] = [str(path.relative_to(ROOT)) for path in (ROOT / APP).glob("**/Dockerfile*")
                                 if "node_modules" not in path.parts and ".venv" not in path.parts]
    result["frontend"] = {relative: (ROOT / APP / "app/cybereye/frontend" / relative).exists()
                          for relative in ("node_modules/typescript/bin/tsc", "node_modules/vite/bin/vite.js",
                                           "dist/index.html", "package-lock.json")}
    if arguments.azure and result["constitution_pin_matches"]:
        account = azure("active-account", ["account", "show"],
                        "{subscriptionId:id,tenantId:tenantId,state:state,cloud:environmentName}")
        result["commands"].append(account)
        if account.get("stdout") != {"subscriptionId": SUBSCRIPTION, "tenantId": TENANT,
                                     "state": "Enabled", "cloud": "AzureCloud"}:
            result["blocked"] = "Active account mismatch or unreadable; no further Azure reads"
        else:
            scoped = ["--subscription", SUBSCRIPTION]
            probes = [
                ("group", ["group", "list", *scoped],
                 f"[?name=='{GROUP}'].{{id:id,location:location,tags:tags}}"),
                ("contents", ["resource", "list", *scoped, "--resource-group", GROUP],
                 "[].{id:id,type:type,location:location}"),
                ("model-accounts", ["cognitiveservices", "account", "list", *scoped],
                 "[].{id:id,name:name,resourceGroup:resourceGroup,kind:kind,location:location,endpoint:properties.endpoint,publicNetworkAccess:properties.publicNetworkAccess}"),
                ("search-skus-in-use", ["search", "service", "list", *scoped],
                 "[].{id:id,location:location,sku:sku.name,replicas:replicaCount,partitions:partitionCount}"),
            ]
            for label, command, query in probes:
                result["commands"].append(azure(label, command, query))
            for namespace, version in (("Microsoft.App", "2024-03-01"),
                                       ("Microsoft.DocumentDB", "2024-05-15"),
                                       ("Microsoft.Search", "2023-11-01")):
                url = (f"https://management.azure.com/subscriptions/{SUBSCRIPTION}/providers/"
                       f"{namespace}/locations/australiaeast/usages?api-version={version}")
                result["commands"].append(azure(f"quota-{namespace}",
                    ["rest", "--method", "get", "--url", url, *scoped],
                    "{nextLink:nextLink,value:value[].{name:name.value,currentValue:currentValue,limit:limit,unit:unit}}"))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()