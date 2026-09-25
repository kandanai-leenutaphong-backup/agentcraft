#!/usr/bin/env bash
# Runs inside the container: fetch every source in sources.txt, upload to blob, write a provenance log.
set -uo pipefail
: "${STORAGE_ACCOUNT:?}" "${CONTAINER:?}"

run=$(date -u +%Y%m%dT%H%M%SZ)
day=${run%%T*}
ua="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36 public-data-retriever"
log=/tmp/run.jsonl
dl=/tmp/dl
mkdir -p "$dl"
: > "$log"
failed=0

blob_put() { # file blob
  az storage blob upload --auth-mode login --account-name "$STORAGE_ACCOUNT" -c "$CONTAINER" \
    -f "$1" -n "$2" --overwrite -o none --only-show-errors
}

record() { # name url status [blob file]
  local sha="" bytes=0
  [[ -n "${5:-}" ]] && sha=$(sha256sum "$5" | cut -d' ' -f1) && bytes=$(stat -c%s "$5")
  jq -nc --arg name "$1" --arg url "$2" --arg status "$3" --arg blob "${4:-}" --arg sha256 "$sha" \
    --argjson bytes "$bytes" --arg at "$(date -u +%FT%TZ)" \
    '{name:$name,url:$url,status:$status,blob:$blob,sha256:$sha256,bytes:$bytes,fetched_at:$at}' >> "$log"
  [[ "$3" == ok ]] || failed=1
  echo "$3 $1 ${4:-$2}"
}

fetch() { # name url filename
  local file="$dl/$3" blob="$1/$day/$3" code
  code=$(curl -sSL -A "$ua" -m 900 -o "$file" -w '%{http_code}' "$2") || code=000
  if [[ "$code" != 200 ]]; then record "$1" "$2" "http_$code"
  elif blob_put "$file" "$blob"; then record "$1" "$2" ok "$blob" "$file"
  else record "$1" "$2" upload_failed "$blob" "$file"
  fi
  rm -f "$file"
}

ercot_mis() { # name reportTypeId count
  local list="https://www.ercot.com/misapp/servlets/IceDocListJsonWS?reportTypeId=$2" code
  code=$(curl -sSL -A "$ua" -m 120 -o "$dl/listing.json" -w '%{http_code}' "$list") || code=000
  [[ "$code" == 200 ]] || { record "$1" "$list" "http_$code"; return; }
  if blob_put "$dl/listing.json" "$1/$day/listing.json"; then
    record "$1" "$list" ok "$1/$day/listing.json" "$dl/listing.json"
  else record "$1" "$list" upload_failed; return
  fi
  # assumes: MIS lists documents newest first
  while read -r -u 4 id cname; do
    fetch "$1" "https://www.ercot.com/misdownload/servlets/mirDownload?doclookupId=$id" "$cname"
  done 4< <(jq -r --argjson n "$3" '.ListDocsByRptTypeRes.DocumentList[:$n][] | .Document | "\(.DocID) \(.ConstructedName // .FriendlyName)"' "$dl/listing.json")
}

while read -r -u 3 name kind target extra; do
  [[ -z "${name:-}" || "$name" == \#* ]] && continue
  case "$kind" in
    url) fetch "$name" "$target" "${extra:-$(basename "${target%%\?*}")}" ;;
    ercot-mis) ercot_mis "$name" "$target" "${extra:-1}" ;;
    *) record "$name" "$target" "unknown_kind_$kind" ;;
  esac
done 3< /tmp/sources.txt

blob_put "$log" "_runs/$run.jsonl" || failed=1
echo "RUN $run failed=$failed"
exit "$failed"
