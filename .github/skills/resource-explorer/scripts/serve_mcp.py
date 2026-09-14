#!/usr/bin/env python3
"""Install locked explorer dependencies in an isolated client-data namespace."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    data_path = os.environ.get("PLUGIN_DATA")
    uv = shutil.which("uv")
    if not data_path or uv is None:
        print("Launch with an Agent Plugins client, Python 3.11+ and uv on PATH.", file=sys.stderr)
        return 2
    data = Path(data_path).resolve() / "resource-explorer"
    data.mkdir(parents=True, exist_ok=True)
    environment = {
        **os.environ, "UV_PROJECT_ENVIRONMENT": str(data / "venv"),
        "UV_CACHE_DIR": str(data / "uv-cache"), "UV_PYTHON_DOWNLOADS": "never",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    synchronized = subprocess.run(
        [uv, "sync", "--locked", "--no-default-groups", "--no-install-project",
         "--no-install-package", "azdata", "--extra", "mcp", "--project", str(root)],
        env=environment, stdout=sys.stderr, check=False,
    )
    if synchronized.returncode:
        return synchronized.returncode
    python = data / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    os.execve(str(python), [str(python), "-B", str(root / "scripts/mcp_server.py"),
                          "--config", str(data / "config.json"), *sys.argv[1:]], environment)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())