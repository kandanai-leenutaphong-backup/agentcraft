# managed-identity-model-clients

Reliable Azure OpenAI / AI Foundry access with identity already in place: a
reusable client, per-request Entra tokens, structured output, streaming that
notices when it fails, embeddings whose vectors are attached to the right
text, and one content-free error type.

Install the plugin for agent access, or install the copied Python package into your application.
Account coordinates and permission to spend model tokens are never inferred from installation.

## Why this exists

The four-line version of this in a tutorial works, and then fails in
production in the same four ways every time:

1. A token is fetched once and frozen into the client. The process serves 401s
   an hour later and a restart "fixes" it.
2. A streamed call returns HTTP 200 and fails three tokens later, in-band. The
   application reports a successful empty answer.
3. Batched embeddings are zipped against the inputs by position. The vectors
   are quietly attached to the wrong text and search gets subtly worse.
4. A provider exception carrying the prompt — often a content-filter excerpt
   of it — is logged verbatim.

Each of those is a small, known fix. This box is the small known fixes,
already made, with the tests that keep them made. Full list, symptom-first:
[GOTCHAS.md](GOTCHAS.md).

## Adoption boundary

**One import, one call: `connect(config)`.**

```python
from modelaccess import ModelConfig, connect

config = ModelConfig(
    endpoint="https://example-account.openai.azure.com/",   # or ModelConfig.from_env()
    deployment="my-chat-deployment",
    embedding_deployment="my-embedding-deployment",         # optional
)

with connect(config) as model:
    answer = model.ask("Name three uses for a paperclip.")
    print(answer.text, answer.metadata())
```

`connect()` returns the whole bundle — `respond`, `ask`, `parse`, `embed`,
`embed_raw`, `stream_text`, `stream_events`, `close` — so adopting this is one
call site, not a set of collaborating pieces to wire up. `connect_async()` is
the asyncio twin with the same surface.

Everything else in the public surface exists to serve that call: `ModelConfig`
to build its argument, the result and error types to read its answers, and the
offline doubles to test your own code around it. Nothing else needs to be
touched to adopt the box, and nothing in it reads global state at import time.

If you already have your own SDK client and want only the identity handling,
`token_provider_for(config)` is the smaller door.

## What you get

- **Identity that keeps working.** The token *callable* is handed to the SDK,
  which invokes it per request, so refresh is the credential's job. Managed
  identity in Azure, a developer sign-in locally, no branching in your code.
- **Sync and async**, as two classes rather than one class with an `is_async`
  flag, because the SDK genuinely awaits the credential in one and calls it in
  the other.
- **A raw door that is never closed.** `respond()` and `embed_raw()` forward
  arbitrary parameters, so tools, reasoning, `previous_response_id`, `include`,
  `background` and next quarter's parameter work without changing this box.
- **Structured output** via `parse(text_format=...)`, with model refusals
  modelled as an ordinary outcome rather than an exception.
- **Streaming with honest terminal states**: text deltas, or raw events, and an
  in-band `error`/`response.failed` becomes an exception instead of silence.
- **Embeddings that stay aligned**, scalar or batched, verified against the
  provider's reported indexes, targeted at an explicitly configured embedding
  deployment — including one on a different account.
- **Bounded time.** Finite default timeout, capped retries.
- **Errors you can log.** One `ModelError` with a stable `category`, HTTP
  status, `retryable`, `request_id` and the provider's short code — and no
  prompt, completion or provider body anywhere in it.

## MCP Plugin

Install `harness-data@harness` once in an Agent Plugins client. This package is independent of
the older `azure-llm-connectors` skill and does not replace it automatically. Its tool names use
the `modelaccess_` prefix to keep the two APIs distinct.

Call `modelaccess_status` to find `${PLUGIN_DATA}/managed-identity-model-clients/config.json`.
The client chooses the absolute base directory. It also holds this server's isolated virtual
environment and dependency cache; startup uses [uv.lock](uv.lock) and the `mcp` extra.
Python 3.11+ and uv must be on the agent host's PATH. No project-local pip install is needed for MCP.

Model calls are disabled until the operator configures real authorized targets, for example:

```json
{
  "endpoint": "https://your-account.openai.azure.com",
  "deployment": "your-chat-deployment",
  "embedding_deployment": "your-embedding-deployment",
  "allow_model_calls": true,
  "max_calls": 10,
  "max_output_tokens": 512
}
```

Restart after changing settings. Target hosts are trusted operator input; `allowed_hosts` can
pin both chat and embedding destinations. `modelaccess_ask` and `modelaccess_embed` expose only
bounded calls, not raw options or credentials. Failed attempts consume the per-process call
budget too; restarting resets it, so it is not a persistent spending quota. See
[CONTRACT.md](CONTRACT.md) for the complete adapter policy.

From this skill directory, reproduce its adapter check without a provider:

```bash
uv sync --locked --no-default-groups --no-install-project --extra mcp --extra dev
.venv/bin/python scripts/mcp_server.py --selftest
```

## Standalone Python Install

Copy the folder, then install it into the environment that will import it:

```bash
cp -r managed-identity-model-clients <your-repo>/
cd <your-repo>
python3 -m pip install ./managed-identity-model-clients
python3 -c "import modelaccess; print(modelaccess.__file__)"
```

An ordinary non-editable install. The last line should print a path under
`site-packages`, from any working directory, with no `PYTHONPATH` and no
`sys.path` edit — copying the folder alone does not achieve that, because the
importable package sits one level down inside it. Only `modelaccess` is
installed; `tests/`, `examples/` and `scripts/` stay in the copied folder.

Four runtime packages, declared in `pyproject.toml` and mirrored in
`requirements.txt`: `openai>=2` and `azure-identity>=1.19` do the work,
`aiohttp>=3.9` is the asyncio credential's transport, and `httpx>=0.27` arrives
with `openai` and is used directly by the fake-transport example. All are
imported lazily: code that injects its own client or token provider needs
none of them, which is how the offline tests and examples run.

`pydantic>=2` is the `structured` extra — `parse(text_format=…)` is the only
thing that needs it, and it arrives transitively with `openai` anyway:

```bash
python3 -m pip install './managed-identity-model-clients[structured]'
```

Configuration is environment-first and has no built-in account:

| Variable | Required | Meaning |
| --- | --- | --- |
| `MODEL_ENDPOINT` | yes | Account endpoint, in any shape you can paste |
| `MODEL_DEPLOYMENT` | yes | Deployment name (not the model family name) |
| `MODEL_EMBEDDING_DEPLOYMENT` | for `embed()` | Embedding deployment name |
| `MODEL_EMBEDDING_ENDPOINT` | if it is on another account | That account's endpoint |
| `MODEL_SCOPE` | no | Entra scope; defaults to the AI Services scope |
| `MODEL_TIMEOUT_SECONDS`, `MODEL_MAX_RETRIES` | no | Bounds |
| `MODEL_CLIENT_ID` | on multi-identity hosts | User-assigned managed identity client id |
| `MODEL_MAX_OUTPUT_TOKENS` | no | Cost guard for convenience calls |

The identity needs a data-plane role on the account (for Azure OpenAI, the
`Cognitive Services OpenAI User` role is the usual one). This box never grants
it, and never mutates any cloud resource.

## Verify

```bash
python3 tests/selftest.py                       # framework-free, offline
python3 examples/01_sync_call.py                # and 02…06
pip install -r requirements-dev.txt && python3 -m pytest tests
```

`tests/selftest.py` needs no test framework and runs offline. The pytest suite
drives the **real** SDK over `httpx.MockTransport`, so the identity claim
(provider re-invoked per request), the URL shape, retries, streaming SSE,
structured output and error classification are asserted against the SDK rather
than against a mirror of this implementation.

The probe with `--confirm-live`, direct library calls, and explicitly granted MCP calls can
contact the configured provider and spend tokens. Native tests, examples and MCP smoke checks
use injected offline clients and transports; those checks authorize no live model work.

## Failure model

- Everything decidable before the socket opens is decided there: endpoint
  shape, deployment name, scope, timeout, retry ceiling, batch size, embedding
  target. Those raise `ConfigError`, which is never retryable.
- Everything else becomes `ModelError` with a stable `category` and a
  `retryable` flag. Branch on `category`; do not parse the message.
- The provider's own exception is preserved as `__cause__`. Nothing it said is
  in the `ModelError` — but the `__cause__` chain still has it, so log
  `str(exc)` and `metadata()`, not a formatted traceback.
- `KeyboardInterrupt`, `SystemExit`, `GeneratorExit` and
  `asyncio.CancelledError` are not failures and are never translated:
  `asyncio.wait_for` raises `TimeoutError`, and a cancelled task stays
  cancelled.
- A streamed failure after HTTP 200 raises `category="stream"`. Partial text
  already yielded stays with the caller — it happened.
- A model refusal is not a failure: `ParsedResult.refused` is True and
  `parsed` is None.
- Read-back has no meaning here; this box only reads from the service. It
  performs no writes of any kind.

## Limits

Honest boundaries, not a roadmap:

- **No key authentication, ever.** Not a fallback, not a flag.
- **No account catalogue.** Endpoint and deployment are yours to supply, and a
  missing one is a startup refusal.
- **Token counting is the service's job.** Batch size is checked locally; token
  limits per input and per request are not, because that needs a tokenizer and
  a character count does not prove it.
- **No management plane.** No role assignment, no resource creation, no policy
  or network change. Adding one belongs in a different box.
- **The endpoint is trusted input.** `normalize_endpoint` checks URL shape, not
  destination: any https host is accepted and an Entra token is sent to it.
  Build `ModelConfig` from operator configuration only. If a value must come
  from data you do not control, pin `allowed_hosts=(...)` from something that
  data cannot edit. There is no default allowlist and no SSRF protection here.
- **An injected `client` or `credential` is yours.** `close()` releases only
  what this package built, unless you pass `owns_client=True`.
- **No agent runtime, tool executor, conversation store, cache, rate limiter or
  evaluation harness.**
- **Live behaviour is unverified here.** Every test and example in this folder
  is offline. Against a real account, run `scripts/probe.py --confirm-live` and
  read its output; that is the only evidence of live reachability this box can
  give you.
- **Threading**: the sync client is safe to share; the async one belongs to one
  event loop.

## Removal

Nothing to roll back — this box owns no state, writes nothing and provisions
nothing.

1. Delete the imports of `modelaccess` in your code (`grep -rn modelaccess`).
2. `python3 -m pip uninstall managed-identity-model-clients`.
3. Delete the folder.
4. Drop `openai`, `azure-identity`, `aiohttp` and `httpx` from your
   dependencies if nothing else uses them — uninstalling this package does not
   remove them.
5. Unset the `MODEL_*` variables.

Any role assignment you created for the identity is yours, was not created by
this box, and outlives it — remove it separately if it was only for this.

## Files

| Path | What it is |
| --- | --- |
| [SKILL.md](SKILL.md) | Agent-facing: decide, install, use, verify, remove |
| [CONTRACT.md](CONTRACT.md) | The spec — enough to reimplement without this folder |
| [GOTCHAS.md](GOTCHAS.md) | G1–G15, symptom first, cited from the code |
| `pyproject.toml` | Packaging metadata: installs `modelaccess`, nothing else |
| `modelaccess/` | The mechanism: config, auth, invoke, results, client, aio, doubles |
| `examples/` | Six runnable worked examples, all offline, all asserting |
| `tests/` | `selftest.py` (no framework), the pytest protocol suite, and the regression suite |
| `scripts/probe.py` | The only live path, opt-in, `--confirm-live` |
