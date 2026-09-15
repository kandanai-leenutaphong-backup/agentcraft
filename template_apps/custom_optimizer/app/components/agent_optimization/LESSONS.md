# Optimization Lessons

These lessons govern the repeatable process, not a guaranteed score. Actual campaign
measurements remain in the owner-partitioned local ledger and are never rewritten by this
document. [PROCESS.md](PROCESS.md) owns the generation method.

## Show the Climb Honestly

- Start from a defensible generic baseline, not an intentionally broken control. The baseline
  is generation 0; `joint-12` adds twelve successors, making thirteen measured versions.
- Plot each measured score and latency, including regressions. An incumbent is the strongest
  measured candidate so far, not a relabeling of the latest one.
- Ground the next hypothesis in development failures and inspect the actual tool outputs.
  Evaluation aggregates are reused feedback, not an untouched test or proof of generalization.
- Prefer understandable evidence changes and useful comparisons over a headline score. Do
  not reduce an algorithm's capability to fabricate gradual progress or suppress worse runs.
- Distinct tools answer distinct questions. Inventory, ordering, evidence concentration,
  technique combinations, calibration and uncertainty are different views where supported.
  A higher tool count or different approach name alone proves nothing.
- Schedule detector changes and diversity early. A long sequence of prompt-only refinements
  can exhaust the generation budget before the required comparisons are measured.

## Execution Lessons

| Observed failure | Repeatable response |
| --- | --- |
| Typed evaluator rejected otherwise valid JSON diagnoses/citations | Host supplies a strict response schema and citation values derived only from returned knowledge. Legacy request formats stay unchanged. |
| Full-cohort baseline exceeded a short browser wait | Budget the wait for training plus evaluation; recover the same experiment from persisted terminal run state, not another baseline. |
| A zero-error browser assertion stopped a fully measured baseline | Completion means all cases retained and errors counted consistently, not rerunning until an error-free sample appears. Validate stage counts, confusion-matrix totals, error rate and stage ordering. Probe admission still requires an error-free exact proposal. |
| A keyword scan mistook reference prose for a leaked label | Parse the recorded JSON evidence and check protected label fields and exact case IDs. The word "expected" in an advisory sentence is not an outcome-label field. |
| A long campaign outlived the browser driver's CLI session allowance | Native CLI credentials expire within one hour. `joint-12` permits two session attempts per declared version; each resume uses the same ledger and unchanged case/configuration pins. |
| Truncated or mistyped development case IDs produced misleading terminal refusals | Reuse exact returned IDs. A refused case is not a reason to broaden data permissions. |
| A large/arbitrary profile slice produced constant or irrelevant scores | Match current evidence features, use an explicit prior row, deduplicate and inspect contrasting incidents. |
| Multiple model campaigns competed for provider capacity | Run the requested campaign alone when possible; keep worker count fixed and preserve all throttling/error outcomes. A configured quota is not a guaranteed throughput. |
| Rich evidence and long prose exhausted bounded output | Return compact question-specific observations and concise model responses. Source/result limits are ceilings, not targets. |
| A useful source/tool existed but was invisible to the coding agent | Read the registry-backed capability catalogue before designing tools; distinguish visibility, permission, actual usage and measured usefulness. |
| A tool's name/plan promised more than its source computed | Compare each question and return contract against its actual query and probe output. In campaign `4be9a88ac16146969822141c6c4a29db` v2, `calibration_view` only counted categories, while `timeline_view` only counted distinct timestamps; neither class calibration nor ordered temporal structure was implemented. Keep the version and measure it under its actual semantics; fix the mismatch in a successor. |
| A comparison claimed controls that differed from its selected parent | Compare immutable parent and candidate pins, not just `held_fixed` prose. The same campaign's v7 selected parent v4 but changed detector 2 to 3 as well as tools and prompt. Its result is a joint change, not an isolated evidence-bundle effect. A strict tool ablation must retain the exact parent prompt, detector and knowledge setting. |
| Runtime or skill changed during a campaign | Preserve recorded task/skill/source identity. Restart only at a safe boundary; a changed fixed contract requires a new experiment. |
| A renewed CLI restarted an already-completed training stage | Resume from the stored state: pending -> train, tuning/running -> wait, tuned -> evaluate, completed -> design the next version. Retain the extra attempt, count generations by immutable versions, and verify every attempt separately. Never select a repeat merely to improve its score. |

[scripts/continue_campaign.mjs](scripts/continue_campaign.mjs) implements the stage-only
continuation rule over ledger-change events and an explicitly supplied owner-authorized
loopback API. It starts no model directly, authors no candidate and modifies no record on
disk. Its tests refuse duplicate training and attempts to advance in-flight/terminal states.
Long provider-backed stages therefore need not depend on one coding-agent credential lifetime.

The approved CLI helper also makes `tune` and `evaluate` idempotent for staged campaigns:
it reads the requested version's feedback first and returns an existing stage with
`stage_reused: true` instead of starting another attempt. This applies to running, completed
and failed attempts; an authorized operator must explicitly admit a failed-stage retry.
The request never silently switches versions. This closes the observed gap where the stage
coordinator advanced correctly but a renewed coding-agent session repeated evaluation anyway.
The evaluator and its recorded scores remain unchanged; earlier repeats remain visible.

Resumed sessions also exposed a response-size failure: accumulated operator guidance preceded
the exact parent training run and development case IDs in `feedback`, so a truncated CLI result
hid the identifiers required by the proposal gate. The helper now returns compact staged
feedback with run IDs and one failure example per represented grade before metric summaries,
plus `latest_operator_guidance` without the full history. Tests include per-class metrics and
large old guidance, not only one-number metrics; they assert identifier ordering explicitly.
Request complete sections with `./opt feedback '{"version":4,"fields":["training_audit"]}'`.
`training_metrics`, `evaluation_metrics`, `development_failures`, `versions` and
`operator_guidance` are also selectable; the owner API and stored feedback remain complete.
Missing classes in failure examples are not invented. An invalid development-case ID may
produce the same terminal 404 as an unknown session; read current feedback and reuse exact IDs
before treating a refused probe as a credential problem. Never broaden the case allowlist.

Rejected inline proposals may never reach the immutable probe ledger. The helper retains one
bounded private `last-probe-rejection.json` with HTTP status, case IDs, parent version/run and
selected tool IDs only. It records no credentials, prompts or source bodies, refuses symlinks,
and never retries or converts a refusal into success. Match those IDs against the actual cohort
and parent pins before assigning a cause; a valid case list does not prove valid ablation controls.
An exact-parent experiment also needs the parent's exact prompt, not only its name and tool IDs.
CLI feedback includes `agent_configuration` for the selected owned version: exact system prompt,
tool IDs, detector version/digest and knowledge setting. Unknown version numbers are refused,
not silently replaced with the latest version. This read-only authoring metadata does not alter
the evaluator's feedback, configuration or scoring. Reuse those bytes for a controlled ablation.

## Local Evidence Contract

Before launch record the command, protocol, baseline/successor count, full case membership,
model, resource bounds, source/profile identities, knowledge policy, skill/task and access
contract. Never depend on a temporary terminal session as the only record.

Each generation keeps immutable detector/tool/prompt/plan pins and its exact passed probe;
both stages keep every case outcome, metrics and genuine best/worst request/response examples.
Finish only when every requested version completed both stages and the coverage gates pass.
Recompute metrics and membership from saved results, then verify the browser plots and replays.

[scripts/verify_campaign.py](scripts/verify_campaign.py) performs one read-only scan of an
experiment, pins the baseline's immutable artifacts once, rechecks those hashes, recomputes
completed-stage metrics and writes `ledger-integrity.json` plus `trajectory.csv` to a separate
proof directory. `--complete` additionally requires the declared version, stage and exploration
counts. [tests/test_verify_campaign.py](tests/test_verify_campaign.py) includes edited-case,
changed-baseline, forged-receipt and incomplete-campaign negatives. Neither a partial pass nor
internally consistent model-response records prove that a whole campaign finished.

Local persistence is not an external backup. A host interruption retains failed/partial
attempts; partial results do not count as a completed generation. Never replace a failed run
file or claim a submitted CLI task finished the campaign.

### Recover After a Host Crash

Before starting the host, archive its saved ledger and inspect each stage's terminal metadata.
Completed stages stay complete. A stage still marked running with no terminal `run.json`
becomes a failed attempt at startup; retry that immutable version only through the owned API.
Preserve partial JSONL bytes and their hash, never append a retry into the interrupted file.

Observed 2026-09-12 in `4be9a88ac16146969822141c6c4a29db`: versions 1-4 survived complete;
v5 training `27d682af3316418a9577fe93d2f07e6f` retained 1,440 complete, unique rows. Its retry
is a new run, `a2d5d41382bc436e8d571a40604d71a8`, with the same tool/detector/prompt pins.
The pre-recovery ledger and restart implementation are archived in the campaign proof folder.
This records recovery, not a claim that the remaining generations completed.

The later v7 interruption retained 969 complete rows in training run
`569fa6e6920d4194b85d98d6ac8ede3d`, although its last progress counter was 960. Retry
`d27b626c2c724b0fba1f41bbe3ac99fb` completed all 5,958 training cases with unchanged pins.
Refresh the next proposal's `parent_training_run_id` from completed feedback after recovery;
an earlier instruction naming the interrupted attempt is stale even when the version number
is unchanged. Count retained rows from complete JSONL records, not the last progress counter.

Compare measurement sources and dependency manifests with the launch archive before reusing
the campaign. The verifier accepts an additional process implementation identity only when a
`recovery-implementation-*.tar.gz` archive has identical measurement files; `cli.py` may differ
for the separately recorded authoring-transport update. Scorer, dataset/profile adapter,
model request builder, sandbox, detector and knowledge code must still match. The skill pin
is checked independently. A different measurement implementation requires a new experiment.

## Helper Generation Reaches Live Workspaces Only By Reinstallation

A running backend process holds the helper generator it imported at start. Changing
[cli.py](cli.py) leaves every existing and future session of that process on the old `./opt`,
so a newly added operation is absent until the process restarts or the files are replaced.

[scripts/install_helper.py](scripts/install_helper.py) is the replacement path, and `generate`
in it is the same function workspace initialization calls, so an installed helper is never a
hand-edited variant. The operator path additionally proves the directory is an initialized
`<session-uuid>/workspace`, reads the installed helper's request URL and `Origin` with `ast`
rather than importing or executing it, refuses any other target, refuses symbolic links,
writes only `opt` (0500) and `optimization_draft.py` (0400) atomically, and reports before/after
SHA-256 digests with an `unchanged` flag so a repeat install is visibly idempotent. It never
reads or copies the session's `task-access.json`.

Reinstallation changes the authoring transport of a campaign already in flight. It does not
change measurement: scoring, case membership and worker pins are untouched, and the helper
digests differ afterwards. Record it as an operator intervention.

Large nested JSON commands caused repeated parsing failures and pushed the coding agent back
to prompt-only variants. The helper now supports a bounded local `draft` operation: `reset`
starts a new proposal, `patch` merges named proposal fields (arrays replace), `append_tool`
adds a tool, and `show` returns one selected field. `probe` with `draft: true` and `case_ids`
sends the assembled proposal to the unchanged exact-proposal gate. No candidate code runs
during assembly, no arbitrary path is accepted and no credential enters the draft. A changed
draft still requires a new successful probe. Publication remains by `probe_id` only.

Example shapes, using real returned case IDs rather than the placeholders below:

```json
{"reset":true,"patch":{"name":"candidate-name","parent_version":3}}
{"patch":{"design_audit":{"hypothesis":"One testable observation-level change."}}}
{"append_tool":{"name":"question-specific-tool","code":"def run(ctx):\n    ..."}}
{"show":"tools"}
{"draft":true,"case_ids":["development-id-one","development-id-two"]}
```

The first four payloads go to `./opt draft`; the last goes to `./opt probe`. They illustrate
transport, not complete candidate contracts. Supply every required field before probing.

## Current Limits

GUIDE incidents are already grouped, labels cover grades only, and development profiles make
training F1 in-sample. Diagnosis and action correctness are unscored; recommendations are
never executed. There are no verified joins to unrelated replay telemetry. The current
investigator receives host-scheduled evidence and knowledge, not a dynamic tool-choice loop.

## Lessons From the Completed Twelve-Generation Run

Campaign `4be9a88ac16146969822141c6c4a29db` completed on 2026-09-13. Its
[measured trajectory and acceptance](../../../docs/AGENT_OPTIMIZATION.md#completed-twelve-generation-climb)
retain every regression and distinguish primary measurements from repeated/interrupted attempts.

- An independently useful view can matter more than additional prompt wording. v11 added
  matched detector-specific development support with all other parent pins unchanged; evaluation
  F1 rose from 0.328578 to 0.557782. v13's later prompt-only refinement regressed. Neither
  observation establishes generalization outside this repeatedly used cohort.
- Measure advisory knowledge separately. v11/v12 kept exact prompt, tools and detector pins;
  knowledge-off requests actually omitted retrieval. F1 fell 0.005550 and mean evaluation
  latency fell 1,009.528 ms. Presence is not usefulness, and this small score difference has
  no repeat-based significance estimate.
- Probe admission proves execution, not each promised computation. v8 passed its exact
  three-case probe with zero correct grades; v9 still omitted the prior it claimed to repair.
  Inspect each question's returned view, not only global detector-summary variation.
- Match structured keys exactly and prove their returned value. The seven-character
  `__all__` key appeared with support 5,958 in all three v10 probes; earlier `__all` queries
  silently returned no prior. A correct selector alone did not guarantee a score increase.
- SQL `LIMIT` and subsequent list slicing create separate omissions. A query's `truncated`
  flag does not prove the full source was covered when the SQL itself limits rows; report
  bounded counts and omitted output honestly. Row totals are not distinct-signature totals.
- Validate publication metadata before spending a model-backed probe. v11 needed repeated
  successful probes solely because rationale, tradeoff or tool-family metadata was rejected
  later. Small draft patches preserved authored source while fixing those required fields.

The best version need not be the last. Report both, with latency stage definitions, per-class
tradeoffs and provider errors. Do not relabel a multi-lever change as a controlled comparison
because its generated audit says the other levers were held fixed.