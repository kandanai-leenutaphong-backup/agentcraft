# Agentcraft

Framework for building end-to-end agentic applications. Runtime capabilities belong

in libraries; authoring tools and workflow guidance belong in skills.
Start with [documentation](docs/README.md); use the
[workspace guide](libraries/README.md) for installation and the canonical catalogue.

Application and cloud statements below are retained records, not live checks rerun
for this documentation recovery increment.

The [Hillclimber writeup app](doc_app/README.md) now lives in `doc_app/`, including its
Vocs site, bundled demo, dataset example and [deployment details](doc_app/deploy/README.md).
Local site and demo production builds pass. `rg-singtel-ticket-poc` and its contained
resources were deleted and independently verified absent on 2026-09-16.
The original source remains available. The [live writeup](https://ca-agentcraft-writeup.wonderfulmoss-6cbdac9f.eastus2.azurecontainerapps.io)
now runs by itself in `rg-agentcraft-testing`, `eastus2`, with only its required hosting resources.
[Deployment details](deploy/README.md#writeup-deployment) own configuration, read-back and
desktop/mobile browser evidence. Corporate sign-in remains required; interactive sign-in and
first-use consent are not yet verified.

The [Content Understanding recipe](libraries/content-understanding/README.md)
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

## Current Foundation

The [16-member uv workspace](libraries/README.md#current-state) has refreshed locks.
`agentcraft` composes specialized APIs; native async `azdata` owns data access and
`llm_interface` is the single model/agent engine. Investigation composes these public
owners; raw-model compatibility and synchronous adapters are retired, not providers.

The [framework](libraries/framework/README.md) provides description, catalogue lookup,
explicit bindings and an opt-in offline MCP host. Its callable composed example runs
synthetic native HTTP data/rules/model work with real filesystem recovery. Source checks
and artifact identities are distinguished in the [release receipt](libraries/framework/distribution/release-candidate.json).
Authoring-only Azure Sky and HyperFrames bundles now live in skills, not runtime libraries;
[library scope](libraries/README.md#library-scope) records admission criteria and remaining candidates.
[capabilities.json](libraries/capabilities.json) owns generated discovery.
The duplicated in-checkout portable plugin tree is removed; the
[workspace guide](libraries/README.md#discovery-and-mcp) owns retained installed guidance
and explicit self-contained external exports.

[Agent optimization](libraries/agent-optimization/README.md) implements local frozen-cohort
evaluation, immutable generations, evidence and persisted replay. Its research collection
is separate: model-quality improvements, live evaluation and cloud observability are not
established by local runtime or synthetic tests. There is no optimization source snapshot.

## Recorded Checks

The [conformance record](libraries/framework/CONFORMANCE.md) separates returned source
checks, dated artifacts, native-client acceptance and unverified live/platform requirements.
Counts from overlapping commands are not a single portfolio total.

- [Investigation acceptance](template_apps/investigation_app/docs/LIBRARY_MIGRATION.md#current-acceptance):
  572 backend/deploy tests, 532 native library checks, 51 framework/core tests, 23 frontend
  tests and 42 signed-browser checks passed against installed packages, with no skips.
  Chat, diagnosis, data/knowledge retrieval, graph and authored agent versions read back.
- [Native client closeout](libraries/framework/distribution/native-client-closeout.json) and
  [guidance deduplication](libraries/framework/distribution/guidance-dedup.json): actual CLI
  installation, discovery, disable and cleanup. Upstream malformed-manifest acceptance remains
  documented separately from mandatory first-party validation.
- [Release receipt](libraries/framework/distribution/release-candidate.json) and
  [independent reader](libraries/framework/distribution/independent-reader.json): recorded
  offline installation, repeated results, refusal recovery and cleanup. Later source/text
  changes are verified by the [Investigation closeout](libraries/framework/distribution/investigation-closeout.json);
  no publication is implied.

[Measured simplification](template_apps/investigation_app/docs/LIBRARY_MIGRATION.md#closeout-reduction):
original runtime/config scope 190 -> 114 files and 29,046 -> 15,539 lines. This closeout
removes two runtime files/171 lines, plus 305 generated mirror and 191 build/cache files.
Expanded end-to-end tests increase total app bytes; no whole-project size, RAM or latency
improvement is inferred from unrelated active data changes.

Historical Perth, Cosmos and MITRE observations remain labeled in the migration record.
Custom Optimizer was not changed or executed in this closeout; content/Git fingerprints
were read solely to verify the exclusion. Existing changes remain intact.

## Retained Cloud Records

The [2026-09-17 activation](deploy/records/investigation-live-verification-20260917.json)
started Perth ADX and verified real scan/evidence, Search, Cosmos, model chat, summary and
corrected diagnosis. Auto-stop remains disabled; continuous compute charges apply.
The approved 20 model/100 data attempt allowance is exhausted and enforced. Further live
testing requires renewed authority; no new resource, role grant or Azure data write occurred.

A dedicated Azure resource group for future connector E2E tests was created and observed empty
on 2026-09-14. The [deployment runbook](deploy/README.md) owns its non-secret targets, verification evidence and protected lifecycle commands.
Service provisioning, sample data and live CRUD tests remain deferred.

## Pending Acceptance

- The bounded live Investigation activation above is verified; broader service coverage,
  renewed request allowances and deployed sign-in remain separate. Offline fixtures and
  one live workflow do not prove every provider guarantee or model quality.
- [Azure access guidance](.github/skills/azure-access-management/SKILL.md) owns native-first
  identity workflows. Investigation's frontend sign-in migration is not started; preserve
  tenant/record authorization, cookies/CSRF, session expiry/revocation and signed-agent
  refusals until separate deployed acceptance passes. Auth configuration is unchanged here.
- [Data verification](libraries/azure-data-connectors/VERIFICATION.md) and
  [model validation](libraries/llm-interface/VALIDATION.md) retain provider, dependency,
  platform and load limitations. App/library source passes are not whole-system acceptance.
- Genuine pinned ontology inputs were found outside the checkout and tested read-only;
  they are no longer a missing-input blocker. Production lifespan, additional platform/
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
[Microsoft&#39;s Trademark &amp; Brand Guidelines](https://www.microsoft.com/legal/intellectualproperty/trademarks/usage/general).
Use of Microsoft trademarks or logos in modified versions of this project must not cause confusion or imply Microsoft sponsorship.
Any use of third-party trademarks or logos are subject to those third-party's policies.
