"""Local-only composition with borrowed data and template-owned writable state."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import dotenv_values
from template_foundations.local_server import free_port, serve


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "app/cybereye/frontend"
COORDINATES = frozenset({
    "ADX_CLUSTER_URI", "ADX_DATABASE", "CYBEREYE_TABLE", "CYBEREYE_EXTRA_TABLES",
    "CYBEREYE_OPENAI_ENDPOINT", "CYBEREYE_MODEL", "CYBEREYE_AGENT_MODELS",
    "CYBEREYE_SEARCH_ENDPOINT", "CYBEREYE_MITRE_SEARCH_INDEX",
    "GREMLIN_ACCOUNT", "GREMLIN_DATABASE", "GREMLIN_GRAPH",
    "GREMLIN_RESOURCE_GROUP", "GREMLIN_SUBSCRIPTION_ID",
    "CYBEREYE_MAX_ROWS", "CYBEREYE_QUERY_TIMEOUT_SECONDS",
})
AUTH_KEYS = ("DEV_PUBLIC_KEY_ED25519", "DEV_REPLAY_LEDGER", "AUTH_TENANT_ID", "AUTH_CLIENT_ID")


def configuration(*, source_root: Path | None, env_file: Path | None,
                  inherited: dict[str, str], root: Path = ROOT) -> dict[str, str]:
    environment = dict(inherited)
    if source_root is not None:
        source_root = source_root.resolve(strict=True)
        files = (source_root / "deploy/env/prod.env", source_root / "app/cybereye/.env")
    else:
        files = (env_file or root / "app/cybereye/.env",)
    if not any(path.is_file() for path in files):
        raise ValueError("no configuration file; pass --source-root or --env-file")
    values: dict[str, str] = {}
    for path in files:
        if path.is_file():
            values.update({key: value for key, value in dotenv_values(path, interpolate=False).items()
                           if value is not None and value.strip()})
    selected = {key: value for key, value in values.items() if key in COORDINATES}
    for target, source in (("GREMLIN_SUBSCRIPTION_ID", "AZURE_SUBSCRIPTION_ID"),
                           ("GREMLIN_RESOURCE_GROUP", "AZURE_RESOURCE_GROUP")):
        if target not in selected and values.get(source):
            selected[target] = values[source]
    for key in COORDINATES:
        environment.pop(key, None)
    environment.update(selected)
    for key in AUTH_KEYS:
        environment[key] = ""
    for key in ("ADX_CLUSTER_URI", "CYBEREYE_OPENAI_ENDPOINT"):
        if not environment.get(key):
            raise ValueError(f"missing required coordinate: {key}")
    for key in ("ADX_CLUSTER_URI", "CYBEREYE_OPENAI_ENDPOINT", "CYBEREYE_SEARCH_ENDPOINT"):
        value = environment.get(key)
        if not value:
            continue
        parsed = urlsplit(value)
        allowed_paths = {"", "/", "/openai/v1", "/openai/v1/"} if key == "CYBEREYE_OPENAI_ENDPOINT" else {"", "/"}
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
                or parsed.query or parsed.fragment or parsed.path not in allowed_paths
                or parsed.port not in (None, 443) or any(character.isspace() for character in value)):
            raise ValueError(f"invalid non-secret service coordinate: {key}")
    state = root / "app/cybereye/.local"
    environment.update({
        "CYBEREYE_AGENT_STORE_DIR": str(state / "agents"),
        "CYBEREYE_ALLOW_MODEL_CALLS": "false",
        "PYTHONDONTWRITEBYTECODE": "1",
    })
    for key in ("CYBEREYE_GUIDE_DATA_DIR", "CYBEREYE_OPTIMIZATION_DIR", "CYBEREYE_COPILOT_WORKSPACES", "CYBEREYE_PYTHON_SANDBOX", "CYBEREYE_COPILOT_CLI"):
        environment.pop(key, None)
    environment.pop("PYTHONPATH", None)
    return environment


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--source-root", type=Path)
    source.add_argument("--env-file", type=Path)
    parser.add_argument("--backend-port", type=int, default=9011)
    parser.add_argument("--frontend-port", type=int, default=5174)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--allow-model-calls", action="store_true", help="Explicitly grant bounded model inference for this local process.")
    arguments = parser.parse_args()
    try:
        environment = configuration(source_root=arguments.source_root, env_file=arguments.env_file,
                                    inherited=dict(os.environ))
        environment["CYBEREYE_ALLOW_MODEL_CALLS"] = "true" if arguments.allow_model_calls else "false"
        if arguments.check:
            print(json.dumps({"configured": sorted(key for key in COORDINATES if environment.get(key)),
                              "state_root": str(ROOT / "app/cybereye/.local"), "cloud_contacted": False}, indent=2))
            return 0
        return serve(environment, arguments.backend_port, arguments.frontend_port,
                 root=ROOT, frontend=FRONTEND, app_module="app.cybereye.backend.local_app:app",
                 label="CyberEye Investigation")
    except (OSError, ValueError) as exc:
        parser.exit(2, f"Local preflight failed: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())