# CyberEye Investigation

Local historical-replay analyst app composed from [Agentcraft libraries](../../libraries/README.md).
It is not live monitoring or an autonomous response system. Existing Perth telemetry,
Cosmos graphs and MITRE knowledge are read in place; no dataset or application deployment
was copied or rewritten by this migration.

## What Exists

Three workspaces: Investigation, Data & Tools Catalogue, and Agent Editor. Application code
owns cyber-specific rules, ontology projections, prompts, citation/evidence policy,
authorization, HTTP/UI adaptation and authored Investigator versions.

Libraries own ADX/graph access, model client/tool iteration compatibility, rule execution,
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

These explicit live-read checks use existing data, preserve auth, and block automatic model
inference in the browser verifier. They do not change the normal application's model behavior.
Current acceptance: 23 API checks and 72 browser checks at 1440/900/390px; Perth scan returns
two situations and evidence, graph navigation reads 1,308 vertices/2,429 edges, and MITRE
previews/keyed citations read the existing 3,908-document index.

## Remaining Limits

- Raw Responses compatibility remains a separate library because `llm_interface` has
  different dependency, event and session contracts. No live model calls were made here.
- Deployed sign-in, replica isolation, new Azure provisioning, new data writes and registry
  publication are not certified by localhost checks. Ten ontology-product tests require
  source build products that were intentionally not imported or regenerated.
- The existing Perth ADX cluster is running with idle auto-stop disabled. Continuous compute
  charges apply; this does not prevent manual stops, external automation or platform outages.
  Its existing [deployment owner](../../deploy/README.md) retains lifecycle authority.

Private state and generated output stay ignored. [Provenance](PROVENANCE.md) retains original
snapshot hashes; historical receipts remain unchanged. Current runtime source is 114 files/
719,915 logical bytes, down from 190 files/1,236,667 bytes before consolidation.