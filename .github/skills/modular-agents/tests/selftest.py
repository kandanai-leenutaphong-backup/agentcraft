"""Run preserved mechanism checks and hosted integration checks without pytest."""

from __future__ import annotations

import os
import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--copy-out", action="store_true")
    arguments = parser.parse_args()
    environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    if arguments.copy_out:
        with tempfile.TemporaryDirectory(prefix="modular-agents-copy-") as temporary:
            destination = Path(temporary) / "modular-agents"
            shutil.copytree(ROOT, destination, ignore=shutil.ignore_patterns(
                ".venv", "__pycache__", ".pytest_cache", "*.egg-info", "node_modules",
                "build", "dist", "artifacts", "state", ".env", ".env.*",
            ))
            environment.pop("PYTHONPATH", None)
            result = subprocess.run(
                [sys.executable, "-I", str(destination / "tests/selftest.py")],
                cwd=temporary, env=environment, check=False,
            )
            return result.returncode
    checks = [
        ROOT / "modules" / module / "tests/selftest.py"
        for module in ("agent-config-build", "purpose-built-tools", "foundry-agent-runtime")
    ]
    checks.extend(sorted((ROOT / "tests").glob("test_*.py")))
    checks.append(ROOT / "examples/offline.py")
    for check in checks:
        result = subprocess.run(
            [sys.executable, str(check)], cwd=ROOT, env=environment,
            text=True, capture_output=True, check=False,
        )
        label = str(check.relative_to(ROOT))
        if result.returncode:
            print(f"FAIL {label}\n{result.stdout}\n{result.stderr}", flush=True)
            return result.returncode
        print(f"PASS {label}", flush=True)
        if check.parent == ROOT / "tests":
            print(result.stderr.strip(), flush=True)
    print(f"PASS {len(checks)} offline acceptance commands; no Azure calls", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())