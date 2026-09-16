# Optimizer Ownership

Separate local application, not an embedded Investigation tab and not an import of that app.
The Python namespace `app.cybereye` is retained inside this independent process for compatibility.
Each app has its own uv project, node_modules, API origin, startup and writable state.

| Outcome | Owner And Surface | Callers / Verification |
| --- | --- | --- |
| Experiment lifecycle, generation ledger, probes and grading | `agent_optimization`, `@agentcraft/agent-optimization` | Host service and workspace use canonical packages |
| GUIDE labels, dataset, baseline and model task | `app/cybereye/backend/optimization` | Injected into workflow; dataset/grade/refusal tests |
| Bounded Python evidence queries | `agent_optimization.SQLiteReader`, `PythonToolRunner` | GUIDE adapter; real Bubblewrap/libseccomp positive and refusal tests |
| Native CLI session and workspace | `copilot_terminal`, `copilot-terminal` | Canonical workflow composes terminal; host owns authorization/settings |
| HTTP API, local identity and authorization | `backend/main.py`, `api/optimization.py`, `security` | Loopback peer/Host/Origin required before routing; standalone positive/refusal tests |
| Advisory knowledge and discovery | `backend/knowledge.py`, `Knowledge.search`, `describe_capabilities` | Injected callbacks; only GUIDE evidence/profiles, evaluator-only labels and optional MITRE knowledge |
| UI composition | `frontend/src/main.tsx` | Full-screen `OptimizationWorkspace`; build and desktop/mobile browser read-back |
| Startup and state handoff | `deploy/local.py`, `deploy/migrate_state.py`, `deploy/deploy.sh` | Allowlisted inputs, fixed state root, idle-only non-overwriting transfer and hash read-back |
| Ordered rule battery | `libraries/situation-detector`, public `situation_detector` | Optimizer joint evaluation and dataset normalization; existing rule/refusal tests |
| Source viewer | `libraries/source-code`, `@agentcraft/source-code` | Detector, replay and version panes; same React/Shiki contracts, build and unit checks |
| Model execution and Search reads | `llm_interface`, async `azdata` | Explicit borrowed identity/grants; native owner-bound sessions/terminal receipts; worker callbacks schedule onto the host loop |
| Local process lifetime | `../shared`, `template_foundations.local_server` | Host-owned settings/state passed to common loopback supervision |

Dependencies run from composition to adapters to workflow/shared foundations. The moved workflow
does not import either application's composition. Configuration and credentials enter at the host.
No ADX or Gremlin client, scanner, chat service, agent editor or Investigator role is constructed.

## Move Map

From `investigation_app` to this app, preserving workflow code and API names:

- `app/components/{agent_optimization,local_query,copilot_terminal}` and their focused tests.
- `app/cybereye/backend/optimization` and `backend/api/optimization.py`.
- Optimization frontend unit checks and their support fixtures; standalone browser checks replace
  the combined-app journey, whose original remains in the ignored rollback snapshot.
- `.local/optimization` and `.local/copilot-workspaces`, after source shutdown and idle read-back.

To the one shared owner, with consumers changed together:
`situation_detector`, `azure_llm`, `azure_search`, `source_code`, and local process supervision.
Original source copies were retired from Investigation, not left as alternate imports.

Investigation lost the optimizer tab, route, startup, settings, experimental-agent links,
GUIDE catalogue slots and optimizer-only tests. Its scanner keeps using the shared rule battery.
Its authored Investigator agents and source project `/home/hanchoong/perth_cyber` were not moved.

## Evidence And Limits

Current B02/B03 evidence: [migration record](../../../libraries/azure-data-connectors/MIGRATION_B02_B03.md).
Earlier state-transfer observations below remain historical. No source campaign was rerun.

Existing experiment: three saved versions, all measured stages completed, original `ready`
experiment status preserved. State move verified 67 optimizer and 239 CLI workspace files by
hash; startup read-back reproduced those bytes. No scores or immutable inputs were changed.
New host knowledge/capability context is not claimed identical to historical context. Saved
records remain inspectable; compatibility checks are not bypassed to permit remeasurement.

Source-only graph checks found no declared violations. The checker also scans retained ignored
CLI caches in `.local`: optimizer output reported 70 unresolved imports and 120 unowned files.
Those are disclosed, not proof of resolution. Shared foundation and Investigation checks report
no violations or unresolved notes. Package install/build and actual browser/API checks cover the
new shared dependency; a checker treating a package as external alone would not prove reuse.

No new model campaign or deployment acceptance was performed for the separation. The original
source project and cloud resource configuration remain outside this change.