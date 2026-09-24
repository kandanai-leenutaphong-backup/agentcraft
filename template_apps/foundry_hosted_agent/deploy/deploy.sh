#!/usr/bin/env bash
# The only operator entry point: test | preflight | build | deploy | invoke | verify | teardown.
set -euo pipefail
here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
app="$(cd -- "$here/.." && pwd)"
libraries="${AGENTCRAFT_LIBRARIES:-$(cd -- "$app/../.." && pwd)/libraries}"
export AGENTCRAFT_LIBRARIES="$libraries"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$here:$app/app:$libraries/foundry-ops/src:$libraries/llm-interface/src:$libraries/framework-core/src:$libraries/modular-agents/modules/agent-config-build${PYTHONPATH:+:$PYTHONPATH}"
exec "${PYTHON:-python3}" "$here/lifecycle.py" "$@"
