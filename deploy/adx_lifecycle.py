from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from resource_group import DeploymentError, azure_cli, permits


@dataclass(frozen=True)
class AdxTarget:
    subscription_id: str
    tenant_id: str
    resource_group: str
    cluster: str
    location: str
    database: str
    endpoint: str
    cloud: str

    @property
    def resource_id(self) -> str:
        return (f"/subscriptions/{self.subscription_id}/resourceGroups/{self.resource_group}"
                f"/providers/Microsoft.Kusto/clusters/{self.cluster}")

    @classmethod
    def load(cls, path: Path) -> AdxTarget:
        def unique_object(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise DeploymentError("Duplicate ADX target field; configuration must be unambiguous.")
                result[key] = value
            return result

        values = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_object)
        uuid = r"[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}"
        patterns = {
            "subscription_id": uuid, "tenant_id": uuid,
            "resource_group": r"[A-Za-z0-9][A-Za-z0-9_-]{0,89}",
            "cluster": r"[a-z][a-z0-9]{3,21}", "location": r"[a-z][a-z0-9]{1,40}",
            "database": r"[A-Za-z][A-Za-z0-9_]{0,127}", "endpoint": r"https://[a-z0-9.]+",
            "cloud": r"AzureCloud",
        }
        if (not isinstance(values, dict) or set(values) != set(patterns)
                or any(not isinstance(values[key], str) or not re.fullmatch(pattern, values[key])
                       for key, pattern in patterns.items())):
            raise DeploymentError("ADX target requires only validated non-secret target fields; no grants, credentials or commands.")
        target = cls(**values)
        if target.endpoint != f"https://{target.cluster}.{target.location}.kusto.windows.net":
            raise DeploymentError("ADX endpoint must match the configured cluster and location in AzureCloud.")
        return target


class AdxLifecycle:
    def __init__(self, target: AdxTarget, cli: Callable = azure_cli) -> None:
        self.target = target
        self.cli = cli
        self.commands: list[dict] = []
        self.last_observed: dict | None = None

    def _call(self, *arguments: str, timeout_seconds: float = 180):
        self.commands.append({"argv": ["az", *arguments, "--only-show-errors", "--output", "json"],
                              "timeout_seconds": timeout_seconds})
        return self.cli(*arguments, timeout_seconds=timeout_seconds)

    @property
    def arguments(self) -> tuple[str, ...]:
        return ("--name", self.target.cluster, "--resource-group", self.target.resource_group,
                "--subscription", self.target.subscription_id)

    def preflight(self, mutation: bool) -> list:
        account = self._call("account", "show", "--query", "{id:id,tenantId:tenantId,state:state,cloud:environmentName}")
        if account.get("tenantId", "").lower() != self.target.tenant_id:
            raise DeploymentError(f"Wrong tenant. Operator must run az login --tenant {self.target.tenant_id}.")
        if account.get("id", "").lower() != self.target.subscription_id:
            raise DeploymentError(f"Wrong subscription. Operator must run az account set --subscription {self.target.subscription_id}.")
        if account.get("state") != "Enabled" or account.get("cloud") != self.target.cloud:
            raise DeploymentError("Account must be Enabled in the configured AzureCloud.")
        permissions = self._call(
            "rest", "--method", "get", "--url",
            f"https://management.azure.com{self.target.resource_id}/providers/Microsoft.Authorization/permissions?api-version=2022-04-01",
            "--subscription", self.target.subscription_id,
            "--query", "value[].{actions:actions,notActions:notActions}",
        )
        actions = ["read", "write"] if mutation else ["read"]
        if not isinstance(permissions, list) or any(
            not permits(permissions, "Microsoft.Kusto/clusters/" + action) for action in actions
        ):
            raise DeploymentError("Required cluster-scoped read/write permission is not reported. No role or policy change is authorized here.")
        return permissions

    def snapshot(self) -> dict:
        cluster = self._call("kusto", "cluster", "show", *self.arguments,
                             "--query", "{id:id,name:name,location:location,state:state,provisioningState:provisioningState,enableAutoStop:enableAutoStop,uri:uri,protectedSettings:{enableDiskEncryption:enableDiskEncryption,enableStreamingIngest:enableStreamingIngest,enablePurge:enablePurge,enableDoubleEncryption:enableDoubleEncryption,publicNetworkAccess:publicNetworkAccess,engineType:engineType,restrictOutboundNetworkAccess:restrictOutboundNetworkAccess,publicIPType:publicIPType}}")
        if isinstance(cluster, dict):
            self.last_observed = {**cluster, "observed_at_utc": datetime.now(timezone.utc).isoformat()}
        if (not isinstance(cluster, dict) or cluster.get("id", "").lower() != self.target.resource_id.lower()
                or cluster.get("name") != self.target.cluster
                or str(cluster.get("location", "")).replace(" ", "").lower() != self.target.location
                or cluster.get("uri") != self.target.endpoint or type(cluster.get("enableAutoStop")) is not bool):
            raise DeploymentError("Cluster ID, name, region, endpoint or auto-stop read-back does not match the exact target; refusing mutation.")
        return self.last_observed

    def wait_running(self) -> dict:
        condition = "state=='Running' && provisioningState=='Succeeded'"
        self._call("kusto", "cluster", "wait", *self.arguments, "--custom", condition,
                   "--interval", "20", "--timeout", "1800", timeout_seconds=1860)
        return self.snapshot()

    @staticmethod
    def require_running(snapshot: dict, *, auto_stop_disabled: bool = False) -> None:
        if (snapshot.get("state") != "Running" or snapshot.get("provisioningState") != "Succeeded"
                or (auto_stop_disabled and snapshot.get("enableAutoStop") is not False)):
            raise DeploymentError("Read-back has not proved Running, Succeeded and the requested auto-stop setting. Inspect before retrying; no rollback is implied.")

    def run(self, action: str, confirmation: str | None = None) -> dict:
        if action not in {"plan", "keep-running", "verify"}:
            raise DeploymentError("Only plan, keep-running and verify are supported for this existing cluster.")
        if action == "keep-running" and confirmation != self.target.resource_id:
            raise DeploymentError(f"Explicit authorization required: --confirm {self.target.resource_id}")
        self.commands = []
        permissions = self.preflight(action == "keep-running")
        before = self.snapshot()
        common = {"schema_version": 1, "target": self.target.resource_id, "tenant_id": self.target.tenant_id,
                  "database": self.target.database, "continuous_billing": True,
                  "external_stop_schedules": "unknown", "effective_access_complete": False,
                  "commands": self.commands}
        if action == "plan":
            return {**common, "action": "plan", "before": before, "confirmation_required": self.target.resource_id,
                    "allowed_mutations": ["start-if-stopped", "enableAutoStop=false"],
                    "wait_timeout_seconds": 1800, "read_back_verified": False}
        if action == "verify":
            self.require_running(before, auto_stop_disabled=True)
            return {**common, "action": "verified", "after": before, "read_back_verified": True}
        current = before
        changed = False
        if before.get("provisioningState") not in {"Succeeded", "Running"}:
            raise DeploymentError("Unsupported provisioning transition; inspect state before any mutation.")
        if before["state"] == "Stopped" and before["provisioningState"] == "Succeeded":
            if not permits(permissions, "Microsoft.Kusto/clusters/start/action"):
                raise DeploymentError("Cluster start permission is not reported; no grant is authorized.")
            self._call("kusto", "cluster", "start", *self.arguments, "--no-wait")
            changed = True
            current = self.wait_running()
        elif before["state"] == "Starting" or (before["state"] == "Running" and before["provisioningState"] == "Running"):
            current = self.wait_running()
        elif before["state"] != "Running":
            raise DeploymentError("Unsupported cluster transition; only Stopped, Starting or Running can be handled. No stop or teardown is allowed.")
        self.require_running(current)
        if current["enableAutoStop"]:
            self._call("rest", "--method", "patch", "--url",
                       f"https://management.azure.com{self.target.resource_id}?api-version=2022-02-01",
                       "--subscription", self.target.subscription_id,
                       "--body", json.dumps({"properties": {"enableAutoStop": False}}, separators=(",", ":")),
                       "--query", "{id:id,state:properties.state,provisioningState:properties.provisioningState,enableAutoStop:properties.enableAutoStop}")
            changed = True
            current = self.wait_running()
        self.require_running(current, auto_stop_disabled=True)
        if current.get("protectedSettings") != before.get("protectedSettings"):
            raise DeploymentError("Protected cluster settings changed during the operation; no corrective mutation is authorized. Review the before/after receipt.")
        return {**common, "action": "kept_running" if changed else "unchanged", "before": before,
                "after": current, "read_back_verified": True}


def main() -> int:
    parser = argparse.ArgumentParser(description="Keep only the configured existing Perth ADX cluster running; continuous billing applies.")
    parser.add_argument("action", choices=("plan", "keep-running", "verify"), nargs="?", default="plan")
    parser.add_argument("--confirm")
    parser.add_argument("--record", type=Path, help="New JSON receipt directly under deploy/records; existing evidence is never overwritten.")
    options = parser.parse_args()
    directory = Path(__file__).resolve().parent
    receipt = None
    runner = None
    try:
        if shutil.which("az") is None:
            raise DeploymentError("Azure CLI with the kusto extension is required; install prerequisites before proceeding.")
        if options.action == "keep-running" and options.record is None:
            raise DeploymentError("keep-running requires --record with a new deploy/records JSON path.")
        if options.record is not None:
            path = options.record.resolve()
            if path.parent != directory / "records" or path.suffix != ".json":
                raise DeploymentError("Receipt must be a new JSON file directly under deploy/records.")
            receipt = path.open("x", encoding="utf-8")
        target = AdxTarget.load(directory / "env" / "existing-perth-adx-lifecycle.json")
        runner = AdxLifecycle(target)
        result = runner.run(options.action, options.confirm)
        status = 0
    except (DeploymentError, OSError, ValueError, TypeError, KeyError) as error:
        result = {"schema_version": 1, "action": options.action, "read_back_verified": False,
                  "error": str(error) if isinstance(error, DeploymentError) else "Invalid configuration, receipt path or CLI response.",
                  "last_observed": runner.last_observed if runner else None,
                  "commands": runner.commands if runner else []}
        status = 1
    result["recorded_at_utc"] = datetime.now(timezone.utc).isoformat()
    if receipt is not None:
        with receipt:
            json.dump(result, receipt, indent=2)
            receipt.write("\n")
    print(json.dumps(result, indent=2), file=sys.stdout if status == 0 else sys.stderr)
    return status


if __name__ == "__main__":
    raise SystemExit(main())