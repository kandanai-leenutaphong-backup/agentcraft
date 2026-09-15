# Template Architecture And Migration

## Current Separation

Agent Optimization is now a separate [Custom Optimizer app](../../custom_optimizer/README.md).
It owns the workflow, GUIDE dataset/labels, terminal, routes, tests and moved experimental state.
Investigation composes only investigation, catalogue and agent editor. Its optimizer endpoints
are absent and its inventory contains Perth, AIT and MITRE only.

The shared rule battery, model/Search clients and source viewer moved to
[template foundations](../../shared/README.md); both apps install that one owner. Local
process supervision is shared, while each launcher owns its settings and state. No app imports
the other. Current manifests describe the remaining internal boundaries; installed foundations
remain external package dependencies. The historical migration catalogue below predates this
split and is retained as the initial ADX-integration record, not current placement authority.

Verification: Investigation backend/launcher 472 passed, 10 prerequisite skips; frontend unit
checks/build pass. Browser separation and local API refusal/read-back checks pass. Existing
optimizer records moved byte-for-byte; its new host tests/build and real sandbox checks pass.
No new model campaign or cloud mutation was part of the separation.

## Initial Migration

Current owner and migration catalogue for the local CyberEye copy. Root
[architecture.json](../architecture.json) declares internal dependencies. Installed `azdata`
is an external public package to this checker; [pyproject.toml](../pyproject.toml) declares its
canonical development source. Library tests independently forbid imports of template code.

Direction: application composition -> HTTP adapters -> domain services/tools -> public library
or retained component. Frontend app -> features -> shared; components never import CyberEye.
Local operations select configuration and launch processes; they do not import application code.

| Capability / Status | Owner, Sources And Public Contract | Callers, Policy And Verification |
| --- | --- | --- |
| Telemetry query / migrating | `libraries/azure-data-connectors`, `azdata.connect` and `QueryRequest`; template `backend/data/azdata_client.py` maps to `ReadOnlyAdx` | Scanner, evidence and ADX tools; injected credential, query-only grant, table-root guard, per-call bounds; `test_azdata_migration.py`, query/tool/scanner tests, `deploy.sh verify --scan` |
| ADX catalogue metadata / deferred | Retained `app/components/data_connector_library`, public `KustoReader` and `KustoTableInspector` | Inventory has a different status/schema contract; migrate after query parity. Existing inventory tests |
| MITRE retrieval / next candidate | Retained `azure_search` and datastore component; candidate `azdata[search]` | Knowledge and catalogue callers; preserve filters, ranking envelopes, counts and missing/error semantics; knowledge/classification tests |
| Models and agents / deferred | Retained `azure_llm`, CyberEye `backend/agents`; candidate `llm-interface` | Chat, diagnosis, summaries and evaluator; preserve Responses/SSE tool events, reasoning, previous-response state and caller ownership before replacement; agent/chat/stream tests |
| Graph / deferred | Retained datastore `GremlinGraph`, CyberEye `backend/data/graph.py` | `azdata` requires resource tokens; existing path uses runtime-resolved read-only key. Not credential-compatible. No silent fallback or auth change; graph tests |
| Authentication / retained | `entra_auth`, `signed_dev_access`, `backend/security` | Shared application gate and owner checks. No access library exists; native sign-in requires its own deployed acceptance. Gate/session/Entra tests |
| Rule battery and optimization / retained | `situation_detector`, `agent_optimization`, `local_query`, `copilot_terminal`; GUIDE facts in `backend/optimization` | Local-only owner-partitioned ledger and read-only GUIDE input. `libraries/agent-optimization` is documentation only, not a substitute. Optimization tests; live campaign deferred |
| Catalogue and rendering / retained | `resource_explorer`, `source_code`, `event_stream`; frontend public barrels | Existing React views, no equivalent frontend package in `libraries`; frontend tests/build and browser editor journey |
| Authoring / retained | `backend/agents/library.py`, `AgentLibrary` and editor HTTP adapter | Template-local immutable versions, explicit role assignment, stale-write/owner refusals; agent library/API and browser save/read-back tests |
| Ontology and Search fixtures / retained | `app/data/ontology`; `app/data/data_pipelines/search` | Ontology runtime contract; Search package is included only because existing fixtures import `build_document`. No publishing command is exposed or executed |
| Local launch / new host composition | `deploy/local.py`, `configuration`, `serve`; `deploy/deploy.sh` | Explicit source-root/env-file input; no source-file execution, auth changes or external writable state; launcher positive/refusal tests |

## Replacement Map

`backend/data/adx.py -> legacy AdxConnector/AdxClient` became
`backend/data/adx.py -> AdxQueryClient -> azdata.DataConnector`.
Runtime query callers have one selected transport, with no fallback switch. The old connector
source and its historical component tests are retained as baseline, not a second active query
path. Retirement is deferred until live scan/evidence parity can run; other catalogue readers
still need the retained datastore component.

The synchronous adapter is temporary. Remove it when scanner/tools and their HTTP callers
use the async library directly in one application event loop. Do not generalize it into a new
connector framework. Application table policy, wire payloads and evidence semantics stay here.

Copied Dockerfile and requirements were removed: they assumed excluded corpora and SDK 6.x,
and omitted the canonical library. `dev.sh` delegates to the single template launcher.
Container packaging and cloud rollout are deliberately not implemented in this increment.

## Verification Boundaries

Offline tests use synthetic coordinates; runtime configuration still fails closed when absent.
GUIDE previews open source databases with SQLite `mode=ro`; labels remain evaluator-only.
Writable local state never points to the source checkout. The inherited cloud target remains
owned by the source deployment; no new lifecycle owner or resource was introduced.

The library fixes are source changes, not a new published artifact. Previous wheel hashes do
not prove these corrected bytes. Live ADX is blocked by a stopped cluster, and successful model,
Gremlin, Search, optimizer and deployed sign-in parity are not inferred from offline results.

Next discriminating check: start the existing cluster through its authorized owner, run the
same historical scan on source and template, compare situations/evidence (ignoring timing and
request IDs), then retire the legacy query implementation. Next library batch is Search;
model-agent streaming needs a separate compatibility experiment.