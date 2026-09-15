#!/usr/bin/env bash
set -euo pipefail

directory="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if ! command -v python3 >/dev/null 2>&1; then
    printf '%s\n' 'Python 3.11+ is required; install it before running this entry point.' >&2
    exit 1
fi
if [[ "${1:-}" == test && "$#" -eq 1 ]]; then
    exec python3 -B -m unittest discover -s "$directory/tests" -q
fi
if [[ "${1:-}" == live ]]; then
    shift
    exec "${LIVE_PYTHON:-python3}" -B "$directory/live.py" "$@"
fi
exec python3 -B "$directory/resource_group.py" "$@"