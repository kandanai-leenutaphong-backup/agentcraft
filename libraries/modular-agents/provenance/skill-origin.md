# Source And Packaging Boundary

One capability: define a modular agent in configuration and run that same agent
locally or in Azure Foundry hosted agents. Internal modules preserve separate
contracts; the immediate skill entry point owns composition and distribution.

## Inputs

The distribution includes four owned modules:

- `modules/agent-config-build`: declarative agent rosters and prompt composition.
- `modules/purpose-built-tools`: typed tools, validation and result shaping.
- `modules/foundry-agent-runtime`: identity-based model/runtime adapters.
- `modules/foundry-hosted-agents`: packaging, invocation and guarded deployment.

Private source checkouts, live evidence, credentials and source deployment targets
are not prerequisites. No sibling skill is an implicit dependency.

## Ownership

Implementation and module contracts belong to this skill. Shared plugin manifests,
catalogue versions and repository documentation remain with their respective owners.
Installing this skill must not enable cloud operations.

## Acceptance

From this skill root, the release checks are:

```bash
python3 tests/selftest.py
```

The aggregate check must preserve the three source mechanisms' selftests and
prove configuration-to-hosted packaging with injected offline collaborators,
including matching refusals. Run it again from a temporary copy containing only
this skill, with declared dependencies installed and no origin on `PYTHONPATH`.
Cloud deployment, role changes, paid inference, and teardown require separate
operator authorization and are not implied by offline success.

## Packaging Decisions

| Module surface | Responsibility |
| --- | --- |
| Hosted bundle | Flat-root ZIP, hosted metadata, explicit source selection and content-addressed artifacts |
| Hosted runtime | Invocations/readiness, bounded tool/model turns, correlated SSE and cancellation; YAML-resolved functions and official model SDK |
| Foundry adapter | Multipart create/update, session query routing, bounded warm retries and live read-back; injected transport and sanitized failures |
| Deployment lifecycle | Upload/wait/grant/warm operations, operator policy and atomic durable receipts |
| Access grants | Reader-grade ARM role IDs, exact-scope read-back, instance identity and revoke-before-delete; deliberately excludes Cosmos/Kusto/SQL planes |

Composition uses the included `agentconfig.AgentSpec`. The MAF client factory is
a separate consumer; hosting does not claim its fallback/compaction behavior.
No application auth bypass, private deployment inventory or live state is included.

## Verification Coverage

- The aggregate acceptance command is `python3 tests/selftest.py`; output enumerates
  each check rather than inheriting a historical result or hardcoded count.
- Extracted zip imports its own source packages, serves a real loopback socket,
	refuses anonymous/malformed calls, executes the configured fixture tool, and
	reports the expected runtime source digest.
- Official OpenAI SDK request/response and Foundry/ARM transport shapes are exercised
	with offline collaborators. No live Azure authorization or model response is claimed.

Dependencies installed separately retain their own licenses. This record describes
the shipped composition, not a license grant for a customer's agents, tools or data.