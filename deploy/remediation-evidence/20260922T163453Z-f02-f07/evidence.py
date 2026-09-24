"""Append-only local remediation evidence; never publishes authoritative records."""

import argparse
import ast
from datetime import datetime, timezone
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tarfile
import time

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("f00_capture", ROOT / "deploy/remediation/20260922T151500Z-f00/capture.py")
CAPTURE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CAPTURE)
CAPTURE.REPO = ROOT
ROOTS = CAPTURE.ROOTS[:3]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def save(name, data):
    path = OUT / name
    if not path.resolve().is_relative_to(OUT):
        raise ValueError("foreign evidence path")
    if not isinstance(data, bytes):
        data = (json.dumps(data, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    with path.open("xb") as stream:
        stream.write(data)
    if path.read_bytes() != data:
        raise ValueError("evidence readback mismatch")
    return {"path": str(path.relative_to(ROOT)), "sha256": digest(data), "bytes": len(data)}


def measure(files):
    result = {"files": len(files), "lines": 0, "functions": 0, "authenticated_http_sites": 0,
              "dependency_mutation_sites": 0}
    symbols = []
    for name, data in files.items():
        text = data.decode()
        result["lines"] += len(text.splitlines())
        if name.endswith(".py") and "/tests/" not in name:
            tree = ast.parse(text)
            symbols.extend(name + "::" + node.name for node in ast.walk(tree)
                           if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)))
            result["authenticated_http_sites"] += sum("Bearer " in line or "project.send_request(" in line for line in text.splitlines())
        result["dependency_mutation_sites"] += sum("uv pip install" in line or '"pip", "install"' in line for line in text.splitlines())
    result["functions"] = len(symbols)
    result["symbols"] = sorted(symbols)
    result["scope"] = "H/E/O allowlisted active UTF-8 files; excludes archives, data, tests from function counts, wheels and dependencies"
    return result


def snapshot(stage, baseline=False):
    files = {}
    if baseline:
        path = ROOT / "deploy/remediation-evidence/20260922T154800Z-f01/post-source.tar.gz"
        if digest(path.read_bytes()) != "d37c6c9edea9fe5d814b847eaf3ef67a5cd6653830d04a81152ba6edb69826b6":
            raise ValueError("F01 recovery archive drift")
        with tarfile.open(path) as archive:
            for member in archive.getmembers():
                if member.isfile() and any(member.name.startswith(root + "/") for root in ROOTS):
                    relative = Path(member.name)
                    if not set(relative.parts).intersection(CAPTURE.EXCLUDED | {"wheelhouse"}) and (relative.suffix in CAPTURE.SUFFIXES or relative.name in CAPTURE.NAMES):
                        files[member.name] = archive.extractfile(member).read()
    else:
        for path in CAPTURE.sources():
            name = str(path.relative_to(ROOT))
            if any(name.startswith(root + "/") for root in ROOTS) and "wheelhouse" not in path.parts:
                data = path.read_bytes()
                CAPTURE.safe(path, data)
                files[name] = data
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, data in sorted(files.items()):
            member = tarfile.TarInfo(name)
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))
    archive_ref = save(stage + "-source.tar.gz", buffer.getvalue())
    with tarfile.open(OUT / (stage + "-source.tar.gz")) as archive:
        for name, data in files.items():
            if archive.extractfile(name).read() != data:
                raise ValueError("archive recovery mismatch")
    return save(stage + "-source.json", {"archive": archive_ref, "archive_verified": True,
        "files": {name: {"sha256": digest(data), "bytes": len(data)} for name, data in sorted(files.items())},
        "measurement": measure(files), "observed_at": datetime.now(timezone.utc).isoformat()})


def clock():
    result = subprocess.run(["python3", ".github/tools/oplog.py", "check", "--run", "r-20260922T163534Z",
        "--log", str((OUT / "task-clock.jsonl").relative_to(ROOT))], cwd=ROOT, capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def run(stage, command):
    started = clock()
    tick = time.monotonic()
    result = subprocess.run(command, cwd=ROOT, capture_output=True, timeout=180)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = result.stdout + b"\nSTDERR\n" + result.stderr
    CAPTURE.safe(OUT / "output.txt", output)
    log = save(stamp + "-" + stage + ".txt", output)
    receipt = save(stamp + "-" + stage + ".json", {"stage": stage, "command": command,
        "exit_code": result.returncode, "seconds": time.monotonic() - tick,
        "start": started, "end": clock(), "output": log})
    print(output.decode(errors="replace"))
    print(json.dumps(receipt))
    return result.returncode


def history():
    path = ROOT / "deploy/remediation-evidence/20260922T151500Z-f00/capture.json"
    original = json.loads(path.read_text())["historical_hash_only"]
    for item in original:
        if digest((ROOT / item["path"]).read_bytes()) != item["sha256"]:
            raise ValueError("historical drift: " + item["path"])
    return save("historical-integrity.json", {"files_verified": len(original), "baseline": str(path.relative_to(ROOT))})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("snapshot", "baseline", "run", "history"))
    parser.add_argument("stage")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.action == "run":
        raise SystemExit(run(args.stage, args.command))
    print(json.dumps(history() if args.action == "history" else snapshot(args.stage, args.action == "baseline")))