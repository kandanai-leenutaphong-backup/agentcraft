# Contract

The specification. Everything here is asserted by `tests/selftest.py`,
`tests/test_sdk_protocol.py` or a worked example, and this document is
sufficient to reimplement the box without reading its source.

Import name: `modelaccess`. Python 3.10+, matching `requires-python` in
`pyproject.toml`.

## MCP Adapter

The optional stdio adapter uses the official MCP SDK, validates every input schema on the
server, and calls only this package's public API. The native library contract below is unchanged.
Verification: [tests/mcp_smoke.py](tests/mcp_smoke.py), via the server's `--selftest` option.

| Tool | Inputs | Output |
| --- | --- | --- |
| `modelaccess_status` | empty object | configuration/grant status, fixture marker, remaining calls, configuration path |
| `modelaccess_ask` | `prompt`, optional `max_output_tokens` | text, result metadata, fixture marker |
| `modelaccess_embed` | `texts`, optional `dimensions` | ordered vectors, embedding metadata, fixture marker |

Operator JSON fields: `endpoint`, `deployment`, optional `embedding_endpoint`,
`embedding_deployment`, `credential_scope`, `allowed_hosts` (list of exact hosts),
`managed_identity_client_id`, `allow_model_calls` (false), `max_calls` (10; 1-1000),
`max_output_tokens` (512; 1-4096), `max_input_characters` (32000; 1-64000), and
`timeout_secs` (30; positive and at most 120). Endpoint/deployment must both be configured
before model calls. Unknown fields and credential fields are refused without their values in errors.

Prompt length is 1-64000 characters and must fit the configured aggregate bound. Embedding
batches hold 1-64 nonempty strings, each at most 8192 characters and subject to the same aggregate
bound. Dimensions default to 3 and may be requested from 1-3072; the provider can impose a narrower
range. Character caps do not prove provider token limits. Tool input cannot override destinations,
deployment names, grants, SDK options or credentials.

Each accepted attempt reserves one call before awaiting the provider; failures consume the
reservation too. SDK retries are zero in this adapter. Restart resets this per-process budget,
which is not a billing quota. Clients are cached by endpoint and deployment and closed at exit;
using an embedding client first cannot change later chat routing on the same host.

MCP failures use `isError` with a category rather than provider text. Fixture mode is a test-only
launch option, not a model-supplied argument; it uses the library's fake clients and marks results.
Raw Responses options, streaming, structured output, and role management remain outside MCP.

## Model of the world

- One **account** is addressed by an endpoint. One **deployment** is a named
  model *inside* one account, and is reachable only through that account's
  endpoint.
- Authentication is Entra only. The unit of credential is a **token provider**:
  a zero-argument callable returning a bearer token, re-invoked by the SDK on
  every request. No token string is ever stored.
- One client wraps one account. Chat and embeddings on different accounts need
  two clients.
- Failures leave this package as exactly one exception type. Provider content
  never travels with them.

## Public surface

### Entry points

| Symbol | Signature | Behaviour |
| --- | --- | --- |
| `connect` | `connect(config=None, *, credential=None, token_provider=None, client=None, owns_client=None) -> ModelClient` | Builds the synchronous client. `config` defaults to `ModelConfig.from_env()`. Precedence: `client` beats `token_provider` beats `credential` beats the ambient `DefaultAzureCredential`. An injected credential is **not** owned, and neither is an injected client: `owns_client` defaults to `client is None`. |
| `connect_async` | `connect_async(config=None, *, credential=None, token_provider=None, client=None, owns_client=None) -> AsyncModelClient` | The asyncio twin, same rules. `credential` must be an asyncio credential and `token_provider` an async callable. |
| `token_provider_for` | `token_provider_for(config) -> Callable[[], str]` | The per-request token callable, for a caller building their own SDK client. |
| `async_token_provider_for` | `async_token_provider_for(config) -> Callable[[], Awaitable[str]]` | The asyncio equivalent. |

`ModelClient(...)` and `AsyncModelClient(...)` take the same keyword arguments
as the function that builds them, `owns_client` included, so the constructor
and the entry point never disagree about ownership.

### Configuration

`ModelConfig` is a frozen dataclass. `endpoint` and `deployment` are required
positionally-or-by-keyword; everything else has a neutral default.

| Field | Type | Default | Rule |
| --- | --- | --- | --- |
| `endpoint` | `str` | — | Normalised on construction. |
| `deployment` | `str` | — | Non-empty, ≤64 chars, `[A-Za-z0-9._-]`. |
| `embedding_deployment` | `str \| None` | `None` | Same rule when set. Never inferred from `deployment`. |
| `embedding_endpoint` | `str \| None` | `None` | Normalised when set. `None` means "same account". |
| `credential_scope` | `str` | `DEFAULT_SCOPE` | Must be `https://…/.default`. |
| `timeout_secs` | `float` | `DEFAULT_TIMEOUT_SECS` (120.0) | Positive and finite. |
| `max_retries` | `int` | `DEFAULT_MAX_RETRIES` (2) | `0 <= n <= 10`. |
| `managed_identity_client_id` | `str \| None` | `None` | Non-blank when set. |
| `default_max_output_tokens` | `int \| None` | `None` | Positive when set; applied to convenience calls only. |
| `allowed_hosts` | `tuple[str, ...] \| None` | `None` | When set, `endpoint` and `embedding_endpoint` must name one of these hosts. `None` accepts any https host. |

Derived: `base_url` (the `/openai/v1/` URL given to the SDK), `account_host`
(hostname, safe to log), `embeddings_are_local` (whether one client can serve
both).

- `ModelConfig.with_overrides(**changes)` — validated copy; unknown field is a
  `ConfigError`.
- `ModelConfig.from_env(prefix=ENV_PREFIX, env=None)` — reads `ENDPOINT`,
  `DEPLOYMENT`, `EMBEDDING_DEPLOYMENT`, `EMBEDDING_ENDPOINT`, `SCOPE`,
  `TIMEOUT_SECONDS`, `MAX_RETRIES`, `CLIENT_ID`, `MAX_OUTPUT_TOKENS` under
  `ENV_PREFIX` (`MODEL_`). Missing endpoint or deployment is a `ConfigError`
  naming the variable. Any key-shaped variable (`MODEL_API_KEY`, `MODEL_KEY`,
  `AZURE_OPENAI_API_KEY`, `OPENAI_API_KEY`) is a `ConfigError`, never ignored.
- `embedding_config(config, *, deployment=None, endpoint=None, **overrides)` —
  returns the config for the account that owns the embedding deployment,
  preserving timeouts, retries and identity settings. `ConfigError` when no
  embedding deployment is configured or named.
- `normalize_endpoint(raw)` — the URL rule alone: accepts a bare hostname, a
  portal endpoint, `/openai` or `/openai/v1` suffixes, with or without a
  trailing slash; returns `https://host[/path]/openai/v1/`; idempotent.
  Refuses empty, non-https, embedded credentials, whitespace, query string,
  fragment, and `..` in the path. **Shape validation, not a security control:**
  every syntactically valid https host is accepted, and an Entra bearer token
  is then sent to it. See "Trust boundary" below.
- Constants: `DEFAULT_SCOPE` (`https://cognitiveservices.azure.com/.default`),
  `DEFAULT_TIMEOUT_SECS`, `DEFAULT_MAX_RETRIES`, `ENV_PREFIX`,
  `MAX_EMBEDDING_INPUTS` (2048, the published batch ceiling).

### Trust boundary

`endpoint`, `embedding_endpoint` and `credential_scope` are **trusted operator
configuration**. A token for `credential_scope` is sent to whatever host the
endpoint names, so a `ModelConfig` built from a tenant record, a request field
or a user-editable settings row is a token-exfiltration path. Nothing in
`normalize_endpoint` prevents that: it checks URL shape.

When an endpoint value has to come from data the operator does not control,
set `allowed_hosts` from something that data cannot edit. It is an ordinary
allowlist over hostnames, checked at construction for both endpoints, and it
is the only host restriction this package makes. `credential_scope` remains
configurable, because a sovereign or non-public cloud has a different resource
audience.

### Clients

`ModelClient` and `AsyncModelClient` have the same surface; every async method
is awaited and the two stream methods return async iterators.

| Method | Returns | Notes |
| --- | --- | --- |
| `respond(**options)` | provider object, untouched | Only `model` is defaulted. Nothing else is added or removed. |
| `ask(prompt, *, deployment=None, instructions=None, **options)` | `TextResult` | `store=False` unless set by the caller. `default_max_output_tokens` applied when configured. |
| `parse(prompt, *, text_format, deployment=None, instructions=None, **options)` | `ParsedResult` | `text_format` is a pydantic model class. A refusal does not raise. |
| `embed(input, *, deployment=None, dimensions=None, **options)` | `EmbeddingResult` | `input` is **positional-only** — one string or any iterable of strings, copied before validation — which is why `embed(input=[…])` lands in `**options` and is a `ConfigError`. A per-call `deployment=` does not relax the cross-account check. |
| `embed_raw(**options)` | provider object, untouched | Only `model` is defaulted, to the embedding deployment. `allow_foreign_account=True` is consumed here — the one documented escape from the cross-account check — and is never sent to the provider. |
| `stream_text(prompt, *, deployment=None, instructions=None, **options)` | iterator of `str` | Raises on in-band `error`/`response.failed`. A plain method on both classes, not a generator, so a closed client refuses **at the call** rather than at first iteration. |
| `stream_events(**options)` | iterator of provider events | Raw feed; error events are yielded, not raised. `stream=True` is redundant but accepted, `stream=False` is a `ConfigError`. |
| `close()` / `aclose()` | `None` | Idempotent. Closes the HTTP client only when it owns it, the credential only when owned. Never raises. |
| `client`, `token_provider` | properties | `client` refuses when closed. |

Both are context managers (`with` / `async with`). Every method on a closed
client raises `ModelError(category="config")`, **at the call** — including the
two streaming methods, which return an iterator rather than being generators.

`connect`/`connect_async` and both constructors take `owns_client`. It defaults
to `client is None`: a client this package builds is closed by `close()`, an
injected one is not, because the caller may still be using it. Pass
`owns_client=True` to transfer the lifecycle. This mirrors `owns_credential`.

Cancellation is never translated. `KeyboardInterrupt`, `SystemExit`,
`GeneratorExit` and `asyncio.CancelledError` propagate unchanged, so
`asyncio.wait_for` raises `TimeoutError`, a cancelled task reports as
cancelled, and Ctrl-C is not absorbed into the retryable-error vocabulary.

Reserved options: passing `model`, `stream` or `input` to a convenience method
is a `ConfigError` (use `respond`/`stream_events`); passing `model`, `input` or
`dimensions` to `embed` as an option is a `ConfigError` (use `embed_raw`).

### Results

- `TextResult` — `text`, `response_id`, `deployment`, `model`, `status`,
  `usage`, `raw`; `complete`, `input_tokens`, `output_tokens`; `metadata()`.
- `ParsedResult` — `parsed`, `text`, `response_id`, `deployment`, `model`,
  `status`, `refusal`, `usage`, `raw`; `complete`, `refused`; `metadata()`.
- `EmbeddingResult` — `vectors` (tuple of tuples, in **input** order),
  `deployment`, `model`, `usage`, `raw`; `vector` (single input only, else
  `ConfigError`), `count`, `dimensions`; `metadata()`.

All three are frozen. `metadata()` and `__repr__` contain identifiers, status
and counts — never prompt, completion, refusal text or vectors.

Alignment rule for `EmbeddingResult`: each returned item is placed at its own
reported `index`. Any of — item count ≠ input count, duplicate index,
out-of-range index, non-integer index, missing vector, empty vector,
non-finite or non-numeric component, differing vector widths — raises
`ModelError(category="unknown", retryable=False)`. A base64 payload raises
`ConfigError`.

### Errors

`ModelError` is the only exception type that escapes. `ConfigError` subclasses
it, so one `except ModelError` is enough.

Attributes: `message`, `category`, `status_code`, `retryable`, `request_id`,
`deployment`, `code`.

`ErrorCategory` is one of `config`, `auth`, `not_found`, `bad_request`,
`rate_limit`, `timeout`, `connection`, `server`, `stream`, `unknown`.
`retryable` is True exactly for `rate_limit`, `timeout`, `connection` and
`server` unless set explicitly.

Mapping: 401/403 → `auth`; 404 → `not_found`; 400/422 and other 4xx →
`bad_request`; 429 → `rate_limit`; 5xx → `server`; SDK timeout → `timeout`;
SDK connection error → `connection`; an exception whose class is named
`ClientAuthenticationError` or `CredentialUnavailableError` → `auth`, not
retryable; anything else → `unknown`, not retryable.

The original exception is attached as `__cause__`, except when the exception
was already a `ModelError`: that one propagates unchanged rather than becoming
its own `__cause__`. A `__cause__` chain may contain provider text — it is what
a debugger needs and what a log formatter must not print. `str(ModelError)`,
`repr(ModelError)` and `metadata()` are the content-free projections; a full
traceback is not.

### Offline doubles

Shipped with the mechanism because the injection seam is only usable if a
stand-in exists.

- `FakeClient(*, responses=(), embeddings=(), streams=())` — sync stand-in.
  Queues are consumed in order; an exception in a queue is raised. Records
  `requests` (each with a `kind` key), `streams_opened`, `closed`.
- `FakeAsyncClient(...)` — the asyncio twin; its stream `close()` is a
  coroutine, which exercises the awaitable-close path.
- `fake_text_response(text, *, response_id, model, status, usage)`
- `fake_parsed_response(parsed, *, text, refusal, response_id, model, status, usage)`
- `fake_embedding_response(vectors, *, indexes=None, model, usage)` — pass
  `indexes` to build shuffled, duplicated or out-of-range responses.
- `text_delta_event(delta)`, `stream_error_event(code)`,
  `stream_failed_event(code)`

These prove this package's logic. They do not prove the wire: for that, drive
the real SDK over `httpx.MockTransport`, as `tests/test_sdk_protocol.py` and
`examples/06_identity_over_fake_transport.py` do.

`__version__` is the package version string.

## Invariants a reimplementation must preserve

1. No account, endpoint or deployment default ships in the code.
2. No token string is materialised; the SDK gets the callable.
3. An injected credential is never closed by this package, and neither is an
   injected client unless `owns_client=True` says so.
4. `store` defaults to False on convenience calls, and `respond`/`embed_raw`
   add nothing at all.
5. Provider content never reaches `str`, `repr` or `metadata()`.
6. An embedding target is configured, never inferred; cross-account calls
   refuse rather than 404, whether the deployment was configured or passed
   per call.
7. Vector order is verified against reported indexes, never assumed.
8. In-band stream failures raise; the underlying stream is closed on every
   exit path.
9. Every method on a closed client refuses with `category="config"`, at the
   call, not at first iteration.
10. Everything decidable before the socket opens is decided before the socket
    opens.
11. A conflicting caller option raises; none is silently dropped.
12. Interpreter- and loop-level control flow — `KeyboardInterrupt`,
    `SystemExit`, `GeneratorExit`, `asyncio.CancelledError` — is never caught,
    classified or retried.

## Out of scope

Deliberately absent, and adding any of them changes what this box is:

- API-key authentication, or any key fallback.
- An account/deployment catalogue, a model registry, or model-name mapping.
- Role assignment, resource creation, or any management-plane call.
- Agent hosting, tool execution, conversation state, or an evaluation harness.
- Caching, rate limiting, queueing, or cost accounting beyond reporting usage.
- Retry policy richer than the SDK's bounded retries.
