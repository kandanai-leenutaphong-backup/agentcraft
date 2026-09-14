# azllm

Azure AI Foundry / Azure OpenAI access with identity, timeouts and a failure model
already in place. Entra only. The portable copy contains no private account defaults.

```python
from azllm import FoundryConfig, connect

config = FoundryConfig(endpoint="https://your-account.openai.azure.com", deployment="your-chat-deployment")
with connect(config) as llm:
    print(llm.ask("Name three uses for a paperclip.").text)
```

That example requires an authorized real target and can incur inference charges. It uses
`store=false`, a finite deadline and sanitized failures. For a no-network worked example,
run [examples/offline.py](examples/offline.py). The injection boundary is
`connect(config, client=...)` or its async equivalent; no consumer types enter the library.

---

## Install

```bash
uv sync --locked --no-default-groups --no-install-project --extra mcp --extra dev
.venv/bin/python tests/selftest.py
```

Requires Python 3.11+ and uv. Library dependencies remain `openai`, `azure-identity` and
`aiohttp`; structured output uses Pydantic. MCP adds the official `mcp` SDK. Versions are
locked in [uv.lock](uv.lock). A Python application can install this directory with pip.

---

## Deployment Coordinates

Configure the account and actual deployment names at the composition root. `FoundryConfig()`
and `connect()` without an endpoint or environment setting now refuse before building a client.
The label `chat` is a neutral default, not an inventory claim. The public embedding names retain
their model type, but neither carries an owning account. Pass `endpoint=` to `embedding_config`.
There is no cross-account fallback, live inventory, or capacity guarantee in this skill.

### RBAC

The identity needs a data-plane role on **each** account it calls — **Cognitive Services
OpenAI User** (or Contributor). Owner on the subscription is *not* sufficient by itself:
control-plane roles do not grant data-plane inference.

```bash
az role assignment create \
  --assignee "<objectId>" \
  --role "Cognitive Services OpenAI User" \
    --scope "/subscriptions/<sub>/resourceGroups/<group>/providers/Microsoft.CognitiveServices/accounts/<account>"
```

Role assignments take a few minutes to propagate, and a token minted before the assignment
does not gain it. A 401/403 immediately after granting means "wait, then re-login".

---

## Configuration

`FoundryConfig` is frozen and validated at construction. The Python API may read explicitly
configured environment variables; the MCP adapter instead receives its own JSON settings file.

```python
from azllm import FoundryConfig

cfg = FoundryConfig(endpoint="https://your-account.openai.azure.com", deployment="your-chat-deployment")
cfg = FoundryConfig.from_env()                          # requires AZURE_LLM_ENDPOINT
cfg = cfg.with_overrides(deployment="chat-batch", timeout_secs=30)
cfg.base_url        # normalized HTTPS endpoint ending in /openai/v1/
cfg.account_host    # hostname only
```

| Environment variable | Field | Default |
| --- | --- | --- |
| `AZURE_LLM_ENDPOINT` | `endpoint` | required; no account default |
| `AZURE_LLM_DEPLOYMENT` | `deployment` | `chat` |
| `AZURE_LLM_SCOPE` | `credential_scope` | `https://ai.azure.com/.default` |
| `AZURE_LLM_TIMEOUT_SECONDS` | `timeout_secs` | `120.0` |
| `AZURE_LLM_MAX_RETRIES` | `max_retries` | `2` |
| `AZURE_LLM_CLIENT_ID` | `managed_identity_client_id` | unset |
| `AZURE_LLM_MAX_OUTPUT_TOKENS` | `default_max_output_tokens` | unset |

The prefix is a parameter: `FoundryConfig.from_env(prefix="MYAPP_")`.

**Endpoint normalisation.** A bare hostname, the portal endpoint, `.../openai`, or
`.../openai/v1` all normalise to the one base URL ending in `/openai/v1/`. The trailing
slash is load-bearing: `httpx` resolves relative request paths against the base URL and
drops the last segment without it.

**Rejected at construction**, not at first call: empty or non-`https` endpoints, endpoints
with embedded credentials, a query string or a fragment (including `?api-key=`), `..` in
the path, deployment names outside Azure's alphabet or over 64 characters, non-positive or
non-finite timeouts, retry counts outside 0–10, scopes not ending in `/.default`, blank
managed identity client ids.

**There is no API key field, and `from_env` refuses to run** when `AZURE_LLM_API_KEY`,
`AZURE_LLM_KEY`, `AZURE_OPENAI_API_KEY` or `OPENAI_API_KEY` is set. The account rejects
keys; accepting one here would only relocate the 401 and persuade someone to put a secret
in a config file first.

---

## Usage

### Sync

```python
from azllm import connect

llm = connect()                              # build once per process, share it
result = llm.ask("Summarise the CAP theorem in one sentence.")

result.text            # the answer
result.response_id     # chain the next turn with previous_response_id
result.deployment      # chat
result.status          # completed | incomplete | failed
result.usage           # {"input_tokens": ..., "output_tokens": ..., ...}
result.raw             # the untouched provider response
result.metadata()      # the projection that is safe to log
llm.close()
```

Per-call deployment override, instructions, and any Responses API option:

```python
llm.ask(
    "Draft a release note.",
    deployment="chat-batch",
    instructions="Be terse.",
    max_output_tokens=300,
    temperature=0.2,
)
```

### Async

```python
import asyncio
from azllm import connect_async

async def main():
    async with connect_async() as llm:
        first, second = await asyncio.gather(
            llm.ask("One fact about tin."),
            llm.ask("One fact about zinc."),
        )
        print(first.text, second.text)

asyncio.run(main())
```

### Streaming

```python
for chunk in llm.stream_text("Explain backpressure."):
    print(chunk, end="", flush=True)
```

```python
async for chunk in llm.stream_text("Explain backpressure."):
    print(chunk, end="", flush=True)
```

A streamed call returns HTTP 200 on the first byte and can still fail three tokens later.
`stream_text` inspects every event and raises `LlmError(category="stream")` on `error` and
`response.failed`, so a truncated answer is never reported as a short one. Use
`stream_events(...)` for the raw feed (tool-call deltas, reasoning summaries, usage) —
that one hands back events unfiltered, error events included.

### Embeddings

```python
from azllm import connect, embedding_config

llm = connect()                                  # a chat connector embeds too
result = llm.embed("the quick brown fox")        # text-embedding-3-large

result.vector          # tuple[float, ...] — only defined for a single input
result.dimensions      # 3072
result.count           # 1
result.usage           # {"prompt_tokens": ..., "total_tokens": ...}
result.metadata()      # safe to log: no input, no vectors
```

The default is `text-embedding-3-large`, **never** the connector's chat deployment. A
batch comes back in input order, verified against the provider's `index` field rather than
assumed from array order:

```python
batch = llm.embed(["first document", "second document", "third"])
batch.count            # 3
batch.vectors[1]       # the vector for "second document", guaranteed
batch.vector           # ConfigError — refuses to guess which one you meant
```

Any iterable works and is copied before anything else happens, so a generator is consumed
exactly once and a list mutated afterwards cannot desynchronise the result:

```python
llm.embed(line.strip() for line in open("corpus.txt") if line.strip())
```

Shorter vectors, and any other embeddings parameter:

```python
llm.embed("index me", dimensions=256, user="analyst-1")
```

An embedding deployment may live on a different account. Supply that account's endpoint:

```python
from azllm import connect, embedding_config

with connect(embedding_config("text-embedding-3-small", endpoint="https://your-embedding-account.openai.azure.com")) as small:
    result = small.embed("the quick brown fox")
    result.dimensions      # 1536
```

`embedding_config` requires an endpoint in this portable distribution, including for known model
names. Pass `base=` to retain an existing config's timeout, retries or managed identity client id.

Async is the same call, awaited:

```python
import asyncio
from azllm import connect_async, embedding_config

async def main():
    async with connect_async(embedding_config(endpoint="https://your-embedding-account.openai.azure.com")) as llm:
        one, many = await asyncio.gather(
            llm.embed("single document"),
            llm.embed(["a", "b", "c"], dimensions=512),
        )
        print(one.dimensions, many.count)

asyncio.run(main())
```

**Limits.** At most 2048 inputs per request — enforced here, before the request is sent,
along with the input type, empty strings, an empty batch and a non-positive `dimensions`.
At most 8192 tokens per input and 300,000 tokens per request — *not* enforced here: proving
that needs a tokenizer, a character count does not imply it, and the service reports both as
`LlmError(category="bad_request", status_code=400)`. The numbers are exported as
`MAX_EMBEDDING_INPUTS`, `MAX_TOKENS_PER_INPUT`, `MAX_TOKENS_PER_REQUEST`.

**Malformed responses raise.** A missing, duplicated or out-of-range index, the wrong
number of vectors, vectors of differing length, or a non-numeric or non-finite component
raises `LlmError(category="unknown")`. Vectors are never returned silently attached to the
wrong text. `encoding_format="base64"` raises `ConfigError` saying so; use `embed_raw` for
that.

`embed_raw(**options)` is the unwrapped `embeddings.create` — only `model` is defaulted,
the provider object comes back untouched, and the same error translation applies.

### Structured output

```python
from pydantic import BaseModel

class Incident(BaseModel):
    severity: str
    systems: list[str]
    summary: str

result = llm.parse("Triage: the payment gateway is timing out.", text_format=Incident)
result.parsed.severity     # validated instance, or None on a refusal
result.usage
```

### Tools, chaining, and everything else

`respond(**options)` is the unwrapped `responses.create`. Nothing is filtered, and only
`model` is defaulted, so any current or future Responses API parameter is reachable
without changing this library.

```python
response = llm.respond(
    input=[{"role": "user", "content": "What is the weather in Sydney?"}],
    tools=[{"type": "function", "name": "get_weather",
            "parameters": {"type": "object", "properties": {"city": {"type": "string"}}}}],
    store=True,
)

follow_up = llm.respond(
    input="And tomorrow?",
    previous_response_id=response.id,
    store=True,
)
```

Server-side chaining with `previous_response_id` requires `store=True` on the turn being
referenced. The convenience methods default `store=False`: retaining prompts and
completions on the service is a data decision, not a default worth making silently.

`llm.client` exposes the underlying `OpenAI`/`AsyncOpenAI` object for anything not modelled
here — files, batch, images. Embeddings *are* modelled: use `embed` and `embed_raw`.

---

## Errors

Everything this library raises is `LlmError` (`ConfigError` is a subclass).

```python
from azllm import LlmError

try:
    llm.ask("...")
except LlmError as exc:
    exc.category      # config auth not_found bad_request rate_limit timeout
                      # connection server stream unknown
    exc.status_code   # HTTP status, when one was received
    exc.retryable     # True for rate_limit, timeout, connection, server
    exc.request_id    # x-request-id — the value to quote in a support case
    exc.deployment
    exc.code          # short provider code, e.g. "content_filter"
    exc.__cause__     # the original SDK exception, intact
```

**The provider's message and response body never cross the boundary.** They routinely quote
the prompt or a content-filter excerpt of it, which would turn every log line and error
tracker into a leak. Only the exception type, HTTP status, short error code and request id
survive; the original exception remains as `__cause__` for a debugger. Prompts, completions
and tokens are never logged by this library at any level.

---

## Performance

- **One client per process.** Building `OpenAI` per request discards the connection pool
  (a fresh TLS handshake every call) and rebuilds the credential chain. The connector
  builds both exactly once; the underlying `httpx` client is thread-safe.
- **The token provider is a callable, not a token.** The SDK invokes it on every request,
  so `azure-identity` refreshes on its own schedule. Nothing here freezes a token — the bug
  where a process authenticates perfectly for an hour and then serves 401s until restart.
- **Retries default to 2.** The SDK backs off on 408/409/429/5xx. More retries against a
    429 deepens the queue rather than clearing it; choose capacity deliberately for fan-out.
- **Timeout defaults to 120 s**, not the SDK's 10 minutes: a wedged deployment should not
  wedge a worker.

---

## Probe

```bash
.venv/bin/python scripts/probe.py
.venv/bin/python scripts/probe.py --deployment chat-batch --json
```

One request, `store=false`, output capped at 16 tokens. Prints status, latency, deployment,
model, usage and response id — never the prompt, the answer or a token. Exit codes: `0` ok,
`2` config, `3` auth/RBAC, `4` deployment not found, `5` rate limited, `6` timeout or
connection, `7` other.

```bash
.venv/bin/python scripts/probe_embeddings.py --deployment text-embedding-3-small \
    --endpoint https://your-embedding-account.openai.azure.com --json
```

One short input per deployment, each routed to the account that owns it. Prints host,
deployment, model, count, dimensions, usage and latency — never the input and never a
vector component. Same exit codes; the worst result across the probed deployments is the
exit status. `--endpoint` forces a specific account, which is how the wrong-account 404 is
demonstrated on purpose.

---

## Tests

```bash
.venv/bin/python tests/selftest.py
.venv/bin/python -m pytest -q
.venv/bin/python scripts/mcp_server.py --selftest
```

236 tests, no network, no Azure login, no cloud mutation: every test injects a fake OpenAI
client or a fake token provider through the same `connect(..., client=...)` seam production
uses. Included is a negative test asserting the frozen-token bug has not been introduced —
the SDK receives a callable, the connector mints nothing at construction, and two simulated
requests get two distinct tokens — and a battery of malformed embedding responses asserting
that vectors are never returned attached to the wrong input.

---

## Installed MCP Mode

Install the `harness-data@harness` plugin and start a new session. Call `azllm_status` to
find the JSON settings path under `PLUGIN_DATA/azure-llm-connectors`. Its runtime, cache and
settings are independent of other servers in the plugin. No model call is enabled by installation.

Example operator settings, requiring real authorized coordinates before use:

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

Restart after changing settings. `azllm_ask` and `azllm_embed` are bounded calls to the same library.
The operator owns the grant and targets; tools cannot supply them. The per-process call budget
resets on restart and is not an account-wide cost limit. Live credentials and RBAC remain separate.
The Python API still exposes streaming, structured output and raw calls; the MCP adapter does not.

## Removal

Disable this MCP server in the client, or uninstall `harness-data` to remove the bundle's capabilities.
For a direct Python integration, close connectors and remove its declared dependency. Preserve or
remove local configuration deliberately; uninstall does not revoke Azure roles or delete resources.

## Reference

- [Azure OpenAI v1 API and the `/openai/v1/` base URL](https://learn.microsoft.com/azure/ai-foundry/openai/api-version-lifecycle)
- [Entra ID authentication for Azure OpenAI](https://learn.microsoft.com/azure/ai-services/openai/how-to/managed-identity)
- [Responses API](https://learn.microsoft.com/azure/ai-foundry/openai/how-to/responses)
- [Embeddings on Azure OpenAI](https://learn.microsoft.com/azure/ai-foundry/openai/how-to/embeddings)
- [Azure AI role-based access control](https://learn.microsoft.com/azure/ai-services/openai/how-to/role-based-access-control)
- [OpenAI Python SDK](https://github.com/openai/openai-python)

See `CONTRACT.md` for the public surface and `GOTCHAS.md` for the traps this library exists
to close.
