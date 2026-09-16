# 04. Skills, MCP And Distribution

This chapter incorporates the complete skills migration requirement. The target is removal
of skill-owned runtimes, not a second package family underneath thinner labels.

## Bounded Objective

- **Objective:** supersede skill-owned implementations with canonical libraries and thin
   usable discovery, under [0. Core Objective](0_CORE_OBJECTIVE.md).
- **Done when:** all 28 native, five embedded and eight protocol entries and all 27 current
   MCP tools are migrated or explicitly retired; zero independent skill runtimes remain;
   shipped skill files and logical bytes each fall by at least 50% using CO-1's fixed scope.
   Every retained discovery/adapter entry resolves and its applicable portable check passes.
- **Scope ceiling:** migrate the audited capability/discovery surface, not a new plugin
   platform or unrelated tooling. Generate only entries needed by retained consumers; aliases
   must not preserve obsolete engines or a duplicate manual.
- **Stop condition:** the block's old runtime is absent, its retained public/discovery path
   works and matching refusals pass. Do not delay removal for unknown external compatibility.

## Canonical Ownership And Discovery

Libraries own implementation, contracts, tests, examples, fixtures, operational findings
and any substantive CLI/MCP adapter. A native skill states triggers, prerequisites, selected
public entry point, scope/authority and how to reach canonical guidance. It contains no
independent engine, test/example tree or second operational manual.

Library-backed guidance lives with its capability; generated discoverable `SKILL.md` entries
are emitted under `.github/skills/<task>/` for source-workspace use and into portable plugin
artifacts for installed use. Library-local `SKILL.md` files alone are not registered by a
standard client. Pure procedural skills keep authored guidance at their current owner;
they do not need fake runtime libraries.

Evolve the existing [catalogue](../../.github/skills/catalogue.json) into one canonical
`libraries/capabilities.json` during implementation. Its schema records stable capability
IDs, source/public API owners, profiles/dependencies, configuration/authorization boundary,
tests/status, guidance source, aliases and optional MCP registration. Preserve the current
task metadata during the move. The old catalogue path becomes a generated discovery view,
not a second authoring source. Generated output includes source revision/digests; validation
detects stale entries, unknown aliases and unsupported tool claims.

No runtime imports this repository's `.github` source. An installed plugin receives declared
released packages or a generated wheel/npm artifact set plus canonical guidance/assets.
Relative guide links must resolve inside that distribution or to versioned public docs,
not `../../libraries` in an assumed sibling checkout. Generation grants no credential,
model permission, MCP activation or cloud resource authority.

## Native Skill Inventory

Baseline: 28 native entries. Exact source paths/package/lock deletion manifests are frozen
per implementation batch; the following groups are the required removal outcomes.
Guidance-only rows stay guidance. A legacy-only behavior not selected here is retired.

| ID | Native Skill | Target Outcome And Source Removal |
| --- | --- | --- |
| S01 | [agent-optimization](../../.github/skills/agent-optimization/SKILL.md) | `libraries/agent-optimization` owns selected generation/cohort/evidence-tool/replay runtime; compose shared detector, model and recovery. Remove skill Python/React/scripts/tests and independently editable executable reference pack; generate any portable snapshot from the new owner. |
| S02 | [architecture-placement](../../.github/skills/architecture-placement/SKILL.md) | `repository-inspection` owns executable graph/boundary checking and tests; placement advice remains thin guidance. Existing `.github/tools/arch.py`, if retained, is an installed-API launcher. |
| S03 | [azure-access-management](../../.github/skills/azure-access-management/SKILL.md) | Reuse `entra_auth`/signed access for selected mechanisms. Native CLI/Entra/Easy Auth/MSAL/Bicep/PIM procedures stay guidance. Retire `azaccess` administration engine/MCP and duplicate compatibility runtimes; move useful maps/examples/findings to library guidance. Do not revive a universal access platform. |
| S04 | [azure-cli-infra-management](../../.github/skills/azure-cli-infra-management/SKILL.md) | Guidance only; exact targets, lifecycle commands and receipts remain with deployment owners. |
| S05 | [azure-data-connectors](../../.github/skills/azure-data-connectors/SKILL.md) | Adopt canonical `azdata`; remove skill `src/azdata` v3, independent metadata/locks/tests and old import paths. Translate retained outcomes; retire unselected v3 configuration/envelopes/estate/management behavior. |
| S06 | [azure-llm-connectors](../../.github/skills/azure-llm-connectors/SKILL.md) | `llm_interface` only; remove `azllm`, skill package/examples/tests and duplicate MCP host. No raw compatibility extension to avoid updating callers. |
| S07 | [azure-search](../../.github/skills/azure-search/SKILL.md) | Canonical Search in `azdata`; move useful examples/refusal cases, delete `harness-azure-search` implementation and packaging. Retain task-specific thin guidance if useful. |
| S08 | [azure-sky-styling](../../.github/skills/azure-sky-styling/SKILL.md) | `libraries/azure-sky-styling` owns opt-in CSS/React/assets/gallery and browser checks. Remove the skill-owned source/examples; retain all required notices and rights evidence. |
| S09 | [codebase-cleanup](../../.github/skills/codebase-cleanup/SKILL.md) | `repository-inspection` owns bounded filesystem inventory/comparison; destructive decisions stay in the host procedure. Remove substantive skill scripts/tests/assets after useful schemas/fixtures move. |
| S10 | [content-from-a-store](../../.github/skills/content-from-a-store/SKILL.md) | Library-owned recipe over native `azdata`/identity APIs; host owns publishing/cache/fallback policy. Delete inline identity/fetch implementation and its standalone snippet-test authority. |
| S11 | [deploy-container-apps](../../.github/skills/deploy-container-apps/SKILL.md) | Guidance only; retain one host `deploy/` entry point, never a library-created competing deployment owner. |
| S12 | [event-stream](../../.github/skills/event-stream/SKILL.md) | Reuse `@agentcraft/event-stream`; remove skill frontend runtime and independent npm package/test/example tree. |
| S13 | [frontend-implementation](../../.github/skills/frontend-implementation/SKILL.md) | Guidance only; use native type/build/browser tooling and canonical UI packages. |
| S14 | [ghcp-cli-frontend](../../.github/skills/ghcp-cli-frontend/SKILL.md) | `copilot-terminal` owns PTY/frontend/adapters/examples/tests; remove skill Python/src code. Host supplies private provider credentials, operator policy and state. No OS/multi-user sandbox claim. |
| S15 | [harness-guide](../../.github/skills/harness-guide/SKILL.md) | `repository-inspection` catalogue module owns validation/query/read CLI; remove skill reader/tests. Thin invocation resolves installed catalogue, not a guessed repository path. |
| S16 | [hyperframes-motion](../../.github/skills/hyperframes-motion/SKILL.md) | `hyperframes-tools` owns local runner/verification adapters and examples; use upstream HyperFrames engine. Remove skill executable/npm tree; preserve local-asset/finite-timeline and render-proof constraints. |
| S17 | [investigation-notebook](../../.github/skills/investigation-notebook/SKILL.md) | `investigation-notebook` owns persistence/search/schema/CLI/tests. Remove skill mechanism; never remove actual notes, databases, draft evidence or unrelated installed notebooks. |
| S18 | [managed-identity-model-clients](../../.github/skills/managed-identity-model-clients/SKILL.md) | Migrate to `llm_interface`; delete `modelaccess`, its packaging and duplicate model MCP. A discovery alias may survive, not its execution engine. |
| S19 | [modular-agents](../../.github/skills/modular-agents/SKILL.md) | `modular-agents` owns configuration/tool definition/measurement and native hosted-bundle APIs; `llm_interface` owns execution. Remove skill modules/examples/tests and duplicate loops; host deploy remains separately authorized. |
| S20 | [portable-app-composition](../../.github/skills/portable-app-composition/SKILL.md) | `app-composition`/`appcompose` is the single document-validation/lifecycle owner. Remove skill `appcompose`, demo runtime and independent tests/packaging. Host supplies resolver/config/authorization. |
| S21 | [recoverable-jobs](../../.github/skills/recoverable-jobs/SKILL.md) | `recoverable-jobs`/`workrecovery` owns completed-output recovery, verified commits and tests. Remove skill runtime without touching pending output or operator recovery directories. |
| S22 | [resource-explorer](../../.github/skills/resource-explorer/SKILL.md) | Use canonical registry/content/UI/probes plus `azdata`. Delete old backend/frontend, embedded inventory package and `vendor/azdata`. Retire unselected subscription-wide estate discovery/search; callers adopt declared-source inventory. |
| S23 | [runbook-replay](../../.github/skills/runbook-replay/SKILL.md) | Guidance only; execute and record the owning runbook, not a second deployment implementation. |
| S24 | [signed-dev-access](../../.github/skills/signed-dev-access/SKILL.md) | One signed-access library owns retained signing/verification/client CLI/wire/tests. Delete `devauth` and duplicated contract/runtime; never weaken canonical bytes/replay/host authorization. |
| S25 | [situation-detector](../../.github/skills/situation-detector/SKILL.md) | One `situation_detector` library; remove skill Python package/tests. Host queries/meaning remain outside library. |
| S26 | [source-code](../../.github/skills/source-code/SKILL.md) | One `@agentcraft/source-code`; remove skill frontend/npm/examples/tests runtime and keep generated discovery. |
| S27 | [ui-experience-audit](../../.github/skills/ui-experience-audit/SKILL.md) | Guidance only; no new UI-audit runtime. Observational records and native browser tools remain explicit. |
| S28 | [web-resource](../../.github/skills/web-resource/SKILL.md) | `libraries/web-resource` owns guarded fetch/capture/provenance/catalogue APIs, CLIs and tests. Delete skill `lib` and substantive script copies; preserve robots/rate/public-network safeguards and source rights. |

### Embedded, Protocol And Historical Entries

| Entry | Target |
| --- | --- |
| `creative-agent-optimization` | Optimization-owned workflow guidance; no independent source snapshot/runtime |
| `agent-config-build` | Modular-agent configuration contract and library-owned guidance |
| `foundry-agent-runtime` | Native hosted bundle/runtime adapter using the single model owner |
| `purpose-built-tools` | Tool-design guidance; validation/measurement owned by modular agents/native model API |
| `resource-inventory` | Canonical Resource Explorer; delete separately packaged embedded implementation |

Protocol records retained as procedures: `protocol-capability-modularization`,
`protocol-demonstrate`, `protocol-document`, `protocol-garbage-collect`, `protocol-lean`,
`protocol-regression-loop`, `protocol-restructure`, `protocol-template-app`.
Reconcile their implementation links with library owners; do not copy protocol engines
into a new runtime. The historical `hyperframes-motion` source pointer becomes a generated
alias/notice or is removed. The retired `adx-event-store` runtime stays retired; its owner
is [azdata.event_store](../../libraries/azure-data-connectors/docs/event-store/README.md).

## MCP Tool Migration

Baseline: seven registrations and 27 catalogue-declared tools, each server using skill-root
source loading; Explorer also loads vendored v3 data. Registration is not proof of startup.
The target is one optional library-owned `agentcraft` host, with capability-owned adapters,
enabled only for operator-configured bindings. The table selects names/semantics; old
tool names may appear in breaking-change notes, not as indefinite runtime shims.

| Current Server | Every Current Tool | Target |
| --- | --- | --- |
| `azure-data-connectors` | `azdata_status` | `data_status`: offline configured binding/support description |
| `azure-data-connectors` | `azdata_query_kql`, `azdata_query_gremlin`, `azdata_query_graph`, `azdata_search` | `data_query`: typed configured binding plus allowed dialect/expression/parameters/projection/limits. Service/target/credentials/grants fixed by binding; adapter calls `azdata.query`. No runtime v3 dependency. |
| `azure-llm-connectors` | `azllm_status`, `azllm_ask`, `azllm_embed` | `model_status`, `model_chat`, `model_embed` over installed `llm_interface`; explicit inference grants and bounded native output |
| `managed-identity-model-clients` | `modelaccess_status`, `modelaccess_ask`, `modelaccess_embed` | Same three canonical model tools; retire duplicate server/runtime rather than a second model interface |
| `azure-access-management` | `azaccess_status`, `azaccess_matrix`, `azaccess_role`, `azaccess_scope`, `azaccess_inspect` | Retire administrative MCP surface. Selected native Azure CLI/Entra inspection and policy mapping remain documented procedures, not an added generic access engine. |
| `portable-app-composition` | `appcompose_status`, `appcompose_validate`, `appcompose_demo` | `composition_status`, `composition_validate`, `composition_demo` over installed `appcompose`; demo explicitly synthetic/offline, never arbitrary config code |
| `recoverable-jobs` | `workrecovery_status`, `workrecovery_list`, `workrecovery_stage`, `workrecovery_read` | `recovery_status`, `recovery_list`, `recovery_stage`, `recovery_read`; host-owned authorized storage, bounded payload/read-back and no false commit |
| `resource-explorer` | `resource_explorer_status`, `resource_explorer_tree`, `resource_explorer_content` | `inventory_status`, `inventory_tree`, `inventory_content` over configured registry/public library; no caller resource URL or subscription widening |
| `resource-explorer` | `resource_explorer_search` | Retire estate-search tool; no replacement advertised unless a later distinct capability is approved |

`data_query` is one typed library operation for the data family, not a universal framework
`execute` endpoint. Unsupported binding/dialect/options refuse before I/O. Model, recovery,
inventory and composition retain their own schemas. An unconfigured capability advertises
accurate unavailable status or is not exposed; it never falls back to old code.

Do not require all adapters at core install time. One MCP executable/module selects declared
optional adapters through a trusted allowlist, validates config before start and closes
created resources once. No server, socket, API key prompt or live probe starts on import.
No tool may receive new endpoint, credential, grant, principal or private filesystem root
as untrusted request authority. Recovery staging is an explicit local-state operation.

## Portable Distribution Contract

1. Build wheels/sdists/npm artifacts from canonical owners; declare normal versioned
   requirements. Workspace/editable sources support development only.
2. Build skill/plugin outputs from the same versioned catalogue and guidance sources.
   Retained launchers import installed public entry points and contain no capability rules.
3. A self-contained plugin can bundle release artifacts with hashes/notices. Generated
   build products are not a second hand-maintained source tree. No `vendor/azdata` source
   copy or implicit download of another checkout is accepted.
4. Prove installation/startup in a temporary directory outside the repo with `PYTHONPATH`
   unset, no sibling checkout and no source-root manipulation. Resolve optional dependencies
   from declared artifacts/indexes, then disable undeclared fetching during smoke tests.
5. Run real MCP SDK client/server round trips: discovery/status, configured fixture success,
   no-grant/unknown-binding/malformed-input/target-escalation refusal, budget exhaustion,
   cancellation and teardown. Stdio protocol output contains no logs/secrets/customer data.
6. Remove old registration/catalogue tool claims in the same source-removal batch. If the
   new adapter is not ready, declare it unavailable/retired; do not leave an active broken
   launcher or silently re-enable legacy code.
7. Keep installation, discovery, MCP activation, runtime authorization, Azure grants and
   package publication as separate actions. A successful install is none of the others.

The future plugin must retain necessary guidance/assets in the installed package even if
no public docs site/registry publication exists yet. Authored skill/plugin contents are
verified against generated outputs before distribution. Loading a library-local skill
does not bypass the client's discovery rules.

## Removal Evidence

Each batch records exact old roots and replacement symbols, retained/retired outcomes,
consumer work, generated discovery, adapter metadata and tests. Search imports, entry
points, registries, build inputs and scripts for links into removed code. Delete those
links, not the intended source-removal outcome. Unknown external users receive a breaking
change notice; they do not create an indefinite compatibility promise.

Test evidence belongs to the selected target contract. Keep positive/refusal/integrity
knowledge; retire obsolete API-shape tests with reasons. Skill/legacy removal can be done
while a host is pending; full portfolio status cannot claim that host works until its new
workflow passes. Saved user data, immutable receipts, notices and provenance are not runtime
duplicates and remain protected.

Next: [05. Documentation And Developer Experience](05_DOCUMENTATION_AND_DEVELOPER_EXPERIENCE.md).