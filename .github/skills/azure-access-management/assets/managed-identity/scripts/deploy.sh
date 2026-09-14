#!/usr/bin/env bash
# deploy.sh — preview, then deploy, then verify. Exit-code driven.
#
# Three steps in a fixed order, because the middle one is the only irreversible
# part and the other two exist to bracket it:
#
#   1. what-if  — what would change. Read it; do not trust it blindly (G11).
#   2. create   — the deployment itself. Idempotent by construction.
#   3. verify   — assert the live grants match what the template declared.
#
# Usage:
#   ./scripts/deploy.sh -g <resource-group> -n <identity-name> [options]
#
# Options:
#   -s <search-service>        grant index management + document access
#   -S <search-rg>             resource group holding it (default: -g)
#   -a <ai-account>            grant model access
#   -A <ai-rg>                 resource group holding it (default: -g)
#   -V                         also grant the SEARCH SERVICE model access,
#                              for server-side vectorization
#   -y                         skip the confirmation prompt
#   -p                         preview only; do not deploy

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEMPLATE="$ROOT/bicep/main.bicep"

RG=""; IDENTITY=""; SEARCH=""; SEARCH_RG=""; AI=""; AI_RG=""
VECTORIZER="false"; ASSUME_YES="false"; PREVIEW_ONLY="false"

while getopts "g:n:s:S:a:A:Vyp" opt; do
  case "$opt" in
    g) RG="$OPTARG" ;;
    n) IDENTITY="$OPTARG" ;;
    s) SEARCH="$OPTARG" ;;
    S) SEARCH_RG="$OPTARG" ;;
    a) AI="$OPTARG" ;;
    A) AI_RG="$OPTARG" ;;
    V) VECTORIZER="true" ;;
    y) ASSUME_YES="true" ;;
    p) PREVIEW_ONLY="true" ;;
    *) echo "see the header of $0 for usage" >&2; exit 2 ;;
  esac
done

[[ -n "$RG" && -n "$IDENTITY" ]] || { echo "-g and -n are required" >&2; exit 2; }
SEARCH_RG="${SEARCH_RG:-$RG}"
AI_RG="${AI_RG:-$RG}"

PARAMS=(identityName="$IDENTITY")
[[ -n "$SEARCH" ]] && PARAMS+=(searchServiceName="$SEARCH" searchServiceResourceGroup="$SEARCH_RG")
[[ -n "$AI" ]] && PARAMS+=(aiAccountName="$AI" aiAccountResourceGroup="$AI_RG")

# Server-side vectorization grants the SEARCH SERVICE's own identity access to
# the model account — a different principal from the workload identity. It must
# exist before it can be granted anything.
if [[ "$VECTORIZER" == "true" ]]; then
  [[ -n "$SEARCH" && -n "$AI" ]] || { echo "-V needs both -s and -a" >&2; exit 2; }
  PRINCIPAL="$(az search service show -n "$SEARCH" -g "$SEARCH_RG" \
      --query identity.principalId -o tsv)"
  if [[ -z "$PRINCIPAL" || "$PRINCIPAL" == "null" ]]; then
    echo "the search service has no identity yet; assigning one" >&2
    az search service update -n "$SEARCH" -g "$SEARCH_RG" \
        --identity-type SystemAssigned -o none
    PRINCIPAL="$(az search service show -n "$SEARCH" -g "$SEARCH_RG" \
        --query identity.principalId -o tsv)"
  fi
  PARAMS+=(grantSearchServiceModelAccess=true searchServicePrincipalId="$PRINCIPAL")
fi

echo "subscription: $(az account show --query name -o tsv)"
echo "group:        $RG"
echo "identity:     $IDENTITY"
echo

echo "── what-if ─────────────────────────────────────────────────────────────"
az deployment group what-if -g "$RG" --template-file "$TEMPLATE" \
    --parameters "${PARAMS[@]}" || true
echo
echo "NOTE: role assignments whose name depends on a principal that does not"
echo "exist yet are reported as 'Unsupported' rather than as 'Create'. An empty"
echo "what-if does NOT mean nothing will change (GOTCHAS.md G11)."
echo

[[ "$PREVIEW_ONLY" == "true" ]] && exit 0

if [[ "$ASSUME_YES" != "true" ]]; then
  read -r -p "deploy these grants? [y/N] " answer
  [[ "$answer" == "y" || "$answer" == "Y" ]] || { echo "aborted"; exit 1; }
fi

echo "── deploy ──────────────────────────────────────────────────────────────"
az deployment group create -g "$RG" -n "identity-$IDENTITY" \
    --template-file "$TEMPLATE" --parameters "${PARAMS[@]}" \
    --query "{state:properties.provisioningState,principalId:properties.outputs.principalId.value,clientId:properties.outputs.clientId.value}" \
    -o json

echo
echo "── verify ──────────────────────────────────────────────────────────────"
python3 "$ROOT/scripts/verify.py" -g "$RG" -n "identity-$IDENTITY"
