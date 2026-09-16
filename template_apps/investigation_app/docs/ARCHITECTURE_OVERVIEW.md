# Investigation Architecture

Current owner map, verified 2026-09-16. Application composition and domain policy depend on
public library contracts; libraries never import the application or its configuration.
The [manifest](../architecture.json) checks internal dependencies. Installed library imports
are external to that checker; library tests and artifact imports verify their independence.

## Capability Catalogue

| Outcome | Owner And Public Contract | Application Adaptation / State / Verification |
| --- | --- | --- |
| Perth telemetry | `azdata.connect`, `QueryRequest`, native Kusto parameters and `OperationResult` | Async `backend/data/adx.py` owns table guard, evidence bounds and wire projection; ADX/replay tests, `verify --scan` |
| Existing Cosmos graph | Async `azdata` Gremlin `readonly_key` profile | Host `data/graph_binding.py` binds exact-account native read-only-key lookup; graph service owns ontology/window/selection; no library key discovery |
| Source inventory/previews | `libraries/resource-explorer`, `resource_explorer`, `.content`, `.probes`; `@agentcraft/resource-explorer` | Registry, exact source targets and graph account binding in `backend/inventory`; selection/refusal and inventory tests; real preview browser checks |
| MITRE retrieval | Public async `azdata` query/read | `backend/knowledge` owns fixed index, unchanged document keys, advisory filters/citations and attempt accounting; no sync facade |
| Rule execution | `libraries/situation-detector`, `situation_detector` | `backend/investigation` supplies queries, synthesis and scoring; detector tests and streamed Perth scan |
| Model execution | `llm_interface`, native Agent Framework | Host supplies explicit grants, exact tool schemas/authorizer, actual owner-bound sessions and one RunEvent presentation adapter; no second loop/provider continuation |
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

Raw model and synchronous Search distributions are retired. Both app locks select OpenAI
3.13.x. Local inference defaults denied; `local --allow-model-calls` needs separate explicit
authorization. Changed/interrupted sessions never replay implicitly. Completed results are
owner-readable at `GET /api/sessions/{id}/result` without another model request.

## Current Verification

[B02/B03 record](../../../libraries/azure-data-connectors/MIGRATION_B02_B03.md) owns current
checks, artifacts, dependencies and blockers. Parent-owned Resource Explorer still imports
the removed graph runtime and expects sync graph methods. Clean startup/full Investigation
API/browser acceptance are blocked until that owner is migrated.

## Historical Verification

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