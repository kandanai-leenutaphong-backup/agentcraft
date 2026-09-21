# Rev10 Preservation Review

Documentation-only checkpoint. Review aid, not relocated governance or authoritative record.
Source: requesting user's Sept21 assignment; implementation by agentcraft-orchestrator, no delegates.
Hypothesis: collapse repeated chronology, assignment limits and reporting duties while preserving information;
explicitly delegated policy/status changes below are NOT lossless compression.

## Exact Sources

Paths below resolve from project root unless repository-relative is stated.

- Authorization: `records/v2/20260921T034329452947Z-constitution-v10-sequential-loop-authorized/record.json`, SHA-256 `f314905843ddc97053d0574229486d70ced84b06cee2eecbe15492d2ab800610`.
- Prestate: `records/v2/20260921T034329485019Z-constitution-v10-sequential-loop-prestate/record.json`, SHA-256 `44894bf4e1176d4c04b14aeae89419a4a124903a92f37ca760a7b5fdf2db2b95`.
- In that prestate bundle, `artifacts/constitution.yaml` is exact rev9, SHA-256 `070cadee2c44731d1b984dafc906a6bba2f2797de1bd2530474ef5777b8c0e37`; `artifacts/0000-README.md` is exact prior spec, SHA-256 `1c007b4f19d850ff8631153f88b4ad08eb749aed7af8f4c2b5a750103d9e818a`. Both matched live bytes before editing.
- New rev10 SHA-256 `e1c62d9cda1edc0c1d51cbd40875cf797797c381817eefa47ff4abc0c9c7fc81`; spec SHA-256 `d28fc207e005334157f3d3b2ab8acf59200a8543fa5f93eb1a0f4232688c6516`.
- Unchanged role `.github/agents/agentcraft-overseer.agent.md` (repository-relative), v1.61 SHA-256 `69086f9e13555340a161e0022557b44a6c9692b67ae8a9eadc933a548fa9f862`.

## Explicit Changes

| Delegated change | Old treatment | New governing location and limit |
| --- | --- | --- |
| Sequential clarification | Application-first objective; fresh-session language could be read as a blanket progression gate | `objective.outcome`, `collaboration.checkpoints`, README Current Loop: original overseer objective first; actual missions, independent evidence, archive/correction, minimal versioned delta, subsequent behavior. No second overseer. No hot-reload/causal claim; fresh loaded-role verification and controlled comparison/replication remain gated. |
| Current versus historical scope | Rev8/9 repeatedly called current assignment local-only; later release authority absent | `decision_source`, `data_understanding.permitted_experiments`, `authority.source/scope/permitted_operations/operational_actions`, `deployment`: historical restrictions retained by exact snapshot/decisions; existing target-bound release authority distinguished. No retroactive grant, new infrastructure/identity/budget, unrelated expansion or execution this turn. |
| v1.61 checkpoint | Not stated in rev9 | `collaboration.checkpoints`, README Current Loop: every two delivery assignments, before expansion, after correction/resume; support calls excluded, unknown count checks now; four facts; supporting-only work requires objective test or named blocker/exit; behavioral only. |
| Status update | README rev7/host-blocked; rev9 deployment still prospective | README opening/Testbed And Next Mission, `deployment`, `reporting.dashboard`: rev10 exploring, unchanged v1.61 source, recorded deployed app baseline, unmet v1.7. Human sign-in unknown, two-event smoke only, eleven retained resources/services, cost/restoration unknown; historical receipts not fresh cloud/model verification. |

Current user corrections remain attributed rescue. Evaluator separation, safety and evidence obligations are not waived.

## Constitution Map

All rows compare exact prestate against live rev10. Field names refer to live YAML unless marked historical.

| Old section / information and obligations | New location / preservation finding |
| --- | --- |
| `schema_version`, `project_id`, `status`, required field sets | Exact parsed equality, including nested required field sets; only revision becomes 10. |
| `decision_source`: Sept19 session, outcome-gated speed, autonomy, measurement, explanation, visualization, replication; role/skills/agents/tools levers | Session exact in `decision_source`; objectives in `objective`, levers in `authority.scope`, explanation/plots/replication in `reporting` and `metrics`. Historical narrative retained in exact rev9 snapshot. |
| Sept19 dataset/ignore/scripts, reference move, local mandate, local-dev-test-subject, routine technical delegation | `authority.source/permitted_operations`, README Historical Datasets/Reference Project; historical move authorization remains snapshot, not repeat permission. |
| Rev7 baseline attribution and exact decision/prestate; rev8 public reorientation and prestate; rev9 delegated integration decision/prestate | All six concrete record paths remain exact in `decision_source`; no old receipt rewritten. |
| Rev8 acquisition/no-cloud/no-model/no-publication and rev9 local integration-only assignment | Explicit historical references in `decision_source`, `authority.source/scope`, `data_understanding.permitted_experiments`. Exact path mapping, added-file bounds, root-engine/role exclusions and original local stage preserved in rev9 and named integrated prestate; later release does not retroactively authorize them. |
| `objective.beneficiary`, decision owner | Exact parsed equality. |
| `objective.outcome`: public app, Cosmos NoSQL, official MITRE Search, same-event Gremlin; exact evidence/uncertainty; no incident/per-event truth inference | `objective.outcome` retains app contract/epistemic limits; priority explicitly changed above. Native integration, scanner, real-package/test-transport and desktop/mobile readback requirements remain `data_understanding.permitted_experiments` and `deployment.live_test`. |
| Two-event smoke, private Perth/remediation exclusions, separate cyber and overseer measures | `objective.outcome`, `authority.operational_actions`, `reporting.dashboard`, unchanged metrics. |
| `primary_metric` | Exact `time-to-live-acceptance`. |
| All 13 metrics: IDs/kinds/units/evaluators/rubric/target operators/null values, formulas/denominators, failures/censoring, repeats, distributions/uncertainty, safety/quality gates | Entire parsed `metrics` array equals rev9, not merely identifiers. No metric wording changed. All targets/evaluators and judgment rubric stay null; no invented thresholds/splits. See validation JSON for identifiers. |
| Metric domains: source-specific flow proposals, not incident recall or acceptance of public events | Exact `dataset.scenario_policy`; README Historical Data Understanding; unchanged cyber metric caveats. |
| `data_understanding.sources`: Splunk Apache-2.0 path LICENSE/NOTICE, exact lock ownership; MITRE v18 commit `b4c5d044bf5a5f117ec241b2536c8cb709f53cdc`, full notice; OTRF MIT/GPL conflict; historical HIKARI/UWF | Exact parsed list equality; source pins/licenses not abbreviated away. |
| `questions`: schema/labels/units/time/entities/classes; missingness/duplicates/overlap/shortcuts; extraction hypotheses, tool/agent responsibilities, split/replay leakage | Exact parsed equality. |
| `permitted_experiments`: raw preservation, development probes, bounded guarded acquisition/non-execution, real-field joins, explicit missingness, public async APIs, no KQL emulation, repeat/failure measurement | All entries exact except historical dispatch exclusion replaced by explicit current-versus-historical scope change above. |
| `outputs`: scripts/JSON observations, evidence-led decisions, manifest/membership/split, evaluators/rubric/targets/baseline | Exact parsed equality. |
| `verification`, `transition`: readback/repeat/cross-check, development disclosure, samples not population, useful probes, frozen ready/new series, no held-out tuning | Exact parsed equality. |
| `dataset.manifest/revision/scenario_policy/held_out_policy` | Entire parsed object unchanged: `dataset/manifest.json`, null revision, incomparable series, source lock, coherent licensed scenario/rules/joins, MITRE advisory, no invented truth/scores, no repo-publication grant, evaluator isolation and disclosed-case refresh. |
| `deployment.target/identity`: RG/tenant/subscription/region, serverless stores, service tiers, one replica, managed identity/storage/vault, preflight | Same exact target identifiers and service constraints; current release pointer replaces obsolete future-only wording. Mutable state/permissions/model availability still need fresh readback. |
| Explicit scoped principals/service-read/ingest/state/ACR/model/sign-in; no broad consent, Owner/Contributor, exemptions/teardown/unrelated mutation | `deployment.identity`, `authority.source/operational_actions`. Existing Foundry resource/model names unchanged. No new grant. |
| `deployment.live_test`: build/backend/route/offline support, real IDs and all stores, authenticated desktop/mobile source journey, matching refusals, transport labeling, legacy defaults/unsupported rules | Retained inline; later signed release evidence distinguished from unknown human sign-in and no fresh check. |
| SQLite/filesystem/Entra persistence, durable storage and true shared replay requirement | `deployment.live_test`; one replica still does not establish shared replay. |
| `deployment.restore`: raw hashes/user edits, versioned prompts/tools/state, known-good redispatch/readback, disposable outputs, no reset/data destruction, verified restoration before promotion | Exact parsed equality; observed recovery remains unverified, not implied by snapshots. |
| `authority.source`: user delegation and original unbounded local grant, historical actions versus current permission | Explicit scope change above; grant does not widen resources. Documentation-only paths and exclusions remain inline. |
| `authority.scope`: role, skills, every supporting agent, capabilities/tools/apps/local deployment, evidence/presentation levers with owner/check/restore duties | All five families retained inline; not mandatory to change. Role metadata/fresh behavior, skill public contracts/journeys, supporting-agent metadata/tool limits/delegation, reusable API/owner/one-writer checks and reporting parity/restoration retained. |
| App Cosmos versus generic resource-explorer ownership, normalized ingestion stability, CAS/defaults/configuration edge, ignored payloads/shared prestate/dirty work | `authority.scope` retains each duty; exact historical local path map referenced, not broadened. |
| Inspection-only reference archive, per-experiment targets/hypothesis/checks/restore, frozen shared machinery during comparison, unresolved trial targets, explicit boundary expansion | `authority.scope`; README Reference Project. |
| `permitted_operations`: data first, local tools/probes/repeats then candidate, autonomous selection, actual JSON attribution, exact candidate piloting | Consolidated inline; fresh scored gates and ordinary routing remain `collaboration.checkpoints`. No permission from lever availability. |
| Dataset CSV/tables/no pcaps; saved local dependency scripts/ignored runtime/preserve system/no venv; archival-only delegation and verified live restore | `authority.permitted_operations`; README retains executable historical procedures. |
| `protected_resources` | Entire list exact: user/private/credential/archive, safety/auth/rights, frozen baseline/tasks/split/evaluator/rubric/acceptance/comparison, metric/instrumentation/coverage, labels/evidence/failures, ungranted external assets. |
| `operational_actions` | Observation/analysis/development/advisory only; explicit ongoing no asset control/remediation/external attacks, private Perth, secrets, auth weakening/publication/deletion. Existing hosting/model authority not asset authority. |
| `limit_policy`, all caps/currency/expiry | Exact `user-unbounded`, all null. No fabricated limit or new resource/budget authority. |
| `stop_conditions`, `cleanup_owner` | Exact lists/string: unknown data not discovery blocker; pause/permissions/provider/unsafe/integrity/side effects; workers/scope/leakage/restoration; no changed criteria/hidden failures; assigned/global settlement. |
| `collaboration.reviewers` | Exact parsed list; user ownership, overseer independent evaluation, orchestrator stage boundary, archivist facts/not grading, note_scribe lessons. |
| `checkpoints`: baseline/corrections/results/promotion/final review, trace to disposition, safety disagreement, pinned assignment, return at checkpoint/blocker/scope/metric change | Retained inline plus explicit sequential/checkpoint changes. No recursive/direct-candidate/support-role dispatch; join workers. |
| Missing prestate checkpoint before mutation, no phantom asynchronous peer; overseer pre/phase/post handoff, compact IDs/gaps, joined publication | `collaboration.checkpoints`; single source of repeated handoff obligations. |
| `reporting.results/project_report/notebook` | Exact `results/<run-id>/`, `reports/latest.html`, `notebook/lessons.md`. |
| `dashboard`: new versus historical incomparable series; rights/pins/joins/unsupported relations/digests/timings | Retained inline; selected-versus-deployed status explicitly updated. |
| Records root/layout/recorder/schema, legacy immutability, exact selected snapshots, no parallel ledger, create-only/readback/verify | Exact explicit paths retained in `reporting.dashboard`; archival ownership and joins in `collaboration`. |
| Project/series/run/parent/iteration/change/result identities, archival/observed timestamps, actors, source/constitution/action/hypothesis/rationale/authority/metric units-denominators-coverage/path-hash | All retained inline; unknown/hidden telemetry remains null/gap, not completeness or zero. |
| Pre/post recoverable versions, coverage/gaps/reversion, no reconstructed history, archivist not grader/implementer/restorer; lessons linkage | Retained `reporting.dashboard`, `collaboration.checkpoints`, `deployment.restore`. |
| Exploratory verdicts, privacy/no secrets/labels/deliberation, max effort unverified, no automatic instrumentation claim | Retained inline, current v1.61 source versus runtime explicitly distinguished. |
| Proposed plots/timelines/effort, baseline/target/samples/failures/uncertainty/gaps; linked exact versions/cases/checks/SME/next decision; shared JSON/HTML calculations/no rerun; separate tooling/cost | Retained inline; not represented as implemented or performance proof. |
| Evaluator/measurement correction starts new series or recomputes both sides, retains receipts/provenance; attribution/privacy/integrity non-negotiable | Retained final `reporting.dashboard` sentences. |

## Spec Map

| Prior README section / information | New location / finding |
| --- | --- |
| Opening rev7/exploring/unbounded/path basis | Opening current rev10; limits/path semantics preserved, status change explicit. |
| Objective: alerts/hosts/windows/uncertainty, flow versus incident, no remediation, separate quality/delivery/equivalent tasks/levers | Current Loop/Testbed, Before Scored Comparison; historic netflow objective detail in exact prior-spec snapshot, now historical rather than current public-event mission. No metric-domain reassignment. |
| Data-understanding sequence/delegation/rights/revisit; routing/candidate not extra service; historical direct invocations/max-effort caveat | Historical Data Understanding and Current Loop; full historical direct-invocation detail remains prior snapshot. Constitution transition still requires returning to discovery on new gaps. |
| First/follow-up/third surveys, six prefixes/2000 rows, duplicate/tactic/label/overlap/time findings, 14-table totals, 51,128 ordinals, rare 63 disclosures, tests/failures/times | Survey paragraphs and evidence links unchanged. Counts remain historical observations, not rerun or improvement. |
| Historical survey commands/pin/options/sampling/defaults/maxima/memory/source guards/readback/refusal/legacy prefix | Commands and all parameters retained verbatim; historical pin now explicitly not current assignment. PyArrow 21.0.0 setup and candidate-host block retained. |
| Decisions/Iterations layouts, roles, pre/phase/post publication, fields, recorder stdin commands, snapshot/reference/correction/privacy/coverage gaps | Records, Current Loop and constitution reporting; commands unchanged, not executed here. |
| Historical missing before-state/action coverage, rev6 routing/rev7 baseline attribution | Records explicitly points to exact prior-spec snapshot, preserving historical details without asserting them as current status. |
| 15 payloads/bytes, ZIP+CSV, five CSV/eight Parquet, no pcaps/pickle, Zenodo/UWF URLs and CC BY 4.0 | Historical Datasets; table and all existing links retained. |
| Taxonomy/export limits, publisher count not local truth, synthetic labels/unverified semantics, provenance metadata/MD5 versus observed SHA-256/attribution | Historical Datasets concise paragraph preserves each distinction. |
| Acquisition setup/download/verify commands, root/path resolution, Python/pip/build prerequisites, local no-deps runtime/no implicit install | Same commands and Historical Datasets implementation paragraph. |
| Lock reuse/verification/refusal, guarded transport, frozen plan/revision review, 8/2 GiB/30-minute/free-space bounds, partial rerun/no concurrency, offline signatures, receipts, repeated success | Historical Datasets; all bounds/duties retained, historical outcomes labeled. |
| Before Scored Comparison and readiness command, unknown not blocker, report gaps, lock not split/discovery not score | Same section/command; constituent requirements condensed, never waived. |
| Reference tree intact ignored move, absent fresh checkout/no runtime, original artifacts, relocation uncertainty, ownership/reuse, no grant/baseline transfer, no staging/commit | Reference Project; historical facts preserved, no repeated move authorized. |

## Checks And Gaps

- Immediate post-constitution action: existing strict `validate.py`, valid. Existing constitution/record tests: 20 passed, 29 subtests. No new tests or production code.
- Parsed entire metric array, field sets, source pins/licenses, dataset, limits, protected resources, stops, restore and reviewer invariants match. All six prior concrete record paths and all 16 prior README links retained; 11 current concrete record paths and 20 local README links exist. Templates are not file links.
- Side-by-side scoped diffs reviewed alongside full original reads and applied hunks; terminal presentation truncated the large constitution diff. Semantic conclusions above rely on those sources and explicit per-section review, not tests or truncated diff alone. No full raw diff archive claim.
- Initial read of required `docs/ARCHITECTURE_OVERVIEW.md` failed: absent. Targeted `rg` returned exit 2 because `.github/instructions/local` is absent, while finding both tests. No component/dependency placement changes.
- First ad hoc reference audit failed by treating `records/v2/<UTC-timestamp>-<record-id>/record.json` as a concrete file; corrected placeholder filter passed. No source defect or validation failure concealed.
- Root `README.md:43` still labels linked role v1.6 despite current v1.61 source. Outside writable scope; unchanged. No root-wide documentation accuracy claim.
- Primary evidence only; no authoritative record/notebook writes, mission/cloud/model execution, delegation, credential access or restore. No performance/causal/v1.7 claim. Total duration, hidden actions, costs and effective effort unknown.
- Return request: overseer dispatch archivist for rev10/spec post-change snapshots and outcome linking both supplied before receipts. This ends documentation checkpoint; next mission acceptance planning requires its own assignment.