---
name: managed-identity-model-clients
description: >
  Use when calling Azure OpenAI or Azure AI Foundry models from Python with
  Entra identity instead of API keys, and the call has to survive production.
  Use for token refresh in a long-lived process (401 after an hour), reusing
  one client instead of building one per request, synchronous and asyncio
  access, raw Responses API pass-through, structured output with pydantic,
  streaming that detects in-band error and response.failed events, embeddings
  whose vectors must stay aligned to their inputs, an embedding deployment on a
  different account, bounded timeouts and retries, credential ownership and
  clean shutdown, and errors that must not carry prompts or completions into
  logs. Do not use for creating accounts or deployments, granting roles, agent
  hosting, or evaluation.
---

# managed-identity-model-clients

Entra-authenticated model access with the production failure modes already
handled. Import name `modelaccess`.

## Decide

Use this box when **all** of these are true:

- the target is Azure OpenAI or Azure AI Foundry, reached from Python 3.10+;
- authentication is Entra (managed identity, or a developer sign-in), not a key;
- the process is longer-lived than a script, or the failure modes matter.

Do not use it for: creating or configuring accounts and deployments; granting
or checking RBAC; hosting agents or executing tools; running evaluations;
caching, queueing or rate limiting. It reads from one data plane and writes
nothing anywhere.

If you only want the identity handling around your own SDK client, take
`token_provider_for(config)` and ignore the rest.

## Installed Plugin

The `harness-data@harness` bundle supplies this skill and its MCP server. Start with
`modelaccess_status`: it reports the actual settings path and grants without contacting a model.
Installation alone does not permit inference. The operator must supply targets and
`allow_model_calls`; tool input cannot change them. Never restart to evade an exhausted budget.

`modelaccess_ask` and `modelaccess_embed` are bounded adapters over the same `modelaccess`
library below. Streaming, structured output and raw SDK options remain Python-only.
Read [CONTRACT.md](CONTRACT.md) for MCP inputs and bounds. The adapter reads explicit JSON
settings, not this project's `MODEL_*` variables. Resolve examples relative to the loaded skill.

For a copied skill, the additional MCP check is:

```bash
uv sync --locked --no-default-groups --no-install-project --extra mcp --extra dev
.venv/bin/python scripts/mcp_server.py --selftest
```

Disable the server or uninstall the containing bundle to remove plugin access. That does not
uninstall a separately installed Python library, delete Azure resources, or revoke role grants.

## Standalone Python Install

Copy the folder, then install it into the environment that will import it:

```bash
cp -r managed-identity-model-clients <your-repo>/
cd <your-repo>
python3 -m pip install ./managed-identity-model-clients
```

A plain, non-editable install. It puts the `modelaccess` package in
`site-packages`, so `import modelaccess` then works from any working directory
with no `PYTHONPATH` and no `sys.path` edit. Copying the folder alone is
**not** enough: the importable package sits one level down inside it.

The install pulls `openai`, `azure-identity`, `aiohttp` and `httpx` — the same
four names `requirements.txt` lists, declared in `pyproject.toml` so nothing is
discovered at the first request instead. `pydantic` arrives with `openai`; it
is also declared as the `structured` extra, because `parse(text_format=…)` is
the only thing that needs it:

```bash
python3 -m pip install './managed-identity-model-clients[structured]'
```

`tests/`, `examples/` and `scripts/` are not installed — they stay in the
copied folder and are run from there.

Confirm it, from a directory that is not the copied folder:

```bash
python3 -c "import modelaccess; print(modelaccess.__file__)"   # …/site-packages/modelaccess/__init__.py
```

Set the coordinates — there is no built-in account, and a missing value is a
startup refusal naming the variable:

```bash
export MODEL_ENDPOINT=https://<your-account>.openai.azure.com/
export MODEL_DEPLOYMENT=<your-chat-deployment>
export MODEL_EMBEDDING_DEPLOYMENT=<your-embedding-deployment>   # only for embed()
export MODEL_EMBEDDING_ENDPOINT=https://<other-account>.openai.azure.com/  # if elsewhere
```

The identity needs a data-plane role on the account (for Azure OpenAI, usually
`Cognitive Services OpenAI User`). Granting it is out of scope here.

## Use

Build one client per process and share it.

```python
from modelaccess import ModelConfig, ModelError, connect

with connect(ModelConfig.from_env()) as model:
    answer = model.ask("Summarise this ticket.", instructions="Two sentences.")
    print(answer.text)
    log.info("model call %s", answer.metadata())   # safe: no prompt, no answer
```

Structured output, with the refusal handled:

```python
from pydantic import BaseModel

class Severity(BaseModel):
    level: str
    confidence: float

result = model.parse("Classify this incident.", text_format=Severity)
if result.refused:
    ...            # a successful call whose answer is "no"
else:
    result.parsed  # a validated Severity
```

Streaming, where the failure case is the point:

```python
try:
    for chunk in model.stream_text("Write the summary."):
        emit(chunk)
except ModelError as failed:      # in-band error or response.failed
    if failed.category == "stream":
        ...
```

Embeddings, aligned and explicitly targeted:

```python
vectors = model.embed(["first document", "second document"]).vectors
# vectors[i] belongs to input i because the provider's index said so
```

If the embedding deployment is on another account, build the second client:
`connect(embedding_config(config))`. One client is bound to one account.

Anything this box does not model goes through the raw door, which is never
closed: `model.respond(**anything)` and `model.embed_raw(**anything)` forward
every parameter untouched, defaulting only the deployment.

asyncio is the same surface: `connect_async`, `await model.ask(...)`,
`async for chunk in model.stream_text(...)`, `await model.aclose()`.

Handle errors by `category` (`config`, `auth`, `not_found`, `bad_request`,
`rate_limit`, `timeout`, `connection`, `server`, `stream`, `unknown`) and
`retryable`. Never parse the message; never log the provider's exception, and
never log a formatted traceback of a `ModelError` — its `__cause__` chain still
holds the provider's text.

Cancellation is not a failure. `KeyboardInterrupt`, `SystemExit`,
`GeneratorExit` and `asyncio.CancelledError` propagate untouched, so
`asyncio.wait_for(model.ask(...), timeout=…)` raises `TimeoutError` and a
cancelled task stays cancelled.

Two ownership rules, both explicit: an injected `credential` and an injected
`client` are the caller's, and `close()` leaves them open. Pass
`owns_client=True` when you want this object to close it.

The endpoint is **trusted operator configuration**. A token goes wherever it
points, and shape validation is not a destination check. If the value comes
from data you do not control, pin it: `ModelConfig(..., allowed_hosts=(...))`.

## Verify

Offline, in the copied folder, before trusting it in a new repository:

```bash
python3 tests/selftest.py                        # framework-free; prints one line per check
for f in examples/*.py; do python3 "$f"; done    # six worked examples, all asserting
pip install -r requirements-dev.txt && python3 -m pytest tests
```

`tests/selftest.py` exits non-zero on any failure, needs no test framework, and
needs none of the four dependencies installed — the lazy imports are what make
that true. The pytest suite drives the **real** SDK over an in-process HTTP
transport, so the identity claim, URL shape, retry ceiling, SSE streaming,
structured output and error classification are checked against the SDK rather
than a mirror of this implementation. Both put the copied folder on `sys.path`
themselves, so they test the folder in front of you rather than whatever is
installed.

Against a real account, the operator probe below spends tokens. Like explicitly granted MCP
calls and direct library use, it is live work, not an installation test:

```bash
python3 scripts/probe.py                 # dry run: prints coordinates, no socket
python3 scripts/probe.py --confirm-live  # one small call, then reports metadata
```

A live failure is reported as an operator-actionable line: category, status,
retryable, request id. `auth` covers 401 and 403 *and* a credential that
refused to issue a token at all, so it is a missing data-plane role, an invalid
or expired credential, the wrong tenant, or a scope/audience that does not match
the account — check the role assignment first, then the credential and
`MODEL_SCOPE`. `not_found` is a 404: usually `MODEL_DEPLOYMENT` holding a model
family name rather than a deployment name, but equally a deployment that was
renamed or deleted, or a `MODEL_ENDPOINT` pointing at a different account.

## Remove

The box owns no state, writes nothing and provisions nothing, so removal is
deletion:

1. `grep -rn modelaccess <your-repo>` and remove those imports.
2. `python3 -m pip uninstall managed-identity-model-clients`.
3. Delete the folder.
4. Drop `openai`, `azure-identity`, `aiohttp` and `httpx` from your
   dependencies if nothing else needs them — uninstalling this package does
   not remove them.
5. Unset the `MODEL_*` variables.

Role assignments were never created by this box and survive its removal; remove
them separately if they existed only for it.

## Read next

- [README.md](README.md) — rationale, adoption boundary, limits.
- [CONTRACT.md](CONTRACT.md) — the full spec, sufficient to reimplement.
- [GOTCHAS.md](GOTCHAS.md) — G1–G15: the failures this box exists to prevent.
