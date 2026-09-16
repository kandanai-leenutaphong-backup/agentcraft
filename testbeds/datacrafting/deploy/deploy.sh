#!/usr/bin/env bash
set -euo pipefail
DEPLOY_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec uv run --frozen --project "$DEPLOY_ROOT/../azure-extraction" python "$DEPLOY_ROOT/lifecycle.py" "$@"