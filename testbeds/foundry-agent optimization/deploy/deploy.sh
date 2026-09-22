#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
case "${1:-}" in
	demonstration-decision|demonstration-build|demonstration-deploy|demonstration-verify|demonstration-handoff) exec python3 deploy/live.py "$@" ;;
	mapped-canary|mapped-canary-readback|native-row-metrics|handoff|baseline-route-canary|observe-validation|observe-holdout) exec python3 deploy/live.py "$@" ;;
	live-check|capabilities|install-loader|evaluator-register|evaluator-canary|canary-readback|restore-sdk|build|deploy|runtime-canary|inspect-runtime|runtime-logs|baseline-validation|model-inventory|provision-optimizer-model|optimizer-model-canary|optimize|optimize-retry-rejected|optimizer-readback|optimizer-operation|optimizer-diagnostics|optimizer-wait|collect-candidates|candidate-validation|apply-selected|final-version-canaries|final-holdout) exec python3 deploy/live.py "$@" ;;
esac
exec python3 deploy/prepare.py "$@"