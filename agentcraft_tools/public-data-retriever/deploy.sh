#!/usr/bin/env bash
# public-data-retriever entry point: up | run | wait | status | logs | verify | teardown   [-e <env>, default eastus]
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
envname=eastus
[[ "${1:-}" == -e ]] && { envname=$2; shift 2; }
cmd=${1:-}

set -a; source "$here/env/$envname.env"; set +a
for v in AZURE_SUBSCRIPTION_ID LOCATION RESOURCE_GROUP STORAGE_ACCOUNT CONTAINER IDENTITY JOB IMAGE; do
  [[ -n "${!v:-}" ]] || { echo "missing $v in env/$envname.env" >&2; exit 2; }
done
command -v az >/dev/null || { echo "az CLI required" >&2; exit 2; }
active=$(az account show --query id -o tsv 2>/dev/null) || { echo "run: az login" >&2; exit 2; }
[[ "$active" == "$AZURE_SUBSCRIPTION_ID" ]] || { echo "run: az account set --subscription $AZURE_SUBSCRIPTION_ID" >&2; exit 2; }

role="Storage Blob Data Contributor"
blob() { az storage "$@" --auth-mode login --account-name "$STORAGE_ACCOUNT" -o none --only-show-errors; }

# Runs in the container; must contain no single quotes.
boot='set -e; command -v jq >/dev/null || tdnf install -y jq >/dev/null; for i in $(seq 20); do az login --identity --client-id "$AZURE_CLIENT_ID" -o none && break; sleep 15; done; for i in $(seq 20); do az storage blob download --auth-mode login --account-name "$STORAGE_ACCOUNT" -c "$CONTAINER" -n _config/fetch.sh -f /tmp/fetch.sh -o none --only-show-errors && az storage blob download --auth-mode login --account-name "$STORAGE_ACCOUNT" -c "$CONTAINER" -n _config/sources.txt -f /tmp/sources.txt -o none --only-show-errors && break; sleep 30; done; exec bash /tmp/fetch.sh'

grant() { # object-id principal-type
  local scope
  scope=$(az storage account show -g "$RESOURCE_GROUP" -n "$STORAGE_ACCOUNT" --query id -o tsv)
  [[ -n $(az role assignment list --scope "$scope" --role "$role" --query "[?principalId=='$1'].id" -o tsv) ]] ||
    az role assignment create --assignee-object-id "$1" --assignee-principal-type "$2" --scope "$scope" --role "$role" -o none
}

push_config() { # retries cover role-assignment propagation
  local f i
  for f in fetch.sh sources.txt; do
    for i in $(seq 20); do
      blob blob upload -c "$CONTAINER" -f "$here/$f" -n "_config/$f" --overwrite && break
      [[ $i == 20 ]] && { echo "upload of $f failed" >&2; exit 1; }
      sleep 15
    done
  done
}

create_job() {
  local id client
  id=$(az identity show -g "$RESOURCE_GROUP" -n "$IDENTITY" --query id -o tsv)
  client=$(az identity show -g "$RESOURCE_GROUP" -n "$IDENTITY" --query clientId -o tsv)
  az container create -g "$RESOURCE_GROUP" -n "$JOB" -l "$LOCATION" --image "$IMAGE" --os-type Linux \
    --cpu 1 --memory 2 --restart-policy Never --assign-identity "$id" \
    --environment-variables STORAGE_ACCOUNT="$STORAGE_ACCOUNT" CONTAINER="$CONTAINER" AZURE_CLIENT_ID="$client" \
    --command-line "bash -c '$boot'" -o none
}

job_state() { az container show -g "$RESOURCE_GROUP" -n "$JOB" --query "[containers[0].instanceView.currentState.state, to_string(containers[0].instanceView.currentState.exitCode)]" -o tsv 2>/dev/null | tr '\n' ' '; }

case "$cmd" in
  up)
    az group create -n "$RESOURCE_GROUP" -l "$LOCATION" --tags app=public-data-retriever -o none
    az storage account create -g "$RESOURCE_GROUP" -n "$STORAGE_ACCOUNT" -l "$LOCATION" --sku Standard_LRS --kind StorageV2 \
      --allow-shared-key-access false --allow-blob-public-access false --min-tls-version TLS1_2 -o none
    [[ $(az storage container-rm exists -g "$RESOURCE_GROUP" --storage-account "$STORAGE_ACCOUNT" -n "$CONTAINER" --query exists -o tsv) == true ]] ||
      az storage container-rm create -g "$RESOURCE_GROUP" --storage-account "$STORAGE_ACCOUNT" -n "$CONTAINER" -o none
    az identity create -g "$RESOURCE_GROUP" -n "$IDENTITY" -l "$LOCATION" -o none
    grant "$(az identity show -g "$RESOURCE_GROUP" -n "$IDENTITY" --query principalId -o tsv)" ServicePrincipal
    grant "$(az ad signed-in-user show --query id -o tsv)" User
    push_config
    create_job
    echo "up: job started; next: $0 wait && $0 verify"
    ;;
  run)
    push_config
    az container delete -g "$RESOURCE_GROUP" -n "$JOB" --yes -o none 2>/dev/null || true
    create_job
    echo "run: started; next: $0 wait && $0 verify"
    ;;
  wait)
    for _ in $(seq 240); do
      read -r state code <<< "$(job_state)"
      [[ "$state" == Terminated ]] && { echo "terminated exit=$code"; exit 0; }
      sleep 15
    done
    echo "timed out; state=$(job_state)" >&2; exit 1
    ;;
  status)
    echo "job: $(job_state)"
    az storage account show -g "$RESOURCE_GROUP" -n "$STORAGE_ACCOUNT" \
      --query "{sharedKey:allowSharedKeyAccess,publicBlob:allowBlobPublicAccess,network:publicNetworkAccess,tls:minimumTlsVersion}" -o tsv
    ;;
  logs)
    az container logs -g "$RESOURCE_GROUP" -n "$JOB"
    ;;
  verify)
    latest=$(az storage blob list --auth-mode login --account-name "$STORAGE_ACCOUNT" -c "$CONTAINER" --prefix _runs/ \
      --query "sort_by(@,&name)[-1].name" -o tsv --only-show-errors)
    [[ -n "$latest" ]] || { echo "no run log found" >&2; exit 1; }
    tmp=$(mktemp)
    blob blob download -c "$CONTAINER" -n "$latest" -f "$tmp"
    echo "$latest"
    python3 -c "import json,sys,collections; rows=[json.loads(l) for l in open(sys.argv[1])]; c=collections.Counter(r['status'] for r in rows); print(dict(c)); [print(' ', r['status'], r['name'], r['url']) for r in rows if r['status']!='ok']; sys.exit(0 if rows and set(c)=={'ok'} else 1)" "$tmp"
    ;;
  teardown)
    az group delete -n "$RESOURCE_GROUP" --yes
    echo "teardown: $RESOURCE_GROUP deleted"
    ;;
  *)
    echo "usage: $0 [-e env] up|run|wait|status|logs|verify|teardown" >&2; exit 2
    ;;
esac
