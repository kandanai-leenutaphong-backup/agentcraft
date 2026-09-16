# Custom Optimizer

Standalone local GUIDE agent-optimization workspace, separated from CyberEye Investigation.
Opens directly into Dataset, Tools, Agents and Performance. The existing detector, immutable
generations, scoring, saved replays, Python sandbox and native Copilot terminal stay together.

## Run

```bash
cd template_apps/custom_optimizer
./deploy/deploy.sh setup
./deploy/deploy.sh local --source-root /home/hanchoong/perth_cyber --check
./deploy/deploy.sh local --source-root /home/hanchoong/perth_cyber
```

Default frontend: <http://127.0.0.1:5180>. API: <http://127.0.0.1:9012>.
Occupied ports advance to the next free port; use the printed URLs. Python/npm environments
are independent of Investigation. No ADX, graph, chat, scanner or Investigator assignment is
composed. [Local runbook](deploy/README.md) owns configuration, checks and state transfer.

GUIDE inputs remain read-only in their existing location. Model and optional MITRE Search
settings are explicit non-secret inputs; credentials stay in the operator's credential store.
Loopback peer, Host and Origin checks protect every route. This is not a multi-user cloud host.

## Preserved State

The existing three-version experiment and private CLI workspaces moved from Investigation:
67 optimizer files and 239 workspace files passed pre/post hash comparison. No record bytes,
scores, prompts, cohorts or statuses were rewritten. All three versions retain completed
training/evaluation stages; the experiment retains its original `ready` status.

Historical replays remain readable. New measurements use the standalone host's own capability
catalogue and MITRE adapter; old input/reference pins are not rewritten to permit resumption
under changed assumptions. Start a new experiment for standalone-host measurements. Old CLI
workspaces remain evidence, not live sessions; a new terminal receives the new API origin.

## Current Migration

Model calls use bounded `llm_interface` native agents with explicit identity, local-operator
session ownership and native run receipts. Inference defaults denied until an operator
separately grants `CYBEREYE_ALLOW_MODEL_CALLS=true`. MITRE reads await public `azdata`.
The raw-model and synchronous Search distributions are retired, with OpenAI 3.13.x selected.
Existing worker callbacks schedule onto the host loop; no library sync runtime is added.
Canonical optimization/recovery/terminal packages own their respective mechanisms.
Current checks and integration limits: [B02/B03 record](../../libraries/azure-data-connectors/MIGRATION_B02_B03.md).

## Historical Verification

Optimizer verification passes 177 Python tests with the real sandbox configured, 21 frontend
unit tests, and its production build. Investigation passes 472 Python tests (10 ontology-input
skips), its remaining frontend tests and build. Browser checks at 1440 and 390 px verify saved-generation
read-back, protocol controls, native CLI availability, bounded layout, and removal of the
optimizer from Investigation. The moved sandbox tests execute real isolated Python and refuse
filesystem/credential/label/network/process escapes. No new paid model campaign was run for
this separation. [Architecture and move map](docs/ARCHITECTURE_OVERVIEW.md) records owners.

Internal `app.cybereye` import names and `/api/cyber/optimization` URLs are retained to avoid
unnecessary churn. They do not import or connect to the Investigation application. Shared
rule execution imports `situation_detector` from `libraries/situation-detector`; source
viewing imports `@agentcraft/source-code` from `libraries/source-code`. Retained model/Search
execution now follows the canonical contracts; process supervision remains in
[the sibling package](../shared/README.md). Historical test counts above do not certify new source.