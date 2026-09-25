# Foundry Ops

`agentcraft-foundry-ops` owns Foundry lifecycle glue repeated across the hosted-agent,
evaluation and optimization testbeds: intent-before-mutation evidence, pinned run manifests,
hosted-version deploy/invoke/cancel/teardown, stored-response read-back, bounded session logs,
ACR build identity and evaluation read-back checks, plus generic native steps for hosted agents:
agent-target evals, custom code evaluators, optimization jobs and tool-call traces.

It is thin over official clients. The caller constructs `AIProjectClient`
(`azure-ai-projects`), agent-scoped OpenAI clients (`project.get_openai_client(agent_name=...)`),
credentials and targets at the edge and passes them in. No module reads the environment,
acquires a credential or imports Azure/OpenAI/httpx at import time. Base install has no
dependencies; `[http]` adds `httpx` for `anonymous_probe` and `read_stored_response` when no
`http_client` is passed. Offline-tested with fakes; partly live-proven through the template (see
[Live status](#live-status)).

```python
from foundry_ops.core import EvidenceLedger, load_run_manifest, series_directory
from foundry_ops.hosting import deploy_version, hosted_definition, invoke

run = load_run_manifest(path, expected_sha256=sha, action="deploy", allowed_root=deploy / "env",
                        pins={"target_sha256": deploy / "env/target.json", "constitution_sha256": constitution})
ledger = EvidenceLedger(series_directory(deploy / "records", run.series))
run.bind(ledger)
deployed = deploy_version(project, ledger, key=source_sha, agent_name=run.agent,
                          definition=hosted_definition(image), metadata={"source_sha256": source_sha})
reply = invoke(openai_for_agent, ledger, key="n1", agent_name=run.agent, version=deployed["version"], input="q")
```

## Layout

One subpackage per lifecycle stage; each `__init__` re-exports its public names (`__all__`). Stage
subpackages import only `core`, never each other; `pipeline` is the one composition layer that imports
stages, and nothing imports `pipeline` (both guarded by `test_build_imports.py`).

| Subpackage | Modules | Stage |
| --- | --- | --- |
| `core` | `errors`, `records`, `manifest`, `bounds`, `logs`, `identifiers` | stdlib-only foundation |
| `build` | `image` | ACR image build and digest pin |
| `hosting` | `hosted`, `verify`, `traces` | deploy, invoke, cancel, sessions, teardown, read-back, tool-call traces |
| `evaluation` | `evals`, `evaluators` | eval runs, rows, criteria, code evaluators, canaries |
| `optimization` | `optimize` | optimization jobs, candidates, configs |
| `data` | `datasets` | native Foundry Datasets: canonical JSONL, sha-pinned version, register, byte read-back, eval `file_id` / optimization `reference` sources |
| `pipeline` | `spec`, `inputs`, `source`, `stages`, `run`, `clients` | declarative run spec driving the whole hosted-agent lifecycle ([below](#pipeline)) |

## Pipeline

One digest-pinned run spec (JSON canonical, YAML accepted) drives package -> build -> deploy ->
invoke/stream -> verify -> register-evaluator -> evaluate -> optimize -> select -> promote ->
re-verify -> re-evaluate. Worked example with an offline end-to-end smoke:
[examples/hosted_agent_e2e](examples/hosted_agent_e2e/README.md).

```python
from foundry_ops import pipeline

spec = pipeline.load_run_spec("proj/run-spec.json", expected_sha256=sha, repo=repo_root)
ledger = pipeline.open_ledger(spec)                     # <records>/<series>/, binds run-spec.json
with pipeline.cloud_clients(spec, layout=my_layout, events=[]) as clients:
    result = pipeline.run(spec, clients, ledger, until="select")  # or from_="optimize"
```

| Entry | Contract |
| --- | --- |
| `load_run_spec(path, *, expected_sha256, repo, available=None)` -> `RunSpec` | Path inside `repo`, sha256 pin, schema: `schema_version`, `kind: foundry-hosted-agent-run`, `series`, `targets` (tenant, subscription, project resource id + endpoint, ACR name/login server, image repository, model account/resource group), `agent` (`name`, `package_dir`, `previous_version`, `previous_image`), `models` (`runtime`, `judge`, `optimizer`), `inputs` (kind -> `{path, sha256}` or list; `items`/`train`/`validation` may be `{dataset: {name, version, sha256, rows?}}`), top-level `evaluator`/`optimization`/`selection_rule` files, `bounds`, `records`, `authorization.cloud_write`, `data: inline|dataset` (default `dataset` when `foundry_ops.data` imports). Unknown fields, secret-shaped values, placeholders, YAML aliases and duplicate keys refuse (`spec_*`). |
| `load_env_manifest(environment, sha, action, *, env_dir, records, repo)` -> `(RunSpec, RunManifest, EvidenceLedger)` | The older `<env>.env` + `<env>.run.json` pair: sha-only input pins, manifest `actions` become the write authorization, data inline. |
| `Clients(az, project, openai, evals, http, token, layout, request_factory, sleep, clock)`, `cloud_clients(spec, *, layout, events=None)` | Edge dependencies. `cloud_clients` is the only SDK construction (Azure CLI credential, `retry_total=0`); tests pass fakes. `layout` is the caller's `ImageLayout` (`build_inputs`, `package_config`, `self_check`). |
| Stages `preflight`, `build`, `deploy`, `invoke`, `invoke_journeys`, `verify`, `register_evaluator`, `evaluate`, `optimize`, `select`, `promote`, `inspect`, `logs`, `teardown` | `(spec, clients, ledger, **options)`. Write stages call `spec.require(stage)` (`stage_unauthorized`). Inputs default to the spec's declared file; an explicit path must match a pin. `target=current|baseline|promoted`. `promote` overlays the selected candidate on the baseline image as a new version in the same series (`baseline_retained` refuses). `optimize` resumes polling from the retained job identity. |
| `run(spec, clients, ledger, *, until=None, from_=None, demonstration=False)`, `plan(...)` | Ordered `STAGES`; completed stages retained as `pipeline-NN-<stage>.json` and reused; unauthorized write stage, undeclared input or resume gap refuse before any side effect. Status `complete`, `pending` (unsettled eval/optimize: rerun resumes), `blocked` (`pipeline-NN-<stage>-blocked-<stamp>.json`), `baseline_retained`. |
| `package_inputs(root, *, include=None)`, `check_package_tools(tools, files)`, `source_manifest(inputs)`, `release_label(manifest)`, `stage_context(inputs, manifest, directory)` | Agent-package allowlist and secret scan; build-context identity (`src-<24>-pkg-<16>` label). |

Data mode `dataset` calls `foundry_ops.data.register_jsonl_dataset` / `readback_dataset` (imported lazily),
then `run_agent_eval(dataset=ref, item_schema, expected_count)` and
`optimization_job(train_dataset=ref, validation_dataset=ref)`; ledger keys gain `-ds`.

## Public API

All errors subclass `core.errors.FoundryOpsError(code, message)`: `RefusedError` (ValueError, before side
effects), `UnresolvedIntentError` (RefusedError), `BoundExceededError`, `VerificationError`
(ValueError), `ReadbackError` (RuntimeError, outcome unknown), `OutcomeUnknownError` (ReadbackError
and ValueError: a submitted write returned no usable identity). `code` is stable; messages name
fields, never values; an unresolved-intent message contains `unresolved`.

| Module | Entry | Contract |
| --- | --- | --- |
| `core.records` | `sha256_hex(data)`, `sha256_file(path)`, `pin(path, *, root=None)`, `encode_json(value)`, `utc_stamp(now=None)` | Canonical JSON: sorted, indent 2, `allow_nan=False`, trailing newline. |
| | `to_plain(value)` | `as_dict()` / `model_dump(mode="json")`, recursive. |
| | `sanitize(value, *, drop_keys=SENSITIVE_KEYS)`, `redact_text(text)`, `error_summary(error, *, limit=4000)` | Drop credential keys, strip URL userinfo/query/fragment, redact bearer/JWT/`sig=`-style values. `provider_detail` keeps allowlisted body fields plus sanitized, depth/length-bounded `errors`/`details`. |
| | `read_pinned(path, *, root, expected_sha256=None)`, `read_receipt(path, *, root, action, expected_sha256=None, expect=None)` | Non-symlink inside `root`; receipt must be `status == "complete"` for `action`; returns `result`. |
| | `EvidenceLedger(directory)`: `path`, `exists`, `read`, `retain(name, value, *, allow_identical=False)`, `retain_bytes(...)`, `intent(name, request, *, context=None)`, `once(name, request, action, *, context=None)`, `list(pattern="*")` | Exclusive create + fsync + read-back; overwrite refused. `intent` writes `<name>-intent.json`. `once` reuses `<name>-result.json`, refuses a dangling intent, else intent -> action -> result. `list` returns sorted regular-file names for a one-component glob; symlinks excluded. |
| `core.manifest` | `load_run_manifest(path, *, expected_sha256, action, allowed_root, pins=None, purpose="migration-development", schema_version=1, series_pattern=..., agent_pattern=..., forbidden_agents=frozenset(), allowed_fields=None)` -> `RunManifest` | Path, digest, schema, purpose, action, series, agent and dotted-field SHA-256 pins (bytes or path). `allowed_fields` refuses other top-level fields (`manifest_field`). |
| | `RunManifest.bind(ledger, name="run-manifest.json")`, `.series`, `.agent`, `.raw`, `.value`, `.sha256` | Same bytes rebind; different bytes refuse. |
| | `series_directory(base, series)` | Creates `<base>/<series>`; symlink/escape refused. |
| `core.bounds` | `poll_until(read, done, *, interval, attempts=None, seconds=None, abort=None, sleep, clock)` -> `PollResult(value, settled, attempts, seconds)` | Unsettled is returned, `abort` reason raises. |
| | `collect_bounded(items, *, max_items, seconds, convert=to_plain, clock)` | Refuses rather than truncates. |
| `core.logs` | `log_messages(chunks, max_bytes=262144, max_events=100)` | SSE `data:` JSON `message` strings; strict UTF-8 across chunks. |
| | `redact(message, *, limit=2000)`, `exception_lines(chunks, *, keywords, max_lines=100, seconds=20.0, max_bytes=1048576, max_events=1000, clock)` | Excerpt `{lines, termination, reason, coverage}`; stream errors end the excerpt. |
| `core.identifiers` | `safe_identifier(value, what)`, `validate_version_label(value, limit=50, *, what="version", code="version_label")` | Labels: 1-`limit` characters. |
| `hosting.verify` | `agent_responses_url(project_endpoint, agent_name)`, `anonymous_probe(url, *, http_client=None, timeout=30.0, payload=None)`, `require_refusal(status)` | Only 401/403 prove refusal; redirects not followed. |
| | `check_identity(observed, expected, *, what="identity")`, `check_active_version(actual, *, version, image, metadata=None, definition=None, definition_keys=DEFINITION_KEYS)` | Pure checks over `as_dict()` payloads. |
| | `is_not_found(error)`, `read_stored_response(openai_client, response_id, *, bearer_token, http_client=None, timeout=60.0)` | Raw GET; `None` only for a JSON error 404. Token scope `AI_SCOPE`. |
| `hosting.hosted` | `hosted_definition(image, *, cpu="1", memory="2Gi", protocol="responses", protocol_version="2.0.0")`, `agent_reference(agent_name, version)` | Image must be digest-pinned. |
| | `deploy_version(project, ledger, *, key, agent_name, definition, metadata, previous_version=None, previous_image=None, seconds=300.0, interval=5.0, sleep, clock)`, `wait_active(project, *, agent_name, version, ...)` | Records `deploy-<key>-{intent,created,active}.json`; resumes from created. |
| | `invoke(openai_client, ledger, *, key, agent_name, version, input, store=True, clock, stream=False, record_name=None, max_events=10000)` | `once(record_name or "invoke-<key>")`; returns `{response (plain dict), output_text, seconds}`. `stream=True` adds `stream: {events [{index, type, seconds, delta?, item?, sequence_number?, item_id?, output_index?}], types, items [{type, seconds, item}], text, first_event_seconds, first_delta_seconds}`; `response` is the terminal event's. No terminal response: `<record>-stream-partial.json` + `ReadbackError`; event bound: `BoundExceededError`. |
| | `cancel_response(openai_client, ledger, *, key, agent_name, version, input, cancel_on="response.created", attempts=10, interval=2.0, sleep, stream=True, record_prefix=None)` | Background response; stream cancels at `response.created` or `response.content_part.added`, `stream=False` cancels while queued/in progress; requires `cancelled` and no output. Prefix default `cancel-<key>`; reads legacy `-accepted-intent.json` and `-cancel-intent.json`. |
| | `reconcile_cancellation(openai_client, ledger, *, record_prefix, response_id=None, attempts=10, interval=2.0, sleep)`, `accepted_response_id(ledger, record_prefix)` | Read-only reconcile of an accepted response (cancel once if running and never requested); never creates a response. |
| | `list_sessions(project, agent_name, *, max_items=1000, seconds=60.0)`, `list_versions(..., include_drafts=None)`, `session_log_excerpt(project, *, agent_name, agent_version, session_id, ...)` | Log excerpt refuses a session of another version. |
| | `HostedTeardown(project, ledger, *, agent_name, execute=False, polls=4, interval=5.0, sleep)`: `responses(openai_client, ids, *, bearer_token, http_client=None)`, `sessions(ids=None)`, `versions(ids=None)`, `agent_readback()`, `outcomes` | Order enforced. Per step: read, intent, delete, bounded read-back; outcomes `planned`, `already-absent`, `deleted`, `still-present`, `delete-failed`. Dry run writes nothing. |
| `evaluation.evals` | `validate_dataset_version(version)`, `wait_for_run(client, *, eval_id, run_id, attempts=30, interval=10.0, seconds=600.0, ..., on_event=None)`, `collect_rows(client, *, eval_id, run_id, expected_count, max_pages=20, seconds=120.0, clock, on_event=None, partial_on_error=False)` | `PartialRowsError.partial` carries rows and cursor for retention. `on_event` gets `{operation: "poll", attempt, utc, status, request_id}` / `{operation: "page", index, rows, total, last_id}`. `partial_on_error` turns a transport failure into `PartialRowsError("row_transport")` with `partial["error"]`, chained from the cause. |
| | `check_counts(counts, *, total, errored=0, skipped=0, passed=None, failed=None)`, `check_criteria(actual, expected)`, `check_row(row, *, eval_id, run_id)`, `check_membership(rows, *, expected, key="query")`, `check_criterion(result, *, name, metric, evaluator_name=None, evaluator_version=None, kind="azure_ai_evaluator", strict_version=False)`, `target_text(row)` | `check_criterion` returns provider `passed`; `strict_version` refuses a service-added version when none was requested. `target_text` requires every emitted representation to agree. |
| | `infer_item_schema(items)`, `agent_eval_definition(name, *, testing_criteria, item_schema, include_sample_schema=True)`, `agent_run_request(eval_id, *, name, agent_name, agent_version, items=None, file_id=None, input_template="{{item.query}}", max_items=1000)` | Wire requests: custom item schema + `sample`; `azure_ai_target_completions` with inline `file_content` items (or `file_id`) against `azure_ai_agent` name/version. No `evaluation_level`. |
| | `create_eval(client, ledger, *, key, request)`, `submit_run(client, ledger, *, key, request)`, `summarize_criteria(rows, *, criteria_names)`, `run_agent_eval(client, ledger, *, key, name, agent_name, agent_version, testing_criteria, items, item_schema=None, input_template=..., attempts=60, interval=10.0, seconds=1800.0, max_pages=20, sleep, clock, on_event=None)` | `eval-<key>-{intent,result}.json`, `eval-run-<key>-...`, `eval-<key>-summary.json`. Summary per criterion `{passed, failed, errored, missing, total, pass_rate}`. Unsettled returns `settled: False`; rerun resumes polling, never resubmits. |
| `evaluation.evaluators` | `code_evaluator_definition(code_text, *, metric, data_schema, display_name, description="", categories=("quality",), metric_type="continuous", desirable_direction="increase", min_value=0, max_value=1)`, `register_code_evaluator(project, ledger, *, name, definition, key=None)`, `check_registered_evaluator(actual, *, name, version, definition)` | `project.beta.evaluators.create_version` once, then `get_version` read-back equal to the requested code definition. |
| | `local_canary(code_text, cases, *, entry="grade")`, `run_code_evaluator_canary(client, ledger, *, key, evaluator_name, evaluator_version, criterion_name, item_schema, data_mapping, cases, match_field, metric=None, ...)`, `check_canary_rows(...)` | Local canary executes caller source in-process. Native canary: one-criterion jsonl eval over `{item, expected}` cases; scores checked exactly (not `passed`); result retained before a mismatch raises. |
| `optimization.optimize` | `inline_dataset(items, *, max_items=1000)`, `optimization_job(agent_name, agent_version, *, train_items, validation_items, evaluators, optimization_model, max_candidates, eval_model=None, max_stalls=None, optimization_config=None, extra_options=None)` | Wire `AgentOptimizationJob` dict with `items` (not `dataset_items`); `evaluation_level` refused. |
| | `submit_optimization(project, ledger, *, key, job, operation_id=None)`, `wait_optimization(project, *, job_id, seconds=3600.0, interval=20.0, attempts=None, sleep, clock, on_event=None)` | `begin_create_optimization_job(polling=False)` once (`optimize-<key>-{intent,identity}.json`), then `get_optimization_job` polling; unsettled returned. |
| | `list_candidates(job, *, require_success=True, require_generated=True)`, `resolve_candidate_config(project, *, endpoint, job_id, candidate_id, api_version="2025-11-15-preview", allowed_fields=CONFIG_FIELDS, max_bytes=1000000, ..., request_factory=None, validate=None)`, `candidate_configs(project, listing, *, endpoint, candidate_ids=None, **options)` | Plain dicts `{candidate_id, name, observation_index, is_baseline, agent_version, avg_score, avg_tokens, eval_id, eval_run_id, mutations, generation: None, parent_id: None, native}`. Config via one bounded `project.send_request` GET; unapproved fields refused. |
| `hosting.traces` | `tool_calls(response=None, *, events=None, stream_items=None, envelope_key=None, metadata_key=None, metadata_prefix=None, expected=(), max_calls=1000)`, `output_text(response)` | One record per `call_id`: `{call_id, name, arguments, output, status, error_code, started_at, ended_at, duration_ms, sources}` (None when unobserved). Sources: native `function_call`/`function_call_output` (and custom/MCP) items, `invoke(stream=True)` items (timing), llm_interface `tool.*` events, envelope/metadata list, or `metadata[<prefix><id>]` records. Missing expected tool, name conflict, duplicate item, malformed declared source: `VerificationError`. |
| `build.image` | `parse_queued_build_id(stderr)`, `az_json(arguments, *, timeout=180.0, events=None, runner=subprocess.run, clock)` | Diagnostics redacted before retention. |
| | `submit_build(az, ledger, *, key, subscription, registry, image, context_dir, dockerfile="Dockerfile", platform="linux/amd64", timeout=900, context=None)`, `wait_build(az, *, subscription, registry, run_id, seconds=900.0, interval=10.0, ...)`, `resolve_image(az, run, *, subscription, registry, registry_host, repository, tag)` | `az` is any `list[str] -> JSON` callable. `context` adds caller fields to the intent (cannot replace `request`). Unknown outcome: `OutcomeUnknownError`. Returns `host/repo@digest`. |

## Deliberately Not Wrapped

- Client construction, credentials, retry policy, timeouts: `AIProjectClient(..., retry_total=0)`,
  `AzureCliCredential`, `get_openai_client(...)` stay with the caller.
- SDK paging, models and serializers: pass SDK pagers in; `Response.output_text` is read, not rebuilt.
- Source-manifest hashing and tar packaging: testbeds hash differently and the hash is the image
  tag, so unifying would change identities.
- Datasets, pending upload and storage SAS/URL validation: one consumer each or preview-only.
- Candidate lineage and application scoring: `optimization` keeps generation/parent
  null and treats `avg_score` as the native composite only; `pipeline.select` applies only the frozen
  `strictly_above_baseline` rule.
- Evaluation/dataset/evaluator deletion, `project.agents.delete`, role grants and CLI/receipt
  assembly (the template's `deploy/cli.py`). Preflight account checks now live in `pipeline.preflight`.
- Application oracles (nonce/tool envelopes, label vocabularies) and `sample` requirements.

## Known Traps Encoded

| Trap | Where |
| --- | --- |
| Dataset registration rejects versions over 50 characters although pending upload accepted 71. | `evaluation.validate_dataset_version` |
| Any Responses retrieve/delete through an agent-scoped client re-creates deleted sessions, which then block version delete with 409. | `HostedTeardown` order `responses -> sessions -> versions` |
| openai 3.13 maps the hosted responses endpoint 404 to `APIConnectionError`. | `read_stored_response` raw GET; `is_not_found` excludes connection errors |
| A 404 without a service error body (routing, wrong base URL) is not absence. | `read_stored_response` raises `ReadbackError` |
| Session delete can return 400/409 while running. | `HostedTeardown.sessions` stops then deletes |
| Session listings repeat deleted/re-created ids. | teardown deduplicates ids; read-back uses `get_session` |
| Deleting an agent's last version removes the agent. | `HostedTeardown.agent_readback` |
| Deletes and hosted readiness are eventually consistent. | `poll_until` bounded read-back |
| `az acr build --no-wait` may print the run id only on stderr. | `build.parse_queued_build_id` |
| Anonymous 404, login redirect or any success is not refusal. | `hosting.require_refusal` |
| A timeout, transport loss or unknown create result is not permission to replay. | `EvidenceLedger.intent` / `once`, `UnresolvedIntentError` |
| Optimization wire JSON uses `items`; `evaluation_level="turn"` returns 400; the create `Operation-Location` 404s publicly. | `optimization.optimization_job`, `wait_optimization` polls `get_optimization_job` |
| Code evaluator registration omits a threshold, so provider `passed` is not a canary signal. | `evaluation.check_canary_rows` checks scores |

Not encoded, caller-owned: `evals.runs.delete` read-back stays retrievable minutes after 200;
`evals.delete` returns `deleted=false` (asynchronous); Container Apps/ingress header behaviour.

## Live Status

Live-proven 2026-09-24 through [template deploy.sh](../../template_apps/foundry_hosted_agent/deploy/README.md),
series `pkg-e2e-baseline-v1`
([receipts](../../agentcraft_projects/foundry-agent-package-e2e-20260924/records/live/pkg-e2e-baseline-v1/)):

| Subpackage | Live-proven for | Offline only |
| --- | --- | --- |
| `core` (`records`, `manifest`, `bounds`) | ledger intent/result, pinned run manifest, bounded polls | |
| `build` | `submit_build`, `wait_build`, `resolve_image` (one ACR run) | |
| `hosting.hosted` | `hosted_definition`, `deploy_version`, `invoke` non-streaming and `stream=True` | `cancel_response`, `reconcile_cancellation`, `session_log_excerpt`, `HostedTeardown` |
| `hosting.verify` | `check_active_version`, `read_stored_response`, `anonymous_probe` (401/403) | |
| `evaluation.evals` | `run_agent_eval` (create, run, poll, rows, summary), `validate_dataset_version` as label check | `target_text` (rows carried `function_call` blocks; recompute was project-side), dataset upload |
| `evaluation.evaluators` | `register_code_evaluator` read-back, `run_code_evaluator_canary` | |
| `optimization` | `optimization_job` (inline and dataset reference), `submit_optimization`, `wait_optimization`, `list_candidates`, `resolve_candidate_config`, `candidate_configs` (jobs `opt_640e1321…`, `opt_0371395b…`) | |
| `data` | `register_jsonl_dataset`, `readback_dataset`, `list_auto_datasets`, eval by `file_id` ([pkg-e2e-datasets-v1](../../agentcraft_projects/foundry-agent-package-e2e-20260924/records/live/pkg-e2e-datasets-v1/)) | |
| `pipeline` | | all (`run`, `load_run_spec`, CLI `run --spec`); stages reuse live-proven calls above |
| `hosting.traces` | `tool_calls(metadata_prefix="tool_call.")` on stored responses, 1-2 calls per turn | `events`/`envelope_key` sources |
| `core.logs` | | all |

Consumers: the three Foundry testbeds (deploy side),
[template_apps/foundry_hosted_agent](../../template_apps/foundry_hosted_agent/README.md), and through it the
[package E2E project](../../agentcraft_projects/foundry-agent-package-e2e-20260924/). Procedure:
[protocol-foundry-agent-lifecycle](../../.github/protocols/protocol-foundry-agent-lifecycle/SKILL.md).

## Checks

```bash
PYTHONPATH=libraries/foundry-ops/src python3 -B -m unittest discover -s libraries/foundry-ops/tests -v
python3 -B -m unittest discover -s libraries/foundry-ops/examples/hosted_agent_e2e
```

Covers overwrite, digest, action, 50-character, 404, teardown-order and log-bound refusals, a
positive and a refusing case per keyword option (`test_options.py`) and per native step
(`test_native.py`), run-spec schema, authorization, resume and dataset-contract refusals
(`test_pipeline.py`), the full `pipeline.run` sequence plus resume against fakes (example smoke), and
imports every module in a subprocess with `azure`, `openai` and `httpx` blocked. `pipeline` is offline-only:
no stage has run live through `pipeline.run` yet; the template's per-action path it replaced was live-proven.

## Limits

- Fakes follow `azure-ai-projects` 2.6.1, `openai` 3.13.0 and `httpx` 0.28.1 signatures observed
  locally; live coverage is only what [Live status](#live-status) lists.
- `check_counts` assumes `passed + failed + errored + skipped == total`; observed only with
  `errored = skipped = 0`.
- Session absence after `delete_session` is read through `get_session` 404; the service behaviour
  of that read after deletion is unknown.
- Dataset upload remains in its testbed; `evaluate` sends inline items.
