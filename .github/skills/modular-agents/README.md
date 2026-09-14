# Modular Agents

Configuration-defined agents, modular tools, and Azure Foundry hosting in one
self-contained skill. Four internal modules preserve independent contracts
without making consumers install four mutually dependent skills.

```text
YAML roster + prompt files + owned tool packages
    |
    v
agentconfig.AgentSpec <--- toolshape validation/envelopes/turn ledger
    |                         |
    +-> foundryagent          +-> hostedagents.Definition
        MAF client factory        |
                                  +-> AgentRuntime: local callable service
                                  +-> flat source zip -> Foundry hosted agent
```

The hosted path preserves the configuration's model, complete composed prompt,
tool order and actual functions. It adapts the deployment protocol from the
source `hcagent` component without importing its canvas, application store,
frontend, data library or cache library. The two unrelated `agentconfig`
packages in the source estate are not combined.

## Start

Run from this skill directory:

```bash
uv sync --locked --no-default-groups --extra dev
.venv/bin/python tests/selftest.py
.venv/bin/python tests/selftest.py --copy-out
.venv/bin/python examples/offline.py
bash deploy/deploy.sh plan
bash deploy/deploy.sh build
```

Python 3.11+, uv and dependency-download access are required initially. The
commands above need no Azure account and make no model calls. `build` prints the
artifact directory, zip digest and runtime tool list. Repeating the build with
the same source produces the same content-addressed artifact.

Use [SKILL.md](SKILL.md) as the task guide and
[deploy/README.md](deploy/README.md) as the sole operator sequence. A consuming
project can install this directory with `uv pip install /path/to/modular-agents`;
copying source into another project is unnecessary. Do not install the source
canvas configuration package into the same environment: it owns the same Python
name, `agentconfig`, with a different API.

## What Ships

| Module | Public package | Preserved or added capability |
| --- | --- | --- |
| [agent-config-build](modules/agent-config-build) | `agentconfig` | YAML fragments, prompt composition, aliases, fail-closed imports, factory seam |
| [purpose-built-tools](modules/purpose-built-tools) | `toolshape` | ToolSpec/Param, validators, result envelopes, dedupe ledger, measurement, worked Azure tools and optional renderers |
| [foundry-agent-runtime](modules/foundry-agent-runtime) | `foundryagent` | MAF client factory/pool, model resolution, retry/fallback, compaction/tracing adapters |
| [foundry-hosted-agents](modules/foundry-hosted-agents) | `hostedagents` | Typed tool registry, source bundling, runtime policy, authenticated invocations, deployment/grant lifecycle |

The original three modules' source, documentation, gotchas, examples and tests
remain together. Their historical live findings are retained with their original
scope, not represented as observations of this migration. See
[PROVENANCE.md](PROVENANCE.md) for inputs and adaptations.

## Hosting Contract

- `Definition` wraps the existing `AgentSpec`; it does not introduce another
  agent configuration language. `ToolRegistry` generates schemas with Pydantic
  and rejects malformed arguments before calling the function.
- `build_bundle` includes actual tool packages and the three required local
  Python packages at zip root. Runtime dependencies are exact pins exported
  from the lock. No path into the origin or another skill is an install input.
- `AgentRuntime` owns policy, tool execution, bounded model turns, cancellation
  and owner-only result read-back. HTTP and Python are callers of that service.
- `FoundryClient`, `Deployer` and `GrantBroker` expose the operator-side lifecycle.
  Exact agent names and separate mutation grants are mandatory. The deployment
  CLI serializes operations per receipt; library callers must do the same.
- Auth remains enabled. Local serving requires a token; hosted serving relies
  on Foundry's authenticated ingress and session isolation. Managed identity
  authenticates the workload to the model, not the human to the application.

Exact APIs, formats, bounds and failure behavior: [CONTRACT.md](CONTRACT.md).

## Verification

The aggregate [tests/selftest.py](tests/selftest.py) uses the standard-library
runner, not pytest. It runs the three preserved selftests, hosted integration
tests and the offline example. `--copy-out` reruns it from an unrelated temporary
directory containing only this skill.

Integration evidence includes positive and matching negative cases for imports,
tool schemas/approval, policy, authentication, owner-only results, upload/update
shape, grant scope, crash recovery, cancellation and artifact integrity. An
extracted zip is served over a real loopback socket. The official OpenAI SDK and
Foundry/ARM transports are exercised with offline responses, not real Azure.

For the optional preserved tool edge-case suite:

```bash
.venv/bin/python -m pytest modules/purpose-built-tools/tests -q -p no:cacheprovider
```

## Limits

- No live Foundry deployment, cloud query, paid inference, role change or remote
  plugin installation was performed for this migration. Hosted Python 3.13 is
  the source protocol target; remote build/platform compatibility needs live
  acceptance in the operator's approved project.
- MAF remains optional. Its preserved injected-SDK tests do not certify every
  current MAF version. Hosted execution does not depend on MAF.
- Headless hosting supports ordinary importable sync/async functions, not
  native server tools, interactive approval, arbitrary binary assets, or the
  original canvas application. Custom packages must declare their full closure.
- The hosted model loop is sequential, stateless between chat messages, and
  emits a `token` event for each completed model response, not provider token
  deltas. It does not silently claim MAF fallback/compaction parity.
- Result retention is process/session-local, capped at 128 turns. A synchronous
  tool already running in a worker thread cannot be forcibly stopped by cancel.
  Use bounded cooperative backends, especially before granting mutating tools.
- Grant automation covers ARM Search reader, Blob container reader and model
  inference roles only. Cosmos SQL, Kusto and SQL table grants require their own
  explicit provider; they are not approximated by broader ARM roles.
- No new frontend is shipped. Existing renderer source is preserved as optional
  reference material; its browser behavior was not revalidated here.
- Shared plugin manifests and root project-state documents remain with the
  concurrent migration owner. See [INTEGRATION.md](INTEGRATION.md).

## Removal And Rollback

Retain the exact deployment receipt and artifacts. Teardown revokes grants this
receipt created, verifies absence, deletes the recorded agent/version and verifies
absence. Pre-existing grants are not silently deleted; external grants are outside
the receipt and remain the operator's responsibility. Resource groups, Foundry
accounts/projects and model deployments are never provisioned or removed here.

A code rollback uploads a previously retained artifact as a new version with
`allow_update` and explicit confirmation, then runs `verify`. Do not rewrite an
artifact in place or force-delete the receipt. After cloud cleanup, uninstall the
Python package or remove its dedicated environment; uninstalling a skill alone
does not perform cloud teardown.