#!/usr/bin/env bash
# GridIQ mock-data test stores: the only operator entry point. See README.md for the sequence.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA="$(cd "$HERE/../out" && pwd)"
ENV_NAME="test-grid"
export PYTHONDONTWRITEBYTECODE=1
PY=(python3 -B)
TAG_PROJECT="gridiq-mockdata"
POLL_SECONDS=30
POLL_MAX=120          # 120 x 30 s = 60 min ceiling for provisioning
RBAC_TRIES=30         # 30 x 30 s = 15 min ceiling for role propagation

REQUIRED=(AZURE_SUBSCRIPTION_ID AZURE_TENANT_ID AZURE_ACCOUNT_UPN RESOURCE_GROUP LOCATION NAME_PREFIX
  DEPLOYMENT_NAME ADX_SKU ADX_DATABASE COSMOS_DATABASE COSMOS_GRAPH GRAPH_PK SEARCH_SKU SEARCH_SEMANTIC
  EMBED_MODEL EMBED_MODEL_VERSION EMBED_SKU EMBED_CAPACITY STORAGE_CONTAINER)
PROVIDERS=(Microsoft.Kusto Microsoft.DocumentDB Microsoft.Search Microsoft.CognitiveServices Microsoft.Storage)
PY_MODULES="azure.identity, azure.kusto.data, gremlin_python, openai, azure.storage.blob"

usage() {
  cat <<EOF
usage: deploy.sh [-e <environment>] <command>

commands, in run order:
  preflight      tools, az login, subscription/tenant/user match, vars set, no secret-shaped vars
  plan           az deployment group what-if (compile-only while the group does not exist)
  provision      tagged group create + az deployment group create infra/main.bicep (bounded poll)
  load           load-kql, load-graph, load-search, load-reports
  load-kql | load-graph | load-search | load-reports
  verify         read every store back from outside; non-zero on any mismatch (VERIFY_LABEL=<tag>)
  smoke          run the real GridIQ tools against the stores
  outputs        print the non-secret deployment outputs
  teardown --confirm /subscriptions/<id>/resourceGroups/<rg>
EOF
}

die() { echo "error: $*" >&2; exit 1; }
say() { echo "== $*"; }

load_env() {
  local file="$HERE/env/$ENV_NAME.env"
  [[ -f "$file" ]] || die "no environment file $file"
  refuse_secrets "$file"
  set -a
  # shellcheck disable=SC1090
  . "$file"
  set +a
  local missing=()
  for v in "${REQUIRED[@]}"; do [[ -n "${!v:-}" ]] || missing+=("$v"); done
  (( ${#missing[@]} == 0 )) || die "unset in $file: ${missing[*]}"
}

refuse_secrets() {
  local file="$1" name value
  while IFS= read -r line; do
    [[ "$line" =~ ^[[:space:]]*# || ! "$line" =~ = ]] && continue
    name="${line%%=*}"; value="${line#*=}"
    if [[ "$name" =~ (KEY|SECRET|PASSWORD|TOKEN|CONNECTION|SAS)$ ]]; then
      die "$file: $name is secret-shaped; secrets never go in the environment file"
    fi
    if [[ "$value" =~ (AccountKey=|SharedAccessSignature|sig=|-----BEGIN|[A-Za-z0-9+/]{40,}) ]]; then
      die "$file: value of $name looks like a credential; remove it"
    fi
  done < "$file"
  for v in AI_SEARCH_API_KEY FABRIC_CLIENT_SECRET AZURE_CLIENT_SECRET; do
    [[ -z "${!v:-}" ]] || die "$v is set in this shell; unset it (this deployment uses the az CLI Entra identity only)"
  done
}

assert_account() {
  local got
  got="$(az account show --query '[id, tenantId, user.name]' -o tsv 2>/dev/null | tr '\n' ' ')" \
    || die "az is not logged in: az login --tenant $AZURE_TENANT_ID"
  read -r sub tenant user <<<"$got"
  [[ "$sub" == "$AZURE_SUBSCRIPTION_ID" ]] || die "active subscription $sub != $AZURE_SUBSCRIPTION_ID; select it yourself, this script will not switch"
  [[ "$tenant" == "$AZURE_TENANT_ID" ]] || die "active tenant $tenant != $AZURE_TENANT_ID"
  [[ "${user,,}" == "${AZURE_ACCOUNT_UPN,,}" ]] || die "signed-in user $user != $AZURE_ACCOUNT_UPN"
}

arm() {
  assert_account
  az account set --subscription "$AZURE_SUBSCRIPTION_ID"
}

operator_id() { az ad signed-in-user show --query id -o tsv; }

group_guard() {
  [[ "$(az group exists -n "$RESOURCE_GROUP")" == "true" ]] || return 1
  local project
  project="$(az group show -n "$RESOURCE_GROUP" --query "tags.project" -o tsv)"
  [[ "$project" == "$TAG_PROJECT" ]] || die "$RESOURCE_GROUP exists without tag project=$TAG_PROJECT; refusing to touch it"
  return 0
}

bicep_params() {
  local oid="$1"
  PARAMS=(--parameters
    namePrefix="$NAME_PREFIX" operatorPrincipalId="$oid"
    adxSku="$ADX_SKU" adxDatabaseName="$ADX_DATABASE"
    cosmosDatabaseName="$COSMOS_DATABASE" cosmosGraphName="$COSMOS_GRAPH"
    searchSku="$SEARCH_SKU" searchSemantic="$SEARCH_SEMANTIC"
    embedModel="$EMBED_MODEL" embedModelVersion="$EMBED_MODEL_VERSION" embedSku="$EMBED_SKU"
    embedCapacity="$EMBED_CAPACITY" storageContainerName="$STORAGE_CONTAINER"
    tags="{\"project\":\"$TAG_PROJECT\",\"owner\":\"$AZURE_ACCOUNT_UPN\",\"purpose\":\"test\"}")
}

outputs_file() {
  local state
  state="$(az deployment group show -g "$RESOURCE_GROUP" -n "$DEPLOYMENT_NAME" --query properties.provisioningState -o tsv 2>/dev/null)" \
    || die "no deployment $DEPLOYMENT_NAME in $RESOURCE_GROUP; run provision"
  [[ "$state" == "Succeeded" ]] || die "deployment $DEPLOYMENT_NAME is $state; run provision"
  OUTPUTS="$(mktemp -t tgrid-outputs.XXXXXX.json)"
  trap 'rm -f "$OUTPUTS"' EXIT
  az deployment group show -g "$RESOURCE_GROUP" -n "$DEPLOYMENT_NAME" --query properties.outputs -o json > "$OUTPUTS"
}

output() { "${PY[@]}" -c "import json,sys; print(json.load(open(sys.argv[1]))[sys.argv[2]]['value'])" "$OUTPUTS" "$1"; }

# ---------------------------------------------------------------- commands

cmd_preflight() {
  say "preflight ($ENV_NAME)"
  for t in az python3; do command -v "$t" >/dev/null || die "missing tool: $t"; done
  az bicep version >/dev/null 2>&1 || die "missing bicep: az bicep install"
  "${PY[@]}" -c "import ${PY_MODULES}" 2>/dev/null || die "python3 lacks one of: ${PY_MODULES} (install with uv pip install --python $(command -v python3) ...)"
  assert_account
  echo "account: $AZURE_ACCOUNT_UPN  subscription: $AZURE_SUBSCRIPTION_ID  tenant: $AZURE_TENANT_ID"
  local oid
  oid="$(operator_id)"; [[ -n "$oid" ]] || die "cannot resolve signed-in user object id"
  echo "operator object id: $oid"
  local roles
  roles="$(az role assignment list --assignee "$oid" --scope "/subscriptions/$AZURE_SUBSCRIPTION_ID" --include-inherited \
    --query "[?roleDefinitionName=='Owner' || roleDefinitionName=='User Access Administrator' || roleDefinitionName=='Role Based Access Control Administrator'].roleDefinitionName" -o tsv | sort -u | tr '\n' ' ')"
  [[ -n "$roles" ]] || die "caller cannot create role assignments (needs Owner, UAA or RBAC Administrator)"
  echo "caller roles able to grant: $roles"
  for p in "${PROVIDERS[@]}"; do
    [[ "$(az provider show -n "$p" --query registrationState -o tsv)" == "Registered" ]] \
      || die "provider $p not registered: az provider register -n $p"
  done
  echo "providers registered: ${PROVIDERS[*]}"
  if group_guard; then echo "group $RESOURCE_GROUP exists (tag project=$TAG_PROJECT)"; else echo "group $RESOURCE_GROUP absent"; fi
  "${PY[@]}" "$HERE/stores.py" check-data
  say "preflight ok"
}

cmd_plan() {
  arm
  az bicep build --file "$HERE/infra/main.bicep" --stdout >/dev/null
  if ! group_guard; then
    say "plan: $RESOURCE_GROUP absent; bicep compiles; provision creates the group, then what-if applies"
    return 0
  fi
  bicep_params "$(operator_id)"
  az deployment group what-if -g "$RESOURCE_GROUP" -n "$DEPLOYMENT_NAME" \
    --template-file "$HERE/infra/main.bicep" "${PARAMS[@]}"
}

cmd_provision() {
  arm
  group_guard || true
  say "group create $RESOURCE_GROUP ($LOCATION)"
  az group create -n "$RESOURCE_GROUP" -l "$LOCATION" \
    --tags project="$TAG_PROJECT" owner="$AZURE_ACCOUNT_UPN" purpose=test -o none
  bicep_params "$(operator_id)"
  say "deployment create $DEPLOYMENT_NAME (async; polling every ${POLL_SECONDS}s, max $((POLL_SECONDS * POLL_MAX / 60)) min)"
  az deployment group create -g "$RESOURCE_GROUP" -n "$DEPLOYMENT_NAME" \
    --template-file "$HERE/infra/main.bicep" "${PARAMS[@]}" --no-wait -o none
  local state="" i
  for ((i = 1; i <= POLL_MAX; i++)); do
    state="$(az deployment group show -g "$RESOURCE_GROUP" -n "$DEPLOYMENT_NAME" --query properties.provisioningState -o tsv)"
    echo "$(date -u +%H:%M:%SZ) provisioningState=$state"
    case "$state" in
      Succeeded) break ;;
      Failed|Canceled)
        az deployment operation group list -g "$RESOURCE_GROUP" -n "$DEPLOYMENT_NAME" \
          --query "[?properties.provisioningState=='Failed'].{resource:properties.targetResource.resourceName, error:properties.statusMessage.error}" -o json
        die "deployment $state" ;;
    esac
    sleep "$POLL_SECONDS"
  done
  [[ "$state" == "Succeeded" ]] || die "deployment still $state after $((POLL_SECONDS * POLL_MAX / 60)) min; rerun provision to keep polling"
  ensure_adx_admin
  az deployment group show -g "$RESOURCE_GROUP" -n "$DEPLOYMENT_NAME" \
    --query "{step:'provision', id:id, provisioningState:properties.provisioningState, timestamp:properties.timestamp, duration:properties.duration, correlationId:properties.correlationId, outputs:properties.outputs, outputResources:properties.outputResources[].id}" -o json \
    | "${PY[@]}" "$HERE/stores.py" record --step provision
  say "provision ok"
}

ensure_adx_admin() {
  local oid cluster db base existing aid
  oid="$(operator_id)"
  cluster="$(az deployment group show -g "$RESOURCE_GROUP" -n "$DEPLOYMENT_NAME" --query properties.outputs.adxName.value -o tsv)"
  db="$ADX_DATABASE"
  base="https://management.azure.com/subscriptions/$AZURE_SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.Kusto/clusters/$cluster/databases/$db/principalAssignments"
  existing="$(az rest --method get --url "$base?api-version=2023-08-15" -o json | "${PY[@]}" -c "
import json, sys
oid, upn = sys.argv[1].lower(), sys.argv[2].lower()
for a in json.load(sys.stdin)['value']:
    p = a['properties']
    if p.get('role') == 'Admin' and str(p.get('principalId', '')).lower() in (oid, upn):
        print(a['name'].split('/')[-1]); break
" "$oid" "$AZURE_ACCOUNT_UPN")"
  if [[ -n "$existing" ]]; then
    echo "adx: $AZURE_ACCOUNT_UPN is Admin on $cluster/$db (assignment $existing)"
    return 0
  fi
  aid="$("${PY[@]}" -c "import sys,uuid; print(uuid.uuid5(uuid.NAMESPACE_URL, sys.argv[1]))" "$cluster/$db/$oid/Admin")"
  az rest --method put --url "$base/$aid?api-version=2023-08-15" -o none --body \
    "{\"properties\":{\"principalId\":\"$oid\",\"principalType\":\"User\",\"role\":\"Admin\",\"tenantId\":\"$AZURE_TENANT_ID\"}}"
  echo "adx: granted $AZURE_ACCOUNT_UPN Admin on $cluster/$db (assignment $aid)"
}

cmd_load_kql()    { arm; outputs_file; "${PY[@]}" "$HERE/stores.py" load-kql --outputs "$OUTPUTS"; }
cmd_load_graph()  { arm; outputs_file; "${PY[@]}" "$HERE/stores.py" load-graph --outputs "$OUTPUTS"; }
cmd_load_search() { arm; outputs_file; "${PY[@]}" "$HERE/stores.py" load-search --outputs "$OUTPUTS"; }

cmd_load_reports() {
  arm; outputs_file
  local account container dir name md5 i uploaded=()
  account="$(output storageName)"; container="$(output storageContainer)"
  for dir in "$DATA"/search/*/; do
    name="$(basename "$dir")/report.pdf"
    md5="$("${PY[@]}" -c "import base64,hashlib,sys; print(base64.b64encode(hashlib.md5(open(sys.argv[1],'rb').read()).digest()).decode())" "$dir/report.pdf")"
    for ((i = 1; i <= RBAC_TRIES; i++)); do
      if az storage blob upload --auth-mode login --account-name "$account" -c "$container" -n "$name" \
           -f "$dir/report.pdf" --overwrite true --content-type application/pdf --content-md5 "$md5" -o none 2>/tmp/tgrid-blob-err.txt; then
        break
      fi
      echo "  retry upload $name ($i/$RBAC_TRIES): $(head -c 160 /tmp/tgrid-blob-err.txt)"
      (( i < RBAC_TRIES )) || die "upload $name failed"
      sleep 30
    done
    echo "load-reports: $container/$name"
    uploaded+=("\"$name\"")
  done
  printf '{"step":"load-reports","account":"%s","container":"%s","blobs":[%s],"finished":"%s"}\n' \
    "$account" "$container" "$(IFS=,; echo "${uploaded[*]}")" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    | "${PY[@]}" "$HERE/stores.py" record --step load-reports
}

cmd_load() { cmd_load_kql; cmd_load_graph; cmd_load_search; cmd_load_reports; say "load ok"; }

cmd_verify() { arm; outputs_file; "${PY[@]}" "$HERE/stores.py" verify --outputs "$OUTPUTS" --label "${VERIFY_LABEL:-}"; }

cmd_smoke() { arm; outputs_file; "${PY[@]}" "$HERE/smoke.py" --outputs "$OUTPUTS"; }

cmd_outputs() {
  arm; outputs_file
  "${PY[@]}" -c "import json,sys; [print(f'{k:24s} {v[\"value\"]}') for k, v in sorted(json.load(open(sys.argv[1])).items())]" "$OUTPUTS"
}

cmd_teardown() {
  local expected="/subscriptions/$AZURE_SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP"
  [[ "${1:-}" == "--confirm" && "${2:-}" == "$expected" ]] || die "teardown requires: --confirm $expected"
  arm
  group_guard || die "$RESOURCE_GROUP does not exist; nothing to delete"
  say "deleting $expected (blocks until done)"
  az group delete -n "$RESOURCE_GROUP" --yes
  [[ "$(az group exists -n "$RESOURCE_GROUP")" == "false" ]] || die "$RESOURCE_GROUP still exists"
  printf '{"step":"teardown","deleted":"%s","finished":"%s"}\n' "$expected" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    | "${PY[@]}" "$HERE/stores.py" record --step teardown
  say "teardown ok; the AI Services account is soft-deleted (see README)"
}

# ---------------------------------------------------------------- dispatch

if [[ "${1:-}" == "-e" ]]; then ENV_NAME="${2:?-e needs an environment name}"; shift 2; fi
COMMAND="${1:-}"; shift || true
case "$COMMAND" in
  preflight|plan|provision|load|verify|smoke|outputs) load_env; "cmd_$COMMAND" ;;
  load-kql|load-graph|load-search|load-reports) load_env; "cmd_${COMMAND//-/_}" ;;
  teardown) load_env; cmd_teardown "$@" ;;
  ""|-h|--help|help) usage ;;
  *) usage; die "unknown command: $COMMAND" ;;
esac
