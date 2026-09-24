# Foundry Hosted Agents Experiment

**Two-version live acceptance passed, 2026-09-22.** Same Foundry Hosted Agent:
baseline version 2 executes `nonce_digest`; version 3 adds and executes
`nonce_statistics`. Actual correlated tool events, exact loaded identity,
stored-response readback and anonymous HTTP 401 passed for both. Original tool
also passes on version 3. Twenty-one focused tests pass.

- [Baseline immutable proof](deploy/records/20260922T060202403083Z-verify.json).
- [New-tool immutable proof](deploy/records/20260922T060615632239Z-verify.json).
- [Original-tool regression readback](deploy/records/20260922T060717524554Z-verify.json).
- [Final inventory](deploy/records/20260922T060747173873Z-inspect.json).

Version 1 was active but inference failed TLS validation; retained, not accepted.
Versions 2 and 3 use platform CA trust with certificate/hostname verification
enabled through the public transport hook. No shared-library changes or second loop.

[Specification and measured results](../../specs/20260922_FOUNDRY_HOSTED_AGENTS_EXPERIMENT.md)
and [deployment sequence](deploy/README.md) own acceptance and operations.

`configuration.yaml` uses the canonical `agentconfig` roster/prompt/`module:function`
contract. Both custom-script tools are deterministic and side-effect-free. `main.py`
composes `llm_interface`'s Microsoft Agent Framework loop with the official Foundry
Responses protocol handler; no second model runner and no optimizer.

Run from repository root, using existing system Python:

```bash
bash testbeds/foundry-hosted-agents/deploy/deploy.sh test
bash testbeds/foundry-hosted-agents/deploy/deploy.sh preflight
```

First command writes a measured offline receipt. Second reads existing Azure metadata
and checks dependencies, identity, registry mode/pull role and model. Neither installs
packages nor writes Azure resources. Explicit install/grant/build/deploy/invoke actions
live under the documented deployment entrypoint. Agent, images, sessions and exact
ACR pull grant remain retained. No pending operations or workers; cost unknown.