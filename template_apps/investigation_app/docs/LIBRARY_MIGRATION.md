# Library Migration

Current source acceptance and dated migration history. Existing data, authored state,
credentials and immutable receipts remain protected. [Architecture](ARCHITECTURE_OVERVIEW.md)
owns current boundaries; the [runbook](../deploy/README.md) owns reproducible commands.

## Generic Reuse Audit

2026-09-17: comprehensive Investigation reuse audit and source migrations after the split.
Status: source migrations, integrated backend/browser acceptance and generated-catalogue
regeneration pass. The [earlier split gates](#current-acceptance) and all historical records below
are preserved, not promoted to evidence for these new bytes. No claim that all bugs are resolved.
No new package, skill directory, capability ID or retired runtime is introduced.

### Coverage And Evidence

The three returned read-only audits supply baseline coverage and candidate evidence; current
public exports, controlling implementations and migration call sites were checked separately.
Inventory, ontology and control gaps in those reports were closed by local source reads.

| Surface | Audited Coverage / Disposition |
| --- | --- |
| [Frontend source](../app/cybereye/frontend/src) | All 50 baseline files: composition 5, scanner 8, Investigation 6, graph 4, chat 2, editor 5, shared 20. Current renderer/extractor/projection, shared dispatcher and height-drag call sites checked; baseline count is not a new current-file count. |
| [Agents](../app/cybereye/backend/agents) | All 13 baseline Python files, including tools; compared against all 22 Python implementations in modular-agents' three modules. New authoring API and thin app policy adapter checked separately. |
| [Remaining backend](../app/cybereye/backend) | Data, knowledge, security, investigation/detector, API, configuration, models, main/local composition and package exports covered by backend audit. Domain queries, citations, authorization and lifecycle remain local. |
| [Inventory](../app/cybereye/backend/inventory) | All four files: manifest coordinate validation, source declarations/reachability, probe binding and service composition. Reuse public registry/probes; retain finite coordinate allowlists, exact-account binding and per-request knowledge-status sharing. |
| [Ontology](../app/data/ontology) | All five files: `__init__.py`, `build.py`, `canonical.py`, `extract.py`, `model.py`. Keep deterministic export projections, event-family extraction, structural/event edges, bucket aggregation and CSV contracts. Inputs and generated products untouched. |
| [Launch](../deploy/deploy.sh) and [control](../app/cybereye/control) | Backend audit covers launcher/verifier/local composition; local launcher and all seven control files checked: roster, agent fragment, data inventory, detector configuration and three prompts. Keep explicit targets, local state isolation, inference grant, replay evidence and authored domain instructions. |

Private audit reports are the editor `content.txt` results under
`/home/hanchoong/.vscode-server/data/User/workspaceStorage/cbc0d77f9206184cd3b77da1ea3edf3f/GitHub.copilot-chat/chat-session-resources/321f5632-995f-45f3-9fe0-d67ea0c45351/`:
backend `call_a6bFfEvEQPKhTAup90awFMqe__vscode-1789552873342`, frontend
`call_3iXeLv1eBpLPip8p9JHtShW0__vscode-1789552873343`, agents
`call_Wc7WdiRuBwa7B7oU5art8xcL__vscode-1789552873344`. These are audit observations,
not migration test receipts; editor-resource retention is not guaranteed. This bounded record
retains their decisions without another documentation tree or copied transcripts.

### Candidate Decisions

`Implemented` below identifies migrated ownership, with integrated acceptance recorded below.
The [owner map](ARCHITECTURE_OVERVIEW.md#capability-catalogue) links public owners and consumers.

| Candidate | Decision And Preserved Boundary |
| --- | --- |
| Authored agent storage | **Extract into existing owner; implemented.** `agentconfig.AgentVersionStore`, generic draft/version/assignment schemas and store error own hashed owner namespaces, immutable versions, CAS assignment and file locking. Preserve existing JSON/disk layout. App wrapper retains Principal authorization, model/tool allowlists and Investigator eligibility. POSIX flock/hard links are not a power-loss-durable database or replica-wide concurrency guarantee. |
| Callable resolution and tool metadata | **Reuse; implemented.** Public `resolve_tool`, `tool` and `tool_metadata`; retain strict loading, local-only reference refusal (including server references), typed metadata checks and original callable identity. |
| Browser flow/session records | **Extract into `entra_auth`; implemented.** `SessionService` coordinates atomic flow claim, state mismatch consumption, opaque-ID digest lookup, token-bounded expiry and revocation over injected stores. App retains Principal serialization/validation, authorization gate, cookies/CSRF, routes and store-outage refusal policy. |
| GUID grammar | **Reuse; implemented.** Public `entra_auth.GUID_PATTERN`; host configuration errors and complete-configuration requirements stay local. |
| Connector accounting | **Extend `azdata`; implemented.** `OperationMetrics` serves app ADX, knowledge and resource probes, with detached snapshots and explicit unknown exception/cancellation outcomes. Reporting field names remain host-owned; counters are not execution budgets or grants. |
| Graph cache | **Export/extend; implemented.** Public `ResultCache` replaces app cache mechanics; app selects `ttl_origin="started"`, preserving its prior TTL origin while the library default stays `completed`. Same-key single-flight and uncached raised failures are shared; no cardinality bound or lock-entry reclamation is claimed. |
| Graph counts/sample/property flattening | **Extract into `resource_explorer`; implemented.** Public `GraphInspection`, `GraphInspectionUnavailable` and `graph_properties`; borrowed connector by default, explicit owned cleanup, invalid/partial result refusal and 101-row sampling for preview truncation detection. App retains account authorization, ontology, windows and selection. |
| Tool-result card | **Extend modular renderers; implemented.** `ToolResultCard` retains compatible defaults and adds scoped plain-CSS structure, host header/band labels, note ordering and non-resizable body option. Domain signals/advisories and outer chat duration/arguments/disclosure remain app-owned; obsolete local card CSS removed. |
| Error/refusal/duplicate interpretation | **Reuse; implemented.** Both result parsing and tool-state classification use canonical extractors; refusal and duplicate remain distinct from execution error. |
| Object-row alignment | **Share only common projection; implemented.** `projectObjectRow` serves app and library renderer; array/scalar fallback, formatting, precision and evidence limits remain caller-specific. |
| Height dragging | **Local consolidation; implemented.** One app `useHeightDrag` serves Section and ChatPanel; retain their different directions, bounds, persistence, reset and composer autogrow. No shared-library resizing framework. |
| Native event presentation | **Local consolidation; implemented.** One dispatcher in frontend API owner shares tool/reasoning lifecycle handling; SSE library still owns framing only, not HTTP, sessions or diagnosis completion policy. |
| Synchronous native tools | **Reuse execution owner; implemented.** `AgentService` binds context with `partial`, preserving execution kind so native `AgentBinding` dispatches synchronous functions off-thread. Explicit schemas and authorization remain intact; no second execution loop. |
| Detector and knowledge health duplication | **Local cleanup; implemented.** One `_execution` definition remains; health and inventory each share one knowledge-status result across their two semantic fields/declarations. No cross-request health cache or domain merge implied. |
| Tables and graph layouts | **Keep different semantics.** Scanner expandable/rich record grids differ from sortable text/result tables; interactive force layout, position retention and label collision handling differ from layered library topology. Keep fullscreen/column controls local. |
| Window parsers and row/byte caps | **Keep different semantics.** Offset-aware UTC/48-hour app windows differ from naive/equal-endpoint library parsers. Native evidence values, rendered previews, oversized-first-row handling and byte accounting are not interchangeable. |
| Domain policy and citations | **Keep local.** KQL table/plugin guards, rule explanation, Perth scoring, MITRE keys/filter relaxation, retrieved-label enforcement, corpus markup/link policy and evidence-ledger provenance are not generic toolshape/rendering semantics. Authentication primitives do not replace the app authorization gate. |
| Backend session locks/stores | **Defer consolidation.** Host lock spans HTTP streaming; native lock spans execution with different queue/deadline/backpressure lifetimes. Live native-session idle/LRU retention is not the absolute-expiry serialized RecordStore contract. |
| Per-run model ceiling | **Existing finding; not migrated.** Roster chat limit 6 and diagnosis limit 10 feed `max(...)` in `AgentService`; the smaller chat model-call ceiling is not independently applied. Budget integration is a separate behavior fix, not reuse. |
| Runtime validation | **Existing finding; not migrated.** App accepts reasoning `max` while native runtime rejects it; integer iteration checks admit booleans. Reconcile configuration/runtime contracts in a separate behavior-fix increment. |
| Other retained audit limits | **Not resolved by reuse.** Frontend audit found per-hook fullscreen state does not establish cross-panel exclusivity. Installed-artifact parity and deployed human authentication remain unverified; local persistence/geometry and live startup are covered below. |

### Verification Boundary

Current source acceptance: 610 backend/deployment tests, 29 frontend tests, TypeScript and
production build pass. Signed native browser: 43 checks across seven phases with synthetic
services. Live acceptance: 23 API checks, 72 scanner/catalogue checks, 40 Investigation checks,
and 24 Agent Editor checks pass. Focused resize/card browser acceptance passes 20 checks.
Separate library checks cover the extracted version store, sessions, metrics, cache and graph
contracts; these overlapping counts are not added to the app total. Architecture checker
reported no violations. Custom Optimizer was not changed or executed in this audit.

Live app remains at `http://127.0.0.1:5182`, API `http://127.0.0.1:9012`, with the original
Investigator assignment restored. Native read-only/authentication and schema safeguards remain.
The composer grip's zero-width layout was exposed by real pointer tests and fixed with a
full-width grid row. Pointer drag, clamping, reload persistence and natural reset pass;
cancel/blur boundary events were synthetic and hook-unmount cleanup was tested offline.

Two saved-agent diagnosis attempts and one diagnostic run rejected overlong supporting
observations. The published schema matched HEAD: 220 characters per observation; the diagnostic
measured 280, 370 and 387 characters. Explicit existing bounds were added to diagnosis instructions,
without changing schemas or adding automatic retries. The next complete editor/live-diagnosis
journey passed. Model conformance is not guaranteed; malformed future calls still fail closed.

Private passing reports: `/tmp/agentcraft-reuse-live-api-final-20260917.json`,
`/tmp/agentcraft-reuse-scanner-20260917/scanner-verification.json`,
`/tmp/agentcraft-reuse-investigation-20260917/report.json`,
`/tmp/agentcraft-reuse-editor-bounded-20260917/report.json`,
`/tmp/agentcraft-reuse-native-20260917/run-t596lc/report.json`, and
`/tmp/privatebrowserreports/integrated-grip-recheck-1789640149511/report.json`.
Failed editor runs remain under `/tmp/agentcraft-reuse-editor-20260917/` and
`/tmp/agentcraft-reuse-editor-confirm-20260917/`; the private schema diagnosis is under
`/tmp/agentcraft-editor-schema-diagnostic-20260917-one-shot/`. Temporary evidence retention
is not guaranteed. These runs certify their observed local workflows, not release wheels.

Focused acceptance must retain positive and matching negative coverage: version restart/CAS/owner
isolation, single-winner flow claims/expiry/revocation, accounting exceptions/cancellation/reset,
cache expiry/failure/isolation, graph row 101/partial refusal/borrowed lifetime, sync versus async
tool dispatch/denial, canonical result states and real drag/reset/persistence. Existing app/library
test owners remain in place; historical successful counts below are not combined into a new total.

### Scoped Source Measurement

Measured 2026-09-17 against HEAD `7af26ebd60d260ad767e1a4b08434def1f7e25b1` using `git show`
for baseline bytes and filesystem reads for current bytes. Same roots: app backend, frontend
`src`, and ontology; only `.py`, `.ts`, `.tsx`, `.css`, excluding bytecode. Tests, deploy,
configuration, libraries, dependencies and generated output are excluded.

| Scope | HEAD Files / Lines / Bytes | Working Source Files / Lines / Bytes |
| --- | --- | --- |
| Investigation runtime roots above | 111 / 15,520 / 726,322 | 111 / 15,206 / 711,949 |

Net app reduction: 314 logical lines and 14,373 bytes; file count unchanged after deleting
the obsolete card and adding the shared height hook. Not a frozen release identity. Extraction adds
reusable library code and tests outside this denominator: net project reduction, disk reclamation,
RAM and latency improvements are unknown. Earlier measurements below have different scopes.

## Current Acceptance

Ownership split and local source acceptance: 2026-09-17. Investigation retains ten
[library owners](../../../libraries/README.md); eleven unused owners moved into skills.
Twelve duplicate skill directories are removed. Native discovery reads canonical sources;
regeneration creates no checkout guidance mirror. The five approved Custom Optimizer edits
change dependency paths only; that application was not executed.

| Current Gate | Observation |
| --- | --- |
| Backend/deployment | 578 tests passed, including genuine pinned ontology inputs; zero skips. |
| Frontend | 23 tests passed; TypeScript and production build passed. Existing bundle-size warning remains. |
| Live API | 23 checks passed: ADX scan/evidence, Cosmos graph, MITRE retrieval and matching refusals. |
| Live scanner/catalogue browser | 72 checks passed across desktop, tablet and mobile; no console/page errors. |
| Live Investigation browser | 40 checks passed: diagnosis, sequences, citations, summary, chat, source inspection and selection changes. |
| Live Agent Editor browser | 24 checks passed: persistence, immutable versions, upload/draft recovery, assignment and execution of both saved versions. Prior Investigator assignment restored. |
| Live query board | Seven native ADX rows matched rendered rows; fullscreen/Escape and desktop/mobile geometry passed; unsafe KQL returned 400. |
| Signed native browser | 43 checks passed across seven phases with synthetic service fixtures, including query recovery, ownership, replay/tamper refusals and on-demand chat sessions. Browser closed. |
| Discovery | 30 generator/distribution tests passed; actual source readers and regeneration check passed. |

Fixed during acceptance: the scanner verifier used obsolete inventory routes; assigning
an Investigator left chat attached to the previous definition. Chat now creates a session
on the next explicit send for the assigned agent ID/version. Existing messages remain;
submitted or interrupted turns are never automatically replayed. The old-session API refusal
and result ownership remain covered by the signed browser suite.

The local app is left running at `http://127.0.0.1:5178`, API `http://127.0.0.1:9012`,
using the existing authorized Perth/Cosmos/MITRE/model targets. Cumulative request caps remain
removed; authentication, read-only data policy and native per-run limits remain. This verifies
local source, not new release wheels, deployed Entra sign-in or broader provider guarantees.

Private reports: `/tmp/agentcraft-split-live-api-20260917.json`,
`/tmp/agentcraft-split-scanner-20260917/scanner-verification.json`,
`/tmp/agentcraft-split-investigation-20260917/report.json`,
`/tmp/agentcraft-split-editor-fixed-20260917/report.json`,
`/tmp/agentcraft-split-native-browser-fixed-20260917/run-MCzzC9/report.json`, and
`/tmp/agentcraft-split-live-query-mrEE38/report.json`. Earlier failed runs remain preserved.

Relocation recovery and exact manifests: `/tmp/agentcraft-owner-move-82oe99ld/` and
`/tmp/agentcraft-split-321f-utzijt9j/`. Moved payload: 339 files / 3,408,006 original logical
bytes. Removed old generated payload: 17,358 files / 348,795,237 logical bytes; separately,
29 duplicate skill files were removed and three historical deployment artifacts were moved
unchanged into the modular-agents library's provenance directory. These are scoped counts,
not net repository size or physical disk reclamation. Temporary recovery retention is not guaranteed.

## History: Installed Closeout

Earlier closeout: 2026-09-17. [Installed acceptance receipt](../../../.github/skills/harness-guide/framework/distribution/investigation-closeout.json)
owns that artifact's hashes, commands, private evidence paths and preserved failures.
All local gates passed; no live provider, deployment or publication operation ran.

| Evidence Class | Observation And Limit |
| --- | --- |
| Source/API | Async graph probes use public `azdata`; the earlier sync-probe blocker is resolved. Strict configuration reuses public `agentconfig`; shared `ResultTable` and `SourceCodeViewer` replace app copies. The owner map links immediate callers. |
| Installed tests | 572 backend/deploy tests, including all 42 genuine ontology cases; 532 native library tests; 51 framework/core tests; 23 frontend tests. Zero failures/skips in these scopes. Subsets overlap and are not additional tests. |
| Installed signed browser | `./deploy/deploy.sh browser-verify native-offline`: 42 checks PASS, seven phases, no browser errors or external attempts, on Python 3.12.3 and Chromium 151.0.7922.34. Current receipt retains desktop/mobile screenshots and exact identities. |
| Browser proof boundary | Real loopback HTTP, frontend controls, native agent/data/Search parsing and graph driver with **SYNTHETIC service fixtures**. Ephemeral signed auth: anonymous 401, foreign-owner 404, replay/tamper 401; test-principal resolver null. Scan selection waits for completed output and automatic work is not duplicated. |
| Lifecycle | Browser and fixture server closed, server exit 0, no external attempts. `native_asgi_support` owns test services and uvicorn uses `lifespan=off`; this is not production-lifespan or live Azure/authentication acceptance. Synthetic state/build/screenshots remain in the external run directory. |
| Genuine ontology inputs | Returned 42 tests passed, zero skipped, with all five pinned input hashes unchanged. Original products are under `/home/hanchoong/perth_cyber/app/data/output`; original raw CSV is also required. [Input tests](../app/cybereye/tests/test_ontology_graph.py) own exact pins and refusal guards. No source output was generated, replaced or copied into this checkout. |
| Artifact isolation | 17 first-party distributions resolve from `site-packages`, zero editables or library source-path injection. Staged Investigation uses four installed frontend tarballs; strict typecheck and production build pass. No Custom Optimizer file was changed or executed. |

The [azdata contract](../../../libraries/azure-data-connectors/CONTRACT.md#request-values)
owns native content versus tagged-wire semantics; [ADX caller](../app/cybereye/backend/data/adx.py)
and [model tool boundary](../app/cybereye/backend/agents/tools/base.py) use the two deliberately.
Historical wheel hashes do not establish current runtime or generated-document identity.
Live provider/deployed auth and broader platform floors remain unverified.

## Closeout Reduction

Same-scope source measurements are retained in the acceptance receipt. Counts below use
logical lines/bytes, not allocated disk, RAM or latency. The earliest closeout baseline
already followed the first small ADX edit; no missing baseline was reconstructed by guess.

| Scope | Before | After |
| --- | --- | --- |
| Closeout Investigation runtime | 115 files / 15,681 lines / 732,299 bytes | 113 files / 15,510 lines / 725,637 bytes |
| Original migration runtime, including config | 190 files / 29,046 lines / 1,236,667 bytes | 114 files / 15,539 lines / 726,986 bytes |
| Closeout app code including verification | 167 files / 1,412,622 bytes | 167 files / 1,557,863 bytes |

Private table/highlighter implementations and duplicate config loading are retired;
domain queries, evidence policy and authorization remain application-owned. Two unused
xterm packages and their aliases are removed. Real end-to-end and refusal coverage adds
145,241 bytes including verification: total app size did not shrink in this closeout.
The original migration reduction is historical, not extra credit for this pass.

Repository cleanup separately removed 305 generated plugin-mirror files and 191 frozen
build/cache files. Their [guidance](../../../.github/skills/harness-guide/framework/distribution/guidance-dedup.json)
and [cleanup](../../../.github/skills/harness-guide/framework/distribution/deep-clean.json) receipts retain
scope, recovery and protected-file evidence. At that checkpoint native skill runtimes were absent;
operational data, notices, source inputs and Custom Optimizer are preserved.

## History: Initial Consolidation

Baseline `00c76c6bb55190877c3d4d4b5b3a14e55bce2cb4`, verified 2026-09-16. The separately
authorized Perth cluster restart and disabled idle auto-stop belong to root deployment.
The following observations describe those exact source/artifact scopes.

## B02/B03 Supersession

Historical intermediate owner/API/evidence record: [library-first migration](../../../libraries/azure-data-connectors/MIGRATION_B02_B03.md).
Synchronous data/model compatibility decisions and measurements below are historical.
Their runtimes are retired; receipts and source baselines remain unchanged.

## Historical Owners

| Outcome / Decision | Public Owner And Retired Source | Consumers, Contract And Check |
| --- | --- | --- |
| Ordered rule execution / extract | `libraries/situation-detector`, `situation_detector`; removed `shared/src/template_foundations/situation_detector` | Investigation scanner and Custom Optimizer joint evaluation; injected callbacks, deterministic digest, bounded window, failures remain errors; original battery suite moved to library |
| Human token and PKCE primitives / extract | `libraries/entra-auth`, `entra_auth`; removed `app/components/entra_auth` | Host security/sign-in adapters retain authorization, routes and cookies; tenant/expiry/key and session negatives preserved |
| Signed caller verification / extract | `libraries/signed-dev-access`, `signed_dev_access`; removed `app/components/signed_dev_access` | Same host gate; raw-byte signature, replay, tamper, expiry and size refusals preserved; no runtime dependency on Entra |
| Catalogue and bounded previews / extract | `libraries/resource-explorer`, `resource_explorer`, `.content`, `.probes`, `@agentcraft/resource-explorer`; removed components and app-owned probe mechanics | App inventory/agent editor; 25-line app composition supplies explicit identity, account and graph factory; no duplicate transport |
| Named event framing / extract | `libraries/event-stream`, `@agentcraft/event-stream`; removed `app/components/event_stream` | App scan/chat stream callers; UTF-8/CRLF framing, JSON failures and reader release preserved; no Python package |
| Read-only source viewer / extract | `libraries/source-code`, `@agentcraft/source-code`; removed shared source viewer | Both frontends and catalogue; original source, token safety, copy/wrap and stale-highlight contract; no Python package |
| Raw model compatibility / keep separate and extract | `libraries/azure-llm-compat`, `AzureLlmClient`, `response_events`, `stream_tool_turn`; bridge and app loop removed | Both hosts; native Responses IDs/events remain distinct from bounded `llm_interface`; host tool authorization and domain policies remain local |
| Sync MITRE reads / extract adapter, reuse transport | `libraries/search-read-adapter`, `search_read_adapter`; removed shared `read.py` | Both knowledge callers; `azdata` is the only transport, key/error identities have one owner; policy/lifetime/refusal coverage preserved |
| Concurrent sync ADX reads / extract, reuse transport | `azdata.adx_read`, `AdxQueryClient`, `QueryRows`, `bind_parameters`; app `azdata_client.py` removed | Scanner, evidence and tools; host query-only policy and table guard; concurrency, parameter, identity and lifetime checks preserved |
| Existing graph reads / extend and extract | `azdata.graph_read.GremlinReader`; app driver/key plumbing and custom ARM component removed | Graph panel and catalogue use one reader; native Cosmos SDK read-only-key call; canonical parsed read traversals; no writes or alternate-target fallback |
| Test-only publishing stack / retire | Removed `shared/azure_search`, `app/data/data_pipelines/search` and old transport-only tests | MITRE fixture projection and frozen key/provenance assertions stay under app tests; actual loaded index is unchanged |
| Event-store operator API / consolidate | `azdata.event_store`; `.github/skills/adx-event-store` removed | Native bootstrap/operator contracts, license, gotchas and 82 self-checks preserved; query-only defaults and explicit mutation grants |

## History: Consolidation Verification

- App, model/Search compatibility and shared consumer suite: **603 passed, 10 skipped**.
  Skips require excluded ontology build products, not unavailable tests removed for a pass.
- Standalone auth/signature/catalogue/detector libraries: **221 passed**. Full data library:
  **190 passed**. Deployment safety: **74 passed**; event-store selftest: **82/82**.
- Both frontend builds pass; Investigation's existing frontend unit suite passes. Custom
  Optimizer's affected workflow/launcher tests: **20 passed, 2 existing local-isolation skips**.
- Final isolated wheel environment: **80 model/Search/ADX/graph checks passed**; 11 public
  imports resolve inside that environment, no editable/local-path runtime dependencies;
  `uv pip check` reports all 78 distributions compatible after app pins are installed.
- Wheel-backed localhost app: **23 API checks and 72 browser checks passed** at 1440x900,
  900x800 and 390x844. Actual controls perform scan/evidence, graph search/two-hop/zoom and
  visible MITRE previews. Missing graph/document and disabled-source refusals pass.
- Perth scan returns two situations; evidence read-back returns 13 rows. Graph holds
  1,308 vertices/2,429 edges; MITRE has 3,908 documents, with 25 preview rows and matching
  keyed provenance read-back. No response was fulfilled with synthetic data.
- Installed `azdata` 4.0.0a4 runtime digest:
  `c8867de1ebd8d1bfc2c96d57db995090f9fef11a3012976c6eb5e31c87feaaf5`.
  Protected application identity reports native transport, wheel install, not editable.
- Architecture check: 150 files/385 imports resolved, no violations. Launcher remains
  independent; the acceptance boundary explicitly imports application read contracts.

Historical private reports and screenshots: `/tmp/agentcraft-migration-resume-20260916/`,
`api-installed.json` and scanner verification under its `browser-installed` directory. These temporary
artifacts are not durable backups or registry publications. The compact deployment record
retains counts, identities and hashes without customer rows.

## History: Measured Reduction

Same baseline/current scope: first-party `.py`, `.ts`, `.tsx`, `.css` runtime source;
exclude tests, deploy and generated/dependency trees. Logical bytes are not allocated disk
or process memory. No RAM/latency improvement was measured.

| Scope | Before Files / Bytes | After Files / Bytes |
| --- | --- | --- |
| Investigation runtime | 190 / 1,236,667 | 114 / 719,915 |
| Shared runtime | 20 / 80,423 | 2 / 2,744 |
| Included component runtime | 70 / 447,420 | 0 / 0 |

Shared's two files are its package marker and 2,663-byte local process supervisor; zero
runtime dependencies. No manual implementation was moved into another template directory.
The relevant next change now belongs to the library named in the owner map.

An exact external cleanup manifest removed 73 stale generated files/476,554 logical bytes:
shared `build/` copies and retired-directory bytecode only. Active dependencies, assets,
data and receipts were excluded. Ignore rules already prevent tracking those outputs.
A clean rebuilt shared wheel proves exactly two runtime files; stale build copies do not ship.
Recover tracked source from the baseline commit; generated output regenerates from source.
The original full filesystem baseline was lost in the machine crash, so a whole-tree disk
reduction is unknown and is not inferred from these comparable source counts.

## History: Pre-Crash Evidence

The following inherited observations describe earlier completed blocks. Their original
`/tmp/agentcraft-migration.KbnBod` receipts did not survive the crash. Final checks above
were rerun from the recovered integrated source and installed wheels.

- Detector baseline and relocated installed consumer: 32 passed each. Same battery,
  detector engine and detector configuration assertions; no behavior changes.
- Library and both app dependency resolutions succeed with explicit uv path sources.
- Frozen source/destination hashes and mechanical import list:
  `/tmp/agentcraft-migration.KbnBod/situation-detector-move.json`.
- Recovery for moved tracked source is the baseline commit; existing parent edits remain intact.
- Live checks are recorded per completed batch below. No registry publication or new
  deployment is claimed by source/artifact tests.
- Detector live batch: API 11/11; browser 60/60; graph status 1,308 vertices/2,429 edges;
  MITRE health available with 3,908 documents. Optimizer: 11 passed, 2 existing isolation skips.
- Auth extraction: 253 passed across preserved library tests and application gate/sign-in/
  session/loopback suites. Baseline exposed missing `pytest-asyncio`; declared the prerequisite,
  preserved every test. Move receipt: `/tmp/agentcraft-migration.KbnBod/auth-move.json`.
- Auth live batch: API 11/11, guarded browser 60/60; healthy ADX, graph and MITRE counts unchanged.
- Catalogue backend: 120 passed before/after move. Both frontend typecheck/build commands pass.
  Investigation unit checks: 22 passed after correcting only the test loader's retired alias.
  Frozen source/destination receipt: `/tmp/agentcraft-migration.KbnBod/catalogue-move.json`.
- Catalogue live block: API 11/11, guarded scanner 60/60, unchanged graph/MITRE health.
  Extra no-save catalogue/source check: 25 real MITRE rows, copy/wrap and zero horizontal
  overflow at 1440/900/390 px; screenshots inspected at desktop/mobile. Private evidence:
  `/tmp/agentcraft-migration.KbnBod/catalogue-ui-v2/results.json`.
- Model compatibility: 24 focused tests; 73 with app startup/gate. No inference.
  Search: 85 adapter, knowledge and retained fixture checks. Move receipts:
  `/tmp/agentcraft-migration.KbnBod/model-compat-move.json` and `search-read-move.json`.

## History: Deliberate Boundaries

- `azure_llm_compat` retains the native Responses contract. `llm_interface` uses different
  OpenAI dependencies, session retention and events. No raw escape hatch or silent fallback
  was added; changing user-visible conversation semantics is outside this data-only increment.
- The graph read-only-key reader is separate from uniform Gremlin's resource-token contract.
  Both reuse the same parsed read syntax; neither falsely claims the other's guarantees.
- Deployed auth, new data writes, model inference, optimization campaigns and publication
  remain unverified. Local data acceptance is complete, not a production-readiness claim.
- ADX idle auto-stop is disabled and read back. Compute charges continue; external stop
  schedules, manual stops and platform outages are not prevented or claimed absent.