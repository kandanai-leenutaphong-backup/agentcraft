"""One-time, fixed-manifest migration of the authorized ADX skill into azdata."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

LIBRARY = Path(__file__).resolve().parents[1]
ROOT = LIBRARY.parents[1]
SOURCE = ROOT / ".github/skills/adx-event-store"
RECORD = LIBRARY / "docs/event-store/preservation.json"
FILES = {
    "mechanism/adx_connector/__init__.py": "src/azdata/event_store/__init__.py",
    "mechanism/adx_connector/client.py": "src/azdata/event_store/client.py",
    "mechanism/adx_connector/config.py": "src/azdata/event_store/config.py",
    "mechanism/adx_connector/connector.py": "src/azdata/event_store/connector.py",
    "mechanism/adx_connector/crud.py": "src/azdata/event_store/crud.py",
    "mechanism/adx_connector/errors.py": "src/azdata/event_store/errors.py",
    "mechanism/adx_connector/identifiers.py": "src/azdata/event_store/identifiers.py",
    "mechanism/adx_connector/ingest.py": "src/azdata/event_store/ingest.py",
    "mechanism/adx_connector/models.py": "src/azdata/event_store/models.py",
    "mechanism/adx_connector/provision.py": "src/azdata/event_store/provision.py",
    "mechanism/adx_connector/retry.py": "src/azdata/event_store/retry.py",
    "mechanism/adx_connector/schema.py": "src/azdata/event_store/schema.py",
    "mechanism/bootstrap_adx.py": "src/azdata/event_store/bootstrap.py",
    "tests/selftest.py": "tests/event_store/selftest.py",
    "tests/test_bootstrap.py": "tests/event_store/test_bootstrap.py",
    "CONTRACT.md": "docs/event-store/CONTRACT.md",
    "GOTCHAS.md": "docs/event-store/GOTCHAS.md",
    "LICENSE": "docs/event-store/LICENSE",
    "PROVENANCE.md": "docs/event-store/PROVENANCE.md",
    "README.md": "docs/event-store/README.md",
    "SKILL.md": "docs/event-store/WORKFLOW.md",
    "references/gotchas.md": "docs/event-store/references/gotchas.md",
    "pyproject.toml": "docs/event-store/legacy-package.toml",
    "requirements.txt": "docs/event-store/legacy-requirements.txt",
    "uv.lock": None,
    ".gitignore": None,
}


def inventory() -> dict[str, Path]:
    files = {}
    for path in SOURCE.rglob("*"):
        if path.is_symlink():
            raise ValueError("Skill migration refuses symlinks.")
        if path.is_file():
            files[path.relative_to(SOURCE).as_posix()] = path
    if set(files) != set(FILES):
        raise ValueError(f"Source differs from frozen manifest: {sorted(set(files) ^ set(FILES))}")
    return files


def transformed(name: str, content: bytes) -> bytes:
    if not name.endswith(".py"):
        return content
    text = content.decode("utf-8")
    text = text.replace("from adx_connector", "from azdata.event_store")
    text = text.replace('logging.getLogger("adx_connector', 'logging.getLogger("azdata.event_store')
    if name == "mechanism/bootstrap_adx.py":
        text = text.replace(
            "# The connector ships beside this script inside the skill.\nsys.path.insert(0, str(Path(__file__).resolve().parent))\n\n", ""
        )
    if name == "tests/test_bootstrap.py":
        text = text.replace('sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "mechanism"))\n', "")
        text = text.replace("import bootstrap_adx as bootstrap", "from azdata.event_store import bootstrap")
    if name == "tests/selftest.py":
        text = text.replace(
            'SKILL_ROOT = Path(__file__).resolve().parent.parent\nMECHANISM = SKILL_ROOT / "mechanism"\n\nsys.path.insert(0, str(MECHANISM))\n\n', ""
        )
        text = text.replace(
            'check("connector imports from its bundled mechanism", Path(sys.modules["adx_connector"].__file__).resolve().is_relative_to(MECHANISM.resolve()))',
            'check("connector imports from canonical azdata package", sys.modules["azdata.event_store"].__package__ == "azdata.event_store")',
        )
    return text.encode("utf-8")


def stage() -> None:
    source_files = inventory()
    if RECORD.exists() or any((LIBRARY / target).exists() for target in FILES.values() if target):
        raise ValueError("Migration refuses existing destinations or preservation evidence.")
    records = []
    for name, path in source_files.items():
        content = path.read_bytes()
        target = FILES[name]
        entry = {"source": name, "destination": target, "source_sha256": hashlib.sha256(content).hexdigest()}
        if target:
            destination = LIBRARY / target
            destination.parent.mkdir(parents=True, exist_ok=True)
            migrated = transformed(name, content)
            with destination.open("xb") as handle:
                handle.write(migrated)
            if destination.read_bytes() != migrated:
                raise ValueError("Destination read-back differs from the frozen transformation.")
            entry["staged_sha256"] = hashlib.sha256(migrated).hexdigest()
        else:
            entry["superseded_by"] = "Member pyproject.toml and parent-owned libraries/uv.lock and ignore rules; original bytes recoverable from source Git baseline."
        records.append(entry)
    RECORD.parent.mkdir(parents=True, exist_ok=True)
    with RECORD.open("x", encoding="utf-8") as handle:
        json.dump({"schema_version": 1, "source_root": ".github/skills/adx-event-store",
                   "source_git_baseline": "00c76c6bb55190877c3d4d4b5b3a14e55bce2cb4",
                   "status": "staged-not-retired", "files": records}, handle, indent=2)
        handle.write("\n")
    print(f"Preserved {sum(bool(target) for target in FILES.values())} files; recorded all {len(FILES)} source hashes.")


def retire() -> None:
    source_files = inventory()
    record = json.loads(RECORD.read_text(encoding="utf-8"))
    if {entry["source"] for entry in record["files"]} != set(FILES) or record["status"] != "staged-not-retired":
        raise ValueError("Preservation evidence does not match this frozen migration.")
    for entry in record["files"]:
        name = entry["source"]
        if entry["destination"] != FILES[name]:
            raise ValueError("Preservation destination changed.")
        if hashlib.sha256(source_files[name].read_bytes()).hexdigest() != entry["source_sha256"]:
            raise ValueError("Original source changed after preservation; refusing retirement.")
        if FILES[name]:
            destination = LIBRARY / FILES[name]
            if not destination.is_file() or destination.is_symlink():
                raise ValueError("Preserved destination missing or unsafe.")
            entry["retired_destination_sha256"] = hashlib.sha256(destination.read_bytes()).hexdigest()
    for path in source_files.values():
        path.unlink()
    for path in sorted((path for path in SOURCE.rglob("*") if path.is_dir()), key=lambda path: len(path.parts), reverse=True):
        path.rmdir()
    SOURCE.rmdir()
    record["status"] = "retired-after-offline-and-artifact-verification"
    RECORD.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(f"Retired only {len(FILES)} frozen source files; preserved destinations read back.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("stage", "retire"))
    options = parser.parse_args()
    stage() if options.action == "stage" else retire()