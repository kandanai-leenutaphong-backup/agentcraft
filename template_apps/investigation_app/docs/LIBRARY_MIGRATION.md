# Library Migration

Completed source consolidation from baseline `00c76c6bb55190877c3d4d4b5b3a14e55bce2cb4`,
verified 2026-09-16. Existing data, authored state, credentials and immutable receipts stayed
protected. The separately authorized Perth cluster restart and disabled idle auto-stop are
owned by root deployment. No inference, data writes, new resources, grants or auth bypasses ran.

## B02/B03 Supersession

Current owner/API/evidence record: [library-first migration](../../../libraries/azure-data-connectors/MIGRATION_B02_B03.md).
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

## Final Verification

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

Final private reports and screenshots: `/tmp/agentcraft-migration-resume-20260916/`,
`api-installed.json` and `browser-installed/scanner-verification.json`. These temporary
artifacts are not durable backups or registry publications. The compact deployment record
retains counts, identities and hashes without customer rows.

## Measured Reduction

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

## Pre-Crash Evidence

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

## Deliberate Boundaries

- `azure_llm_compat` retains the native Responses contract. `llm_interface` uses different
  OpenAI dependencies, session retention and events. No raw escape hatch or silent fallback
  was added; changing user-visible conversation semantics is outside this data-only increment.
- The graph read-only-key reader is separate from uniform Gremlin's resource-token contract.
  Both reuse the same parsed read syntax; neither falsely claims the other's guarantees.
- Deployed auth, new data writes, model inference, optimization campaigns and publication
  remain unverified. Local data acceptance is complete, not a production-readiness claim.
- ADX idle auto-stop is disabled and read back. Compute charges continue; external stop
  schedules, manual stops and platform outages are not prevented or claimed absent.