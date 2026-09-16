# Investigation Architecture

Current owner map, verified 2026-09-16. Application composition and domain policy depend on
public library contracts; libraries never import the application or its configuration.
The [manifest](../architecture.json) checks internal dependencies. Installed library imports
are external to that checker; library tests and artifact imports verify their independence.

## Capability Catalogue

| Outcome | Owner And Public Contract | Application Adaptation / State / Verification |
| --- | --- | --- |
| Perth telemetry | `libraries/azure-data-connectors`, `azdata.adx_read.AdxQueryClient`, `QueryRows`, `bind_parameters`, async `azdata.connect` | `backend/data/adx.py` owns allowed tables, query policy, evidence bounds and `QueryResponse`; ADX migration/replay tests, `verify --scan` |
| Existing Cosmos graph | `azdata.graph_read.GremlinReader`, `GraphReadConfig` | `backend/data/graph.py` owns ontology labels, window/selection rules and wire projections; identity injected from lifespan; graph tests and `verify --data` |
| Source inventory/previews | `libraries/resource-explorer`, `resource_explorer`, `.content`, `.probes`; `@agentcraft/resource-explorer` | Registry, exact source targets and graph account binding in `backend/inventory`; selection/refusal and inventory tests; real preview browser checks |
| MITRE retrieval | `libraries/search-read-adapter`, `search_read_adapter.SearchReadClient`, `.safe_key`, `.SearchError`; transport is `azdata` | `backend/knowledge` owns filters, document kinds and citation policy; knowledge/classification tests and keyed read-back |
| Rule execution | `libraries/situation-detector`, `situation_detector` | `backend/investigation` supplies queries, synthesis and scoring; detector tests and streamed Perth scan |
| Legacy model execution | `libraries/azure-llm-compat`, `AzureLlmClient`, `response_events`, `stream_tool_turn` | `backend/agents/service.py` supplies prompts, permitted tools, display metadata, diagnosis and evidence/citation validation; streaming/diagnosis/session tests, no live inference in this increment |
| Human token/sign-in primitives | `libraries/entra-auth`, `entra_auth` | `backend/security` owns principal, authorization, callbacks/cookies and record ownership; Entra and auth refusal tests |
| Signed caller verification | `libraries/signed-dev-access`, `signed_dev_access` | Host supplies public keys, replay ledger and authorization; replay/tamper/owner/refusal tests; deployed acceptance separate |
| Source viewing and SSE framing | `libraries/source-code`, `@agentcraft/source-code`; `libraries/event-stream`, `@agentcraft/event-stream` | Frontend callers supply text/streams; frontend unit/build and browser evidence; no application state in libraries |
| Investigator authoring | `backend/agents/library.py`, editor API/UI | Application-owned immutable versions and role assignment; authored state stays under `.local`; editor/ownership tests |
| Local launch | `template_apps/shared`, `template_foundations.local_server.serve` | Each `deploy/local.py` owns configuration and state; one process helper, zero runtime dependencies; launcher tests |
| Acceptance | `deploy/verify.py`, existing browser verifier | Calls public application read surfaces, never a runtime dependency; localhost only, explicit live-data options, no model calls or data writes |

## Boundaries

Composition root: `backend/main.py`. It borrows one Azure identity and injects it into data,
catalogue, graph and model clients. Shutdown closes owned clients before releasing identity,
including partial startup. HTTP adapters use the same domain services as non-browser callers.
Auth remains enabled through the existing local/deployed gates; no bypass was introduced.

`app/components` and its forwarding surfaces are removed. `template_apps/shared` contains
only standard-library local process supervision. Test-only MITRE document projection lives
under app tests; the unexposed publishing stack and duplicate Search/ARM transports are gone.
Loaded telemetry, graphs, indexes, authored agents and historical receipts were not changed.

The raw model compatibility package is deliberately separate from `llm_interface`: OpenAI
2.x versus 3.x dependencies, native Responses IDs, wire events and session retention are not
interchangeable. No fallback switch or raw escape hatch was added to the bounded interface.
Changing those contracts is not part of this data-workflow migration.

## Verification

`./deploy/deploy.sh test` runs backend/launcher, frontend unit and production build checks.
The final combined app/compatibility/consumer run passes 603 tests, with 10 pre-existing
ontology-product skips. Other extracted library tests pass 221; canonical data tests pass 190.
Architecture checks report no violations.

`./deploy/deploy.sh verify --scan --data` passes 23 real-data/API/refusal checks.
`CYBEREYE_DATA_WORKFLOWS=1 ./deploy/deploy.sh browser-verify scanner` passes 72 checks:
Perth scan/evidence, graph search/depth/zoom, and visible MITRE previews at 1440, 900 and 390px.
Automatic inference is blocked only by the verifier; the normal app behavior is unchanged.
Graph counts are 1,308 vertices/2,429 edges; MITRE contains 3,908 documents.

Current evidence, source measurements and deliberate limits:
[migration record](LIBRARY_MIGRATION.md). Earlier immutable artifact comparison:
[M1 continuation](../../../deploy/records/library-integration-continuation-20260915.md).
Current source checks do not retroactively certify those earlier wheel hashes.