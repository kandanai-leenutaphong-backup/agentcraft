from __future__ import annotations

import argparse
import fnmatch
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

TAGS = {
    "managed-by": "agentcraft-deploy",
    "capability": "azure-data-connectors",
    "purpose": "live-crud-tests",
    "data-policy": "synthetic-only",
    "lifecycle": "explicit-teardown",
}
GROUP_ACTION = "Microsoft.Resources/subscriptions/resourceGroups/"


class DeploymentError(RuntimeError):
    pass


@dataclass(frozen=True)
class Target:
    subscription_id: str
    tenant_id: str
    resource_group: str
    location: str
    cloud: str
    capability: str = "azure-data-connectors"
    purpose: str = "live-crud-tests"
    data_policy: str = "synthetic-only"

    @property
    def resource_id(self) -> str:
        return f"/subscriptions/{self.subscription_id}/resourceGroups/{self.resource_group}"

    @property
    def tags(self) -> dict[str, str]:
        return {**TAGS, "capability": self.capability, "purpose": self.purpose, "data-policy": self.data_policy}

    @classmethod
    def load(cls, path: Path) -> Target:
        patterns = {
            "SUBSCRIPTION_ID": r"[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}",
            "TENANT_ID": r"[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}",
            "RESOURCE_GROUP": r"rg-agentcraft-[a-z0-9-]{1,65}",
            "LOCATION": r"[a-z][a-z0-9]{1,40}",
            "CLOUD": r"AzureCloud",
        }
        optional = {"CAPABILITY": "capability", "PURPOSE": "purpose", "DATA_POLICY": "data_policy"}
        allowed = {**patterns, **{key: r"[a-z][a-z0-9-]{1,63}" for key in optional}}
        values = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip() or line.startswith("#"):
                continue
            key, separator, value = line.partition("=")
            if key not in allowed or key in values or separator != "=" or not re.fullmatch(allowed[key], value):
                raise DeploymentError("Environment must contain only unique validated non-secret target assignments; no shell syntax or credential fields.")
            values[key] = value
        if not set(patterns).issubset(values):
            raise DeploymentError("Environment requires SUBSCRIPTION_ID, TENANT_ID, RESOURCE_GROUP, LOCATION and CLOUD.")
        return cls(*(values[key] for key in patterns), **{field: values[key] for key, field in optional.items() if key in values})


def azure_cli(*arguments: str, timeout_seconds: float = 180):
    try:
        result = subprocess.run(
            ["az", *arguments, "--only-show-errors", "--output", "json"],
            capture_output=True, text=True, check=True, timeout=timeout_seconds,
        )
        return json.loads(result.stdout) if result.stdout.strip() else None
    except subprocess.TimeoutExpired:
        raise DeploymentError("Azure CLI timed out; the outcome may be unknown. Run verify before retrying a mutation.") from None
    except subprocess.CalledProcessError as error:
        known = next((code for code in ("AuthorizationFailed", "RequestDisallowedByPolicy", "ScopeLocked", "ExpiredAuthenticationToken")
                      if code in (error.stderr or "")), "command_failed")
        raise DeploymentError(f"Azure CLI {' '.join(arguments[:2])}: {known}. Inspect account, permissions, policy and locks; no automatic grant or policy change is allowed.") from None
    except (OSError, ValueError):
        raise DeploymentError("Azure CLI could not run or returned invalid JSON; verify the installed CLI and login.") from None


def permits(entries: list, action: str) -> bool:
    return any(
        any(fnmatch.fnmatchcase(action.lower(), pattern.lower()) for pattern in entry.get("actions", []))
        and not any(fnmatch.fnmatchcase(action.lower(), pattern.lower()) for pattern in entry.get("notActions", []))
        for entry in entries
    )


class ResourceGroupDeployment:
    def __init__(self, target: Target, cli: Callable = azure_cli) -> None:
        self.target = target
        self.cli = cli

    def preflight(self, required_action: str) -> dict:
        account = self.cli("account", "show", "--query", "{id:id,tenantId:tenantId,state:state,cloud:environmentName}")
        if account.get("tenantId", "").lower() != self.target.tenant_id:
            raise DeploymentError(f"Wrong tenant. Operator must run az login --tenant {self.target.tenant_id}, then select the documented subscription.")
        if account.get("id", "").lower() != self.target.subscription_id:
            raise DeploymentError(f"Wrong active subscription. Operator must run az account set --subscription {self.target.subscription_id}.")
        if account.get("state") != "Enabled" or account.get("cloud") != self.target.cloud:
            raise DeploymentError("Account must be Enabled in the configured AzureCloud; no cloud switch is performed automatically.")
        permissions = self.cli(
            "rest", "--method", "get", "--url",
            f"https://management.azure.com/subscriptions/{self.target.subscription_id}/providers/Microsoft.Authorization/permissions?api-version=2022-04-01",
            "--query", "value[].{actions:actions,notActions:notActions}",
        )
        if not isinstance(permissions, list) or not permits(permissions, GROUP_ACTION + required_action):
            raise DeploymentError(f"Caller lacks reported {GROUP_ACTION}{required_action} at subscription scope. Ask an administrator for appropriate scoped access; do not grant it here.")
        return {"subscription_id": self.target.subscription_id, "tenant_id": self.target.tenant_id,
                "cloud": self.target.cloud, "required_action": GROUP_ACTION + required_action,
                "reported_action_allowed": True, "effective_access_complete": False}

    def exists(self) -> bool:
        result = self.cli("group", "exists", "--name", self.target.resource_group, "--subscription", self.target.subscription_id)
        if type(result) is not bool:
            raise DeploymentError("Resource-group existence could not be established.")
        return result

    def snapshot(self) -> dict:
        group = self.cli("group", "show", "--name", self.target.resource_group, "--subscription", self.target.subscription_id)
        tags = group.get("tags") or {}
        if (group.get("id", "").lower() != self.target.resource_id.lower()
                or group.get("location") != self.target.location
            or any(tags.get(name) != value for name, value in self.target.tags.items())):
            raise DeploymentError("Existing group has unexpected ID, location or ownership tags; refusing adoption, retagging or deletion.")
        if group.get("properties", {}).get("provisioningState") != "Succeeded":
            raise DeploymentError("Resource-group read-back is not Succeeded; inspect before another mutation.")
        resources = self.cli("resource", "list", "--resource-group", self.target.resource_group,
                             "--subscription", self.target.subscription_id, "--query", "[].{id:id,name:name,type:type}")
        if not isinstance(resources, list):
            raise DeploymentError("Resource-group contents could not be enumerated.")
        return {"resource_id": group["id"], "name": group["name"], "location": group["location"],
            "provisioning_state": "Succeeded", "tags": {name: tags[name] for name in self.target.tags},
                "resource_count": len(resources), "resources": resources,
                "observed_at_utc": datetime.now(timezone.utc).isoformat(), "read_back_verified": True}

    def run(self, action: str, confirmation: str | None = None) -> dict:
        if action not in {"plan", "create", "verify", "teardown"}:
            raise DeploymentError("Unknown resource-group action.")
        if action in {"create", "teardown"} and confirmation != self.target.resource_id:
            raise DeploymentError(f"Explicit confirmation required: --confirm {self.target.resource_id}")
        required = "write" if action == "create" else "delete" if action == "teardown" else "read"
        preflight = self.preflight(required)
        present = self.exists()
        if action == "plan":
            locations = self.cli("account", "list-locations", "--query", "[].name")
            if not isinstance(locations, list) or self.target.location not in locations:
                raise DeploymentError("Configured resource-group location is not listed for this account.")
            return {"action": "plan", "target": self.target.resource_id, "location": self.target.location,
                    "would_create": not present, "existing": self.snapshot() if present else None,
                    "tags": self.target.tags, "confirmation_required": self.target.resource_id,
                    "scope": "resource-group-only", "preflight": preflight}
        if action == "create":
            if not present:
                locations = self.cli("account", "list-locations", "--query", "[].name")
                if not isinstance(locations, list) or self.target.location not in locations:
                    raise DeploymentError("Configured resource-group location is not listed for this account.")
                self.cli("group", "create", "--name", self.target.resource_group, "--location", self.target.location,
                         "--subscription", self.target.subscription_id, "--tags", *(f"{name}={value}" for name, value in self.target.tags.items()))
            return {"action": "unchanged" if present else "created", "preflight": preflight, **self.snapshot()}
        if action == "verify":
            if not present:
                raise DeploymentError("Resource group is absent. Creation needs a separate authorized create action.")
            return {"action": "verified", "preflight": preflight, **self.snapshot()}
        if not present:
            return {"action": "already_absent", "resource_id": self.target.resource_id, "read_back_verified": True}
        snapshot = self.snapshot()
        if snapshot["resource_count"]:
            raise DeploymentError("Teardown refuses non-empty groups. Review the actual resources and authorize their separate lifecycle first.")
        locks = self.cli("lock", "list", "--resource-group", self.target.resource_group,
                         "--subscription", self.target.subscription_id, "--query", "[].{id:id,level:level}")
        if not isinstance(locks, list) or locks:
            raise DeploymentError("Teardown refuses a locked group or unknown lock status; do not remove locks automatically.")
        self.cli("group", "delete", "--name", self.target.resource_group, "--subscription", self.target.subscription_id, "--yes")
        if self.exists():
            raise DeploymentError("Deletion returned but resource group is still present; absence is not verified.")
        return {"action": "deleted", "resource_id": self.target.resource_id, "read_back_verified": True}


def main() -> int:
    parser = argparse.ArgumentParser(description="Plan, create, verify or explicitly retire an owned testing resource group only.")
    parser.add_argument("-e", "--environment", choices=("azdata-live", "agentcraft-testing"), default="azdata-live")
    parser.add_argument("action", choices=("plan", "create", "verify", "teardown"), nargs="?", default="plan")
    parser.add_argument("--confirm")
    options = parser.parse_args()
    try:
        if shutil.which("az") is None:
            raise DeploymentError("Azure CLI is required. Install it and run az login in your own terminal before proceeding.")
        target = Target.load(Path(__file__).resolve().parent / "env" / f"{options.environment}.env")
        result = ResourceGroupDeployment(target).run(options.action, options.confirm)
        print(json.dumps(result, indent=2))
        return 0
    except (DeploymentError, OSError, ValueError, TypeError, KeyError) as error:
        print(f"Deployment refused: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())