# Template Applications

## Separate Applications

- [Investigation](investigation_app/README.md): scanner, evidence, graph, chat, catalogue and
	Agent Editor. No Agent Optimization tab, API, GUIDE dependency or terminal remains.
- [Custom Optimizer](custom_optimizer/README.md): standalone GUIDE experiments, detector/tools,
	version history, metrics/replays and native Copilot CLI. No ADX or Investigation server needed.
- [Shared foundations](shared/README.md): one retained rule battery, model/Search clients,
	source viewer and local process launcher used through explicit package/alias contracts.

Recorded local URLs: Investigation <http://127.0.0.1:5175>, Custom Optimizer
<http://127.0.0.1:5180>. Each app has its own uv/npm environment and deployment entry point.
The existing three-version experiment and private CLI workspaces moved with hash verification:
67 optimizer files and 239 workspace files, unchanged bytes. Authored Investigator agents remain
in Investigation. Original source project and cloud deployment were not changed for this split.

Historical separation acceptance: both apps' backend/frontend tests and builds passed. Browser checks exercised the two separate
surfaces and saved history at desktop/mobile widths; actual sandbox positive/refusal tests pass.
No new model campaign was run for the separation. See each app's runbook for precise commands.
These records are not fresh acceptance of the library/skill split. Custom Optimizer
was not changed or executed for this documentation update.

## Investigation App

[CyberEye](investigation_app/README.md) is a local copy of the historical cybersecurity
replay application used for gradual adoption of [Agentcraft libraries](../libraries/README.md).
Template source is eligible for version control; private state and generated output remain
ignored. Version control does not authorize external publication of source-project code,
third-party assets, private data or deployment coordinates.

Investigation now composes ten retained library owners through their public contracts;
the [workspace guide](../libraries/README.md#current-state) records eight Python members
and four npm packages. Eleven unused library owners moved into skills and twelve duplicate
skill directories are removed. The [migration record](investigation_app/docs/LIBRARY_MIGRATION.md#current-acceptance)
owns recorded native-library acceptance and remaining limits. Parent split acceptance
and generated-guidance refresh remain pending; no whole-project size or RAM gain is claimed.

Historical observation, 2026-09-15: 505 application tests, 7 launcher tests, frontend tests/typecheck/build,
21 editor browser checks and 14 local API/GUIDE checks passed. The architecture check reported
no violations. Twenty-two application tests require absent ontology or sandbox prerequisites.
Live ADX scan was attempted but the shared cluster is stopped; successful scan/evidence parity
is not established. No model run, deployment or cloud mutation occurred.

Use the template's [local runbook](investigation_app/deploy/README.md) and single
[entry point](investigation_app/deploy/deploy.sh). Copied data is not required: existing GUIDE
inputs can be read in place, while all new writable state stays inside the template.