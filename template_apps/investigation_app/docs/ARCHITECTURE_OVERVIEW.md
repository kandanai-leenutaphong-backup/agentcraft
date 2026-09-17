# Investigation Architecture

Current owner map, source-checked 2026-09-17. Application composition and domain policy depend on
public library contracts; libraries never import the application or its configuration.
The [manifest](../architecture.json) checks internal dependencies. Installed library imports
are external to that checker; library tests and artifact imports verify their independence.

## Capability Catalogue

| Outcome | Owner And Public Contract | Application Adaptation / State / Verification |
| --- | --- | --- |
| Perth telemetry | [azdata contract](../../../libraries/azure-data-connectors/CONTRACT.md) | [ReadOnlyAdx](../app/cybereye/backend/data/adx.py) owns table guard and evidence bounds. Native content enters domain calculations; [tool envelopes](../app/cybereye/backend/agents/tools/base.py) serialize at the model boundary. |
| Existing Cosmos graph | Async `azdata` Gremlin `readonly_key` profile; public `resource_explorer.GraphInspection`, `graph_properties` and `ResultCache` | [Graph binding](../app/cybereye/backend/data/graph_binding.py) owns exact-account read-only-key lookup; [graph service](../app/cybereye/backend/data/graph.py) owns ontology/window/selection and cache keys. Generic inspection and caching have library owners. |
| Source inventory/previews | [resource_explorer](../../../libraries/resource-explorer/README.md), public probes and React explorer | [Inventory composition](../app/cybereye/backend/inventory/probes.py) injects async graph service, registry and credentials. No removed sync graph runtime is required. |
| MITRE retrieval | Public async `azdata` query/read | [Knowledge](../app/cybereye/backend/knowledge) owns fixed index, document keys, advisory filters/citations and attempt reporting. |
| Connector-operation accounting | Public `azdata.OperationMetrics` | [ADX](../app/cybereye/backend/data/adx.py), [knowledge](../app/cybereye/backend/knowledge/search.py) and [resource probes](../../../libraries/resource-explorer/src/resource_explorer/probes.py) share submitted/completed/known-attempt/unknown-outcome mechanics; hosts retain reporting fields. Metrics observe operations, not authorize them. |
| Rule execution | [situation_detector](../../../libraries/situation-detector/README.md) | [Investigation](../app/cybereye/backend/investigation) supplies queries, synthesis and scoring. [UI scan handling](../app/cybereye/frontend/src/app/App.tsx) selects only completed scan output. |
| Model execution | [llm_interface](../../../libraries/llm-interface/CONTRACT.md), native Agent Framework | [Agent service](../app/cybereye/backend/agents/service.py) supplies grants, schemas, tool authorization, owner-bound sessions and one RunEvent presentation adapter. |
| Strict roster/prompt loading | [agentconfig](../../../libraries/modular-agents/modules/agent-config-build/CONTRACT.md), `resolve_tool`, `tool` and `tool_metadata` | [App configuration](../app/cybereye/backend/agents/config.py) calls `load_agent_config` and `load_instructions` with `strict=True`; app owns local-only references, model/tool allowlists and cyber-specific constraints. [Tool metadata](../app/cybereye/backend/agents/tools/base.py) retains typed domain validation. |
| Human and signed caller evidence | [entra_auth](../../../libraries/entra-auth/README.md), public `SessionService`; [signed_dev_access](../../../libraries/signed-dev-access/README.md) | [Security](../app/cybereye/backend/security) retains Principal mapping, authorization, cookie/session policy, replay scope and record ownership; the library coordinates generic flow/session records. Deployed acceptance is separate. |
| Result/source presentation | [modular renderers](../../../libraries/modular-agents/modules/purpose-built-tools/renderers/README.md): `ResultTable`, `ToolResultCard`, canonical error/refusal/duplicate extractors and `projectObjectRow`; [SourceCodeViewer](../../../libraries/source-code/README.md) | [ToolRender](../app/cybereye/frontend/src/shared/agent-output/ToolRender.tsx), [ToolArguments](../app/cybereye/frontend/src/shared/agent-output/ToolArguments.tsx) and [ToolBoard](../app/cybereye/frontend/src/features/investigation/ToolBoard.tsx) retain domain labels, value formatting, arguments and evidence limits. Generic card structure supports plain CSS and host header/band options. |
| SSE framing | [event-stream](../../../libraries/event-stream/README.md) | [Frontend API](../app/cybereye/frontend/src/shared/api/api.ts) owns HTTP, authorization and event meaning. |
| Investigator authoring | Public `agentconfig.AgentVersionStore` and authoring schemas; [app policy adapter](../app/cybereye/backend/agents/library.py), editor API/UI | Library owns version storage and revision-checked assignment; app retains owner authorization, model/tool allowlists and Investigator eligibility. Persistent authored state is separate from fixture output. |
| Local launch | [Shared supervisor](../../shared/README.md), `template_foundations.local_server.serve` | [Local launcher](../deploy/local.py) owns configuration and process groups. |
| Historical ontology build | [App ontology](../app/data/ontology/__init__.py), `build_graph`, `read_graph`, `write_graph` | Canonicalization, export-family extraction, relationship vocabulary and replay buckets remain domain-owned; generic live graph inspection is not an ontology builder. |
| Acceptance | [API verifier](../deploy/verify.py), [native browser verifier](../app/cybereye/frontend/tests/browser/verify-native-investigation.mjs) | [Runbook](../deploy/README.md) separates synthetic native services from explicitly authorized live reads/inference. |

## Boundaries

Composition root: [main.py](../app/cybereye/backend/main.py). It borrows one Azure identity and injects it into data,
catalogue, graph and model clients. Shutdown closes owned clients before releasing identity,
including partial startup. HTTP adapters use the same domain services as non-browser callers.
Auth remains enabled through the existing local/deployed gates; no bypass was introduced.

`app/components` and its forwarding surfaces are removed. `template_apps/shared` contains
only standard-library local process supervision. Test-only MITRE document projection lives
under app tests; the unexposed publishing stack and duplicate Search/ARM transports are gone.
Loaded telemetry, graphs, indexes, authored agents and historical receipts were not changed.

Raw model and synchronous Search distributions are retired. Local inference defaults denied;
`local --allow-model-calls` needs separate explicit
authorization. Changed/interrupted sessions never replay implicitly. Completed results are
owner-readable at `GET /api/sessions/{id}/result` without another model request.

## Current Verification

[Generic reuse audit](LIBRARY_MIGRATION.md#generic-reuse-audit) owns current candidate decisions,
coverage and pending integrated checks. Library extensions are implemented in source, not
new packages or restored retired capabilities. Local `useHeightDrag` and native event dispatch
remain presentation adaptations; native synchronous tool dispatch remains with `llm_interface`.

[Earlier split acceptance](LIBRARY_MIGRATION.md#current-acceptance) retains its counts, exact browser
receipt and ontology input checks; those observations do not certify the subsequent reuse edits.
The offline ASGI/browser composition
uses production routes and real native SDK parsing with synthetic service fixtures;
test-owned lifecycle does not verify the production `lifespan` above. Historical source,
wheel and live-data observations stay in that record and do not certify current bytes.