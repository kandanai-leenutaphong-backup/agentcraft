# 06. Migration Execution Plan

All batches below are **NOT_STARTED**. This task writes the spec, not the migration.
Batch order follows actual implementation dependencies, not preparation milestones. Under
[0. Core Objective](0_CORE_OBJECTIVE.md), deliver working capability and remove its old
runtime first; build only the engineering prerequisites that result actually needs.

## Bounded Objective

- **Objective:** deliver successive usable library/removal increments quickly, with no
  unbounded preparation or compatibility phase.
- **Done when:** every delivered block has one demonstrated public capability or concrete
  removal/documentation outcome, measured before/after evidence and passing relevant checks;
  the full migration meets CO-1 through CO-6 and all required app-adoption gates.
- **Scope ceiling:** before each block, record its result, owned paths, focused check and
  effort/time bound in the existing record. No extra framework/test/deployment machinery
  except a prerequisite of that result; no new feature family or silent bound extension.
- **Stop condition:** stop the block on its passing result or named blocker. At the effort
  bound, expose remaining work and choose a smaller step instead of silently overrunning.

## First Result

Choose one small audited skill whose canonical library already exists. Reuse its source
and tests, adapt its direct discovery/consumer imports, remove the duplicate runtime and
run the scoped success/refusal checks. This first delivered implementation block must
produce that result, not just inventory, descriptors, a new empty package or another plan.

Do the B00 checks for that block only. B01 work is prerequisite only if the operation
actually requires it. Complete the remaining inventory and common machinery alongside
later concrete migrations; do not hold useful removals behind a portfolio-wide setup phase.

## Execution Rules

- One writer per source path, shared contract, environment/lock and cloud resource. Direct
  implementation is normal; optional teams own independently demonstrable outcomes, not
  separate technical layers of the same unfinished feature.
- Read current worktree and source ownership, then freeze exact retained/retired paths and
  tests for the next batch. Preserve user work, data, receipts and notices. No commit/branch,
  force operation or broad deletion follows from the plan.
- Form one local hypothesis/check, make the smallest target-contract change, run its focused
  check immediately, and repair that block before widening scope. Do not build all framework
  abstractions before proving one real caller.
- Dependencies/framework semantics are decided for the library. App changes follow them.
  A failing old API test is classified as target regression, required safety regression or
  obsolete shape; it is not automatic justification for a shim.
- Remove old runtime/import/registration paths in the delivered batch. If an app/adapter
  still needs work, report it pending/broken and disable inaccurate discovery. No fallback
  to legacy code, no claim that the app passes until it actually does.
- After every affected Investigation block, run the target-adapted Perth/graph/MITRE local
  API/browser checks when runnable and authorized. A temporarily unported app has a named
  blocker and next action, never a fabricated green gate. Full acceptance requires actual
  app success; library retirement is not reversed to avoid adoption work.
- Cloud-only/model/write tests require chapter 07 preflight and target-bound authority.
  Continue authorized independent source work when those are blocked, but do not claim
  full release acceptance. No inferred right to restart/stop a cluster or seed data.

## Ordered Batches

| Batch | Outcome And Dependencies | Primary Writable Owners | Removal / Exit Evidence |
| --- | --- | --- | --- |
| B00 | Reuse the existing audit; freeze facts/coverage for the current block only; no dependency | Existing capability/removal records; current consumer paths and selected assertions | Complete coverage of the 38 features, 28 skills, five embedded/eight protocol entries and 27 tools incrementally by B09. No repeat full audit before the first useful migration. Do not silently declare unknowns dead. |
| B01 | Minimum shared/core/composition work required by one demonstrable caller; depends on its scoped B00 facts | Needed existing or selected core/composition/catalogue owner; one shared lock owner | Reuse portable composition; prove only the needed descriptor/resolver/lifecycle/route/asset behavior. Deliver a working caller, not empty machinery. Retire the corresponding old implementation in its batch. |
| B02 | Async data and inventory integration; depends only on shared pieces it actually uses | `azure-data-connectors`, `resource-explorer`, `situation-detector`; data/inventory MCP adapters; affected host data/rule/knowledge code | Adopt standard policy/errors/lifecycle; migrate async ADX/Search; unify graph read/profile; remove v3 data/Search/vendor/runtime copies, `adx_read`, `graph_read`, `search-read-adapter` and old skill implementations. Preserve target data/effect/security meaning; offline and real read workflows on new contract. |
| B03 | Single model/agent runtime; shared pieces and B02 tools only where needed | `llm-interface`, `modular-agents`, model MCP adapter; both app model/session/event integrations | Remove `azure-llm-compat`, skill `azllm`, `modelaccess` and duplicate invocation loops. One compatible model dependency set. Port session IDs/events/config/authorizers/tests; prove tool/owner/schema/budget/refusal/terminal cleanup before any live model test. |
| B04 | Canonical identity, signing and recovery; depends only on shared pieces it actually uses | `entra-auth`, `signed-dev-access`, `recoverable-jobs`; host auth/state adapters; recovery MCP | Merge signing/verification ownership, retain distinct record/replay invariants, migrate recovery manifests carefully. Remove compatibility auth runtimes, `devauth`, `workrecovery` skill copies and `azaccess` engine/tools. Native administrative guidance remains. Positive/replay/expired/foreign-owner/unknown-commit cases pass; no data deletion. |
| B05 | Remaining offline/tool/UI capability owners; only actual B01-B04 API dependencies | `repository-inspection`, `investigation-notebook`, `web-resource`, `copilot-terminal`, `azure-sky-styling`, `hyperframes-tools`, frontend primitives | Migrate one coherent tool at a time; remove substantive skill scripts/vendor snapshots and independent example/test authorities. Native engines stay native. Verify guarded acquisition, notebook integrity, local PTY isolation/ownership, rendering assets and motion evidence in actual applicable runtimes. No cloud mutation for a pure local tool. |
| B06 | Optimization workflow on shared foundations; depends B02-B05 | `agent-optimization`, `modular-agents`; Custom Optimizer host/domain adapters | Adopt selected immutable generation/cohort/evidence-tool/config/replay outcomes. Model/data/recovery/detector/terminal are shared APIs, not copied source. Delete skill runtime and independent executable reference pack. Keep research and frozen result provenance distinct; no quality gain claimed without campaign evidence. |
| B07 | Complete discovery/MCP/documentation distribution; incrementally built in B01-B06 | Canonical capability catalogue; generated skills/catalogue/MCP declarations; capability docs/examples; optional host/package metadata | All retained native/embedded entries resolve outside checkout; all 27 old tools mapped/retired as chapter 04. No stale active registration, untracked dependency trick or manual runtime bundle. Knowledge index, task/reference and migration notices reflect target. Real MCP client/server success/refusal/close tests. |
| B08 | Integrated consumer adoption and whole-profile proofs; depends selected B02-B07 artifacts | Investigation, Custom Optimizer, documented reference feature/workflow harnesses; exact owned acceptance/deploy fields | Repair remaining async/session/wire/config callers on target. Verify installed artifact app journeys and standalone capabilities; restricted identity/provider-denial checks, hosted auth and approved live scenarios. All required consumers work; no pending/broken host hidden by completed library status. |
| B09 | Final removal audit, release-ready artifacts and evidence; depends B08 | Package versions/locks/build metadata, release candidate receipt, catalogue/docs/remaining owned deletion manifests | No independent runtime under skills, no obsolete compatibility/vendor/import/launcher path. All selected conformance/feature/workflow/usability gates pass, cleanup/retention reconciled. Registry publication only if separately authorized; unrequested publication is not assumed. |

This is a dependency order, not a requirement to postpone easy direct consumer changes until
B08. Port related app/MCP callers in B02-B06 when practical so each local increment remains
usable. B08 verifies the integrated artifact and closes any explicitly recorded adoption gaps.
No mandatory agent/team minimum is attached to these batches.
Batch IDs identify remaining work, not a requirement to finish every earlier row before
starting an independent later result. Do not let a synthetic dependency on an unfinished
framework layer block use of an already sufficient canonical library.

## Batch Record Contract

Use one compact record per delivered increment, linked from the canonical capability's
verification record rather than a parallel ticket registry:

| Field | Required Evidence |
| --- | --- |
| Identity | Batch ID, capability/feature IDs, contract revision, source revision, owned paths |
| Target | Selected outcomes, intentionally retired outcomes, exact public API/config/event changes |
| Bound | One concrete deliverable, applicable chapter scope ceilings, focused check, effort/time bound and stop condition; actual effort reported separately, never estimated as measured |
| Source removal | Exact old roots/files/metadata/imports/launchers, replacement owner, recovery method, protected data/notices |
| Consumers | Verified caller/build/discovery graph, app adoption actions, remaining named blockers |
| Checks | Commands, artifact identity, success/refusal/failure/blocked/unrun counts, expected versus observed |
| State | Independent contract/implementation/distribution/discovery/removal/adoption/verification statuses |
| Operations | Exact cloud/local state changes authorized and performed, measured/unknown cost, cleanup/retention |

No synthetic private customer payload belongs in the record. No original test failure is
erased by a successful retry. A moving source or concurrently edited owner stops only the
conflicting block, not unrelated authorized work.

## Removal Procedure

1. Record current revision/worktree and exact candidate paths. Trace imports, string/dynamic
   loads, catalogue entries, MCP registration, packaging, examples and test runners.
2. Classify retained domain/safety knowledge, obsolete API-only behavior and protected data.
   Move useful tests/examples/operations to their single owner; preserve rights/provenance.
3. Implement the selected target contract and required adapters; run the narrow check.
4. Update or retire affected registrations/discovery/lock/import references. Publish the
   breaking-change map; adapt host callers or explicitly mark their remaining work.
5. Delete the frozen old-runtime set, including superseded metadata/vendor trees/fallbacks.
   Do not keep a compatibility package as the delivered result.
6. Verify absence and target behavior immediately. A missed consumer becomes an adoption
   fix or an explicit retired feature, not an indefinite old-source dependency.

Temporary reversible work while a batch is in progress is allowed. A permanent dual engine,
silent fallback or finished batch that still ships its superseded runtime is not.
Source-only deletion is never permission to destroy a credential, dataset, record, pending
recovery output, backup or cloud resource.

## App Migration Details

### Investigation

- Await canonical ADX/Search/graph operations; remove transport thread/Runner glue and legacy
  exception aliasing. Keep domain table policies, evidence bounds, ontology and query meaning.
- Adopt new model session IDs and native framework event semantics. Update API/browser
  adapters and tests together; no `previous_response_id` compatibility engine.
- Keep the host's caller/record authorization, source selection and immutable authoring
  outcomes. If a persisted/wire schema changes, version and migrate/read-only the old records
  explicitly; never wipe them or reinterpret silently.
- Configure catalogue route prefix/provenance at the host. Generic libraries must not bake
  in Perth, CyberEye, MITRE, GUIDE or source-project identifiers.
- Reuse the existing scenario/data checks as independent domain observations; adapt API
  assertions to the target contract. Model calls stay separately authorized and bounded.

### Custom Optimizer

- Use the same selected data/model/detector/recovery/terminal owners; remove runtime copies
  including active historical/reference-pack import paths.
- Preserve experiment inputs/results and label visibility boundaries, not old module names
  or event schemas. New generation schemas need explicit version/migration/read-back.
- A campaign runs only with separately approved dataset, model/call/token budget, cohort,
  scorer and retention; existing result display does not authorize recomputation.

### Installed Plugins And Other Hosts

Migrate retained MCP/config/discovery callers in their removal batch. Unknown external
consumers receive a documented breaking change, not a permanent shim. Inventory additional
in-repo users of selected contracts; do not modify unrelated source/data merely because it
shares the workspace. Full portfolio claims list exactly which consumers were validated.

## Cost And Stop Conditions

No fixed estimates, fabricated dates or required team sizes. Record durations/calls only
when measured. Missing authority, a real target-contract contradiction, unsafe irreversible
data choice or material scope expansion is an escalation. Ordinary app incompatibility is
implementation work. A required provider that is unavailable remains blocked; declare the
source/removal state accurately and do not invent live success.

Next: [07. Verification And Release](07_VERIFICATION_AND_RELEASE.md).