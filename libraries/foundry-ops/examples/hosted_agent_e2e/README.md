# Hosted agent end to end (pipeline example)

One agent package and one run spec take a Foundry Hosted Agent through package -> build -> deploy ->
invoke/stream -> verify -> register-evaluator -> evaluate -> optimize -> select -> promote ->
re-verify -> re-evaluate with [`foundry_ops.pipeline`](../../README.md#pipeline). Operator entry point:
[template deploy.sh](../../../../template_apps/foundry_hosted_agent/deploy/README.md) (`deploy/cli.py`
over the pipeline). Offline smoke of the whole sequence:

```bash
python3 -B -m unittest discover -s libraries/foundry-ops/examples/hosted_agent_e2e
```

| File | Role |
| --- | --- |
| [run-spec.example.json](run-spec.example.json) | placeholder-only spec; every cloud action refuses it (`spec_placeholder`) |
| [offline_fakes.py](offline_fakes.py) | SDK-shaped fakes, fixture package and inputs, `Rig` rendering the example spec with real pins |
| [test_example_smoke.py](test_example_smoke.py) | full `run()`, resume, `until`/`from_`, baseline-retained stop |

Example package: reuse [template app](../../../../template_apps/foundry_hosted_agent/app/) (built-in
`configuration.yaml`, `agent_tools.py`, `prompts/`) or a live-run package such as
[agent/](../../../../agentcraft_projects/foundry-agent-package-e2e-20260924/agent/). The smoke test writes
its own two-tool fixture package; no second agent is maintained here.

## 1. Author the package

`<project>/agent/`: `configuration.yaml` (one default agent, `model` = `models.runtime`, tools
`module:function`), `prompts/**/*.{md,txt}`, `<module>.py` tools raising exceptions with `error_code`.
Anything else refuses (`package_file`, `package_secret`, `package_symlink`).

## 2. Author caller inputs and the run spec

Inputs (formats: [template runbook](../../../../template_apps/foundry_hosted_agent/deploy/README.md#caller-file-formats)):
`inputs/journeys.json` (1-20, include one deliberate tool failure), `criteria.json`,
`evaluator.json` (+ code and canary files pinned inside it), `optimization.json` (evaluator refs,
`max_candidates`; models come from the spec), `selection-rule.json` (frozen), `dataset/{train,validation}.jsonl`.

Copy `run-spec.example.json` into the project, replace every `<...>`, pin each file:

```bash
sha256sum agentcraft_projects/<project>/inputs/*.json agentcraft_projects/<project>/dataset/*.jsonl
S=agentcraft_projects/<project>/run-spec.json
SHA=$(sha256sum "$S" | cut -d' ' -f1)       # review the spec, then pin it
X="bash template_apps/foundry_hosted_agent/deploy/deploy.sh"; W=--authorize-cloud-write
```

| Field | Rule |
| --- | --- |
| `targets` | existing project, registry, model account; ids only, never a secret |
| `models` | `runtime` = package model; `judge`/`optimizer` fill `eval_model`/`optimization_model` (a differing file value refuses) |
| `inputs`, `evaluator`, `optimization`, `selection_rule` | `{path, sha256}` repo-relative; `items`/`train`/`validation` may be `{dataset: {name, version, sha256, rows}}` with `data: dataset` |
| `bounds` | `max_invocations` <= 20, `eval_wait_seconds` <= 1800, `optimize_wait_seconds` <= 21600, `deploy_wait_seconds` <= 900, `max_candidates` <= 20 |
| `authorization.cloud_write` | the only write stages that may run; omit `teardown` to make retention structural |
| `data` | `inline` (rows in requests) or `dataset` (registered once via `foundry_ops.data`, reused on identical bytes) |

## 3. Run, stage by stage or whole

| Step | Command | Gate | Evidence (`<records>/<series>/`) |
| --- | --- | --- | --- |
| preflight | `$X run --spec $S --spec-sha256 $SHA --until preflight` | read | `pipeline-01-preflight.json`: package model/tools, `AcrPull`, no gaps |
| build | `$X run … $W --until build` | billable ACR build | `build-src-…-image.json`: `host/repo@sha256:…` |
| deploy | `$X run … $W --until deploy` | new version | `deploy-src-…-active.json` |
| invoke, verify | `$X run … $W --until verify` | inference, stored responses | `invoke-*-result.json` per journey; 401/403, tool records = `expected_tools` |
| register-evaluator, evaluate | `$X run … $W --until evaluate` | evaluator version, eval runs | canary scores exact; `eval-*-summary.json` |
| optimize | `$X run … $W --until optimize` | one billable job | `optimize-*-identity.json`, then `-candidates.json`; `pending` = rerun to resume |
| select | `$X run … $W --until select [--demonstration]` | ledger only | `select-<job>-<rule>-<decision>.json` |
| promote, re-verify, re-evaluate | `$X run … $W` | overlay version, inference, eval | `deploy-src-…-opt-<digest>-active.json`; journeys and eval on the promoted version |

Every stage completion is retained as `pipeline-NN-<stage>.json` and reused on rerun; nothing
settled is replayed. Single actions stay available (`$X optimize --spec $S --spec-sha256 $SHA $W`,
`$X promote …`, `$X inspect …`, `$X logs …`).

Status: `complete`; `pending` (eval/optimize unsettled at its bound: rerun the identical command);
`blocked` (`pipeline-NN-<stage>-blocked-<stamp>.json`, fix and rerun); `baseline_retained` (no
candidate beat the baseline; promote and later stages not applicable, baseline stays live).

## Resume

- `--from <stage>` requires every earlier stage retained complete (`resume_gap` otherwise).
- An intent without result is outcome-unknown (`unresolved_intent`): reconcile read-only, never delete it.
- New bytes for a retained stage refuse (`record_exists`, `series_deployed`, `series_optimized`): new series.
- Long polls: `setsid nohup timeout 7200 $X run … > /tmp/run.txt 2>&1 < /dev/null &`.

## Cost and bounds

Billable: one ACR build, two hosted versions (baseline + promoted), `2 x journeys` inferences,
evaluator canary, two evals (judge inference per row), one optimization job (`max_candidates`
candidates, each evaluated on validation). Bounds cap waits and candidates; nothing retries a write.

## Teardown

Separate authority. Add `teardown` to `authorization.cloud_write` in a reviewed spec, then
`$X teardown --spec … --plan`, then `$X teardown --spec … $W`: stored responses -> sessions ->
versions -> agent read-back. Evaluators, evals, datasets, optimization jobs, model deployments and
ACR tags follow the [skill teardown order](../../../../.github/skills/foundry-native-agents/SKILL.md#lifecycle).

## Not verified

The pipeline path has run only against these fakes. Live proof of the same stages exists through the
per-action template path (series `pkg-e2e-*`), not through `pipeline.run`.
