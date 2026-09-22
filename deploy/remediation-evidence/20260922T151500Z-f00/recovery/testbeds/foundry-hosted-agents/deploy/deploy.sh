#!/usr/bin/env bash
set -euo pipefail
here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo="$(cd -- "$here/../../.." && pwd)"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$here/..:$repo/libraries/modular-agents/modules/agent-config-build:$repo/libraries/llm-interface/src:$repo/libraries/framework-core/src${PYTHONPATH:+:$PYTHONPATH}"
exec python3 "$here/experiment.py" "$@"