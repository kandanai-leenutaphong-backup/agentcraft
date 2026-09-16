#!/usr/bin/env bash
#
# Historical writeup deployment source; existing-writeup is retired.
#
# All existing-writeup commands now refuse before any Azure call.
# Current writeup lifecycle: repository-root deploy/deploy.sh writeup.
# This legacy target is retained for reference only.
#
# Subcommands:
#   infra    resource group + ACR + Container Apps environment + Container App
#   base     rebuild the dependency base image (only when requirements.txt changes)
#   publish  build the Vocs site, build the content layer, and roll it out (~60s)
#   image    alias for publish
#   auth     Entra app registration + Container Apps built-in auth
#   devkey   push the Ed25519 PUBLIC verifier so signed requests are accepted
#   verify   assert anonymous requests are refused and signed requests admitted
#   all      infra -> base -> publish -> auth -> verify
#   teardown / destroy  refused: the resource group is shared
#
# Sign-in model: two mutually exclusive paths, both enforced by the app process.
#
#   1. Entra. Container Apps built-in auth runs the OIDC flow at /.auth/login/aad
#      and injects X-MS-CLIENT-PRINCIPAL-*. Platform action is AllowAnonymous so
#      requests reach the app; the app, not the platform, refuses anonymous
#      readers. The issuer is pinned to one tenant, so only that tenant's
#      accounts pass even though the registration is multi-tenant.
#
#   2. Ed25519 signed requests, for agent/CI piloting without a browser. Wire
#      shape from gridiq AUTODEV section 4.2. The server holds only the public
#      verifier. Unset DEV_PUBLIC_KEY_ED25519 and the path ceases to exist.
#
# The client secret is created, piped straight into a Container App secret, and
# never printed or written to disk.

set -euo pipefail

NAME=""
RESOURCE_GROUP=""
LOCATION=""
SUBSCRIPTION=""
TARGET_TENANT=""
ACR_NAME=""
APP_DISPLAY_NAME="Azure-Native Agentic Hillclimbing"
EXISTING_ENVIRONMENT=""
AUTH_TENANT=""
CONFIRM="no"
IMAGE_TAG="$(date -u +%Y%m%d%H%M%S)"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONTEXT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

log()  { printf '\033[36m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[33mwarn\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[31mfail\033[0m %s\n' "$*" >&2; exit 1; }

usage() { awk 'NR>1 && /^#/ { sub(/^# ?/, ""); print; next } NR>1 { exit }' "$0"; exit 0; }

TARGET_ENV="existing-writeup"
if [[ "${1:-}" == "-e" ]]; then
  TARGET_ENV="${2:-}"
  [[ "${TARGET_ENV}" =~ ^[a-z0-9-]+$ ]] || die "invalid environment name"
  shift 2
fi
TARGET_FILE="${SCRIPT_DIR}/env/${TARGET_ENV}.env"
[[ -f "${TARGET_FILE}" ]] || die "unknown environment: ${TARGET_ENV}"
declare -A TARGET_FIELDS=()
while IFS='=' read -r target_key target_value || [[ -n "${target_key}" ]]; do
  [[ -z "${target_key}" || "${target_key}" == \#* ]] && continue
  case "${target_key}" in
    SUBSCRIPTION|TARGET_TENANT|NAME|RESOURCE_GROUP|LOCATION|EXISTING_ENVIRONMENT|ACR_NAME|AUTH_TENANT)
      [[ -z "${TARGET_FIELDS[$target_key]:-}" ]] || die "duplicate target field: ${target_key}"
      [[ "${target_value}" =~ ^[A-Za-z0-9._-]+$ ]] || die "invalid target value for ${target_key}"
      printf -v "${target_key}" '%s' "${target_value}"
      TARGET_FIELDS[$target_key]=1
      ;;
    *) die "unknown target field: ${target_key}" ;;
  esac
done < "${TARGET_FILE}"
for target_key in SUBSCRIPTION TARGET_TENANT NAME RESOURCE_GROUP LOCATION EXISTING_ENVIRONMENT ACR_NAME AUTH_TENANT; do
  [[ -n "${!target_key}" ]] || die "missing target field: ${target_key}"
done

COMMAND="${1:-}"
[[ -z "${COMMAND}" || "${COMMAND}" == "-h" || "${COMMAND}" == "--help" ]] && usage
[[ "${TARGET_ENV}" != "existing-writeup" ]] \
  || die "existing-writeup is retired; use repository-root deploy/deploy.sh writeup."
shift || true

while [[ $# -gt 0 ]]; do
  case "$1" in
    --subscription)   SUBSCRIPTION="$2"; shift 2 ;;
    --resource-group) RESOURCE_GROUP="$2"; shift 2 ;;
    --location)       LOCATION="$2"; shift 2 ;;
    --name)           NAME="$2"; shift 2 ;;
    --tag)            IMAGE_TAG="$2"; shift 2 ;;
    --environment)    EXISTING_ENVIRONMENT="$2"; shift 2 ;;
    --auth-tenant)    AUTH_TENANT="$2"; shift 2 ;;
    --yes)            CONFIRM="yes"; shift ;;
    *) die "unknown argument: $1" ;;
  esac
done

require_az() {
  command -v az >/dev/null || die "Azure CLI not found"
  az account show >/dev/null 2>&1 || die "not signed in — run: az login"
  [[ "$(az account show --query id -o tsv)" == "${SUBSCRIPTION}" ]] \
    || die "subscription mismatch; run: az account set --subscription ${SUBSCRIPTION}"
  [[ "$(az account show --query tenantId -o tsv)" == "${TARGET_TENANT}" ]] \
    || die "tenant mismatch; sign in to tenant ${TARGET_TENANT}"
  [[ "$(az account show --query environmentName -o tsv)" == "AzureCloud" ]] \
    || die "cloud mismatch; expected AzureCloud"
  az extension show --name containerapp >/dev/null 2>&1 \
    || die "containerapp extension missing; run: az extension add --name containerapp"
}

app_name()   { echo "ca-${NAME}"; }
tenant_id()  { az account show --query tenantId -o tsv; }

fqdn() {
  az containerapp show --subscription "${SUBSCRIPTION}" -g "${RESOURCE_GROUP}" -n "$(app_name)" \
    --query properties.configuration.ingress.fqdn -o tsv 2>/dev/null || true
}

acr_name() {
  az acr show --subscription "${SUBSCRIPTION}" -g "${RESOURCE_GROUP}" -n "${ACR_NAME}" \
    --query name -o tsv 2>/dev/null || true
}

cmd_infra() {
  require_az
  log "resource group ${RESOURCE_GROUP} (${LOCATION})"
  az group create --subscription "${SUBSCRIPTION}" -n "${RESOURCE_GROUP}" -l "${LOCATION}" --only-show-errors >/dev/null

  log "provisioning registry, environment, and app"
  az deployment group create \
    --subscription "${SUBSCRIPTION}" \
    --resource-group "${RESOURCE_GROUP}" \
    --template-file "${SCRIPT_DIR}/main.bicep" \
    --parameters name="${NAME}" location="${LOCATION}" \
                 existingEnvironmentName="${EXISTING_ENVIRONMENT}" \
    --only-show-errors >/dev/null

  log "url https://$(fqdn)"
}

cmd_base() {
  require_az
  local acr
  acr="$(acr_name)"
  [[ -n "${acr}" ]] || die "no registry in ${RESOURCE_GROUP} — run 'infra' first"
  log "building the dependency base"
  az acr build --subscription "${SUBSCRIPTION}" --registry "${acr}" --image writeup-base:1 \
    --file "${SCRIPT_DIR}/Dockerfile.base" "${CONTEXT_DIR}" --only-show-errors >/dev/null
  log "base image ready"
}

cmd_image() {
  require_az
  local acr registry started
  acr="$(acr_name)"
  [[ -n "${acr}" ]] || die "no registry in ${RESOURCE_GROUP} — run 'infra' first"
  registry="$(az acr show --subscription "${SUBSCRIPTION}" -n "${acr}" --query loginServer -o tsv)"
  started=$(date +%s)

  # Node 22 is required by Vocs and is installed per-user, not system-wide.
  export PATH="${HOME}/.local/node22/bin:${PATH}"

  # The kiosk demo is staged into docs/public/demo so the site build carries it.
  log "staging the demo"
  "${SCRIPT_DIR}/stage_demo.sh" >/dev/null

  log "building the static site"
  (cd "${CONTEXT_DIR}" && npm run build >/dev/null)

  # Content is one layer on a cached base, so this stays well under a minute.
  log "building ${registry}/writeup:${IMAGE_TAG}"
  az acr build \
    --subscription "${SUBSCRIPTION}" \
    --registry "${acr}" \
    --image "writeup:${IMAGE_TAG}" \
    --file "${SCRIPT_DIR}/Dockerfile" \
    --build-arg BASE="${registry}/writeup-base:1" \
    "${CONTEXT_DIR}" \
    --only-show-errors >/dev/null

  log "rolling out"
  az containerapp update --subscription "${SUBSCRIPTION}" -g "${RESOURCE_GROUP}" -n "$(app_name)" \
    --image "${registry}/writeup:${IMAGE_TAG}" --only-show-errors >/dev/null

  log "published in $(( $(date +%s) - started ))s — https://$(fqdn)"
}

cmd_auth() {
  require_az
  local host tenant client_id secret
  host="$(fqdn)"
  [[ -n "${host}" ]] || die "app not deployed — run 'infra' first"
  tenant="$(tenant_id)"

  local redirect="https://${host}/.auth/login/aad/callback"

  client_id="$(az ad app list --display-name "${APP_DISPLAY_NAME}" \
      --query "[0].appId" -o tsv 2>/dev/null || true)"

  if [[ -z "${client_id}" ]]; then
    log "creating single-tenant app registration in tenant ${tenant}"
    client_id="$(az ad app create \
        --display-name "${APP_DISPLAY_NAME}" \
        --sign-in-audience AzureADMyOrg \
        --web-redirect-uris "${redirect}" \
        --enable-id-token-issuance true \
        --query appId -o tsv)" \
      || die "could not create an app registration — your tenant may block this. Ask an admin for a single-tenant registration with redirect URI ${redirect}"
  else
    log "reusing app registration ${client_id}"
    az ad app update --id "${client_id}" \
      --web-redirect-uris "${redirect}" \
      --enable-id-token-issuance true --only-show-errors
  fi

  # The secret goes straight from creation into a Container App secret. It is
  # never echoed, never stored on disk, and can be rotated by re-running 'auth'.
  log "issuing and storing a client secret"
  secret="$(az ad app credential reset --id "${client_id}" \
      --display-name "containerapp-easyauth" --years 1 --append \
      --query password -o tsv)"
  [[ -n "${secret}" ]] || die "no client secret returned"

  az containerapp secret set --subscription "${SUBSCRIPTION}" -g "${RESOURCE_GROUP}" -n "$(app_name)" \
    --secrets "aad-client-secret=${secret}" --only-show-errors >/dev/null
  unset secret

  log "enabling built-in authentication"
  az containerapp auth microsoft update \
    --subscription "${SUBSCRIPTION}" \
    -g "${RESOURCE_GROUP}" -n "$(app_name)" \
    --client-id "${client_id}" \
    --client-secret-name "aad-client-secret" \
    --issuer "https://login.microsoftonline.com/${AUTH_TENANT}/v2.0" \
    --yes --only-show-errors >/dev/null

  # Anonymous must reach the app, because the app also honours signed requests.
  # The app itself refuses unauthenticated readers.
  az containerapp auth update \
    --subscription "${SUBSCRIPTION}" \
    -g "${RESOURCE_GROUP}" -n "$(app_name)" \
    --enabled true \
    --action AllowAnonymous \
    --only-show-errors >/dev/null

  log "sign-in pinned to tenant ${AUTH_TENANT}"
  log "share https://${host}"
}

cmd_devkey() {
  require_az
  local pubkey
  pubkey="$(python3 "${SCRIPT_DIR}/dev_sign.py" init | cut -d= -f2-)"
  [[ -n "${pubkey}" ]] || die "could not derive a public verifier"

  # Public key only. The private half never leaves this machine.
  az containerapp update --subscription "${SUBSCRIPTION}" -g "${RESOURCE_GROUP}" -n "$(app_name)" \
    --set-env-vars "DEV_PUBLIC_KEY_ED25519=${pubkey}" \
    --only-show-errors >/dev/null
  log "signed-request path enabled for this operator key"
}

cmd_revoke() {
  require_az
  az containerapp update --subscription "${SUBSCRIPTION}" -g "${RESOURCE_GROUP}" -n "$(app_name)" \
    --remove-env-vars DEV_PUBLIC_KEY_ED25519 --only-show-errors >/dev/null
  log "signed-request path removed; Entra is the only way in"
}

cmd_verify() {
  require_az
  local host code
  host="$(fqdn)"
  [[ -n "${host}" ]] || die "app not deployed"

  code="$(curl --connect-timeout 15 --max-time 60 -s -o /dev/null -w '%{http_code}' "https://${host}/healthz")"
  [[ "${code}" == "200" ]] && log "health endpoint ready (200)" \
                           || die "expected 200 for health endpoint, got ${code}"

  # A browser must be sent to sign-in; an API-style caller must be refused.
  code="$(curl --connect-timeout 15 --max-time 60 -s -o /dev/null -w '%{http_code}' -H 'Accept: text/html' "https://${host}/")"
  [[ "${code}" == "302" ]] && log "browser redirected to sign-in (302)" \
                           || die "expected 302 for a browser, got ${code}"

  code="$(curl --connect-timeout 15 --max-time 60 -s -o /dev/null -w '%{http_code}' "https://${host}/")"
  [[ "${code}" == "401" ]] && log "anonymous request refused (401)" \
                           || die "expected 401 anonymous, got ${code} — CONTENT MAY BE PUBLIC"

  # Assets must be refused too, not just the document.
  code="$(curl --connect-timeout 15 --max-time 60 -s -o /dev/null -w '%{http_code}' "https://${host}/assets/quiet-revolution-grid-domain.png")"
  [[ "${code}" == "401" ]] && log "assets refused anonymously (401)" \
                           || die "expected 401 for assets, got ${code}"

  if [[ -f "${HOME}/.writeup/dev_signing_key" ]]; then
    APP_URL="https://${host}" python3 "${SCRIPT_DIR}/dev_sign.py" request GET /index.html \
      >/dev/null 2>&1 && log "signed request admitted" || die "signed request failed"
  else
    warn "signed request unverified: no existing operator key"
  fi

  log "open https://${host} in a browser to complete sign-in"
}

cmd_destroy() {
  die "refusing teardown: ${RESOURCE_GROUP} is shared; resource-specific cleanup needs separate approval"
}

case "${COMMAND}" in
  infra)   cmd_infra ;;
  base)    cmd_base ;;
  publish) cmd_image ;;
  image)   cmd_image ;;
  auth)    cmd_auth ;;
  devkey)  cmd_devkey ;;
  revoke)  cmd_revoke ;;
  verify)  cmd_verify ;;
  all)     cmd_infra; cmd_base; cmd_image; cmd_auth; cmd_verify ;;
  teardown|destroy) cmd_destroy ;;
  *) die "unknown subcommand: ${COMMAND}" ;;
esac
