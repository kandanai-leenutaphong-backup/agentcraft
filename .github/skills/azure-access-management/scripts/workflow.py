#!/usr/bin/env python3
"""Offline capability routing and native-first plans; never executes a plan."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any
from uuid import UUID


ROOT = Path(__file__).resolve().parents[1]
MAX_BYTES = 1_000_000
DECISIONS = {"native-first", "retain-helper", "retain-compatibility", "retain-evidence"}
EQUIVALENCE = {"partial", "host-specific", "native-mechanism", "not-applicable"}
FIELDS = {"tenant_id", "subscription_id", "resource_group", "app_name", "identity_name",
          "client_id", "principal_id", "scope", "enforcement", "caller"}
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.()-]{0,89}\Z")


def read_json(path: Path) -> dict[str, Any]:
    with path.open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("Input exceeds the byte limit")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("Input must be a JSON object")
    return value


def catalogue() -> dict[str, Any]:
    return read_json(ROOT / "capabilities.json")


def contained_file(relative: str) -> Path:
    path = (ROOT / relative).resolve()
    if not path.is_relative_to(ROOT) or not path.is_file():
        raise ValueError("Catalogue references an absent or escaping file")
    return path


def check_inventory(data: dict[str, Any]) -> dict[str, Any]:
    if data.get("schema_version") != 1 or data.get("owner") != "azure-access-management":
        raise ValueError("Invalid catalogue owner or version")
    identifiers: set[str] = set()
    for entry in data["capabilities"]:
        identifier = entry["id"]
        if identifier in identifiers or not re.fullmatch(r"[a-z0-9-]+", identifier):
            raise ValueError("Invalid or duplicate capability id")
        identifiers.add(identifier)
        if entry["decision"] not in DECISIONS or entry["equivalence"] not in EQUIVALENCE:
            raise ValueError("Invalid capability disposition")
        if not entry["outcome"] or not entry["features"] or not entry["limit"]:
            raise ValueError("Incomplete capability inventory")
        workflow = data["workflows"][entry["workflow"]]
        contained_file(workflow["reference"])
        contained_file(entry["implementation"])
        for source in entry["native"]:
            if not data["native_sources"][source].startswith("https://"):
                raise ValueError("Invalid native source")
        for check in workflow["checks"]:
            for relative in data["checks"][check]:
                contained_file(relative)
    if {entry["workflow"] for entry in data["capabilities"]} != set(data["source_families"]):
        raise ValueError("A source family is missing from the catalogue")
    return {"status": "PASS_OFFLINE", "capabilities": len(identifiers),
            "source_families": len(data["source_families"]), "live_verified": False}


def validated_config(config: dict[str, Any]) -> dict[str, str]:
    if set(config) - FIELDS:
        raise ValueError("Unknown configuration fields; credentials and approval fields are forbidden")
    if any(not isinstance(value, str) or not value or len(value) > 2048
           or any(ord(character) < 32 for character in value) for value in config.values()):
        raise ValueError("Configuration values must be bounded nonempty strings")
    values = dict(config)
    for name in ("tenant_id", "subscription_id", "client_id", "principal_id"):
        if name in values:
            values[name] = str(UUID(values[name]))
    for name in ("resource_group", "app_name", "identity_name"):
        if name in values and not NAME.fullmatch(values[name]):
            raise ValueError("Invalid resource coordinate")
    if "scope" in values:
        scope = values["scope"]
        subscription = values.get("subscription_id", "")
        if not subscription or not scope.lower().startswith(f"/subscriptions/{subscription}/"):
            raise ValueError("Scope must be bound to the configured subscription")
        segments = scope.split("/")[1:]
        if any(not re.fullmatch(r"[A-Za-z0-9_.()-]{1,260}", segment)
               or segment in (".", "..") for segment in segments):
            raise ValueError("Unsafe scope syntax")
    if values.get("enforcement", "platform") not in {"platform", "application"}:
        raise ValueError("Invalid enforcement choice")
    if values.get("caller", "human") not in {"human", "provider-token", "custom-signed"}:
        raise ValueError("Invalid caller choice")
    return values


def plan(task: str, config: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    if task not in data["workflows"]:
        raise ValueError("Unknown workflow")
    values = validated_config(config)
    required = {"tenant_id"}
    if task in {"container-apps", "managed-identity", "access"}:
        required.add("subscription_id")
    if task == "container-apps":
        required.update(("resource_group", "app_name"))
        if values.get("caller") == "custom-signed" and values.get("enforcement", "platform") == "platform":
            raise ValueError("Custom signatures require a separately reviewed application gate; no automatic fallback")
    if task == "managed-identity":
        required.update(("resource_group", "identity_name"))
    if task == "access":
        required.add("scope")
    if required - set(values):
        raise ValueError("Missing required non-secret target coordinates")
    commands: list[list[str]] = []
    subscription = values.get("subscription_id")
    if subscription:
        commands.append(["az", "account", "show", "--subscription", subscription,
                         "--query", "{id:id,tenantId:tenantId,cloud:environmentName}", "--output", "json"])
    if task == "container-apps":
        commands.append(["az", "containerapp", "auth", "show", "--subscription", subscription,
                         "--resource-group", values["resource_group"], "--name", values["app_name"],
                         "--output", "json"])
    if task == "managed-identity":
        commands.append(["az", "identity", "show", "--subscription", subscription,
                         "--resource-group", values["resource_group"], "--name", values["identity_name"],
                         "--output", "json"])
    if task == "access":
        commands.append(["az", "role", "assignment", "list", "--subscription", subscription,
                         "--scope", values["scope"], "--include-inherited", "--all", "--output", "json"])
    selected = [entry for entry in data["capabilities"] if entry["workflow"] == task]
    workflow = data["workflows"][task]
    return {
        "schema_version": 1, "status": "PLAN_ONLY", "task": task,
        "target": values, "preferred": workflow["preferred"], "reference": workflow["reference"],
        "capabilities": [entry["id"] for entry in selected],
        "readback_argv": commands, "executed": False, "authority_granted": False,
        "live_verified": False, "checks": workflow["checks"],
        "sequence": [
            "Review native coverage and host-specific compatibility before choosing an implementation.",
            "Verify operator tenant, subscription, target ownership and required permissions; unknown is not allowed.",
            "Keep approval outside request data and use the host deployment or governance entry point for mutations.",
            "Read back exact changed state and exercise the matching unauthorized path.",
            "Record pending/unknown outcomes and use the existing lifecycle owner for cleanup.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    commands.add_parser("catalogue")
    commands.add_parser("check")
    detail = commands.add_parser("describe")
    detail.add_argument("capability")
    planner = commands.add_parser("plan")
    planner.add_argument("task")
    planner.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    try:
        data = catalogue()
        if args.action == "catalogue":
            result = data
        elif args.action == "check":
            result = check_inventory(data)
        elif args.action == "describe":
            entries = [entry for entry in data["capabilities"] if entry["id"] == args.capability]
            if not entries:
                raise ValueError("Unknown capability")
            result = entries[0]
        else:
            result = plan(args.task, read_json(args.config), data)
        print(json.dumps(result, indent=2, sort_keys=True))
    except (OSError, ValueError, KeyError, TypeError):
        print("Invalid input or catalogue; no command was executed and no authority granted", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
