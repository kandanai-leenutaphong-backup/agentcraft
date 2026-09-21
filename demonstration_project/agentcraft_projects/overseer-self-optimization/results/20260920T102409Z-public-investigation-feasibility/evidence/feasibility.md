# Public Investigation Feasibility

Non-authoritative orchestrator evidence. Read-only assignment complete; implementation, acquisition, redistribution and deployment remain gated. No comparative improvement claim.

## Assignment And Pins

- Workspace: `/home/hanchoong/agentcraft`.
- Constitution: `demonstration_project/agentcraft_projects/overseer-self-optimization/constitution/constitution.yaml`, revision 7, SHA-256 `b2b59aebc22e8205f66586ca18d8c0aa8efcd60ab05465816806606ed04487ff`, verified at first terminal observation `2026-09-20T10:24:09Z`.
- Authority: this user assignment permits local source inspection and small public metadata research, plus new evidence here. Revision 7 does not authorize the new Cosmos/Search/cloud objective. No candidate invoked; candidate version pin not supplied for this assignment. Effort requested: max; effective effort: unverified. Costs and total elapsed effort: unknown.
- Intended future target: new `rg-agentcraft-dev`. No Azure commands requested by this worker. Several terminal responses contained unrelated concurrent Azure output; discarded, not treated as verification of any resource, permission or action.
- Stage: investigate / data-understanding feasibility. Next transition: overseer revises constitution, settles source rights and dispatches archivist for exact dirty-source before snapshots; then authorizes one acquisition/join probe. No automatic build or rollout.
- No model calls, payload downloads, source edits, dataset writes, commits, deletion, environment creation/activation, repository publication or cloud mutation requested. Only these evidence files added. No workers or resources spawned.

## Controlling Contracts

All source paths below are workspace-relative. Findings are from source inspection unless explicitly marked executed.

| Contract | Exact Owner | Observation / Minimum Change |
| --- | --- | --- |
| Composition and required source | `template_apps/investigation_app/app/cybereye/backend/main.py:41`; `backend/config.py:21` under that app | Production constructs `ReadOnlyAdx`, injects it into scanner and agent, and requires ADX plus model endpoint. Replace telemetry binding with the Cosmos-backed application service; do not retain a fake ADX endpoint just to pass startup. Keep borrowed credential and close ordering. |
| Bounded queries | `template_apps/investigation_app/app/cybereye/backend/data/adx.py:99` | Existing service accepts KQL rooted at configured tables. NoSQL is not a config-only switch and must not accept KQL under an SQL label. Reuse envelopes/bounds, replace query implementation and caller contracts. |
| NoSQL reuse owner | `libraries/azure-data-connectors/CONTRACT.md`; `src/azdata/adapters/cosmos.py:16` within that library | Public `connect("cosmos", ConnectorConfig(...), credential=..., policy=...)`, explicit database/container/top-level partition field; `ReadRequest`, `QueryRequest(dialect="cosmos-sql")`, parameter names `@name`, query option `cosmos.partition`. Native partitioned CRUD and replace-upsert, conditional replace, readback; no schema/provision, transactional batch or persistent continuation guarantee. Add app's missing `cosmos` dependency extra; no duplicate Cosmos transport. |
| Evidence IDs | `template_apps/investigation_app/app/cybereye/backend/agents/tools/base.py:28`; `backend/api/scanning.py:105` | `resource_id` is the telemetry citation key; route rebuilds a situation from window if absent in owner cache, then reads up to 100 rows. Existing projection lacks process GUID/parent and structured scenario/entity references. Add explicit bounded evidence lookup through same service used by tools. |
| Cosmos key mismatch | `libraries/azure-data-connectors/src/azdata/adapters/cosmos.py:67`; `template_apps/investigation_app/app/cybereye/frontend/src/shared/ui/ResourceChip.tsx:5` | Cosmos item `id` rejects `/`; UI citations expect `event://...`. Keep Cosmos-safe document ID separate from stable `resource_id`, with deterministic partition-aware resolution. ResourceChip only expands/copies; it is not a record-detail reader. |
| Scanner | `template_apps/investigation_app/app/cybereye/backend/investigation/detector/engine.py:177`; `detector/rules.py:38` | Generic battery is reusable. Domain execution calls `adx.parameterized(entry["query"], ...)`; rules include CyberArk and Defender Graph-alert predicates not justified by selected public data. Replace active detector declarations with source-supported rules, retain explicit derivation/version/evidence semantics. Do not translate KQL heuristically. |
| Situation identity | `template_apps/investigation_app/app/cybereye/backend/investigation/detector/engine.py:47` | ID hashes host/principal/first time, not dataset revision or scenario. Add scenario/revision-qualified identity before combining datasets. Derived situations are not original incident labels. |
| Tool binding and policy | `template_apps/investigation_app/app/cybereye/backend/agents/tools/activity.py:25`; `tools/raw_kql.py:14`; `tools/base.py:51`; `agents/service.py:94`; `control/prompts/foundation/tool_policy.md` | Tools bind directly to ADX and fixed telemetry columns. Purpose-built tools preferred; arbitrary KQL fallback is explicitly subordinate. Keep curated purpose-built operations; remove fallback from Cosmos roster or replace only with separately bounded/authorized SQL surface and matching negative tests. Do not broaden permissions to ease migration. |
| Tool/model allowlist | `template_apps/investigation_app/app/cybereye/backend/agents/config.py:122`; `control/agent_config.yaml` | Local module prefix and strict config resolution exist; model is hardcoded to `gpt-5.6-luna`. Make supported deployment/model selection explicit at edge; public source does not confer access to this model. Retain default inference denial and current-turn evidence ledger rules. |
| Source catalogue | `template_apps/investigation_app/app/cybereye/backend/inventory/sources.py:57` | `/api/cyber/sources` is descriptive/probed; declaration is explicitly not proof a tool uses it. Telemetry source points to `app.state.adx` / `ToolContext.adx`. Update descriptions, health and bindings together. |
| Inventory allowlist | `template_apps/investigation_app/app/cybereye/backend/inventory/manifest.py:49`; `inventory/probes.py:14`; `control/data_inventory.yaml` | Separate inventory manifest only supports adx_table/gremlin_graph/search_index/local_table. Adds no NoSQL preview merely by adding a catalogue row. Extend source type/probe at reusable resource-explorer owner and compose in app. Replace Perth/AIT declarations with public-source identities. |
| Shared inventory contract | `libraries/resource-explorer/src/resource_explorer/backend/contracts.py:65`; `backend/registry.py:25`; `frontend/wire.ts:32`; `frontend/status.ts:108` | Both backend and frontend closed type sets require a Cosmos container type. This is a real cross-package follow-up, not an app-only string substitution. |
| Gremlin binding | `template_apps/investigation_app/app/cybereye/backend/data/graph_binding.py:12` | Fixed account/db/graph, query-only policy, ARM `list_read_only_keys` for exactly configured target. NoSQL Entra credential does not authenticate Gremlin traversal. Keep key in memory or design an explicitly authorized Key Vault-reference alternative. No keys read in this assignment. |
| Graph drilldown | `template_apps/investigation_app/app/cybereye/backend/data/graph.py:30`; `backend/api/graph.py:28` | Existing entities/node/selection/search routes reusable; node IDs passed as traversal bindings. Core/mention labels omit Process. Event edges carry 15-minute buckets, not exact event membership. No shared-source revision check with telemetry. Add scenario-qualified IDs, process vocabulary, source revision and evidence membership; preserve bounds/404 vs 503. |
| Ontology owner | `template_apps/investigation_app/app/data/ontology/{canonical.py,model.py,build.py}` | Builder hashes source export and counts families, but existing canonicalization folds host FQDN to short name and account identity to base name ignoring realm. Node ID slug truncates; edge ID derives endpoints/label. Reuse owner, extend for public Windows records; do not merge equal host/user names across scenarios/domains. |
| UI entity links | `template_apps/investigation_app/app/cybereye/frontend/src/shared/ui/EntityMentions.tsx:27` | Matches lowercased display names, resolves duplicate name by highest event_count, ignores names shorter than 3 and classes outside allowlist. This cannot safely select same-named principals/processes. Explicit IDs in structured result rows must take precedence; ambiguous prose must not silently pick an entity. |
| MITRE Search | `template_apps/investigation_app/app/cybereye/backend/knowledge/search.py:28` | Fixed Search connector, `analytic`/`situation_type` slices, bounded queries, deterministic keyed read and identity checks, no local fallback. Preserve `doc_id`, `native_id`, `attack_url`, `path`, `commit`, `license`, `retrieved_at`; add release/digest linkage. Retrieval is advisory, never telemetry evidence. |
| Search publishing gap | `template_apps/investigation_app/app/cybereye/tests/test_knowledge_documents.py`; `docs/ARCHITECTURE_OVERVIEW.md` | Projection helper is test-owned; removed publishing stack is not a production ingestion entry point. Test fixture's CC-BY-4.0 is not MITRE's license. Add bounded official-STIX projection/publication procedure using public azdata Search APIs, not imported test code. |
| Deployment | `template_apps/investigation_app/deploy/README.md:3` | Existing cloud entry point is offline plan/package only; apply/verify/teardown refuse. Old isolated target is not new grant. Durable SQLite profiles/agent files and durable auth/session/replay storage remain unresolved. Need protected production image, managed identity, exact inventory, readback and restart/ownership refusal gates. |

## Public Data And Rights

**Chosen source hypothesis: OTRF Security-Datasets / Mordor APT29 day 1**, Windows emulation at commit `d9d40ef123d2c87d5d3df28c96bcab4f0faccc87`. Best inspected fit for coherent multi-stage host/user/process investigation. Technically viable candidate, not yet cleared for redistribution or measured joins. No unrelated netflow substituted as incident truth.

Exact evidence URLs:

1. Source revision: https://api.github.com/repos/OTRF/Security-Datasets/git/ref/heads/master (observed commit above).
2. Canonical license, fetched at pinned commit: https://raw.githubusercontent.com/OTRF/Security-Datasets/d9d40ef123d2c87d5d3df28c96bcab4f0faccc87/LICENSE . MIT; copyright 2021 Open Threat Research Forge; copyright and permission notice must accompany copies/substantial portions.
3. Conflicting README: https://github.com/OTRF/Security-Datasets/blob/d9d40ef123d2c87d5d3df28c96bcab4f0faccc87/README.md . Read master bytes; pinned directory metadata identifies README blob `43ff5ec0712d450b3dba92f036f6788cf6d99e9a`. MIT badge but GPL-3.0 footer. Do not silently call this dual licensing or assume the footer is obsolete. Obtain documented resolution of selected archive coverage before redistributing; public access alone is insufficient.
4. Scenario description: https://raw.githubusercontent.com/OTRF/Security-Datasets/d9d40ef123d2c87d5d3df28c96bcab4f0faccc87/datasets/compound/apt29/README.md . Publisher states activity replicates ATT&CK evaluations, not an actual victim incident. Scenario workbook is separately linked; its rights/contents not inspected, so do not bundle it by inference.
5. Day-1 source metadata: https://raw.githubusercontent.com/OTRF/Security-Datasets/d9d40ef123d2c87d5d3df28c96bcab4f0faccc87/datasets/compound/apt29/day1/README.md . Describes host audit configuration, Sysmon v11/4.30, Windows Security, PowerShell and WEF; documents `Channel`, `EventID`, Sysmon 1/3/10 and Security 4624/4688 among others. Parent/day README timestamps and counts disagree. Those are publisher statements, not measurements of archive contents.
6. Archive metadata only: https://api.github.com/repos/OTRF/Security-Datasets/git/trees/a8137f65b514dcff04265c12f10bdbb0fd5e13a6 . `apt29_evals_day1_manual.zip` Git blob `7352679a173ec0310f9d0ed587782545182dd394`, API size 13,944,973 bytes. README says 367M; meaning unverified. SHA-256 and extracted member hashes unknown, no archive fetched.
7. Future acquisition URL, **not fetched**: https://raw.githubusercontent.com/OTRF/Security-Datasets/d9d40ef123d2c87d5d3df28c96bcab4f0faccc87/datasets/compound/apt29/day1/apt29_evals_day1_manual.zip . Must use saved acquisition owner, byte/uncompressed/member limits, path-traversal refusal, source/transform digests and explicit authorization. Never execute embedded commands or follow lab credential links.
8. Alternative examined only for license: https://raw.githubusercontent.com/splunk/attack_data/master/LICENSE . Apache-2.0 with Splunk 2023 designation; distribute license, retain relevant notices, mark changes and include upstream NOTICE if present. Scenario-level coverage, revision and metadata not inspected. This is a fallback lead, not a substitute certified corpus or permission for third-party material.

**Supported versus proposed fields:** only Channel/EventID and channel/event-family summaries observed in source metadata. Required probe candidates: `ComputerName`/`Computer`, provider/channel, `EventID`, `EventRecordID`, `UtcTime`/`TimeCreated`, `ProcessGuid`, `ParentProcessGuid`, `ProcessId`, `Image`, `CommandLine`, `User`, SID/domain, `LogonId`/`LogonGuid`, `SourceProcessGUID`/`TargetProcessGUID`, source/destination IP. Actual spelling, presence, null rates and timezone semantics remain unknown until authorized row inspection. Use scenario + host + ProcessGuid for process identity; PID alone cannot survive reuse. Scope LogonId to host/session; names alone are not authoritative joins. Preserve unresolved relations rather than invent them.

**Labels:** incident is a derived emulation-case wrapper with `ground_truth_kind=emulation_scenario`; original scenario/technique narrative remains attributed. Alarm is derived by our versioned deterministic rule with matched `resource_id`s, not original EDR/SIEM output. Whole scenario membership does not label every event malicious. No original alarm labels, per-event attack labels, incident recall, production false-positive rate, real victim attribution or comprehensive attack coverage demonstrated. Any inspected scenario becomes development evidence, not hidden evaluation.

**Cheap discriminating experiment, next authorized increment:** acquire only pinned day-1 host archive after rights/snapshot gate; inventory all member names and hashes safely, then inspect a bounded process-creation/access/logon window. Measure missing identity/time fields, duplicates, ProcessGuid/ParentProcessGuid coverage and same-host user joins. Require at least one source-supported host-user-process chain with resolvable evidence and one negative collision case (same username in another domain/scenario or PID reuse) that stays separate. Derive one alarm from actual records, then prove case -> alarm -> every event -> graph vertex/edge resolves to the identical source revision and raw location. Incomplete windows/truncation must be explicit. No invented thresholds or full-corpus claims. If source cannot support a join, reduce the claim or select another source before building UI.

## MITRE Knowledge Pin

- Official repository: https://github.com/mitre-attack/attack-stix-data . Selected release v18.0, not claimed latest.
- Tag: https://api.github.com/repos/mitre-attack/attack-stix-data/git/ref/tags/v18.0 -> annotated tag `5fd30fbc78c67b87dbee673625ab57d87eae3994`.
- Tag object: https://api.github.com/repos/mitre-attack/attack-stix-data/git/tags/5fd30fbc78c67b87dbee673625ab57d87eae3994 -> commit `b4c5d044bf5a5f117ec241b2536c8cb709f53cdc`; API reports unsigned tag. Immutable identity is not a cryptographic publisher signature.
- Pinned license fetched: https://raw.githubusercontent.com/mitre-attack/attack-stix-data/b4c5d044bf5a5f117ec241b2536c8cb709f53cdc/LICENSE.txt . Nonexclusive royalty-free ATT&CK license for research/development/commercial use, provided copyright designation and license reproduced. Preserve exact 2025 notice in release artifacts: copyright 2025 The MITRE Corporation; work reproduced/distributed with MITRE permission. Current master inspected separately says 2026; do not substitute it for release notice. Not MIT, Apache or CC BY. Trademark/endorsement rights not inferred.
- Proposed bundle: `enterprise-attack/enterprise-attack.json` at that commit, not fetched; SHA-256/counts/types unverified. Before ingestion verify STIX version, object IDs/modified times, revoked/deprecated filtering, relationships, attack-pattern/tactic and detection-strategy/analytic support. Do not fabricate analytics for missing types. Keep complete license/disclaimers with permitted derived documents and source manifest; index documents carry provenance, not a misleading license shorthand.
- Keep MITRE content outside incident truth. Search matches characterize techniques; no assertion that activity occurred or was malicious. Do not copy linked third-party reports under MITRE terms.

## Smallest Implementation Sequence After Authority

1. **Acquisition/contract slice first, no cloud:** extend existing ontology owner with one public-record normalizer and canonical identities; save pinned source/license manifest and a repeatable bounded acquisition/probe entry under app deploy. Tests use sanitized licensed fixtures or explicitly synthetic structural fixtures; real-scenario gate uses approved inputs. No full source migration before discriminating probe passes.
2. **One vertical case:** app-owned Cosmos telemetry/evidence service using azdata public APIs; case/alarm/event records with scenario/revision partition, fixed projections and bounded parameterized queries; one supported detector and evidence route/tool; graph derived only from exact normalized records. Keep `resource_id` separate from Cosmos `id`. Do not build an arbitrary KQL-to-SQL compiler. No claims of all old detectors working.
3. **Drilldown:** shared typed entity/event references passed scanner -> API -> result rows -> graph selection -> exact event detail. Add Process and case/alarm relationships, graph source digest/generation, matching scenario/window filtering, stable pagination and visible truncation. Do not use lossy display-name selection as identity. Prove unknown ID, foreign scenario, missing event and stale graph revision refuse. Retain 15-minute aggregation labeling or implement exact event-window reads; never present bucket membership as second-accurate evidence.
4. **Knowledge and catalogue:** project-owned STIX projection/publication through azdata Search; preserve existing keyed-document contract. Extend resource-explorer Cosmos type/probe once; update app catalogue/allowlist/tool metadata. Remove unused private defaults from public profile, not historical evidence.
5. **Protected deployment:** implement app deploy entry for new RG with NoSQL account + Gremlin-capable account, Search, image/identity/auth/durable-state dependencies. Do not assume one Cosmos account serves both APIs. Freeze exact inventory/region/subscription/quota/cost bounds with overseer. Separate ingestion writer from read-only app identity. Existing Gremlin connector cannot load edges; explicitly scoped deployment loader must own fixed, idempotent vertex/edge writes or an authorized shared connector extension must add that capability. Do not weaken query-only runtime policy. Verify graph IDs/counts/provenance and NoSQL readbacks, Search exact citations, restart/state/owner/refusal behavior through authenticated ingress.
6. **Only then AgentCraft:** freeze deployed image/data/knowledge/graph generations, task/split/evaluator/acceptance, candidate version and model authority; baseline with fresh invocation. New objective starts new comparison series, not continuation of netflow scores.

## Snapshot And File Proposal Manifest

Before any source mutation, overseer/archivist must snapshot exact working-tree bytes, not HEAD. Existing dirty files observed at start include root/demo READMEs, constitution, lessons, dataset scripts and new project results/records; this worker did not alter them. No archival receipt supplied here.

Proposed existing-file allowlist for the **vertical implementation** (review/snapshot before assignment; not a current write grant). Prefix `A=template_apps/investigation_app/`:

```text
Aarchitecture.json
Adocs/ARCHITECTURE_OVERVIEW.md
AREADME.md
Apyproject.toml
Auv.lock
Aapp/cybereye/.env.example
Aapp/cybereye/backend/config.py
Aapp/cybereye/backend/main.py
Aapp/cybereye/backend/data/__init__.py
Aapp/cybereye/backend/data/graph.py
Aapp/cybereye/backend/data/graph_binding.py
Aapp/cybereye/backend/models.py
Aapp/cybereye/backend/api/data_sources.py
Aapp/cybereye/backend/api/scanning.py
Aapp/cybereye/backend/api/graph.py
Aapp/cybereye/backend/investigation/scanner.py
Aapp/cybereye/backend/investigation/detector/engine.py
Aapp/cybereye/backend/investigation/detector/rules.py
Aapp/cybereye/backend/investigation/detector/composition.py
Aapp/cybereye/backend/agents/config.py
Aapp/cybereye/backend/agents/service.py
Aapp/cybereye/backend/agents/tools/base.py
Aapp/cybereye/backend/agents/tools/activity.py
Aapp/cybereye/backend/agents/tools/evidence.py
Aapp/cybereye/backend/inventory/sources.py
Aapp/cybereye/backend/inventory/manifest.py
Aapp/cybereye/backend/inventory/probes.py
Aapp/cybereye/control/data_inventory.yaml
Aapp/cybereye/control/agent_config.yaml
Aapp/cybereye/control/agents/cyber.yaml
Aapp/cybereye/control/situation_detector.json
Aapp/cybereye/control/prompts/foundation/tool_policy.md
Aapp/cybereye/control/prompts/foundation/historical_replay.md
Aapp/data/ontology/__init__.py
Aapp/data/ontology/canonical.py
Aapp/data/ontology/model.py
Aapp/data/ontology/extract.py
Aapp/data/ontology/build.py
Aapp/cybereye/frontend/src/shared/types.ts
Aapp/cybereye/frontend/src/shared/api/api.ts
Aapp/cybereye/frontend/src/shared/ui/EntityMentions.tsx
Aapp/cybereye/frontend/src/shared/ui/ResourceChip.tsx
Aapp/cybereye/frontend/src/features/investigation/ToolBoard.tsx
Aapp/cybereye/frontend/src/features/graph/GraphPanel.tsx
Aapp/cybereye/tests/test_tool_query_binding.py
Aapp/cybereye/tests/test_sources.py
Aapp/cybereye/tests/test_data_inventory.py
Aapp/cybereye/tests/test_detector_engine.py
Aapp/cybereye/tests/test_ontology_graph.py
Aapp/cybereye/tests/test_graph_service.py
Aapp/cybereye/tests/test_knowledge_documents.py
Aapp/cybereye/tests/test_knowledge_search.py
Aapp/cybereye/frontend/tests/browser/verify-native-investigation.mjs
libraries/resource-explorer/src/resource_explorer/backend/contracts.py
libraries/resource-explorer/src/resource_explorer/backend/registry.py
libraries/resource-explorer/src/resource_explorer/probes.py
libraries/resource-explorer/frontend/wire.ts
libraries/resource-explorer/frontend/status.ts
```

`A` above is literal shorthand, not executable paths: e.g. `Aarchitecture.json` means `template_apps/investigation_app/architecture.json`. File existence/bytes not read for every adjacent proposal; snapshot preflight must distinguish present from absent and return exact digests. ReadOnlyAdx can remain for an explicitly selected legacy profile; it must not be silently invoked by the public profile. No deletion authorized. Confirm graph writer choice before adding any library mutation paths.

Exact proposed new files, absent status to verify before creation:

```text
template_apps/investigation_app/app/data/ontology/public_windows.py
template_apps/investigation_app/app/cybereye/backend/data/telemetry.py
template_apps/investigation_app/app/cybereye/backend/knowledge/documents.py
template_apps/investigation_app/app/cybereye/tests/test_public_attack_data.py
template_apps/investigation_app/app/cybereye/tests/test_cosmos_telemetry.py
template_apps/investigation_app/deploy/public_data.py
template_apps/investigation_app/deploy/public_sources.lock.json
template_apps/investigation_app/deploy/env/agentcraft-dev.json
template_apps/investigation_app/deploy/infra/main.bicep
template_apps/investigation_app/THIRD_PARTY_NOTICES.md
```

New source-normalizer stays under existing ontology boundary; no app import in library. Snapshot `deploy/deploy.sh`, `deploy/cloud.py`, `deploy/README.md`, `deploy/tests/test_cloud.py`, `deploy/verify.py` before later deployment increment; cloud template alone is not a runnable release. Root README only when new feature makes current claims wrong. Constitution/dataset manifest/records/lessons remain overseer/support-owned, not this worker's changes. Lock updates only with a separately authorized dependency operation; no environment created here.

## Verification And Runnable Checks

Executed offline, exact existing system interpreter; first attempt without shared foundation failed import. Retry:

```bash
cd /home/hanchoong/agentcraft/libraries/azure-data-connectors
PYTHONPATH=src:../framework-core/src python3 -B -m unittest tests.adapters.test_cosmos -v
```

Result: **18 tests passed, unittest elapsed 0.155s**. Scripted transport; no cloud, models or data writes. Covers required partition, partition mismatch, native create/upsert, conditional versions, no retry on write/conflict, content readback, bounded read attempts, unknown/unattempted outcomes, partition-scoped continuation and SQL mutation refusal. Does not validate new app integration, dataset or resource permissions.

After dependencies are available in an already provisioned interpreter, focused existing checks (not executed here; no setup/uv sync implied):

```bash
cd /home/hanchoong/agentcraft/template_apps/investigation_app
PYTHONDONTWRITEBYTECODE=1 python3 -B -m pytest -p no:cacheprovider app/cybereye/tests/test_tool_query_binding.py app/cybereye/tests/test_sources.py app/cybereye/tests/test_data_inventory.py app/cybereye/tests/test_graph_service.py app/cybereye/tests/test_knowledge_search.py app/cybereye/tests/test_knowledge_documents.py -q
python3 -B -m unittest deploy.tests.test_cloud -v
```

System Python observed 3.12.3; pytest/azure/fastapi available, azdata/agentconfig not installed. Pylance selected interpreter unknown. Do not treat test collection or source package availability as production build acceptance. Existing browser runner builds/writes fixtures and starts a server, so not run under this read-only assignment.

Proposed focused gates after implementation: `test_public_attack_data.py` deterministic IDs/raw provenance/no domain collision, missing-field refusal, real source chain and derived alarm labeling; `test_cosmos_telemetry.py` bounded partition/scenario/time filters, URI-to-key resolution, mutation/alternate-target refusal, idempotent loader/readback and restart behavior; extend graph/knowledge/inventory tests rather than duplicate their infrastructure. Native signed browser journey must open incident -> alarm -> event -> host/user/process graph -> exact event readback at desktop/mobile, preserving same revision and window. Match unknown/foreign IDs, revoked caller, stale graph, truncation and unavailable source refusals. Deployment acceptance must use production lifespan and authenticated ingress, not synthetic fixture server. No such new tests exist or passed yet.

## Publication And Blockers

- Root and inspected library licenses are MIT; root notice names Microsoft. App Python dependencies include local `template_apps/shared` and framework-core, situation-detector, entra-auth, signed-dev-access, resource-explorer, llm-interface, modular-agents, azdata. Frontend file dependencies additionally include event-stream/source-code. Ship permitted sources/notices or independently reproducible pinned package artifacts; copying app folder alone is insufficient. Complete transitive license/SBOM/artifact audit not performed.
- Frontend `private: true` prevents npm publication, not source openness. Azure services and model remain external hosted dependencies; open source does not promise free, offline, unauthenticated or unrestricted access. No repo visibility or release action authorized.
- Private-default risks confirmed: PerthCyber/airportgraph/model literals, Perth/AIT inventory, legacy model hardcoding, private original-data test gates, historical receipts and local state. Review source-package allowlist and Git history separately before any publication; do not publish private data, authored state, credentials or historical screenshots. No credential values inspected or retained intentionally.
- Blocking next implementation: versioned constitution and assigned writable paths; archival before receipt; resolved dataset rights; saved acquisition/probe procedure and actual schema evidence. Deployment additionally needs exact resource authority, persistent state/auth contract, graph edge-loader authority, production packaging, live permission/region/cost checks. None supplied by this feasibility result.
- Capture limitations: individual local action timestamps/durations mostly unknown; exact raw host tool transcript remains session-owned. Terminal intermittently returned unrelated concurrent commands; account/RG/provider results are excluded. Source findings are not a secret audit, license opinion or exhaustive code map. No authorized snapshot/restore evidence yet.

**Return:** status complete for read-only feasibility checkpoint; mission implementation blocked on named gates. Smallest next decision: settle OTRF archive license ambiguity (or commission pinned Splunk scenario review), revise exploring constitution for the public-data target, archive this evidence and exact proposed first-slice files, authorize one bounded host-data join probe. No follow-on work started.