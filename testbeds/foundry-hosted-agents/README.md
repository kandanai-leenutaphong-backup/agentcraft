# Foundry Hosted Agents Experiment

SDK migration live acceptance passed on separate `agentcraft-migration-tool-proof-v1`,
versions 1/2/3. Final version 3 proves `nonce_digest`, `nonce_statistics` and new
`nonce_reverse`, exact image/config identity, stored readback and anonymous refusal.
Native cancellation reads back `cancelled` without completed output; task/client cleanup
is locally tested, not independently confirmed by provider logs. Forty-one tests pass.
Actual ACR builds `crm`/`crn` overlapped for 43.349496 seconds using the same locked
archive and distinct frozen tags; direct returned run/tag/digest associations passed.
No agent version was deployed by this build-only check.
[Acceptance-gap correction](../../deploy/remediation-evidence/20260922T193935Z-acceptance-gaps/README.md).
[Migration procedure and receipts](deploy/README.md#migration-canary-current-procedure).
Historical accepted agent/versions below remain unchanged. F09 accepted, 2026-09-22:
[authoritative result](../../agentcraft_projects/foundry-official-integration-20260922/records/v2/20260922T200128628556Z-f09-migration-accepted/record.json).

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

Deploy-side lifecycle glue uses the shared [`foundry_ops`](../../libraries/foundry-ops/README.md)
library since 2026-09-24 (offline only: 42 tests pass; no live action has run on it).
Image source manifest is unchanged by that migration.

`configuration.yaml` uses the canonical `agentconfig` roster/prompt/`module:function`
contract. All three custom-script tools are deterministic and side-effect-free. `main.py`
composes `llm_interface`'s Microsoft Agent Framework loop with the official Foundry
Responses protocol handler; no second model runner and no optimizer.

Run from repository root, using existing system Python:

```bash
bash testbeds/foundry-hosted-agents/deploy/deploy.sh test
bash testbeds/foundry-hosted-agents/deploy/deploy.sh preflight --manifest testbeds/foundry-hosted-agents/deploy/env/migration-h-v1.json --manifest-sha256 4e1ee1636486d49d8fb52962e2ea88d59f1bf5ee2410b8b71d122b863a0e9b95
```

First command writes a measured offline receipt. Second reads existing Azure metadata
and checks dependencies, identity, registry mode/pull role and model. Neither installs
packages nor writes Azure resources. Explicit install/grant/build/deploy/invoke actions
live under the documented deployment entrypoint. Agent, images, sessions and exact
ACR pull grant remain retained. No pending operations or workers; cost unknown.