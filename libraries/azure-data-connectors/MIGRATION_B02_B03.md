# B02/B03 Migration Record

Scope: assigned data/model libraries and template app hosts. No component-owner paths,
root workspace metadata, skill runtimes, user state, receipts, source checkout or cloud
resources are writable in this block. Existing `docs/event-store` history is preserved.

## Selected Contracts

- Async `azdata.connect` and typed `QueryRequest`/`ReadRequest` own application reads.
- Kusto accepts native datetime, timespan and JSON dynamic parameters. Undeclared
  parameters receive a generated declaration; explicitly declared KQL remains supported.
- Gremlin `resource_token` and `readonly_key` are separate profiles. The latter requires
  `gremlin_readonly_key_provider(config)`, accepts read/query only, and never discovers a
  credential. Hosts bind exact native Cosmos `list_read_only_keys` using borrowed identity.
- `llm_interface` and native Agent Framework own inference, tools, sessions and run events.
  App grants default false; host opt-in is `CYBEREYE_ALLOW_MODEL_CALLS=true`.
- Native model sessions replace provider continuation IDs. No automatic stale-session
  replay. Historical campaign files are untouched and are not evidence for new inference.

## Bounded Increments

Each increment is one owner change plus immediate focused check, with at most three local
repairs before reporting a blocker. No portfolio framework implementation or cloud gate
is part of this scope. Elapsed effort was not measured.

| Increment | Immediate Check | Observation |
| --- | --- | --- |
| Gremlin explicit profile | `tests/adapters/test_gremlin.py` and transport tests | Initial 12 tests and 12 subtests passed |
| Native Kusto parameters | `tests/adapters/test_kusto.py` | 9 tests and 4 subtests passed |
| Async Investigation ADX | app `test_azdata_migration.py` | 10 tests and 6 subtests passed |
| Async graph and exact native key provider | app `test_async_graph.py` | Fixture constructor failed first; corrected, 2 passed |
| Async MITRE reader | app `test_knowledge_search.py -k KnowledgeCacheTests` | Applied indentation defect corrected; 5 passed |
| Native Investigation agent | app `test_native_agent.py` | Event helper scope defect corrected; 3 passed |
| Native Optimizer prediction | app `test_native_model.py` | 1 passed |

## Retired Source And Tests

- `azdata/adx_read.py`, `tests/contract/test_adx_read.py`: synchronous thread/loop bridge,
  wrapper identity and `QueryRows` shape retired. Parameter, bound, partial, concurrency,
  no-I/O refusal and borrowed cleanup coverage now belongs to Kusto and async host tests.
- `azdata/graph_read.py`, `tests/test_graph_read.py`, `graph-read` extra: independent sync
  driver/key lookup retired. Parsed traversal, fixed target, bounds, safe faults, retry,
  no mutation and cleanup are tested at the async Gremlin owner; exact key lookup at host.
- `libraries/azure-llm-compat/src/azure_llm_compat/{__init__,client,config,credentials,agent,streaming}.py`,
  its metadata/lock and `tests/{test_azure_llm,test_response_streaming,test_agent}.py`:
  raw SDK passthrough, provider IDs and duplicate tool/event loop deliberately retired.
  Native model library tests retain owner, authorization, schema, budget, terminal,
  cancellation and borrowed-resource checks; app tests exercise actual native boundaries.
- `libraries/search-read-adapter/src/search_read_adapter/{__init__,read,errors,keys}.py`,
  its metadata and `tests/{test_contract,test_read}.py`: synchronous Runner and error aliases
  retired. Canonical Search tests and host async knowledge tests own retained guarantees.
  Existing MITRE key bytes are preserved in the app's document schema, not a data facade.

Recovery: tracked source remains recoverable from git; no git reset, commit or branch
operation was performed. The protected untracked shared Search test remains user-owned.

## Integration Status

Implementation and focused checks are not full app or release acceptance. Parent-owned
`resource_explorer.probes` must drop its `azdata.graph_read` import and await injected graph
`element_count`, `sample`, and `aclose`. Optimizer dataset host needs public
`agent_optimization.LocalQueryError` and `SQLiteReader` exports, now supplied by that owner.
Root dependency enrollment, skill retirements and MCP distribution belong to parent.

No cloud mutation, inference, role grant, publication or data deletion authorized or run.
Live provider/model, restricted-identity and deployed-auth gates remain unverified. New
source must receive new artifact evidence; historical wheel hashes are never reused.

## Final Integration Evidence

Private environment: `/tmp/agentcraft-b02-b03-20260916`, Python 3.12.3. Neither app `.venv`
nor root workspace environment was synchronized. App-owned uv locks select OpenAI 3.13.0.
After physical deletion, `uv lock --check` is blocked because parent root workspace still
lists deleted `search-read-adapter`; parent must remove that member before final re-lock.

| Check | Observed Result |
| --- | --- |
| Full data library `python -m pytest libraries/azure-data-connectors/tests -q` | 182 passed, 271 subtests |
| Full model library `python -m pytest libraries/llm-interface/tests -q` | 48 passed, 48 subtests; obsolete legacy comparison removed |
| Optimizer app/deploy tests with existing source Bubblewrap executable | 74 passed, 18 subtests; no sandbox skips; includes CLI credential grant positive/refusal |
| Investigation frontend `npm test` and `npm run build` | 23 passed; production build passed |
| Optimizer frontend `npm test` and `npm run build` | 21 passed; production build passed |
| Final native Investigation host checks | 3 passed: success, schema refusal, authorizer refusal, owner result readback |
| Final native Optimizer prediction check | 1 passed: one model attempt, exact model refusal, owner session/terminal receipt |
| Clean Investigation complete app/deploy suite | BLOCKED: 8 collection errors from parent-owned `resource_explorer.probes` importing removed `azdata.graph_read` |
| Local launcher tests | Investigation 7 passed; Optimizer 6 passed |

The earlier integration run had 90 failures and 13 teardown errors before async fixtures
and obsolete request expectations were migrated. Named focused suites then passed: ADX 10,
graph domain 51, knowledge/classification/verifier 70, scanner/config/tools 29,
guard/evidence 19, lifecycle/auth 41, sessions/signed/editor 44, diagnosis 32, replay 7.
These are slice evidence, not a claim the final clean whole Investigation app passes.

### Live Local Observations

- Optimizer started through `LIVE_PYTHON=... deploy/deploy.sh local --source-root /home/hanchoong/perth_cyber`
  at frontend `http://127.0.0.1:5242`, API `http://127.0.0.1:9042`, inference denied.
- Two direct local snapshot API reads, before/after final restart, returned HTTP 200, one existing experiment and three saved
  versions, `Cache-Control: no-store, private`. Foreign Origin returned HTTP 401 with 0 body bytes.
- Existing `browser-verify` runner passed 6 Optimizer checks: saved versions, viewport
  geometry and CLI availability at 1440x900 and 390x844. Each viewport read three saved
  versions. Screenshots were inspected. Combined runner failed when reaching Investigation.
  Server log observed 6 browser GET reads and 4 credential-free terminal-info POSTs across
  those viewports. CLI availability is not an inference grant.
- Investigation startup printed frontend 5241/API 9041, then exited on the removed graph
  import. `verify --scan --data --api http://127.0.0.1:9041` failed connecting to `/healthz`
  before any service reads or JSON receipt. `CYBEREYE_DATA_WORKFLOWS=1` scanner browser
  runner recorded connection refused, 0 checks. No fake HTTP or data response was supplied.
- Current-source live ADX queries: 0; Cosmos traversals: 0; MITRE reads: 0; model calls: 0.
  Old Perth/graph/MITRE counts remain historical, not refreshed acceptance.

Logs/screenshots remain private under `/tmp/agentcraft-b02-b03-*`; no receipt/data/history
was deleted. No cloud mutation, key grant, model inference, publication or source checkout
modification occurred. Key-provider behavior was tested with native SDK-boundary fixtures,
not by retrieving a live key during this blocked acceptance.

### Parent Enrollment

- Root `libraries/pyproject.toml`: remove `search-read-adapter` member and obsolete
  `azure-llm-compat` exclusion/other references; regenerate root lock and profiles.
- Both apps replace legacy dependencies with `llm-interface[openai]==0.1.0a1`,
  `openai>=3.13.0,<3.14`; no raw-model package or sync Search facade remains.
- Investigation selects `azdata[kusto,search,identity,gremlin]==4.0.0a4`,
  `gremlinpython>=3.7.7,<3.8`, and host-owned `azure-mgmt-cosmosdb>=9,<10` for its explicit
  exact-target key provider. Existing pinned PyJWT 2.12.1 remains.
- Optimizer selects `agent-optimization==0.1.0a1`, `copilot-terminal-runtime==0.2.0`,
  `recoverable-jobs==1.0.0`; npm adds `@agentcraft/agent-optimization` and `copilot-terminal`
  from their library owners. App import adaptation never edits `app/components`.
- Resource Explorer must remove its old exception import, await injected graph
  `element_count`/`sample`/`aclose`, and preserve explicit failure categories without raw
  provider exception chains. Rebuild it, then rerun full Investigation and real data/browser gates.
- Parent retains skills/catalogue/MCP retirement and unified framework enrollment. No
  canonical library or app here imports an old skill runtime.

Additional retired test: `libraries/llm-interface/tests/test_existing_contracts.py` asserted
legacy-only signatures, quiet EOF acceptance and differing borrowed-client rules. Native
embedding/stream/ownership/allowlist/error tests replace its selected guarantees. App raw
Responses transport classes in `test_situation_summary_stream.py` were replaced with native
summary/no-retry/terminal tests. Stale provider-ID retry tests now assert no implicit replay.
Diagnosis tests now preserve later native errors after sink tools instead of suppressing them.

F1-F8 scope: existing typed descriptors/results/policies and native model types retained;
explicit identity/profile/grants, async cleanup, attempt/partial semantics and versioned native
events covered offline. No new framework/core/transport/tool-loop implementation was added.
Unified profile conformance, current Investigation live data, resource-token live graph,
restricted provider identity, deployed auth, real inference and provider/model compatibility
remain blocked or unverified. No full framework or release-readiness claim is made.

## Final Artifacts And Checks

Fresh model source snapshot, sdist and sdist-built wheel are under
`/tmp/agentcraft-b02-b03-final.kO4qYs/artifacts`; final data artifacts after packaged-guidance
correction are under `/tmp/agentcraft-b02-data-final.eQ2qFs/artifacts`. Builds used `uv build --no-sources` outside
the broken parent workspace. Final wheel installation was non-editable in the private
Python 3.12 environment. Final full library/app checks above ran against these wheels.

| Wheel | Runtime Python Files | SHA-256 |
| --- | --- | --- |
| `azdata-4.0.0a4-py3-none-any.whl` | 32 | `a787e51f88d65a7f4e531641277229a22283e3f5b934e4016aaf52ebf5af3bb4` |
| `llm_interface-0.1.0a1-py3-none-any.whl` | 8 | `fd39849ec11d93f3026e50ee1d9ca94e9200928f0eaabfe2f096409b86391d2b` |

Every runtime Python file matched current canonical source by SHA-256. Imports resolve
under `/tmp/agentcraft-b02-b03-20260916/lib/python3.12/site-packages`. All four retired
runtime imports are absent there. These are new artifact identities, not reused receipts.
Post-test record updates are not claimed to be inside the already-built sdists.

- AST scan: 214 owned Python files, zero legacy imports. Excluded other-owner
  `app/components/**` and protected untracked `template_apps/shared/tests/test_search_read.py`.
  That user test intentionally remains an external legacy-consumer exception; no deletion
  or rewrite was attempted. Repository-wide absence is not claimed while parent work remains.
- `uv pip check --python /tmp/agentcraft-b02-b03-20260916/bin/python`: 99 compatible packages.
- Current documentation check: 11 owned documents, 94 local file links, zero missing paths.
- `git diff --check` passed. Event-store history has no tracked diff. No commit or branch
  operation occurred. Retired-file removal required exact-path `rm` after two edit-tool
  deletion attempts reported success without deleting files; disk/artifact absence was then proved.
- Shared-terminal interference interrupted one final data rerun after 150 tests. Separate
  complete rerun passed 182 tests/271 subtests; interruptions were not counted as passes.

Reproduction commands from repository root, with the isolated interpreter substituted for `PY`:

```bash
PY=/tmp/agentcraft-b02-b03-20260916/bin/python
"$PY" -m pytest libraries/azure-data-connectors/tests -q
"$PY" -m pytest libraries/llm-interface/tests -q
CYBEREYE_PYTHON_SANDBOX=/home/hanchoong/perth_cyber/app/cybereye/.local/tools/bubblewrap/usr/bin/bwrap \
  "$PY" -m pytest -c template_apps/custom_optimizer/pyproject.toml \
  template_apps/custom_optimizer/app/cybereye/tests template_apps/custom_optimizer/deploy/tests -q
"$PY" -m pytest -c template_apps/investigation_app/pyproject.toml \
  template_apps/investigation_app/app/cybereye/tests template_apps/investigation_app/deploy/tests -q
npm --prefix template_apps/investigation_app/app/cybereye/frontend test
npm --prefix template_apps/investigation_app/app/cybereye/frontend run build
npm --prefix template_apps/custom_optimizer/frontend test
npm --prefix template_apps/custom_optimizer/frontend run build
```

The Investigation full-suite command intentionally remains blocked until parent fixes the
Resource Explorer dependency. Parent must also re-lock the app projects after removing the
retired root workspace member. The running Optimizer preview includes final CLI/model
grant refusal and stays at `http://127.0.0.1:5242`; no inference flag was passed.