# CONTRACT — foundry-agent-runtime

Everything needed to reimplement this box, in any language, against the same
Foundry project and the same declarative roster. Exact names, exact defaults,
exact algorithms.

---

## 1. Configuration

### 1.1 Environment variables

Prefix defaults to `FOUNDRY_` and is overridable, so two projects can be wired
into one process.

| Variable | Required | Type | Default |
| --- | --- | --- | --- |
| `<P>PROJECT_ENDPOINT` | yes | string | — |
| `<P>MODEL_DEPLOYMENT` | yes | string | — |
| `<P>MODEL_DEPLOYMENT_FAST` | no | string | `""` |
| `<P>API_VERSION` | no | string | absent |
| `<P>FALLBACK_MODELS` | no | comma-separated | empty |
| `<P>MAX_RETRIES` | no | integer ≥ 1 | `3` |

Values are stripped. An empty string after stripping is treated as absent. Both
required variables missing produces **one** error naming both, not two errors.

### 1.2 Endpoint form

```
https://<resource>.services.ai.azure.com/api/projects/<project>
```

### 1.3 Validation, split by severity

**Fatal — the constructor raises:**

| Condition | Reason |
| --- | --- |
| empty `project_endpoint` | nothing to call |
| empty `model_deployment` | nothing to call it with |
| endpoint not `https://` | a bearer token must not cross plaintext |
| `max_retries < 1` | zero attempts is not a retry policy |

**Non-fatal — reported by `warnings()`, never raised:**

| Condition | Reason |
| --- | --- |
| endpoint lacks `/api/projects/` | account endpoint, not project (G1) |
| endpoint ends with `/` | some clients build a double slash |
| primary appears in `fallback_models` | fallback shares the failure domain (G8) |

The split is deliberate. Shape rules that are *usually* right must warn, not
raise, so an endpoint form nobody anticipated is an investigation rather than an
outage.

### 1.4 Derived values

```
model_queue()  = dedupe_preserving_order([model_deployment, *fallback_models])
resolve_model(requested):
    ""      -> model_deployment
    "fast"  -> model_deployment_fast or model_deployment
    other   -> other verbatim
```

The config object is **immutable**. `with_model(name)` returns a copy; the retry
loop needs a config per attempted model and mutating a shared one corrupts
concurrent turns.

---

## 2. Identity

- Exactly one credential per process, built on first use, guarded by a lock with
  a double check inside it.
- Default is the SDK's ambient credential chain, which resolves to a developer
  login locally and to workload identity in cloud. No key material anywhere, at
  any layer, in any environment.
- Token audience for the Foundry data plane: `https://ai.azure.com/.default`.
  Configurable; sovereign clouds differ.
- The credential is never logged, never serialised, never placed on the config
  object.

---

## 3. Client construction

Arguments passed to the Agent Framework Azure client:

| Key | Source | Notes |
| --- | --- | --- |
| `project_endpoint` | `config.project_endpoint` | verbatim |
| `model_deployment_name` | `config.model_deployment` | verbatim |
| `credential` | injected or process credential | |
| `api_version` | `config.api_version` | **omitted entirely when unset** |

`api_version` is omitted rather than passed as null: some versions treat an
explicit null as a version request and fail rather than defaulting.

### 3.1 Client pool

- Cache key is the **agent id**. One client per agent, for the process lifetime.
- Thread-safe, double-checked. Concurrent first-access for one agent id yields
  one client, not two.
- `clear()` empties the cache. Clients already handed to a running turn continue
  to work; they are simply not handed out again.

Sharing one client across agents is the defect in G2. Building one per request
is correct but pays a construction and a handshake per turn.

---

## 4. Tool marking

A tool is a plain function carrying a marker attribute:

```
attribute name: __agent_tool__
attribute value: {
    "description":   str,   # explicit override, else the docstring, stripped
    "approval_mode": str,   # default "never_require"
    ...                     # arbitrary consumer keys, preserved
}
```

The decorator **returns the function unwrapped**. Calling it directly is
unaffected, which is what keeps tools unit-testable without the SDK.

Marker resolution reads a caller-supplied tuple of attribute names, first match
wins. A tool library using a different marker interoperates by passing its own
name; there is no requirement that this box's marker be the only one present.

### 4.1 Binding

```
bind_tools(tools, client, markers):
    if client is not an SDK client:   return list(tools)          # unchanged
    for each tool, in order:
        metadata = first marker attribute present, else None
        if metadata is None:          keep as-is                  # already SDK, or hosted
        else:                         wrap with sdk.tool(approval_mode=...)
```

Order is preserved and never sorted (G7). Unmarked entries pass through so an
already-decorated tool or a hosted platform-tool object is not wrapped twice.

An SDK client is identified by the top-level package of its type's defining
module, not by `isinstance` — importing the class to compare against would defeat
the lazy-import property of the whole package.

---

## 5. Agent construction

### 5.1 Spec field resolution

Accepts a mapping or an object. For each field, in this fixed order:

1. attribute on the spec
2. mapping key on the spec
3. key inside the spec's `extra` mapping

First hit wins, so a declared field always beats pass-through metadata of the
same name.

| Field | Type | Default | Notes |
| --- | --- | --- | --- |
| `agent_id` | str | `""` | logging identity |
| `name` | str | agent id, else `"agent"` | |
| `description` | str | `""` | |
| `instructions` | str | `""` | empty builds, and logs a warning |
| `tools` | sequence | `()` | order significant |
| `model` | str | `""` | `""` = config default, `"fast"` = alias |
| `parallel_tool_calls` | bool | `false` | |
| `compaction` | bool | `true` | |

### 5.2 Model precedence

```
model_override  >  spec.model  >  config.model_deployment
```

after `resolve_model` has expanded the `"fast"` alias. An unresolvable model
raises; it is never silently defaulted.

### 5.3 The SDK call

```
client.as_agent(
    name              = resolved name,
    description       = resolved description,
    instructions      = resolved instructions,
    tools             = bound_tools or None,          # None, never []  (G4)
    default_options   = { "allow_multiple_tool_calls": parallel,
                          "model_id": model },
    middleware        = middleware or None,
    context_providers = list(providers) or None,
)
```

### 5.4 Compaction attachment

Post-construction, and skipped entirely when any of these hold: the spec sets
`compaction: false`; `token_budget <= 0`; no tokenizer; the agent already carries
a strategy.

The strategy is composed, in this order:

1. tool-result compaction
2. truncation — `max_n=200`, `compact_to=100`

Tool results first, because they are the largest and least re-read content in a
transcript. Reversing the order truncates messages while one oversized tool
result still dominates the window.

`token_budget` is the context window **minus** the response budget, not the
window.

---

## 6. Failure classification

Case-insensitive substring match against `str(exception)`. Matching on text
rather than exception type is deliberate: types vary by transport and SDK
version, the status code and reason in the text do not.

| Class | Substrings |
| --- | --- |
| `fatal` | `content_filter`, `content management policy`, `unauthorized`, `forbidden`, `401`, `403` |
| `rate_limit` | `429`, `rate limit`, `retry after`, `throttl`, `token rate limit`, `peak load`, `maximum usage` |
| `transient` | `sorry, something went wrong`, `internal server error`, `502`, `503`, `504`, `service unavailable`, `gateway timeout` |
| `unknown` | anything else |

**Evaluation order is fatal → rate_limit → transient → unknown.** A 403 whose
body mentions throttling is fatal (G11).

### 6.1 Retry-after parsing

```
match  retry\s*(?:after|in)\s*(\d+)     else  (\d+)\s*second
clamp  to [5, 60] seconds
absent -> caller default, 15
```

### 6.2 Per-attempt decision

```
should_retry(exc, attempt, max_retries):     # attempt is 0-based
    fatal                      -> (false, 0)
    attempt >= max_retries - 1 -> (false, 0)
    rate_limit                 -> (true, parse_retry_seconds(text))
    otherwise                  -> (true, min(2^attempt * 2, 30))
```

Unknown errors are retried. Observed failure modes are overwhelmingly transient,
and a genuinely permanent unknown costs at most `max_retries` attempts.

### 6.3 Fallback loop

```
for model in config.model_queue():
    for attempt in 0 .. max_retries-1:
        try:    return run(model)
        except: classify
                fatal        -> re-raise immediately, do not try other models
                not retryable-> break to the next model
                otherwise    -> sleep(delay), retry the same model
raise the last exception
```

Each deployment starts its attempt count fresh: a saturated deployment must not
consume the budget of one that is healthy.

---

## 7. Reference sequence

```
config = FoundryConfig.from_env()
pool   = ClientPool(foundry_agent_client(config))

for agent_id, spec in roster.items():
    agents[agent_id] = build_agent(
        spec, pool.client_for(agent_id), config, agent_id=agent_id,
        middleware=build_tracing_middleware(),
        tokenizer=tokenizer, token_budget=window - response_budget,
    )

answer = await run_with_fallback(
    lambda model: agents["planner"].run(user_text), config, context="planner")
```

---

## 8. Logging

Structured, prefixed, and free of secrets. Event names are part of the contract
because dashboards key on them.

| Event | When |
| --- | --- |
| `foundry.credential.created` | first credential build |
| `foundry.client.built` | client construction, with the redacted config |
| `foundry.client.pooled` | a new agent id enters the pool |
| `foundry.agent.built` | agent construction, with model and its source |
| `foundry.agent.no_instructions` | empty system prompt |
| `foundry.compaction.attached` / `.disabled` / `.unavailable` | strategy outcome |
| `foundry.middleware.created` / `.unavailable` | tracing outcome |
| `foundry.tool.complete` / `.error` | per tool invocation |
| `foundry.retry` | every retried failure, with class and delay |
| `foundry.retry.exhausted` | queue exhausted |

The redacted config keeps the endpoint host and drops the project path. Error
text in traces is truncated to 200 characters — an unbounded tool exception can
carry an entire response body into a log sink.

---

<!-- api-surface:start -->

## Public surface

Every name exported by `foundryagent`. Generated from the package with `template/api_surface.py`; regenerate after changing `__all__`.

| Name | Kind | Description |
| --- | --- | --- |
| `FoundryConfig` | class | Where the model lives, and how hard to try when it refuses. |
| `DEFAULT_ENV_PREFIX` | constant | 'FOUNDRY_' |
| `get_credential` | function | Return the process-wide credential, building it on first use. |
| `set_credential` | function | Install an explicit credential, replacing any cached one. |
| `reset_credential` | function | Drop the cached credential. For tests, and for a deliberate re-auth. |
| `has_credential` | function | True when a credential is already cached. Never builds one. |
| `foundry_agent_client` | function | Build a zero-arg factory producing Foundry-backed agent clients. |
| `ClientPool` | class | One client per agent id, built on demand and cached for the process. |
| `build_agent` | function | Build one SDK agent from a spec and a client. |
| `spec_field` | function | Read ``key`` from a spec of any accepted shape. |
| `tool` | function | Mark a function as agent-callable. Usable bare or with arguments. |
| `tool_metadata` | function | Return the stamped metadata for ``fn``, or ``None`` when unmarked. |
| `TOOL_MARKER` | constant | '__agent_tool__' |
| `DEFAULT_TOOL_MARKERS` | constant | ('__agent_tool__',) |
| `bind_tools` | function | Bind marked callables to the concrete SDK, preserving order. |
| `maf_available` | function | True when the Agent Framework can be imported. |
| `is_maf_client` | function | True when ``client`` is an Agent Framework client. |
| `build_compaction_strategy` | function | Build the composed context-compaction strategy. |
| `build_tracing_middleware` | function | Build the tool-tracing middleware pipeline. |
| `classify` | function | Return ``"fatal"``, ``"rate_limit"``, ``"transient"`` or ``"unknown"``. |
| `is_rate_limit` | function | True when the service is shedding load rather than refusing the request. |
| `is_fatal` | function | True when retrying cannot help: content filter, auth, authorization. |
| `is_transient` | function | True for server-side errors that commonly succeed on a second attempt. |
| `parse_retry_seconds` | function | Extract a retry-after hint from error text, clamped to a sane range. |
| `should_retry` | function | Decide whether to retry ``exc``, and how long to wait first. |
| `run_with_fallback` | function | Run ``run(model_deployment)``, retrying and falling back across models. |
| `SdkUnavailable` | class | Raised when a required SDK is absent, carrying the install line. |
| `sdk_available` | function | True when ``path`` can be loaded — substituted or genuinely installed. |
| `set_sdk` | function | Substitute the module returned for ``path``. |
| `set_sdk_absent` | function | Force ``path`` to behave as if it were not installed. |
| `clear_sdks` | function | Drop every substitution. Call in test teardown. |

<!-- api-surface:end -->
