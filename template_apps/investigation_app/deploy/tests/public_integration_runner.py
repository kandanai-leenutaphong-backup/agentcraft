"""Retain local integration command evidence without cloud or environment setup."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--cwd", type=Path, required=True)
    parser.add_argument("--source", type=Path, action="append", default=[])
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("command required")
    args.evidence.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    record = {"started_at": stamp, "command": command, "cwd": str(args.cwd.resolve()),
              "sources": {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in args.source},
              "effort": "max requested; runtime unverified", "transport": "offline unless explicitly stated by check"}
    started = time.monotonic()
    process = subprocess.Popen(command, cwd=args.cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, start_new_session=True)
    try:
        stdout, stderr = process.communicate(timeout=args.timeout)
        output = stdout + stderr
        record["exit_code"] = process.returncode
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            stdout, stderr = process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            stdout, stderr = process.communicate()
        output = stdout + stderr
        record.update(exit_code=124, failure="timeout")
    record["elapsed_seconds"] = time.monotonic() - started
    record["finished_at"] = datetime.now(timezone.utc).isoformat()
    record["output"] = output
    path = args.evidence / (stamp + "-command.json")
    with path.open("x") as handle:
        json.dump(record, handle, indent=2)
        handle.write("\n")
    assert json.loads(path.read_text()) == record
    print(output, end="")
    print(f"Evidence: {path}")
    raise SystemExit(record["exit_code"])


if __name__ == "__main__":
    main()