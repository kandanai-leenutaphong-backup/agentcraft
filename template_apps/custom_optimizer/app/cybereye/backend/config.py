from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True, slots=True)
class Settings:
    app_root: Path = APP_ROOT
    guide_data_dir: str = os.getenv("CYBEREYE_GUIDE_DATA_DIR", "")
    optimization_dir: str = str(APP_ROOT / ".local/optimization")
    openai_endpoint: str = os.getenv("CYBEREYE_OPENAI_ENDPOINT", "")
    model: str = os.getenv("CYBEREYE_MODEL", "gpt-5.6-luna")
    search_endpoint: str = os.getenv("CYBEREYE_SEARCH_ENDPOINT", "")
    knowledge_index: str = os.getenv("CYBEREYE_MITRE_SEARCH_INDEX", "")
    copilot_cli: str = os.getenv("CYBEREYE_COPILOT_CLI", str(Path.home() / ".local/bin/copilot"))
    python_sandbox: str = os.getenv("CYBEREYE_PYTHON_SANDBOX", str(APP_ROOT / ".local/tools/bubblewrap/usr/bin/bwrap"))
    copilot_workspace_dir: str = str(APP_ROOT / ".local/copilot-workspaces")
    command_path: str = os.getenv("PATH", "/usr/local/bin:/usr/bin:/bin")
    local_api_origin: str = "http://127.0.0.1:" + os.getenv("CYBEREYE_PORT", "9012")


settings = Settings()