# Agentcraft

Reusable agent skills, callable libraries and workflow guidance for application development,
Azure integration, authentication, data access, evaluation and verification.

## Agent Team

Local [agent coordination](.github/agents/README.md) uses `overseer` as the normal user contact,
`orchestrator` for bounded feature ownership, and optional specialists. Shared skills and
safety authorities remain active.

Library integration and live verification remain in progress. The [deployment runbook](deploy/README.md)
and [library documentation](libraries/README.md) own current procedures, evidence and remaining
acceptance work, including pending live checks, migrations and promotions.

## Feature Status

Status describes library runtime features, not research or skills. First pass does not mean production-ready.

| Feature | Status | Project Documentation And Evidence | Official References |
| --- | --- | --- | --- |
| Evaluation | Not added | [Research](libraries/agent-optimization/EVALUATIONS.md), [API and operating constraints](libraries/agent-optimization/API_AND_OPERATIONS.md), [source index](libraries/agent-optimization/SOURCES.md) | [Cloud evaluation](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/cloud-evaluation), [built-in evaluators](https://learn.microsoft.com/en-us/azure/foundry/concepts/built-in-evaluators) |
| Optimization | Not added | [Research](libraries/agent-optimization/OPTIMIZATION.md), [source index](libraries/agent-optimization/SOURCES.md) | [Agent Optimizer](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/agent-optimizer-overview), [Prompt Optimizer](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/prompt-optimizer) |
| Observability | Not added | [Research and migration notes](libraries/agent-optimization/OBSERVABILITY.md), [source index](libraries/agent-optimization/SOURCES.md) | [Tracing setup](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/trace-agent-setup), [agent monitoring](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/how-to-monitor-agents-dashboard), [Application Insights](https://learn.microsoft.com/en-us/azure/azure-monitor/app/agents-view) |
| LLM Interface | First pass in libraries | [Overview](libraries/llm-interface/README.md), [usage](libraries/llm-interface/USAGE.md), [contract](libraries/llm-interface/CONTRACT.md), [offline example](libraries/llm-interface/examples/offline.py), [validation](libraries/llm-interface/VALIDATION.md) | [Foundry SDK overview](https://learn.microsoft.com/en-us/azure/foundry/how-to/develop/sdk-overview) |
| Data Connectors | First pass in libraries | [Overview](libraries/azure-data-connectors/README.md), [contract](libraries/azure-data-connectors/CONTRACT.md), [all-provider SDK research](libraries/azure-data-connectors/research/README.md), [verification](libraries/azure-data-connectors/VERIFICATION.md), [live-test plan](libraries/azure-data-connectors/tests/live_tests/LIVE_TEST_DESIGN.md) | [Search SDK](https://learn.microsoft.com/en-us/python/api/azure-search-documents/azure.search.documents.aio.searchclient?view=azure-python), [Cosmos SDK](https://learn.microsoft.com/en-us/python/api/azure-cosmos/azure.cosmos.aio.containerproxy?view=azure-python) |

### Completeness Gaps

Assumes: a reusable foundation for authenticated, stateful agents. Proposed acceptance areas, not new-package decisions or claims of absent skills; reuse existing owners.

- **Identity and authorization:** human, agent and workload identities; tenant/record isolation; least-privilege tools and approvals. Access skills exist; integrated refusal checks remain necessary.
- **Agent and tool execution:** extend the LLM interface's agent path with required tool contracts, execution bounds, cancellation and workflows. Do not create a second tool loop.
- **Durable state and recovery:** conversation ownership, persisted outputs, checkpoints, restart recovery and retention/deletion.
- **Knowledge ingestion and retrieval:** ingestion, indexing, access-aware retrieval, citations and freshness. Connectors alone are not a complete knowledge workflow.
- **Safety and governance:** input/output policy, untrusted-content handling, tool-side enforcement, approval/audit evidence and budgets. Scores do not enforce permissions.
- **Deployment and lifecycle:** validated configuration, secret/identity integration, versioned releases, health/readiness, rollback and workload-appropriate hosting/scheduling.
- **End-to-end acceptance:** a documented reference consumer, callable workflows, regression tests, authorized live checks and usable installation/operation. Library passes alone do not prove integration.

Recommended order: authorized agent/tool workflow with durable read-back; evaluation and observability; safety/recovery/deployment acceptance; then optimization against a frozen baseline. UI, multi-agent coordination and long-term memory depend on the use case.

## Current Foundation

Start with the [skill catalogue](.github/skills/README.md): 29 capability skills and five embedded
entries, with source, contracts, examples and focused checks. Follow each selected skill's
installation instructions; loading guidance alone does not install dependencies or grant access.

The experimental [Azure data-connector library](libraries/azure-data-connectors/README.md)
provides one async interface across ten service profiles: Search, Cosmos NoSQL, Blob, Table,
ADX, Eventhouse, GraphModel, Gremlin, SQL and PostgreSQL. Official SDKs, models and native drivers
sit behind explicit capabilities, policy and read-back evidence. The `4.0.0a3` source suite
passes 130 offline tests. A local [CyberEye template](template_apps/README.md) now uses it for ADX
queries. Investigation and Custom Optimizer now run as separate local template applications,
with preserved experimental history and single-owned shared foundations. Broader live parity
requires separate verification; other consumer migrations
remain deferred. It is not an in-place `azdata` 3.x upgrade.

The [libraries workspace](libraries/README.md) uses uv with a shared lock and independently
buildable packages. The consolidated [Azure access skill](.github/skills/azure-access-management/SKILL.md) owns native-first authentication, workload identity/access workflows,
retained compatibility helpers and offline SDK evidence. The separate access-library experiment is retired.

A dedicated Azure resource group for future connector E2E tests was created and observed empty
on 2026-09-14. The [deployment runbook](deploy/README.md) owns its non-secret targets, verification evidence and protected lifecycle commands.
Service provisioning, sample data and live CRUD tests remain deferred.

Customer deployment targets and source-project examples were removed or anonymized from the skills.
The optimization snapshot contains portable source and explicitly synthetic records; the cleanup case study preserves anonymized historical measurements.
No capability was retired by that sanitization. Azure lifecycle commands require an explicit subscription.

The [MIT license](LICENSE) covers repository-authored code. Bundled fonts and artwork retain their
separate notices; external runtime dependencies retain their own terms. Read the
[distribution guidance](.github/skills/AGENT-PLUGINS-SKILLS.md) before publishing a derived package.

## Value Adds

### LLM And Agent Access With Minimal Cognitive Load

The [LLM interface](libraries/llm-interface/README.md) supplies a guarded, discoverable API for several-line Foundry calls and streaming agents.
Hosts supply endpoint, deployment and authorized identity, then instructions/tools as needed. Microsoft Agent Framework supplies native provider, tool-loop, event and lifecycle mechanisms.
The implemented alpha and standalone examples are ready for independent testing.
Comparative cognitive-load reduction remains unmeasured; short examples and offline checks do not prove it.

## Pending Tasks

### Connector Skill Retirement

Assess whether the [Azure data connectors](.github/skills/azure-data-connectors/SKILL.md)
and [Azure LLM connectors](.github/skills/azure-llm-connectors/SKILL.md) skills are fully
superseded by the [libraries](libraries/README.md), migrate useful materials and functionality
to their library owners, then delete the original skills once supported callers and contracts
are preserved or explicitly retired. Initial conclusions (2026-09-15): neither skill is fully
superseded. Data gaps include provisioning, discovery/content/estate browsing, observation,
full snapshot/diff verification and live-environment lifecycle; LLM gaps include synchronous/raw
Responses compatibility and the MCP adapter. Both registered MCP servers still launch from the
original skill directories, and the data library is not an in-place API upgrade. All 45 operational
findings now have library-specific guides, but the original runtimes remain intact. The
[retirement assessment](libraries/CONNECTOR_RETIREMENT.md) records remaining migrations and
verification required before deletion.

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
	uncertain-write cases, broader Python/platform coverage and completion of the local
	CyberEye ADX consumer migration. The copied application runs independently; existing data
	and deployment remain borrowed test prerequisites, not newly owned resources.
	[Verification evidence](libraries/azure-data-connectors/VERIFICATION.md) records offline and artifact checks.
- The [live-test design](libraries/azure-data-connectors/tests/live_tests/LIVE_TEST_DESIGN.md)
	covers all ten profiles. The historical empty resource group does not prove live service
	coverage. Gremlin resource-token issuance and driver compatibility, GraphModel beta/capacity,
	service provisioning, role grants and live tests require explicit targets and authorization.

### Agent Optimization Library

- [Research collection](libraries/agent-optimization/README.md): documentation collected;
	runtime features not added. Implementation, dataset/evaluator compatibility, reproducible offline
	tests, authorized live evaluation and artifact publication remain unverified.

### LLM Interface Library

- [Library](libraries/llm-interface/README.md): `0.1.0a1` implements the few-line standalone-call
	and streaming-agent paths with independent offline fixtures. The [validation record](libraries/llm-interface/VALIDATION.md)
	owns current test and artifact evidence. Pending: authorized live Foundry identity/permissions
	and model behavior, actual non-OpenAI provider conformance, broader dependency/Python and
	load coverage, and a fresh coding-assistant usability comparison against Agent Framework.
- LLM adoption into the local investigation template is deferred: Responses/SSE events,
	tool execution and owner-bound conversation state need their own compatibility checks.
	The source investigation project remains unchanged; no live model call ran in the ADX increment.

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
