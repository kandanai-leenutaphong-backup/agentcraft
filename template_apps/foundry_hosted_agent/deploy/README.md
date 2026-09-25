# Deployment Runbook

`deploy.sh` is the only entry point (`cli.py` over `foundry_ops.pipeline`). Run from the template root
(`template_apps/foundry_hosted_agent`). Offline `test` needs nothing; every other action
reads `env/<environment>.env` and the digest-pinned `env/<environment>.run.json`, or one digest-pinned
run spec (`--spec FILE --spec-sha256 SHA`; schema and walkthrough:
[pipeline example](../../../libraries/foundry-ops/examples/hosted_agent_e2e/README.md)). In spec mode
input flags are optional (the spec declares the files), `--env-dir`/`--records` are refused (the spec
names records), and write actions also need the stage in the spec's `authorization.cloud_write`.

Status 2026-09-24: `preflight`, `build`, `deploy`, `invoke --journeys`, `verify --journeys`,
`register-evaluator`, `evaluate` and `optimize` (submission) ran live for series `pkg-e2e-baseline-v1`;
receipts under `agentcraft_projects/foundry-agent-package-e2e-20260924/records/live/`. `select`, overlay
`deploy`, `logs` and `teardown` remain offline-tested only.

## Agent package

An agent package is a folder: `configuration.yaml` (canonical `agentconfig`, one default agent),
`prompts/**/*.{md,txt}`, and tool modules `*.py` referenced `module:function`. The run manifest
field `package_dir` names it repository-relative; absent, the built-in example in `app/`
(`configuration.yaml`, `prompts/`, `agent_tools.py`) is the package.

- Allowlist: exactly those shapes; `__pycache__/` is skipped. Any other file, dotfile, symlink,
  non-UTF-8 file, secret-shaped content (private key, JWT, account/SAS key, token assignment), a
  tool outside the package's own modules, or a configuration `include:` refuses before any cloud call.
- Image: runtime at `/app` (app/ minus the example package), package at `/app/package`,
  `AGENT_PACKAGE_DIR=/app/package`, libraries at `/opt/agent/lib`. Build context is runtime + package +
  vendored libraries + Dockerfile + lock; caller datasets, evaluators and records never enter it.
- Identity: `package_sha256 = sha256(json.dumps({package-relative path: file sha256}, sort_keys=True))`
  (the source digest's encoding). `app/source-manifest.json` carries `files`, `sha256`,
  `package_files`, `package_sha256`, `config_sha256` (= `package/configuration.yaml`). The tag and
  release label is `src-<24 hex>-pkg-<16 hex>` (49 characters). Version and response metadata carry
  `source_sha256`, `config_sha256`, `package_sha256`.

## Before the first cloud action

1. Existing resources only: Foundry project with a system-assigned identity, a model deployment,
   an Azure Container Registry. This runbook provisions nothing and grants no role.
2. The project identity holds unconditional `AcrPull` on the registry (`preflight` checks; granting
   it is a separate, owner-authorized action).
3. `cp deploy/env/example.env deploy/env/<environment>.env`, replace every `<...>`. The package's
   default agent `model` must equal `MODEL_DEPLOYMENT`.
4. `cp deploy/env/example.run.json deploy/env/<environment>.run.json`; set `series`, `agent`,
   `env_sha256` (`sha256sum deploy/env/<environment>.env`), optionally `package_dir`, and under
   `inputs` the sha256 of every caller file the series will pass (below). Review it, then pin it:
   `SHA=$(sha256sum deploy/env/<environment>.run.json | cut -d' ' -f1)`.
5. `az login --tenant <tenant>` and `az account set --subscription <subscription>`. No key,
   token or connection string is used anywhere.

Caller files (`--journeys`, `--criteria`, `--items`, `--evaluator`, `--optimization`, `--train`,
`--validation`, `--rule`, `--optimization-config`, `--instructions-from-candidate`) must lie inside the
repository and equal the manifest pin `inputs.<kind>` (kinds `journeys`, `criteria`, `items`,
`evaluator`, `optimization`, `train`, `validation`, `selection_rule`, `optimization_config`,
`candidate_record`); an unpinned or drifted file refuses. A kind may pin a list of distinct sha256 values when a
series passes several files of that kind (e.g. validation and verification `items`). Receipts record each file's path and sha256.
`--records DIR` (inside the repository) moves the evidence root from `deploy/records`. `--env-dir DIR` (an
existing directory inside the repository) reads `<environment>.env` and `<environment>.run.json` from a
caller project instead of `deploy/env`.

## Sequence

`X="bash deploy/deploy.sh"`, `M="-e dev --manifest-sha256 $SHA"`, `W=--authorize-cloud-write`.

| # | Command | Writes | Success output |
| --- | --- | --- | --- |
| 1 | `$X test` | none | `{"status": "complete", "action": "test", ...}` |
| 2 | `$X preflight $M` | none (reads) | package model/tools, `agent_exists`, no gaps |
| 3 | `$X build $M $W` | ACR build (billable) | `host/repo@sha256:...`, `package_sha256` |
| 4 | `$X deploy $M $W [--optimization-config F \| --instructions-from-candidate R]` | new hosted version | `version`, active read-back |
| 5 | `$X invoke $M $W [--input TEXT] [--stream]` or `--journeys F` | inference, stored responses, sessions | `response_id`, `output_text`; stream event count |
| 6 | `$X verify $M [--journeys F]` | none (reads, anonymous POST) | exact version, 401/403, identity, tool records |
| 7 | `$X register-evaluator $M $W --evaluator F` | evaluator version, canary eval + run | `version`, canary `passed` |
| 8 | `$X evaluate $M $W --criteria F --items F [--previous-version]` | eval + run against the deployed version (or the manifest's `previous_version`) | per-criterion summary, rows |
| 9 | `$X optimize $M $W --optimization F --train F --validation F` | one optimization job | every candidate id, `avg_score`, config sha256 |
| 10 | `$X select $M --rule F [--demonstration]` | none (ledger only) | `decision`, candidate, record path |
| 11 | `$X inspect $M` / `$X logs $M [--session-id ID]` | none (reads) | versions, sessions / redacted excerpts |
| 12 | `$X teardown $M --plan`, then `$X teardown $M $W` | deletes owned responses, sessions, versions | outcomes, agent `absent` |
| 13 | `$X promote $M $W [--instructions-from-candidate R \| --optimization-config F]` | overlay version in the same series | as `deploy` with overlay; default source is the series' one select record |
| 14 | `$X run --spec S --spec-sha256 SHA [$W] [--until STAGE] [--from STAGE] [--demonstration]` | the window's write stages | `result.status` `complete`/`pending`/`blocked`/`baseline_retained`, per-stage `pipeline-NN-<stage>.json` |

Supersedes one-off wrappers such as the E2E project's `records/live/optimize_v2.sh` and
`promote_v2.sh` (retained as evidence): the same steps are `run --from optimize --until select` and
`run --from promote` against one spec.

Every manifest action prints `{"status", "action", "receipt", "code", "seconds"}` and retains the
receipt under `<records>/<series>/`. Exit `0` complete (for `run` also `pending` and
`baseline_retained`), `2` refused or blocked. An option on the
wrong action, `--authorize-cloud-write` on a read-only action, or a missing required file refuses
before any Azure call.

Promotion flow (spec-style): baseline series `build` → `deploy` → `invoke`/`verify --journeys` →
`register-evaluator` → `evaluate` → `optimize` → `select`; then a new series whose manifest sets
`previous_version` to the baseline version and pins the select record as `candidate_record` →
`deploy --instructions-from-candidate <records>/<baseline-series>/select-...json` → `invoke`/`verify`.
A package changed by the candidate's instructions (new prompt bytes) instead needs a new `build`.

What each stage does (all mechanics are `foundry_ops.pipeline` over the stage packages):

- `build`: offline tests, `preflight`, stages runtime + package + libraries + `source-manifest.json`,
  one server-side `az acr build`; digest-pinned output.
- `deploy`: `create_version` with the digest image and identity metadata; one deployment per series.
  With an overlay the definition carries `environment_variables.OPTIMIZATION_CONFIG =
  json.dumps({"instructions": <stripped>, "model": <package model>}, sort_keys=True)` on the same image
  (proven in the optimization testbed); metadata adds `optimization_config_sha256` (sha256 of that
  JSON, what the runtime reports), `promotion` (`selected`, `demonstration` or `configured`), and for a
  candidate `optimization_candidate_id`, `candidate_config_sha256`. Read back after active. A sibling
  series' build record of the identical source label is reused; nothing is rebuilt.
- `invoke`: `hosted.invoke`, one stored version-pinned call per release/version/mode/input; `--stream`
  retains ordered events. `--journeys` runs each journey once in its declared mode.
- `verify`: active exact version (and overlay env), anonymous 401/403, every stored response by raw GET
  with output and identity equal. Tool records from `traces.tool_calls(metadata_prefix="tool_call.")`
  must each carry the native item and the `tool_call.<n>` record (status, timing). With `--journeys`:
  per journey the ordered `(name, ok|error, error_code)` list equals `expected_tools`; streamed journeys
  also open `response.created`, end `response.completed`, carry the stored call ids, and their text
  deltas equal the stored output text. `expected_answer` is reported as `answer_match`, not gated.
- `register-evaluator`: `code_evaluator_definition` → `register_code_evaluator` (read back) →
  `run_code_evaluator_canary`; a canary mismatch fails.
- `evaluate`: `run_agent_eval` against the deployed version; resumes from its summary record. `--previous-version`
  targets the reviewed manifest's `previous_version` instead (baseline side of a side-by-side report); refuses
  `previous_missing` when it is null.
- `optimize`: `optimization_job` (rows projected to `query`/`ground_truth`/`desired_num_turns`/`criteria`
  or `item_fields`) → `submit_optimization` once → `wait_optimization` → `list_candidates` →
  `resolve_candidate_config` for every candidate, retained in `optimize-<key>-candidates.json`. One job
  per series; unsettled returns `settled: false` and a rerun resumes polling.
- `select`: frozen rule over that record. Eligible = `avg_score` strictly above the same job's baseline;
  highest wins, ties to earliest observation; none eligible (or baseline-only) → `baseline`.
  `--demonstration` promotes the top candidate labelled `demonstration` only if the rule allows it.
  Scores are the native composite, labelled so.
- `teardown`: stored responses, then sessions, then versions created by this series, then agent
  read-back. Evaluators, evals, datasets and optimization jobs are not torn down here.

## Caller file formats

| Kind | Shape |
| --- | --- |
| journeys | `{"journeys": [{"id", "input", "stream": bool, "expected_tools": [{"name", "status": "ok"\|"error", "error_code"?}], "expected_answer"?, "notes"?}]}`, 1-20, unique ids and (input, stream); `error_code` iff `error` |
| criteria | `{"testing_criteria": [...], "name"?, "input_template"?, "item_fields"?, "wait_seconds"? (<= 1800)}` or a bare list |
| items, train, validation | JSON list or JSONL of non-empty objects |
| evaluator | `{"name", "metric", "display_name", "data_schema", "description"?, "code_text" \| ("code_file", "code_sha256"), "canary": {"criterion_name", "item_schema", "data_mapping", "match_field", "metric"?, "cases" \| ("cases_file", "cases_sha256")}}`; files relative to the spec; cases `[{"item", "expected"}]` or `{"canaries": [...]}` |
| optimization | `{"evaluators": [{"name", "version"}], "optimization_model", "max_candidates", "eval_model"?, "max_stalls"?, "optimization_config"?, "item_fields"?, "wait_seconds"? (<= 21600)}` |
| selection_rule | `{"status": "frozen", "score": "avg_score", "eligibility": "strictly_above_baseline", "tie_break": "earliest_observation", "fallback": "baseline", "demonstration": {"allowed": bool, "label": "demonstration"}}` |
| optimization_config | `{"instructions", "model"?}`; `model` must equal the package model |
| candidate_record | a `select` result (or complete `select` receipt) with decision `selected` or `demonstration` |

## Idempotency and reruns

Each mutation writes an intent record before the call and a result record after it. A rerun reuses
results (`build`, `deploy`, `invoke`, `evaluate`, `register-evaluator`, `optimize` return or resume the
retained outcome; `select` is deterministic and rewrites nothing). An intent without a result means
the outcome is unknown: the action refuses (`unresolved_intent`). Reconcile by read-back
(`preflight`, `verify`, `inspect`, `az acr task show-run`); never delete an intent to retry.

A new version of an existing agent needs a new run manifest with a new `series`,
`previous_version` (the current latest) and `previous_image`; the old series' records stay intact.
With an optimization overlay the image is unchanged by design and `previous_image` is not compared.

## Failure playbook

| Code in receipt or stderr | Meaning | Action |
| --- | --- | --- |
| `--authorize-cloud-write` / `--manifest-sha256` | missing explicit authority or pin | pass it deliberately |
| `... does not apply to ...`, `<kind>_missing` | option on the wrong action, required file absent | fix the command |
| `env_placeholder`, `env_missing`, `env_format`, `env_unknown` | env file incomplete or wrong | fix `env/<environment>.env`, update `env_sha256`, re-pin |
| `env_secret`, `env_auth_disabled`, `env_agent_access` | secret-shaped or auth-weakening variable | remove it; use managed identity or Key Vault references |
| `manifest_digest`, `manifest_pin`, `manifest_action`, `manifest_fields`, `manifest_package`, `manifest_inputs` | manifest changed, env drifted, action not allowed, bad package path or pins | review, then re-pin |
| `input_unpinned`, `input_pin`, `input_path` | caller file not pinned, drifted, or outside the repository | review the file, pin its sha256 under `inputs` |
| `package_file`, `package_symlink`, `package_secret`, `package_binary`, `package_size`, `package_config`, `package_tool` | package outside its allowlist, secret-shaped or tools outside the package | fix the package; secrets never enter it |
| `record_exists` on `run-manifest.json` | series already bound to other bytes | new `series` |
| `series_deployed`, `series_optimized` | series already has another deployment / job | new `series`; never resubmit |
| `account_mismatch` | active `az` account differs | `az account set --subscription ...` |
| `preflight_gaps` | project, registry, `AcrPull`, model or ownership gap | fix the named gap; this runbook grants nothing |
| `unresolved_intent`, `build_outcome_unknown`, `version_unknown`, `job_identity_unknown` | prior write outcome unknown | reconcile read-only |
| `readiness_deadline` | version not active in 300 s | inspect with `verify`; do not redeploy |
| `anonymous_accepted` | endpoint answered without credentials | stop; treat as an auth incident |
| `identity_mismatch`, `version_readback`, `stored_response_drift`, `optimization_readback` | serving image/config/package/overlay differs from the build | stop; inspect the version |
| `tool_call_missing`, `tool_call_mismatch`, `tool_record_incomplete`, `stream_order`, `stream_tool_drift`, `stream_text_drift` | tool records or stream differ from the journey or the runtime contract | inspect the stored response; do not re-invoke to recover |
| `journey_not_invoked` | verify journey without its invocation | run `invoke --journeys` first |
| `criteria_missing`, `items_missing`, `train_missing`, `evaluators_missing`, `canary_missing` | evaluation/optimization input absent or empty | supply the pinned file |
| `canary_failed` | native evaluator scores differ from expected | inspect retained canary rows; no eval or job |
| `rule_unfrozen`, `rule_unsupported`, `demonstration_refused`, `optimization_missing` | selection rule not frozen/pinned or unknown, demonstration not allowed, no job | freeze and pin the rule; run `optimize` |
| `baseline_retained` | selection kept the baseline | nothing to promote |
| `overlay_fields`, `overlay_model`, `overlay_instructions`, `overlay_choice` | overlay carries more than instructions, a foreign model, or both flags | fix the overlay file |
| `still-present`, `delete-failed` in teardown | eventual consistency or blocked delete | rerun teardown; results are recorded per step |

## Not done here

ACR image deletion, role grants, model and optimizer deployment, dataset upload
(`pending_upload`/Blob; `evaluate` sends inline items), network changes, and teardown of evaluators,
evals and optimization jobs. Baking candidates into `app/.agent_configs` is not automated; the overlay
is the definition env var. Registry cleanup: `az acr repository delete` on the owned tag, separately
authorized.
