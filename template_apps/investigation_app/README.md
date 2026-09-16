# CyberEye Investigation

Local historical-replay analyst app composed from [Agentcraft libraries](../../libraries/README.md).
It is not live monitoring or an autonomous response system. Existing Perth telemetry,
Cosmos graphs and MITRE knowledge are read in place; no dataset or application deployment
was copied or rewritten by this migration.

## What Exists

Three workspaces: Investigation, Data & Tools Catalogue, and Agent Editor. Application code
owns cyber-specific rules, ontology projections, prompts, citation/evidence policy,
authorization, HTTP/UI adaptation and authored Investigator versions.

Libraries own async ADX/graph access, bounded native model/tool execution, rule execution,
auth mechanisms, catalogue/previews, source viewing and SSE framing. `app/components` is
removed. [Shared](../shared/README.md) contains only local process supervision, with no
runtime dependencies. [Custom Optimizer](../custom_optimizer/README.md) remains independent
and imports the same public libraries; no app imports the other.

[Capability ownership](docs/ARCHITECTURE_OVERVIEW.md) and
[migration evidence](docs/LIBRARY_MIGRATION.md) identify every owner and verification command.

## Run

```bash
cd template_apps/investigation_app
./deploy/deploy.sh setup
./deploy/deploy.sh test
./deploy/deploy.sh local --source-root /home/hanchoong/perth_cyber --check
./deploy/deploy.sh local --source-root /home/hanchoong/perth_cyber
```

Default frontend: <http://127.0.0.1:5174>; API: <http://127.0.0.1:9011>.
Occupied ports select the next free port; use the URLs printed by the launcher.
The [local runbook](deploy/README.md) owns prerequisites and configuration.

```bash
./deploy/deploy.sh verify --scan --data
CYBEREYE_DATA_WORKFLOWS=1 ./deploy/deploy.sh browser-verify scanner
```

These explicit live-read checks use existing data and preserve auth. Inference now defaults
denied; only a separate operator grant may set `CYBEREYE_ALLOW_MODEL_CALLS=true`. Historical
23 API/72 browser results do not certify the migrated source. Current checks and blockers:
[B02/B03 record](../../libraries/azure-data-connectors/MIGRATION_B02_B03.md).

## Remaining Limits

- `llm_interface` owns real in-memory sessions and native run events. Chat sessions are
  owner-bound; interrupted or changed-definition sessions require explicit restart. Completed
  results are readable at `GET /api/sessions/{id}/result` by the same owner, without inference.
- Resource Explorer's parent-owned graph probe requires async contract adoption before
  whole-app acceptance. No legacy runtime is restored to hide that blocker.
- Deployed sign-in, replica isolation, new Azure provisioning, new data writes and registry
  publication are not certified by localhost checks. Ten ontology-product tests require
  source build products that were intentionally not imported or regenerated.
- The existing Perth ADX cluster is running with idle auto-stop disabled. Continuous compute
  charges apply; this does not prevent manual stops, external automation or platform outages.
  Its existing [deployment owner](../../deploy/README.md) retains lifecycle authority.

Private state and generated output stay ignored. [Provenance](PROVENANCE.md) retains original
snapshot hashes; historical receipts remain unchanged and do not certify new runtime bytes.