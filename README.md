# Agentcraft

Framework for building end-to-end agentic applications. Investigation's runtime dependencies
belong in libraries; other capabilities and workflow guidance belong in skills.
Start with [documentation](docs/README.md); use the
[workspace guide](libraries/README.md) for installation and the canonical catalogue.

Investigation's latest completed split acceptance is listed below. Subsequent
[generic reuse migrations](template_apps/investigation_app/docs/LIBRARY_MIGRATION.md#generic-reuse-audit)
are source-implemented; integrated backend/browser checks and discovery regeneration remain pending.
Other application and cloud statements remain dated records, not fresh live checks.

The Hillclimber writeup app moved on 2026-09-18 to
`/home/hanchoong/han-ops-center/agentcraft_doc app`, including its Vocs site, bundled demo,
dataset example, active deployment tooling and release receipts. Quote the path's space.
Local site and demo production builds pass at the destination. `rg-singtel-ticket-poc` and its contained
resources were deleted and independently verified absent on 2026-09-16.
The original source remains available. The [live writeup](https://ca-agentcraft-writeup.wonderfulmoss-6cbdac9f.eastus2.azurecontainerapps.io)
now runs by itself in `rg-agentcraft-testing`, `eastus2`, with only its required hosting resources.
[Deployment details](deploy/README.md#writeup-deployment) own configuration, read-back and
desktop/mobile browser evidence. Corporate sign-in remains required; interactive sign-in and
first-use consent are not yet verified.

The [Content Understanding recipe](.github/skills/azure-content-understanding/SKILL.md)
owns native async Microsoft SDK extraction, its uv manifest/lock, contracts,
tests and recorded report outputs. The [datacrafting testbed](testbeds/datacrafting/README.md)
now has an [independently reviewed Operations v3 dataset](testbeds/datacrafting/operations-crafting/REVIEW.md):
14 detection and 8 conditional-action cases with 75,908 synthetic SCADA rows and
322 alarms. More than twice the v2 counts were added as visible noise per case.
154 tests and persisted replay pass; this validates the synthetic process, not
training robustness or real telemetry integration. The extra Function wrapper remains removed.
Source PDFs and CU outputs remain intact. No new cloud calls or teardown occurred;
[historical deployment and cleanup records](testbeds/datacrafting/deploy/README.md) identify
the last observed resources, including the CU service and retired DI account. Diagram
semantics, current cloud liveness and exact cost remain unverified.

## Agent Team

Local [agent coordination](.github/agents/README.md) uses `overseer` as the normal user contact,
`orchestrator` for one verifiable increment at a time, and optional specialists. Teams return
evidence before follow-on work is commissioned. Shared skills and safety authorities remain active.

[AgentCraft Overseer v1.6](.github/agents/agentcraft-overseer.agent.md) specializes this team for
data-understanding-first, measured solution improvement, with strict brevity, a validated project constitution
with explicit modification levers. Direct children are exactly [agentcraft-orchestrator](.github/agents/agentcraft-orchestrator.agent.md),
archivist and [note scribe](.github/agents/note_scribe.agent.md). Domain orchestrator owns assigned stages/iterations
and pilots all candidates/specialists; overseer owns mission alignment, strategic priorities, authorization/criteria
changes and evidence review. No direct test-subject exception. Definition/preflight checks only;
native client activation and live mission behavior are not certified by those checks.
Dedicated [archivist](.github/agents/archivist.agent.md) owns the process's version/timestamp JSON record
bundles, exact constitution/source snapshots and verified decision-to-outcome references. The overseer
retains decisions; note scribe owns lessons. Total automatic capture and tested live reversion are not implied.

## Current Foundation

The [8-member uv workspace](libraries/README.md#current-state) sits within ten retained
Investigation-used library directories, alongside four npm packages.
Native async `azdata` owns data access and
`llm_interface` is the single model/agent engine. Investigation composes these public
owners; raw-model compatibility and synchronous adapters are retired, not providers.

The skill-owned [framework](.github/skills/harness-guide/framework/README.md) provides description, catalogue lookup,
explicit bindings and an opt-in offline MCP host. Its callable composed example runs
synthetic native HTTP data/rules/model work with real filesystem recovery. Source checks
and artifact identities are distinguished in the historical [release receipt](.github/skills/harness-guide/framework/distribution/release-candidate.json).
Eleven unused library owners moved into skills; twelve duplicate skill directories are removed.
[Library scope](libraries/README.md#library-scope) records retained owners and moved guidance.
[capabilities.json](libraries/capabilities.json) owns generated discovery.
The duplicated in-checkout portable plugin tree is removed; the
[workspace guide](libraries/README.md#discovery-and-mcp) owns source-only discovery
and explicit self-contained external exports. Regeneration and post-reuse local Investigation
acceptance pass; no whole-project size or RAM improvement is established.

[Agent optimization](.github/skills/agent-optimization/SKILL.md) implements local frozen-cohort
evaluation, immutable generations, evidence and persisted replay. Its research collection
is separate: model-quality improvements, live evaluation and cloud observability are not
established by local runtime or synthetic tests. There is no optimization source snapshot.

The [overseer self-optimization demonstration](demonstration_project/README.md) has an authorized
local data-understanding constitution and a dispatched `local-dev-test-subject`. Two recorded
exploratory iterations reproduced CSV-prefix observations and corrected a label-extraction tool gap.
Scored comparison, independent evaluation and performance gains remain unverified; unknown data
properties and targets are active discovery work, not permission blockers.
HIKARI-2021 and UWF-ZeekData22 tables are acquired with a scripted, hash-verified download sequence;
payloads are Git-ignored. Cyber detection quality and held-out evaluation remain unverified.
The former Optimization Framework is retained intact as a Git-ignored local reference beneath
that project, not an active runtime. Its historical partial results do not establish arbitrary
code execution, independent comparison, full Investigation acceptance or production cloud proof.

## Recorded Checks

The historical [conformance record](.github/skills/harness-guide/framework/CONFORMANCE.md) separates returned source
checks, dated artifacts, native-client acceptance and unverified live/platform requirements.
Counts from overlapping commands are not a single portfolio total.

- [Investigation reuse acceptance](template_apps/investigation_app/docs/LIBRARY_MIGRATION.md#verification-boundary):
  610 backend/deploy tests, 29 frontend tests, production build and 43 signed native-browser
  checks passed. Live acceptance: 23 API checks, 72 scanner/catalogue checks, 40 Investigation
  checks and 24 Agent Editor checks; results and saved versions read back. Local source
  acceptance does not recertify historical release artifacts or guarantee model outputs.
- [Native client closeout](.github/skills/harness-guide/framework/distribution/native-client-closeout.json) and
  [guidance deduplication](.github/skills/harness-guide/framework/distribution/guidance-dedup.json): historical CLI
  installation, discovery, disable and cleanup. Upstream malformed-manifest acceptance remains
  documented separately from mandatory first-party validation.
- [Release receipt](.github/skills/harness-guide/framework/distribution/release-candidate.json) and
  [independent reader](.github/skills/harness-guide/framework/distribution/independent-reader.json): recorded
  offline installation, repeated results, refusal recovery and cleanup. Later source/text
  changes are recorded by the historical [Investigation closeout](.github/skills/harness-guide/framework/distribution/investigation-closeout.json);
  no publication is implied.

[Measured simplification](template_apps/investigation_app/docs/LIBRARY_MIGRATION.md#closeout-reduction):
original runtime/config scope 190 -> 114 files and 29,046 -> 15,539 lines. This closeout
removes two runtime files/171 lines, plus 305 generated mirror and 191 build/cache files.
Expanded end-to-end tests increase total app bytes; no whole-project size, RAM or latency
improvement is inferred from unrelated active data changes.

Historical Perth, Cosmos and MITRE observations remain labeled in the migration record.
Custom Optimizer received only five approved dependency/path edits; it was not executed
or otherwise modified. Existing changes remain intact.

## Retained Cloud Records

Perth ADX is Running with idle auto-stop disabled through its existing deployment owner.
Continuous compute charges apply; manual stops, external schedules and outages are not prevented.

A dedicated Azure resource group for future connector E2E tests was created and observed empty
on 2026-09-14. The [deployment runbook](deploy/README.md) owns its non-secret targets, verification evidence and protected lifecycle commands.
Service provisioning, sample data and live CRUD tests remain deferred.

## Pending Acceptance

- Beyond Investigation's authorized existing targets, live provider acceptance still needs
  explicit targets, identities and data-processing/inference authority. Investigation's
  [local request-count quota is removed](template_apps/investigation_app/deploy/README.md#current-scope);
  native per-run limits remain. Offline fixtures do not establish broader provider acceptance.
- [Azure access guidance](libraries/entra-auth/docs/skills/azure-access-management.md) owns native-first
  identity workflows. Investigation's frontend sign-in migration is not started; preserve
  tenant/record authorization, cookies/CSRF, session expiry/revocation and signed-agent
  refusals until separate deployed acceptance passes. Auth configuration is unchanged here.
- [Data verification](libraries/azure-data-connectors/VERIFICATION.md) and
  [model validation](libraries/llm-interface/VALIDATION.md) retain provider, dependency,
  platform and load limitations. App/library source passes are not whole-system acceptance.
- Genuine pinned ontology inputs were found outside the checkout and tested read-only;
  they are no longer a missing-input blocker. Deployed lifecycle, additional platform/
  dependency floors and complete static typing remain unverified; typing markers are partial.
- Independent-reader evidence covers its recorded three offline tasks, not a fresh run
  of this documentation revision. Native plugin installation is verified separately.
  Comparative effort, memory, latency and model-quality gains are not claimed.

## Limits

- Live cloud access, paid model calls and deployments require operator configuration and authorization.
- Installation and guidance do not enable MCP, authenticate callers or authorize tools.
- Final artifact acceptance and publication are separate; no public registry availability is claimed.
- New contributions, datasets and third-party assets need their own provenance and rights review.

The [MIT license](LICENSE) covers repository-authored code. Bundled fonts and artwork retain their
separate notices; external runtime dependencies retain their own terms. Review the
[release contract](libraries/README.md#release-contract) before publishing a derived package.

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
