"""Append-only acceptance-gap evidence using existing deployment owners."""

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
PRIOR = ROOT / "deploy/remediation-evidence/20260922T174900Z-f08"
SPEC = importlib.util.spec_from_file_location("prior_gap_evidence", PRIOR / "evidence.py")
OWNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(OWNER)
OWNER.OUT = OWNER.PREVIOUS.OUT = OUT
RUN = "r-20260922T193935Z"
CLOCK = Path("/tmp/agentcraft-acceptance-gap-closure-clock.jsonl")
DEADLINE = datetime.fromisoformat("2026-09-22T21:06:18+00:00")
save = OWNER.PREVIOUS.save


def ref(path):
    with path.open("rb") as stream:
        checksum = hashlib.file_digest(stream, "sha256").hexdigest()
    return {"path": str(path.relative_to(ROOT)), "sha256": checksum, "bytes": path.stat().st_size}


def clock():
    result = subprocess.run(["python3", ".github/tools/oplog.py", "check", "--run", RUN,
                             "--log", str(CLOCK)], cwd=ROOT, capture_output=True, text=True, check=True)
    value = json.loads(result.stdout)
    value["mission_remaining_seconds"] = (DEADLINE - datetime.now(timezone.utc)).total_seconds()
    return value


OWNER.clock = clock


def prepare():
    request = json.loads((OUT / "request.json").read_text())
    assert ref(ROOT / request["review"])["sha256"] == request["review_sha256"]
    constitution = ROOT / "agentcraft_projects/foundry-official-integration-20260922/constitution/constitution.yaml"
    assert ref(constitution)["sha256"] == request["constitution_sha256"]
    manifest = ROOT / "testbeds/foundry-agent-evaluation/deploy/env/migration-e-final-h-v3.json"
    frozen = json.loads(manifest.read_text())
    expected = frozen["accepted_host"]
    deployed = json.loads((ROOT / expected["deployment"]).read_text())["result"]
    assert deployed["agent"] == frozen["agent"] and deployed["version"] == expected["version"]
    assert deployed["source"]["sha256"] == expected["source_sha256"]
    assert deployed["source"]["files"]["app/configuration.yaml"] == expected["config_sha256"]
    assert deployed["image"].endswith("@" + expected["image_digest"])
    for name in expected["verification"]:
        checked = json.loads((ROOT / name).read_text())["result"]
        assert checked["readback"] and checked["anonymous_status"] in (401, 403)
        for key in ("source_sha256", "config_sha256"):
            assert checked["tool_evidence"][key] == expected[key]
        assert checked["tool_evidence"]["agent_version"] == expected["version"]
    protected = set()
    for directory in (ROOT / "deploy/remediation-evidence",):
        for child in directory.iterdir():
            if child.is_dir() and child != OUT:
                protected.update(path for path in child.rglob("*") if path.is_file() and "__pycache__" not in path.parts)
    for name in ("foundry-hosted-agents/deploy/records", "foundry-agent-evaluation/deploy/records",
                 "foundry-agent optimization/deploy/evidence"):
        protected.update(path for path in (ROOT / "testbeds" / name).rglob("*.json")
                         if not set(path.parts).intersection({"migration-h-overlap-v1", "migration-e-final-h-v3"}))
    project = ROOT / "agentcraft_projects/foundry-official-integration-20260922"
    for name in ("constitution", "notebook", "records", "dataset"):
        protected.update(path for path in (project / name).rglob("*") if path.is_file())
    return save("prewrite-pins.json", {"request": ref(OUT / "request.json"), "clock": clock(),
        "constitution": ref(constitution), "E_manifest": ref(manifest),
        "H_manifest": ref(ROOT / "testbeds/foundry-hosted-agents/deploy/env/migration-h-overlap-v1.json"),
        "accepted_H": [ref(ROOT / name) for name in [expected["deployment"], *expected["verification"]]],
        "protected_files": [ref(path) for path in sorted(protected)],
        "archival_baseline": ref(PRIOR / "final-source.tar.gz"),
        "capture_gaps": ["Initial reads, first local test and manifest checks preceded this command wrapper; host tool transcript retains them.",
                         "Original mission monotonic run unavailable; inherited absolute UTC deadline retained.",
                         "Effective effort, tokens and provider costs unknown."]})


def history():
    before = json.loads((OUT / "prewrite-pins.json").read_text())
    for item in before["protected_files"]:
        assert ref(ROOT / item["path"]) == item, item["path"]
    original = json.loads((ROOT / "deploy/remediation-evidence/20260922T151500Z-f00/capture.json").read_text())
    for item in original["historical_hash_only"]:
        assert ref(ROOT / item["path"])["sha256"] == item["sha256"], item["path"]
    return save("historical-integrity.json", {"protected_files_unchanged": len(before["protected_files"]),
        "F00_historical_files_unchanged": len(original["historical_hash_only"]), "observed": clock()})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare", "run", "clock", "history"))
    parser.add_argument("stage", nargs="?", default="check")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.action == "run":
        raise SystemExit(OWNER.run(args.stage, args.command))
    print(json.dumps({"prepare": prepare, "clock": clock, "history": history}[args.action]()))