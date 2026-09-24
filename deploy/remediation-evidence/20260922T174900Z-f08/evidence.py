"""F08 primary evidence; authoritative publication remains overseer-owned."""

import argparse
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "previous_evidence", ROOT / "deploy/remediation-evidence/20260922T163453Z-f02-f07/evidence.py")
PREVIOUS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PREVIOUS)
PREVIOUS.OUT = OUT
RUN = "r-20260922T174802Z"
DEADLINE = datetime.fromisoformat("2026-09-22T21:06:18+00:00")


def clock():
    result = subprocess.run(["python3", ".github/tools/oplog.py", "check", "--run", RUN,
        "--log", str((OUT / "task-clock.jsonl").relative_to(ROOT))],
        cwd=ROOT, capture_output=True, text=True, check=True)
    value = json.loads(result.stdout)
    value["mission_remaining_seconds"] = (DEADLINE - datetime.now(timezone.utc)).total_seconds()
    return value


def run(stage, command):
    owners = {"testbeds/foundry-hosted-agents/deploy/deploy.sh",
              "testbeds/foundry-agent-evaluation/deploy/deploy.sh",
              "testbeds/foundry-agent optimization/deploy/deploy.sh"}
    if len(command) < 3 or command[0] != "bash" or command[1] not in owners:
        raise ValueError("only owning deployment entrypoints permitted")
    started = clock()
    if started["mission_remaining_seconds"] <= 0:
        raise RuntimeError("hard deadline expired; no new actions")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    PREVIOUS.save(stamp + "-" + stage + "-intent.json", {"command": command, "start": started})
    tick = time.monotonic()
    result = subprocess.run(command, cwd=ROOT, capture_output=True)
    output = result.stdout + b"\nSTDERR\n" + result.stderr
    PREVIOUS.CAPTURE.safe(OUT / "output.txt", output)
    log = PREVIOUS.save(stamp + "-" + stage + ".txt", output)
    receipt = PREVIOUS.save(stamp + "-" + stage + ".json", {
        "command": command, "exit_code": result.returncode, "seconds": time.monotonic() - tick,
        "start": started, "end": clock(), "output": log,
        "capture_gap": "Clock checks unavailable during blocking owning command."})
    print(output.decode(errors="replace"))
    print(json.dumps(receipt))
    return result.returncode


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("snapshot", "history", "run", "clock"))
    parser.add_argument("stage", nargs="?", default="before-f08")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.action == "run":
        raise SystemExit(run(args.stage, args.command))
    print(json.dumps(clock() if args.action == "clock" else
                     PREVIOUS.history() if args.action == "history" else PREVIOUS.snapshot(args.stage)))