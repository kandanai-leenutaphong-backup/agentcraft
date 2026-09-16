# Modular Agents

Distribution `modular-agents==0.2.0`; public packages `agentconfig`, `toolshape`,
and `hostedagents`. Configuration, prompts, tool validation/measurement, native
hosted bundles and owner-bound invocation transport. `llm_interface` owns all
model execution, tool-loop budgets and provider lifecycle.

## Install And Verify

Python 3.11+; reference composition uses Python 3.12. Install the normal declared
requirements and the canonical `llm-interface` release. Use `[hosted]` for the
HTTP/provider extras. [Workspace installation](../README.md#installation) owns source setup.
Neither distribution is presumed published; remote hosted builds remain blocked
until their exact requirements are available to the authorized build environment.

```bash
python tests/selftest.py
python examples/offline.py
```

The offline example (source-or-asset-not-bundled; source reference: `examples/offline.py`) loads prompts/tools, validates and measures
one synthetic tool, refuses an unknown tool, and builds/reads back a temporary
content-addressed host bundle. No model, cloud or grant operation occurs.

## Public APIs

| Task | API / Reference |
| --- | --- |
| Roster, prompts, allowlisted tools | `agentconfig.configure`, `build_spec`, `build_all_specs`, `AgentSpec`; [configuration contract](modules/agent-config-build/CONTRACT.md) |
| Strict config/prompt reads and raw source tracking | `load_agent_config(..., strict=True, sources=...)`, `load_instructions(..., strict=True, sources=...)`; [strict contract](modules/agent-config-build/CONTRACT.md#opt-in-strict-loading-and-source-tracking) |
| Shape and measure tools | `toolshape.ToolSpec`, `Param`, `purpose_built`, `turn`, `MemorySink`, `aggregate`; [tool contract](modules/purpose-built-tools/CONTRACT.md) |
| Select a hosted definition | `hostedagents.load_definition`, `Definition`, `ToolRegistry` |
| Native model execution | `AgentRuntime(definition, policy, connection=connection)` with `llm_interface.connect` and `policy.execution_policy()` |
| Build/read an immutable bundle | `hostedagents.build_bundle`, `load_bundle`, `BundleError` |
| Authenticated local adapter | `hostedagents.application.create_app`, `local_authorizer`, `load_runtime` |
| Optional result UI | `@agentcraft/modular-agents`, `ResultTable`, `getArchetypeRenderer`; [renderer setup](modules/purpose-built-tools/renderers/README.md) |

`ToolRegistry.native_tools` binds the same validated invocation used by direct calls.
It does not add a second model loop. Native request/tool counts and cancellation
are tested with a real SDK over `httpx.MockTransport`, with sockets blocked.
Optional npm renderers export `./styles` and `./tailwind-preset`; hosts provide
the Tailwind build described by the renderer guide. ESM and declarations are built
with `npm run build`; host visual acceptance is separate.

## Ownership And Retirement

Host supplies configuration roots, tool sources, caller identity, credentials,
operator policy, artifact destination and cleanup decisions. Agent YAML cannot grant
execution. Default inference/tool permissions are empty. Caller results are owner-only
and process-local, last 128 turns, not restart-durable storage.

`foundryagent`, raw `OpenAIModel`, standalone skill packages, locks, administration
clients and grant/deployment engines are retired. Native bundles contain host tool
source/configuration and a launcher, not copied library source. Deployment belongs
to the host runbook and requires separate authorization.

[CONTRACT.md](CONTRACT.md) defines bounds and conformance gaps.
[MIGRATION.md](MIGRATION.md) records breaking imports and exact retirements.
[PROVENANCE.md](PROVENANCE.md) and [LICENSE](LICENSE) preserve source notices.
[GOTCHAS.md](GOTCHAS.md) and historical provenance (historical-not-advertised; source reference: `provenance/skill-origin.md`)
retain operational findings, not promises of current cloud compatibility.