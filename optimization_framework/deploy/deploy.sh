#!/usr/bin/env bash
set -euo pipefail
umask 077

FRAMEWORK_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
export PYTHONPATH="$FRAMEWORK_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONDONTWRITEBYTECODE=1

usage() {
    printf '%s\n' \
        'Usage: deploy.sh COMMAND [OPTIONS]' \
        'setup                 Install frontend dependencies (no lockfile writes), build UI' \
        'test                  Run framework offline pytest suite and packaging tests' \
        'local [--port N] [--root PATH] [--allow-model-calls]' \
        'verify [--receipt PATH]  Isolated deterministic CLI/report/read-back checks' \
        'report --root PATH --run ID [--format json|csv|html] --output PATH' \
        'native-run --allow-model-calls --task ID [--root PATH] [native CLI limits]' \
        'describe|preflight|run|status|cancel|restore|feedback|respond  Existing CLI options' \
        'install-skill --client vscode --target PROJECT  Portable native skill bundle' \
        'cloud|teardown        Blocked: no cloud implementation or nonlocal authentication'
}

command_name="${1:-help}"
if [[ $# -gt 0 ]]; then shift; fi
case "$command_name" in
    help|--help|-h) usage; exit 0 ;;
    cloud|deploy|teardown)
        printf '%s\n' '{"status":"blocked","error":"cloud_not_implemented","detail":"Nonlocal authentication, deployment and teardown are not implemented."}' >&2
        exit 2 ;;
esac
command -v python3 >/dev/null || { printf '%s\n' 'Required: python3 >= 3.12 on PATH.' >&2; exit 2; }
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else "Required: python3 >= 3.12 on PATH.")'
for argument in "$@"; do
    if [[ "$argument" == --a* ]]; then
        if [[ "$argument" != --allow-model-calls || ( "$command_name" != local && "$command_name" != native-run ) ]]; then
            printf '%s\n' 'Only exact --allow-model-calls on local or native-run grants model permission.' >&2
            exit 2
        fi
    fi
done

case "$command_name" in
    setup)
        [[ $# -eq 0 ]] || { usage >&2; exit 2; }
        command -v npm >/dev/null || { printf '%s\n' 'Required: Node.js and npm on PATH.' >&2; exit 2; }
        cd -- "$FRAMEWORK_ROOT/frontend"
        npm install --package-lock=false --no-audit --no-fund
        npm run build
        ;;
    test)
        [[ $# -eq 0 ]] || { usage >&2; exit 2; }
        python3 -c 'import pytest' 2>/dev/null || { printf '%s\n' 'Required: pytest for python3. Install with python3 -m pip install pytest in your approved environment.' >&2; exit 2; }
        cd -- "$FRAMEWORK_ROOT"
        exec python3 -m pytest -q -p no:cacheprovider tests/test_core.py tests/test_executor.py tests/test_native_service.py tests/test_registry.py tests/test_cli_credentials.py deploy/tests
        ;;
    local) exec python3 -m optimization_framework serve "$@" ;;
    native-run)
        granted=false
        for argument in "$@"; do
            [[ "$argument" != --allow-model-calls ]] || granted=true
            if [[ "$argument" == --executor* ]]; then
                printf '%s\n' 'native-run fixes --executor copilot; do not supply --executor.' >&2
                exit 2
            fi
        done
        if [[ "$granted" != true ]]; then
            printf '%s\n' '{"status":"blocked","error":"model_calls_not_allowed"}' >&2
            exit 2
        fi
        exec python3 -m optimization_framework run --executor copilot "$@"
        ;;
    describe|preflight|run|status|cancel|restore|feedback|respond)
        exec python3 -m optimization_framework "$command_name" "$@"
        ;;
    verify|report|install-skill)
        exec python3 "$FRAMEWORK_ROOT/deploy/local.py" "$command_name" "$@"
        ;;
    *) usage >&2; exit 2 ;;
esac