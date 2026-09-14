#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$ROOT/runtime.sh"
exec uv run --locked --project "$ROOT" python -m data_collection.corpus "$@"