# 01. Scope And Decisions

This chapter applies under [0. Core Objective](0_CORE_OBJECTIVE.md), which overrides it.
Normative language describes the migration target; inventories describe current source.

## Bounded Objective

- **Objective:** fix the minimum library-first decisions needed to deliver CO-1 through CO-6.
- **Done when:** each UL-01 through UL-12 has an explicit target and authority boundary;
   no legacy consumer can veto runtime removal, and exclusions identify protected data/work.
- **Scope ceiling:** the named capabilities, consumers and safety requirements only. No new
   feature family, approval hierarchy or mandatory package count from design discussion.
- **Stop condition:** the next removal/adoption block can proceed without an unresolved
   scope or authority choice. Do not reopen settled decisions for another planning pass.

## Binding Requirements

| ID | Requirement |
| --- | --- |
| UL-01 | Select library contracts for coherent capabilities, maintained native dependencies and explicit guarantees. Applications follow; legacy parity is not a design constraint. |
| UL-02 | One canonical owner under `libraries/` for retained implementation, contract, tests, examples, fixtures and operational knowledge. Reuse native SDKs/frameworks; no copied engines, global utility piles or caller-name switches. |
| UL-03 | Common installation, discovery, configuration, diagnostics, authority, lifecycle, budget and event conventions; capability-specific typed data/model/auth/UI APIs remain distinct. |
| UL-04 | Independently installable artifacts with declared dependencies; one supported unified profile. No editable/sibling-checkout assumption, source-path injection or mandatory unrelated provider/UI dependencies. |
| UL-05 | Thin standard-discoverable skill entries remain. Library-local guidance requires configured discovery or generated native entries; moving a skill alone is not discovery. |
| UL-06 | MCP/HTTP/CLI/UI adapters consume installed public APIs. A portable plugin works outside the repo with accurate configuration, bounded work and no implicit access. |
| UL-07 | Remove superseded runtime trees, vendor copies, package metadata/locks and executable fallbacks in their delivered migration batch. Missing old-feature parity or unknown external users does not postpone removal. |
| UL-08 | Preserve safety invariants: caller/record isolation, explicit authorization, least privilege, bounded work, integrity, truthful unknown/partial effects, secret protection and owned cleanup. Legacy representation and unsafe defaults are not invariants. |
| UL-09 | Verify selected contracts through focused offline/native-boundary tests, isolated artifacts, relevant real environments, composed workflows and required refusals. Evidence identifies exact artifacts and scope. |
| UL-10 | One lightweight, navigable knowledge system; package contracts, current guides, deployment instructions, design and historical evidence have explicit separate owners. |
| UL-11 | Prove developer usability with an independent consumer and complete public examples. Measure claimed effort/performance improvements; a short snippet or new namespace is not proof. |
| UL-12 | Keep design, implementation, removal, app adoption, live acceptance and publication status separate. Do not claim a working app or capability-complete release while its required checks are blocked or unrun. |

## Settled Design Decisions

1. **One bounded model/agent implementation.** `llm_interface` and native Microsoft Agent
   Framework are the model execution owners. Migrate `azure_llm_compat`, `azllm` and
   `modelaccess` consumers; delete those runtimes and duplicate tool loops. No permanent
   legacy model profile, version pin conflict or raw SDK escape hatch in the destination.
2. **Async data access is canonical.** Keep `azdata` typed operations and native service
   semantics. Convert app ADX/Search callers to async; remove app-oriented `adx_read` and
   `search-read-adapter` synchronization/error facades after their port/removal batch.
   A documented sync operator API can remain only for the selected operator capability,
   not to avoid changing the investigation app.
3. **Graph credentials are explicit service profiles, not duplicate libraries.** Consolidate
   parsing, driver lifetime and results under the `azdata` graph owner. Retain a deliberate
   read-only-key credential profile for the existing Cosmos workflow, with host-supplied
   identity and no implicit retrieval, separate from the resource-token profile. Remove
   the independent synchronous `graph_read` runtime; do not pretend a key is a resource
   token or weaken write authorization to combine them.
4. **Operator ADX remains a separate semantic capability within `azdata`.** Keep useful
   ingestion/schema/provisioning workflows and native SDK semantics with explicit grants.
   Legacy-only helpers not selected in the coverage matrix are retired rather than emulated.
   No invented keyed transactions or permanent exactly-once guarantee.
5. **Composition reuses the portable composition engine.** Bring the retained `appcompose`
   capability into libraries. A thin `agentcraft` entry package assembles typed handles and
   delegates lifecycle/manifest validation to that owner; it does not implement a second
   application runtime or provider/tool loop.
6. **One discovery authority, generated views.** Evolve and relocate the current skill
   catalogue into the library-owned capability catalogue. `.github/skills/catalogue.json`
   and native entries become generated discovery views where applicable. No second
   hand-maintained runtime registry; pure procedural skills retain their guidance owner.
7. **One optional MCP host, capability-owned adapters.** Consolidate retained tools into
   a library-distributed host with explicit enabled bindings. Retire duplicate model
   servers and unused administrative/estate tools; old tool names are migration inputs,
   not compatibility obligations. Python use does not require MCP.
8. **Documentation is repo-first.** A curated Markdown knowledge index and capability-owned
   contracts/examples are authoritative. A docs site is a renderer, not a duplicated
   authoring tree; no site rewrite is part of this plan.

Chosen local distribution/import names in this specification are implementation targets,
not claims of registry ownership or current availability. A registry name collision can
change packaging spelling without reopening the ownership or retirement decisions.

## Scope

Migration includes all current library capabilities and all retained reusable runtimes,
examples, tests and operational guidance in the audited 28 native skills, five embedded
entries and seven registered MCP servers. Eight protocol records remain procedural unless
their inspected implementation payload needs a canonical tool owner.

Required reference consumers: Investigation and Custom Optimizer; their setup, configuration,
async call sites, model sessions/events, tests and docs change to match the target. The
existing Perth ADX, Cosmos graph and loaded MITRE workflows remain acceptance scenarios,
not API-shape constraints. Retained skill/plugin consumers are also migrated or retired.

Other workspace areas such as documentation applications, imported testbeds and unrelated
ongoing work are not automatically migration destinations. Inspect their declared imports
when a selected library changes; modify only verified consumers within separately assigned
owned paths. Do not absorb their data or deployments into a foundational library.

## Safety And Authority

- This task delivers design/specification files only. It executes no source cull, application
  migration, dependency update, MCP activation, registry publication or cloud operation.
- Runtime migration approval does not grant Azure provisioning, role assignments, secret
  retrieval, model calls, test data writes, starts/stops or teardown. Those require exact
  target, identity, operation, budget, retention and cleanup authority in the execution phase.
- Retirement concerns code and obsolete artifacts, not authored records, recovery payloads,
  canonical datasets, credentials, backups, licenses or immutable evidence.
- Known required workflows must work on the new contract before full app/portfolio success
  is reported. An app failure is repaired in the app or a genuine target-library defect;
  restoring a duplicate runtime is not the default repair.
- A test asserting only a retired class/signature/event shape is replaced or removed with
  a reason. A test for a required safety or intended-result guarantee stays meaningful
  against the new implementation. Unsupported outcomes are fixed in advance, not chosen
  after a test fails.

## Non-Goals

No universal `execute(dict)` interface, mandatory all-to-all dependencies, arbitrary
plugin imports from configuration, global ambient credential/client singleton, duplicate
SDK transport, unrequested application visual redesign or one runtime package per skill.
No retroactive claims that research-only evaluation/optimization code, old wheel receipts
or installed dependencies constitute current framework acceptance.

## What Finalized Means

The architectural direction, target owners, retirement decisions, implementation sequence
and evidence gates are settled here. Exact release pins, live target approvals, public
package-name availability and native provider feasibility are bounded implementation
preflights with owners and failure outcomes, not invitations to keep legacy indefinitely.
Any genuine change to selected scope or guarantees is recorded as a spec revision. A
missing credential or failed external provider does not authorize bypassing its gate.

Next: [02. Capabilities And Dispositions](02_CAPABILITIES_AND_DISPOSITIONS.md).