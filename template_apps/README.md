# Template Applications

## Separate Applications

- [Investigation](investigation_app/README.md): scanner, evidence, graph, chat, catalogue and
	Agent Editor. No Agent Optimization tab, API, GUIDE dependency or terminal remains.
- [Custom Optimizer](custom_optimizer/README.md): standalone GUIDE experiments, detector/tools,
	version history, metrics/replays and native Copilot CLI. No ADX or Investigation server needed.
- [Shared foundations](shared/README.md): one retained rule battery, model/Search clients,
	source viewer and local process launcher used through explicit package/alias contracts.

Current local URLs: Investigation <http://127.0.0.1:5175>, Custom Optimizer
<http://127.0.0.1:5180>. Each app has its own uv/npm environment and deployment entry point.
The existing three-version experiment and private CLI workspaces moved with hash verification:
67 optimizer files and 239 workspace files, unchanged bytes. Authored Investigator agents remain
in Investigation. Original source project and cloud deployment were not changed for this split.

Both apps' backend/frontend tests and builds pass. Browser checks exercise the two separate
surfaces and saved history at desktop/mobile widths; actual sandbox positive/refusal tests pass.
No new model campaign was run for the separation. See each app's runbook for precise commands.

## Investigation App

[CyberEye](investigation_app/README.md) is a local copy of the historical cybersecurity
replay application used for gradual adoption of [Agentcraft libraries](../libraries/README.md).
Template source is eligible for version control; private state and generated output remain
ignored. Version control does not authorize external publication of source-project code,
third-party assets, private data or deployment coordinates.

First increment replaces scanner/evidence/tool ADX transport with canonical `azdata` 4.0.0a3
through a temporary synchronous adapter. Source project and shared deployment are unchanged.
Search, model/agent orchestration, graph, authentication and optimization remain retained
components, with explicit next checks in the template's migration catalogue.

Observed 2026-09-15: 505 application tests, 7 launcher tests, frontend tests/typecheck/build,
21 editor browser checks and 14 local API/GUIDE checks passed. The architecture check reported
no violations. Twenty-two application tests require absent ontology or sandbox prerequisites.
Live ADX scan was attempted but the shared cluster is stopped; successful scan/evidence parity
is not established. No model run, deployment or cloud mutation occurred.

Use the template's [local runbook](investigation_app/deploy/README.md) and single
[entry point](investigation_app/deploy/deploy.sh). Copied data is not required: existing GUIDE
inputs can be read in place, while all new writable state stays inside the template.