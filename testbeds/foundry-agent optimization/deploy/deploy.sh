#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
case "${1:-}" in
	install-loader|restore-sdk|optimizer-operation|optimize-retry-rejected|observe-holdout|final-holdout|register-existing|demonstration-*|apply-selected|final-version-canaries|baseline-validation|provision-optimizer-model) printf '%s\n' 'Retired historical action. Use a pinned migration manifest and read-only optimizer-reconcile; no replay.' >&2; exit 2 ;;
	manifest-check|existing-job-parity|mapped-canary|mapped-canary-readback|native-row-metrics|baseline-route-canary|observe-validation|live-check|capabilities|evaluator-register|evaluator-canary|canary-readback|build|deploy|runtime-canary|inspect-runtime|runtime-logs|model-inventory|optimizer-model-canary|optimize|optimizer-readback|optimizer-reconcile|optimizer-diagnostics|optimizer-wait|collect-candidates|candidate-validation) exec python3 deploy/live.py "$@" ;;
esac
exec python3 deploy/prepare.py "$@"