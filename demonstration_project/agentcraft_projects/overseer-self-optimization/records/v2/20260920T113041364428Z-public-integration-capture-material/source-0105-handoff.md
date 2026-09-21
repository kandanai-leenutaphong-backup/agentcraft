# Public App Integration Checkpoint

Status: **needs-rescope**. Objective: complete local public-investigation vertical app integration.
Stage: exploring / data-understanding, local build-test. Next transition: exact UI pre-change
snapshot receipt, then finish source-aware UI and rerun signed browser acceptance. No follow-on
cloud assignment, scored comparison or v1.7 improvement is claimed.

## Pins And Authority

- Revision 8 before mutation: `e14a78eb975a5c651fa0d4c311e0854a22c72aa764705f40281fa900537cfaf1`.
- Revision 9 validated: `070cadee2c44731d1b984dafc906a6bba2f2797de1bd2530474ef5777b8c0e37`.
  First validation refused `decision_source` maxLength; historical prose was compressed and
  immediate repeat passed. Exploring status, separate public series and unfrozen scoring remain.
- Authorization receipt: `records/v2/20260920T105621430601Z-public-integrated-app-deployment-authorized/record.json`,
  SHA-256 `3baad87de19d58d0167896b3dc77a02e58d970ffff3763b83bacf37f5321e423`.
- Prestate receipt: `records/v2/20260920T105621593777Z-public-integrated-app-deployment-prestate/record.json`,
  SHA-256 `e6965a8775a73a7355920f5658f74bd1854598bc5d265d41a0345987cf60c2cf`.
  Verified all 90 present snapshots, including constitution, and 12 absent claims against disk;
  no initial drift. Mapping remains `changes[].path -> changes[].before.snapshot`.
- Candidate dispatch: none required or performed. Artifact is application source, not a newly
  invoked candidate agent. Max effort requested; effective runtime effort unverified.

## Implemented

Hypothesis: an explicit source profile can bind production composition, scanner, routes, tools,
inventory and graph to one evidence-preserving public Cosmos service, retaining legacy ADX defaults.
Source/service/route tests support this locally; complete UI acceptance remains unfinished.

- New app owners: `backend/data/telemetry.py`, `backend/data/public_graph.py`,
  `backend/investigation/public_detector.py`, `backend/agents/tools/public.py`.
  Production main selects them, not a detached demo service. Public tools and HTTP share instances.
- Fixed partition/entity/time/evidence queries through public async `azdata`; no alternate transport
  in production and no KQL-to-SQL conversion. Raw queries, writes, target overrides and unknown/foreign
  IDs refuse. Native Cosmos mutation/target policy checks run before credential acquisition.
- Normalization predicate exported through ontology public API and reused by public detector.
  One observed Sysmon rule; unsupported legacy rules excluded from the public roster.
- Separate app-owned public roster, prompt and inventory. Editor required evidence tool follows
  the selected roster; owner/CAS storage was not rewritten. No roles or skills changed.
- Generic Cosmos inventory extension stays in `resource_explorer` public probes and closed
  Python/React contracts. App owns domain-specific package/source integrity.
- Public board supports actual case -> derived alarm -> event -> exact host/user/process graph
  -> source readback. Existing graph canvas supports Process, source objects and clickable evidence.
  Public ambiguous-name matches are not selected automatically; explicit IDs select the node.
- Config requires explicit Cosmos coordinates and pinned manifest bytes. Dependency extra and
  lock updated offline for `azure-cosmos==4.17.0`; no installs, environment creation or activation.
- Existing ingestion and normalized package owner remain unchanged; source lock and raw payload
  untouched. Two real events, one derived case/alarm, ten vertices, nineteen edges and 3,135
  official advisory MITRE documents remain smoke coverage, not incident ground truth.
- Documentation updated in root/app README, app architecture, app deployment runbook and env example.
  New runner assigned to existing acceptance boundary.

New verification/presentation paths, relative to app root:

```
app/cybereye/control/public_agent_config.yaml
app/cybereye/control/public_data_inventory.yaml
app/cybereye/control/prompts/public/investigation.md
app/cybereye/frontend/src/features/investigation/publicApi.ts
app/cybereye/frontend/src/features/investigation/PublicCases.tsx
app/cybereye/frontend/src/features/investigation/publicCases.css
app/cybereye/frontend/tests/browser/verify-public-investigation.mjs
app/cybereye/tests/test_cosmos_telemetry.py
app/cybereye/tests/public_runtime.py
app/cybereye/tests/public_browser.py
deploy/tests/public_integration_runner.py
```

## Checks And Failures

All paths below are relative to this evidence directory. Command receipts retain actual argv,
cwd, timestamps, elapsed seconds, exit status and complete captured stdout/stderr. Counts from
overlapping checks are not additive.

| Evidence | Observed Outcome | SHA-256 |
| --- | --- | --- |
| `20260920T112245850767Z-command.json` | Final scoped backend gate: 286 passed; three dependency warnings | `b04a2d0627df71620d346fc5bfdba54c1d436df978f19ed0ffa60948884701d3` |
| `20260920T112256295932Z-command.json` | Existing frontend tests: 29 passed | `7be2c48a170f9dd9ca9ed02bf148b824f7472ec35259d4258bd870e8ff1aa185` |
| `20260920T111717051962Z-command.json` | Production `tsc -b && vite build`: passed; large-chunk warning retained | `ca28a1399fbdb33b0dda2411a379fb47172571700a4ab9b2ee1af36d9a3f5181` |
| `20260920T112214437601Z-command.json` | Architecture: 189 source files, 487 resolved edges, no violations; 14 unowned files reported | `6ec929cbd82ed3c6e462c9017988b4f7a73c8d7e2c4a34c199bb4a8fdb62b77c` |
| `2026-09-20T11-17-28-057Z-browser/report.json` | 21 checks passed and ten screenshots; overall FAILED on two `/api/whoami` 404s | `38da3952ccc1eb8d478bfc0c397a4e4bbcba5f04f8ef5c8c4983da78ca60c3a0` |
| `snapshot-request.json` | Exact minimum unmodified UI snapshot request | `77b8f2c162128e8b34c19b564b85bb7a61aaccd1f79b13cc38f00494a5b6e939` |

Browser observed 1440x1000 and 390x844: actual case/alarm/event selection, host/user/process graph,
evidence return, provenance readback, keyboard focus, nonblank graph and measured nonoverflowing
public board geometry. Source data is real; store adapters are synthetic. Production lifespan,
routes, signed authorization and native Search keyed reads are exercised. This is not native
Cosmos SDK network I/O, deployed Entra login, a populated cloud Search index or model acceptance.

Retained failures/retries:

- System Python lacked `azdata`; existing app interpreter lacked `agentcraft_core`. Existing
  `/tmp/agentcraft-investigation-browser-env/bin/python` supplied current app dependencies except
  Cosmos SDK. Historical wheel runtime lacked required native packages. Nothing installed.
- First frontend build caught missing Profiles callback; repaired, build passed.
- Signed-route fixture passed duplicate Search transport keyword; repaired, route checks passed.
- First browser run timed out after 180 seconds with no useful startup capture. Fixture incorrectly
  emitted readiness after failed startup and had unconfigured model endpoint in its test binding.
  Repaired startup/readiness/error capture, bounded fetch and owned process-group timeout cleanup.
- Browser found `[object Object]` graph provenance and blank graph times; repaired source rendering
  and evidence-derived times. Desktop/mobile journey checks then passed; `/api/whoami` still failed.
- Final broader gate initially found two lifecycle fixtures missing `telemetry_profile`; updated
  fixture to explicit legacy `adx`, reran narrow checks and final 286-test gate successfully.
- Public scenario bounds corrected for minute-resolution controls; fractional event boundary gets
  its own negative test. Browser has not rerun after that backend-only fix.

## Blocking UI Findings

1. Public profile still renders “Scan ADX window”, ADX/KQL explanations, legacy date and firewall
   starter prompts. Screenshot `2026-09-20T11-17-28-057Z-browser/desktop-source.png` records this.
   Owning files App.tsx, ScannerPanel.tsx and ChatPanel.tsx were absent from supplied prestate.
   They remain unchanged. `snapshot-request.json` carries exact paths, hashes and bounded changes.
2. Signed-only offline fixture does not compose the existing Entra-owned `/api/whoami` handler.
   Requests therefore return 404. Do not bypass auth or fake a successful identity response;
   compose the existing protected handler in the test runtime and rerun browser checks.
3. Actual scanner button flow and native agent dispatch using public tools need final browser/native
   acceptance after UI binding. Direct public tool callables and their real native roster wiring are
   tested; no fresh candidate invocation or external model execution was performed.

Remaining local risks: native Cosmos SDK request mapping not exercised in the installed browser
runtime; graph semantic edge tampering beyond source/identity/evidence checks and mixed timestamp
formats beyond this exact smoke package need focused review. Legacy browser suite was not rerun.
No claim of full application acceptance, complete open-source audit, remote deployment or gains.

## Deployment And State Handoff

Exact requirements are in app `deploy/README.md#public-integration-checkpoint`.
No cloud writes or credential retrieval in this assignment. Future target is tenant
`c79ab2bb-79cb-47f1-b4da-b6852fe45ff7`, subscription `67255afe-8670-4401-a1b8-df6ca63a3516`,
`rg-agentcraft-dev`, `australiaeast`; selected scoped service/ingest/app-state/ACR/model grants
and single-tenant sign-in still require effective preflight. Model reuse
`han-primary-foundry-resource` / `gpt-5.6-luna` availability remains unknown.

Preserve authored agent directory and its parent SQLite profile file on a durable volume with
verified POSIX locks, hard links, atomic replacement and SQLite transaction semantics. One active
writer/replica, controlled rollout, restart readback; no assumed network-volume compatibility.
Agent file store has no directory fsync and is not a crash-durable database. Existing Entra
flows/sessions require Azure Table storage. Signed replay requires a real shared Azure Table
ledger: one replica is not replay protection. Chat sessions, scan caches and evidence grants
remain ephemeral/owner-bound. No unrelated state framework changed.

Pending deployment artifacts: exact image/library dependency pins, production frontend, notices,
manifest/config, idempotent Cosmos/Gremlin/Search loader and graph JSON property encoding, workload
identity/data-plane grants, ACR pull, HTTPS sign-in/session/replay configuration, protected rollout
and external authenticated readback. Root cloud engine was not edited.

## Capture And Settlement

- Primary evidence only; no writes to `records/v2`, no notebook publication, no support-role or
  candidate dispatch. Overseer owns archival publication and after-state snapshot request.
- Tool reads/searches/edits and initial pin checks are observable in host session trace, but not
  exported as a complete action ledger here. Initial constitution validation failure and early
  runtime probes are summarized above; exact timing/cost for those actions is unknown.
- Selected loaded skills and source hashes are in final backend command receipt. Root architecture
  document was absent; app architecture was read. Full artifact source-manifest receipt follows.
- Browser screenshots and report are read back; last server reports `settled: true`, exit code 0.
  Task-owned servers are not retained. Existing unrelated local servers were not stopped.
- No virtual environment created or activated. Existing interpreter executable used directly.
- No reversion performed; retained prestate mapping verified, live restore remains `not_verified`.
- Smallest next decision: overseer obtains three exact UI snapshots and assigns continuation under
  unchanged local/no-cloud/no-model bounds. This packet requests that checkpoint, not wider authority.