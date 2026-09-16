#!/usr/bin/env bash
# ============================================================================
# deploy_kiosk.sh — Build + deploy the kiosk-mode public demo.
# ============================================================================
#
# Builds Dockerfile.kiosk (pure-nginx static SPA, no backend) on ACR and
# rolls it out to a non-production Container App.
#
# Why a separate script:
#   - Different Dockerfile (Dockerfile.kiosk vs Dockerfile)
#   - Different Container App target (kiosk-only, NEVER production)
#   - No env vars to inject (kiosk has no backend)
#   - No control/.env coupling (kiosk needs no LLM credentials)
#
# Prerequisites:
#   - azure_config.env populated by deploy_infra.sh (ACR_NAME,
#     ACR_LOGIN_SERVER, AZURE_RESOURCE_GROUP, APP_IDENTITY_ID).
#   - The target Container App already exists in the kiosk environment.
#     This script only updates its image — it does not provision the app.
#
# Options:
#   --tag TAG       Image tag (default: kiosk-YYYYMMDD-HHMMSS).
#   --app-name N    Target Container App (default: gridiq-v2).
#   --build-only    Build + push to ACR; do not roll out.
#   --update-only   Skip build; just point the app at --tag.
#   --yes           Skip prompts.
#
# Safety:
#   The script refuses to target any production app name. The hard-coded
#   blocklist below blocks gridiq-v1 / pathfinderiq-aemo / any name with
#   "prod" in it. Override only by editing PROD_BLOCKLIST below.
# ============================================================================
set -euo pipefail

# ── Colours ─────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'
info()  { echo -e "${BLUE}ℹ${NC}  $*"; }
ok()    { echo -e "${GREEN}✓${NC}  $*"; }
warn()  { echo -e "${YELLOW}⚠${NC}  $*"; }
fail()  { echo -e "${RED}✗${NC}  $*"; }
step()  { echo -e "\n${BOLD}${CYAN}━━━ $* ━━━${NC}\n"; }

# ── Production-target blocklist ─────────────────────────────────────
# Names this script will refuse to target. gridiq-v1 is the live
# regression / production backend; the kiosk image must never land
# there. Add new prod app names here as the deploy estate evolves.
PROD_BLOCKLIST=("gridiq-v1" "pathfinderiq-aemo")

# ── Args ────────────────────────────────────────────────────────────
IMAGE_TAG="kiosk-$(date +%Y%m%d-%H%M%S)"
CONTAINER_APP_NAME="gridiq-v2"
BUILD_ONLY=false
UPDATE_ONLY=false
AUTO_YES=false
# Optional client-side passcode gate. When non-empty, the build bakes
# the SHA-256 of this string into the bundle and shows a one-field
# unlock screen on first load. Empty = no gate. See PasswordGate.tsx.
KIOSK_PASSWORD=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --tag) IMAGE_TAG="$2"; shift 2 ;;
    --app-name) CONTAINER_APP_NAME="$2"; shift 2 ;;
    --build-only) BUILD_ONLY=true; shift ;;
    --update-only) UPDATE_ONLY=true; shift ;;
    --password) KIOSK_PASSWORD="$2"; shift 2 ;;
    --yes|-y) AUTO_YES=true; shift ;;
    --help|-h) sed -n '2,/^set -euo/p' "$0" | head -n -1; exit 0 ;;
    *) fail "Unknown option: $1"; exit 1 ;;
  esac
done

# ── Production-target refusal ───────────────────────────────────────
# Fires BEFORE any az call or build so a typo or stale shell alias
# cannot push the kiosk image at a production app.
for _prod in "${PROD_BLOCKLIST[@]}"; do
  if [[ "$CONTAINER_APP_NAME" == "$_prod" ]]; then
    fail "Refusing to target '$CONTAINER_APP_NAME' — this is a production app."
    fail "If you need to update production, use the backend deploy in the main repo."
    exit 2
  fi
done
if [[ "${CONTAINER_APP_NAME,,}" == *prod* ]]; then
  fail "Refusing to target '$CONTAINER_APP_NAME' — name contains 'prod'."
  exit 2
fi

# ── Locate project root ────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"
cd "$PROJECT_ROOT"

# ── WSL path helper ─────────────────────────────────────────────────
_az_path() {
  local p="$1"
  if [[ "$p" == /mnt/[a-z]/* ]] && command -v wslpath &>/dev/null; then
    wslpath -m "$p"
  else
    echo "$p"
  fi
}

# ── Load infra config ──────────────────────────────────────────────
if [[ ! -f azure_config.env ]]; then
  fail "azure_config.env not found. Run ./deploy_infra.sh first."
  exit 1
fi
# shellcheck disable=SC1091
# Unset CONTAINER_APP_NAME before sourcing so azure_config.env doesn't
# override the --app-name default.
_saved_app_name="$CONTAINER_APP_NAME"
source azure_config.env
CONTAINER_APP_NAME="$_saved_app_name"
unset _saved_app_name

: "${ACR_NAME:?ACR_NAME missing}"
: "${ACR_LOGIN_SERVER:?ACR_LOGIN_SERVER missing}"
: "${AZURE_RESOURCE_GROUP:?AZURE_RESOURCE_GROUP missing}"
: "${AZURE_SUBSCRIPTION_ID:?AZURE_SUBSCRIPTION_ID missing}"

IMAGE_NAME="${ACR_LOGIN_SERVER}/gridiq:${IMAGE_TAG}"

step "Kiosk deployment"
info "Subscription:   $AZURE_SUBSCRIPTION_ID"
info "Resource group: $AZURE_RESOURCE_GROUP"
info "ACR:            $ACR_LOGIN_SERVER"
info "Container App:  $CONTAINER_APP_NAME"
info "Image:          $IMAGE_NAME"
info "Dockerfile:     Dockerfile.kiosk (nginx-only)"

if ! $AUTO_YES; then
  read -r -p "Proceed? [y/N] " ans
  [[ "${ans,,}" == "y" || "${ans,,}" == "yes" ]] || { info "Aborted."; exit 0; }
fi

# ── Az CLI sanity ──────────────────────────────────────────────────
if ! az account show &>/dev/null; then
  fail "Run: az login"; exit 1
fi
az account set --subscription "$AZURE_SUBSCRIPTION_ID" >/dev/null

# ── Build ──────────────────────────────────────────────────────────
if ! $UPDATE_ONLY; then
  step "Building image on ACR"
  # Strip node_modules for the upload — the Docker build re-installs.
  if [[ -d "$PROJECT_ROOT/app/frontend/node_modules" ]]; then
    info "Removing app/frontend/node_modules/ (rebuilt in container)"
    rm -rf "$PROJECT_ROOT/app/frontend/node_modules"
  fi
  if ! az acr build \
    --registry "$ACR_NAME" \
    --image "gridiq:${IMAGE_TAG}" \
    --file "$(_az_path "$PROJECT_ROOT/Dockerfile.kiosk")" \
    --build-arg "VITE_KIOSK_PASSWORD=${KIOSK_PASSWORD}" \
    "$(_az_path "$PROJECT_ROOT")"; then
    fail "ACR build failed."
    exit 1
  fi
  ok "Built and pushed: $IMAGE_NAME"
  if $BUILD_ONLY; then exit 0; fi
fi

# ── Roll out ───────────────────────────────────────────────────────
step "Updating Container App"
if ! az containerapp update \
  --name "$CONTAINER_APP_NAME" \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --image "$IMAGE_NAME" \
  --output none; then
  fail "Container App update failed."
  exit 1
fi
ok "Container App updated to $IMAGE_NAME"

# Strip any backend env vars left over from the cloned spec — kiosk has no backend.
step "Stripping backend env vars"
ENV_NAMES=$(az containerapp show \
  --name "$CONTAINER_APP_NAME" \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --query "properties.template.containers[0].env[].name" -o tsv 2>/dev/null || true)
if [[ -n "$ENV_NAMES" ]]; then
  REMOVE_ARGS=()
  while IFS= read -r name; do
    [[ -n "$name" ]] && REMOVE_ARGS+=("$name")
  done <<< "$ENV_NAMES"
  if ((${#REMOVE_ARGS[@]} > 0)); then
    info "Removing ${#REMOVE_ARGS[@]} env var(s) from container"
    az containerapp update \
      --name "$CONTAINER_APP_NAME" \
      --resource-group "$AZURE_RESOURCE_GROUP" \
      --remove-env-vars "${REMOVE_ARGS[@]}" \
      --output none || warn "Env var strip returned non-zero (may be already empty)"
  fi
fi

# Keep replicas warm and allow burst headroom for stage demos. The kiosk
# is a static SPA with all demo state client-side (Zustand stores, no
# server sessions), so horizontal scaling is safe with no coordination.
# min=2 keeps two warm so a single replica reboot or zone blip never
# leaves the demo URL unanswerable; max=5 gives audience headroom in
# case the deep link is shared. The HTTP concurrency rule scales out
# when any single replica passes 30 in-flight requests — well under
# nginx default limits but tight enough that a packed room triggers
# a second replica before latency degrades.
step "Configuring warm-replica scale (2 warm, burst to 5)"
az containerapp update \
  --name "$CONTAINER_APP_NAME" \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --min-replicas 2 \
  --max-replicas 5 \
  --scale-rule-name http-concurrency \
  --scale-rule-type http \
  --scale-rule-http-concurrency 30 \
  --output none || warn "Scale config update failed (non-fatal)"

# Pull the FQDN and report.
FQDN=$(az containerapp show \
  --name "$CONTAINER_APP_NAME" \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --query "properties.configuration.ingress.fqdn" -o tsv)
ok "Deployment complete"
echo ""
echo "  URL: https://${FQDN}"
echo "  Tag: ${IMAGE_TAG}"
echo ""
