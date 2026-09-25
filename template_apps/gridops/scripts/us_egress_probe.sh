#!/usr/bin/env bash
# Probe source URLs from a US Azure region: one-shot Container Instance, print logs, delete the probe resource group.
# Usage: scripts/us_egress_probe.sh [location]   (needs az login; uses the active subscription)
set -euo pipefail

location="${1:-eastus}"
rg="rg-gridops-egress-probe-${location}"
name="egress-probe"

urls=(
  "https://www.ercot.com/"
  "https://www.ercot.com/mp/data-products/data-product-details?id=NP4-160-SG"
  "https://www.ercot.com/mp/data-products/data-product-details?id=PG7-200-ER"
  "https://www.ercot.com/gridinfo/transmission"
  "https://www.ercot.com/gridinfo/resource"
  "https://www.ercot.com/gridinfo/generation"
  "https://www.ercot.com/committees/ros/pdcwg"
  "https://www.ercot.com/services/comm/mkt_notices/opsmessages"
  "https://www.ercot.com/mktrules/guides/procedures"
  "https://www.ercot.com/mktrules/nprotocols"
  "https://www.ercot.com/mktrules/guides/noperating"
  "https://www.ercot.com/mktrules/guides/planning"
  "https://www.ercot.com/news/february2021"
  "https://apiexplorer.ercot.com/"
  "https://api.ercot.com/api/public-reports"
  "https://www.ferc.gov/media/february-2021-cold-weather-outages-texas-and-south-central-united-states-ferc-nerc-and"
  "https://www.puc.texas.gov/"
  "https://hifld-geoplatform.hub.arcgis.com/"
)

script='curl -s -m 15 https://ipinfo.io/json | grep -E "\"(country|region|org)\""; ua="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36"; for u in "$@"; do printf "%s %s\n" "$(curl -sL -o /tmp/b -m 25 -A "$ua" -w "%{http_code}" "$u")" "$u"; grep -o "<title>[^<]*" /tmp/b | head -1 | sed "s/^/    /"; grep -q "_Incapsula_Resource\|Attention Required" /tmp/b && echo "    BLOCK_PAGE"; done; echo PROBE_DONE'

az group create -n "$rg" -l "$location" --tags purpose=gridops-egress-probe ephemeral=true -o none
trap 'az group delete -n "$rg" --yes --no-wait' EXIT

az container create -g "$rg" -n "$name" -l "$location" \
  --image mcr.microsoft.com/azure-cli:latest --os-type Linux --cpu 1 --memory 1 \
  --restart-policy Never \
  --command-line "bash -c '$script' probe ${urls[*]}" -o none

for _ in $(seq 1 60); do
  state=$(az container show -g "$rg" -n "$name" --query "containers[0].instanceView.currentState.state" -o tsv 2>/dev/null || true)
  [[ "$state" == "Terminated" ]] && break
  sleep 5
done
az container logs -g "$rg" -n "$name"
