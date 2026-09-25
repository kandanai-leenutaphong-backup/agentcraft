#!/usr/bin/env bash
# Rev-2 optimization (series pkg-e2e-optimize-v2) through template deploy.sh only.
# Usage (any cwd): records/live/optimize_v2.sh preflight | register | poll [rounds] | select [demonstration]
# `poll` submits once (identity retained) then resumes polling each round; never resubmits. Log to stdout.
set -uo pipefail
cd "$(dirname -- "${BASH_SOURCE[0]}")/../../../../template_apps/foundry_hosted_agent" || exit 1
P=../../agentcraft_projects/foundry-agent-package-e2e-20260924
SHA=$(sha256sum "$P/deploy-env/optimize-v2.run.json" | cut -d' ' -f1)
COMMON=(-e optimize-v2 --manifest-sha256 "$SHA" --env-dir "$P/deploy-env" --records "$P/records/live")
SERIES="$P/records/live/pkg-e2e-optimize-v2"
case "${1:-}" in
  preflight) timeout 200 bash deploy/deploy.sh preflight "${COMMON[@]}" ;;
  register) timeout 230 bash deploy/deploy.sh register-evaluator "${COMMON[@]}" --authorize-cloud-write \
              --evaluator "$P/inputs/evaluator-graded-v2.json" ;;
  # Ledger-only; pass `demonstration` only when no generated candidate beats the baseline on native exact.
  select) timeout 60 bash deploy/deploy.sh select "${COMMON[@]}" --rule "$P/inputs/selection-rule-v2.json" \
            ${2:+--demonstration} ;;
  poll)
    for i in $(seq 1 "${2:-30}"); do
      echo "=== round $i $(date -u +%FT%TZ)"
      timeout 230 bash deploy/deploy.sh optimize "${COMMON[@]}" --authorize-cloud-write --previous-version \
        --optimization "$P/inputs/optimization-v2.json" --train "$P/dataset/train.jsonl" \
        --validation "$P/dataset/validation.jsonl"
      rc=$?
      echo "rc=$rc"
      latest=$(ls -t "$SERIES"/*-optimize.json 2>/dev/null | head -1)
      if [[ $rc -ne 0 ]]; then tail -c 1500 "$latest"; echo STOP_ERROR; exit "$rc"; fi
      if ! grep -q '"settled": false' "$latest"; then echo SETTLED; exit 0; fi
      grep -o '"status": "[a-z_]*"' "$latest" | head -3
      sleep 45
    done
    echo ROUNDS_EXHAUSTED ;;
  *) echo "usage: $0 preflight|register|poll [rounds]|select [demonstration]" >&2; exit 2 ;;
esac
