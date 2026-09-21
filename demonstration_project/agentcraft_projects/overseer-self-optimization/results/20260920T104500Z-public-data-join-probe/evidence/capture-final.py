"""Append closure after the retained architecture failure; no previous evidence overwritten."""

from datetime import datetime, timezone
import difflib
import importlib.util
import json
from pathlib import Path
import sys


EVIDENCE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("checkpoint_capture", EVIDENCE / "capture.py")
capture = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(capture)


def main():
    architecture = capture.command([sys.executable, "-B", ".github/tools/arch.py", "--root", str(capture.APP), "--json"])
    previous_path = EVIDENCE / "checkpoint-evidence.json"
    previous = json.loads(previous_path.read_text())
    prestate = json.loads((capture.PRESTATE / "record.json").read_text())
    changed = []
    differences = []
    for entry in prestate["changes"]:
        target = capture.ROOT / entry["path"]
        before = entry["before"]
        original = (capture.PRESTATE / before["snapshot"]).read_bytes() if before["state"] == "present" else b""
        if before["state"] == "present":
            assert capture.digest(original) == before["sha256"]
        if not target.exists():
            assert before["state"] == "absent"
            continue
        current = target.read_bytes()
        if current == original:
            continue
        changed.append({"path": entry["path"], "before": before,
                        "after": {"sha256": capture.digest(current), "bytes": len(current)}})
        differences.extend(difflib.unified_diff(original.decode().splitlines(keepends=True), current.decode().splitlines(keepends=True),
                                                fromfile="prestate/" + entry["path"], tofile="current/" + entry["path"]))
    capture.retain(EVIDENCE / "source-changes-final.patch", "".join(differences).encode())
    package = Path(previous["package"]["package_path"])
    manifest_payload = (package / "manifest.json").read_bytes()
    assert capture.digest(manifest_payload) == previous["package"]["package_sha256"]
    manifest = json.loads(manifest_payload)
    for name, expected in manifest["transforms"].items():
        assert capture.digest((capture.APP / name).read_bytes()) == expected
    for name, expected in manifest["artifacts"].items():
        assert capture.digest((package / name).read_bytes()) == expected["sha256"]
    previous_code = {entry["path"]: entry["after"]["sha256"] for entry in previous["changed_paths"]}
    intervening = [entry["path"] for entry in changed if previous_code[entry["path"]] != entry["after"]["sha256"]]
    assert intervening == ["template_apps/investigation_app/architecture.json"]
    output = {"status": "complete" if architecture["exit_code"] == 0 else "checks-require-review",
              "authority": "non-authoritative orchestrator evidence; overseer archival pending",
              "recorded_at": datetime.now(timezone.utc).isoformat(),
              "supersedes_primary_capture": {"path": previous_path.name, "sha256": capture.digest(previous_path.read_bytes())},
              "repair": {"path": intervening[0], "reason": "Declare application-tests -> public-data-operations; actual import already tested.",
                         "previous_failure": "Retained checkpoint-evidence.json architecture command exit 1; no output erased."},
              "commands": [architecture], "changed_paths": changed,
              "constitution": previous["constitution"], "archival_refs": previous["archival_refs"],
              "package": previous["package"], "repeat_receipts": previous["repeat_receipts"],
              "source_restore": "prestate and source-changes-final.patch retained; not executed",
              "settlement": previous["settlement"], "capture_gaps": previous["capture_gaps"],
              "effective_effort": "unverified", "next_checkpoint": "checkpoint.md#smallest-next-decision",
              "evidence": [{"path": str(path.relative_to(capture.PROJECT)), "sha256": capture.digest(path.read_bytes()),
                            "bytes": path.stat().st_size} for path in sorted(EVIDENCE.iterdir())
                           if path.is_file() and path.name != "checkpoint-final.json"]}
    payload = (json.dumps(output, indent=2, sort_keys=True) + "\n").encode()
    capture.retain(EVIDENCE / "checkpoint-final.json", payload)
    print(json.dumps({"status": output["status"], "sha256": capture.digest(payload),
                      "changed_paths": len(changed), "architecture": architecture,
                      "package_sha256": previous["package"]["package_sha256"]}, indent=2))
    return int(output["status"] != "complete")


if __name__ == "__main__":
    raise SystemExit(main())