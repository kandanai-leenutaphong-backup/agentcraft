#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"
ACTION=${1:-help}
if [[ $# -gt 0 ]]; then shift; fi
case "$ACTION" in
  setup)
    uv sync --locked --python /usr/bin/python3
    npm --prefix frontend ci --no-audit --no-fund
    ;;
  local)
    if [[ -n "${LIVE_PYTHON:-}" ]]; then
      exec "$LIVE_PYTHON" -B -m deploy.local "$@"
    fi
    exec uv run --locked python -B -m deploy.local "$@"
    ;;
  move-state) exec uv run --locked python -B -m deploy.migrate_state "$@" ;;
  test)
    uv run --locked python -B -m pytest "$@"
    npm --prefix frontend test
    npm --prefix frontend run build -- --logLevel warn
    ;;
  browser-verify)
    exec node frontend/tests/browser/verify-standalone.mjs "$@"
    ;;
  *) printf '%s\n' 'Usage: deploy/deploy.sh {setup|local|test|browser-verify}' \
       'local --source-root /path/to/perth_cyber [--check]' \
       'Local optimizer only. No investigation app or cloud lifecycle commands.'
     [[ "$ACTION" == help ]]
     ;;
esac