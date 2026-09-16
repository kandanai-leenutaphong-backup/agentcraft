#!/usr/bin/env bash
# ============================================================================
# deploy_kiosk_internal.sh — Build + deploy the kiosk to the INTERNAL tenant.
# ============================================================================
#
# Module role:
#   Internal-only deploy target. Same pipeline as deploy_kiosk.sh but
#   points at the Microsoft internal subscription
#   (ME-M365x21900035-hchoong-1) rather than the customer-facing sandbox.
#   Builds in the internal ACR and deploys to the internal Container App
#   environment. Provisions the gridiq-internal Container App on first
#   run if it does not exist; on subsequent runs just rolls a new image.
#
# Replica policy:
#   min=1 / max=2. Tighter than the public kiosk because the internal
#   instance is for staff testing — no audience headroom needed.
#
# Identity model:
#   Uses a system-assigned managed identity scoped only to AcrPull on the
#   internal ACR. Mirrors the hardening already applied to gridiq-v2 and
#   gridiq-v2 in the sandbox sub.
#
# Usage:
#   ./deploy_kiosk_internal.sh --yes
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

# ── Args ────────────────────────────────────────────────────────────
IMAGE_TAG="kiosk-$(date +%Y%m%d-%H%M%S)"
AUTO_YES=false
BUILD_ONLY=false
UPDATE_ONLY=false
# Client-side passcode gate, shared with the public kiosk (deploy_kiosk.sh).
# Supply it with --password or KIOSK_PASSWORD; never commit the value.
# See app/frontend/src/components/kiosk/PasswordGate.tsx for semantics.
KIOSK_PASSWORD="${KIOSK_PASSWORD:-}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --tag) IMAGE_TAG="$2"; shift 2 ;;
    --yes|-y) AUTO_YES=true; shift ;;
    --build-only) BUILD_ONLY=true; shift ;;
    --update-only) UPDATE_ONLY=true; shift ;;
    --password) KIOSK_PASSWORD="$2"; shift 2 ;;
    --help|-h) sed -n '2,/^set -euo/p' "$0" | head -n -1; exit 0 ;;
    *) fail "Unknown option: $1"; exit 1 ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [[ ! -f azure_config_internal.env ]]; then
  fail "azure_config_internal.env not found."; exit 1
fi
# shellcheck disable=SC1091
source azure_config_internal.env

: "${AZURE_SUBSCRIPTION_ID:?missing}"
: "${AZURE_RESOURCE_GROUP:?missing}"
: "${ACR_NAME:?missing}"
: "${ACR_LOGIN_SERVER:?missing}"
: "${CONTAINER_APP_ENV:?missing}"
: "${CONTAINER_APP_NAME:?missing}"

IMAGE_NAME="${ACR_LOGIN_SERVER}/gridiq:${IMAGE_TAG}"

# ── WSL path helper (mirrors deploy_kiosk.sh) ──────────────────────
_az_path() {
  local p="$1"
  if [[ "$p" == /mnt/[a-z]/* ]] && command -v wslpath &>/dev/null; then
    wslpath -m "$p"; else echo "$p"
  fi
}

step "Internal kiosk deployment"
info "Subscription:   $AZURE_SUBSCRIPTION_ID"
info "Resource group: $AZURE_RESOURCE_GROUP"
info "ACR:            $ACR_LOGIN_SERVER"
info "CA Environment: $CONTAINER_APP_ENV"
info "Container App:  $CONTAINER_APP_NAME"
info "Image:          $IMAGE_NAME"

if ! $AUTO_YES; then
  read -r -p "Proceed? [y/N] " ans
  [[ "${ans,,}" == "y" || "${ans,,}" == "yes" ]] || { info "Aborted."; exit 0; }
fi

# ── Az CLI sanity ──────────────────────────────────────────────────
if ! az account show &>/dev/null; then fail "Run: az login"; exit 1; fi
az account set --subscription "$AZURE_SUBSCRIPTION_ID" >/dev/null

# ── Build ──────────────────────────────────────────────────────────
if ! $UPDATE_ONLY; then
  step "Building image on ACR"
  if [[ -d "$SCRIPT_DIR/app/frontend/node_modules" ]]; then
    info "Removing app/frontend/node_modules/ (rebuilt in container)"
    rm -rf "$SCRIPT_DIR/app/frontend/node_modules"
  fi
  if ! az acr build \
    --registry "$ACR_NAME" \
    --image "gridiq:${IMAGE_TAG}" \
    --file "$(_az_path "$SCRIPT_DIR/Dockerfile.kiosk")" \
    --build-arg "VITE_KIOSK_PASSWORD=${KIOSK_PASSWORD}" \
    "$(_az_path "$SCRIPT_DIR")"; then
    fail "ACR build failed."; exit 1
  fi
  ok "Built and pushed: $IMAGE_NAME"
  if $BUILD_ONLY; then exit 0; fi
fi

# ── Provision-or-update ────────────────────────────────────────────
ACR_ID=$(az acr show -n "$ACR_NAME" --query id -o tsv)

if ! az containerapp show -n "$CONTAINER_APP_NAME" -g "$AZURE_RESOURCE_GROUP" &>/dev/null; then
  step "Creating Container App ($CONTAINER_APP_NAME)"
  # First-run create. System-assigned identity is added in the next
  # step so we can grant AcrPull before the first image pull happens
  # via the new identity. Initial create uses --registry-username and
  # --registry-password=NONE? Actually Container Apps requires SOME
  # auth mechanism at create time. We use the admin user temporarily
  # then switch to system identity below.
  #
  # Simpler: enable ACR admin user briefly, create, then switch. That
  # avoids a chicken-and-egg with role assignments.
  ADMIN_WAS_ON=$(az acr show -n "$ACR_NAME" --query "adminUserEnabled" -o tsv)
  if [[ "$ADMIN_WAS_ON" != "true" ]]; then
    info "Temporarily enabling ACR admin user for bootstrap"
    az acr update -n "$ACR_NAME" --admin-enabled true --output none
  fi
  ACR_PWD=$(az acr credential show -n "$ACR_NAME" --query "passwords[0].value" -o tsv)
  ACR_USER=$(az acr credential show -n "$ACR_NAME" --query "username" -o tsv)

  az containerapp create \
    --name "$CONTAINER_APP_NAME" \
    --resource-group "$AZURE_RESOURCE_GROUP" \
    --environment "$CONTAINER_APP_ENV" \
    --image "$IMAGE_NAME" \
    --target-port 8080 \
    --ingress external \
    --transport auto \
    --min-replicas 1 \
    --max-replicas 2 \
    --cpu 0.5 --memory 1Gi \
    --registry-server "$ACR_LOGIN_SERVER" \
    --registry-username "$ACR_USER" \
    --registry-password "$ACR_PWD" \
    --output none

  step "Hardening to system-assigned identity (AcrPull only)"
  SYS_PID=$(az containerapp identity assign \
    -n "$CONTAINER_APP_NAME" -g "$AZURE_RESOURCE_GROUP" \
    --system-assigned --query "principalId" -o tsv)
  az role assignment create \
    --assignee-object-id "$SYS_PID" \
    --assignee-principal-type ServicePrincipal \
    --role AcrPull --scope "$ACR_ID" --output none
  sleep 20
  az containerapp registry set \
    -n "$CONTAINER_APP_NAME" -g "$AZURE_RESOURCE_GROUP" \
    --server "$ACR_LOGIN_SERVER" --identity system --output none

  if [[ "$ADMIN_WAS_ON" != "true" ]]; then
    info "Restoring ACR admin user to disabled"
    az acr update -n "$ACR_NAME" --admin-enabled false --output none || true
  fi

  ok "Container App provisioned"
else
  step "Updating Container App image"
  az containerapp update \
    --name "$CONTAINER_APP_NAME" \
    --resource-group "$AZURE_RESOURCE_GROUP" \
    --image "$IMAGE_NAME" --output none
  ok "Container App updated to $IMAGE_NAME"
fi

# ── Strip backend env vars (kiosk has no backend) ──────────────────
step "Stripping any backend env vars"
ENV_NAMES=$(az containerapp show -n "$CONTAINER_APP_NAME" -g "$AZURE_RESOURCE_GROUP" \
  --query "properties.template.containers[0].env[].name" -o tsv 2>/dev/null || true)
if [[ -n "$ENV_NAMES" ]]; then
  REMOVE_ARGS=()
  while IFS= read -r name; do [[ -n "$name" ]] && REMOVE_ARGS+=("$name"); done <<< "$ENV_NAMES"
  if ((${#REMOVE_ARGS[@]} > 0)); then
    az containerapp update -n "$CONTAINER_APP_NAME" -g "$AZURE_RESOURCE_GROUP" \
      --remove-env-vars "${REMOVE_ARGS[@]}" --output none || warn "Env var strip non-zero"
  fi
fi

# ── Scale config ───────────────────────────────────────────────────
step "Configuring replica scale (1 warm, burst to 2)"
az containerapp update \
  --name "$CONTAINER_APP_NAME" \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --min-replicas 1 --max-replicas 2 \
  --scale-rule-name http-concurrency \
  --scale-rule-type http \
  --scale-rule-http-concurrency 30 \
  --output none || warn "Scale config update failed (non-fatal)"

FQDN=$(az containerapp show -n "$CONTAINER_APP_NAME" -g "$AZURE_RESOURCE_GROUP" \
  --query "properties.configuration.ingress.fqdn" -o tsv)
ok "Deployment complete"
echo ""
echo "  URL: https://${FQDN}"
echo "  Tag: ${IMAGE_TAG}"
echo ""
