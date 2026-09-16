# Unified Library Specification

Status: **Finalized design and implementation plan; execution not started.**
Created: 2026-09-16T04:58:18Z. Source revision: `015d1bfc683c3b929490ce595f66744a4c8d56fa`.

**Read first: [0. Core Objective](0_CORE_OBJECTIVE.md).** Its six result-first objectives
override conflicting detail in every chapter. Measurable outcomes and chapter scope limits
control implementation; architecture and preparation serve those outcomes.

## Outcome

One coherent, modular Agentcraft framework: libraries own capability implementations,
contracts, tests, examples and operational guidance; applications and adapters follow
the selected library contracts; native skills provide thin discovery. Superseded
runtimes, vendor copies and permanent compatibility layers are removed in the migration.

**Library first, not legacy first.** Existing applications provide useful scenarios and
identify migration work. They do not veto the target design or require preservation of
old API names, synchronous call patterns, provider response IDs or wire envelopes.
Authentication, authorization, integrity, bounded execution, truthful results and
owned cleanup remain requirements of the new contract.

This specification consolidates the four documents listed in the traceability chapter.
It supersedes their conflicting migration recommendations; it does not claim the target
is implemented or grant cloud access, publication, data deletion or paid execution.

## Read And Execute In Order

| Order | Specification | Purpose |
| --- | --- | --- |
| 0 | [Core Objective](0_CORE_OBJECTIVE.md) | Overriding outcomes, reduction/conformance targets, scope discipline and result-first delivery |
| 01 | [Scope And Decisions](01_SCOPE_AND_DECISIONS.md) | Binding direction, selected outcomes, exclusions and authority |
| 02 | [Capabilities And Dispositions](02_CAPABILITIES_AND_DISPOSITIONS.md) | Existing library feature inventory, target owners and required removals |
| 03 | [Framework And Interface Standard](03_FRAMEWORK_AND_INTERFACE_STANDARD.md) | Dependency graph, public access, configuration, policy, results and lifecycle |
| 04 | [Skills, MCP And Distribution](04_SKILLS_MCP_AND_DISTRIBUTION.md) | All skill/embedded/MCP migrations, discovery generation and portable packaging |
| 05 | [Documentation And Developer Experience](05_DOCUMENTATION_AND_DEVELOPER_EXPERIENCE.md) | Knowledge architecture, page/interface contracts and independent usability |
| 06 | [Migration Execution Plan](06_MIGRATION_EXECUTION_PLAN.md) | Ordered deliverable batches, owned paths, dependencies and exit checks |
| 07 | [Verification And Release](07_VERIFICATION_AND_RELEASE.md) | Conformance, artifacts, live proving environment, workflows, evidence and cleanup |
| 08 | [Traceability And Risks](08_TRACEABILITY_AND_RISKS.md) | Input hashes, requirement coverage, conflict resolutions and bounded blockers |

The numeric prefix is the sequence of this finite specification, not the naming policy
for the future knowledge base. Each chapter has one responsibility; inventories are
design records, not another runtime capability catalogue.
The index is complete when every chapter is reachable in order, has a bounded objective,
and points to the same overriding objective; it is not a separate planning deliverable.

## Completion States

Track `contract`, `implementation`, `distribution`, `discovery`, `legacy_removal`,
`consumer_adoption` and `verification` separately for each delivered batch. A removed
legacy runtime stays removed even if an app still needs work. That app remains visibly
pending/broken, with no hidden fallback. Full portfolio completion requires adapted
in-scope apps and all required verification, not merely finished library packages.

Current status of every execution batch: **NOT_STARTED**. Earlier local migration results
are historical evidence only. The present task authors and validates this specification.