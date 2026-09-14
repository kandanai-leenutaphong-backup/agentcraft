"""Rebuild this pack's payload from the skill's own first-party sources."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import zipfile

from skillpack import FORMAT, MAX_BYTES, MAX_FILES, PACK, PAYLOAD, file_digest, safe_path, verify


SELECTION_FORMAT = "agent-optimization-sources-v2"
SKIP_PARTS = {".git", "__pycache__", "node_modules", ".pytest_cache", ".mypy_cache",
              ".ruff_cache", "dist", "build", ".venv", "venv", "artifacts"}
SKIP_SUFFIXES = {".pyc", ".pyo", ".tsbuildinfo"}
SECRET_NAMES = {".env", "task-access.json", "credentials", "credentials.json", "id_rsa", "id_ed25519"}
SECRET_SUFFIXES = {".pem", ".key", ".pfx", ".p12"}


def source_file(root, name):
    path = root / name
    if path.is_absolute() and not path.is_relative_to(root):
        raise ValueError("Source leaves its repository root")
    if ".." in Path(name).parts or any(part in SECRET_NAMES for part in Path(name).parts):
        raise ValueError("Unsafe or credential-shaped source path")
    if path.suffix in SECRET_SUFFIXES or any(parent.is_symlink() for parent in (path, *path.parents) if parent != root):
        raise ValueError("Source cannot contain secrets or symbolic links")
    if not path.is_file():
        raise ValueError(f"Required source is absent: {name}")
    return path


def add_file(entries, root, source, destination, role):
    safe_path(destination)
    if destination in entries:
        raise ValueError(f"Duplicate payload selection: {destination}")
    path = source_file(root, source)
    content = path.read_bytes()
    entries[destination] = {"content": content, "source": source, "role": role,
                            "executable": bool(path.stat().st_mode & 0o111)}


def collect(root, selection):
    entries = {}
    for tree in selection["trees"]:
        directory = root / tree["path"]
        if not directory.is_dir() or directory.is_symlink():
            raise ValueError(f"Required source tree is absent: {tree['path']}")
        for path in sorted(directory.rglob("*")):
            relative = path.relative_to(root)
            if any(part in SKIP_PARTS for part in relative.parts) or path.suffix in SKIP_SUFFIXES:
                continue
            if path.is_symlink():
                raise ValueError(f"Source tree contains a link: {relative}")
            if path.is_file():
                inner = path.relative_to(directory).as_posix()
                add_file(entries, root, relative.as_posix(), f"{tree['destination']}/{inner}", tree["role"])
    for item in selection["mapped_files"]:
        add_file(entries, root, item["source"], item["destination"], item["role"])
    return entries


def build(source_root=PACK, *, replace=False, pack=PACK):
    root = Path(source_root).resolve(strict=True)
    pack = Path(pack).resolve()
    selection_path = pack / "assets/sources.json"
    selection = json.loads(selection_path.read_text())
    if selection.get("format") != SELECTION_FORMAT:
        raise ValueError("Unsupported source-selection manifest")
    target = pack / PAYLOAD
    manifest_path = pack / "manifest.json"
    if not replace and (target.exists() or manifest_path.exists()):
        raise ValueError("Snapshot already exists; use --replace only for an intentional new consolidation")
    entries = collect(root, selection)
    size = sum(len(entry["content"]) for entry in entries.values())
    if len(entries) > MAX_FILES or size > MAX_BYTES:
        raise ValueError("Selected source exceeds payload bounds")
    with tempfile.TemporaryDirectory(prefix="optimization-snapshot-") as folder:
        staged = Path(folder)
        (staged / "assets").mkdir()
        manifest = {"format": FORMAT, "version": selection["version"],
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "consolidation": "first-party snapshot of this skill's own sources; no host application or third-party clone",
                    "source": {"basis": selection["basis"],
                               "selection_sha256": file_digest(selection_path)},
                    "payload": {"path": PAYLOAD}, "files": [],
                    "roots": sorted({tree["destination"].split("/")[0] for tree in selection["trees"]}
                                    | {item["destination"].split("/")[0] for item in selection["mapped_files"]}),
                    "example": {"synthetic": True,
                                "scope": "hand-authored record shapes; no measurement, dataset or campaign result"},
                    "external_requirements": ["Linux Python 3.11+ for native terminal and sandbox execution",
                                              "Bubblewrap and libseccomp; never bypass isolation",
                                              "Node 20+, React and TypeScript for the frontend check",
                                              "Host-authorized dataset, model/knowledge adapters and a native Copilot CLI"],
                    "limitations": selection["excluded"] + [
                        "The archive duplicates this skill's portable sources for offline inspection; it is not a second installed runtime.",
                        "Hashes establish internal consistency, not publisher authenticity or a redistribution grant.",
                        "Example ledger records are invented illustrations and are never evidence of performance."]}
        with zipfile.ZipFile(staged / PAYLOAD, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for name, entry in sorted(entries.items()):
                member = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
                member.compress_type = zipfile.ZIP_DEFLATED
                member.external_attr = (stat.S_IFREG | (0o755 if entry["executable"] else 0o644)) << 16
                archive.writestr(member, entry["content"])
                manifest["files"].append({"path": name, "source_path": entry["source"], "role": entry["role"],
                                          "bytes": len(entry["content"]),
                                          "sha256": hashlib.sha256(entry["content"]).hexdigest()})
        manifest["payload"].update(sha256=file_digest(staged / PAYLOAD), bytes=(staged / PAYLOAD).stat().st_size,
                                   expanded_bytes=size)
        (staged / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        verify(staged)
        for entry in manifest["files"]:
            if file_digest(root / entry["source_path"]) != entry["sha256"]:
                raise ValueError("Source changed during consolidation; retry at a stable boundary")
        for source, destination in ((staged / PAYLOAD, target), (staged / "manifest.json", manifest_path)):
            descriptor, temporary = tempfile.mkstemp(dir=destination.parent, prefix=destination.name + ".")
            os.close(descriptor)
            try:
                Path(temporary).write_bytes(source.read_bytes())
                os.replace(temporary, destination)
            finally:
                Path(temporary).unlink(missing_ok=True)
    return {"status": "packaged", "files": len(entries), "expanded_bytes": size,
            "payload_bytes": manifest["payload"]["bytes"], "sha256": manifest["payload"]["sha256"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=PACK,
                        help="first-party source root; defaults to this skill directory")
    parser.add_argument("--replace", action="store_true")
    arguments = parser.parse_args(argv)
    try:
        print(json.dumps(build(arguments.source_root, replace=arguments.replace), indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"refused: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())