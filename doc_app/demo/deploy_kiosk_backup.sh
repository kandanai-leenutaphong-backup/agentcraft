#!/usr/bin/env bash
# ============================================================================
# deploy_kiosk_backup.sh — Build + deploy the kiosk to the BACKUP MIRROR.
# ============================================================================
#
# Module role:
#   Emergency-failover deploy target. Identical pipeline to
#   deploy_kiosk.sh but points at the gridiq-v2 Container App, which is
#   provisioned in the same Container App Environment as gridiq-v2 and
#   pulls from the same ACR. URL:
#     https://gridiq-v2.nicesmoke-72d7e88d.australiaeast.azurecontainerapps.io
#
# Replica policy:
#   min=2 / max=3. Slightly tighter ceiling than the primary (max 5)
#   because the backup is for redundancy, not load-shedding.
#
# Usage:
#   ./deploy_kiosk_backup.sh --yes
#   ./deploy_kiosk_backup.sh --tag kiosk-20260421-203131    # mirror an
#                                                            # existing
#                                                            # primary tag
#                                                            # without
#                                                            # rebuilding
#
# Implementation:
#   This is a thin wrapper around deploy_kiosk.sh. It just forces
#   --app-name gridiq-v2 and overrides the scale-rule min/max via a
#   post-step. Keeping the build/push pipeline in one place (the
#   primary script) means we never drift between the two.
# ============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Forward all caller args, plus pin the app name to the backup mirror.
"$SCRIPT_DIR/deploy_kiosk.sh" --app-name gridiq-v2 "$@"

# Re-apply the backup-specific scale config. deploy_kiosk.sh hard-codes
# min=2/max=5 for the primary; the backup runs tighter at 2/3 since
# its job is redundancy not burst capacity.
source "$SCRIPT_DIR/azure_config.env"
echo ""
echo "━━━ Re-pinning backup scale to min=2 max=3 ━━━"
az containerapp update \
  --name gridiq-v2 \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --min-replicas 2 \
  --max-replicas 3 \
  --scale-rule-name http-concurrency \
  --scale-rule-type http \
  --scale-rule-http-concurrency 30 \
  --output none
echo "✓  Backup mirror scale: 2 warm, burst to 3"
echo "  URL: https://gridiq-v2.nicesmoke-72d7e88d.australiaeast.azurecontainerapps.io"
