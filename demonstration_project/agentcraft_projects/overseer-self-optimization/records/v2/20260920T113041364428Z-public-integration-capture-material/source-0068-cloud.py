"""Isolated Investigation release feasibility. No cloud mutation implementation."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re
import tarfile


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = ROOT.parents[1]
TARGET_FILE = "deploy/env/investigation-isolated.json"
SOURCE_FILES = (
    "app/cybereye/backend/main.py",
    "app/cybereye/backend/agents/profiles.py",
    "app/cybereye/backend/security/config.py",
    "app/cybereye/backend/security/composition.py",
    "pyproject.toml",
    "uv.lock",
    "app/cybereye/frontend/package-lock.json",
)
LIBRARIES = (
    "framework-core", "situation-detector", "entra-auth", "signed-dev-access",
    "resource-explorer", "llm-interface", "modular-agents", "azure-data-connectors",
    "event-stream", "source-code",
)
SOURCE_SUFFIXES = frozenset({".py", ".typed", ".toml", ".json", ".lock", ".ts", ".tsx",
                             ".js", ".mjs", ".cjs", ".css", ".html", ".yaml", ".yml", ".md"})
EXCLUDED_PARTS = frozenset({"node_modules", "__pycache__", "dist", "build", "tests", "test",
                            "artifacts", "reports", "research", "output"})


def unique_fields(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate target field")
        result[key] = value
    return result


def load_target(path: Path) -> dict:
    target = json.loads(path.read_text(), object_pairs_hook=unique_fields)
    fixed = {"cloud": "AzureCloud", "subscription_id": "67255afe-8670-4401-a1b8-df6ca63a3516",
             "tenant_id": "c79ab2bb-79cb-47f1-b4da-b6852fe45ff7", "region": "australiaeast"}
    names = {"resource_group", "container_app", "environment", "registry", "identity", "auth_registration"}
    if not isinstance(target, dict) or set(target) != set(fixed) | names:
        raise ValueError("unknown or missing target fields")
    if any(target[key] != value for key, value in fixed.items()):
        raise ValueError("target differs from scoped authority")
    if any(not isinstance(target[key], str) or not re.fullmatch(r"[a-z][a-z0-9-]{2,62}", target[key])
           or "investigation" not in target[key] for key in names):
        raise ValueError("invalid isolated resource name")
    return target


def package_inputs(repository: Path) -> list[Path]:
    app = repository / "template_apps/investigation_app"
    directories = [app / "app/cybereye/backend", app / "app/cybereye/control",
                   app / "app/cybereye/frontend/src", app / "app/data/ontology",
                   repository / "template_apps/shared/src"]
    metadata_roots = [app, app / "app/cybereye/frontend", repository / "template_apps/shared"]
    for library in LIBRARIES:
        owner = repository / "libraries" / library
        metadata_roots.append(owner)
        directories.extend(owner / name for name in ("src", "frontend", "modules", "scripts"))
    candidates = [app / "app/__init__.py", app / "app/cybereye/__init__.py"]
    for owner in metadata_roots:
        if owner.is_dir():
            candidates.extend(path for path in owner.iterdir() if not path.is_dir())
    for directory in directories:
        if directory.is_symlink():
            raise ValueError("source directory symlink refused")
        if directory.is_dir():
            candidates.extend(directory.rglob("*"))
    selected = set()
    for path in candidates:
        relative = path.relative_to(repository)
        parts = relative.parts
        if any(part.startswith(".") or part in EXCLUDED_PARTS for part in parts):
            continue
        if path.is_symlink() or any(parent.is_symlink() for parent in path.parents if parent != repository.parent):
            raise ValueError("source symlink refused")
        if not path.is_file():
            continue
        allowed = path.suffix in SOURCE_SUFFIXES or path.name in {"LICENSE", "MANIFEST.in", "THIRD_PARTY_NOTICES"}
        if not allowed:
            continue
        sensitive_name = any(word in path.name.lower() for word in ("secret", "credential"))
        if path.suffix in {".json", ".yaml", ".yml", ".toml"} and sensitive_name:
            raise ValueError("credential-shaped source filename requires explicit review")
        selected.add(path)
    required = [app / item for item in SOURCE_FILES]
    required.extend(owner / "pyproject.toml" for owner in metadata_roots
                    if owner.name in LIBRARIES[:8] or owner.name == "shared")
    if any(path not in selected for path in required):
        raise ValueError("required source or locked dependency metadata absent")
    return sorted(selected)


def package(output: Path, *, repository: Path = REPOSITORY) -> dict:
    destination = repository / "template_apps/investigation_app/deploy/packages"
    if output.parent.resolve() != destination.resolve() or output.suffix != ".tar":
        raise ValueError("output must be a new .tar directly inside deploy/packages")
    if destination.is_symlink():
        raise ValueError("package destination symlink refused")
    inputs = package_inputs(repository)
    manifest = {"kind": "source-review-candidate", "image_built": False, "deployable": False,
                "files": [], "excludes": ["credentials", "local state", "installed dependencies",
                                           "generated output", "tests", "research"]}
    destination.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as stream, tarfile.open(fileobj=stream, mode="w") as archive:
        for source in inputs:
            relative = source.relative_to(repository).as_posix()
            payload = source.read_bytes()
            header = tarfile.TarInfo(relative)
            header.size = len(payload)
            header.mode = 0o644
            archive.addfile(header, io.BytesIO(payload))
            manifest["files"].append({"path": relative, "sha256": hashlib.sha256(payload).hexdigest()})
        payload = json.dumps(manifest, sort_keys=True, indent=2).encode()
        header = tarfile.TarInfo("source-manifest.json")
        header.size = len(payload)
        header.mode = 0o644
        archive.addfile(header, io.BytesIO(payload))
    return {"path": str(output), "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
            "files": len(inputs), "kind": manifest["kind"], "image_built": False, "deployable": False}


def plan(root: Path = ROOT) -> dict:
    observations = []
    for relative in SOURCE_FILES:
        path = root / relative
        observations.append({"path": relative, "exists": path.is_file(),
                             "sha256": hashlib.sha256(path.read_bytes()).hexdigest()
                             if path.is_file() else None})
    blockers = [
        {"id": "durable_application_state", "required":
         "A supported durable filesystem with SQLite transaction/locking and atomic file semantics, "
         "proven across restart and revision replacement, or an application-owned storage contract.",
         "observed": "Current source uses local SQLite profiles and filesystem agent versions. "
         "No verified durable Container Apps volume is configured. Azure Files shared-key and "
         "private-network policy limitations are reported, not reverified by this offline command."},
        {"id": "durable_auth_state", "required":
         "Managed-identity reachable Azure Tables for browser flows/sessions and signed replay claims.",
         "observed": "Production configuration requires azure-table replay; maxReplicas=1 does not "
         "replace a durable replay ledger. Private networking and table access remain unverified."},
        {"id": "live_auth_acceptance", "required":
         "Tenant-pinned Entra sign-in and signed agent access through the production gate; "
         "positive journeys plus anonymous, wrong-tenant, expired, forged, replay and foreign-owner refusals.",
         "observed": "No isolated registration, public verification key, callback or deployed acceptance exists."},
        {"id": "bounded_model_verification", "required":
         "At most 10 actual model requests across deployed verification, including retries and tool loops.",
         "observed": "Local cumulative quotas were removed. No deployed request-count enforcement "
         "has been proven; inference remains disabled and this runner makes zero model calls."},
    ]
    if not all(item["exists"] for item in observations):
        blockers.append({"id": "missing_source", "required": "All release inputs exist.",
                         "observed": "One or more named source inputs are absent."})
    return {
        "schema_version": 1,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "status": "blocked",
        "target": load_target(root / TARGET_FILE),
        "evidence_basis": "Source inspection on 2026-09-19; current digests identify inputs, not semantic revalidation.",
        "authority": {
            "source": "Current user assignment: Fully autonomy. All decisions authorized and cloud modification authorized.",
            "scope": "Only isolated Investigation resources; no existing shared app or identity mutation.",
            "eligible_mutations": [],
            "deferred_mutations": [
                "Create named isolated resource group with owner/lifetime tags",
                "Create named Basic ACR with admin disabled",
                "Create named user-assigned identity and registry-scoped AcrPull assignment",
                "Create named Container Apps environment and private-first app",
                "Create named single-tenant auth registration with exact callback",
            ],
            "excluded": ["shared resource mutation", "secret/key retrieval", "policy exemption",
                         "ADX start outside root deployment owner", "app/library contract changes"],
        },
        "limits": {"cpu": 0.5, "memory": "1Gi", "min_replicas": 0, "max_replicas": 1,
                   "revision_mode": "Single", "verification_model_calls": 10,
                   "model_calls_enabled": False, "maximum_lifetime_hours": 24},
        "cost": {"estimate": "unknown; pricing and quota validation required before provisioning",
                 "billable_resources_created": 0, "adx_started": False},
        "cleanup": {"resources_created": [], "action": "None: no cloud writes. Future teardown must "
                    "freeze inventory, verify ownership and locks, then verify absence; tenant objects separate."},
        "source_inputs": observations,
        "packaging": {"kind": "source-review-candidate", "image_built": False,
                  "deployable": False, "local_image_checks": "not run"},
        "historical_preflight": {"path": "reports/investigation-preflight.json",
                                 "exists": (root.parents[1] / "reports/investigation-preflight.json").is_file()},
        "blockers": blockers,
        "cloud_contacted": False,
        "cloud_mutations": [],
        "model_calls": 0,
        "next_decision": "Application owner must supply a supported durable state contract or prove "
                         "a policy-compatible filesystem preserving current semantics. Do not provision idle resources.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("plan", "preflight", "package", "apply", "verify", "teardown"))
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args(argv)
    if (arguments.action == "package") != (arguments.output is not None):
        parser.error("only package requires --output")
    try:
        result = plan()
    except (OSError, ValueError):
        parser.exit(2, "Cloud target/source preflight refused; inspect committed target and source inputs.\n")
    result["action"] = arguments.action
    result["operation"] = "planned" if arguments.action == "plan" else "refused"
    if arguments.action == "package":
        try:
            result["artifact"] = package(arguments.output)
        except (OSError, ValueError):
            parser.exit(2, "Source package refused; inspect paths, required inputs and output collision.\n")
        result["operation"] = "packaged-source-only"
    print(json.dumps(result, indent=2))
    return 0 if arguments.action in {"plan", "package"} else 2


if __name__ == "__main__":
    raise SystemExit(main())