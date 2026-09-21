from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import stat
import tarfile


def provision_signer():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from signed_dev_access import load_private_key, public_key_fingerprint

    directory = Path.home() / ".local/state/agentcraft/rg-agentcraft-dev"
    if any(parent.is_symlink() for parent in (directory, *directory.parents)):
        raise ValueError("operator_state_symlink_refused")
    directory.mkdir(parents=True, mode=0o700, exist_ok=True)
    metadata = directory.stat()
    if metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) != 0o700:
        raise ValueError("operator_state_requires_owner_mode_0700")
    path = directory / "caller.ed25519"
    created = False
    if not path.exists():
        key = Ed25519PrivateKey.generate()
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, "wb") as output:
            output.write(key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
                                           serialization.NoEncryption()))
            output.flush()
            os.fsync(output.fileno())
        created = True
    key = load_private_key(str(path))
    public = base64.b64encode(key.public_key().public_bytes(serialization.Encoding.Raw,
                             serialization.PublicFormat.Raw)).decode()
    return {"public_key": public, "fingerprint": public_key_fingerprint(public),
            "private_path": str(path), "created": created, "private_value_captured": False}


def build_context(root: Path, destination: Path):
    from investigation_loader import PACKAGE_SHA256, load_package

    app = root / "template_apps/investigation_app"
    package = app / "deploy/data/public-investigation/packages" / PACKAGE_SHA256
    load_package(package)
    roots = [root / "libraries" / name for name in ("framework-core", "situation-detector", "entra-auth",
        "signed-dev-access", "resource-explorer", "llm-interface", "modular-agents", "azure-data-connectors",
        "event-stream", "source-code")]
    roots += [root / "template_apps/shared", app / "app/cybereye/backend", app / "app/cybereye/control",
              app / "app/cybereye/frontend/src", app / "app/data/ontology"]
    excluded = {"tests", "test", "docs", "build", "dist", "node_modules", "__pycache__", "examples",
                "reports", "records", "deploy", "skills", "history"}
    suffixes = {".py", ".typed", ".ts", ".tsx", ".js", ".mjs", ".cjs", ".json", ".toml", ".yaml", ".yml",
                ".css", ".md", ".txt", ".html", ".svg", ".png", ".woff", ".woff2"}
    entries = {}

    def add(path, name=None):
        if not path.is_file() or path.is_symlink() or path.resolve() != path:
            raise ValueError("build_source_missing_or_symlinked")
        relative = name or path.relative_to(root).as_posix()
        payload = path.read_bytes()
        if b"-----BEGIN PRIVATE KEY-----" in payload or b"-----BEGIN OPENSSH PRIVATE KEY-----" in payload:
            raise ValueError("build_private_material_refused")
        entries[relative] = {"source": path, "sha256": hashlib.sha256(payload).hexdigest(), "bytes": len(payload)}

    for directory in roots:
        for path in sorted(directory.rglob("*")):
            relative = path.relative_to(directory)
            if any(part.startswith(".") or part in excluded for part in relative.parts):
                continue
            if path.is_file() and (path.suffix in suffixes or path.name in {"LICENSE", "NOTICE"}):
                add(path)
    for relative in ("pyproject.toml", "uv.lock", "app/__init__.py", "app/cybereye/__init__.py",
                     "app/data/__init__.py", "app/cybereye/frontend/package.json",
                     "app/cybereye/frontend/package-lock.json", "app/cybereye/frontend/index.html",
                     "app/cybereye/frontend/tsconfig.json", "app/cybereye/frontend/tsconfig.app.json",
                     "app/cybereye/frontend/tsconfig.node.json", "app/cybereye/frontend/vite.config.ts"):
        candidate = app / relative
        if candidate.exists():
            add(candidate)
    for name in ("Dockerfile.investigation", "investigation_loader.py", "investigation_verify.py", "investigation.py", "resource_group.py", "env/agentcraft-dev.json"):
        add(root / "deploy" / name)
    frontend = app / "app/cybereye/frontend/dist"
    if not (frontend / "index.html").is_file():
        raise ValueError("production_frontend_build_required")
    for path in sorted(frontend.rglob("*")):
        if path.is_file():
            if path.suffix not in {".html", ".js", ".css", ".svg", ".png", ".woff", ".woff2", ".txt", ".json"}:
                raise ValueError("unexpected_frontend_artifact")
            add(path)
    for path in sorted(package.rglob("*")):
        if path.is_file():
            add(path, "package/" + path.relative_to(package).as_posix())
    with tarfile.open(destination, "x:gz") as archive:
        for name, item in sorted(entries.items()):
            archive.add(item["source"], arcname=name, recursive=False)
    with tarfile.open(destination, "r:gz") as archive:
        if set(archive.getnames()) != set(entries):
            raise ValueError("build_archive_manifest_mismatch")
        for item in archive:
            if not item.isfile() or hashlib.sha256(archive.extractfile(item).read()).hexdigest() != entries[item.name]["sha256"]:
                raise ValueError("build_archive_readback_mismatch")
    return {"archive": str(destination), "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
            "entries": {name: {key: value for key, value in item.items() if key != "source"} for name, item in entries.items()},
            "package_sha256": PACKAGE_SHA256, "secrets_or_private_history": "excluded_by_explicit_source_selection"}


def seal_sources(root, project, evidence, receipt):
    selected = {item["original_path"]: item for item in receipt["prestate_files"]}
    capture = json.loads((project / "records/capture/20260920T115843866Z-public-runtime/capture-manifest.json").read_text())
    accepted_ref = next(item for item in receipt["records"] if item["id"] == "public-app-local-acceptance-outcome")
    accepted_path = project / accepted_ref["path"]
    if hashlib.sha256(accepted_path.read_bytes()).hexdigest() != accepted_ref["sha256"]:
        raise ValueError("accepted_snapshot_record_changed")
    accepted = json.loads(accepted_path.read_text())
    for item in capture["sources"]:
        artifact = next((entry for entry in accepted["artifacts"] if entry["source_path"] == item["staged_path"]), None)
        if artifact is not None:
            retained = accepted_path.parent / artifact["path"]
            if hashlib.sha256(retained.read_bytes()).hexdigest() != artifact["sha256"]:
                raise ValueError("accepted_snapshot_bytes_changed")
            selected.setdefault(item["original_path"], {"original_path": item["original_path"],
                "path": str(retained.relative_to(project)), "sha256": artifact["sha256"], "bytes": artifact["bytes"]})
    for capture in sorted(evidence.glob("*-capture.json")):
        for source in json.loads(capture.read_text()).get("sources", []):
            if not source["exists"]:
                selected.setdefault(source["path"], {"original_path": source["path"], "absent_before": True})
    snapshot = evidence / "sources"
    snapshot.mkdir(exist_ok=False)
    changes = []
    for relative, before in selected.items():
        source = root / relative
        if not source.exists():
            continue
        payload = source.read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        if digest == before.get("sha256"):
            continue
        target = snapshot / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as output:
            output.write(payload)
        if target.read_bytes() != payload:
            raise ValueError("source_snapshot_readback_mismatch")
        changes.append({"path": relative, "before": before,
                        "after": {"path": str(target.relative_to(project)), "sha256": digest, "bytes": len(payload)}})
    indexed = [{"path": str(path.relative_to(project)), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "bytes": path.stat().st_size} for path in sorted(evidence.rglob("*")) if path.is_file()]
    return {"kind": "primary-evidence-not-authoritative-record", "changes": changes, "files": indexed,
            "private_material": "not selected", "reversion": "snapshots retained; restoration not performed"}