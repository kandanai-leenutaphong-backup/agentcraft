# Deployment Entry Point

Run from repository root with existing system Python. No venv. Quote the literal
space in this testbed name. Historical constitution revisions grant no new campaign.

## Migration Canary (Current Procedure)

F08 live acceptance completed; 46 tests pass.
[F09 authoritative acceptance](../../../agentcraft_projects/foundry-official-integration-20260922/records/v2/20260922T200128628556Z-f09-migration-accepted/record.json)
was published 2026-09-22. Do not replay settled series writes.
The [append-only acceptance correction](../../../deploy/remediation-evidence/20260922T193935Z-acceptance-gaps/README.md)
closes H build concurrency and final-H E handoff without another optimizer run.
F07 same 19-file scope: 3501 -> 3523 -> 4291 at review, now 4372 lines; three
active install sites, all uv, including this Dockerfile. Custom authenticated HTTP
sites 6 -> 1; no net line/function reduction. C09 remains local lifecycle plus
live terminal verification, not proof of live downstream client closure.
Accepted Iris versions 5/6 and frozen evaluator/data remain unchanged. New agent:
`agentcraft-migration-iris-v1`; fresh series `migration-o-v1`, three synthetic rows,
at most two generated candidates plus baseline. These rows are development integration inputs, not
prediction-quality evidence, independent train/validation, or a holdout campaign.

Observed native jobs:
- `migration-o-v1`: `opt_7541d601c3ee4109b03cf97c1bfd7fec`, baseline-only at
	perfect trivial-prompt score; no generated-config acceptance.
- `migration-o-v2`: `opt_e4a3b37d9a304212812e6fc31e0338ba`, fresh arbitrary
	synthetic code mapping, baseline 1/3; stopped after two stalls, no generated config.
- `migration-o-v3`: `opt_4d8f98325041438aa3fa24dd54050bd4`, same v2 development
	rows/scorer, ten-stall bound; baseline plus two generated configs. Native scores
	1/3, 2/3, 3/3; independent hosted development scores 0/3, 2/3, 3/3.
	Versions 3/4/5 load actual returned instructions on repaired image
	`sha256:0ee3cbc25329ce77fb90a874156f93deea47adae3b0d418c7d84f3414f293a0c`.

[Independent JSON](evidence/migration-o-v3/candidate-validation-metrics.json),
[CSV](evidence/migration-o-v3/candidate-validation-metrics.csv),
[native metrics](evidence/migration-o-v3/migration-o-v3-recomputed-metrics.json),
[native rows](evidence/migration-o-v3/migration-o-v3-native-rows.csv).
All nine independent responses were stored/read back with exact loaded hashes.
Latest version 5 is generated candidate 2. This proves configuration integration;
historical prediction regression 28/30 versus 29/30 remains unchanged.

Provider `max_candidates` caps generated candidates, excluding baseline. Collection
requires successful terminal status, `candidates_completed` within cap, exact returned
count plus one baseline, unique IDs and complete evaluations. Baseline-only refuses.
Development rows use typed SDK constructors: snake-case `dataset_items` is not wire
JSON (`items` is). Frozen row files remain unchanged. Service registration omitted
SDK metric `threshold`; binary canaries require exact 1/0/0 independently of provider
pass threshold 0.5. Known criterion ID/null additions are normalized narrowly.

Cancellation uses native deferred `TextResponse`; `runtime-canary --probe cancellation`
retains response ID before cancel and proves terminal readback without completed output.
Task/client cleanup is locally tested; provider cleanup log evidence remains unavailable.
No interrupted-work durability or rollback claim. Direct CLI queued-build identity
handles observed null JSON through its single exact queued-ID diagnostic; dropped
or ambiguous identity refuses resubmission.

Fresh-series recipes below require a new manifest. v2/v3 explicitly pin migration-only
prerequisites; no historical campaign/holdout state is copied. Candidate validation
requires `--previous <exact-runtime-active.json> --previous-sha256 <digest>` on first
call and retains that binding. An existing-agent runtime `deploy` also requires these
flags, exact previous cloud state, and a distinct image. Deploys made after the
`foundry_ops` migration write library-shaped `deploy-<source>-active.json` plus the
testbed view `deploy-<source>-deployment.json`; pass the `-deployment.json` file as
`--previous` for those, legacy `-active.json` for earlier ones. Returned row responses resume
verification without repeating inference; unknown row intents still refuse.

Deploy-side glue (`live.py`, `hosting.py`, `campaign.py`) uses
[foundry-ops](../../../libraries/foundry-ops/README.md), put on `sys.path` by `live.py`.
`prepare.py` keeps its own helpers: the dataset manifest pins its bytes.

From repository root, with separate live authority before mutating stages:

```bash
O_MANIFEST='testbeds/foundry-agent optimization/deploy/env/migration-o-v1.json'
O_SHA=$(sha256sum "$O_MANIFEST" | cut -d ' ' -f1)
O_RUN=(bash 'testbeds/foundry-agent optimization/deploy/deploy.sh')
O_FLAGS=(--manifest deploy/env/migration-o-v1.json --manifest-sha256 "$O_SHA")
"${O_RUN[@]}" test
"${O_RUN[@]}" manifest-check "${O_FLAGS[@]}"
"${O_RUN[@]}" existing-job-parity "${O_FLAGS[@]}"
"${O_RUN[@]}" evaluator-register "${O_FLAGS[@]}"
"${O_RUN[@]}" evaluator-canary "${O_FLAGS[@]}"
"${O_RUN[@]}" canary-readback "${O_FLAGS[@]}"
"${O_RUN[@]}" mapped-canary "${O_FLAGS[@]}"
"${O_RUN[@]}" mapped-canary-readback "${O_FLAGS[@]}"
"${O_RUN[@]}" build "${O_FLAGS[@]}"
"${O_RUN[@]}" deploy "${O_FLAGS[@]}"
"${O_RUN[@]}" runtime-canary "${O_FLAGS[@]}"
"${O_RUN[@]}" optimizer-model-canary "${O_FLAGS[@]}"
"${O_RUN[@]}" optimize "${O_FLAGS[@]}"
"${O_RUN[@]}" optimizer-readback "${O_FLAGS[@]}"
"${O_RUN[@]}" collect-candidates "${O_FLAGS[@]}"
"${O_RUN[@]}" native-row-metrics "${O_FLAGS[@]}"
"${O_RUN[@]}" candidate-validation "${O_FLAGS[@]}" --previous "$O_RUNTIME" --previous-sha256 "$O_RUNTIME_SHA"
"${O_RUN[@]}" observe-validation "${O_FLAGS[@]}"
```

Set `O_RUNTIME` to the chosen owned active deployment receipt relative to the O
testbed root and `O_RUNTIME_SHA` to its SHA-256 before candidate validation.
Stop until each canary receipt says `passed:true`. Read an in-progress native job
again through `optimizer-readback`, or use bounded provider `optimizer-wait`; never
repeat `optimize`. `optimizer-reconcile` is read-only. No local-file busy watchers.
Each accepted create retains first-response job/operation IDs, sanitized headers and
request hash; `polling=False` leaves no SDK polling thread. Unknown identity needs
operator reconciliation, not another create. Raw candidate-list REST is removed.

`get_optimization_job().result.candidates` matched all three existing candidate IDs,
names, scores/tokens and evaluation links in the assigned read-only parity check.
Native result fields are retained as returned; no fabricated timestamps or lineage.
Collection requires exact declared membership and successful terminal status; a
failed/cancelled job remains retained partial evidence, never complete acceptance.

**Retained exception:** loader 1.0.0b1 public `load_config` strips local instruction
whitespace, permits fallback and lacks timeout/retry controls. Config acquisition
keeps one bounded GET matching the installed loader route, not a verified public
REST reference. It validates safe IDs, payload size, fields, model/tools/skills and
exact instruction bytes. Runtime still uses public loader; inline configuration is
deprecated upstream but retained pending resolver-path parity. No private imports.
`AgentOptimizationEvaluatorRef` exposes name/version only; explicit `data_mapping`
lives on Evals criteria. Native envelope parity requires the new live mapping canary.

All writes/receipts stay in `deploy/evidence/migration-o-v1/`. Existing job read-only
identity: `opt_21aee306b2db4bebb7eb89a07d9c1f8d`; no old campaign/holdout rerun.
Candidate validation creates separate canary versions, applies each actual returned
configuration, checks loaded instruction hash and reads stored response metadata.
`apply-selected`, holdout/demo, dependency-repair and rejected-submit retry actions
are retired. Complete F08 does not imply classification improvement.

## Historical Live Sequence

Current state: native-generated `_0001` hosted as DEMONSTRATION version 6, not
production promotion or best configuration. Both generated prompts lost frozen
validation selection: 28/30 versus native baseline 29/30. Parent explicitly authorized
separate demonstration selection using existing validation only, ties by candidate ID.
Capability victory: native optimization generated changed configuration actually
hosted plus complete metrics; quality improvement is not guaranteed or claimed.
Constitution rev2, scorer, data and thresholds are unchanged. No new optimizer run.
Baseline v5 remains active restore target. Historical baseline/same-config holdout
each scored 30/30; generated demonstration candidate holdout is **not evaluated**.
Never rerun holdout or use its outcomes for demonstration selection.

## Reusable Skill: Native Optimized Demonstration

Separate capability success from quality promotion. A regressing native-generated
configuration may be hosted only under explicit demonstration authority, labeled as
regression even above absolute quality thresholds. Record that distinction and
validation-only deterministic selection before mutation. Preserve historical best
selection, holdout records and baseline restore image. Do not inject expected answers.

The following completed sequence is archival context only. Its active dispatch is
retired; do not rerun the historical campaign or demonstration.

```bash
bash 'testbeds/foundry-agent optimization/deploy/deploy.sh' demonstration-decision
bash 'testbeds/foundry-agent optimization/deploy/deploy.sh' demonstration-build
bash 'testbeds/foundry-agent optimization/deploy/deploy.sh' demonstration-deploy
bash 'testbeds/foundry-agent optimization/deploy/deploy.sh' demonstration-verify
bash 'testbeds/foundry-agent optimization/deploy/deploy.sh' demonstration-handoff
```

Build overlays exact returned instruction bytes without modifying baseline files.
Deploy requires baseline v5 prestate before creating the next same-agent version.
Verify checks active latest image, native config ID/digest and loaded instructions,
three train-only authenticated scenarios, stored readback, anonymous refusal, retained
baseline v5 and protected v3. A scenario is operational evidence, not independent
quality or generalization evidence. An unresolved inference intent refuses retry;
reconcile its retained stored-response ID before further inference.

Version 6 image: `sha256:92c9eb5f876cce8e0d863a38fe0d2f2f6a852a3b5b5a6236de0302792d85560d`.
Native config SHA-256: `9346076f87f7a478ca9f754225e2941744ded500f5c4b7094958b0cffda99f5c`.
Instructions SHA-256: `97ef14fa51b393282ac0fb4d51465d9cc3aa5416fa8563f1aeed8a97e1a87887`.
[Decision](evidence/demonstration-decision.json) retains authority and restore identity;
[result](evidence/demonstration-result.json) retains live evidence. No automatic teardown.

### Metrics Location And Generation Semantics

[Independent CSV](evidence/candidate-validation-metrics.csv) and
[JSON](evidence/candidate-validation-metrics.json) contain all three candidate IDs,
including baseline, independent accuracy/macro-F1/invalid rate and native eval/run IDs.
Demonstration context verifies CSV/JSON identity and metric equality before build.
Foundry evaluation definition `eval_e04377ec0cd044e59db2e8a962268709` has runs:

| Candidate suffix | Evaluation run | Independent accuracy | Macro-F1 |
| --- | --- | --- | --- |
| `_0000` baseline | `evalrun_397c972249ef48bcb52f38495e930a65` | 29/30 | 0.9665831244778613 |
| `_0001` demonstration | `evalrun_fc68c867e50b40c09dbcafea5559e698` | 28/30 | 0.9326599326599326 |
| `_0002` generated | `evalrun_feca20e9f7ad4cc0aea58879b7fd22c2` | 28/30 | 0.9326599326599326 |

All invalid rates are zero. Foundry project evaluation runs/report URLs expose native
rows and composite search scores; find exact `report_url` in
[native evidence](evidence/native-mapping-v2-candidate-metrics.json), or use
`client.evals.runs.retrieve(eval_id=..., run_id=...)` and `output_items.list`.
The optimization job `opt_21aee306b2db4bebb7eb89a07d9c1f8d` and its candidates/config
API expose native configuration provenance, not these independent hosted scores.
[Recomputed native metrics](evidence/native-mapping-v2-recomputed-metrics.json) and
[native rows CSV](evidence/native-mapping-v2-native-rows.csv) remain separate evidence.
Composite `avg_score` is not macro-F1. Service returned baseline plus two generated
candidates, not an exhaustive generation ledger; generation and parent IDs remain
null. Never invent lineage from `_0001`, list position, or `max_candidates`.

## Historical Campaign Sequence (Not Executable)

```bash
bash 'testbeds/foundry-agent optimization/deploy/deploy.sh' live-check
bash 'testbeds/foundry-agent optimization/deploy/deploy.sh' evaluator-register
bash 'testbeds/foundry-agent optimization/deploy/deploy.sh' evaluator-canary
bash 'testbeds/foundry-agent optimization/deploy/deploy.sh' canary-readback
bash 'testbeds/foundry-agent optimization/deploy/deploy.sh' build
bash 'testbeds/foundry-agent optimization/deploy/deploy.sh' deploy
bash 'testbeds/foundry-agent optimization/deploy/deploy.sh' runtime-canary
bash 'testbeds/foundry-agent optimization/deploy/deploy.sh' baseline-validation
bash 'testbeds/foundry-agent optimization/deploy/deploy.sh' model-inventory
bash 'testbeds/foundry-agent optimization/deploy/deploy.sh' provision-optimizer-model
bash 'testbeds/foundry-agent optimization/deploy/deploy.sh' optimize
bash 'testbeds/foundry-agent optimization/deploy/deploy.sh' optimizer-readback
bash 'testbeds/foundry-agent optimization/deploy/deploy.sh' optimizer-wait
bash 'testbeds/foundry-agent optimization/deploy/deploy.sh' collect-candidates
bash 'testbeds/foundry-agent optimization/deploy/deploy.sh' candidate-validation
bash 'testbeds/foundry-agent optimization/deploy/deploy.sh' apply-selected
bash 'testbeds/foundry-agent optimization/deploy/deploy.sh' build
bash 'testbeds/foundry-agent optimization/deploy/deploy.sh' deploy
bash 'testbeds/foundry-agent optimization/deploy/deploy.sh' final-version-canaries
bash 'testbeds/foundry-agent optimization/deploy/deploy.sh' final-holdout
```

Do not repeat completed registration/submission commands: immutable intents refuse
duplicate mutation. Read existing results; reconcile returned IDs. Build/deploy reuse
owned receipts and require exact source/image readback. Validation resumes completed
rows, but refuses an unresolved row intent rather than issuing duplicate inference.
Canary readback status `complete` means read succeeded; acceptance requires `passed:true`.
`optimizer-wait` observes one existing job for at most 3600 seconds and never resubmits
or cancels it. A finished read action is not a successful job. Inspect `status`,
`settled`, candidates and per-row outputs. Provider operations can outlive the observer.
`optimizer-diagnostics`, `inspect-runtime` and `runtime-logs` are read-only diagnosis.
Candidate collection/validation/apply/final commands completed in the historical
campaign. Final holdout refuses before selected
configuration deployment and fresh baseline/chosen train-only routing canaries.

Long-running receipts created before startup-source capture was added hash runner
source at exit, not necessarily its loaded bytes; do not treat those hashes as
loaded runner identity. Container image/source identity is separately archived and
read back, unaffected by this instrumentation gap. Later receipts capture runner
module digests before action execution.
The first silent local observer was stopped and replaced by a status-heartbeat
observer; no native cancellation was submitted. Its state-change receipt survives,
but no final action-duration receipt exists for that interrupted local reader.

Native evaluator code requires `grade(sample, item)`, not a class. Three cloud canaries
prove 1/0/0 before scoring. SDK 2.6.1 advertises `evaluation_level="turn"`, but service
rejects it with HTTP 400; omit it for documented default single-turn behavior.
Initial rejected requests and successful corrected job remain separate evidence.
Provider's `Operation-Location` returns an internal-style project/job path that
responds HTTP 404 through the public host. Same-operation reconciliation returns
the original job ID; no second job is created. Use `optimizer-readback` or
`optimizer-wait` through SDK `get_optimization_job`, not that broken LRO URL.
Historical `optimizer-operation` receipts preserve routing diagnostics. Active
`optimizer-reconcile` only calls `get_optimization_job` with the retained job ID;
it never repeats submission to rediscover headers.

First native job `opt_89d941bff7214fa0b670b77249c583ad` completed baseline-only:
native score 0 was invalid search guidance because optimizer supplies output in
`item["sample.output_text"]`, unlike the initial standalone canary's `item["response"]`.
Retained 30 native rows independently recompute to 29/30 correct. Nothing overwrites
that job. Corrected evaluator accepts the native field and passed separate
`mapped-canary` / `mapped-canary-readback` positive/wrong/invalid checks without
explicit data mapping. Frozen independent scorer, splits, thresholds and image did
not change. Corrected series uses `native-mapping-v2-` evidence filenames.

Corrected job `opt_21aee306b2db4bebb7eb89a07d9c1f8d` completed with baseline and
two native-generated configs. `max_candidates=3` does not promise three generated
configs; stall termination and actual returned IDs control reporting. Each has
30 native evaluation rows; `native-row-metrics` verifies exact membership and
exports recomputed metrics plus native raw-row CSV. Native composite scores are
retained separately and never labeled macro-F1. No generation or parent inference.
Independent hosted validation then measures all returned configs on the same 30
rows before one deterministic selection. Applied-candidate and holdout stages
must not run early or change selection after held-out outcomes.

Historical wrong-package installation downgraded dependencies; historical `restore-sdk`
restored Projects 2.6.1, hosting 2.1.0 and MAF core 1.18.0. Receipts remain immutable.
`install-loader`, `restore-sdk`, `optimize-retry-rejected`, `optimizer-operation`
and holdout/demo actions are retired from active dispatch. File observers no longer
loop; `observe-validation` returns one resumable status read.
Use [host lock](host-requirements.lock) and [runtime lock](runtime-requirements.lock):
99 packages, loader 1.0.0b1, complete closure, no legacy hosting adapter. No dependency
suppression, global sync, environment creation or unrelated conflict repair.
[Dependency manifest](dependency-manifest.json) pins canonical wheels and official
uv/Python images. Container installation uses uv 0.9.30, explicit image interpreter,
offline wheels and required hashes; records freeze/locations and runs compatibility.
F01 verified locks/imports offline; image build/live acceptance remains F08.
Local user-site imports already satisfy these profiles. Existing unrelated conflicts
remain; actual target additions/replacements require exact recovery review.

Native inline requests upload only 87 train and 30 validation rows. Service registers
them as `opt-inline-<job-id-suffix>` and its `-val` version. No raw source or holdout
enters image, optimizer, mounts or candidate tools. Native loader applies instructions
only and refuses model/tools/skills/temperature drift. Resolver failure refuses fallback
when a candidate was explicitly requested.

Live classifier: `agentcraft-iris-optimization`, version 6 demonstration, authenticated endpoint:
`https://han-primary-foundry-resource.services.ai.azure.com/api/projects/han-primary-foundry/agents/agentcraft-iris-optimization/endpoint/protocols/openai/responses?api-version=v1`.
Dedicated optimizer model: `agentcraft-iris-optimizer-gpt54`, gpt-5.4 `2026-03-05`,
GlobalStandard capacity 100. Protected `agentcraft-hosted-tool-proof` v3 is never mutated.
No teardown action is authorized; retain resources and report costs as unknown.

## Historical Preparation

```bash
bash 'testbeds/foundry-agent optimization/deploy/deploy.sh' snapshot
bash 'testbeds/foundry-agent optimization/deploy/deploy.sh' acquire
bash 'testbeds/foundry-agent optimization/deploy/deploy.sh' prepare
bash 'testbeds/foundry-agent optimization/deploy/deploy.sh' test
bash 'testbeds/foundry-agent optimization/deploy/deploy.sh' verify
bash 'testbeds/foundry-agent optimization/deploy/deploy.sh' preflight
python3 .github/skills/agentcraft-process/validate.py 'testbeds/foundry-agent optimization/agentcraft_projects/foundry-agent-optimization/constitution/constitution.yaml'
```

Each entrypoint action appends a measured primary JSON receipt in `evidence/`,
prints its path/digest and exits nonzero on failure. These are worker evidence,
not authoritative AgentCraft records. Only overseer publishes those records.

| Action | Expected result | Failure response |
| --- | --- | --- |
| `test` | Offline metric, dedup, split, immutable output and config refusal tests | Repair same slice before freezing or running expensive work |
| `snapshot` | Existing recovery archive hash and 68 historical record hashes match | Stop on drift; never rewrite historical receipts |
| `acquire` | UCI publisher license verified before pinned ZIP; provenance stored | Preserve receipt; do not bypass robots/TLS or silently change data revision |
| `prepare` | 87 train / 30 validation / 30 holdout; native JSON plus immutable manifest | Conflicting duplicate labels, changed source or immutable outputs refuse |
| `verify` | All frozen hashes, split disjointness and native roundtrip pass | Reconcile drift; no score or optimizer run |
| `preflight` | Read-only exact account/project/model/evaluator/optimizer and protected-host readback | Name unavailable prerequisite; do not switch shared CLI context or mutate cloud |
| constitution validator | `valid` plus SHA-256 | Repair document; structural validation is not live acceptance |

`snapshot` imports the already captured reviewed prechange archive from the fixed
session temporary path only when retained copy is absent; it does not manufacture
historical bytes from current source. Preserve `evidence/prechange.tar.gz` in the
overseer archive before moving machines. SHA-256:
`9a873d53a750d3f17a14116199df8c7ddab02fb9a1127253529cecc1f4b572d2`.
Initial capture used `tar` and `tar -d` against original disk before rename. Recovery
archive is ignored by Git but retained locally; source paths and hashes are in snapshot receipt.
Restore only into a separate recovery directory, never over a dirty working tree.

System dependencies: `azure-ai-projects==2.6.1`, installed `agentconfig`, `llm_interface`,
`azure-identity`, `harness-web-resource==1.1.0`, PyYAML, jsonschema and Azure CLI.
Historical user-site transport was installed from repository owner with
`python3 -m pip install --user --break-system-packages --no-deps --no-build-isolation ./.github/skills/web-resource`.
That historical command is not an active installation procedure. Current package
operations require reviewed uv locks and existing explicit interpreter/target.
No virtual environment or dependency upgrade. Initial intercepted command and PEP 668
refusal are retained in handoff evidence. Missing prerequisite is not an implicit install grant.

Acquisition stores publisher page/ZIP and per-file provenance under ignored
`dataset/private/source`. Existing bytes are verified and reused without network.
Pinned ZIP is mandatory on fresh acquisition; publisher-page/timestamp changes may
require a new provenance manifest, never overwrite existing frozen manifest.
Dataset membership, native payloads and evaluator remain deterministic for pinned ZIP.
`prepare` repeat on retained sources must preserve manifest bytes exactly.
`dataset/private/holdout.json` is mode 0600; this protects other users, not same-user
candidates. Do not mount any private data or repository in a candidate runtime.

Preflight authenticates through existing Azure CLI without logging tokens. Exact
subscription/tenant mismatch refuses rather than switching context. SDK requests
have disabled retries and bounded connection/read timeouts; only GET/list operations.
It records optional loader absence, service metadata and unresolved live canaries.
`builtin.string_check` v2 needs constructor mappings that native optimizer evaluator
references do not carry; verify a supported versioned binding before optimization.
New agent identity and native mutations/promotion remain unverified, not hidden failures.

Future build/deploy/verify/teardown must extend this entrypoint within next assignment,
reuse [existing hosting owner](../../foundry-hosted-agents/deploy/README.md), and leave
accepted host unchanged. Never invoke its existing build/deploy actions for the new
classifier without new scope and identity binding.