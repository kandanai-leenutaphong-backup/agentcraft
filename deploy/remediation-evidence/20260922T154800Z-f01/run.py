"""Append-only F01 command receipts; never publishes authoritative records."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
RUN = "r-20260922T154843Z"


def clock():
    result = subprocess.run([sys.executable, str(ROOT / ".github/tools/oplog.py"),
                             "check", "--run", RUN, "--log", str(OUT / "worker-clock.jsonl")],
                            capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def run(command, cwd=ROOT, timeout=600):
    before = clock()
    started = time.monotonic()
    timestamp = datetime.now(timezone.utc)
    environment = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", UV_NO_PROGRESS="1",
                       UV_PYTHON_DOWNLOADS="never", UV_NO_BUILD_ISOLATION="1")
    process = subprocess.Popen(command, cwd=cwd, env=environment, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True)
    timed_out = False
    checks = [before]
    while True:
        try:
            stdout, stderr = process.communicate(timeout=min(45, max(1, timeout - (time.monotonic() - started))))
            break
        except subprocess.TimeoutExpired:
            checks.append(clock())
            if time.monotonic() - started >= timeout:
                process.kill()
                stdout, stderr = process.communicate()
                timed_out = True
                break
    checks.append(clock())
    result = {"command": command, "cwd": str(cwd), "started_at": timestamp.isoformat(),
              "ended_at": datetime.now(timezone.utc).isoformat(), "seconds": time.monotonic() - started,
              "exit_code": process.returncode, "timed_out": timed_out, "stdout": stdout,
              "stderr": stderr, "clock_checks": checks,
              "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    path = OUT / (timestamp.strftime("%Y%m%dT%H%M%S%fZ") + "-command.json")
    payload = json.dumps(result, indent=2, allow_nan=False) + "\n"
    with path.open("x") as stream:
        stream.write(payload)
    if path.read_text() != payload:
        raise RuntimeError("receipt readback mismatch")
    print(json.dumps({"receipt": str(path.relative_to(ROOT)), "exit_code": process.returncode,
                      "seconds": result["seconds"], "stdout_tail": stdout[-5000:], "stderr_tail": stderr[-5000:]}))
    return process.returncode or (124 if timed_out else 0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cwd", type=Path, default=ROOT)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    arguments = parser.parse_args()
    command = arguments.command
    if command[:1] == ["--"]:
        command = command[1:]
    if not command:
        parser.error("explicit command required")
    sys.exit(run(command, arguments.cwd, arguments.timeout))