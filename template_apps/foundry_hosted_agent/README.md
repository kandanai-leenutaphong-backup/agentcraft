# Foundry Hosted Agent Starter

Minimal reusable skeleton for a native Microsoft Foundry Hosted Agent: a Responses protocol
container whose model and tool loop is Microsoft Agent Framework through `llm_interface`,
configured by one canonical `agentconfig` `configuration.yaml`, plus a lifecycle whose only entry
point is [deploy/deploy.sh](deploy/deploy.sh) over the shared `foundry_ops.pipeline`.

Generalized from [testbeds/foundry-hosted-agents](../../testbeds/foundry-hosted-agents/deploy/README.md)
(live-accepted 2026-09-22). Kept: platform CA trust with verification on, exact image/config identity
in response metadata, stored-response read-back, anonymous 401/403 refusal, teardown order
responses -> sessions -> versions, 50-character label limit. Stripped: nonce proofs and envelopes,
grants, overlap builds, cancellation probes.

Status 2026-09-25: 81 offline tests pass (`bash deploy/deploy.sh test`, real local SDKs, no network).
The generic lifecycle moved into [`foundry_ops.pipeline`](../../libraries/foundry-ops/README.md#pipeline);
`deploy/cli.py` maps the same actions onto it, and `run --spec` executes the whole sequence (offline-tested
only).
Live for series `pkg-e2e-baseline-v1` of the
[package E2E](../../agentcraft_projects/foundry-agent-package-e2e-20260924/records/live/pkg-e2e-baseline-v1/):
`preflight`, `build`, `deploy`, `invoke --journeys` (streaming and non-streaming, one deliberate tool
failure), `verify --journeys`, `register-evaluator`, `evaluate`, `optimize` (submission and polling).
`select`, overlay `deploy`, `logs` and `teardown` are offline-tested only; the redeploy series
`pkg-e2e-optimized-v1` is in progress.

## File map

| Path | Owns |
| --- | --- |
| [app/main.py](app/main.py) | `ResponsesAgentServerHost` handler, streamed `run_agent` (`llm_interface.connect`), native event emission, cancellation, identity metadata, `--self-check` image smoke |
| [app/tool_calls.py](app/tool_calls.py) | `ToolCallRecorder`: the one instrumentation wrapper around every configured tool, call-id binding, structured errors |
| [app/composition.py](app/composition.py) | `package_root` (`AGENT_PACKAGE_DIR`), `package_manifest` (package digest), `load_spec`: exactly one default agent; tools only from `agent_tools` (built-in) or the package's own modules. `load_optimized_spec`: native candidate loading |
| [app/configuration.yaml](app/configuration.yaml) | agent name, model deployment, prompts, tools |
| [app/prompts/agent.md](app/prompts/agent.md) | instructions |
| [app/agent_tools.py](app/agent_tools.py) | example deterministic tools `count_words` and `describe_unit` (fails with declared `unknown_unit`) |
| [deploy/deploy.sh](deploy/deploy.sh) | entry point; sets `PYTHONPATH` to the repository libraries |
| [deploy/cli.py](deploy/cli.py) | actions and flags -> `foundry_ops.pipeline` stages; `run` over a run spec; refusals before any Azure call; receipts |
| [deploy/lifecycle.py](deploy/lifecycle.py) | template-specific only: image layout (runtime, package, vendored libraries, Dockerfile, lock), `agentconfig` package reading, offline self-check, env/manifest or spec context |
| [deploy/Dockerfile](deploy/Dockerfile) | digest-pinned uv + Python 3.12 base, hash-locked install into the image's system interpreter |
| [deploy/runtime-requirements.in](deploy/runtime-requirements.in), [.lock](deploy/runtime-requirements.lock) | third-party pins; lock derived from the testbed's live lock minus repository packages |
| [deploy/env/example.env](deploy/env/example.env), [example.run.json](deploy/env/example.run.json) | documented targets (placeholders) and the run manifest pinning them |
| [deploy/README.md](deploy/README.md) | run order, expected output, failure playbook |
| [tests/](tests/) | runtime ([test_runtime.py](tests/test_runtime.py)), lifecycle and CLI refusals ([test_deploy.py](tests/test_deploy.py)), package lifecycle over fakes ([test_lifecycle_package.py](tests/test_lifecycle_package.py)) |

## Run order

Full procedure, operator inputs, gates, evidence and recovery:
[protocol-foundry-agent-lifecycle](../../.github/protocols/protocol-foundry-agent-lifecycle/SKILL.md).
Operators write only an agent package, pinned caller files and an env/run-manifest pair.

`test` -> `preflight` -> `build` -> `deploy` -> `invoke` -> `verify` -> `register-evaluator` ->
`evaluate` -> `optimize` -> `select`; then a new series `deploy --instructions-from-candidate` (or
`--optimization-config`) -> `invoke` -> `verify` -> `evaluate`. `teardown --plan` -> `teardown` only
under separate authority. Cloud writes need `--authorize-cloud-write`; every cloud action needs
`-e <environment>` and `--manifest-sha256`, or `--spec FILE --spec-sha256` (one run spec; same-series
`promote` and `run [--until S] [--from S]`, see the
[pipeline example](../../libraries/foundry-ops/examples/hosted_agent_e2e/README.md)). Commands, file
formats and failure codes: [deploy/README.md](deploy/README.md).

## Tool-call observability

Every tool listed in `configuration.yaml` runs through `tool_calls.ToolCallRecorder`; `main.py` holds no
tool logic. The `llm_interface` `authorize_tool` hook binds each execution to its model `call_id`; a
name outside the configured set, an empty or >128-character `call_id`, or a repeated `call_id` is refused.

A caller joins two sources by `call_id`, in both the stream and the stored response
(`GET /responses/{id}`, `store: true`):

| Field | Where | Kind |
| --- | --- | --- |
| `call_id`, `name`, `arguments` (JSON string) | output item `type: function_call` | native |
| `result` (JSON string; `{"error": {"code", "message"}}` on failure) | output item `type: function_call_output`, field `output` | native |
| `started_at`, `ended_at` (UTC ISO-8601, ms, `Z`), `duration_ms` (float, 3 dp), `status` (`ok`/`error`), `error_code` (string or `null`), plus `call_id`, `name` | response `metadata["tool_call.<n>"]` | custom |

The custom part exists because native function-call items carry no timing, status or error code.
`<n>` is 1-based in completion order. The value is compact JSON, sorted keys, no spaces, at most 512
characters:

```json
{"call_id":"call_fixture_1","duration_ms":1.056,"ended_at":"2026-09-24T06:37:55.895Z","error_code":"unknown_unit","name":"describe_unit","started_at":"2026-09-24T06:37:55.894Z","status":"error"}
```

Identity keys and `tool_call.<n>` keys share the 16-key Responses metadata limit; `create_server`
refuses an identity that leaves fewer than `LIMITS["max_tool_calls"]` free keys. `response.created`
carries identity keys only. `tool_call.<n>` keys appear from `response.completed` onward.

Stream event order for one tool call followed by an answer:
`response.created`, `response.in_progress`, `response.output_item.added` (function_call),
`response.function_call_arguments.delta`, `response.function_call_arguments.done`,
`response.output_item.done` (function_call), `response.output_item.added` (function_call_output),
`response.output_item.done` (function_call_output), `response.output_item.added` (message),
`response.content_part.added`, `response.output_text.delta`..., `response.output_text.done`,
`response.content_part.done`, `response.output_item.done` (message), `response.completed`.
Non-streaming responses carry the same output items and metadata.

Failures:

- Tool exception: the result is `{"error": {"code": <error_code>, "message": ...}}`, `status: error`,
  and the turn completes. `error_code` is the exception's `error_code` attribute when it matches
  `[A-Za-z][A-Za-z0-9_.-]{0,63}`, and its message is kept (at most 256 characters). Otherwise the code
  is the exception class name and the message is `tool failed`, so internals are not exposed.
- Unknown tool: refused before execution. The response is `failed`, with no function-call items and
  no `tool_call.<n>` key.

## Agent package

An agent package is a folder holding the agent's entire internals: `configuration.yaml` (same schema
as [app/configuration.yaml](app/configuration.yaml)), `prompts/`, and tool modules named
`module:function`. At startup `main.py` reads `AGENT_PACKAGE_DIR` (in the image `/app/package`).
Unset: the built-in example in `app/` (`configuration.yaml`, `prompts/`, `agent_tools.py`) is served.

- Refused at startup: `AGENT_PACKAGE_DIR` set but blank, missing, not a directory, or without
  `configuration.yaml`.
- Tool modules: `module` is one identifier naming `<package>/<module>.py`, a regular non-symlink file.
  It is executed without changing `sys.path` or writing bytecode. Refused: dotted or path-like names,
  stdlib names, runtime names (`main`, `composition`, `tool_calls`, `agent_tools`, `agentconfig`,
  `llm_interface`, `agentcraft_core`), anything importable elsewhere, and `function` values that are
  not plain functions defined in that module (re-exports, classes).
- Identity: response metadata and `--self-check` gain `package_sha256`. It is the SHA-256 of
  `json.dumps({relative_path: file_sha256}, sort_keys=True)` over every file in the package, with
  `__pycache__` excluded; a symlink anywhere refuses. This is the same serialization as the source
  manifest. For the built-in example it covers the three members listed above. Existing identity keys
  are unchanged.
- Tool calls: package tools run through the same `ToolCallRecorder`. An exception's `error_code`
  attribute becomes `status: error` plus that code.

## Optimized configuration

At startup `composition.load_optimized_spec` loads candidates through the native
`azure.ai.agentserver.optimization.load_config`, with `config_dir=app/.agent_configs` fixed and the
platform managed identity.

- Baseline: with no `OPTIMIZATION_CANDIDATE_ID`, no `OPTIMIZATION_CONFIG` and no `app/.agent_configs/`,
  `load_config` is not called. The spec is `configuration.yaml` unchanged and no identity key is added.
- Applied: only `instructions` is applied. `model` must be absent or equal to the configured deployment.
  `skills`, `tools`/`tool_definitions`, `temperature` and `skills_dir` are refused. `name` is read but
  not applied.
- Refused (the process fails to start): an unsafe candidate id (outside `[A-Za-z0-9_-]{1,128}`), inline
  JSON that is not an object or has keys outside `name, instructions, model, temperature, skills, tools`,
  a requested candidate that fails to load, and a requested candidate that `load_config` silently
  replaces with `baseline/`.
- Identity: response metadata keeps `source_sha256`, `config_sha256`, `agent_name` and `agent_version`
  unchanged. It also adds `optimization_source` (`env`, `local` or `api`) and
  `optimization_candidate_id` (candidate id, `inline` or `baseline`). The third addition is
  `optimization_config_sha256`, the SHA-256 of `json.dumps({"instructions": ..., "model": ...},
  sort_keys=True)` for the applied spec.
- Baked candidates under `app/.agent_configs/<id>/` (`.md`/`.yaml`) enter the build context and the
  source digest through the existing app-suffix allowlist.

## Left to the app author

- Real tools and prompts: ship an agent package (above), or add functions to `agent_tools.py` and
  list them in `configuration.yaml`.
  Keep tools side-effect-free or idempotent; host cancellation cannot undo a synchronous side effect.
  Declare stable failure codes as an `error_code` class attribute on the raised exception.
- Input contract: `parse_input` accepts bounded text only; structured input is the author's.
- `LIMITS` in `main.py` (model/tool calls, tokens, timeout).
- Targets, run manifests and review of each manifest digest.
- Role grants (`AcrPull` for the project identity), model deployment, networking, ACR image cleanup.
- Evaluation and optimization inputs (journeys, criteria, evaluator, optimization spec, rows,
  selection rule). The lifecycle runs them; the runtime loads candidates but does not create them.
- Lock refresh: edit `runtime-requirements.in`, regenerate with the `uv pip compile` command in the
  lock header, rerun `test`.

## Limits

- Live-proven in the baseline series: real model calls through `llm_interface`, platform
  `DefaultAzureCredential` and `FOUNDRY_*` injection, the server-side image build, streaming and
  non-streaming tool calls with `tool_call.<n>` records, stored-response read-back, anonymous refusal.
- Not exercised live: the `api` source of `load_config` (Foundry candidate fetch), the overlay
  `deploy`, `select`, `logs`, `teardown`, and more than two tool calls per turn.
- `azure-ai-agentserver-optimization==1.0.0b1` and its hashes are copied from the optimization
  testbed lock and have not been re-resolved.
- The lock is a subset of the testbed's live-accepted lock; resolution from the index (the testbed
  used a local wheelhouse) is unverified.
- Secret-shaped env detection is a pattern backstop; per-variable formats are the primary guard.
