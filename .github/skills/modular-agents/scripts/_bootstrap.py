"""Resolve bundled source from this skill only, never from another checkout."""

import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
for module in ("agent-config-build", "purpose-built-tools", "foundry-agent-runtime", "foundry-hosted-agents"):
    sys.path.insert(0, str(SKILL_ROOT / "modules" / module))