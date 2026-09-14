---
name: modular-agents
description: 'Build configuration-defined agents with modular purpose-built tools and host the same agent on Azure Foundry hosted agents. Use when defining an agent roster in YAML, composing prompt files, registering typed tools, validating or measuring tool behavior, running a roster through Microsoft Agent Framework, packaging a flat hosted-agent source bundle, deploying or verifying a Foundry hosted version, diagnosing missing tools or session ownership, or recovering a deployment with explicit operator grants. Includes four internal modules, offline acceptance, authenticated invocation, and exact-scope deployment receipts; installation enables no Azure access.'
---

# Modular Agents

One skill, four internal modules. One user outcome: configuration and tool source
become an agent that can run locally and as a Foundry hosted agent.

## Choose The Surface

| Need | Owner | Read |
| --- | --- | --- |
| YAML roster, fragments, prompt composition, import allowlist | `agentconfig` | [Configuration module](modules/agent-config-build/SKILL.md) |
| Tool schema, validation, result envelopes, duplicate suppression, measurement | `toolshape` | [Tool module](modules/purpose-built-tools/SKILL.md) |
| Microsoft Agent Framework clients, per-agent isolation, retries and fallback | `foundryagent` | [Client runtime module](modules/foundry-agent-runtime/SKILL.md) |
| Flat code bundle, hosted invocations, deployment, grants and receipts | `hostedagents` | [Hosting contract](CONTRACT.md), [deployment runbook](deploy/README.md) |

The client runtime module does **not** deploy hosted agents. Its `as_agent`
factory and the hosted application are two consumers of the same `AgentSpec`.
The hosted adapter uses the official OpenAI SDK for model calls and the existing
Foundry invocations 2.0 protocol for deployment. It is not a prompt-only agent
registration and not an Azure Container Apps deployment.

## Install And Prove

From this skill directory, with Python 3.11+ and uv:

```bash
uv sync --locked --no-default-groups --extra dev
.venv/bin/python tests/selftest.py
.venv/bin/python tests/selftest.py --copy-out
.venv/bin/python examples/offline.py
```

All four Python packages install from this directory. No sibling skill or origin
checkout is required. Optional `--extra framework` installs the preserved MAF
integration; it is not needed by the hosted adapter. Dependencies and runtime
pins come from [pyproject.toml](pyproject.toml) and [uv.lock](uv.lock).

## Define The Agent

Start from [examples/control](examples/control) and
[examples/agent_tools](examples/agent_tools). Add a fragment, include it in the
base roster, name the model deployment, and reference prompt files and tools:

```yaml
agents:
  notes:
    name: Notes Agent
    model: example-deployment
    instructions:
      - notes.md
    tools:
      - agent_tools.notes:list_topics
      - agent_tools.notes:search_notes
```

Agent ids are stable public identifiers. Foundation prompts apply to the whole
roster. Build the whole roster at startup; an unresolved prompt or tool must
stop the build, not remove a capability silently.

## Define A Tool

Use a normal, typed, importable Python function. Apply `@agentconfig.tool`
outside `@toolshape.purpose_built(ToolSpec(...))`. Keep descriptions, accepted
parameter forms, result shape and duplicate key in that `ToolSpec`; inject the
backend into the tool's composition module, never into model-supplied arguments.

[examples/agent_tools/notes.py](examples/agent_tools/notes.py) contains synchronous
and asynchronous tools over an offline backend. The source tool module retains
Azure examples, call records, the weight meter, ablation guidance and optional
React renderers. None of those examples is an implicit runtime dependency.

Hosted constraints are deliberate: concrete parameter annotations, matching
ToolSpec/signature defaults, no variadic parameters, no nested functions, no
credential parameters, and no tools requiring interactive approval. Native
framework/server tool objects stay in the client-runtime path until a hosted
adapter for their execution semantics is implemented.

## Compose Once

```python
from pathlib import Path
from hostedagents import load_definition

definition = load_definition(
    Path("control"),
    agent_id="notes",
    allowed_prefixes=("agent_tools.",),
)
```

`definition.spec` remains the original `agentconfig.AgentSpec`.
`definition.tools.schemas` and `await definition.tools.invoke(...)` describe and
execute the same callables. `AgentRuntime` adds operator policy, per-turn limits,
model orchestration, result ownership, and cancellation.

To use `foundryagent.build_agent`, supply the same spec and pass
`markers=(agentconfig.TOOL_MARKER, foundryagent.TOOL_MARKER)` so MAF sees both
decorator conventions. See [examples/offline.py](examples/offline.py).

## Build And Host

1. Declare owned tool package paths and the import allowlist in a build document
   based on [examples/build.json](examples/build.json).
2. Keep runtime policy separate from agent YAML. Default tool/model grants are
   empty/false. The worked example explicitly grants only its two fixture tools.
3. Run `bash deploy/deploy.sh build`. It outputs a content-addressed artifact
   directory. No Azure request, token or model call occurs.
4. Follow [deploy/README.md](deploy/README.md) for target configuration, operator
   policy, plan, upload, grant read-back, verification and teardown.
5. Use `verify` to read back the exact version, source identity, model, policy and
   recorded grants. Then explicitly authorize and perform the required live
   tool/model probe. A healthy container is not evidence of inference or data RBAC.

Installation does not deploy anything. Do not enable cloud policy, run paid
inference, create role assignments or tear down resources without authorization.
Agent YAML and invocation JSON cannot request wider operator grants.

## Authentication And State

Foundry owns authenticated ingress; its session identity is the hosted adapter's
caller boundary. A local extracted runtime instead requires
`MODULAR_AGENTS_LOCAL_TOKEN` and binds loopback only. No caller identity header is
trusted. Readiness is public and reports no configuration.

The CLI uses the operator's Azure CLI credential. The hosted model client uses
the sandbox's managed identity. These are different identities with different
permissions. Consumer and maintenance sessions use disjoint derived names.

Deployment receipts persist under the environment's `STATE_DIR`, outside agent
zips. Chat results retain the last 128 turns in the process/session and support
owner-only read-back; they are not restart-durable. See the exact limits in
[CONTRACT.md](CONTRACT.md) before promising a multi-user service.

## Troubleshoot And Remove

Start with [GOTCHAS.md](GOTCHAS.md); module-local gotcha ids retain their original
meaning. Source measurements are historical, not new cloud evidence.

For a deployed agent, use `deploy/deploy.sh teardown` with its receipt and
explicit permission. It revokes recorded owned grants before deleting the agent
and reads both back absent. Removing the skill does not remove Azure resources.
For a local-only installation, uninstall `modular-agents` from its environment;
the three preserved modules contain no persistent resources of their own.

[INTEGRATION.md](INTEGRATION.md) records the shared-plugin handoff. This change
owns only this skill directory, not catalogue versions or the plugin MCP manifest.