#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$ROOT/runtime.sh"
uv run --locked --project "$ROOT" python -m unittest discover -s "$ROOT/tests" -p 'test_*.py' -v
uv run --locked --project "$ROOT" python -m unittest discover -s "$ROOT/../../skills/web-resource/tests" -p test_network.py -v