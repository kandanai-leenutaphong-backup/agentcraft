#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"
ACTION=${1:-help}
if [[ $# -gt 0 ]]; then shift; fi
case "$ACTION" in
  public-data-runtime)
    [[ $# -eq 1 && "$(basename "$1")" == harness_web_resource-*.whl && -f "$1" ]] || { printf '%s\n' 'Supply one existing harness-web-resource wheel.' >&2; exit 2; }
    exec "${LIVE_PYTHON:-python3}" -B -m pip install --no-deps --no-index --target "$ROOT/deploy/data/runtime" "$1"
    ;;
  public-data)
    export PYTHONPATH="$ROOT/deploy/data/runtime${PYTHONPATH:+:$PYTHONPATH}"
    exec "${LIVE_PYTHON:-python3}" -B -m deploy.public_data "$@"
    ;;
  cloud)
    exec "${LIVE_PYTHON:-python3}" -B -m deploy.cloud "$@"
    ;;
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
    printf '%s\n' 'Usage: deploy/deploy.sh {public-data|public-data-runtime|cloud|setup|test|local|verify|replay-baseline|browser-verify}' \
      'public-data --evidence PATH {acquire|verify|normalize|checks}: local public package, no Azure or model calls.' \
      'public-data-runtime /path/to/harness_web_resource-VERSION-py3-none-any.whl: optional existing wheel, no venv.' \
      'cloud {plan|preflight|package|apply|verify|teardown}: isolated target feasibility; mutations refused.' \
      'cloud package --output deploy/packages/NAME.tar: source-only review candidate, not a release image.' \
      'local --source-root /path/to/perth_cyber [--check]' \
      'replay-baseline {rules|evidence|assemble} --help: offline native-observation composition' \
      'browser-verify [editor|editor-live|investigation|native-offline|scanner|inventory]' \
      'native-offline: LIVE_PYTHON, active virtualenv or Investigation .venv; synthetic native I/O; no cloud.' \
      'Live browser suites use existing services and may invoke models; explicit operator authorization required.' \
      'Local migration and offline cloud planning only. No cloud provisioning, release, or teardown.'
    [[ "$ACTION" == help ]]
    ;;
esac