# GOTCHAS

Each entry is a trap that costs an afternoon, what it looks like, and where this library
closes it. Verified against `openai` 3.6.0 and `azure-identity` 1.25.3 in August 2026.

---

## G1 — `model` is the deployment name, not the model name

**Symptom.** `NotFoundError: 404` for a model you can see in the portal.

**Cause.** On Azure OpenAI the `model` field carries the *deployment* name. `"gpt-5.6"` is
a model; `"chat"` is the deployment of it on this account. The mapping lives in the
resource, not in the SDK.

**Here.** Configure the actual deployment name. `chat` is a neutral example label, not an
inventory claim. `LlmError(category="not_found")` identifies the failure without repeating
provider content.

---

## G2 — a frozen token authenticates for exactly one hour

**Symptom.** A long-lived process works perfectly, then serves 401s until it is restarted.

**Cause.** The widespread sample pattern captures a token string at startup:

```python
token = credential.get_token(SCOPE).token
client = OpenAI(base_url=..., api_key=token)     # expires in ~60 minutes
```

**Here.** The OpenAI SDK accepts `api_key` as a callable and re-invokes it on every request
(`openai/_client.py`: `self.api_key = self._api_key_provider()`). This library passes the
callable from `get_bearer_token_provider` and never materialises a token string.
`tests/test_auth_and_client.py::test_a_frozen_token_is_never_introduced` fails if that ever
changes.

---

## G3 — the async client *awaits* the token provider

**Symptom.** `TypeError: object str can't be used in 'await' expression`, or an
`Authorization` header containing `<coroutine object ...>`.

**Cause.** `OpenAI` calls `provider()`; `AsyncOpenAI` calls `await provider()`.
`azure.identity.get_bearer_token_provider` returns a sync callable and
`azure.identity.aio.get_bearer_token_provider` returns a coroutine factory. They are not
interchangeable.

**Here.** Two connector classes, two credential modules. `connect_async` documents that its
`credential` must come from `azure.identity.aio`.

---

## G4 — the trailing slash on the base URL is load-bearing

**Symptom.** Every request 404s, on an endpoint that is visibly correct.

**Cause.** `httpx` resolves a relative request path against the base URL. With
`.../openai/v1` the last segment is replaced, so `responses` is requested at
`.../openai/responses`. With `.../openai/v1/` it is not.

**Here.** `normalize_endpoint` always produces the trailing slash, accepts every shape a
human pastes (bare host, portal endpoint, `.../openai`, `.../openai/v1`), and is
idempotent.

---

## G5 — an API key on this account cannot work, ever

**Symptom.** 401 with a key that was copied correctly from the portal.

**Cause.** The account has `disableLocalAuth=true`. Keys are refused at the service. Worse,
the OpenAI SDK reads `OPENAI_API_KEY` from the environment implicitly, so a stale variable
silently changes what is sent.

**Here.** There is no key field, and `FoundryConfig.from_env` raises `ConfigError` when
`AZURE_LLM_API_KEY`, `AZURE_LLM_KEY`, `AZURE_OPENAI_API_KEY` or `OPENAI_API_KEY` is set —
naming the variable, never printing its value.

---

## G6 — Owner on the subscription does not grant inference

**Symptom.** 403 for an identity that can create and delete the account.

**Cause.** Control-plane roles (Owner, Contributor) do not confer data-plane access. The
data plane needs **Cognitive Services OpenAI User** (or Cognitive Services Contributor) on
the account.

**Also.** A new role assignment takes minutes to propagate, and an already-issued token does
not gain it — `az login` again after granting.

**Here.** The `auth` category message names the role. `scripts/probe.py` exits `3` for it.

---

## G7 — a streaming call returns 200 and can still fail

**Symptom.** A truncated or empty answer, reported as success.

**Cause.** The HTTP status is decided at the first byte. Content-filter trips, capacity
failures and model errors arrive *inside* the stream as `error` or `response.failed`
events. Loops that collect `response.output_text.delta` and ignore every other event
cannot see them.

**Here.** `stream_text` inspects every event and raises `LlmError(category="stream")`,
carrying the provider's short code (`content_filter`, `server_error`) and no message.
`stream_events` deliberately does not — raw feed, caller's semantics.

---

## G8 — provider error messages quote the prompt

**Symptom.** Prompt fragments in application logs, error trackers and 500 pages.

**Cause.** `openai.APIStatusError` carries `.response` and `.body`, and content-filter
errors quote the offending input. `str(exc)` in a log line publishes it.

**Here.** `classify()` keeps the exception type, HTTP status, short error code and
`x-request-id`, and nothing else; the original exception survives as `__cause__` for a
debugger. `LlmResult.__repr__` and `.metadata()` report `text_chars`, not text.

---

## G9 — `previous_response_id` needs `store=True` on the *earlier* turn

**Symptom.** 404 on the response id when chaining.

**Cause.** Server-side conversation state exists only if the referenced response was
stored. This library defaults `store=False` on convenience calls, because retaining prompts
and completions on the service is a data-residency decision.

**Here.** Pass `store=True` explicitly on the turn you intend to reference, or use
`respond()` which defaults nothing.

---

## G10 — building a client per request costs more than the call

**Symptom.** Latency dominated by TLS handshakes; occasional token-acquisition spikes.

**Cause.** A new `OpenAI` object means a new connection pool and a new credential chain.

**Here.** `FoundryConnector` builds both once and is safe to share across threads. Build one
per process at the composition root.

---

## G11 — the async credential leaks a transport if it is not closed

**Symptom.** `Unclosed client session` at interpreter exit; connections held open.

**Cause.** `azure.identity.aio` credentials and `AsyncOpenAI` own async transports that
must be closed explicitly.

**Here.** `aclose()` and `async with`. Ownership is tracked: a credential you passed in is
never closed for you, because you may still be using it.

---

## G12 — the SDK's default timeout is 10 minutes

**Symptom.** A wedged deployment wedges a worker; a request queue backs up behind it.

**Here.** `timeout_secs` defaults to 120 and must be positive and finite; `max_retries`
defaults to 2 and is capped at 10, because retrying a 429 harder deepens the queue. For
fan-out, provision and select appropriate capacity rather than increasing retries blindly.

---

## G13 — a deployment is reachable only through its own account's endpoint

**Symptom.** `text-embedding-3-small` 404s on an endpoint where
`text-embedding-3-large` works, with an error that reads like the name is misspelled.

**Cause.** The embedding deployments can be on different accounts. There is no cross-account
routing and no fallback — the endpoint
decides which resource is asked, and that resource has never heard of the other's
deployment.

**Here.** Supply `endpoint=` to `embedding_config`. The portable catalogue intentionally
contains no owning accounts. Missing coordinates raise `ConfigError`; the helper still preserves
the base config's timeout and identity settings.

---

## G14 — the embedding default must not be the chat deployment

**Symptom.** `embed()` 404s on a connector that answers `ask()` perfectly.

**Cause.** The obvious implementation defaults `model` to `config.deployment`, which on a
connector built for chat is `chat`. A chat deployment cannot serve
`embeddings.create`.

**Here.** `embed()` defaults to `DEFAULT_EMBEDDING_DEPLOYMENT` and only honours
`config.deployment` when that is itself a known embedding deployment — which is what makes
`connect(embedding_config(...)).embed(...)` route correctly while a chat connector still
embeds without being reconfigured.

---

## G15 — `data` order is not input order

**Symptom.** A batch embedding job that scores well on average and returns nonsense for
individual documents.

**Cause.** The response carries an `index` field per item precisely because the array order
is not contractual. Code that zips `data` against the input list is correct until the day
it is not, and the failure is silent: every vector is a valid vector, just of the wrong
text.

**Here.** `EmbeddingResult.vectors` is built by placing each item at its declared `index`.
A duplicate index, an out-of-range index, a missing one, a count that does not match the
inputs, vectors of differing length, or a non-finite component raises
`LlmError(category="unknown")` rather than returning a plausible, wrong answer.

---

## G16 — token limits are not character limits

**Symptom.** A 400 from a request that passed every local check.

**Cause.** Each input is capped at 8192 tokens and a request at 300,000 tokens in
aggregate. Tokens are not characters, and no character count proves either bound.

**Here.** Only what is decidable from the values in hand is enforced locally — string type,
non-empty text, and at most 2048 inputs per request. The token limits are documented
(`MAX_TOKENS_PER_INPUT`, `MAX_TOKENS_PER_REQUEST`), left to the service, and surface as
`LlmError(category="bad_request", status_code=400)`. Adding a tokenizer dependency to
guess at them locally would be a second, differently-wrong opinion.

## G17 - A copied personal endpoint is not a portable default

**Symptom.** A copied library needs a credential for an account the new operator does not own.
**Cause.** The input package included one operator's account and deployment inventory.
**Fix.** This copy leaves account coordinates empty and requires the endpoint explicitly.
`tests/selftest.py` checks that a missing endpoint refuses before constructing a client.

## G18 - Installing MCP must not authorize model spend

**Symptom.** A caller can discover inference tools before any operator has approved model calls.
**Cause.** Tool discovery describes capabilities; it is not a billing or authorization decision.
**Fix.** The MCP adapter denies by default and reserves each authorized attempt against a
per-process budget. Its SDK smoke test proves refusal, bounded fixture results and exhaustion.
