#!/usr/bin/env bash
# Rev-2 promotion (series pkg-e2e-optimized-v2) through template deploy.sh only; run after optimize_v2.sh select
# and `python3 -B inputs/build_inputs.py` emitted deploy-env/optimized-v2.{env,run.json}.
# Usage (any cwd): records/live/promote_v2.sh preflight | deploy | invoke | verify | eval-validation | eval-verification
set -uo pipefail
cd "$(dirname -- "${BASH_SOURCE[0]}")/../../../../template_apps/foundry_hosted_agent" || exit 1
P=../../agentcraft_projects/foundry-agent-package-e2e-20260924
SHA=$(sha256sum "$P/deploy-env/optimized-v2.run.json" | cut -d' ' -f1)
COMMON=(-e optimized-v2 --manifest-sha256 "$SHA" --env-dir "$P/deploy-env" --records "$P/records/live")
SELECT=$(ls "$P"/records/live/pkg-e2e-optimize-v2/select-*.json | grep -v -- '-baseline\.json$')
W=--authorize-cloud-write
case "${1:-}" in
  preflight) timeout 200 bash deploy/deploy.sh preflight "${COMMON[@]}" ;;
  deploy) timeout 230 bash deploy/deploy.sh deploy "${COMMON[@]}" $W --instructions-from-candidate "$SELECT" ;;
  invoke) timeout 230 bash deploy/deploy.sh invoke "${COMMON[@]}" $W --journeys "$P/inputs/journeys.json" ;;
  verify) timeout 230 bash deploy/deploy.sh verify "${COMMON[@]}" --journeys "$P/inputs/journeys.json" ;;
  eval-validation) timeout 1900 bash deploy/deploy.sh evaluate "${COMMON[@]}" $W \
                     --criteria "$P/inputs/criteria-optimized-v2-validation.json" --items "$P/dataset/validation.jsonl" ;;
  eval-verification) timeout 1900 bash deploy/deploy.sh evaluate "${COMMON[@]}" $W \
                       --criteria "$P/inputs/criteria-optimized-v2-verification.json" --items "$P/dataset/verification.jsonl" ;;
  *) echo "usage: $0 preflight|deploy|invoke|verify|eval-validation|eval-verification" >&2; exit 2 ;;
esac
