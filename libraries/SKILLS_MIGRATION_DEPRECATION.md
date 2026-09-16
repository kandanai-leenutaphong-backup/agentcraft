# Skills Migration And Deprecation

> **Superseded for the unified migration:** [final specification](../specs/20260916T045818Z_UNIFIED_LIBRARY_SPEC/README.md).
> Retained as a historical input, not a separate active plan. The final spec's library-first
> decisions, mandatory runtime removal, app-adoption status and verification gates control.

**Required direction, 2026-09-16: libraries own reusable capability code; skills discover
and explain it; applications adapt to library contracts; old skill runtimes are removed.**

This document records requirements and a source inventory. It does not execute migration,
delete files, publish packages, change MCP registrations or authorize cloud operations.

## Binding Requirements

1. **Libraries own implementations, contracts, tests, examples and operational guidance.**
   Reuse an existing capability owner before creating a package. Native SDKs and frameworks
   retain their responsibilities. Do not create one library per skill merely to move files.
2. **Keep thin discovery entries under `.github/skills/`.** An entry states when to use a
   capability, prerequisites, the supported public API and where its authoritative guidance
   lives. A library-local skill file can be canonical, but needs configured discovery or a
   generated discoverable entry; moving a file alone does not register it with the client.
3. **MCP adapters consume library public APIs through declared dependencies.** Installed
   plugins must work without a sibling workspace checkout, source-path injection or an old
   skill runtime. Loading guidance, installing a dependency and enabling MCP are distinct.
4. **Remove old runtimes as the migration outcome, not a conditional future cleanup.**
   Applications, scripts and MCP hosts change to use the selected library contract. Missing
   legacy parity, unchanged application imports and unknown external consumers are not vetoes
   on removal. Publish breaking changes and track consumer work; do not keep a second runtime
   until every consumer catches up.

The [portfolio design](DESIGN.md) supplies the ownership direction. This requirement supersedes
the preservation-first removal policy in [Connector Skill Retirement](CONNECTOR_RETIREMENT.md)
and its summaries: those records remain dated evidence of differences, not a requirement to
reproduce every legacy feature before deleting its implementation.

## Library First, Not Legacy First

- Design the library for a coherent capability, a usable public contract, maintained upstream
  dependencies and explicit guarantees. An existing application's shape does not dictate it.
- Translate or rewrite application call sites, session handling, configuration and tests at
  the host. Keep application policy, domain records, authorization decisions and deployments
  out of foundational libraries.
- A legacy-only feature has two outcomes: implement it because it belongs in the library's
  intended capability, or retire it. Its mere existence is not a requirement to reproduce it.
- Do not add caller-name switches, raw-option escape hatches, duplicate tool loops, permanent
  compatibility packages or copied implementations to preserve old application behavior.
- Retain useful positive and refusal tests against the new contract. Retire tests whose only
  purpose is an abandoned API shape; do not turn a missing feature promised by the selected
  new contract into a passing refusal.
- Preserve authentication, ownership, bounded execution, integrity, honest partial results
  and cleanup guarantees. Library-first design does not authorize weaker safety controls.

The [library development playbook](LIBRARY_DEV_SKILL.md) and
[workspace guide](README.md) own library acceptance and packaging. Caller usability means
making the intended API usable, not preserving every historical caller unchanged.

## Target Ownership

| Concern | Target Owner | What May Remain In A Skill |
| --- | --- | --- |
| Reusable Python, TypeScript, React, CSS and CLI behavior | Existing or deliberately selected capability library | No independently maintained implementation |
| Contracts, regression tests, examples, fixtures and operational findings | Same library as the behavior | Links or generated distribution assets, not a second authority |
| Task routing and agent workflow | Thin native skill entry; library-owned usage guidance where applicable | Triggers, prerequisites, ordered procedure, references and explicit limitations |
| MCP request validation and public API adaptation | Library-owned optional adapter or declared adapter package | A small launcher that imports an installed public entry point |
| Operator configuration, access grants and application policy | Consuming host or plugin composition root | Instructions naming the authority, never request-supplied grants |
| Deployment targets, provisioning sequence and receipts | Owning `deploy/` directory | Link to the operator entry point; no competing deployment mechanism |
| Pure procedural skills | Existing guidance owner | Procedure and reference links; no artificial runtime package |

A thin entry need not fit an arbitrary line count. It must not contain a second contract,
embedded implementation, separately maintained example tree or competing operational manual.
Small invocation scripts are adapters only when they contain no capability rules.

## Distribution Requirements

- Declare imported packages and supported versions in the importing package's metadata.
  Development workspace links do not replace distributable dependency requirements.
- Generate discoverable entries or portable bundles from their canonical owner. Record the
  source revision and artifact identity; never maintain a handwritten runtime copy in skills.
- A generated bundle may contain release artifacts when a plugin needs self-contained
  distribution. It is a build product, not another source owner or an indefinite legacy path.
- Prove installation and MCP startup outside the repository, without editable siblings,
  `PYTHONPATH` tricks or undeclared downloads. Supply required dependencies through declared
  artifacts; lack of registry publication is a packaging task, not permission to vendor legacy.
- Keep installation free of implicit live access. Exercise configured fixture success and
  matching denial, malformed-input, bounds/budget and cleanup behavior for retained MCP tools.
- MCP tool names and schemas may change with the selected contract. Update registrations,
  discovery metadata and callers together; old wire compatibility is not a library constraint.

## Source Scan

Observed on 2026-09-16 from the [skill catalogue](../.github/skills/catalogue.json), actual
skill directories, package metadata, payload roots, representative MCP imports and existing
library manifests. This is an ownership and removal inventory, not an API-parity audit or
fresh runtime test report. Environments, caches and build outputs are not source owners.

- **28 native skill directories**, each containing its own discovery entry.
- **Five embedded entries**, owned by optimization, modular agents and resource exploration.
- **Eight protocol records**, whose authored procedures live under
  [protocols](../.github/protocols/README.md), not as additional native skill directories here.
- **Seven MCP registrations and 27 catalogue-declared tools** in the
  [launch manifest](../.github/mcp.json) and catalogue. Declaration is not observed server startup.
- **27 Python/npm manifests inside skills**, including nested compatibility and vendor packages.
  This is a manifest count, not 27 independent capabilities or proof that every package installs.

The [existing library inventory](README.md) identifies available destinations; the
[framework audit](FRAMEWORK_MIGRATION.md) supplies the broader contract comparison.
The table below is a dated migration requirement, not a second machine registry. Extend or
reconcile the existing catalogue when implementing the change; do not maintain competing lists.

### All Native Skills

**Reuse** means a library owner exists, not that it is drop-in compatible. **Establish** means
the indicated library boundary is proposed, not implemented; select its intended outcomes and
remove the old skill runtime in that migration. **Guidance** means no new runtime package is
justified. A proposed destination does not confer a permanent right to retain the old runtime.

| Native Skill | Observed Payload | Required Library-First Disposition |
| --- | --- | --- |
| [agent-optimization](../.github/skills/agent-optimization/SKILL.md) | Python/React package, embedded workflow, reference-pack assets, scripts and tests | **Establish** runtime ownership within [agent-optimization](agent-optimization/README.md), currently research-only. Select the intended optimization contract; remove the skill implementation and independently maintained executable reference pack. Retain provenance or generate artifacts from the new owner. |
| [architecture-placement](../.github/skills/architecture-placement/SKILL.md) | Architecture checker CLI, requirements and tests | **Establish** a bounded architecture-checking library/tool package or retire the executable checker. Keep placement advice as guidance; do not create an application framework around the checker. |
| [azure-access-management](../.github/skills/azure-access-management/SKILL.md) | `azaccess`, capability data, MCP, API/browser compatibility packages and deployment assets | **Reuse** [entra-auth](entra-auth/README.md) for selected caller-authentication primitives. **Establish** separate administration ownership only for retained planning/inspection behavior; native Entra/Azure CLI/Bicep procedures remain guidance. Remove compatibility runtimes, not host authorization. Do not revive a universal access framework to preserve old helpers. |
| [azure-cli-infra-management](../.github/skills/azure-cli-infra-management/SKILL.md) | Native Azure CLI procedure | **Guidance.** Keep target/authority/ownership workflow; executable deployment sequences belong to the consuming deployment owner. No library merely to wrap CLI commands. |
| [azure-data-connectors](../.github/skills/azure-data-connectors/SKILL.md) | `azdata` 3.4.0, broad read/write/operator APIs, MCP and tests | **Reuse** [azdata v4](azure-data-connectors/README.md). Remove skill `src/azdata` and its independent package surface. Select library-supported CRUD/operator outcomes; translate consumers or retire other v3 behavior. No requirement to preserve `AzureDataConfig`, old result envelopes or every provisioning/discovery helper. |
| [azure-llm-connectors](../.github/skills/azure-llm-connectors/SKILL.md) | `azllm`, synchronous/asynchronous model clients, MCP and tests | **Reuse** [llm-interface](llm-interface/README.md). Remove `azllm`; move callers to its intended sessions, streaming, options and budgets. Do not add raw SDK escape hatches for old consumers. Existing [azure-llm-compat](azure-llm-compat/README.md) is transitional code to retire, not the target home for another legacy client. |
| [azure-search](../.github/skills/azure-search/SKILL.md) | Separate `harness-azure-search` Python package and tests | **Reuse** the Search adapter in [azdata](azure-data-connectors/CONTRACT.md). Use [search-read-adapter](search-read-adapter/README.md) only where that distinct contract remains justified. Move useful examples/refusal cases, remove the separate Search implementation; keep specialized discovery guidance if useful. |
| [azure-sky-styling](../.github/skills/azure-sky-styling/SKILL.md) | CSS/React exports, galleries, fonts/artwork, scripts and browser tests | **Establish** a styling/asset library if retaining this visual capability. Move source, examples, browser tests and redistribution notices together; remove the skill-owned implementation and galleries. Keep only discovery and library references. |
| [codebase-cleanup](../.github/skills/codebase-cleanup/SKILL.md) | Filesystem inventory/comparison scripts, assets and tests | **Establish** a bounded cleanup-analysis tool library or retire those scripts. Keep destructive-operation authority in the host workflow. Migrate the actual inventory/comparison rules and tests, not a copied script tree behind a new entry. |
| [content-from-a-store](../.github/skills/content-from-a-store/SKILL.md) | Inline Python token/fetch implementation and snippet selftest | **Reuse** maintained identity/data APIs and library-owned examples; remove the inline implementation and its separate test authority. Keep content caching, fallback, purge and publishing policy host-owned unless a justified shared capability is selected. No handwritten identity transport just to preserve the example. |
| [deploy-container-apps](../.github/skills/deploy-container-apps/SKILL.md) | Deployment workflow guidance | **Guidance.** Keep native deployment procedure and prerequisites. Target configuration, scripts and receipts remain with the owning deployment directory, not a new generic runtime. |
| [event-stream](../.github/skills/event-stream/SKILL.md) | Separate `@harness/event-stream` TypeScript source package | **Reuse** [event-stream](event-stream/README.md). Remove skill `frontend/` and its independent package metadata; import the library from consumers and generated examples. |
| [frontend-implementation](../.github/skills/frontend-implementation/SKILL.md) | Frontend workflow and references | **Guidance.** Route to the appropriate UI libraries and native build/browser tooling; no runtime to extract merely because it is a skill. |
| [ghcp-cli-frontend](../.github/skills/ghcp-cli-frontend/SKILL.md) | React/xterm source, Python PTY runtime, examples and tests | **Establish** one terminal capability library with distinct Python/frontend packages as needed. Keep provider credentials, tool authorization and local-operator policy host-owned. Remove skill `src/` and `python/`; preserve necessary provenance/notices at the library owner. |
| [harness-guide](../.github/skills/harness-guide/SKILL.md) | Catalogue reader/search CLI and tests | **Establish** library/tool ownership for catalogue validation and lookup. Host supplies catalogue locations; keep native metadata under its declared owner. Remove the skill-local reader implementation; a launcher may remain. |
| [hyperframes-motion](../.github/skills/hyperframes-motion/SKILL.md) | npm package, pinned runner/tool scripts, examples and tests | **Establish** ownership for useful local rendering/verification adapters, or use upstream tooling directly. Do not fork the upstream motion engine. Move local contracts, examples, tests and notices; retire the skill-owned executable tree. |
| [investigation-notebook](../.github/skills/investigation-notebook/SKILL.md) | Portable notebook mechanism, schemas/templates and tests | **Establish** a notebook library/tool owner for persistence, search and validation. Keep note-writing procedure discoverable. Remove the skill mechanism after extraction; never treat actual user notes/databases as removable runtime source. |
| [managed-identity-model-clients](../.github/skills/managed-identity-model-clients/SKILL.md) | Independent `modelaccess` package, MCP, examples and tests | **Reuse** [llm-interface](llm-interface/README.md), not a second identity/model client. Remove `modelaccess`; translate supported use cases to the selected model contract. Merge or alias overlapping model guidance where useful; discovery aliases do not require runtime shims. |
| [modular-agents](../.github/skills/modular-agents/SKILL.md) | Configuration/tool/hosting modules, embedded workflows, examples and deployment CLI | **Establish** ownership for retained configuration and hosted-bundle behavior; **reuse** [llm-interface](llm-interface/README.md) and native Agent Framework for execution where selected. Remove skill-owned modules and duplicate model/tool execution. Host deployment remains separately authorized and owned. |
| [portable-app-composition](../.github/skills/portable-app-composition/SKILL.md) | `appcompose`, demo capabilities, MCP and tests | **Establish** the composition library as the single owner of document validation, dependency ordering and lifecycle. Remove skill `appcompose/`; keep actual application resolver/configuration/authorization in the host. |
| [recoverable-jobs](../.github/skills/recoverable-jobs/SKILL.md) | `workrecovery`, MCP, examples and refusal/recovery tests | **Establish** the recovery library; remove skill `workrecovery/`. Preserve completed-output integrity, verified-commit and failure behavior for the chosen contract. Protect operator recovery directories and pending output during package removal. |
| [resource-explorer](../.github/skills/resource-explorer/SKILL.md) | Backend/frontend packages, embedded inventory package, contracts and vendored `azdata` 3.4.0 | **Reuse** [resource-explorer](resource-explorer/README.md) and [azdata](azure-data-connectors/README.md). Remove legacy backend/frontend/inventory implementations and `vendor/azdata`; adapt MCP/UI consumers to the library's supported tree/content contract, not the reverse. |
| [runbook-replay](../.github/skills/runbook-replay/SKILL.md) | Replay procedure and reference templates | **Guidance.** Keep evidence and authorization procedure. Execute the owning application's runbook; do not create another deployment implementation. |
| [signed-dev-access](../.github/skills/signed-dev-access/SKILL.md) | Independent `devauth` package, signing scripts, wire documentation and tests | **Reuse** [signed-dev-access](signed-dev-access/README.md). Put retained signing/verification behavior behind its selected public API; change callers where needed. Remove `devauth` and duplicate test/contract ownership without weakening replay or authorization checks. |
| [situation-detector](../.github/skills/situation-detector/SKILL.md) | `harness-situation-detector` Python battery and tests | **Reuse** [situation-detector](situation-detector/README.md). Remove skill `python/` and its package/tests; keep canonical regression cases at the library and application-specific queries in their host. |
| [source-code](../.github/skills/source-code/SKILL.md) | Separate `@harness/source-code` React/Shiki source package | **Reuse** [source-code](source-code/README.md). Remove skill `frontend/` and its independent npm package. Move examples and rendering/refusal coverage to the library owner. |
| [ui-experience-audit](../.github/skills/ui-experience-audit/SKILL.md) | Audit procedure | **Guidance.** Keep observational workflow; browser and geometry tools remain explicit dependencies, not a new UI-audit runtime. |
| [web-resource](../.github/skills/web-resource/SKILL.md) | `harness-web-resource`, guarded acquisition library, CLIs, collections and tests | **Establish** one acquisition library/tool owner. Remove skill `lib/` and substantive script implementations; share URL guards/provenance logic through public APIs. Preserve source provenance and redistribution limits; acquired evidence is not automatically safe to delete or publish. |

### Embedded And Historical Entries

| Entry | Required Disposition |
| --- | --- |
| `creative-agent-optimization` | Its parent optimization owner owns runtime and examples. Retain a discoverable workflow only if it remains a useful task entry. |
| `agent-config-build` | Configuration compilation belongs to the selected modular-agent owner, not an independently copied embedded module. |
| `foundry-agent-runtime` | Adopt the selected model/framework and hosted-runtime contracts; do not preserve another execution engine for old callers. |
| `purpose-built-tools` | Keep tool-design guidance; retained validation/measurement code needs one declared owner, composed with the model/framework API. |
| `resource-inventory` | Use the canonical resource-explorer library; remove the separately packaged embedded implementation. |

The catalogue also contains a legacy `hyperframes-motion` source pointer. It is not another
native skill or a reason to preserve a second runtime. Reconcile aliases and source pointers
with the selected discovery entry during migration. The already-retired `adx-event-store`
skill has a canonical [event-store owner](azure-data-connectors/docs/event-store/README.md);
do not recreate it as a standalone runtime to satisfy an old import path.

## MCP Migration Inventory

All seven inspected servers manipulate `sys.path` to load their skill-owned packages;
Resource Explorer additionally injects a vendored `azdata` path. All seven registrations
currently launch scripts beneath skills. This is the current removal work, not the target
distribution contract. A small skill launcher may remain only when it loads installed APIs.

| Current Server / Source | Catalogue-Declared Tools | Required Target |
| --- | --- | --- |
| [azure-data-connectors](../.github/skills/azure-data-connectors/scripts/mcp_server.py) | `azdata_status`, `azdata_query_kql`, `azdata_query_gremlin`, `azdata_query_graph`, `azdata_search` | Adapter over installed `azdata` v4 public requests/results. Remove v3 imports and skill-root source injection; drop tools outside the selected library capability rather than retain v3. |
| [azure-llm-connectors](../.github/skills/azure-llm-connectors/scripts/mcp_server.py) | `azllm_status`, `azllm_ask`, `azllm_embed` | Adapter over `llm_interface`; change tool schemas/results when necessary. Remove `azllm` dependency and old startup environment. |
| [managed-identity-model-clients](../.github/skills/managed-identity-model-clients/scripts/mcp_server.py) | `modelaccess_status`, `modelaccess_ask`, `modelaccess_embed` | Converge with the selected model adapter. Remove duplicate `modelaccess` runtime/server where one tool surface suffices; do not retain both engines for tool-name compatibility. |
| [azure-access-management](../.github/skills/azure-access-management/scripts/mcp_server.py) | `azaccess_status`, `azaccess_matrix`, `azaccess_role`, `azaccess_scope`, `azaccess_inspect` | Installed administration library API for retained read-only inspection/planning, or remove the corresponding tools. Caller authentication and administrative inspection are different capabilities. |
| [portable-app-composition](../.github/skills/portable-app-composition/scripts/mcp_server.py) | `appcompose_status`, `appcompose_validate`, `appcompose_demo` | Installed composition library and library-owned demo. Host supplies configuration/allowlist; no skill-local `appcompose`. |
| [recoverable-jobs](../.github/skills/recoverable-jobs/scripts/mcp_server.py) | `workrecovery_status`, `workrecovery_list`, `workrecovery_stage`, `workrecovery_read` | Installed recovery library. Host supplies authorized durable storage; remove source injection without deleting pending recovery output. |
| [resource-explorer](../.github/skills/resource-explorer/scripts/mcp_server.py) | `resource_explorer_status`, `resource_explorer_tree`, `resource_explorer_content`, `resource_explorer_search` | Installed resource-explorer/data public APIs. Remove legacy `resource_explorer_api` and vendored data runtime; align callers with supported discovery/content behavior or retire old tools. |

Every retained adapter must expose accurate configuration/status, reject request-level target
or grant escalation, bound its work and clean up owned resources. Preserve budget/refusal
tests where applicable, not obsolete internal class names. If a server is retired, remove its
registration and catalogue tool claims rather than leaving a discoverable broken endpoint.

## Execution Requirements

Implement in small removal batches, not one prolonged compatibility phase:

1. Select the library contract and intentionally unsupported legacy outcomes. Existing APIs
  are evidence of migration work, not requirements automatically inherited by the library.
2. Put retained source, tests, examples and useful failure guidance at their canonical owner.
  Build declared artifacts and prove the supported positive/refusal paths through public APIs.
3. Replace or retire affected MCP adapters; reconcile the catalogue, skill entries, launch
  manifest, dependencies and package-owned operational guidance in the same delivered batch.
4. Delete superseded runtime trees, vendor copies, old package metadata/locks and executable
  fallback paths in that batch. Do not leave a deprecated second implementation as the result.
5. Adapt application call sites to the library. Record unfinished host work explicitly, without
  making the library emulate abandoned interfaces or retaining the removed runtime for them.

Start with capabilities whose canonical libraries already exist to establish portable packaging
and discovery; extract distinct remaining capabilities only where they earn a library owner.
The two model skills and raw compatibility package need one explicit consolidation decision,
not three parallel client families. The access skill must split mechanisms from native workflow
guidance rather than move all Azure policy into the authentication library.

The data and model [retirement assessment](CONNECTOR_RETIREMENT.md) records operational
knowledge already moved into [data operations](azure-data-connectors/OPERATIONS.md) and
[model operations](llm-interface/OPERATIONS.md). Reconcile the remaining findings with selected
contracts; historical gotchas are not requirements to perpetuate their obsolete implementations.
Update conflicting retirement summaries and supported-install instructions when migration lands.

## Removal And Completion

Each migration names its target contract, retained outcomes, intentionally retired outcomes,
old source paths to remove and application changes. This is an execution checklist, not a
parity gate or an approval board.

Completion requires one canonical implementation, no library/skill/plugin import or launcher
into the removed runtime, an accurate discovery surface, installable artifacts and focused checks
against the supported contract. Repository applications are updated or explicitly marked as
pending/broken with a named follow-up; they must not silently fall back to the old runtime.
An incomplete application migration is not evidence that the skill runtime must remain.

Removal and application adoption have separate statuses. A library/skill migration can be
complete while application adoption is pending; the portfolio cannot claim those applications
work until their actual workflows pass. External compatibility is not promised implicitly.

Historical receipts, provenance, licenses and user data are not duplicate runtimes. Preserve
necessary evidence and notices, relocate useful fixtures to their owner, and remove executable
fallbacks. Runtime deletion never authorizes deleting operational data or cloud resources.

## Evidence And Limits

Observed counts and ownership above come from the source scan, not remembered catalogue totals.
Library presence means a declared destination exists, not that legacy parity or live behavior
has been proven. In particular, optimization is research-only, raw model compatibility is a
distinct current package, and vendored data access still exists in the explorer skill.

Document validation checks local links, native/embedded catalogue coverage, MCP tool coverage
and whitespace. No library suites, browser journeys, installed-plugin round-trips or live
operations were run for this documentation task. Those checks belong to implementation and
must report the actual supported contract rather than promise unchanged applications.

Unknown: out-of-repository consumers, every client's discovery configuration and live service
compatibility. Publish the supported replacement and breaking-change notice; none of these
unknowns creates an indefinite legacy support obligation. This document is the durable record;
no separate notebook or runtime registry is introduced.

