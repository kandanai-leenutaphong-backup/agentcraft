# CyberEye Investigation

Local copy of the historical replay analyst application, gradually replacing retained
components with canonical [Agentcraft libraries](../../libraries/README.md). It is not
live monitoring or an autonomous response system. Source project and cloud deployment stay unchanged.

## First Increment

- CyberEye's scanner, evidence tools and query API now use `azdata` 4.0.0a3 for ADX transport.
- `ReadOnlyAdx` keeps application table restrictions and the existing `QueryResponse` shape.
  A temporary synchronous adapter supplies typed parameter declarations, one event loop,
  bounded concurrency, status-to-exception mapping and explicit shutdown.
- Python dependencies resolve in this template's own uv environment, with a declared editable
  dependency on the canonical library. No source-project code or dependency directory is imported.
- Existing authentication, frontend, model orchestration, Search, graph, catalogue and
  agent editing remain. Agent Optimization moved to [Custom Optimizer](../custom_optimizer/README.md).
  [Migration map](docs/ARCHITECTURE_OVERVIEW.md) owns current component status.

## Optimizer Separation

Investigation now has three workspaces: Investigation, Data & Tools Catalogue, and Agent
Editor. Optimizer routes return 404; no optimizer service, GUIDE source, terminal, or
experimental-agent link is composed. Existing authored Investigator agents remain here.

Custom Optimizer independently owns the previous experiment history, GUIDE adapters, workflow
and native terminal. Shared foundations live once in [the shared package](../shared/README.md);
neither app imports the other. Both local Python and frontend builds are independent.

Separation checks: 472 Investigation tests passed, 10 ontology-product tests skipped;
standalone optimizer and real sandbox tests pass. Browser read-back at 1440/390 px verifies
saved generations in the new app and only the three remaining Investigation tabs. The local
API checks also prove optimizer absence, GUIDE absence and the unchanged access refusals.

## Run And Verify

```bash
cd template_apps/investigation_app
./deploy/deploy.sh setup
./deploy/deploy.sh test
./deploy/deploy.sh local --source-root /home/hanchoong/perth_cyber --check
./deploy/deploy.sh local --source-root /home/hanchoong/perth_cyber
```

Default frontend: <http://127.0.0.1:5174>; API: <http://127.0.0.1:9011>.
This session is running Investigation at <http://127.0.0.1:5175> and Custom Optimizer at
<http://127.0.0.1:5180>.
Occupied ports select the next free port; use the URLs printed by the launcher.
The [local runbook](deploy/README.md) owns prerequisites, verification and failures.

## Earlier Migration Evidence

- 505 application tests passed; 22 skipped for absent ontology products or sandbox setup.
- Seven launcher isolation/refusal tests passed. Frontend unit tests and typecheck/build passed.
- Existing editor browser journey passed 21 checks at 1440, 900, 390 and 320 px:
  tool inspection, draft recovery, immutable saves, reload, assignment and responsive geometry.
- Migration exposed and fixed two library transport defects: missing Azure Core bearer policy
  and duplicate aiohttp redirect options. The library's 126-test suite passes.
- Live ADX scan returned 502; independent ARM read on 2026-09-15 found the existing cluster
  `Stopped`. Corrected health endpoint reports `200/degraded`. Successful scan/evidence parity
  remains unverified until an authorized operator starts the cluster.
- No model inference, optimization campaign, container build, cloud write, access grant,
  deployment update, or source-project edit was performed.

Template source is eligible for version control; private state and generated output remain ignored. Data,
credentials, saved source state and deployment scripts were not copied. Investigation owns
its authored agents; GUIDE, experiments and terminal workspaces now belong to Custom Optimizer.
[Provenance](PROVENANCE.md) records original hashes and snapshot exclusions. Distribution and
third-party rights need review before this local copy becomes a published template.