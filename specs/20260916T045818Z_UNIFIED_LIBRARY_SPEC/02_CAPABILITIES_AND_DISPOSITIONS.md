# 02. Capabilities And Dispositions

This is the migration inventory, not a requirement to reproduce every historical API.
Feature IDs retain the framework audit's cross-references. Target means a selected outcome;
current means source observed by the consolidated input audits on 2026-09-16. Execution
rechecks exact paths, signatures and consumers before each batch.

## Bounded Objective

- **Objective:** assign each retained outcome one library owner and each obsolete runtime
	an explicit removal, under [0. Core Objective](0_CORE_OBJECTIVE.md).
- **Done when:** all 38 audited feature IDs have one disposition, and each delivered block
	identifies its replacement API, exact old paths and affected consumers.
- **Scope ceiling:** use the existing inventory; recheck only facts needed by the current
	block. Proposed destinations are ownership choices, not orders to create a new package
	for each row. No additional feature family without an explicit scope change.
- **Stop condition:** the block's owner, replacement/removal and relevant check are known.
	Proceed to implementation; do not repeat a portfolio-wide inventory for reassurance.

## Existing Library Portfolio

Baseline: 11 capability directories, eight Python distributions, three npm packages;
Resource Explorer spans both languages. Seven Python distributions share the uv workspace.
`azure-llm-compat` is excluded because its OpenAI 2.x range conflicts with the bounded model
package's OpenAI 3.x requirements. Agent Optimization is research-only in this directory.
These are recorded baseline facts, not fresh package/install verification by this spec.

| Current Owner / Public Namespace | Target Disposition | Current Authority |
| --- | --- | --- |
| `azdata` | Keep and standardize data profiles, policy and evidence; absorb useful adapters into native async ownership | [Contract](../../libraries/azure-data-connectors/CONTRACT.md) |
| `llm_interface` | Sole model/agent runtime; native Agent Framework owns invocation | [Contract](../../libraries/llm-interface/CONTRACT.md) |
| `azure_llm_compat` | Retire; both template apps migrate to `llm_interface` | [Current compatibility](../../libraries/azure-llm-compat/README.md) |
| `search_read_adapter` | Retire sync/error adaptation; app knowledge readers consume async `azdata` | [Current facade](../../libraries/search-read-adapter/README.md) |
| `entra_auth` | Keep tenant/token/PKCE/expiring-record primitives; host authorization stays external | [Exports](../../libraries/entra-auth/src/entra_auth/__init__.py) |
| `signed_dev_access` | Keep signatures/replay and add selected signing client/CLI from skill; one wire owner | [Exports](../../libraries/signed-dev-access/src/signed_dev_access/__init__.py) |
| `situation_detector` | Keep domain-neutral battery; align cancellation/events/budget integration | [Exports](../../libraries/situation-detector/src/situation_detector/__init__.py) |
| `resource_explorer` | Keep registry/probes/wire/UI with neutral defaults and explicit host routes/claims | [Guide](../../libraries/resource-explorer/README.md) |
| `@agentcraft/source-code` | Keep safe source rendering; distribution/type/asset conformance | [Exports](../../libraries/source-code/frontend/index.ts) |
| `@agentcraft/event-stream` | Keep named frame decoding; add semantic event validation only at its owning adapter | [Decoder](../../libraries/event-stream/frontend/read-events.ts) |
| `agent-optimization` research | Add the selected optimization runtime from skills, composing existing libraries; research remains labeled evidence | [Research scope](../../libraries/agent-optimization/README.md) |

## Data Features

| ID | Current Feature / Surface | Selected Target And Migration Work |
| --- | --- | --- |
| D1 | Async `connect`, typed create/read/update/upsert/delete/query/ingest/schema/provision/status, `OperationResult` | Keep one uniform data contract; unsupported modes remain explicit. Update grants/diagnostics to chapter 03; no request-level target or authority override. |
| D2 | `describe`, operation capabilities/caveats, async close/context | Keep offline descriptors; readiness is an explicitly authorized observation, not inferred from configuration. |
| D3 | Requests, keys, versions, limits, results, evidence, continuation, transport injection | Preserve meaning and integrity of values/effects, not old class layout. Safe correlation/diagnostics are shared; payload serialization is never default logging. |
| D4 | `azdata.adx_read` thread/loop bridge, `QueryRows`, parameter binding, package identity | Port needed binding/native-row conversion to the ADX owner; use async queries in hosts. Identity inspection becomes framework diagnostics, not a transport wrapper. Delete `adx_read.py` and its sync-only public surface. |
| D5 | `azdata.graph_read` key lookup, reconnect, sync query/count/sample/flatten helpers | One async graph owner and parser/driver. Fixed read-only-key and resource-token credential profiles remain explicit; host opts into exact key-provider use. Count/sample is typed query composition; delete the independent reader. |
| D6 | `azdata.event_store` operator config/query/commands/schema, raw SDK access | Keep bounded public operator query/schema calls with explicit authority. Remove public raw-client escape hatches and ambient credential discovery from the target; code that deliberately calls native SDKs is outside library guarantees. |
| D7 | Append-oriented repository insert/read/latest/update/delete/purge/extent-tag operations | Keep documented ingestion/retention outcomes and exact destructive confirmations. Retire misleading transactional CRUD/upsert claims; native predicates are trusted operator inputs, not request code. |
| D8 | Queued/managed/file/row ingestion, schema inference, batch receipt/read-back | Keep; accepted is not stored, deduplication is retention-bounded. Reuse native SDK retry semantics with explicit accounting; do not add a parallel ingestion engine. |
| D9 | Cluster/database inspect/provision/wait/teardown helpers | Keep only the explicit operator API; deployment root owns approval, target and sequence. Unknown existence never becomes absent. No infrastructure mutation enters ordinary data-query grants. |
| D10 | `python -m azdata.event_store.bootstrap` CSV/expected-count/report workflow | Keep a public operator command over D6-D9 with target-bound confirmations and exact batch verification; modernize CLI as needed, retire old skill launcher/runtime. |

### Data Service Coverage

The selected v1 framework profile retains the useful currently declared service families,
not every provider SDK operation. Freeze feature/mode assertions before implementation.

| Profile | Intended Operations | Explicit Non-Goals |
| --- | --- | --- |
| Search | Document read/delete/merge/upsert; keyword/full/semantic/vector query, counts/facets/answers/captions; constrained schema management | No fabricated document create-if-absent/version guarantee; no drop/recreate disguised as schema update |
| Cosmos NoSQL | Explicit partitioned CRUD/replace/upsert and bound query/continuation | No cross-request transaction, unsupported partition shape or implicit merge |
| Blob | Block-blob CRUD/replace, exact bytes, prefix listing/continuation | No implicit append/page blob, lease or historical-version service |
| Table | Composite keys, native entity types, ETags, merge/replace and bound OData | No invented nested/null support or conditional-upsert guarantee |
| ADX and Eventhouse | Shared KQL owner, parameters, streaming acknowledgment and table-schema reads | No keyed transactions, snapshot pagination or content proof from acknowledgment |
| Fabric GraphModel | Explicit preview read GQL, definition/refresh and bound job status | No arbitrary parameter interpolation, vertex CRUD or durable cross-instance job claims |
| Cosmos Gremlin | Typed read traversals and resource-token-authorized vertex operations; explicit read-only-key query profile | No mutations through read-only-key profile, automatic credential fallback, transactions or pretend upsert |
| SQL and PostgreSQL | Keyed rows, parsed bound SELECT, merge and native transactional merge-upsert, schema reads | No arbitrary tables/functions, full replacement or distributed transactions |

Unsupported cases count only as refusal coverage. A required positive operation cannot be
changed to unsupported after its check fails; revise this specification and scope explicitly.

## Models And Agents

| ID | Current Feature / Surface | Selected Target And Migration Work |
| --- | --- | --- |
| M1 | Model `connect`, config/policy/limits/capabilities, describe/close | Keep fixed endpoint/deployment binding, explicit borrowed credential and default-denied inference. Resolve one compatible native dependency profile. |
| M2 | Chat, structured output, native messages/responses and streaming | Keep framework-native typed values and constrained options. No raw Responses kwargs/header/body override API. |
| M3 | Ordered embeddings with native index/cardinality/dimension validation | Keep explicit deployment and batch integrity; no implicit model fallback or model-generated embedding endpoint. |
| M4 | Agent binding, typed tools, authorizer, progress and one invocation loop | Keep native Agent Framework invocation; share correlation/budget context without implementing another tool loop. |
| M5 | Owner-bound in-memory sessions, result read-back and versioned run events | Adopt as target. Apps use new session IDs and events, not provider `previous_response_id`. Durable persistence is a declared host/recovery capability, not inferred from an in-memory result. |
| M6 | Explicit `from_clients` provider extension | Keep a trusted adapter API with frozen conformance requirements; no config-driven imports or unchecked native-enforcement claims. |
| M7 | Raw Responses client/text/stream/embedding/SDK access in `azure_llm_compat` | Retire. Implement only genuine missing selected M1-M6 capability, not a raw compatibility mode. Move consumers/configuration/tests to native model contract. |
| M8 | Legacy `response_events`, `stream_tool_turn`, credential helpers | Retire duplicate loops/events/credential ownership. Host may map new semantic events to its UI, but cannot keep a second model engine. |

The same model owner replaces skill `azllm` and `modelaccess`. Names or wire compatibility
alone do not justify preserving three client families. Prior session artifacts are protected
data; explicit host migration or read-only historical display replaces silent reinterpretation.

## Authentication And Rules

| ID | Current Feature / Surface | Selected Target And Migration Work |
| --- | --- | --- |
| A1 | Tenant/token validation, verified claims and bearer/header helpers | Keep; normalized caller evidence is mapped to host policy, never an automatic authorization grant. |
| A2 | Bounded JWKS lookup/cache and safe auth diagnostics | Keep stale-key/cooldown/expiry refusal; redact default diagnostics and preserve terse public auth denial. |
| A3 | PKCE/state/authorization/logout/session-key primitives | Keep; host owns routes/cookies/CSRF/session semantics. Native Easy Auth/MSAL can be an explicit deployment choice, not a forced cloud change during source migration. |
| A4 | In-process/Azure Table expiring record store with consume/delete/purge | Keep distinct expiry/atomic-consume contract; do not repurpose as a conversation database. |
| A5 | Signature verify/canonicalization/fingerprint | Keep and consolidate corresponding signing primitives from `devauth`; one versioned wire specification. |
| A6 | Pure ASGI middleware/installer and identity factory | Keep optional host installation; framework installation never creates keys or enables access. |
| A7 | In-process/Azure replay ledger and claim-once | Keep atomic replay/capacity/refusal semantics; describe replica scope and owned cleanup. Not interchangeable with A4. |
| R1 | Configuration/window normalization, selected rules and stable digest | Keep pure no-I/O functions; names in configuration never identify executable code. |
| R2 | Sync/async/streamed query-test battery | Keep a pure sequential sync path and bounded async path. Propagate cancellation/control exceptions, await cleanup, preserve final declaration ordering, correlate events under chapter 03. |

## Inventory, Knowledge And Frontend

| ID | Current Feature / Surface | Selected Target And Migration Work |
| --- | --- | --- |
| C1 | Registry/selection/opaque node identities | Keep configured-source inventory. Selection narrows UI reads but never grants access or discovers an unconfigured estate. |
| C2 | Inventory service/probe protocol, Pydantic wire responses | Keep with neutral provenance default and explicit host prefixes. Apps set historical-replay claims when true. |
| C3 | Content/discovery bounds/status/rows/graph samples and optional-SDK helpers | Keep selected bounded-content contract; place graph query mechanics in `azdata`. Move test-only override helpers out of supported public runtime exports. |
| C4 | ADX/Search/graph catalogue probes and accounting | Keep one probe adapter per selected source contract; share data clients and run context through public APIs, never duplicate transport/auth. |
| C5 | Four GET inventory routes and selection header | Retain as optional capability HTTP contribution with host-supplied prefix/auth; adopt versioned target schemas, update UI and MCP callers. |
| C6 | React explorer/layout/tree/detail/rows/status/source-tool views | Keep actual user outcomes; remove source-project literals. Call host services through typed props/clients. No UI-owned agent execution. |
| C7 | Browser client, schema parsing, tree/selection state, keyboard/row/status helpers | Keep needed public functions; designate internals instead of exporting everything by accident. Breaking changes are documented and consumers updated. |
| C8 | Fixed-index synchronous `search_read_adapter` and key/error aliases | Retire. Knowledge adapters await `azdata` directly; needed pure key rules move once to data ownership or host document schema, not a sync facade. |
| U1 | Safe Shiki source viewer, line numbering/wrap/copy/stale-result handling | Keep typed React component with explicit assets and ESM/types; no execution/upload. |
| U2 | UTF-8/CRLF named SSE and JSON framing | Keep framework-free primitive; schema validation, terminal semantics and reconnect remain explicitly higher-level. Bound/cancel reader behavior according to its documented profile. |
| X1 | Optimization/evaluation/observability research | Preserve references as research. Selected runtime generation/cohort/replay outcomes come from the migrated optimization capability; no automatic promise of every researched Foundry feature. |

## Additional Capability Owners From Skills

These are selected destinations, not packages already implemented. Reuse upstream tools
inside them; do not generate a package for a purely procedural skill.

| Target Root / Public Family | Retained Outcome | Rationale |
| --- | --- | --- |
| `libraries/app-composition` / `appcompose` | Versioned document validation, allowlisted bindings, dependency ordering, route/asset ownership, startup rollback and shutdown | One composition engine reused by the framework root, not a new engine in the facade |
| `libraries/recoverable-jobs` / `workrecovery` | Recoverable completed outputs, verified commit/read-back and durable manifests | Distinct from scheduling, retrying unfinished work, sessions or queues |
| `libraries/modular-agents` / configuration and hosted-bundle APIs | Agent roster/prompt/tool binding, measured tool configuration and native hosted packaging | Composes `llm_interface`, detector and native framework; no retained duplicate invocation loop |
| `libraries/agent-optimization` / `agent_optimization` | Immutable generations, frozen cohorts, evidence-tool/detector/prompt experiments and replay UI | One actual workflow owner; evaluator/labels and host authorization remain explicit |
| `libraries/copilot-terminal` / Python PTY and React exports | Local interactive terminal sessions and bounded provider/credential integration | Privileged trusted-local capability, not a multi-user sandbox; notices/licensing gate distribution |
| `libraries/repository-inspection` / catalogue, architecture and filesystem modules | Read-only inspection of repository capabilities, dependency boundaries and filesystem weight | One offline repository-inspection tool family with distinct typed outputs; no generic runtime utilities or automatic deletion |
| `libraries/investigation-notebook` / notebook API/CLI | Durable findings, schema validation, search and transitions | Source/runtime migrates, existing user notes/databases never enter deletion manifests |
| `libraries/web-resource` / acquisition API/CLI | Guarded public fetch/capture, rate/robots policy, provenance and catalogue checks | One acquisition guard/ledger owner; no network bypass or publisher-content redistribution |
| `libraries/azure-sky-styling` / CSS/React exports | Opt-in styling tokens/materials and tested gallery/assets | A specific visual capability, not the framework's mandatory theme |
| `libraries/hyperframes-tools` / rendering/verification adapters | Pinned native HyperFrames invocation, finite timeline checks, render/probe evidence | Upstream engine stays upstream; no bespoke video engine or fake runtime extraction |

Native administrative access, Container Apps deployment, review/audit procedures and
content-store application policy remain guidance or host responsibilities. Retire redundant
helper engines where a native procedure suffices; chapter 04 records every skill explicitly.

## Current Versus Target Dependencies

Observed literal source edges were `resource_explorer -> azdata` and
`search_read_adapter -> azdata`; frontend Explorer has a source-viewer peer. Callback
dependencies are host-composed. Metadata source mappings alone do not establish runtime
dependencies. Unknown external/dynamic consumers create inventory work, not retirement vetoes.

The target graph is in [03](03_FRAMEWORK_AND_INTERFACE_STANDARD.md). Final package
dependencies must reflect actual imports, not just directory grouping. Every additional
foundation needs a real shared invariant or second consumer named in its contract.

Next: [03. Framework And Interface Standard](03_FRAMEWORK_AND_INTERFACE_STANDARD.md).