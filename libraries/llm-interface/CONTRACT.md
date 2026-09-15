# Implemented Contract

**`llm-interface` 0.1.0a1, Python 3.11+.** This is the runtime authority; the original
[design](DESIGN.md) includes future or optional capabilities not delivered by this alpha.
Import from `llm_interface`, not its internal provider/guard modules.

## Public API

Exports: `connect`, `Connection`, `ConnectionConfig`, `Policy`, `Limits`, `Capabilities`,
`LlmError`, `bind_agent`, `AgentBinding`, `Session`, `RunEvent`, `ToolCall`,
`report_progress`, `from_clients`; framework `Message`, `Content`, `ChatOptions`,
`ChatResponse`, `ChatResponseUpdate`, `GeneratedEmbeddings`, `AgentResponse`, `tool`.

### Construction

`connect(endpoint, model, *, credential, allow_model_calls=False, allowed_tools=(),
limits=None, policy=None, provider="auto", embedding_model=None, allowed_hosts=None,
credential_scope=None, capabilities=None, transport=None)` returns a `Connection`.
Instead of endpoint/model fields, pass a complete `ConnectionConfig` as the first argument.
Do not combine `Policy` with individual grant/limit keywords.

Construction, import and `describe()` acquire no token and perform no model request.
Native clients are constructed on first use. Credentials are explicit and borrowed.
Provider SDK extras are loaded lazily; missing dependencies produce an actionable error.

| Profile | Selection / Native Owner | Implemented Operations |
| --- | --- | --- |
| `foundry` | Auto for `/api/projects/<project>`; real `AIProjectClient` and `FoundryChatClient` | Project OpenAI-v1 responses, streaming/agents and text embeddings through `OpenAIEmbeddingClient` when configured |
| `azure_openai` | Auto for account origins; `OpenAIChatClient` and Azure Identity token provider | Responses, agents, structured output, text embeddings |
| `azure_completions` | Explicit; `OpenAIChatCompletionClient` | Chat Completions through the same caller/agent methods; text embeddings |
| `openai` / `openai_completions` | Explicit; caller supplies native key/token callable and supported base URL | Same implemented protocol surfaces; no Azure-auth fallback |
| Injected provider | `from_clients()` with a caller-owned factory | Common guards/events; native destination/retry/evidence enforcement belongs to adapter author |

Azure profiles require `get_token` credentials or token callables; Foundry project
construction requires a `get_token` credential. Both synchronous and asynchronous
Azure Identity credentials are supported through the matching native token provider.
No raw bearer token is cached by this library. Default audiences are `https://ai.azure.com/.default`
for projects and `https://cognitiveservices.azure.com/.default` for Azure OpenAI accounts.
Sovereign/private-cloud correctness is not inferred from a syntactically valid custom scope.

Endpoints are trusted operator configuration: HTTPS, no user-info/query/fragment, default
HTTPS port, bounded supported path shape and exact allowed host. If `allowed_hosts` is
omitted, the explicitly supplied host is pinned. That does not make a request-supplied
endpoint safe. Redirects and native calls outside the bound inference routes refuse.
The built-in native transport disables environment proxies and hidden SDK retries.

Azure model/deployment names and optional embedding deployments are explicit. Different
embedding accounts use separate connections. Neither a model family name nor an installed
extra proves a deployment exists or that the credential has permission.

### Policy And Capabilities

`Policy(allow_model_calls=False, allowed_tools=frozenset(), limits=Limits())` snapshots
tool names. All inference is denied by default; tools additionally need exact name grants.
The caller's `connect(..., allow_model_calls=True)` is a host/operator decision, not a
model-supplied setting or an Azure role grant.

`Capabilities(chat=True, streaming=True, tools=True, structured_output=True,
embeddings=True, reasoning=False)` declares the chosen profile. The connection default
disables embeddings unless an embedding deployment is configured. Capabilities describe
the adapter/operator's expected features, not live model evidence. A false required
capability refuses before dispatch; a provider may still reject an unsupported deployment.

`agent(..., required_capabilities=(...))` checks named requirements locally. The host
still owns user authorization and data access. This wrapper is not a sandbox against
code possessing the same credential or underlying client.

### Limits

| Field | Default | Meaning |
| --- | --- | --- |
| `timeout_seconds` | 120 | Whole operation/run deadline, including execution-slot wait and stream backpressure |
| `max_model_calls` | 8 | Native model attempts across one direct operation or agent run |
| `max_tool_calls` | 16 | Authorized function executions across one run |
| `max_output_tokens` | 1024 | Per-model-call output ceiling |
| `max_input_bytes` | 128000 | Serialized native request and checked message/instruction input bound |
| `max_output_bytes` | 1000000 | Aggregate native response bytes and separately bounded emitted/returned JSON content |
| `max_tool_result_bytes` | 60000 | Each tool result/progress record |
| `max_concurrency` | 4 | Active operations/agent runs per connection; supported range 1-64 |
| `max_events` | 10000 | Aggregate native updates and separately bounded emitted run events |

Numbers must be positive finite values, not bools. Bounds are not billing quotas; character/
byte counts are not token counts. Budgets are process/run-local, not replica-wide.
Unknown billing, side effects and provider work remain unknown on lost/cancelled responses.

## Model Calls

`model.chat.get_response(text_or_messages, *, stream=False, options=None)` accepts
text, one framework `Message`, or a list/tuple of Messages. Inputs/options are snapshotted.
Non-streaming returns an awaitable `ChatResponse`; streaming returns a framework
`ResponseStream` subclass with `aclose()` and async context management. Its updates are
`ChatResponseUpdate`; `await stream.get_final_response()` reads the one execution's result.

Supported options: `max_tokens`, `temperature`, `top_p`, `response_format`, `reasoning`
when declared, `tools`, `tool_choice`, `parallel_tool_calls`. `model` is accepted only
when equal to the fixed deployment and `store` only when false. Reasoning supports
`effort` and public `summary` settings, not raw hidden reasoning access. Sampling values
are finite and bounded. `max_tokens` cannot exceed the policy ceiling.

The framework supplies internal instructions for agent calls; public options cannot
override them. Unknown options, raw SDK headers/body/URL settings and hosted tools
refuse. Direct tool declarations must be registered framework FunctionTools with granted
names, and direct model calls never invoke them automatically.

The supported content profile is text plus framework local function/result, usage and
reasoning-summary content. Images, arbitrary URLs/files/audio and hosted execution
are explicitly unsupported in this alpha. No generic raw Responses escape hatch exists.

`response_format` uses the native framework/Pydantic schema support; `.value` carries
validated data. Inspect finish status and refusal rather than assuming every provider
response contains a valid structured value.

## Embeddings

`await model.embeddings.get_embeddings(texts, *, options=None)` requires an explicit
`embedding_model`. Inputs: 1-2048 nonempty strings in a list/tuple, within the byte bound.
Only `dimensions` is currently an optional request field. Built-ins request float vectors;
base64, image, token-ID and other encodings are unsupported rather than silently coerced.

Before framework normalization, native results must have exactly one item per input,
unique integer indices covering the complete input set, nonempty finite numeric vectors
and equal/declared dimensions. A malformed batch returns no usable vectors. Valid results
are ordered by input index, not native position. Returned framework embedding values
and usage remain the upstream public types.

## Agents, Tools And Sessions

`model.agent(instructions=..., tools=(), name="assistant", authorize_tool=None,
required_capabilities=())` or `bind_agent(connection=model, ...)` constructs an
`AgentBinding`. Each run creates isolated native framework agent/tool execution state;
HTTP clients are reused. There is exactly one native function-invocation loop.

Tools are normal typed synchronous/asynchronous functions or framework `FunctionTool`
values. Native schema generation is reused. Each name must be granted; duplicate names,
hosted tool objects, declaration-only tools and interactive-approval modes refuse.
Complete generated arguments are checked before any batch tool executes. Unknown names,
duplicate call IDs, extra arguments, strict type failures and truncated tool calls refuse.
Synchronous functions run off the event loop. The tool result must be finite JSON data
within its bound; arbitrary exceptions are replaced with a payload-free `tool_failed`.

Explicit `FunctionTool` JSON-schema mappings survive binding and are validated with
`jsonschema` before any function in the batch runs. A recognized declared JSON Schema draft
is honored; omitted draft uses 2020-12. Invalid schemas and unknown drafts refuse during
binding. Local references are supported; remote references are never fetched and an unresolved
reference refuses the call. Pydantic schemas retain their native strict validation. JSON Schema
constraints are not an authorization mechanism; the host tool authorizer still applies.

Optional `authorize_tool(ToolCall)` may return/await exactly `True` to approve a call.
It receives name, snapshotted arguments, principal, run ID and call ID. A denied call
executes no function and stops subsequent model work. Budget reservations occur without
an intervening await. A concurrently started sibling tool may already have effects when
another fails; no atomic batch or rollback is claimed.

`agent.run(messages, *, session=None, principal="operator", stream=False, options=None)`
returns an awaitable `AgentResponse` or a managed `ResponseStream[RunEvent, AgentResponse]`.
Per-run tool overrides are refused. Omitted session means a fresh single-turn session.

`agent.create_session(principal=...)` creates an in-memory owner-bound session. The host
must derive principal from its authenticated caller; the default is single-operator use,
not multi-user authentication. Turns serialize per session. Different owners, binding/
definition changes and interrupted sessions refuse before another model call. No provider
conversation ID is accepted from a request. History is held by `InMemoryHistoryProvider`
under `store=False`; oversized history refuses through input limits instead of silently
dropping messages. There is no disk/replica persistence or transcript-transfer API.

`session.result(principal=...)` returns a copy of the last completed response or `None`;
another owner is denied. A failed later run does not erase that previous result. Receipts
distinguish runs. The host owns retention of session objects and any durable persistence.

## Stream Events

`RunEvent` has `schema_version=1`, `kind`, `run_id`, monotonically increasing run-local
`sequence`, and `data`. `event.text` is the text for `text.delta`, otherwise empty.
`to_dict()` deliberately includes the payload and is not a log-safe projection.

| Kind | Data |
| --- | --- |
| `run.started` | Agent name, session ID |
| `text.delta` | `text` |
| `reasoning.summary.delta` | Provider-supported summary `text`, item `id` |
| `tool.call.delta` | `call_id`, name, argument fragment |
| `tool.call.ready` | `call_id`, name, complete validated arguments |
| `tool.started` | `call_id`, name; authorization has succeeded |
| `tool.progress` | `call_id`, explicit tool-emitted progress object |
| `tool.result` | `call_id`, original bounded JSON tool result |
| `tool.failed` | `call_id`, name, safe failure metadata |
| `usage` | Observed framework usage fields |
| `run.completed` / `run.incomplete` / `run.refused` | Agent/session identity and counts |
| `run.failed` | Safe error code/category/field/action, followed by `LlmError` |

`await report_progress({...})` is supported inside an executing async tool in a streamed
run. It cannot be called outside that context and is not model-generated tool arguments.
Non-streaming callers should not use progress-only tools. No browser/SSE server is started.

The bounded queue holds at most 16 updates; slow consumers backpressure the producer.
Native event/body and run event/output limits apply. A normal consumed run has one terminal
event. Caller cancellation, deadline cancellation or a disconnected consumer may prevent
delivery of a terminal event; the exception/close outcome remains authoritative. Exactly-once
network delivery, event replay and automatic resumption are not implemented.

Explicit failure events are retained and raised after bounded native iteration closes.
Quiet EOF without terminal evidence raises `missing_terminal_event`; partial text remains
partial. A tool call on an incomplete response is never executed. The final response is
available without another provider call. Close streams with `async with` or `aclose()`.

## Lifetime, Cancellation And Errors

One connection belongs to one event loop. Owned resources close idempotently; injected
credentials and transport are borrowed. Connection close cancels active work and closes
outstanding streams. Cancellation propagates, and interrupted sessions cannot replay
implicitly. Native stream settlement is bounded to one additional second with new model/
tool work denied. Remote work or a synchronous tool thread may continue; no rollback or
zero-cost cancellation is promised.

`LlmError` exposes safe `code`, `category`, optional `field`, `action`, and `metadata()`.
Provider error messages are not forwarded or chained onto the public exception. Categories
include `config`, `invalid`, `denied`, `unsupported`, `auth`, `rate_limit`, `failed` and
`interrupted`. No automatic retry occurs, including after tool effects or output.

Text/agent results carry a small receipt under `additional_properties["llm_interface"]`:
run ID, model/tool counts, status, measured elapsed milliseconds and `persistence=not_configured`.
Do not automatically log full framework results, messages, tool events or vectors.
Payload-capable framework/SDK DEBUG logging, sensitive framework telemetry and Azure
Projects console logging are refused. Arbitrary external instrumentation remains host-owned.

## Extend With Another Provider

`from_clients(config, *, chat_factory, embedding_client=None, policy, capabilities,
owned_resources=(), native_embedding_validation=False)` is an explicit trusted adapter API.
`chat_factory(middleware, enabled)` must return a framework-compatible client with the
supplied guards attached and exactly one tool loop when enabled. Native target binding,
auth, redirects, retries, byte limits and pre-normalization evidence are the adapter's
responsibility. The library still applies input policy, output shape and event contracts.

Native embedding index validation must be implemented by that adapter before asserting
`native_embedding_validation=True`; otherwise embedding calls refuse. This flag records
an adapter-author assertion, not an automatic proof. `describe()` labels native enforcement
as adapter-owned. Add conformance tests for each real provider before advertising support.
Dependencies are borrowed unless explicitly listed in `owned_resources`; duplicates close once.

No factory imports or executes configuration-supplied code. There is no automatic plugin
discovery or runtime skill import. The built-in Foundry/OpenAI paths do not require this API.

## Not Implemented Or Verified

No application migration, cloud grant, live inference, remote-agent hosting, MCP server,
multimodal/hosted tools, separate Foundry models-endpoint adapter, synchronous legacy shim,
durable persistence, or automatic retries/fallback. Those require their own scoped work.
The [testing record](VALIDATION.md) distinguishes offline observations from live identity,
provider/model compatibility, dependency matrix and cognitive-load testing still pending.