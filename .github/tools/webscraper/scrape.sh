#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$ROOT/runtime.sh"
if ! command -v uv >/dev/null 2>&1; then
    printf '%s\n' 'Missing uv. Follow setup.sh prerequisites.' >&2
    exit 2
fi
exec uv run --locked --project "$ROOT" collect-html --out "$WEBSCRAPER_STATE_HOME/output" "$@"