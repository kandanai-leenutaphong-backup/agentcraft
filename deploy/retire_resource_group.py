from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from resource_group import DeploymentError, ResourceGroupDeployment, Target, azure_cli


def digest(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def load_target(path: Path) -> tuple[Target, dict[str, str]]:
    def unique_object(pairs):
        values = {}
        for key, value in pairs:
            if key in values:
                raise DeploymentError("Duplicate retirement configuration field.")
            values[key] = value
        return values

    values = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_object)
    uuid = r"[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}"
    patterns = {"subscription_id": uuid, "tenant_id": uuid, "resource_group": r"rg-singtel-ticket-poc",
                "location": r"[a-z][a-z0-9]{1,40}", "cloud": r"AzureCloud"}
    if (not isinstance(values, dict) or set(values) != {*patterns, "expected_tags"}
            or any(not isinstance(values[key], str) or not re.fullmatch(pattern, values[key])
                   for key, pattern in patterns.items())):
        raise DeploymentError("Retirement configuration must name only the exact legacy group and validated non-secret target fields.")
    tags = values["expected_tags"]
    if (not isinstance(tags, dict) or set(tags) != {"data", "owner", "project"}
            or any(not isinstance(value, str) or not re.fullmatch(r"[a-z0-9-]{1,64}", value) for value in tags.values())):
        raise DeploymentError("Retirement requires the observed legacy ownership tags, not an adoption or retag operation.")
    return Target(**{key: values[key] for key in patterns}), tags


class ResourceGroupRetirement:
    def __init__(self, target: Target, expected_tags: dict[str, str], cli: Callable = azure_cli) -> None:
        self.target = target
        self.expected_tags = expected_tags
        self.cli = cli
        self.commands: list[dict] = []
        self.last_observed: dict | None = None
        self.group = ResourceGroupDeployment(target, self._call)

    def _call(self, *arguments: str, timeout_seconds: float = 180):
        self.commands.append({"argv": ["az", *arguments, "--only-show-errors", "--output", "json"],
                              "timeout_seconds": timeout_seconds})
        return self.cli(*arguments, timeout_seconds=timeout_seconds)

    @property
    def arguments(self) -> tuple[str, ...]:
        return ("--name", self.target.resource_group, "--subscription", self.target.subscription_id)

    def require_no_locks(self) -> None:
        group_locks = self._call("lock", "list", "--resource-group", self.target.resource_group,
                                 "--subscription", self.target.subscription_id, "--query", "[].{id:id,level:level}")
        subscription_locks = self._call(
            "rest", "--method", "get", "--url",
            f"https://management.azure.com/subscriptions/{self.target.subscription_id}/providers/Microsoft.Authorization/locks?api-version=2016-09-01",
            "--query", "value[].{id:id,level:properties.level}")
        if not isinstance(group_locks, list) or not isinstance(subscription_locks, list) or group_locks or subscription_locks:
            raise DeploymentError("Retirement refuses governance locks or unknown lock status. No lock removal is authorized.")

    def snapshot(self) -> dict:
        group = self._call("group", "show", *self.arguments, "--query",
                           "{id:id,name:name,location:location,tags:tags,managedBy:managedBy,provisioningState:properties.provisioningState}")
        if (not isinstance(group, dict) or group.get("id", "").lower() != self.target.resource_id.lower()
                or group.get("name") != self.target.resource_group or group.get("location") != self.target.location
                or group.get("tags") != self.expected_tags or group.get("managedBy")
                or group.get("provisioningState") != "Succeeded"):
            raise DeploymentError("Legacy group identity, ownership, location or lifecycle changed. Inspect before another mutation.")
        resources = self._call("resource", "list", "--resource-group", self.target.resource_group,
                               "--subscription", self.target.subscription_id,
                               "--query", "[].{id:id,name:name,type:type,location:location,kind:kind}")
        prefix = self.target.resource_id.lower() + "/providers/"
        if (not isinstance(resources, list) or any(not isinstance(resource, dict)
                or not isinstance(resource.get("id"), str) or not resource["id"].lower().startswith(prefix)
                for resource in resources)):
            raise DeploymentError("Inventory is unknown or contains resources outside the authorized group.")
        ids = [resource["id"].lower() for resource in resources]
        if len(ids) != len(set(ids)):
            raise DeploymentError("Inventory contains duplicate resource IDs.")
        self.last_observed = {"group": group, "resources": sorted(resources, key=lambda resource: resource["id"].lower())}
        return self.last_observed

    def wait_absent(self) -> None:
        self._call("group", "wait", *self.arguments, "--deleted", "--interval", "20", "--timeout", "3600",
                   timeout_seconds=3660)
        if self.group.exists():
            raise DeploymentError("Resource group remains present after the native waiter; deletion is not verified.")

    def run(self, action: str, confirmation: str | None = None, inventory: dict | None = None,
            inventory_sha256: str | None = None) -> dict:
        if action not in {"plan", "delete", "wait", "verify"}:
            raise DeploymentError("Unsupported retirement action.")
        if action == "delete":
            if confirmation != self.target.resource_id:
                raise DeploymentError(f"Exact group confirmation required: --confirm {self.target.resource_id}")
            if (not isinstance(inventory, dict) or inventory.get("action") != "plan"
                    or inventory.get("target") != self.target.resource_id or not isinstance(inventory.get("snapshot"), dict)
                    or not isinstance(inventory_sha256, str) or not re.fullmatch(r"[a-f0-9]{64}", inventory_sha256)
                    or inventory.get("inventory_sha256") != inventory_sha256 or digest(inventory["snapshot"]) != inventory_sha256):
                raise DeploymentError("Delete requires the frozen plan and its explicitly confirmed inventory SHA-256.")
        preflight = self.group.preflight("delete" if action == "delete" else "read")
        common = {"schema_version": 1, "target": self.target.resource_id, "tenant_id": self.target.tenant_id,
                  "location": self.target.location, "preflight": preflight, "commands": self.commands,
                  "scope": "entire-named-resource-group-including-service-data",
                  "external_resources_directly_mutated": [], "tenant_objects_deleted": False}
        if not self.group.exists():
            return {**common, "action": "verified_absent" if action == "verify" else "already_absent", "read_back_verified": True}
        if action == "verify":
            raise DeploymentError("Legacy group still exists. Deletion has not been verified; inspect or use the read-only wait action.")
        if action == "wait":
            self.wait_absent()
            return {**common, "action": "verified_absent", "read_back_verified": True}
        self.require_no_locks()
        snapshot = self.snapshot()
        inventory_digest = digest(snapshot)
        if action == "plan":
            return {**common, "action": "plan", "snapshot": snapshot, "resource_count": len(snapshot["resources"]),
                    "inventory_sha256": inventory_digest, "confirmation_required": self.target.resource_id,
                    "read_back_verified": True, "deletion_performed": False}
        if inventory_digest != inventory_sha256:
            raise DeploymentError("Legacy resource inventory changed since the frozen plan. No deletion issued; inspect and reconfirm scope.")
        self._call("group", "delete", *self.arguments, "--yes", "--no-wait")
        self.wait_absent()
        return {**common, "action": "deleted", "inventory_sha256": inventory_digest,
                "resource_count_before": len(snapshot["resources"]), "read_back_verified": True}


def main() -> int:
    parser = argparse.ArgumentParser(description="Retire only the configured legacy Singtel resource group after exact inventory confirmation.")
    parser.add_argument("action", choices=("plan", "delete", "wait", "verify"))
    parser.add_argument("--confirm")
    parser.add_argument("--inventory", type=Path)
    parser.add_argument("--confirm-inventory")
    parser.add_argument("--record", type=Path, required=True)
    options = parser.parse_args()
    directory = Path(__file__).resolve().parent
    receipt = None
    runner = None
    try:
        record = options.record.resolve()
        if record.parent != directory / "records" or record.suffix != ".json":
            raise DeploymentError("Receipt must be a new JSON file directly under deploy/records.")
        receipt = record.open("x", encoding="utf-8")
        target, tags = load_target(directory / "env" / "singtel-retirement.json")
        runner = ResourceGroupRetirement(target, tags)
        inventory = json.loads(options.inventory.read_text(encoding="utf-8")) if options.inventory else None
        result = runner.run(options.action, options.confirm, inventory, options.confirm_inventory)
        status = 0
    except (DeploymentError, OSError, ValueError, TypeError, KeyError) as error:
        result = {"schema_version": 1, "action": options.action, "read_back_verified": False,
                  "error": str(error) if isinstance(error, DeploymentError) else "Invalid configuration, receipt path or CLI response.",
                  "last_observed": runner.last_observed if runner else None, "commands": runner.commands if runner else []}
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