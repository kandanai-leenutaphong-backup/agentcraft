# Selected Modular-Agent Migration

| Old Skill Root | Canonical Owner / Disposition |
| --- | --- |
| `modules/agent-config-build` | Coherent `agentconfig`, prompt/config contracts, tests and examples |
| `modules/purpose-built-tools` | Coherent `toolshape`, validation/measurement, tests and examples |
| Hosted definitions, policy, packaging and application | Retained; engine delegates to `llm_interface`, model module only binds target/policy |
| `modules/foundry-agent-runtime/foundryagent` | Retired duplicate execution/retry/native-client engine; historical guidance/notices retained |
| Hosted `client.py`, `deployment.py`, `grants.py`, CLI/scripts and tests | Retired administration surface; host/native runbook owns authorized operations |
| Skill metadata, lock, build cache, scripts/tests | Replaced by this distribution and retained/adapted checks |
| Deploy runbook/example targets | Historical provenance, not current executable deployment instructions |
| `deploy/state` generated artifacts | Protected in place, not deleted or advertised as current runtime |

Exact hashes, file moves and retirements: [MIGRATION.json](MIGRATION.json).
Unshipped build cache and deployment state are excluded from both source-reduction
counts. No customer configuration, data or checkpoint is removed.
Measured shipped skill scope: 139 files / 1,545,861 bytes to 1 file / 1,201 bytes.
The raw frozen inventory also records the excluded generated build/state entries.

## Breaking Imports

- Distribution stays `modular-agents`, now `0.2.0`; `agentconfig` and `toolshape` retain
  coherent APIs, not arbitrary same-file wrappers.
- `hostedagents` exports definitions, typed tool registry, runtime/policy, bundle/read-back
  functions and their refusal types.
- Replace `AgentRuntime(..., model=OpenAIModel(...))` with a native `connection=`.
  Build it using `llm_interface.connect`, `policy=runtime_policy.execution_policy()` and
  the exact definition model. Connections are borrowed unless ownership is explicit.
- `foundryagent`, `OpenAIModel`, deployment/grant clients and skill `_bootstrap` imports
  are removed. No compatibility aliases revive their independent engines.
- Retained result renderers are exported by `@agentcraft/modular-agents@0.2.0`, with
  `./styles` and `./tailwind-preset`; they import no application source.
- Bundles contain host source/configuration and a launcher, not library copies. Exact
  canonical releases must be available to the remote build; no publication is presumed.

## Verification

[VALIDATION.md](VALIDATION.md) records actual checks. Raw SDK-shape, legacy retry and
administration tests retire with their unselected APIs; native request-count, cancellation,
owner/refusal and bundle integrity checks replace relevant outcomes. No model inference,
cloud write, access grant, deployment, teardown or publication occurred.