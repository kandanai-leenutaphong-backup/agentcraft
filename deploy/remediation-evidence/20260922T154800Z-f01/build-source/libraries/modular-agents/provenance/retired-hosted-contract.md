# Modular Agents Contract

## 1. Ownership And Dependency Direction

One immediate plugin skill entry point: `modular-agents/SKILL.md`.

```text
agentconfig -> PyYAML
toolshape -> standard library
foundryagent -> optional MAF and Azure Identity
hostedagents.definition -> agentconfig + toolshape + Pydantic
hostedagents.engine -> definition + RuntimePolicy + injected model
hostedagents.application -> engine + HTTP + model adapter
hostedagents.packaging -> definition + explicit package source directories
hostedagents.deployment -> client + grants + verified bundle + operator policy
scripts/agent.py -> composition edge, files, environment, operator credential
```

The four packages install from one source distribution. No import or filesystem
read reaches another skill or the origin checkout. `foundryagent` is optional
for hosted execution and is not copied into hosted artifacts. The hosting
adapter imports no canvas `agentconfig.document` or `agentconfig.dataplane`.

The preserved modules retain their contracts:
[configuration](modules/agent-config-build/CONTRACT.md),
[tool shape](modules/purpose-built-tools/CONTRACT.md),
[MAF client runtime](modules/foundry-agent-runtime/CONTRACT.md).

## 2. Definition And Tool Surface

`hostedagents` exports `Definition`, `DefinitionError`, `ToolRegistry` and
`load_definition`. Supported module APIs are named below; private underscore
members are not extension surfaces.

`load_definition(control_dir, *, agent_id=None, allowed_prefixes=()) -> Definition`
serializes the preserved process-global loader, clears stale cache/default/import
policy, resolves the whole roster and selects one agent. An omitted allowlist
denies every configured tool import, even after a prior granted load.

`Definition.from_spec(spec)` accepts `agentconfig.AgentSpec`. `spec` preserves
the agent id, name, description, model, complete instructions, ordered callables,
surface and extra metadata. Hosting requires an explicit non-empty model name.
Extra metadata is not an authorization grant and is not copied into runtime
policy. Only the selected resolved definition travels in its bundle.

`ToolRegistry(functions, *, max_result_bytes=60000)` exposes `names`, `references`,
`schemas`, and `await invoke(name, arguments)`. `schemas` is a detached JSON copy
in OpenAI function-tool shape. Callables must:

- Be top-level Python functions, synchronous or asynchronous, importable by
  `module:function`; no closures, bound methods or platform tool objects.
- Have concrete, resolvable parameter annotations, no `Any`, positional-only or
  variadic parameters, and a non-empty description.
- Have unique valid names. A `ToolSpec` name, parameters, required flags and
  defaults must agree with the Python signature.
- Not accept credential/password/token/API-key/connection-string parameters.
  This is a named-field guard, not a full semantic credential audit.
- Not carry a marker requiring interactive approval. The headless adapter
  refuses such a definition rather than discarding its approval requirement.

Pydantic strict models reject unknown keys and wrong types before execution.
Domain validators remain in `toolshape`. Sync functions run in a worker thread;
context-local turn ledgers propagate. Result strings are JSON-decoded when
possible, other values wrapped in an object. Oversized/non-JSON-finite results
become an error envelope; exceptions disclose their class, not their message.
The original `toolshape` exception logger is unchanged: do not put credentials
into backend exception text or configure a log sink that exposes sensitive data.

`ToolRegistry` is the low-level callable adapter, not an authorization boundary.
Use `AgentRuntime` for effectful externally reachable operations.

## 3. Runtime Policy And Target

`hostedagents.policy.RuntimePolicy` rejects unknown keys and is immutable.

| Field | Default | Accepted bound |
| --- | --- | --- |
| `allowed_tools` | `[]` | unique exact names present in this definition |
| `allow_model` | `false` | JSON boolean, not a truthy string |
| `max_message_bytes` | 16000 | 1..100000 |
| `max_output_tokens` | 2000 | 1..16000 |
| `max_tool_rounds` | 4 | 1..8 |
| `max_tool_calls` | 16 | 1..64 per turn |
| `max_result_bytes` | 60000 | 256..1000000 per tool/model response |
| `turn_timeout_seconds` | 120 | 1..240 |
| `max_concurrent_turns` | 4 | 1..32 |

A complete turn retains at most 1000000 result bytes. Limits bound execution;
they are not billing quotas. Granting a tool permits its implementation's effects,
so review its backend and timeout behavior before adding its name.

`RuntimeTarget.model_endpoint` is empty by default. Model-enabled bundles require
an explicit HTTPS Azure public-cloud account endpoint ending `/openai/v1`; user
information, query strings, fragments and non-443 ports are refused. Sovereign
cloud/private endpoint aliases need a reviewed extension, not disabling validation.
The model deployment comes from the agent definition.

## 4. Local And Hosted Execution

`hostedagents.engine.AgentRuntime(definition, policy, *, model=None, artifact_id=...)`
owns `status`, async `call`, `prepare_chat`, async `chat_events`, `result`, and
`abort`. Model execution uses injected `ChatModel.complete(model, messages, tools,
max_tokens)`. `hostedagents.model.OpenAIModel` implements it with the official
OpenAI SDK and a credential passed at the edge; SDK retries are disabled because
the bounded runtime owns the call budget.

Every tool call generated by the model crosses the same validation and allowlist
as a direct call. The model receives only granted tool schemas. The configured
system prompt is sent unchanged. Calls are sequential; no hidden fallback model
or parallel tool permission is added. One bounded chat message is one turn;
prior conversation is not supplied automatically.

`chat_events` emits SSE-compatible `(event, payload)` tuples. Event vocabulary:
`token`, `tool_call_start`, `tool_call_delta`, `tool_call_end`, `tool_result`,
`citation`, `metadata`, `rate_limited`, `keepalive`, `done`, `error`, `aborted`.
Only the used subset is emitted; there is no fabricated citation or rate-limit
event. Tool correlation uses ids. Exactly one terminal event ends a consumed
turn. Model response text arrives as a completed-response `token`, not native
token-by-token provider streaming. Keepalives are emitted while work is pending.

Turn ids must be unique within retained results. The last 128 turns are kept in
memory; completed entries are evicted first. `result` and `abort` return 404 for
unknown or differently owned turns. This is not a shared durable job store.
Cancellation stops async model work; a running synchronous backend thread may
continue until its own timeout. Do not promise rollback of tool side effects.

## 5. HTTP And Caller Authentication

`hostedagents.application.create_app(runtime, *, authorize)` adapts the service.
`authorize(request) -> principal` is injected by the host, not taken from a JSON
field or caller-controlled identity header. Empty principal is 401.

- `GET /readiness`: public `ready`, with no identity/configuration data.
- `POST /invocations`: authenticated JSON, bounded to 128000 bytes.
- Unknown paths are 401 before route lookup for anonymous callers.
- Responses use `Cache-Control: no-store, private`.

Invocation shape rejects unknown keys. Fields: `op`, `tool`, `arguments`,
`message`, `turn_id`, `stream`. Operations:

| `op` | Result | Effect permission |
| --- | --- | --- |
| `health` | runtime identity, model, tool names, policy, active turn count | authenticated caller |
| `tools` | full tool schemas | authenticated caller |
| `call` | tool result/refusal envelope | exact `allowed_tools` membership |
| `chat` | SSE by default; `stream:false` returns completed result | `allow_model`; each tool separately granted |
| `result` | retained result or running status | originating principal |
| `abort` | cancellation request outcome | originating principal |

Malformed shape is 400; missing authentication 401; missing grant 403; unknown or
foreign turn 404; duplicate turn id 409; body over limit 413; concurrency bound
429; direct operation timeout 504. Tool argument refusal remains data, not a
transport crash. Generic backend failure text is not returned.

`serve(root, environment=...)` is the configuration edge. An extracted bundle
uses `PORT` (default 8088). Local mode requires a non-empty
`MODULAR_AGENTS_LOCAL_TOKEN` of at least 32 characters, uses constant-time bearer
comparison and binds `127.0.0.1`. Supply the token directly through the operator's
environment; never through a prompt, committed file or CLI argument.

Hosted mode requires both platform-supplied `FOUNDRY_AGENT_SESSION_ID` and
`FOUNDRY_AGENT_VERSION`, binds `0.0.0.0`, and relies on Foundry's authenticated
ingress. These variables are deployment context, not a general authentication
mechanism. Do not set them on a public standalone server or expose the container
around Foundry's ingress. Hosted model credentials use `ManagedIdentityCredential`;
local model credentials use the operator's `AzureCliCredential`.

The platform session is the hosted authorization unit. This does not prove
cross-user record isolation for an external multi-user application. Such an app
must authenticate users and derive separate session keys in its own relay.

## 6. Bundle Format And Integrity

`hostedagents.packaging.build_bundle(definition, *, package_sources, output_dir,
policy, target, requirements, cpu, memory) -> Bundle` packages only explicit
source. `load_bundle(directory)` revalidates artifacts before upload.

`package_sources` maps top-level Python package names to their actual imported
source directory. Every tool package is required; additional private dependencies
must be listed too. Dependency discovery does not import or read sibling skills.
Runtime package-name conflicts, symlinks, unsupported binary assets, unpinned
requirements/URLs/local dependency paths and credential-shaped source are refused.
The credential scan is a backstop, not certification that arbitrary source is safe.

Flat zip contents:

```text
main.py
agent_config.json
tool_schemas.json
runtime_manifest.json
requirements.txt
agentconfig/
toolshape/
hostedagents/
<explicit tool and dependency packages>/
```

No wrapper folder, virtual environment, caches, tests, private keys, client grant
plan, deployment receipt or client metadata. Uncompressed source is bounded to
128 MiB and the zip to 64 MiB. Metadata selects Python 3.13, `remote_build`, the
`python main.py` entry point and invocations protocol `2.0.0`.

On disk, a content-addressed artifact directory contains `agent.zip`,
`metadata.json`, and `manifest.json`. `Bundle.sha256` identifies the zip;
`Bundle.artifact_id` identifies zip plus metadata; `Bundle.runtime_sha256`
identifies the runtime file-hash manifest. Startup verifies every listed runtime
file and recomputes schemas before readiness. Health returns `runtime_sha256`
as `artifact_id`. These hashes detect drift, not malicious replacement of both
source and manifest; trust reviewed source and the authorized distribution path.

Repeated identical builds reuse the artifact. Existing modified artifacts are
refused, never overwritten. Keep runtime requirements aligned with `uv.lock`.
The format is not a guarantee that an arbitrary package has declared every
import; run the extracted artifact under its own locked dependencies before release.

## 7. Operator Deployment

`hostedagents.client.FoundryClient(endpoint, credential, transport=None)` owns
`get_agent`, `version_status`, `upload`, `invoke`, `warm`, and `delete_agent`.
Credentials are caller-owned. No token enters a receipt, zip, log or response.
Redirects are refused. Error messages carry operation/status, not response bodies.

Foundry API contract preserved from source:

- Project endpoint: `https://<account>.services.ai.azure.com/api/projects/<project>`.
- Audience: `https://ai.azure.com/.default`; API version `v1`.
- New agent: multipart `POST /agents`, `x-ms-agent-name` and
  `x-ms-code-zip-sha256`; update: `POST /agents/{name}` without the name header.
- Multipart parts: `metadata` JSON and `code` zip.
- Wait: `GET /agents/{name}/versions/{version}` reaches `active`, not merely 201.
- Invoke: `POST /agents/{name}/endpoint/protocols/invocations` with
  `agent_session_id` in the query, never a header or body field.
- Delete: `DELETE /agents/{name}?force=true`, followed by read-back absent.

`session_key(principal, agent, purpose=...)` separates consumer and maintenance
namespaces. Names are routing identities, not credentials. Warm retries bounded
cold-start/transient status codes, never 401/403 indefinitely.

`OperatorPolicy` rejects unknown fields. It holds exact `allowed_agents`,
`allow_deploy`, `allow_update`, `allow_invoke`, `allow_delete`,
`allow_role_changes` (all default false) and an explicit `grants` list.
`Deployer` applies this policy before mutation. Its `hosted_process` edge flag
refuses deploy/update/delete under a hosted workload; the CLI derives it from
platform environment. Programmatic callers own truthful context and serialization.

Receipts bind endpoint, agent name, operator, artifact digests, live version,
instance principal, state and grant records. CLI operations use an exclusive
file lock. States: `uploading`, `waiting`, `granting`, `warming`, `active`,
`failed`, `deleted`. Writes are atomic and owner-readable/writable.

Existing unreceipted agents, changed live versions/identities and ambiguous
interrupted uploads are refused. A completed upload can resume verification;
an upload that may have happened before its version was recorded requires
explicit reconciliation, not another POST. Grant intent is recorded before PUT,
so failed read-back retains cleanup knowledge across restart.

`verify` proves exact live version, runtime source identity, policy/model when
the artifact is supplied, and every recorded grant at exact scope. It is not an
inference/data-plane authorization probe. `active` means runtime verified and
healthy; required live model/data probes remain separate acceptance.

## 8. Grants, Teardown And Exclusions

`hostedagents.grants.Grant`, `GrantBroker`, `GrantError`, `ROLES`, and
`assignment_matches` define the supported ARM surface:

| Role | Minimum supported scope |
| --- | --- |
| Cognitive Services OpenAI User | exact Cognitive Services/Foundry account |
| Search Index Data Reader | exact Search service |
| Storage Blob Data Reader | exact Blob container |

Role names outside this closed list fail validation. Grants use the hosted
instance principal, never the blueprint principal, and `principalType` is
`ServicePrincipal`. Assignment ids are deterministic. Positive read-back must
match principal, role and exact scope; inherited parent grants do not pass.

Teardown revokes only receipt-owned created assignments and reads them absent
before deleting the exact recorded agent/version. Pre-existing grants are
preserved. No subscription sweep or deletion of external assignments occurs.
If revocation is not yet visible, teardown stops while the identity still exists.

Cosmos SQL role assignments, Kusto principal assignments, SQL table users,
Entra tenant provisioning, account/project/model creation, ACR and Container
Apps are not implemented by this adapter. Do not substitute broad Contributor
roles. Adding a provider must include exact-scope positive/negative tests,
read-back, durable recovery and teardown semantics before its grant is accepted.