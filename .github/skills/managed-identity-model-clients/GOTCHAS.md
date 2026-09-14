# Gotchas

Numbered, symptom-first. Each one cost somebody an afternoon. Code cites them
as `GOTCHAS.md, Gn`.

## G1 — No account is configured, and the failure looks like permissions

**Symptom.** A copied library "works" in one repository and answers 401 or 404
in another, against an account the new owner has never heard of.

**Cause.** A built-in default endpoint or deployment: one environment's address
compiled into the code, surviving the copy.

**Fix.** `ModelConfig` requires `endpoint` and `deployment`. `from_env()`
refuses with the exact variable name (`MODEL_ENDPOINT`, `MODEL_DEPLOYMENT`)
when either is unset. If you add a default, add it to your own composition
root, not to this package.

## G2 — Requests land on the wrong URL path

**Symptom.** 404 from a correct-looking endpoint, or requests going to
`/openai/responses` instead of `/openai/v1/responses`.

**Cause.** `httpx` resolves a relative request path against the base URL. A
base URL without a trailing slash discards its last path segment. Portal
endpoints, pasted hostnames and `/openai`-suffixed URLs are all different
shapes of the same account.

**Fix.** `normalize_endpoint()` accepts every shape and returns exactly
`https://host[/path]/openai/v1/`, with the trailing slash. It is idempotent,
runs in `ModelConfig.__post_init__`, and refuses http, embedded credentials,
query strings and `..` in the path.

## G3 — A streamed call "succeeds" and returns nothing

**Symptom.** `stream_text` yields no text, no exception is raised, and the
caller reports an empty but successful answer. The provider recorded a content
filter trip or a capacity failure.

**Cause.** A streaming Responses call returns HTTP 200 on its first byte. Any
later failure arrives *in-band*, as an SSE `error` or `response.failed` event.
Code that iterates deltas and ignores event types cannot see it.

**Fix.** `stream_delta()` raises `ModelError(category="stream")` on both event
types, carrying the provider's short error code and nothing else. `respond()`
and `stream_events()` deliberately do not: holding the raw feed means owning
its semantics.

## G4 — Everything works for an hour, then serves 401 until restarted

**Symptom.** A long-lived process authenticates perfectly and then fails
continuously, with a restart as the only fix.

**Cause.** A token string materialised once and handed to the client:
`api_key=credential.get_token(scope).token`. Tokens expire; a string does not
refresh.

**Fix.** Hand the SDK the *callable*. It invokes it on every request, so the
credential owns refresh. This package never materialises a token string; the
claim is proven in `tests/selftest.py` and `tests/test_sdk_protocol.py` by
counting provider invocations across requests through the real SDK.

## G5 — `TypeError: object str can't be used in 'await' expression`

**Symptom.** The async client fails before any request is made, or a coroutine
object is placed in an HTTP header.

**Cause.** `OpenAI` *calls* its token provider and expects `str`;
`AsyncOpenAI` *awaits* it and expects a coroutine. The sync and asyncio
identity modules return different things.

**Fix.** Two classes and two provider functions. Use `connect()` with a sync
credential and `connect_async()` with an asyncio one. The mismatch is
reproduced deliberately in `tests/test_sdk_protocol.py`.

## G6 — An embedding call 404s and the deployment name looks fine

**Symptom.** `embeddings.create` returns 404 against an account that
demonstrably hosts that model.

**Cause.** Two separate traps. A chat deployment cannot serve embeddings, and
falling back to it produces a 404 that reads like a typo. And a deployment is
reachable *only through the endpoint of the account that owns it* — embedding
deployments frequently live on a second account.

**Fix.** `embedding_deployment` is configured explicitly and never inferred.
When it lives elsewhere, set `embedding_endpoint` too; `embed()` then refuses
to send the call to the wrong account and points you at
`connect(embedding_config(config))`, which is the second client to build.

## G7 — A refusal is reported as a crash, or as a valid empty object

**Symptom.** Either an exception with no provider error in it, or a structured
result whose fields are silently empty.

**Cause.** A model refusal is a *successful* call whose answer is "no". The
SDK puts it in `output[].content[].refusal` and leaves `output_parsed` None.

**Fix.** `ParsedResult.parsed` is None and `ParsedResult.refused` is True.
Nothing raises. The refusal *text* is available on `.refusal` but is kept out
of `metadata()` and `__repr__`, because a refusal can quote what it refused.

## G8 — Vectors are attached to the wrong text

**Symptom.** Search results are subtly wrong. Nothing errors. Ranking looks
plausible but is off by one, or arbitrarily permuted.

**Cause.** Assuming `response.data[i]` corresponds to `input[i]`. The
correspondence is carried by each item's `index` field, and a batched response
is not obliged to arrive in order.

**Fix.** `EmbeddingResult.from_response` places every vector by its reported
index and raises rather than returning anything it cannot align: wrong count,
duplicate index, out-of-range index, non-integer index, ragged widths,
non-finite components, base64 payloads. `.vector` refuses on a batch instead
of returning the first of twelve.

## G9 — Closing a client breaks the caller's credential, or the caller's client

**Symptom.** After one component shuts down, an unrelated component's calls
fail with a closed-transport error.

**Cause.** A credential — or an HTTP client — passed in by the caller, closed by
the callee. `client=` is a first-class injection seam, so two connectors
sharing one `OpenAI` object is a supported arrangement, and one of them
closing it is not.

**Fix.** Ownership is explicit and symmetric. `close()`/`aclose()` close the
HTTP client only when this package built it (`owns_client` defaults to
`client is None`) and the credential only when it built that. Pass
`owns_client=True` to hand over the lifecycle deliberately. A close that
raises is logged, never propagated — shutdown must not fail.

## G10 — Sockets leak when a stream is abandoned or fails mid-flight

**Symptom.** Connection-pool exhaustion, or "Unclosed client session" at exit,
in a process that stops consuming streams early.

**Cause.** Two different things. A generator that is dropped rather than
exhausted only runs its `finally` when closed; and an *async* generator
suspended inside another async generator is not unwound synchronously when the
outer one raises — it waits for the garbage collector.

**Fix.** Both iterators close the underlying stream in a `finally`, and the
async `stream_text`/`stream_events` explicitly `aclose()` the inner generator,
so an in-band failure releases the socket immediately. Asserted in
`tests/selftest.py` and in `examples/02_async_streaming.py`.

## G11 — Prompts and completions end up in logs and error trackers

**Symptom.** An error page, a log aggregator or an exception tracker contains
model input — often a content-filter excerpt, which is by definition the most
sensitive part of it.

**Cause.** `openai.APIStatusError` carries the provider's response object and
decoded body. `str(exc)` renders them.

**Fix.** `classify()` builds a `ModelError` from the exception *type*, HTTP
status, short error code and request id only. `str()`, `repr()` and
`metadata()` on every result are content-free; the original exception stays
reachable as `__cause__` for a debugger.

That last clause is the sharp edge: the **`__cause__` chain still carries the
provider's text**. A handler that logs `str(exc)` is safe; one that logs a
formatted traceback, or calls `logging.exception`, is not. Log the projections,
not the chain.

## G12 — Prompts are retained server-side that nobody agreed to retain

**Symptom.** A data-residency review discovers stored conversations.

**Cause.** `store` defaults to True on the Responses API.

**Fix.** `ask()`, `parse()` and `stream_text()` send `store=False` unless the
caller sets it. `respond()` sends exactly what you give it and adds nothing —
that is the point of the raw door.

## G13 — One wedged deployment wedges the worker

**Symptom.** A request hangs for ten minutes. Under load, a pool of workers
disappears one at a time.

**Cause.** The SDK's default timeout is ten minutes, and its default retry
behaviour re-queues into a deployment that is already at capacity.

**Fix.** `timeout_secs` defaults to 120 and must be finite and positive;
`max_retries` defaults to 2 and is capped at 10. Beyond that a "retry"
strategy is a queue and belongs in the caller, not in a client library.

## G14 — `wait_for` does not time out, and a cancelled task reports as failed

**Symptom.** `asyncio.wait_for(client.ask(...), timeout=…)` raises a
`ModelError` instead of `TimeoutError`. A task that was cancelled finishes with
an exception rather than as cancelled, so a task group or a shutdown path
hangs, mis-reports, or a retry loop keyed on `except ModelError` retries a
request the caller already gave up on.

**Cause.** `asyncio.CancelledError` has inherited from `BaseException` since
Python 3.8, so `except BaseException` around an await point swallows
cancellation. The synchronous twin of the same construct swallows
`KeyboardInterrupt` and `SystemExit`.

**Fix.** Both `_translate` helpers catch `Exception`, never `BaseException`.
Cancellation, Ctrl-C, `SystemExit` and `GeneratorExit` propagate unchanged, and
the `finally` blocks that release streams still run. Asserted against the real
`AsyncOpenAI` client over `httpx.MockTransport` in
`tests/test_regressions.py`, and framework-free in `tests/selftest.py`.

## G15 — A configured endpoint is where your token goes

**Symptom.** Nothing, until an endpoint value that came from somewhere editable
sends an Entra bearer token to a host the operator never chose.

**Cause.** `normalize_endpoint` refuses http, embedded credentials, query
strings and `..`, which *looks* like a security control. It is not one: it
validates URL shape. Any https host is accepted, and the token for
`credential_scope` is then sent there.

**Fix.** Treat `endpoint`, `embedding_endpoint` and `credential_scope` as
trusted operator configuration — environment, deployment template, secret
store. Do not build a `ModelConfig` from a tenant record, a request field or a
user-editable settings row. When a value must come from such a source, set
`allowed_hosts=(...)` from something that source cannot edit; construction then
refuses any endpoint outside it. There is no default allowlist, because this
package ships no account catalogue, and a fake one would be worse than none.
