#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$ROOT/runtime.sh"
if ! command -v uv >/dev/null 2>&1; then
    printf '%s\n' 'Missing uv. Install it from https://docs.astral.sh/uv/getting-started/installation/ and rerun setup.sh.' >&2
    exit 2
fi
uv sync --locked --project "$ROOT"
uv run --locked --project "$ROOT" python -m playwright install chromium
printf '%s\n' 'Ready. Run ./scrape.sh https://example.com or ./test.sh.'
printf 'Environment: %s\nOutput: %s/output\n' "$UV_PROJECT_ENVIRONMENT" "$WEBSCRAPER_STATE_HOME"