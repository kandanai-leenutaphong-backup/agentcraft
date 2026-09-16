# Caller Guide

**`llm-interface` 0.1.0a1.** Use this page to make calls; implementation details are in
[CONTRACT.md](CONTRACT.md). No provider SDK class or hand-written tool loop is needed.

## Connect And Call

Install [the package's Foundry extra](README.md#use). Get `endpoint` and `deployment`
from the operator, not from model output. In an async application:

```python
from azure.identity.aio import ManagedIdentityCredential
from llm_interface import connect

async with ManagedIdentityCredential() as identity, connect(
    endpoint, deployment, credential=identity, allow_model_calls=True,
) as model:
    answer = await model.chat.get_response("Summarize this text.")
    print(answer.text)
```

A project endpoint contains `/api/projects/<project>`. An Azure OpenAI account origin
or `/openai/v1` endpoint selects the account client automatically. The identity must
already have appropriate service access. For development, explicitly substitute
`AzureCliCredential` after operator login. `model.describe()` makes no network request.

The complete Foundry script (source-or-asset-not-bundled; source reference: `examples/foundry.py`) supplies command-line setup and is
dry-run by default. offline.py (source-or-asset-not-bundled; source reference: `examples/offline.py`) is a complete runnable synthetic
example with no cloud access, hidden host application or undefined configuration.

## Use As An Agent

While the model connection is open:

```python
agent = model.agent(instructions="Answer briefly using only the supplied facts.")
async with agent.run("Explain these facts.", stream=True) as stream:
    async for event in stream:
        print(event.text, end="")
    final = await stream.get_final_response()
```

Add ordinary typed functions with `model.agent(instructions=..., tools=[lookup])` and
grant their exact names in `connect(..., allowed_tools=("lookup",))`. Functions remain
application-owned; the framework executes them. An optional `authorize_tool` callback
can narrow each invocation using its `ToolCall` principal, arguments and run/call IDs.

Events expose `kind`, `data`, `run_id`, `sequence` and `to_dict()`. Text uses `event.text`;
tool events carry a correlated `call_id`. No native provider-event parsing is necessary.
An executing async tool may `await report_progress({...})` to emit real progress.

## Other Calls

| Need | Call |
| --- | --- |
| Structured output | `await model.chat.get_response(text, options={"response_format": MyPydanticModel})`; inspect `response.value` |
| Native model deltas | `model.chat.get_response(text, stream=True)`; use `async with`, then `get_final_response()` |
| Text embeddings | Set `embedding_model` at connection construction, then `await model.embeddings.get_embeddings(["first", "second"])` |
| Embedding dimensions | Pass `options={"dimensions": 256}` if that deployment supports it |
| Non-streaming agent | `await agent.run(text)` |
| Multi-turn session | `session = agent.create_session(principal=user_id)`, then `agent.run(text, session=session, principal=user_id)` |
| Read last completed result | `session.result(principal=user_id)`; in memory only, no new inference |

`Message`, `Content` and framework response types are exported from `llm_interface`.
For multiple turns, supply an owner ID derived from trusted application authentication,
not a caller-controlled JSON field. Omit session for a fresh single-turn conversation.
Do not share a user-bound session across principals or use an old session after changing
the agent definition/model binding. Keep one connection per event loop and close streams.

## Handle A Refusal

```python
from llm_interface import LlmError

try:
    answer = await model.chat.get_response(text)
except LlmError as error:
    print(error.code, error.action)
```

No inference is permitted unless `allow_model_calls=True` was explicitly configured.
Unknown options, forbidden tools and unsupported capabilities refuse. There is no hidden
retry/fallback. An interrupted stream may already have emitted partial text or executed
tools; never restart blindly. Incomplete output and model refusal are distinct from an
authorization error. Native result metadata is not a safe automatic log payload; use
the small `additional_properties["llm_interface"]` run receipt for text/agent results.

## Configure Once

Use `Limits(...)` to lower/choose execution ceilings, `Capabilities(...)` to declare
deployment features, or one `Policy(...)` instead of individual grant keywords. These are
host construction choices, not per-prompt configuration. `from_clients(...)` is only for
adapter authors adding another framework provider; ordinary callers need not use it.

## Acceptance

The short paths are implemented and exercised by standalone fixtures. Comparative
cognitive-load reduction is still unmeasured. The [fresh-coding-agent experiment](VALIDATION.md#low-friction-acceptance)
compares setup, lookups, decisions, glue, errors and swaps with native Agent Framework.
The investigation app remains a read-only reference, never this package's test target.