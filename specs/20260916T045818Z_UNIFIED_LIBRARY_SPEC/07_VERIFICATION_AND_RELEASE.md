# 07. Verification And Release

This consolidates the library-development playbook into enforceable target acceptance.
Capability correctness, independent developer usability, source retirement, app adoption
and distribution are different proofs. A pass in one never silently substitutes for another.

## Bounded Objective

- **Objective:** prove the current result and the final supported framework profile with the
  smallest sufficient evidence, under [0. Core Objective](0_CORE_OBJECTIVE.md).
- **Done when:** every required case for the frozen scope passes, matching refusals and
  cleanup hold, and conformance/removal measures meet CO-1 through CO-3. No required failure,
  blocked case or unrun case is hidden in a completion claim.
- **Scope ceiling:** apply AC-01 through AC-15 only to relevant advertised behavior and risks.
  Reuse current checks/evidence; no separate test platform, duplicated signoff or unrelated
  live campaign merely for reassurance. Never weaken a real safety or required live gate.
- **Stop condition:** the block's agreed checks pass or a specific prerequisite blocks them.
  Record that outcome and proceed with independent authorized work; do not expand the suite
  or its claimed scope while testing. Full release checks remain due for the full profile.

## Delivery Unit And Iteration

Each retained capability delivers its public typed contract, supported profile matrix,
owner-local operational guidance/examples, focused tests, installable artifacts, feature
scenarios, composed workflow evidence where promised, and truthful verification record.
Azure-backed/hosted advertised behavior additionally needs the real proving environment
below. Pure utilities do not acquire artificial cloud dependencies to satisfy a file template.

For each increment: intended developer task and no-goals; native API reuse decision; smallest
public call with failure/cleanup example; frozen expected support; local edit; immediate
focused check; real consumer adoption/removal; artifact/live verification in proportion to
advertised scope. Do not implement a second transport, serializer, tool loop or fixture engine
to make the verifier easier. Native SDK boundary tests inject external I/O, not the method
whose serialization/authorization is being claimed.

## Coverage Matrix

One capability-owned matrix covers every advertised feature/provider/mode/guarantee and
every promised composition. Rows have stable case ID, public symbol/profile, prerequisites,
authority, expected positive/refusal outcome, independent oracle, scenario function, workflow
membership and required evidence class. Use parameterized cases; not one ceremonial test
per SDK method. Freeze support before execution; `describe()` cannot be its own oracle.

| Gate | Required Checks | Applies To |
| --- | --- | --- |
| AC-01 | Exact exports/types/config schema; declared support and meaningful default refusal | Every public capability/profile |
| AC-02 | Import/construction/describe without tokens, network, thread/subprocess or data writes; explicit startup | Core/composition and I/O capabilities; stateless declarations |
| AC-03 | Caller/target/grant/owner/tool isolation; untrusted config cannot import code or widen scope | Policy/auth, MCP/HTTP, composition, model tools, data/recovery |
| AC-04 | Native value/order/key/partition/version integrity; empty versus absent versus unknown; partial effects and unattempted tails | Data, model outputs, previews, ingestion, recovery |
| AC-05 | Startup rollback, concurrency, close once, borrowed resource survival, cancellation/stream backpressure/terminal failure | Stateful/async/hosted capabilities; pure helpers declare inapplicable |
| AC-06 | Native provider serialization/query/schema/CRUD/verification and actual positive/refusal service paths | Each advertised data profile/operation, not only Perth reads |
| AC-07 | Graph resource-token and explicit read-only-key profiles; mutation denial before lookup, exact target, bounds and cleanup | Selected graph profiles; test identity/permissions separately |
| AC-08 | Model structured output/embedding alignment, tool validation/authorization, session owner, terminal events and bounded usage | `llm_interface`, modular agents and model MCP |
| AC-09 | Config round-trip/refusal, DAG/cycle rules, route/asset conflicts, remove-member recomposition and rollback | `appcompose` and framework root |
| AC-10 | Completed-output integrity, uncertain save/read-back, crash recovery, expiry/replay claims and no unauthorized deletion | Recovery, notebook/auth stores, optimization state as relevant |
| AC-11 | Native skill discovery, aliases/status, clean plugin install, actual MCP SDK round-trip, denied/malformed/budget/close paths | Generated discovery and every retained adapter |
| AC-12 | True local rendering/PTY/filesystem/acquisition behavior, assets/notices, URL/robots/refusal guards | Retained local tool and frontend families |
| AC-13 | Real deployed caller auth/ownership/signing/proxy invariants, actual service denial under restricted approved identity | Advertised hosted/auth/cloud integration, not inferred from localhost |
| AC-14 | Independent setup/usage/recovery/cleanup and measured claimed effort reduction | Unified supported profiles and meaningful new wrappers |
| AC-15 | Old roots/imports/metadata/vendor/launchers absent, target discovery accurate, no duplicated implementation or data loss | Every removal batch and final portfolio |

Retire obsolete signature-only tests deliberately. Retain success/refusal/safety knowledge
against the target. An unimplemented required positive cannot earn credit as an unsupported
refusal; change scope explicitly and preserve the prior failure record.

## Artifact Gates

Build wheels and sdists with `uv build --no-sources`; rebuild from sdist and compare runtime
content. Install outside checkout with no editable siblings, `PYTHONPATH`, current-directory
imports, dataset or credential files masking missing dependencies. Verify import origin,
distribution metadata, versions and SHA-256. Test base-only installation and selected extras,
declared Python/OS/dependency floors and the composed profile. Shared lock success is not
proof every allowed dependency combination works.

Inspect notices/licenses, typing metadata, dependencies, examples/guidance and accidental
private/build contents. Frontend npm artifacts similarly include usable ESM/types and
explicit CSS/assets/peers; verify installation in a clean host and both target frontend builds.
Generated plugin bundles contain only reviewed versioned artifacts and necessary guidance.
No registry name or upload is assumed by source naming.

Source changes invalidate candidate identity: rebuild before fresh evidence. Preserve old
receipts without relabeling their wheel hashes. Publication requires separately authorized
registry/target/artifact paths and native trusted/OIDC flow; never credentials in config/logs.
Verify install from the actual registry if publication is in scope. Release-ready local
artifacts can be complete while publication remains unrequested, explicitly named as such.

## Mandatory Live Proving Environment

A unified framework release needs a reproducible real Azure reference environment covering
its advertised Azure-backed/hosted feature and workflow matrix. An empty resource group,
mock server, local app or syntactically valid endpoint is not that proof. Reuse existing
approved services when appropriate; provision missing required services/models only under
explicit authority. Deploy a reference host/worker where hosted behavior is promised, not
an artificial HTTP service for every pure library.

The pure decoder, rule processor, repository analysis and local PTY/notebook/motion tools
retain native local acceptance. Exercise them in the actual composition/runtime where
advertised. The source playbook's Azure mandate is carried by meaningful service/hosted
coverage, not needless cloud mutation for an offline utility. No advertised cloud behavior
may be reclassified local merely to avoid its live check.

Before any live execution, record tenant/subscription/cloud or Fabric workspace, exact
resources/models/regions/SKUs, identities, allowed operations, synthetic/borrowed data,
network policy, limits/cost responsibility, time window, retention and owned cleanup. A
test grant, provisioning grant, RBAC grant, model-call grant and teardown grant are separate.
CLI login or earlier migration authority supplies none implicitly.

One lifecycle owner per environment in `deploy/`: committed non-secret config, declarative
resources as appropriate, preflight/apply/verify/feature/workflow/report/teardown actions
through the existing `deploy/deploy.sh` entry point. Implement explicit subcommands there;
no required step exists only in shell history. Existing app deployments keep their own
ownership; never create a competing root for the same live target.

The documented operator sequence must provide:

1. Offline runner tests and a no-mutation plan with exact targets and required permissions.
2. Explicit authorized idempotent apply, ownership check and independent field read-back.
3. External service/host readiness and caller auth checks, with protected settings unchanged.
4. Selection of one feature case, a composed workflow or the complete approved suite.
5. Machine/human reports, partial results and reconciliation after failure or interruption.
6. Separately authorized owned teardown, absence read-back or approved retained resources.

Wrong target, missing authority, collision, budget exhaustion and unknown existence/cleanup
are refusal tests for the runner itself. Never enable public access, fetch another credential,
change RBAC or substitute targets to make a blocked check pass.

## Feature And Workflow Scenarios

Each advertised live feature has an individually runnable module with callable operation/check
function and thin `main()` adapter. A normal proposed shape is `run(context) -> CaseResult`,
async where the operation is async. Host context supplies approved bindings, fixture ownership
and budgets; it does not hide a second implementation behind a generic dispatcher.

Each feature scenario verifies artifact identity/authority before I/O, calls installed public
APIs, inspects typed/native results and requested evidence, checks the matching negative case,
and reports safe observations plus cleanup. Standalone scripts fail nonzero under normal and
optimized Python; do not rely solely on removable `assert` statements for live enforcement.

Freeze expected fixture values before writes. Read back with a fresh client when practical:
identity, content, order, ETag/version, absence, batch count or named native guarantee. A 200,
accepted ingestion or `Succeeded` ARM status is not persistence/drift proof. Bounded eventual-
consistency polling is service-aware and charged to the same budget.

Local policy denial and real provider denial are separate tests with approved restricted
runtime identities and a separate authorized observer/setup identity. Do not revoke human
grants or use a privileged setup credential to conceal a missing runtime permission.
Injected response loss against a real service is hybrid resilience evidence, not evidence
Azure naturally emitted that failure. Do not overload a service to manufacture errors.

Workflows import operation/check functions and pass actual outputs forward; do not parse
subprocess stdout or copy operation logic. The workflow owns shared fixtures until final
read-back; an intermediate feature must not delete the next feature's input.

Required workflow families:

- Data: write/query or page/update/fresh read/delete/absence for the profiles that advertise
  those operations; ADX uses explicit batch ingestion and batch-specific verification.
- Model: bounded call/structured output or embeddings; authorized data tool stream; terminal
  result and owner-checked read-back without another model call.
- Composition: validate/bind/start, inject limited identity/config, consume capability, fail
  an intermediate startup/operation and verify reverse-order cleanup.
- Recovery/optimization: complete output, uncertain save, recover/read-back; frozen cohort
  generation/result integrity and protected labels. Quality claims need dataset/scorer/
  threshold and retained per-case outcomes, not one plausible answer or exact output string.
- In-scope apps: adapted Perth scan/evidence, existing Cosmos graph and MITRE knowledge,
  model/session interactions and Custom Optimizer workflows on the selected contracts.
- Plugins/UI: discover/install/invoke/refuse/close outside checkout; operate rendered controls
  with actual results, safe recovery, keyboard and desktop/mobile geometry/screenshots.

## Evidence And Outcomes

| Status | Meaning | Credit |
| --- | --- | --- |
| `PASS_OFFLINE` | Controlled I/O/native-boundary test met its oracle | Offline only |
| `PASS_ARTIFACT` | Installed artifact/import/content/dependency test passed | Packaging only |
| `PASS_LIVE` | Installed library invoked approved real service and met positive oracle | Exact feature/environment only |
| `PASS_REFUSAL` | Intended negative safely refused | Negative only; identify local versus provider enforcement |
| `FAIL` | Behavior contradicts frozen selected contract | Blocks required gate |
| `BLOCKED` | Missing authority, provider, identity, budget, fixture or observable evidence | Blocks required gate, not code-retirement direction |
| `NOT_RUN` | Unattempted/skipped with reason | No required positive credit |

Each record includes case/workflow IDs, contract/library version, artifact digest/import
origin, dependency/Python/OS/native API/model versions, approved non-secret target/principal,
UTC interval, run/request/trace correlation, expected/observed status/evidence/count/digest/
version, measured latency/attempts/usage, caveats and cleanup/retention. Unknowns remain
null/unknown. Never include credentials, customer rows, prompts/completions, raw provider
exceptions or unreviewed tool output in ordinary receipts.

Keep expected/attempted/completed/failed/blocked/unrun denominators; never summarize only
successful survivors. Retain failures and partial results. Required failure/block/unrun,
missing evidence or inconsistent cleanup produces nonzero exit. Historical observations
cannot prove a new source/wheel/runtime; refresh identity after changes.

## Cleanup And Final Acceptance

Freeze an exact fixture/resource manifest, protecting borrowed loaded data and user state.
Reconcile unknown writes by read-back. Cleanup deletes only owned approved state and verifies
absence; teardown authority is separate. List retained resources and expiry/cost responsibility.
A cleanup error does not erase the primary result or authorize broader deletion.

Full framework migration acceptance requires selected contracts/docs/examples implemented;
all required offline/artifact/live/refusal/workflow/usability checks satisfied; old skill/
compatibility/vendor runtimes absent; generated discovery/installed plugins accurate; required
apps working on new contracts; and state cleanup/retention reconciled. If a required gate
is blocked, name the achieved milestone rather than declaring capability-complete.

Existing alphas and earlier 603/190/221/80-test or 23/72 app reports are historical baseline
evidence only. No new tests, live calls or publication ran while preparing this specification.

Next: [08. Traceability And Risks](08_TRACEABILITY_AND_RISKS.md).