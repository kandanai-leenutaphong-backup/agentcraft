#!/usr/bin/env python3
"""Prepare locked dependencies in plugin data, then replace this process with the MCP server."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


def main() -> int:
    skill_root = Path(__file__).resolve().parents[1]
    data_path = os.environ.get("PLUGIN_DATA")
    if not data_path:
        print("PLUGIN_DATA is required; launch through an Agent Plugins client.", file=sys.stderr)
        return 2
    uv = shutil.which("uv")
    if uv is None:
        print("Install uv: https://docs.astral.sh/uv/getting-started/installation/", file=sys.stderr)
        return 2
    data = Path(data_path).resolve()
    environment = {
        **os.environ,
        "UV_PROJECT_ENVIRONMENT": str(data / "venv"),
        "UV_CACHE_DIR": str(data / "uv-cache"),
        "UV_PYTHON_DOWNLOADS": "never",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    synchronized = subprocess.run(
        [uv, "sync", "--locked", "--no-default-groups", "--no-install-project",
         "--extra", "mcp", "--project", str(skill_root)],
        env=environment, stdout=sys.stderr, check=False,
    )
    if synchronized.returncode:
        return synchronized.returncode
    python = data / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    os.execve(str(python), [
        str(python), str(skill_root / "scripts/mcp_server.py"),
        "--config", str(data / "config.json"), *sys.argv[1:],
    ], environment)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())