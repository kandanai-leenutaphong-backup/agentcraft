# Agentcraft

Reusable agent skills, callable libraries and workflow guidance for application development,
Azure integration, authentication, data access, evaluation and verification.

Start with the [skill catalogue](.github/skills/README.md): 29 capability skills and five embedded
entries, with source, contracts, examples and focused checks. Follow each selected skill's
installation instructions; loading guidance alone does not install dependencies or grant access.

The experimental [Azure data-connector library](libraries/azure-data-connectors/README.md)
provides one async interface across ten service profiles: Search, Cosmos NoSQL, Blob, Table,
ADX, Eventhouse, GraphModel, Gremlin, SQL and PostgreSQL. Official SDKs, models and native drivers
sit behind explicit capabilities, policy and read-back evidence. The `4.0.0a3` offline suite
passes 123 tests; live acceptance and migration of
existing skill/application consumers are deferred. It is not an in-place `azdata` 3.x upgrade.

The [libraries workspace](libraries/README.md) uses uv with a shared lock and independently
buildable packages. The consolidated [Azure access skill](.github/skills/azure-access-management/SKILL.md)
now owns native-first authentication, workload identity and access workflows, their retained
compatibility helpers and offline SDK evidence. The separate access-library experiment is retired.

A dedicated Azure resource group for future connector E2E tests was created and observed empty
on 2026-09-14. The [deployment runbook](deploy/README.md) owns its non-secret targets,
verification evidence and protected lifecycle commands. Service provisioning, sample data
and live CRUD tests remain deferred.

Customer deployment targets and source-project examples have been removed or anonymized from
the skills. The optimization snapshot contains portable source and explicitly synthetic record
examples; the cleanup case study preserves anonymized historical measurements. No capability was
retired by that sanitization. Azure lifecycle commands require an explicit subscription.

The [MIT license](LICENSE) covers repository-authored code. Bundled fonts and artwork retain their
separate notices; external runtime dependencies retain their own terms. Read the
[distribution guidance](.github/skills/AGENT-PLUGINS-SKILLS.md) before publishing a derived package.

## Value Adds

### LLM And Agent Access With Minimal Cognitive Load

The [LLM interface](libraries/llm-interface/README.md) implements a several-line path for
using a model deployed on Microsoft Foundry: supply its endpoint, model/deployment
and authorized identity, then make a standalone call or bind instructions/tools and run
a streaming agent through the same library. Coding assistants should not have to choose
provider SDK classes, rebuild tool loops, parse native events or repeatedly wire policy
and lifecycle code. Microsoft Agent Framework supplies those native mechanisms; the
library supplies one discoverable, guarded interface. The implemented alpha and standalone
examples are ready for independent testing. Comparative cognitive-load reduction remains
to be measured, not inferred from short examples or offline functional checks.

## Pending Work

### Native Frontend Sign-In Migration

- Evaluate and migrate the investigation application's frontend sign-in to native Azure
	Container Apps Easy Auth where it satisfies the [migration contract](.github/skills/azure-access-management/references/frontend-signin.md).
- Preserve application authorization, API refusal behavior, cookies/CSRF, session expiry
	and revocation, and any signed-agent path. Retire custom auth routes, stores and the
	component only after the documented compatibility and deployed acceptance checks pass.
- Not started. Application and Azure authentication configuration remain unchanged;
	deployment changes require separately scoped authorization.

## Pending Testing

### Azure Access Management Skill

- [Consolidated skill](.github/skills/azure-access-management/README.md): live Easy Auth
	frontend/API sign-in and logout, token/session/CSRF/proxy refusals, identity grant
	read-back, PIM/pipeline/IaC integration, replica replay behavior and real provider access.
- Offline compatibility, planner and artifact checks are recorded in its consolidation
	report. They do not prove a native replacement of the investigation app's auth component;
	the application remains unchanged and that migration needs its own acceptance.

### Azure Data Connectors Library

- [Current library](libraries/azure-data-connectors/README.md): live service/permission and
	uncertain-write cases, broader Python/platform coverage and real consumer migration.
	[Verification evidence](libraries/azure-data-connectors/VERIFICATION.md) records offline and artifact checks.
- The [live-test design](libraries/azure-data-connectors/tests/live_tests/LIVE_TEST_DESIGN.md)
	covers all ten profiles. The historical empty resource group does not prove live service
	coverage. Gremlin resource-token issuance and driver compatibility, GraphModel beta/capacity,
	service provisioning, role grants and live tests require explicit targets and authorization.

### Agent Optimization Library

- [Research collection](libraries/agent-optimization/README.md): documentation-only work
	in progress. Implementation, dataset/evaluator compatibility, reproducible offline
	tests, authorized live evaluation and artifact publication remain unverified.

### LLM Interface Library

- [Library](libraries/llm-interface/README.md): `0.1.0a1` implements the few-line standalone-call
	and streaming-agent paths with independent offline fixtures. The [validation record](libraries/llm-interface/VALIDATION.md)
	owns current test and artifact evidence. Pending: authorized live Foundry identity/permissions
	and model behavior, actual non-OpenAI provider conformance, broader dependency/Python and
	load coverage, and a fresh coding-assistant usability comparison against Agent Framework.
- The investigation application is a read-only reference, not an integration target.
	No application modification, test, server or browser run is part of this work. Live model
	calls require separately scoped authorization.

## Limits

- Live cloud access, paid model calls and deployments require operator configuration and authorization.
- Offline fixture checks do not establish production permissions or measured model performance.
- This checkout provides skills, not a repository-root plugin installer or an automatically deployed app.
- New contributions, datasets and third-party assets need their own provenance and rights review.

## Contributing

This project welcomes contributions and suggestions.  Most contributions require you to agree to a
Contributor License Agreement (CLA) declaring that you have the right to, and actually do, grant us
the rights to use your contribution. For details, visit [Contributor License Agreements](https://cla.opensource.microsoft.com).

When you submit a pull request, a CLA bot will automatically determine whether you need to provide
a CLA and decorate the PR appropriately (e.g., status check, comment). Simply follow the instructions
provided by the bot. You will only need to do this once across all repos using our CLA.

This project has adopted the [Microsoft Open Source Code of Conduct](https://opensource.microsoft.com/codeofconduct/).
For more information see the [Code of Conduct FAQ](https://opensource.microsoft.com/codeofconduct/faq/) or
contact [opencode@microsoft.com](mailto:opencode@microsoft.com) with any additional questions or comments.

## Trademarks

This project may contain trademarks or logos for projects, products, or services. Authorized use of Microsoft
trademarks or logos is subject to and must follow
[Microsoft's Trademark & Brand Guidelines](https://www.microsoft.com/legal/intellectualproperty/trademarks/usage/general).
Use of Microsoft trademarks or logos in modified versions of this project must not cause confusion or imply Microsoft sponsorship.
Any use of third-party trademarks or logos are subject to those third-party's policies.
