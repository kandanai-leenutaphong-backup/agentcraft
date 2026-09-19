"""Local packaging operations; application behavior remains in the existing CLI."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


FRAMEWORK = Path(__file__).resolve().parents[1]
ENTRY = FRAMEWORK / "deploy" / "deploy.sh"


def cli(*arguments):
    return subprocess.run(
        ["python3", "-m", "optimization_framework", *map(str, arguments)],
        check=True, capture_output=True, timeout=30,
    ).stdout


def publish(path, content):
    destination = Path(path).expanduser().absolute()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("xb") as stream:
        os.chmod(destination, 0o600)
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    if destination.read_bytes() != content:
        raise RuntimeError("output_readback_mismatch")
    return destination


def report(args):
    content = cli("report", "--root", args.root, "--run", args.run, "--format", args.format)
    destination = publish(args.output, content)
    return {"status": "complete", "output": str(destination), "bytes": len(content),
            "sha256": hashlib.sha256(content).hexdigest()}


def install_skill(args):
    destination = args.target.expanduser().absolute() / ".github/skills/optimization-experiment"
    if any(path.is_symlink() for path in (destination, *destination.parents)):
        raise ValueError("symlink_install_target")
    fixed = ["README.md", "pyproject.toml", "API_CONTRACT.json",
             "skills/optimization-experiment/SKILL.md",
             "frontend/package.json", "frontend/package-lock.json", "frontend/index.html",
             "frontend/tsconfig.json", "frontend/vite.config.ts", "frontend/README.md",
             "tests/test_core.py", "tests/test_executor.py", "tests/test_native_service.py"]
    sources = [FRAMEWORK / name for name in fixed]
    for directory, pattern in (("src", "*.py"), ("specs", "*.md"), ("deploy", "*.py"),
                               ("deploy", "*.sh"), ("deploy", "*.md"),
                               ("frontend/src", "*"), ("frontend/tests", "*")):
        sources.extend(path for path in (FRAMEWORK / directory).rglob(pattern) if path.is_file())
    payloads = {}
    for source in sorted(set(sources)):
        if any(path.is_symlink() for path in (source, *source.parents)):
            raise ValueError("symlink_bundle_source")
        relative = source.relative_to(FRAMEWORK)
        if "__pycache__" in relative.parts or source.suffix in {".pyc", ".pyo"}:
            continue
        payloads["framework/" + relative.as_posix()] = source.read_bytes()
    payloads["SKILL.md"] = (
        '---\nname: optimization-experiment\n'
        'description: "Use for local measured optimization experiments, deterministic tasks, '
        'explicitly authorized Copilot config-only trials, SME feedback and persisted reports."\n'
        '---\n\n# Optimization Experiment\n\n'
        'Read the bundled [primary skill](framework/skills/optimization-experiment/SKILL.md).\n'
        'Resolve all framework paths from that file, not the calling workspace.\n'
        'Discovery grants no model, cloud or application-write authority.\n'
    ).encode()
    hashes = {name: hashlib.sha256(content).hexdigest() for name, content in sorted(payloads.items())}
    payloads["bundle.json"] = (json.dumps({"schema_version": 1, "files": hashes}, indent=2) + "\n").encode()
    for name, content in payloads.items():
        path = destination / name
        if any(parent.is_symlink() for parent in (path, *path.parents)):
            raise ValueError("symlink_install_target")
        if path.exists() and (not path.is_file() or path.read_bytes() != content):
            raise FileExistsError("install_conflict: use a fresh target; existing files are never overwritten")
    for name, content in payloads.items():
        path = destination / name
        if not path.exists():
            publish(path, content)
    os.chmod(destination / "framework/deploy/deploy.sh", 0o700)
    for name, expected in hashes.items():
        if hashlib.sha256((destination / name).read_bytes()).hexdigest() != expected:
            raise RuntimeError("bundle_readback_mismatch")
    return {"status": "complete", "client": args.client, "skill": str(destination / "SKILL.md"),
            "files_verified": len(hashes), "model_calls": False, "cloud_calls": False,
            "fresh_agent_discovery": "unverified"}


def verify(args):
    checks = []
    subprocess.run(["bash", "-n", str(ENTRY)], check=True, timeout=10)
    checks.append("bash -n deploy/deploy.sh")
    runs = []
    with tempfile.TemporaryDirectory(prefix="optimization-packaging-") as temporary:
        root = Path(temporary) / "state"
        described = json.loads(cli("describe", "--root", root))
        assert described["executor"] == ["deterministic"]
        assert described["allow_model_calls"] is False
        assert described["cloud_calls"] is False
        checks.append("describe: deterministic only; model/cloud calls disabled")
        for task in ("agent-tool-availability", "csv-export-transformation"):
            run = json.loads(cli("run", "--root", root, "--task", task,
                                 "--idempotency-key", "packaging-" + task))
            assert run["status"] == "completed" and run["acceptance"] == "passed"
            assert run["decision"] == "inconclusive"
            assert [candidate["status"] for candidate in run["candidates"]] == ["passed", "failed", "passed"]
            assert run["metrics"]["model_requests"] is None
            run_id = run["id"]
            stored = json.loads(cli("status", "--root", root, "--run", run_id))
            assert stored == run
            duplicate = json.loads(cli("run", "--root", root, "--task", task,
                                       "--idempotency-key", "packaging-" + task))
            assert duplicate == stored
            exported = []
            for format_name in ("json", "csv", "html"):
                output = Path(temporary) / f"{task}.{format_name}"
                result = subprocess.run(
                    ["bash", str(ENTRY), "report", "--root", str(root), "--run", run_id,
                     "--format", format_name, "--output", str(output)],
                    cwd=temporary, check=True, capture_output=True, timeout=30,
                )
                receipt = json.loads(result.stdout)
                content = output.read_bytes()
                assert hashlib.sha256(content).hexdigest() == receipt["sha256"]
                assert content == cli("report", "--root", root, "--run", run_id, "--format", format_name)
                if format_name == "json":
                    assert json.loads(content) == stored
                exported.append({"format": format_name, "bytes": len(content), "sha256": receipt["sha256"]})
            refused = subprocess.run(
                ["bash", str(ENTRY), "report", "--root", str(root), "--run", run_id,
                 "--output", str(Path(temporary) / f"{task}.json")],
                capture_output=True, timeout=30,
            )
            assert refused.returncode == 2
            assert json.loads((Path(temporary) / f"{task}.json").read_bytes()) == stored
            checks.append(task + ": run, retained failure/repair, restart, idempotency, three exports, no-clobber")
            runs.append({"task": task, "run_id": run_id, "status": run["status"],
                         "acceptance": run["acceptance"], "decision": run["decision"], "exports": exported})
        for arguments, error in [
            (["native-run", "--task", "csv-export-transformation"], "model_calls_not_allowed"),
            (["cloud"], "cloud_not_implemented"),
        ]:
            refused = subprocess.run(["bash", str(ENTRY), *arguments], cwd=temporary,
                                     capture_output=True, timeout=10)
            assert refused.returncode == 2 and json.loads(refused.stderr)["error"] == error
            checks.append("refusal: " + error)
        refused = subprocess.run(
            ["python3", "-m", "optimization_framework", "run", "--root", str(root),
             "--task", "csv-export-transformation", "--executor", "copilot"],
            capture_output=True, timeout=30,
        )
        assert refused.returncode == 2 and json.loads(refused.stderr)["error"] == "model_calls_not_allowed"
        checks.append("CLI copilot refuses without model grant")
    receipt = {"status": "complete", "checked_at": datetime.now(timezone.utc).isoformat(),
               "python": sys.version.split()[0], "evidence_class": "synthetic-integration",
               "model_calls": False, "cloud_calls": False, "checks": checks, "runs": runs,
               "cleanup": "Isolated temporary root and exports removed; no server started.",
               "unverified": ["live native execution", "browser journey", "cloud/nonlocal authentication",
                              "fresh-agent discovery/adoption", "comparative improvement", "arbitrary-domain adapters"]}
    if args.receipt:
        publish(args.receipt, (json.dumps(receipt, indent=2) + "\n").encode())
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    verification = commands.add_parser("verify")
    verification.add_argument("--receipt", type=Path)
    export = commands.add_parser("report")
    export.add_argument("--root", type=Path, required=True)
    export.add_argument("--run", required=True)
    export.add_argument("--format", choices=("json", "csv", "html"), default="json")
    export.add_argument("--output", type=Path, required=True)
    installation = commands.add_parser("install-skill")
    installation.add_argument("--client", choices=("vscode",), required=True)
    installation.add_argument("--target", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = {"verify": verify, "report": report, "install-skill": install_skill}[args.command](args)
    except (OSError, ValueError, RuntimeError, AssertionError, subprocess.SubprocessError) as error:
        print(json.dumps({"status": "failed", "error": type(error).__name__,
                          "detail": "Operation failed; inspect prerequisites or choose an unused output path."}), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())