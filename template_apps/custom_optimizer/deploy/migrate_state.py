from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def hashes(root: Path) -> dict[str, str]:
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            result[str(path.relative_to(root))] = "symlink:" + os.readlink(path)
        elif path.is_file():
            with path.open("rb") as handle:
                result[str(path.relative_to(root))] = hashlib.file_digest(handle, "sha256").hexdigest()
    return result


def move_state(source: Path, destination: Path, *, source_stopped: bool) -> dict:
    if not source_stopped:
        raise ValueError("stop the source template first and acknowledge --source-stopped")
    source = source.resolve(strict=True)
    if source == destination.resolve():
        raise ValueError("source and destination must differ")
    entries = [name for name in ("optimization", "copilot-workspaces") if (source / name).exists()]
    for name in entries:
        if (source / name).is_symlink() or (destination / name).exists():
            raise ValueError("state destination already exists or source is a symlink")
    for path in (source / "optimization/experiments").glob("*/*/experiment.json"):
        record = json.loads(path.read_text())
        if record["status"] in {"running", "baseline_running"}:
            raise ValueError("an experiment still has active work")
    before = {name: hashes(source / name) for name in entries}
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    moved = []
    try:
        for name in entries:
            (source / name).rename(destination / name)
            moved.append(name)
    except OSError:
        for name in reversed(moved):
            if not (source / name).exists():
                (destination / name).rename(source / name)
        raise
    for name in entries:
        if hashes(destination / name) != before[name]:
            raise RuntimeError("moved state verification failed; preserve both locations for inspection")
    return {"source": str(source), "destination": str(destination), "moved": entries,
            "files_verified": {name: len(values) for name, values in before.items()},
            "hashes": before, "record_bytes_changed": False}


def main() -> int:
    parser = argparse.ArgumentParser(description="Move idle optimizer state from the investigation template")
    parser.add_argument("--from-template", type=Path, required=True)
    parser.add_argument("--source-stopped", action="store_true")
    arguments = parser.parse_args()
    output = ROOT / "artifacts/migration/state-move.json"
    if output.exists():
        parser.error("state-move receipt already exists; existing records will not be overwritten")
    report = move_state(arguments.from_template / "app/cybereye/.local", ROOT / "app/cybereye/.local",
                        source_stopped=arguments.source_stopped)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
    print(json.dumps({key: value for key, value in report.items() if key != "hashes"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())