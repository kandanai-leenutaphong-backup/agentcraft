# LLM Interface

**Implemented alpha: `llm-interface` 0.1.0a1, import `llm_interface`, Python 3.11+.**
Ready for independent testing, not a live-production or publication claim.

**The payoff: using a model deployed on Microsoft Foundry, either directly or as a
streaming agent, takes several lines of application code.** One factory, familiar
framework methods, explicit identity/grants and no caller-written provider or tool loop.
Start with [USAGE.md](USAGE.md), not the architecture documents.

## Use

Install from the checkout into your application's environment:

```bash
python -m pip install './libraries/llm-interface[foundry]'
```

**LIVE integration shape, not executed in this sweep.** Inside your async application,
with explicitly authorized endpoint, deployment, identity and inference budget:

```python
from azure.identity.aio import ManagedIdentityCredential
from llm_interface import connect

async with ManagedIdentityCredential() as identity, connect(
      endpoint, deployment, credential=identity, allow_model_calls=True,
) as model:
      print((await model.chat.get_response("Summarize this message.")).text)
```

An agent uses the same connection:

```python
agent = model.agent(instructions="Answer briefly using the supplied evidence.")
async with agent.run("Explain this result.", stream=True) as stream:
      async for event in stream:
            print(event.text, end="")
      final = await stream.get_final_response()
```

The model connection must still be open. Grant tool names with `allowed_tools=(...)`
at construction, then supply those functions to `model.agent(tools=[...])`. Nothing
grants Azure permissions automatically. For local development use an explicitly selected
`AzureCliCredential`; do not rely on an ambient credential chain.

## Implemented

| Outcome | Public Surface |
| --- | --- |
| Connect to Foundry project or Azure OpenAI account | `connect(endpoint, model, credential=..., allow_model_calls=True)`; profile selected from endpoint shape |
| Text / structured response | `await model.chat.get_response(text_or_messages, options=...)` |
| Native model streaming | `model.chat.get_response(..., stream=True)`; framework updates and final response |
| Text embeddings | `await model.embeddings.get_embeddings(texts)` with explicit `embedding_model` |
| Streaming tool-using agents | `model.agent(instructions=..., tools=...).run(..., stream=True)` |
| Tool progress and authorization | `report_progress(...)` in async tools; optional host `authorize_tool(ToolCall)` |
| Owner-bound conversation and result read-back | `agent.create_session(principal=...)`, `agent.run(..., session=..., principal=...)`, `session.result(principal=...)` |
| Other framework clients | Explicit `from_clients(...)` adapter-author contract; no config-supplied code loading |

Microsoft Agent Framework owns the common types, schemas and tool loop. Provider SDKs
and Azure Identity own protocols and credential refresh. This package binds targets,
grants and limits, validates native embedding indices before normalization, checks stream
completion, sanitizes failures, manages lifetime and emits correlated run events.

## Test Locally

From the repository root after [workspace setup](../README.md#installation), using the
selected external `UV_PROJECT_ENVIRONMENT`. The offline example needs the OpenAI provider;
select the `foundry` extra separately for Foundry-specific tests.

```bash
"$UV_PROJECT_ENVIRONMENT/bin/python" -B libraries/llm-interface/examples/offline.py
"$UV_PROJECT_ENVIRONMENT/bin/python" -B -m unittest discover -s libraries/llm-interface/tests -v
```

The [offline example](examples/offline.py) runs the real framework and native SDKs
against synthetic HTTP with socket access blocked. It needs no Azure login, credentials
or resources. Current tests do not require retired runtime packages. Commands are source
checked here; prior offline evidence is reused, not a new install or suite run.

[The Foundry example](examples/foundry.py) defaults to no-network description. It requires
`--confirm-live` before any inference. Live identity, role and model verification still
require separately scoped authorization.

## Contract And Evidence

- [CONTRACT.md](CONTRACT.md): exact exports, options, grants, lifecycle, events and limits.
- [OPERATIONS.md](OPERATIONS.md): 18 migrated legacy failure findings, current recipes
      and incompatible behavior; the historical retirement assessment (`CONNECTOR_RETIREMENT.md`, absent from this checkout)
      is a historical input, not current permission to install retired runtimes.
- [VALIDATION.md](VALIDATION.md): current implementation evidence, historical comparisons,
   pending live tests and the fresh-coding-agent usability experiment.
- [DESIGN.md](DESIGN.md) and [VALUE.md](VALUE.md): original design and value rationale;
   the implemented contract takes precedence where an item remains future work.

## Limits

Text, JSON-schema output, text embeddings and local function tools are implemented.
Multimodal content, separate Foundry `/models` embedding endpoints, hosted tools/remote
agents, synchronous compatibility wrappers, durable storage, automatic fallback and browser
adapters are not implemented and are not required for the basic call path. Raw compatibility
and skill-local runtimes are retired; use this public owner, not import-order compatibility.

Sessions/results are in memory; credentials authenticate the service, not application users.
Host-supplied principal and tool authorization remain necessary for multi-user applications.
`store=False` is a provider request, not a claim of zero retention throughout every service.

[Investigation](../../template_apps/investigation_app/docs/ARCHITECTURE_OVERVIEW.md)
is an immediate native caller. Its synthetic acceptance is not live model evidence.
Historical shared artifact, MCP and reader results belong to [conformance](../../.github/skills/harness-guide/framework/CONFORMANCE.md).
Comparative cognitive-load reduction remains unmeasured; short examples are not a controlled
usability comparison. Publication and live operations require separate authorization.