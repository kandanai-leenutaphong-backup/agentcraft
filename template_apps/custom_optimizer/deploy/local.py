from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import dotenv_values
from template_foundations.local_server import serve

ROOT = Path(__file__).resolve().parents[1]
COORDINATES = {"CYBEREYE_OPENAI_ENDPOINT", "CYBEREYE_MODEL", "CYBEREYE_SEARCH_ENDPOINT",
               "CYBEREYE_MITRE_SEARCH_INDEX", "CYBEREYE_GUIDE_DATA_DIR", "CYBEREYE_PYTHON_SANDBOX",
               "CYBEREYE_COPILOT_CLI"}


def configuration(source_root: Path | None, env_file: Path | None, inherited: dict[str, str]) -> dict[str, str]:
    environment = {key: value for key, value in inherited.items()
                   if not key.startswith(("CYBEREYE_", "ADX_", "GREMLIN_", "DEV_", "AUTH_")) and key != "PYTHONPATH"}
    files = (source_root / "deploy/env/prod.env", source_root / "app/cybereye/.env") if source_root else (env_file or ROOT / ".env",)
    if not any(path.is_file() for path in files):
        raise ValueError("supply --source-root or --env-file with model and GUIDE coordinates")
    for path in files:
        if path.is_file():
            environment.update({key: value for key, value in dotenv_values(path, interpolate=False).items()
                                if key in COORDINATES and value})
    if source_root:
        environment["CYBEREYE_GUIDE_DATA_DIR"] = str((source_root / "app/data/output/guide").resolve())
        sandbox = source_root / "app/cybereye/.local/tools/bubblewrap/usr/bin/bwrap"
        if sandbox.is_file():
            environment["CYBEREYE_PYTHON_SANDBOX"] = str(sandbox.resolve())
    if not environment.get("CYBEREYE_OPENAI_ENDPOINT") or not environment.get("CYBEREYE_GUIDE_DATA_DIR"):
        raise ValueError("model endpoint and GUIDE data directory are required; ADX is not")
    for name in ("CYBEREYE_OPENAI_ENDPOINT", "CYBEREYE_SEARCH_ENDPOINT"):
        value = environment.get(name)
        if not value:
            continue
        parsed = urlsplit(value)
        allowed = {"", "/", "/openai/v1", "/openai/v1/"} if name == "CYBEREYE_OPENAI_ENDPOINT" else {"", "/"}
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
                or parsed.query or parsed.fragment or parsed.port not in {None, 443}
                or parsed.path not in allowed or any(character.isspace() for character in value)):
            raise ValueError(f"invalid non-secret endpoint: {name}")
    data = Path(environment["CYBEREYE_GUIDE_DATA_DIR"]).resolve(strict=True)
    if not all((data / name).is_file() for name in ("source.sqlite", "labels.sqlite", "manifest.json")):
        raise ValueError("GUIDE preparation is incomplete")
    environment["CYBEREYE_GUIDE_DATA_DIR"] = str(data)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return environment


def main() -> int:
    parser = argparse.ArgumentParser(description="Run only Custom Optimizer on loopback")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--source-root", type=Path)
    source.add_argument("--env-file", type=Path)
    parser.add_argument("--backend-port", type=int, default=9012)
    parser.add_argument("--frontend-port", type=int, default=5180)
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    try:
        environment = configuration(arguments.source_root, arguments.env_file, dict(os.environ))
        if arguments.check:
            print(json.dumps({"configured": sorted(name for name in COORDINATES if environment.get(name)),
                              "state_root": str(ROOT / "app/cybereye/.local"), "requires_adx": False,
                              "cloud_contacted": False}, indent=2))
            return 0
        return serve(environment, arguments.backend_port, arguments.frontend_port,
                     root=ROOT, frontend=ROOT / "frontend", app_module="app.cybereye.backend.main:app",
                     label="Custom Optimizer")
    except (OSError, ValueError) as error:
        parser.exit(2, f"Preflight failed: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())