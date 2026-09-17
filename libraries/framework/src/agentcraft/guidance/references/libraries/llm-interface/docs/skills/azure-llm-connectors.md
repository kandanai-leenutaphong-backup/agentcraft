# Azure Model Integration

Install `llm-interface` with its needed provider extra; import `llm_interface`.
The [implemented contract](../../CONTRACT.md) and [usage](../../USAGE.md) own the
async target. `azllm`, `azure_llm_compat` and `modelaccess` are not alternate
providers or compatibility prerequisites. This guide supersedes historical
statements that the retired model skills still ship Python/MCP runtimes.

Azure LLM Connectors is the single native model-integration skill;
`managed-identity-model-clients` remains a catalogue alias. Its detailed
[identity and failure notes](managed-identity-model-clients.md) remain available.

## Public Contract And Authorization

`connect(endpoint, model, *, credential, allow_model_calls=False, ...)` returns a
`Connection`. Construction and `describe()` do not acquire tokens or call models.
Use `await connection.chat.get_response(...)`, a managed streaming response,
`await connection.embeddings.get_embeddings(...)`, or `connection.agent(...)`.
Microsoft Agent Framework and provider SDKs own native protocols and the tool loop.

Endpoint, deployment, exact allowed host, credential, grants and limits enter at
the host composition root. Inference is denied by default. Tool names require
separate grants and the host may authorize each `ToolCall`. These decisions do
not authenticate an application user or grant Azure permissions. Loading the
native skill permits no model spend, service call, grant or target change.

Azure profiles use explicit host-selected identity or supported token callables;
native Azure Identity providers refresh credentials. Do not cache a token string
as a permanent key or silently select ambient credentials. Use account origins or
supported Foundry project endpoints; native clients build inference paths. Pin
operator-selected destinations. Shape validation cannot authorize user-supplied URLs.

## Results, Errors And Bounds

Framework `ChatResponse` / `ChatResponseUpdate`, `GeneratedEmbeddings` and
`AgentResponse` remain the public result types. Structured response values use
native framework/Pydantic validation; inspect refusal and completion before using
`.value`. Partial output and HTTP 200 are not complete success.

`LlmError` exposes safe `code`, `category`, `field`, `action` and `metadata()`.
Categories include config, invalid, denied, unsupported, auth, rate_limit, failed
and interrupted. Provider payloads are not forwarded or chained. Do not log full
messages, framework results, vectors or tool events. Payload-capable native DEBUG
logging and sensitive telemetry are refused; other instrumentation is host-owned.

Default per-operation/run limits: 120 seconds including slot wait/backpressure,
8 model attempts, 16 tool calls, 1,024 output tokens per call, 128,000 input bytes,
1,000,000 output bytes, 60,000 bytes per tool result, concurrency 4 and 10,000 events.
Concurrency is bounded to 1-64. Byte limits are not token counts or billing quotas;
run-local budgets are not replica-wide or old MCP process-lifetime budgets.
No automatic retry or fallback occurs, including after partial output/tool effects.

Native failure events raise. Quiet EOF without terminal evidence raises
`missing_terminal_event`; no final success is synthesized from partial text.
Consume the final result and close streams with `async with` or `aclose()`.
The final result does not trigger another model request.

Embedding calls require an explicit `embedding_model` and 1-2048 nonempty strings
within byte limits. Before normalization, indices must uniquely cover every input;
vectors must be nonempty, finite and dimension-consistent. Invalid batches yield
no usable vectors. Valid vectors follow input index, not response-array position.
Different embedding accounts require separate explicit connections, not guessed
endpoints or a fallback chat deployment.

## Lifecycle And Retired Recipes

Reuse one connection within one event loop. Async context management or `aclose()`
closes owned clients and streams exactly once, never borrowed credentials or
transports. The host closes its credentials. Cancellation propagates; it cannot
guarantee remote rollback, zero billing or termination of a synchronous tool thread.
Interrupted sessions cannot silently resume. Owner-bound session results are
in memory; the host owns any durable persistence and caller identity.

There is no synchronous/raw Responses shim, `store=True`, `previous_response_id`
escape hatch, unknown SDK-option forwarding, hosted-tool adapter, separate Foundry
`/models` endpoint adapter or bundled MCP server. Use `store=False`; this is a
provider request, not a universal no-retention guarantee. An independently authorized
host adapter must enforce its own process budget and input schema; no legacy adapter
is retained merely to preserve obsolete signatures.

## Findings And Verification

[Operational notes](../../OPERATIONS.md) retain all azllm G1-G18 findings with target
corrections. Their old skill/source references and retention gates are historical.
The retirement manifest (source-or-asset-not-bundled; source reference: `azure-llm-connectors-retirement.json`) records every removed
path, hash and external recovery location; no obsolete source is kept in docs.
The existing offline example (source-or-asset-not-bundled; source reference: `../../examples/offline.py`) describes the target.

```bash
PYTHONPATH=libraries/llm-interface/src python -B -m unittest discover \
  -s libraries/llm-interface/tests -q
```

Existing tests use synthetic transports and socket refusal. They cover inference
denial, target integrity, token/client ownership, bounded/failed streams, embedding
indices, safe errors, tools and session ownership. No live identity, model, provider
compatibility, cloud deployment or wheel publication is proved by this retirement.
Native names/triggers and Microsoft MIT notices remain; parent owns discovery,
shared metadata and removal of `azllm_*` MCP registrations.