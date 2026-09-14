# CONTRACT

The public surface of `azllm`, and what each part guarantees. Anything not listed here is
private and may change: import from `azllm`, not from `azllm._invoke`.

## Entry points

| Callable | Returns | Notes |
| --- | --- | --- |
| `connect(config=None, *, credential=None, token_provider=None, client=None)` | `FoundryConnector` | `config` defaults to `FoundryConfig.from_env()`. A caller-supplied `credential` is **not** closed by the connector. |
| `connect_async(...)` | `AsyncFoundryConnector` | `credential` must come from `azure.identity.aio`; `token_provider` must be a coroutine factory. |
| `token_provider_for(config)` | `Callable[[], str]` | For callers building their own `OpenAI` client. |
| `async_token_provider_for(config)` | `Callable[[], Awaitable[str]]` | Same, for `AsyncOpenAI`. |
| `embedding_config(deployment=DEFAULT_EMBEDDING_DEPLOYMENT, *, endpoint=None, base=None, **overrides)` | `FoundryConfig` | Endpoint of the account that **owns** that embedding deployment. Unknown name without `endpoint=` raises `ConfigError`. |

`client=` bypasses all credential and client construction. It is the injection point the
entire test suite uses, which is why the suite needs no cloud.

## `FoundryConfig`

Frozen dataclass. All validation happens in `__post_init__`, so an invalid config cannot
exist.

| Field | Default | Rejects |
| --- | --- | --- |
| `endpoint` | empty; caller must configure it | empty, non-https, embedded credentials, query/fragment, `..`, whitespace, missing host |
| `deployment` | `chat` | empty, >64 chars, characters outside `[A-Za-z0-9-_.]` |
| `credential_scope` | `https://ai.azure.com/.default` | not https, not ending `/.default` |
| `timeout_secs` | `120.0` | non-numeric, ≤0, NaN, inf, `bool` |
| `max_retries` | `2` | non-int, <0, >10, `bool` |
| `managed_identity_client_id` | `None` | blank string (use `None`) |
| `default_max_output_tokens` | `None` | non-int, ≤0 |

- `base_url` — the normalised `https://host[/path]/openai/v1/` string handed to the SDK.
  Normalisation is idempotent.
- `account_host` — hostname only; safe to log.
- `with_overrides(**changes)` — validated copy; unknown field names raise `ConfigError`.
- `from_env(prefix="AZURE_LLM_", env=None)` — reads `ENDPOINT`, `DEPLOYMENT`, `SCOPE`,
  `TIMEOUT_SECONDS`, `MAX_RETRIES`, `CLIENT_ID`, `MAX_OUTPUT_TOKENS`. Blank values are
  treated as unset. Raises `ConfigError` when any key-auth variable is present.

There is no API key field. Entra-only access is the library's policy, regardless of
whether an operator's account also permits keys.

## Connector methods

Identical on `FoundryConnector` and `AsyncFoundryConnector`; the async ones are awaited,
and the async stream methods are async iterators.

| Method | Returns | Defaults it applies |
| --- | --- | --- |
| `respond(**options)` | provider response, untouched | `model` only |
| `ask(prompt, *, deployment=None, instructions=None, **options)` | `LlmResult` | `store=False`, `input`, `model`, config output cap |
| `parse(prompt, *, text_format, deployment=None, instructions=None, **options)` | `ParsedResult` | same as `ask` |
| `embed(input, /, *, deployment=None, dimensions=None, **options)` | `EmbeddingResult` | `model` (embedding default), `input` |
| `embed_raw(**options)` | provider response, untouched | `model` (embedding default) only |
| `stream_text(prompt, ...)` | iterator of `str` deltas | same as `ask`, plus `stream=True` |
| `stream_events(**options)` | iterator of raw events | `model`, `stream=True` |
| `close()` / `aclose()` | — | idempotent |

Properties: `config`, `client` (the raw SDK client), `token_provider`.

Guarantees:

- **Pass-through.** Every keyword not named above reaches `responses.create` unchanged, so
  `tools`, `previous_response_id`, `reasoning`, `include`, `metadata`, `background`,
  `temperature` and future parameters are never blocked.
- **Reserved options.** `model`, `stream` and `input` are owned by the convenience methods
  and raise `ConfigError` if passed to them. Use `respond`/`stream_events` for full control.
  `embed` reserves `model`, `input` and `dimensions`; `embed_raw` reserves nothing.
- **Per-call override.** `deployment=` overrides the config for one call and does not
  mutate the connector. A blank override raises `ConfigError`.
- **`store` defaults to `False`** on `ask`, `parse` and `stream_text`; `respond` and
  `stream_events` default nothing.
- **Caching.** The SDK client and the token provider are built once, in `__init__`, and
  reused for the connector's lifetime.
- **Closed connectors** raise `LlmError(category="config", retryable=False)` from every
  method and from `.client`, eagerly — including the streaming methods, which validate
  before returning their iterator.

## Embeddings

`embed` accepts one string or any iterable of strings. An iterable is **copied before
validation**, so a generator is consumed exactly once and a list mutated afterwards cannot
desynchronise the result from the text that was sent.

The deployment is resolved as: the per-call `deployment=`, else `config.deployment` **when
that is itself a known embedding deployment**, else `DEFAULT_EMBEDDING_DEPLOYMENT`
(`text-embedding-3-large`). A chat `config.deployment` is never used for embeddings.

Rejected before any request is sent, as `ConfigError`:

| Check | Rule |
| --- | --- |
| input type | `str`, or an iterable of `str`; `bytes` and mappings are refused |
| input text | non-empty and not whitespace-only, per entry |
| batch size | 1 … 2048 entries |
| `dimensions` | positive `int` or `None`; `bool` is not an `int` here |
| reserved options | `model`, `input`, `dimensions` cannot be passed as `**options` |

**Not** checked locally: token counts. Each input may be at most 8192 tokens and a request
at most 300,000 tokens in aggregate. Proving that needs a tokenizer, a character count does
not imply it, and this package will not add the dependency — the service enforces both and
reports them as `LlmError(category="bad_request", status_code=400)`. The limits are exported
as `MAX_EMBEDDING_INPUTS`, `MAX_TOKENS_PER_INPUT`, `MAX_TOKENS_PER_REQUEST`.

`EmbeddingResult`: `vectors` (a tuple of tuples of `float`, in input order), `deployment`,
`model`, `usage`, `raw`, plus `count`, `dimensions`, `vector` and `metadata()`.

- `vector` returns the single vector and raises `ConfigError` for any other count — reading
  `vectors[0]` on a batch is a silent way to embed twelve documents and index the first.
- Alignment is verified, not assumed. A response with a missing, duplicated or out-of-range
  index, the wrong number of vectors, vectors of differing length, an empty vector, or a
  non-numeric / non-finite component raises `LlmError(category="unknown", retryable=False)`
  with a structural message. Integer components are coerced to `float`; `bool` is refused.
- Vectors returned as base64 strings (`encoding_format="base64"`) raise `ConfigError`
  naming the cause; use `embed_raw` to handle them.
- `metadata()` and `__repr__` carry deployment, model, count, dimensions and usage — never
  a vector and never the input.

## Results

`LlmResult`: `text`, `response_id`, `deployment`, `model`, `status`, `usage`, `raw`,
`complete`, `input_tokens`, `output_tokens`, `metadata()`.

`ParsedResult`: `parsed` (validated instance, or `None` on refusal or truncation), plus the
same fields.

`metadata()` is the log-safe projection: identifiers, status, counts and `text_chars` — never
the text. `__repr__` reports `text_chars`, not the text.

## Errors

Every failure leaves this library as `LlmError`; `ConfigError` is the `category="config"`
subclass. The exported `ErrorCategory` literal type enumerates the categories below.

| Category | Cause | `retryable` |
| --- | --- | --- |
| `config` | invalid configuration, closed connector | False |
| `auth` | 401, 403, credential could not issue a token | False |
| `not_found` | 404 — usually a model name that is not a deployment name | False |
| `bad_request` | 400, 422, other 4xx | False |
| `rate_limit` | 429 | True |
| `timeout` | client-side deadline | True |
| `connection` | DNS, TLS, reset | True |
| `server` | 5xx | True |
| `stream` | `error` or `response.failed` event mid-stream | False |
| `unknown` | anything else | False |

Fields: `category`, `status_code`, `retryable`, `request_id`, `deployment`, `code`,
`message`. The provider's message and body are never included; `__cause__` preserves the
original exception.

## Constants

`ACCOUNT_NAME`, `SECONDARY_ACCOUNT_NAME`, `DEFAULT_ENDPOINT`, `SECONDARY_ENDPOINT`,
`DEFAULT_SCOPE`, `DEFAULT_DEPLOYMENT`, `HIGHEST_CAPACITY_DEPLOYMENT`,
`DEFAULT_EMBEDDING_DEPLOYMENT`, `EMBEDDING_DEPLOYMENT` (its 1.0 name, same string),
`KNOWN_DEPLOYMENTS` and `EMBEDDING_DEPLOYMENTS` (immutable mappings of `DeploymentProfile`),
`known_deployment(name)`, `embedding_deployment(name)`, `MAX_EMBEDDING_INPUTS`,
`MAX_TOKENS_PER_INPUT`, `MAX_TOKENS_PER_REQUEST`, `DEFAULT_TIMEOUT_SECS`,
`DEFAULT_MAX_RETRIES`, `ENV_PREFIX`, `normalize_endpoint`.

`DeploymentProfile` carries `name`, `model`, `model_version`, `capacity`, `kind`, `account`
and `endpoint`. The portable copy contains no account inventory. Account/endpoint constants
and `HIGHEST_CAPACITY_DEPLOYMENT` are empty. The two public embedding names retain their
type, with blank version/coordinates and zero capacity meaning "not observed".

Unknown deployment names remain accepted. `embedding_config` requires `endpoint=` in this
distribution; it cannot infer a deployment's owner from a model family. `DEFAULT_DEPLOYMENT`
is the neutral label `chat`, not a claim that any account has that deployment.

## MCP Adapter

The stdio server uses the official MCP SDK and validates tool inputs against JSON Schema.
Configuration enters through a JSON file passed with `--config`, not ambient service variables.
Unknown configuration fields, including credential fields, are refused without echoing values.

| Tool | Input | Result |
| --- | --- | --- |
| `azllm_status` | empty object | configuration, fixture marker, grants, remaining call budget, config path; no network |
| `azllm_ask` | `prompt`; optional `max_output_tokens` | text plus the library's result metadata and fixture marker |
| `azllm_embed` | `texts`; optional `dimensions` | ordered vectors plus embedding metadata and fixture marker |

Operator settings: `endpoint`, `deployment`, `embedding_endpoint`, `embedding_deployment`,
optional `managed_identity_client_id`, `allow_model_calls` (default false), `max_calls`
(default 10, maximum 1000), `max_output_tokens` (default 512, maximum 4096),
`max_input_characters` (default 32000, maximum 64000), and `timeout_secs` (default 30, maximum 120).
An omitted embedding endpoint uses the configured chat endpoint, never a guessed second account.

Each accepted model attempt consumes one call from the per-process budget before awaiting the
provider. Failed attempts consume their reservation too. A restart resets the budget; this is not
a persistent billing quota. SDK retries are disabled in this adapter. Model calls require the
operator grant and target, not a tool argument. Caller-supplied deployment, endpoint and grant
overrides are absent from the schemas. `ask` retains `store=False`.

Embedding batches are limited to 64 nonempty strings, each at most 8192 characters, within the
aggregate character grant. Requested dimensions are 1-3072. These are adapter bounds, not token
counts or a promise that every model supports those dimensions. Provider token limits still apply.

Tool failures set MCP `isError`; errors contain stable categories, not provider messages or inputs.
`--fixtures` uses injected fake clients and marks results; it is not part of the installed launch
command. HTTP hosting, streaming MCP output, arbitrary Responses options and tool-driven grants
are not exposed. Use the Python API for those supported library features.

## Logging

Logger name `azllm.connector` / `azllm.aio`, level `DEBUG` only. Emits host, deployment,
timeout, retry count, response id, status, token counts, vector counts and text *lengths*.
Never a prompt, a completion, a parsed object, an embedding input, a vector, or a token.
