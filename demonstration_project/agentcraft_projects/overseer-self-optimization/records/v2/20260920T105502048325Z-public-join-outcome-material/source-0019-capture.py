"""Read back this assigned local checkpoint; never publish authoritative records."""

from datetime import datetime, timezone
import difflib
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import subprocess
import sys
import time


EVIDENCE = Path(__file__).resolve().parent
PROJECT = EVIDENCE.parents[2]
ROOT = PROJECT.parents[2]
APP = ROOT / "template_apps/investigation_app"
PRESTATE = PROJECT / "records/v2/20260920T103636935194Z-public-investigation-acquisition-prestate"
DECISION = PROJECT / "records/v2/20260920T103636896949Z-public-investigation-reorientation-authorized/record.json"


def digest(payload):
    return hashlib.sha256(payload).hexdigest()


def retain(path, payload):
    if path.exists():
        if path.read_bytes() != payload:
            raise ValueError("immutable evidence differs")
        return
    with path.open("xb") as handle:
        handle.write(payload)
    assert path.read_bytes() == payload


def command(arguments):
    started = datetime.now(timezone.utc).isoformat()
    clock = time.monotonic()
    result = subprocess.run(arguments, cwd=ROOT, text=True, capture_output=True, timeout=60)
    return {"command": arguments, "cwd": str(ROOT), "started_at": started,
            "duration_seconds": time.monotonic() - clock, "exit_code": result.returncode,
            "stdout": result.stdout, "stderr": result.stderr}


def main():
    started = datetime.now(timezone.utc).isoformat()
    clock = time.monotonic()
    assert digest(DECISION.read_bytes()) == "82504e0d55f7b69f2eecbc0ff08386e7ee527d2a176ed62fcbc3984eb7f3a9c7"
    assert digest((PRESTATE / "record.json").read_bytes()) == "02a589498324482fd152172070bd8890aeecc7d5f0e16630e8b8e990626b1b36"
    prestate = json.loads((PRESTATE / "record.json").read_text())
    changed = []
    diff = []
    for entry in prestate["changes"]:
        path = ROOT / entry["path"]
        before = entry["before"]
        original = b""
        if before["state"] == "present":
            original = (PRESTATE / before["snapshot"]).read_bytes()
            assert digest(original) == before["sha256"]
        if not path.exists():
            assert before["state"] == "absent"
            continue
        current = path.read_bytes()
        if current == original:
            continue
        changed.append({"path": entry["path"], "before": before,
                        "after": {"sha256": digest(current), "bytes": len(current)},
                        "action": "created" if before["state"] == "absent" else "updated"})
        diff.extend(difflib.unified_diff(original.decode().splitlines(keepends=True), current.decode().splitlines(keepends=True),
                                         fromfile="prestate/" + entry["path"], tofile="current/" + entry["path"]))
    retain(EVIDENCE / "source-changes.patch", "".join(diff).encode())
    runs = [(path, json.loads(path.read_text())) for path in sorted(EVIDENCE.glob("20*.json"))]
    builds = [(path, run) for path, run in runs if run.get("action") == "normalize" and run["status"] == "complete"]
    latest = builds[-1][1]["output"]
    assert latest["package_sha256"] == builds[-2][1]["output"]["package_sha256"]
    package = Path(latest["package_path"])
    manifest_bytes = (package / "manifest.json").read_bytes()
    assert digest(manifest_bytes) == latest["package_sha256"]
    manifest = json.loads(manifest_bytes)
    for name, expected in manifest["artifacts"].items():
        payload = (package / name).read_bytes()
        assert digest(payload) == expected["sha256"] and len(payload) == expected["bytes"]
    for name, expected in manifest["transforms"].items():
        assert digest((APP / name).read_bytes()) == expected
    acquisition = [run for _, run in runs if run.get("action") == "acquire"][-1]
    assert all(item["cache"] == "verified-skip" for item in acquisition["output"])
    checks = [run for _, run in runs if run.get("action") == "checks"][-1]
    assert all(item["exit_code"] == 0 for item in checks["output"])
    commands = [command([sys.executable, "-B", ".github/skills/agentcraft-process/validate.py",
                         str(PROJECT.relative_to(ROOT) / "constitution/constitution.yaml")]),
                command([sys.executable, "-B", ".github/tools/arch.py", "--root", str(APP), "--json"]),
                command(["git", "diff", "--check", "--", *[entry["path"] for entry in changed]])]
    for name in ("splunk/rundll32_tmp.log", "mitre/enterprise-attack.json", "packages/" + latest["package_sha256"] + "/manifest.json"):
        commands.append(command(["git", "check-ignore", "--", str((APP / "deploy/data/public-investigation" / name).relative_to(ROOT))]))
    commands.append(command(["git", "check-ignore", "--", "template_apps/investigation_app/deploy/data/runtime/webres/__init__.py"]))
    runtime = APP / "deploy/data/runtime"
    wheel = Path("/tmp/agentcraft-release-final/wheels/harness_web_resource-1.1.0-py3-none-any.whl")
    output = {"authority": "non-authoritative orchestrator primary evidence; overseer owns archival dispatch",
              "status": "complete" if all(item["exit_code"] == 0 for item in commands) else "checks-require-review",
              "started_at": started, "finished_at": datetime.now(timezone.utc).isoformat(),
              "duration_seconds": time.monotonic() - clock,
              "constitution": {"revision": 8, "sha256": digest((PROJECT / "constitution/constitution.yaml").read_bytes())},
              "archival_refs": [{"path": str(path.relative_to(PROJECT)), "sha256": digest(path.read_bytes())}
                               for path in (DECISION, PRESTATE / "record.json")],
              "changed_paths": changed, "commands": commands, "package": latest,
              "repeat_receipts": [str(path.relative_to(PROJECT)) for path, _ in builds[-2:]],
              "acquire_verified_skip_count": len(acquisition["output"]),
              "failed_attempts": [{"path": str(path.relative_to(PROJECT)), "error": run.get("error"),
                                   "duration_seconds": run.get("duration_seconds")} for path, run in runs if run["status"] == "failed"],
              "observed_cli_invocations": len(runs),
              "tracked_cli_seconds_not_total_effort": sum(run["duration_seconds"] for _, run in runs),
              "runtime": {"python": sys.version, "executable": sys.executable, "platform": platform.platform(),
                          "distributions": [{"name": item.metadata["Name"], "version": item.version}
                                            for item in importlib.metadata.distributions(path=[str(runtime)])],
                          "transport_wheel_sha256": digest(wheel.read_bytes()),
                          "transport_module_sha256": digest((runtime / "webres/__init__.py").read_bytes())},
              "candidate": {"invocations": 0, "pin": None, "reason": "not assigned in this local data slice"},
              "effort": {"requested": "max", "effective": "unverified", "total_duration_seconds": None, "cost": None},
              "settlement": {"workers": "none dispatched", "processes": "no persistent process started",
                             "cloud_operations": "none", "model_calls": "none", "private_inputs": "none",
                             "local_holdings": "retained ignored inputs/runtime/packages; no existing user file deleted",
                             "reversion": "prestate snapshots and exact diff retained; restore not executed",
                             "archival_outcome": "overseer checkpoint request pending; no records/notebook publication"},
              "capture_gaps": ["Initial inspection/install/edit tool timings unknown; source reads/actions summarized in actions.md.",
                               "Full host-owned raw tool transcript not exported; no private session log read.",
                               "Run-directory timestamp is an identifier, not measured start; receipts contain actual UTC.",
                               "No Pylance-specific host tools; editor-selected interpreter unknown. Runtime checks use /usr/bin/python3.",
                               "No production app/UI, Azure store, deployment, held-out score or effective max-effort attestation."]}
    output["evidence"] = [{"path": str(path.relative_to(PROJECT)), "sha256": digest(path.read_bytes()), "bytes": path.stat().st_size}
                          for path in sorted(EVIDENCE.iterdir()) if path.is_file() and path.name != "checkpoint-evidence.json"]
    encoded = (json.dumps(output, indent=2, sort_keys=True) + "\n").encode()
    retain(EVIDENCE / "checkpoint-evidence.json", encoded)
    print(json.dumps({"status": output["status"], "changed_paths": len(changed), "evidence_sha256": digest(encoded),
                      "package_sha256": latest["package_sha256"], "commands": commands}, indent=2))
    return int(output["status"] != "complete")


if __name__ == "__main__":
    raise SystemExit(main())