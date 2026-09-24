---
name: foundry-agent-runtime
description: Run an agent roster on Azure AI Foundry with the Microsoft Agent Framework, using managed identity instead of API keys. Use when wiring a model into an agent runtime, when an agent answers with another agent's tools, when a project endpoint returns 403 or 404 that looks like a permissions problem, when content-filter refusals are being retried across every fallback model, when tool results blow the context window mid-run, when a deployment works in the portal but 400s from the app, or when asked to make agent construction testable without an Azure account.
license: MIT
---

# foundry-agent-runtime

Four calls wire a declarative roster onto Foundry. Everything else in the box
exists to make those four correct under concurrency, load, and a missing SDK.

## Decide

Use this when **all** hold:

- The model is hosted in an Azure AI Foundry project.
- The runtime is the Microsoft Agent Framework.
- More than one agent shares a process.

Do not use it for: a single chat completion (call the SDK), a non-Azure model
host, or an agent framework other than MAF (rewrite `_maf.py`, keep the rest).

## Install

```bash
cp -r foundry-agent-runtime <your-project>/
pip install agent-framework azure-identity
python3 tests/selftest.py          # offline; proves the box works here
```

Grant the app identity the **Azure AI User** role (or higher) on the Foundry
project. No key, no connection string, no secret in configuration.

```bash
export FOUNDRY_PROJECT_ENDPOINT="https://<resource>.services.ai.azure.com/api/projects/<project>"
export FOUNDRY_MODEL_DEPLOYMENT="<deployment>"
export FOUNDRY_MODEL_DEPLOYMENT_FAST="<cheap-deployment>"   # optional
export FOUNDRY_FALLBACK_MODELS="<other-deployment>"          # optional
```

The endpoint must contain `/api/projects/`. Without it you have the account
endpoint, and every call will fail as a permissions error (GOTCHAS.md G1).

## Use

### Wire the roster

```python
import foundryagent as fa

config = fa.FoundryConfig.from_env()
pool   = fa.ClientPool(fa.foundry_agent_client(config))
tracing = fa.build_tracing_middleware(on_event=metrics.record)

agents = {
    agent_id: fa.build_agent(
        spec, pool.client_for(agent_id), config,
        agent_id=agent_id, middleware=tracing,
        tokenizer=tokenizer, token_budget=window - response_budget,
    )
    for agent_id, spec in roster.items()
}
```

`spec` is a mapping or any object carrying `name`, `description`,
`instructions`, `tools`, `model`. Unknown keys are read from an `extra` mapping
if present, so a config loader's own spec type works unchanged.

### Take a turn

```python
answer = await fa.run_with_fallback(
    lambda model: agents["planner"].run(user_text),
    config, context="planner",
)
```

Retries throttles with the service's own retry-after, backs off on transient
errors, re-raises content-filter and auth failures immediately, and moves to the
next deployment when one is exhausted.

### Write a tool

```python
@fa.tool
def lookup_status(asset_id: str) -> dict:
    """Return the current status of an asset by its identifier."""
    return {"asset_id": asset_id, "status": "nominal"}
```

Plain function, plain call in tests, no SDK import. Binding happens at agent
build. **Never** alias an `Annotated` parameter type at module scope — it breaks
the build for every agent that shares it, not just this tool (GOTCHAS.md G5).

### Classify a failure yourself

```python
kind = fa.classify(exc)   # "fatal" | "rate_limit" | "transient" | "unknown"
```

## Verify

```bash
python3 scripts/probe.py                  # config, SDK, identity
python3 scripts/probe.py --build          # + client and agent construction
python3 scripts/probe.py --run "ping"     # + one live turn
```

Stages run in the order failures cascade and stop at the first one, so the output
names the broken layer. Exit 0 pass, 1 fail, 2 bad invocation.

Before promoting a model swap, prove the new deployment with `--run`. A
deployment can be healthy in the portal and 400 from the app (GOTCHAS.md G12).

## Test without Azure

```python
fa.set_sdk("agent_framework", fake_framework)
fa.set_sdk("agent_framework.azure", fake_azure)
fa.set_sdk_absent("agent_framework")      # assert the degraded paths
fa.clear_sdks()                            # teardown
```

Substitution goes through the shipping code path — there is no test-only branch.
A stub client with an `as_agent` method needs no substitution at all: `bind_tools`
no-ops on a non-SDK client, so the same roster runs in CI unchanged.

## Symptoms

| Symptom | Read |
| --- | --- |
| 403/404 that looks like permissions | G1 |
| Agent uses another agent's tools | G2 |
| Uneven cold-start auth latency | G3 |
| Service rejects a tool-less agent | G4 |
| Every chat for one agent 500s | G5 |
| Compaction or tracing silently stopped | G6 |
| Reordering tools changed behaviour | G7 |
| Fallback model never helps | G8 |
| Tool failed, agent answered anyway | G9 |
| Long runs rejected part-way through | G10 |
| Filter refusal takes ten times too long | G11 |
| Healthy in the portal, 400 from the app | G12 |
| Filter fires on ordinary domain terms | G13 |
| Turns abort during silent reasoning | G14 |

## Remove

Delete `foundryagent/` and the factory call; construct against the SDK directly.
Nothing to unwind — the box creates no Azure resource and holds only a cached
credential and a dict of clients, both process-local.
