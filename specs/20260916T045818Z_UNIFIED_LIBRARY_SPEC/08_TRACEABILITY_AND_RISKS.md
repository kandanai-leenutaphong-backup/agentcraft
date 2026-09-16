# 08. Traceability And Risks

This chapter records where the specification came from and how contradictory recommendations
were resolved. The sequence is the single target-design authority for this full migration;
input documents remain superseded history, not parallel live plans.

## Bounded Objective

- **Objective:** keep decisions, concrete outcomes and blockers traceable without creating
	another planning workflow, under [0. Core Objective](0_CORE_OBJECTIVE.md).
- **Done when:** the four source hashes and all UL/CO requirements map to their owning
	chapters; each actual blocker has an owner, next discriminating check and explicit effect
	on scope; measured outcomes remain separate from targets and historical evidence.
- **Scope ceiling:** update this record only when a decision, result or real risk changes.
	No repeated source-hash ceremony, speculative risk catalogue, transcript or new tracker.
- **Stop condition:** another implementer can identify the next bounded action and relevant
	evidence. Do not prolong preparation to eliminate every hypothetical future uncertainty.

## Input Provenance

Read in full for this consolidation on 2026-09-16. Repository revision:
`015d1bfc683c3b929490ce595f66744a4c8d56fa`. Hashes are the exact input bytes before
supersession notices were added; three input plans were untracked at capture time.
They identify the reviewed inputs, not execution/artifact/live proof.

| Source | SHA-256 At Consolidation | Incorporated Here |
| --- | --- | --- |
| [SKILLS_MIGRATION_DEPRECATION.md](../../libraries/SKILLS_MIGRATION_DEPRECATION.md) | `c547cb18b6b2bbe520c096f9e9d1dc398684a3e1aa4a31d8c7f43032dd8b0a70` | Binding library-first/removal requirements: 01. All native/embedded/protocol/MCP sources, guidance ownership and portable distribution: 04. Execution/status/protection rules: 06-07. |
| [DOCUMENTATION_AND_INTERFACE_DESIGN.md](../../libraries/DOCUMENTATION_AND_INTERFACE_DESIGN.md) | `60f24c2cb7ca9060885c1065e1a6c099ab464ac44a34b10e45dcb7b624e54732` | Shared interface standards: 03. Reader/knowledge structure, single ownership, page/interface cards, tested examples, rollout and Microsoft references: 05. Validation/usability: 07. |
| [FRAMEWORK_MIGRATION.md](../../libraries/FRAMEWORK_MIGRATION.md) | `41ace29323b965244d545a825eaa9f7b4efea5dfb4324a61c3a78015f62564f0` | Existing portfolio/features D1-D10, M1-M8, A1-A7, R1-R2, C1-C8, U1-U2, X1: 02. Current gaps resolved by F1-F8: 03. Target disposition, batches and closure: 06-07. |
| [LIBRARY_DEV_SKILL.md](../../libraries/LIBRARY_DEV_SKILL.md) | `ecce960231cc22dd30d309cef4be7e68f80a40e3a671d5719fc099f973c4284f` | Native-first iterative development: 03/06/07. Full delivery unit, artifacts, Azure proving environment, public-import cases, imported workflows, evidence/cleanup, independent usability and change discipline: 05/07. |

The sources need not be consulted to discover an extra migration gate: normative requirements
are incorporated here. Links provide audit provenance and current implementation references.
Existing capability contracts describe current code until their implementation batch updates
them; they do not override the selected target to preserve a legacy app shape.

## Requirement Coverage

The overriding [core objective](0_CORE_OBJECTIVE.md) takes precedence over the older source
plan assumptions. Its numerical values are execution targets, not measurements from this
documentation change. Existing detailed requirements are interpreted within these bounds.

| Objective | Owners | Required Outcome |
| --- | --- | --- |
| CO-1 | 02, 04, 06, 07 | Zero independent skill runtimes; at least 50% fewer shipped skill files and bytes against the same baseline scope |
| CO-2 | 05, 07 | Current reference/example for every retained capability; valid local links; agreed common tasks reachable in at most three navigation steps |
| CO-3 | 03, 07 | Every retained runtime library conforms to applicable F1-F8; no undocumented deviations; one installable working combined profile |
| CO-4 | 01, 02, 03, 06 | Each added abstraction has an immediate consumer and demonstrated reuse/invariant benefit; no speculative scaffolding |
| CO-5 | All chapters, 06 | Objective, completion evidence, scope ceiling and stop condition per chapter; explicit deliverable/check/effort bound per block |
| CO-6 | 06, 07 | First and subsequent implementation blocks deliver concrete working/removal results with focused proof, not prolonged preparation |

| Requirement | Design Chapter | Execution Batches | Acceptance |
| --- | --- | --- | --- |
| UL-01 Library-first target | 01, 02, 03 | B00-B09 | AC-01, AC-14, AC-15; no old-caller veto |
| UL-02 Single owner/native reuse | 02, 03, 04 | B01-B07 | AC-01, AC-06, AC-08, AC-15 |
| UL-03 Common standards | 03 F1-F8 | B01-B06 | AC-01-AC-10, common conformance |
| UL-04 Independent packaging | 03 F2, 04 | B01, B07-B09 | AC-02, AC-11, artifact/floor/profile gates |
| UL-05 Thin native discovery | 04 | B01-B07 | AC-11, AC-15 |
| UL-06 Public-API adapters | 03, 04 | B01-B08 | AC-03, AC-05, AC-11, outside-checkout round trips |
| UL-07 Mandatory source retirement | 01, 02, 04, 06 | Each removal batch, B09 final | AC-15; removal/adoption statuses separate |
| UL-08 Safety invariants | 01, 03 | All stateful/privileged batches | AC-03-AC-10, AC-13 and owned cleanup |
| UL-09 Multi-level verification | 07 | B00-B09 | All applicable AC gates, frozen matrix |
| UL-10 Knowledge ownership | 05 | B01-B09, B07 integration | Link/example/navigation/status checks |
| UL-11 Independent usability | 05, 07 | Each public-contract increment, B08-B09 | AC-14; measured claims only |
| UL-12 Honest milestone status | README, 01, 06, 07 | Every batch | No required FAIL/BLOCKED/NOT_RUN hidden in a complete claim |

Chapter 04 has explicit rows for all 28 native skills, five embedded entries, eight protocol
records and every one of the 27 current MCP tool names. Its target is one optional host with
15 selected tools across data/model/composition/recovery/inventory; the administrative and
estate-search surfaces are intentionally retired. These counts are source-scan/coverage
facts, not proof that current or future servers successfully start.

## Resolved Conflicts

| Earlier Tension | Final Resolution |
| --- | --- |
| Fixed architecture/type/profile lists and B00/B01 preparation could delay simple useful migrations | CO-4/CO-6 override the layout. Create only machinery needed for the current result; reuse the audit incrementally and deliver the first canonical capability/removal before completing portfolio scaffolding. |
| Framework audit allowed legacy compatibility profiles and removal only after every consumer migrated | UL-01/UL-07 prevail. Retire obsolete engines in their batch; port apps to the selected library contract and track adoption separately. Full app success still requires its new workflow to pass. |
| Caller-first design could be read as preserving existing signatures/events/defaults | Caller-first means usability of the intended API. Existing callers reveal migration work, not a constraint on target architecture. Safety/result truth remain, legacy API parity does not. |
| Three model client families and a duplicate tool loop | `llm_interface`/native Agent Framework are the sole runtime owners; delete compatibility/model-skill engines and migrate sessions/events/dependencies. |
| Sync ADX/Search/graph facades defended by current app structure | Canonical async data APIs; port app callers. Useful parameter/data-shape rules move once, not the old synchronization engine. A genuine operator capability can remain explicitly synchronous. |
| Uniform resource-token graph versus existing Cosmos read-only-key access | One graph owner with explicit credential profiles, not secret substitution or duplicate drivers. Host key-provider authority is separate from query permission; data-write access is never inferred. |
| Source skills suggested an administration library if needed; earlier access-library experiment was retired | Native Azure administration remains guidance. Retire `azaccess` MCP/runtime instead of resurrecting a universal access engine. Auth mechanisms remain in their existing libraries. |
| Research-only optimization directory versus substantive skill runtime | Move selected generation/cohort/evidence/replay outcomes into the optimization library and compose foundations. Keep wider research topics labeled research, not unimplemented advertised features. |
| Source playbook demanded Azure proof for every capability, including pure/local helpers | Mandatory real Azure reference proof remains for the advertised Azure/hosted framework scope. Native local utilities have applicable local proof and participate in real hosted composition only where promised; no artificial cloud service per helper. No promised cloud case becomes local to avoid a required gate. |
| Library-local skill sources versus standard native discovery | Keep one canonical guidance source and generate/configure discoverable entries plus portable artifacts. Moving alone loses discovery and does not satisfy UL-05. |
| Many proposed documents versus one current knowledge authority | This ordered spec is the design authority; capability contracts/examples/runbooks keep their own factual ownership; four inputs are marked superseded. No duplicate website/manual or runtime registry is introduced. |

## Execution Risks And Bounded Responses

| Risk | Owner / First Discriminating Check | Required Response |
| --- | --- | --- |
| Native model packages/options/session behavior differ from legacy | B03 model owner; clean dependency resolve plus native client/tool/session contract tests | Repair selected library support or app mapping. Do not keep raw engine; record genuine scope/guarantee changes in spec. |
| Async graph/native driver buffering/credential behavior differs | B02 data owner; parser/identity/bounds native tests and exact approved existing graph read-back | Preserve profile honesty, distinguish decoded versus wire bounds, fix root integration. Missing cloud authority blocks live credit, not source retirement. |
| Persisted app sessions, authored agents or optimization records use old schema | B03/B04/B06 host owner; explicit versioned fixture and migration/read-only recovery test | Protect original data, label unsupported history, migrate intentionally. No wipe or silent coercion for acceptance. |
| Unknown external callers or private configurations | B00/B07 distribution owner; import/entrypoint scan and breaking-change documentation | Publish target/migration notice; no indefinite compatibility runtime. Do not claim unobserved external apps work. |
| Thin skill/plugin relies on checkout-local paths or undeclared installs | B07 packaging owner; install/run without source checkout/network fallback | Fix declared artifacts/discovery. Never vendor legacy source as a shortcut. |
| Capability graphs or route/asset owners conflict | B01 composition owner; actual dependency manifest and collision/rollback test | Resolve ownership/cycle explicitly; no hidden private import or duplicate writer. |
| Copied terminal/art/fonts or reference packs have unresolved rights | B05/B06 package owner; review recorded provenance and required redistribution notices before build/publication | Preserve rights evidence, block affected distribution, or explicitly revise selected scope. Migration does not manufacture a license. |
| Real Azure tests require resources, restricted identity, inference or writes not authorized | B08 deployment/feature owner; exact-target no-mutation preflight | Seek scoped authority; mark required cases BLOCKED and continue independent authorized source work. No new grants, keys, endpoints or auth disablement. |
| Real provider cannot supply a promised guarantee | Owning capability; frozen positive case and independent native observation | Fix or explicitly revise spec/profile; do not turn a failed promised positive into unsupported after the fact. |
| Parallel user work changes source or state during migration | Named writer; current worktree/process/path recheck before each batch | Preserve work, stop conflicting slice and coordinate; never reset/stash/revert other changes. |
| Apparent cleanup reduces sources but grows generated duplicates/dependencies | B09 removal/package owner; scoped source+artifact inventory before/after, clean rebuild | Delete only frozen generated/runtime set, prevent regeneration of retired code; no claims of RSS/disk/latency gain without measurement. |

## Required Implementation Records

Before B00 closes, record actual revision/worktree, capability/caller/removal manifests and
target coverage matrix. Before B08 live work, record exact artifact/version/dependency pins,
approved Azure target/identity/limits/time/retention/cleanup and independent expected results.
Those concrete values are execution inputs, not missing architectural decisions or
authorization implied by this document's timestamp.

Before B09 closes, record all batch statuses, physical source removal, generated discovery/
adapter identities, installed public imports, app/feature/workflow results, independent
usability observations and reconciled cleanup. Record publication separately. No receipt
contains secrets/customer content, and no old receipt is relabeled for a new artifact.

## Specification Validation

The specification-authoring check is limited to source consolidation, actual catalogue
coverage, numbered-file navigation, local evidence links, requirement/batch/gate references
and contradictory-authority removal. It is not a runtime, browser, Azure, MCP or package
acceptance run. Execution begins only when the migration work is requested under its
proper source/cloud/publication scope.

Return to [specification index](README.md).