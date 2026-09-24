# Foundry Ops

`agentcraft-foundry-ops` owns Foundry lifecycle glue repeated across the hosted-agent,
evaluation and optimization testbeds: intent-before-mutation evidence, pinned run manifests,
hosted-version deploy/invoke/cancel/teardown, stored-response read-back, bounded session logs,
ACR build identity and evaluation read-back checks.

It is thin over official clients. The caller constructs `AIProjectClient`
(`azure-ai-projects`), agent-scoped OpenAI clients (`project.get_openai_client(agent_name=...)`),
credentials and targets at the edge and passes them in. No module reads the environment,
acquires a credential or imports Azure/OpenAI/httpx at import time. Base install has no
dependencies; `[http]` adds `httpx` for `anonymous_probe` and `read_stored_response` when no
`http_client` is passed. Offline-tested with fakes only; no live acceptance yet.

```python
from foundry_ops.hosted import deploy_version, hosted_definition, invoke
from foundry_ops.manifest import load_run_manifest, series_directory
from foundry_ops.records import EvidenceLedger

run = load_run_manifest(path, expected_sha256=sha, action="deploy", allowed_root=deploy / "env",
                        pins={"target_sha256": deploy / "env/target.json", "constitution_sha256": constitution})
ledger = EvidenceLedger(series_directory(deploy / "records", run.series))
run.bind(ledger)
deployed = deploy_version(project, ledger, key=source_sha, agent_name=run.agent,
                          definition=hosted_definition(image), metadata={"source_sha256": source_sha})
reply = invoke(openai_for_agent, ledger, key="n1", agent_name=run.agent, version=deployed["version"], input="q")
```

## Public API

All errors subclass `errors.FoundryOpsError(code, message)`: `RefusedError` (ValueError, before side
effects), `UnresolvedIntentError` (RefusedError), `BoundExceededError`, `VerificationError`
(ValueError), `ReadbackError` (RuntimeError, outcome unknown). `code` is stable; messages name
fields, never values.

| Module | Entry | Contract |
| --- | --- | --- |
| `records` | `sha256_hex(data)`, `sha256_file(path)`, `pin(path, *, root=None)`, `encode_json(value)`, `utc_stamp(now=None)` | Canonical JSON: sorted, indent 2, `allow_nan=False`, trailing newline. |
| | `to_plain(value)` | `as_dict()` / `model_dump(mode="json")`, recursive. |
| | `sanitize(value, *, drop_keys=SENSITIVE_KEYS)`, `redact_text(text)`, `error_summary(error, *, limit=4000)` | Drop credential keys, strip URL userinfo/query/fragment, redact bearer/JWT/`sig=`-style values. |
| | `read_pinned(path, *, root, expected_sha256=None)`, `read_receipt(path, *, root, action, expected_sha256=None, expect=None)` | Non-symlink inside `root`; receipt must be `status == "complete"` for `action`; returns `result`. |
| | `EvidenceLedger(directory)`: `path`, `exists`, `read`, `retain(name, value, *, allow_identical=False)`, `retain_bytes(...)`, `intent(name, request, *, context=None)`, `once(name, request, action, *, context=None)` | Exclusive create + fsync + read-back; overwrite refused. `intent` writes `<name>-intent.json`. `once` reuses `<name>-result.json`, refuses a dangling intent, else intent -> action -> result. |
| `manifest` | `load_run_manifest(path, *, expected_sha256, action, allowed_root, pins=None, purpose="migration-development", schema_version=1, series_pattern=..., agent_pattern=..., forbidden_agents=frozenset())` -> `RunManifest` | Path, digest, schema, purpose, action, series, agent and dotted-field SHA-256 pins (bytes or path). |
| | `RunManifest.bind(ledger, name="run-manifest.json")`, `.series`, `.agent`, `.raw`, `.value`, `.sha256` | Same bytes rebind; different bytes refuse. |
| | `series_directory(base, series)` | Creates `<base>/<series>`; symlink/escape refused. |
| `bounds` | `poll_until(read, done, *, interval, attempts=None, seconds=None, abort=None, sleep, clock)` -> `PollResult(value, settled, attempts, seconds)` | Unsettled is returned, `abort` reason raises. |
| | `collect_bounded(items, *, max_items, seconds, convert=to_plain, clock)` | Refuses rather than truncates. |
| `logs` | `log_messages(chunks, max_bytes=262144, max_events=100)` | SSE `data:` JSON `message` strings; strict UTF-8 across chunks. |
| | `redact(message, *, limit=2000)`, `exception_lines(chunks, *, keywords, max_lines=100, seconds=20.0, max_bytes=1048576, max_events=1000, clock)` | Excerpt `{lines, termination, reason, coverage}`; stream errors end the excerpt. |
| `verify` | `agent_responses_url(project_endpoint, agent_name)`, `anonymous_probe(url, *, http_client=None, timeout=30.0, payload=None)`, `require_refusal(status)` | Only 401/403 prove refusal; redirects not followed. |
| | `check_identity(observed, expected, *, what="identity")`, `check_active_version(actual, *, version, image, metadata=None, definition=None, definition_keys=DEFINITION_KEYS)` | Pure checks over `as_dict()` payloads. |
| | `is_not_found(error)`, `read_stored_response(openai_client, response_id, *, bearer_token, http_client=None, timeout=60.0)`, `safe_identifier(value, what)` | Raw GET; `None` only for a JSON error 404. Token scope `AI_SCOPE`. |
| `hosted` | `hosted_definition(image, *, cpu="1", memory="2Gi", protocol="responses", protocol_version="2.0.0")`, `agent_reference(agent_name, version)` | Image must be digest-pinned. |
| | `deploy_version(project, ledger, *, key, agent_name, definition, metadata, previous_version=None, previous_image=None, seconds=300.0, interval=5.0, sleep, clock)`, `wait_active(project, *, agent_name, version, ...)` | Records `deploy-<key>-{intent,created,active}.json`; resumes from created. |
| | `invoke(openai_client, ledger, *, key, agent_name, version, input, store=True, clock)` | `once("invoke-<key>")`; returns `{response, output_text, seconds}`. |
| | `cancel_response(openai_client, ledger, *, key, agent_name, version, input, cancel_on="response.created", attempts=10, interval=2.0, sleep)` | Background stream; cancel at `response.created` or `response.content_part.added`; requires `cancelled` and no output. |
| | `list_sessions(project, agent_name, *, max_items=1000, seconds=60.0)`, `list_versions(..., include_drafts=None)`, `session_log_excerpt(project, *, agent_name, agent_version, session_id, ...)` | Log excerpt refuses a session of another version. |
| | `HostedTeardown(project, ledger, *, agent_name, execute=False, polls=4, interval=5.0, sleep)`: `responses(openai_client, ids, *, bearer_token, http_client=None)`, `sessions(ids=None)`, `versions(ids=None)`, `agent_readback()`, `outcomes` | Order enforced. Per step: read, intent, delete, bounded read-back; outcomes `planned`, `already-absent`, `deleted`, `still-present`, `delete-failed`. Dry run writes nothing. |
| `evals` | `validate_dataset_version(version)`, `wait_for_run(client, *, eval_id, run_id, attempts=30, interval=10.0, seconds=600.0, ...)`, `collect_rows(client, *, eval_id, run_id, expected_count, max_pages=20, seconds=120.0, clock)` | `PartialRowsError.partial` carries rows and cursor for retention. |
| | `check_counts(counts, *, total, errored=0, skipped=0, passed=None, failed=None)`, `check_criteria(actual, expected)`, `check_row(row, *, eval_id, run_id)`, `check_membership(rows, *, expected, key="query")`, `check_criterion(result, *, name, metric, evaluator_name=None, evaluator_version=None, kind="azure_ai_evaluator")`, `target_text(row)` | `check_criterion` returns provider `passed`; `target_text` requires every emitted representation to agree. |
| `build` | `parse_queued_build_id(stderr)`, `az_json(arguments, *, timeout=180.0, events=None, runner=subprocess.run, clock)` | Diagnostics redacted before retention. |
| | `submit_build(az, ledger, *, key, subscription, registry, image, context_dir, dockerfile="Dockerfile", platform="linux/amd64", timeout=900)`, `wait_build(az, *, subscription, registry, run_id, seconds=900.0, interval=10.0, ...)`, `resolve_image(az, run, *, subscription, registry, registry_host, repository, tag)` | `az` is any `list[str] -> JSON` callable. Returns `host/repo@digest`. |

## Deliberately Not Wrapped

- Client construction, credentials, retry policy, timeouts: `AIProjectClient(..., retry_total=0)`,
  `AzureCliCredential`, `get_openai_client(...)` stay with the caller.
- SDK paging, models and serializers: pass SDK pagers in; `Response.output_text` is read, not rebuilt.
- Source-manifest hashing and tar packaging: testbeds hash differently and the hash is the image
  tag, so unifying would change identities.
- Datasets, pending upload, storage SAS/URL validation, optimization jobs, candidate config,
  custom evaluator registration and canaries: one consumer each or preview-only.
- Evaluation/dataset/evaluator deletion, `project.agents.delete`, role grants, preflight account
  checks and receipt/CLI assembly.
- Application oracles (nonce/tool envelopes, label vocabularies) and `sample` requirements.

## Known Traps Encoded

| Trap | Where |
| --- | --- |
| Dataset registration rejects versions over 50 characters although pending upload accepted 71. | `evals.validate_dataset_version` |
| Any Responses retrieve/delete through an agent-scoped client re-creates deleted sessions, which then block version delete with 409. | `HostedTeardown` order `responses -> sessions -> versions` |
| openai 3.13 maps the hosted responses endpoint 404 to `APIConnectionError`. | `read_stored_response` raw GET; `is_not_found` excludes connection errors |
| A 404 without a service error body (routing, wrong base URL) is not absence. | `read_stored_response` raises `ReadbackError` |
| Session delete can return 400/409 while running. | `HostedTeardown.sessions` stops then deletes |
| Session listings repeat deleted/re-created ids. | teardown deduplicates ids; read-back uses `get_session` |
| Deleting an agent's last version removes the agent. | `HostedTeardown.agent_readback` |
| Deletes and hosted readiness are eventually consistent. | `poll_until` bounded read-back |
| `az acr build --no-wait` may print the run id only on stderr. | `build.parse_queued_build_id` |
| Anonymous 404, login redirect or any success is not refusal. | `verify.require_refusal` |
| A timeout, transport loss or unknown create result is not permission to replay. | `EvidenceLedger.intent` / `once`, `UnresolvedIntentError` |

Not encoded, caller-owned: `evals.runs.delete` read-back stays retrievable minutes after 200;
`evals.delete` returns `deleted=false` (asynchronous); Container Apps/ingress header behaviour.

## Checks

```bash
PYTHONPATH=libraries/foundry-ops/src python3 -B -m unittest discover -s libraries/foundry-ops/tests -v
```

Covers overwrite, digest, action, 50-character, 404, teardown-order and log-bound refusals, and
imports every module in a subprocess with `azure`, `openai` and `httpx` blocked.

## Limits

- Fakes follow `azure-ai-projects` 2.6.1, `openai` 3.13.0 and `httpx` 0.28.1 signatures observed
  locally; no live Foundry call has exercised this package.
- `check_counts` assumes `passed + failed + errored + skipped == total`; observed only with
  `errored = skipped = 0`.
- Session absence after `delete_session` is read through `get_session` 404; the service behaviour
  of that read after deletion is unknown.
- Consumers: the three Foundry testbeds (deploy side) and
  `template_apps/foundry_hosted_agent`. Single-consumer steps (optimizer, dataset upload,
  non-streaming cancel) remain in their testbed.
