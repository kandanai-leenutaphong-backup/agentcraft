#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(dirname -- "$SCRIPT_DIR")"
ENVIRONMENT="example"

if [[ "${1:-}" == "-e" ]]; then
    ENVIRONMENT="${2:?environment name required}"
    shift 2
fi
if [[ ! "$ENVIRONMENT" =~ ^[A-Za-z0-9_-]+$ ]]; then
    printf '%s\n' 'Invalid environment name.' >&2
    exit 2
fi
if [[ "${1:-}" == "--help" || "$#" == 0 ]]; then
    printf '%s\n' 'Usage: deploy/deploy.sh [-e NAME] build|plan|deploy|verify|invoke|teardown [options]' \
        'build: [--output-dir DIR]' 'deploy: --artifact DIR --confirm' \
        'verify: [--artifact DIR]' 'invoke: --request FILE --confirm' 'teardown: --confirm'
    exit 0
fi
command -v uv >/dev/null || { printf '%s\n' 'Install uv before running this entry point.' >&2; exit 2; }
export PYTHONDONTWRITEBYTECODE=1
exec uv run --locked --no-default-groups --project "$SKILL_ROOT" \
    python "$SKILL_ROOT/scripts/agent.py" --env "$SCRIPT_DIR/env/$ENVIRONMENT.env" "$@"