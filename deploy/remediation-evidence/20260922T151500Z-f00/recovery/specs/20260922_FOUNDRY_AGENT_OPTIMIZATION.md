# Foundry Agent Optimization

## Live Revision 2

Current outcome: **capability demonstration complete; development regression**.
Native-generated candidate `cand_opt_21aee306b2db4bebb7eb89a07d9c1f8d_0001` runs as
hosted Iris version 6, image `sha256:92c9eb5f876cce8e0d863a38fe0d2f2f6a852a3b5b5a6236de0302792d85560d`.
Parent's explicit final bounded assignment distinguishes having been optimized from
metric improvement: actual native-generated changed config hosted plus candidate
metrics is capability victory. This is DEMONSTRATION, not production promotion or
best-config claim. Choose only existing validation among generated candidates, same
metric ordering then stable candidate ID. Both scored 28/30 versus baseline 29/30;
macro-F1 0.9326599326599326 versus 0.9665831244778613. Thresholds stay unchanged;
exceeding 0.90 does not remove regression. No new optimizer run or holdout scoring.
Generated candidate holdout: **not evaluated**. No improvement/generalization claim.
Decision recorded before build/deploy in the testbed's `demonstration-decision.json`;
`demonstration-result.json` retains active image, exact loaded config/instruction
digests, three known train scenarios, stored response readback and anonymous 401.
Baseline v5 retained unchanged as restore target; protected hosted v3 untouched.

Historical comparison outcome: **unchanged; native baseline selected**. All 90 independent
validation rows completed: native baseline macro-F1 0.9665831244778613; generated
candidates each 0.9326599326599326. Frozen selection retained native baseline.
Applied exact returned config, rebuilt, deployed version 5, verified loaded hashes,
anonymous refusal and stored responses. Final baseline/selected holdout each 30/30,
accuracy/macro-F1 1.0, invalid rate 0. No reselection after holdout.
Version 5 image digest `sha256:962d979d09a9bb16ebf515da4b14920b492dfdbabe2eb120ee2ab559fe48589e`.
Initial final-result writer mechanically marked improvement from repeated-baseline
variance; `final-verdict-correction.json` supersedes that interpretation, preserving
raw measurements. No claim of generated-prompt improvement. Bounded capability
victory above does not rewrite that comparison or its holdout records.

Constitution revision 2 SHA-256
`854bfde0ee9421f141881d865834646f77972635a665737ba656c8fb79b7098d`
and parent dispatch authorize scoped live execution without changing frozen splits,
independent scorer or thresholds. The preparation section below is historical.

Hosted `agentcraft-iris-optimization` v1 image:
`agentcraftdev67255.azurecr.io/agentcraft-iris-optimization@sha256:c45f1e517c5cc897ff437ac825e28438131c8f940a8e6e0521e7963e58d056e6`.
Native grade-function canaries pass 1/0/0; official loader 1.0.0b1 applies native
instructions through agentconfig and llm_interface. Anonymous 401 and loaded hash /
stored-response checks passed before baseline. Thirty-row validation accuracy
0.9333333333333333, macro-F1 0.9333333333333332, invalid rate 0.

Native SDK job `opt_89d941bff7214fa0b670b77249c583ad` accepted with baseline v1,
custom evaluator `agentcraft-iris-exact-734a913b43f2` v1, instruction-only config,
three requested candidates and five stalls. Dedicated supported optimizer model
`agentcraft-iris-optimizer-gpt54` is gpt-5.4 `2026-03-05`; classifier remains
gpt-5.6-luna. This is an optimizer-model integration choice, not a scored model change.
At that historical stage holdout remained untouched; later baseline selection and
holdout are disclosed above, without transferring their scores to demonstration v6.
Primary receipts and raw baseline CSV/JSON live under the testbed deploy/evidence directory.

The first job settled `succeeded/stopped_early` with baseline only. Its native
adapter scored correct outputs zero because optimizer uses flattened
`sample.output_text`; standalone canary used `response`. Retained native rows
recompute with frozen scorer to 29/30 correct, macro-F1 0.9665831244778613.
This does not rewrite native scores or establish improvement.

Corrected native adapter `agentcraft-iris-exact-b50f31e17769` v1 passed actual
native-field positive/wrong/invalid canaries. Separate job
`opt_21aee306b2db4bebb7eb89a07d9c1f8d` completed with baseline and two generated
instruction candidates; all have 30 retained evaluation rows. Corrected search
evidence is namespaced `native-mapping-v2`; independent scorer and comparison
controls remain unchanged. Complete independent hosted candidate validation preceded
historical baseline selection and final holdout. Provider LRO location returns 404;
SDK `get_optimization_job` works and was used through terminal readback.

Failures retained: wrong optional-loader package/version and dependency downgrade
(runtime pins restored); native grader class rejected (top-level grade repaired);
SDK explicit `turn` enum rejected (documented single-turn default used); project-route
inference connection failure (empty sessions verified, dedicated agent endpoint passed).
No protected v3 source/config/image mutation; no secrets or TLS relaxation.

## Authority And Checkpoint

[Published preparation decision](20260922_FOUNDRY_AGENT_OPTIMIZATION_DECISION.json),
SHA-256 `faa8f96079fae45cf8d14d77564b6cf32d821d1087e03399dd6d7f04d3bca2c2`,
and current user assignment authorize snapshot, rename, constitution, public acquisition,
local implementation and prerequisite reads. No preceding constitution was required.
This increment ends at local preparation; no optimizer job, model call, upload,
agent creation, image build, deployment, role change or other cloud mutation.
Broader mission authority remains available for a subsequent live assignment.

New exact testbed: [testbeds/foundry-agent optimization](../testbeds/foundry-agent%20optimization/README.md).
Prior proof moved to [foundry-agent-evaluation](../testbeds/foundry-agent-evaluation/README.md).
Historical JSON and archive bytes remain immutable; active documentation paths changed.
Root architecture document is absent. Existing host README, deployment guide,
`agentconfig` public API and `llm_interface` contract govern placement and reuse.
No shared library, accepted host source, user edit, or role definition is changed.

## Outcome And Hypothesis

Beneficiary: operator testing native Foundry configuration optimization end to end.
Outcome: independently measurable classifier served by a configuration-defined hosted
agent, with immutable native candidate evidence and deployment readback.
Hypothesis: instruction-only native optimization can improve exact classification on
fixed development validation without reducing final held-out accuracy or macro-F1.
This is a small public benchmark integration experiment, not a claim of novel domain
capability, statistical significance, private-data generalization or unseen pretraining data.

## Data And Rights

UCI Iris, Fisher (1936), DOI `10.24432/C56C76`, publisher CC BY 4.0.
Publisher license URL: https://archive.ics.uci.edu/dataset/53/iris
Archive: https://archive.ics.uci.edu/static/public/53/iris.zip
Archive SHA-256 `d11fe30213d36434a0879aab7cb00ce3c812eb7ba2495874438abff7b7b762e9`.
License-page bytes and timestamped provenance retained beside raw data. Acquisition
uses installed repository-owned `webres` 1.1.0: public-address pinning, robots,
redirect checks, rate limits, byte bounds and TLS verification. No credentials.
Attribution remains in manifest; derivatives record changes: deduplication, split and query formatting.

150 rows, four positive finite centimeter measurements, no missing measurements.
Exact feature-key deduplication removes 3 rows; contradictory labels fail closed.
147 unique samples: 48 setosa, 50 versicolor, 49 virginica.
Deterministic SHA-256 ordering with seed `uci-iris-v1-20260922`, stratified by class:
train 87 (28/30/29), validation 30 (10 each), final holdout 30 (10 each).
All feature-key IDs are disjoint. No source row number or label enters query features.
Near-neighbor measurements remain; species/order/dataset familiarity and pretraining
memorization limit external validity. Exact duplicates cannot cross partitions.

[Manifest](../testbeds/foundry-agent%20optimization/agentcraft_projects/foundry-agent-optimization/dataset/manifest.json)
SHA-256 `18d7e82c2cbb97dc958ca51587d7c0f545c2b8f19363342aa7a1f60ef0258365`.
Only native train and validation JSON may enter optimizer requests. Validation is
optimizer-visible development data, never claimed held out. Raw source and final
holdout labels remain evaluator-only, excluded from candidate image, mount, tool and
upload allowlists. Local mode 0600 is not isolation against a same-user process.
Before live execution, inspect exact image/context and candidate tools/mounts; never
give a candidate repository or raw-data access. No holdout scoring in preparation.

Development signal probe: nearest centroid fitted only on train, evaluated on validation:
accuracy 0.90, macro-F1 0.899749373433584, invalid rate 0, n=30.
This is data exploration, not a measured hosted-agent baseline or optimizer gain.

## Frozen Evaluation

[Scorer](../testbeds/foundry-agent%20optimization/evaluator.py), SHA-256
`86700e5ab974545564e424e33d97d3767a404d0e9943cf479937178e0aacb176`.
Accept only exact class label after surrounding whitespace removal. JSON, explanation,
synonym, missing or non-string response counts as invalid and incorrect; never drop rows.
Accuracy = correct / all assigned rows. Per-class precision, recall and F1 use
one-vs-rest counts; absent denominators yield zero. Macro-F1 averages all three classes.
Retain confusion matrix with invalid column, per-class support and every row outcome.

Delegated technical targets, frozen before candidate or holdout outcomes:
accuracy >=0.90; macro-F1 >=0.90; invalid rate =0. Candidate selection uses complete
validation results, primary macro-F1, then accuracy, then fewer invalid outputs,
then stable candidate ID. Require validation macro-F1 gain >=0.01 versus frozen
hosted baseline for an improvement claim; ties/ceiling are unchanged, not fabricated gain.
Select once, then evaluate selected candidate and frozen baseline once on final holdout.
Require both holdout quality targets and no holdout accuracy/macro-F1 regression.
Failed holdout is reported; no tuning/reselection against its outcomes in this series.
Retain per-row latency, p50/p95, token usage and cost when observed; unknown stays null.
No user-imposed spend, latency or iteration limit; operational timeouts are safety controls.

## Native Optimizer Contract

Installed `azure-ai-projects==2.6.1` exposes
`AIProjectClient.beta.agents.begin_create_optimization_job`.
Request uses `AgentOptimizationJob(inputs=AgentOptimizationJobInputs(...))`,
`OptimizedAgentIdentifier` with explicit new name and actual registered version,
and inline train/validation `AgentOptimizationInlineDatasetInput` values.
Each item supplies `query`, `ground_truth`, `desired_num_turns=1` and
`classification_correctness` criterion demanding exact label equality.
Native serialization and deserialization roundtrip locally. No holdout is supplied.
Never submit with omitted/latest agent or evaluator version. Retain operation ID
before submission and reconcile uncertain writes rather than creating another job.

Read-only service inventory confirms optimizer list route and built-in evaluators.
`builtin.string_check` v2 exposes required constructor fields `name`, `input`,
`reference`, `type`, `operation`; exact operation is `eq`. Optimizer evaluator ref
exposes only `name` and `version`, not constructor parameters. Therefore direct
use of that built-in is NOT certified. Next live increment must bind a supported
versioned exact evaluator and prove correct/wrong/invalid canaries before submitting
optimization, or explicitly use native rubric scoring solely as search guidance
with independent frozen classification scoring. Do not silently use coherence or
token-level `builtin.f1_score` as classification accuracy/macro-F1.
Freeze any binding correction before scored comparisons; evaluator changes require
a new comparison series or recomputation of both sides, never retroactive patching.

SDK candidate fields: `candidate_id`, `name`, `mutations`, `avg_score`, `avg_tokens`,
`eval_id`, `eval_run_id`, `promotion`; terminal result adds `baseline`, `best`, `candidates`.
Retain these service fields verbatim plus row-level evaluation evidence and local
accuracy/macro-F1/counts under separate names. Composite `avg_score` is not macro-F1.
`max_stalls` documentation describes reflective minibatch proposals that may not
trigger full validation. Candidate list does NOT promise every attempted generation,
parentage or chronological lineage. Store service IDs and observation order; generation
and parent ID are null unless explicitly returned. Never infer generation from array index.
Preserve failures, warnings, missing rows and partial candidate coverage.

## Configuration And Hosting

New identity: `agentcraft-iris-optimization`; never reuse `agentcraft-hosted-tool-proof`.
Baseline config SHA-256 `cf64f2725e3148c618b522b8c0be25fcbfa195434dadab74467763329b5adcb4`;
prompt SHA-256 `27c6e80293b9035930732b89df34bde92243b1cab87d456399809a8a0234d2c6`.
Strict loader uses `agentconfig`; `compose(model, spec)` delegates agent construction
to caller-owned `llm_interface` connection. No second inference loop or custom tool runner.
Only system instructions may vary initially. Model, tools (empty), labels, parser,
evaluator, splits and thresholds are frozen. Native mutation-to-config binding must
be verified before optimization; source edits alone do not prove loaded identity.

Reuse existing authenticated Responses host, CA trust, source/image archive and
protected deployment sequence in the existing hosted testbed; do not mutate accepted
host to share an identity or copy its inference engine. Next increment implements the
new scoped hosting adapter and proves loaded prompt/config/image hashes, anonymous
denial, actual classification and stored-response readback. `azure.ai.agentserver.responses`
and `agentconfig` are available; optional `azure.ai.agentserver.agentframework` is absent.
That absence does not require a second model loop; native optimization loader support
and its compatibility with configuration overrides remain live-integration work.

Existing endpoint: `https://han-primary-foundry-resource.services.ai.azure.com/api/projects/han-primary-foundry`.
Readback confirms `gpt-5.6-luna`, model version `2026-07-09`, chat completion capability,
and protected hosted v3 active with unchanged image/source/config. Actual inference
availability, optimizer mutations, promotion and new-agent deployment remain unverified.

## Recovery And Next Assignment

Prechange archive SHA-256 `9a873d53a750d3f17a14116199df8c7ddab02fb9a1127253529cecc1f4b572d2`.
Archive comparison against disk passed before rename. Post-move check verifies 68
immutable records; prior closeout remains
`1d1caa3fd83116ff8476c97c496ee28122bd5092dfac1972e3287590d6964a9f`.
Recover into a separate directory using archive original paths; never overwrite
untracked user edits. Live rollback remains accepted host unchanged; new resources
are retained for diagnosis, not deleted without scoped teardown authority.

Next assignment: finalize native evaluator/config-loader canaries, create separate
hosted baseline, pin its actual version/image/loaded config, then submit native job
under validated constitution and retain per-candidate evaluation data. This document
does not claim a live campaign, model-quality gain, cloud deployment or full lineage.
Worker evidence remains primary evidence; only overseer publishes authoritative records.