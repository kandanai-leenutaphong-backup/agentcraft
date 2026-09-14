#!/usr/bin/env python3
"""Start this skill's locked MCP runtime without writing into its package."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    data_root = os.environ.get("PLUGIN_DATA")
    uv = shutil.which("uv")
    if not data_root:
        print("PLUGIN_DATA is required; launch through an Agent Plugins client.", file=sys.stderr)
        return 2
    if uv is None:
        print("Install uv: https://docs.astral.sh/uv/getting-started/installation/", file=sys.stderr)
        return 2
    data = Path(data_root).resolve() / root.name
    data.mkdir(parents=True, exist_ok=True)
    environment = {**os.environ, "UV_PROJECT_ENVIRONMENT": str(data / "venv"),
                   "UV_CACHE_DIR": str(data / "uv-cache"), "UV_PYTHON_DOWNLOADS": "never",
                   "PYTHONDONTWRITEBYTECODE": "1"}
    process = subprocess.run(
        [uv, "sync", "--locked", "--no-default-groups", "--no-install-project",
         "--extra", "mcp", "--project", str(root)],
        env=environment, stdout=sys.stderr, check=False,
    )
    if process.returncode:
        return process.returncode
    python = data / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    os.execve(str(python), [str(python), "-B", str(root / "scripts/mcp_server.py"),
                          "--config", str(data / "config.json"), *sys.argv[1:]], environment)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())