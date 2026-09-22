# Managed-Identity Model Clients

Use installed `llm-interface`; import `llm_interface`. The native skill name
remains a discovery trigger; the `managed-identity-model-clients` distribution
and `modelaccess` runtime are retired. Start with the
[canonical model guide](azure-llm-connectors.md) and [contract](../../CONTRACT.md).
No separate token cache, synchronous facade, raw SDK pass-through or MCP runtime
is copied into this library.

## Target Use

Supply an explicit `azure.identity.aio.ManagedIdentityCredential` or separately
selected developer credential to `connect(...)` at the host composition root.
Async and sync credentials are supported by matching native providers; model
operations themselves are async. Reuse one connection within one event loop.
The host owns configuration, caller authorization and credential cleanup.

Model calls require `allow_model_calls=True` from the authorized host; no skill
load, configuration file, tool argument or installation supplies that grant.
Roles are separately authorized administrative decisions. Use the selected
deployment, not a model family name, and exact trusted endpoint/host coordinates.
Different embedding accounts use separate connections with explicit embedding
deployments. Never infer credentials, keys or an alternate account.

Current operations are `chat.get_response`, managed native streaming,
`embeddings.get_embeddings` and framework agents. Structured output uses native
`response_format` and validated `.value`; inspect refusal/completion. No raw
Responses option can enable `store=True`, change target, add headers or bypass
the supported option set. No synchronous shim is required to retire old callers.

## Retained Findings

These preserve all fifteen managed-identity skill findings. They are historical
observations, interpreted against the current target, not fresh live evidence.

| Original finding | Target behavior / host action |
| --- | --- |
| G1 Missing account resembles permission failure | Validate explicit coordinates locally before diagnosing live identity. No built-in account or ambient fallback. |
| G2 Requests reach the wrong URL | Use supported account/project endpoint shapes; native clients own path construction. |
| G3 Stream appears successful without usable output | Require terminal evidence; in-band failures and quiet EOF raise, never synthesize completion. |
| G4 Frozen token expires after an hour | Borrow an identity/token callable; native Azure Identity providers own refresh. |
| G5 Async token provider receives a string | Use matching native sync/async provider contracts; do not hand-roll a token wrapper. |
| G6 Embedding deployment belongs to another account | Create a separate explicit connection. A chat deployment is never the implicit embedding default. |
| G7 Refusal mistaken for crash or valid empty object | Inspect finish/refusal state before consuming structured `.value`. |
| G8 Vectors attached to wrong text | Validate native count, complete unique integer indices, finite vectors and dimensions before normalization; return input order. |
| G9 Closing one client closes caller resources | Credentials and injected transports are borrowed. The host closes them; owned resources close once. |
| G10 Abandoned/failing streams leak sockets | Use stream async context management or `aclose()`; connection close settles outstanding native work. |
| G11 Errors/telemetry expose payloads | Use `LlmError.metadata()` only. Provider messages/chains are stripped; results, vectors and events are not log-safe. |
| G12 Unexpected provider retention | `store=True` and provider-response chaining are unsupported; `store=False` is not a universal retention guarantee. Host owns session retention. |
| G13 One stuck deployment occupies a worker | Deadline includes slot waits and backpressure; bounded concurrency and no hidden retries. |
| G14 Cancellation becomes ordinary failure | Cancellation propagates and interrupted sessions refuse implicit replay; no remote rollback or zero-cost promise. |
| G15 Configured endpoint receives credentials | Trusted exact host/route binding, redirect refusal and explicit audience; request data cannot choose targets. |

## Errors, Limits And Lifecycle

Use `LlmError.code`, `category`, `field`, `action` and safe `metadata()`, not old
`ModelError` message parsing or provider tracebacks. Config/invalid/denied/
unsupported are distinct from auth/rate_limit/failed/interrupted outcomes.

Default limits: 120 seconds for the whole operation/run, 8 model calls, 16 tool
calls, 1,024 output tokens per call, 128,000 input bytes, 1,000,000 output bytes,
60,000 bytes per tool result, concurrency 4 and 10,000 events. These are local
bounds, not global billing quotas. Embedding batches are 1-2048 nonempty strings
within those bounds. Unsupported options and malformed batches refuse.

Close the connection through async context management or `aclose()` and close
borrowed credentials at the host. Cancellation may leave remote work or a sync
tool thread running; cleanup is not rollback. Session/result storage is in memory,
owner-bound and not durable. No account, deployment, role, model call or service
write is created by import, installation or this retirement.

## Retirement Evidence

[Exact paths, hashes and recovery](managed-identity-model-clients-retirement.json).
Old contracts/examples are obsolete APIs, not target examples; the library's
[offline example](../../examples/offline.py) supplies the maintained path.
The Microsoft MIT notice remains in the native skill and canonical library.

```bash
PYTHONPATH=libraries/llm-interface/src python -B -m unittest discover \
  -s libraries/llm-interface/tests -q
```

Existing model safety tests cover target/refusal, stream completion, vector order,
safe failures, cleanup and owner-bound results without live calls. Live identity,
provider behavior and packaging/publication remain unverified. Parent integration
owns old `modelaccess_*` MCP registrations and shared discovery/metadata.