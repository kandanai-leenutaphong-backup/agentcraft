#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
repository_root="$(dirname -- "$project_root")"
runtime="$project_root/data/.runtime"

if [[ "${1:-}" == setup-parquet ]]; then
    exec python3 -m pip install --no-deps --only-binary=:all: --target "$runtime" 'pyarrow==21.0.0'
fi

if [[ "${1:-}" == setup ]]; then
    python3 -m pip install --no-deps --no-build-isolation --target "$runtime" \
        "$repository_root/.github/skills/web-resource"
    exit 0
fi

export PYTHONPATH="$runtime"
export PYTHONDONTWRITEBYTECODE=1
if ! python3 -c 'import webres' 2>/dev/null; then
    printf 'Missing local download dependency. Run: bash %q setup\n' "$0" >&2
    exit 2
fi

if [[ "${1:-}" == test ]]; then
    shift
    exec python3 "$project_root/scripts/test_datasets.py" "$@"
fi
if [[ "${1:-}" == explore ]]; then
    shift
    exec python3 "$project_root/scripts/explore_data.py" "$@"
fi
exec python3 "$project_root/scripts/datasets.py" "$@"