#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"
ACTION=${1:-help}
if [[ $# -gt 0 ]]; then shift; fi
case "$ACTION" in
  setup)
    uv sync --locked --python /usr/bin/python3
    npm --prefix app/cybereye/frontend ci --no-audit --no-fund
    ;;
  test)
    uv run --locked python -B -m pytest app/cybereye/tests deploy/tests "$@"
    npm --prefix app/cybereye/frontend test
    npm --prefix app/cybereye/frontend run build
    ;;
  local)
    if [[ -n "${LIVE_PYTHON:-}" ]]; then
      exec "$LIVE_PYTHON" -B -m deploy.local "$@"
    fi
    exec uv run --locked python -B -m deploy.local "$@"
    ;;
  verify)
    if [[ -n "${LIVE_PYTHON:-}" ]]; then
      exec "$LIVE_PYTHON" -B -m deploy.verify "$@"
    fi
    exec uv run --locked python -B -m deploy.verify "$@"
    ;;
  replay-baseline)
    if [[ -n "${LIVE_PYTHON:-}" ]]; then
      exec "$LIVE_PYTHON" -B -m app.cybereye.tests.replay_baseline "$@"
    fi
    exec uv run --locked python -B -m app.cybereye.tests.replay_baseline "$@"
    ;;
  browser-verify)
    SUITE=${1:-editor}
    if [[ $# -gt 0 ]]; then shift; fi
    case "$SUITE" in
      editor) SCRIPT=verify-agent-editor.mjs; export CYBEREYE_EDITOR_LIVE=0 ;;
      editor-live) SCRIPT=verify-agent-editor.mjs; export CYBEREYE_EDITOR_LIVE=1 ;;
      investigation) SCRIPT=verify_chat_tabs.mjs ;;
      native-offline)
        SCRIPT=verify-native-investigation.mjs
        export ARTIFACT_DIR="${ARTIFACT_DIR:-/tmp/agentcraft-investigation-browser}"
        ;;
      scanner) SCRIPT=verify-scanner.mjs ;;
      inventory) SCRIPT=verify-current-catalogue.mjs ;;
      *) printf '%s\n' "Unknown browser suite: $SUITE" >&2; exit 2 ;;
    esac
    export CYBEREYE_URL="${CYBEREYE_URL:-http://127.0.0.1:5174}"
    if [[ ! "$CYBEREYE_URL" =~ ^http://(127\.0\.0\.1|localhost):[0-9]+/?$ ]]; then
      printf '%s\n' 'Browser verification requires a loopback HTTP origin.' >&2
      exit 2
    fi
    export ARTIFACT_DIR="${ARTIFACT_DIR:-$ROOT/artifacts/browser/$SUITE}"
    unset CYBEREYE_SIGNING_MODULE
    exec node "app/cybereye/frontend/tests/browser/$SCRIPT" "$@"
    ;;
  *)
    printf '%s\n' 'Usage: deploy/deploy.sh {setup|test|local|verify|replay-baseline|browser-verify}' \
      'local --source-root /path/to/perth_cyber [--check]' \
      'replay-baseline {rules|evidence|assemble} --help: offline native-observation composition' \
      'browser-verify [editor|editor-live|investigation|native-offline|scanner|inventory]' \
      'native-offline: LIVE_PYTHON, active virtualenv or Investigation .venv; synthetic native I/O; no cloud.' \
      'Live browser suites use existing services and may invoke models; explicit operator authorization required.' \
      'Local-only migration harness. No cloud provisioning, release, or teardown.'
    [[ "$ACTION" == help ]]
    ;;
esac