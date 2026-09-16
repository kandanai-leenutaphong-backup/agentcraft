---
name: library-development
description: "Use when designing, implementing, extending, testing, or preparing a reusable capability library: caller-first APIs, native SDK reuse, independent packages, Azure live-test deployment, public-import Python feature scenarios, composed workflows, and developer-usability acceptance. Live execution, access changes, cleanup, and publication require explicit scoped authorization."
---

# Capability Library Development

> **Superseded for the unified migration:** [final specification](../specs/20260916T045818Z_UNIFIED_LIBRARY_SPEC/README.md).
> Retained as a historical input, not a separate active plan. The final spec's library-first
> decisions, mandatory runtime removal, app-adoption status and verification gates control.

**Deliver a usable library plus a reproducible live Azure proving environment.** Correct
behavior against real services and straightforward developer consumption are independent
completion gates. Offline tests, a deployment script, or a short example alone close neither.

This is the canonical playbook authored for explicit use from this directory. Its filename
and location do not register an automatically discovered client skill. It creates no library,
cloud resource, role assignment, live-test runner, or publication merely by being read.

## Scope And Authorities

Use for new capabilities and meaningful extensions to existing libraries. For a narrow fix,
reuse the existing contract, scenarios, environment, and evidence; rerun the affected checks
without reopening the whole design. Stop at a requested design or offline milestone, but
label that milestone honestly rather than calling the capability complete.

The method is portable; the final section binds it to Agentcraft's Python/uv workspace.
Read the consuming repository's architecture before placing components or dependencies.
Follow its declared owners, public APIs, security policy, and deployment authority.

| Responsibility | Existing Authority |
| --- | --- |
| Scope, proportional checks, and authority | [Work contract](../.github/instructions/work-contract.instructions.md) |
| Capability ownership and dependency direction | [Architecture principles](../.github/instructions/architecture-principles.instructions.md) |
| This workspace's dependency/build/release commands | [Libraries workspace guide](README.md) |
| One deployment directory and operator entry point | [Deployment rules](../.github/instructions/deployment.instructions.md) |
| Azure target, provisioning, and ownership procedure | [Azure infrastructure skill](../.github/skills/azure-cli-infra-management/SKILL.md) |
| Caller/workload identity and access changes | [Azure access skill](../.github/skills/azure-access-management/SKILL.md) |
| Official-source acquisition and provenance | [Web-resource skill](../.github/skills/web-resource/SKILL.md) |

Reuse these authorities; do not copy their implementations or silently grant new permissions.
No mandatory agent team, fixed document count, or exhaustive research phase is required.

## Unit Of Delivery

| Deliverable | Required Outcome |
| --- | --- |
| Public library | Independently installable, versioned capability with a small documented API and explicit unsupported behavior |
| Caller guide and examples | Complete setup, imports, ordinary calls, result handling, failure recovery, and cleanup through public APIs |
| Contract and coverage matrix | Advertised features, providers, modes, guarantees, and workflows mapped to independent acceptance criteria |
| Offline suite | Fast positive/refusal checks plus tests through real dependency boundaries with controlled I/O |
| Azure deployment | Reproducible provisioning, identity integration, verification, and owned teardown of the live proving environment |
| Feature scripts | Structured, individually runnable Python scenarios that call the installed library against real Azure dependencies |
| Workflow scripts | Import and compose feature functions, pass actual outputs between steps, and verify the end-to-end result |
| Evidence record | Exact artifact/environment identity, per-case outcomes, read-back, coverage, costs or unknowns, and cleanup state |

Preserve suitable existing files and names. A library that adds no useful rule or reduction
in caller effort may be better delivered as a recipe or extension of an existing owner.
Do not invent a package merely to satisfy this layout.

## Iterative Development Loop

### 1. Start With The Caller

Name the task, intended developer, supported host environments, and observable result.
Write the smallest realistic public usage example, including required identity/configuration,
result inspection, resource lifetime, and one important refusal. Name explicit non-goals.

Separate initial host setup from repeated calls in an already configured host. A three-line
call that depends on undocumented setup is not a three-line integration. Define acceptance
for both. Configuration must not silently enable cloud access, infer tenant policy, or hide
an application-specific dependency.

Identify the next falsifiable behavior and cheapest useful check. Implement one small
vertical increment; do not finish every design document before the first executable example.

### 2. Establish Reuse And The Added Value

Search the capability catalogue, current owners, real call sites, and official SDK/framework
references. Select actual dependency versions and probe load-bearing uncertainties locally.
Record source provenance when acquiring documentation; distinguish current, classic, preview,
unreleased, and locally observed behavior.

For each substantial behavior choose: use directly, document a recipe, extend an owner,
wrap a demonstrated gap, or implement new behavior. State the concrete reason for custom code.
SDKs should continue to own their native protocols, model types, serializers, paging, and
credential machinery wherever those public APIs meet the requirement.

Standardize the discipline, not every library's architecture. A cross-service facade can
own common request/result semantics; another library can retain useful framework types.
Neither requires a universal client, duplicate tool loop, generic option escape hatch, or
custom transport without a demonstrated need.

### 3. Specify The Next Contract Slice

Define public imports, input/output shapes, native semantics, capability limits, and refusal
behavior. Include authority boundaries, ownership of borrowed/created resources, cancellation,
timeouts, concurrency, retry policy, and partial/unknown outcomes where relevant.

- Import, construction, and description perform no remote calls or credential acquisition.
- Configuration and credentials enter through trusted host inputs; requests cannot widen them.
- Mutations and paid operations require explicit grants; a local grant is not Azure RBAC.
- Unsupported capabilities refuse before side effects rather than quietly emulating a weaker one.
- Returned data preserves relevant native meaning, ordering, completion, and verification evidence.
- Timeouts and cancellation do not imply rollback, zero charges, or permission to replay a write.
- Application identity, record ownership, retention, and deployment policy remain host-owned.

Use one coverage matrix derived from the reviewed contract. Give each case a stable ID,
public symbol, provider/mode, prerequisites, positive or expected-refusal path, independent
oracle, feature script, and workflow membership. Freeze expected support before a run;
`describe()` must not supply its own passing criteria. Removing support cannot silently
turn a failing promised feature into a successful refusal.

### 4. Implement And Validate Immediately

Implement the smallest supported call through the chosen dependency, then run its focused
check before adding another feature. Add the corresponding public-import feature scenario
as the feature grows; live testing must not remain a design-only appendix until release.

Test native serialization, authentication-policy wiring, argument forwarding, response
normalization, streaming completion, and resource cleanup where used. Mock external I/O
at the boundary being tested, not the SDK method whose integration correctness is the claim.
Add a lower-boundary regression when consumer execution reveals a gap in higher-level mocks.

Exercise matching positive and negative cases for authorization, integrity, concurrency,
and state changes. Preserve errors and denominators. Upstream gap tests should trigger
reassessment when the dependency changes, not preserve an obsolete workaround indefinitely.

### 5. Build The Actual Consumer Artifact

Follow the workspace's existing build/release commands. Build wheel and sdist, rebuild from
the sdist, and install the candidate in an isolated environment outside the checkout.
Verify the imported module comes from that artifact, not an editable source tree, skill,
template application, current working directory, or `PYTHONPATH` injection.

Exercise base-only installation, implemented extras, supported environments, and declared
dependency floors in proportion to the claims. Record exact tested combinations; a shared
lock does not establish every allowed dependency combination. Inspect distributions for
undeclared/local-path requirements, unintended source/data, notices, and typing metadata.

Run examples and acceptance against that candidate. Development may use editable installs;
final live evidence must identify the installed artifact. If source changes, rebuild before
attributing new source results to a release artifact. Publication remains a separate action.

## Mandatory Azure Proving Environment

Every capability in this portfolio requires an actual Azure deployment supporting its live
feature and workflow tests before capability-complete acceptance. Deploy the required service
resources and model deployments; also deploy a reference host/worker when hosted behavior is
part of the promise. A client library does not need an artificial HTTP service merely to
be called a deployment. A resource group alone does not prove a capability works.

### Authority Before Execution

Prepare scripts and plans without executing cloud mutations. Before a live run, obtain explicit
authorization covering tenant/subscription or Fabric workspace, resource IDs/names, regions,
SKUs/capacity, identities, operations, synthetic data, model/tool calls, network policy, spend
and call/token/time bounds, lifetime, retention, and exact cleanup ownership.

Provisioning, access grants, test mutations, teardown, and publication are distinct authorities;
one approved plan may enumerate them, but an omitted permission is not implied. Existing Azure
login, inherited Owner access, or a previous resource-group approval is insufficient.
If authority or capacity is missing, finish the authorized preparation and report `BLOCKED`.
Do not silently drop live acceptance, enable public access, weaken auth, or switch targets.

### One Documented Operator Sequence

The owning deployment root keeps configuration, infrastructure, orchestration, and operational
records together. Its `deploy/deploy.sh` is the operator entry point; reuse or extend it,
not a competing sequence in shell history. Exact subcommand names are host-owned.

The entry point must offer:

1. Offline runner/preflight tests and a no-mutation plan identifying exact targets and grants.
2. Idempotent authorized apply: verify existing ownership and read back provisioned fields.
3. Verification of resources, authentication, network reachability, and service readiness;
   verify any hosted endpoint externally through its real auth path.
4. Selection of one feature case, a workflow, or the full approved live suite.
5. A structured report and reconciliation of run-owned fixtures after success or failure.
6. Explicit owned teardown with absence read-back and visible unresolved remnants.

Document commands in order, prerequisites, expected results, failures, and recovery. Keep
non-secret targets in environment-specific data files; do not execute them as arbitrary code.
Use approved identity injection, never repository secrets or key-fetching fallback.
One writer owns each target and fixture namespace. Do not silently adopt existing resources.

Unit-test the runner's wrong-target, missing-authority, collision, budget, and cleanup refusals
before cloud use. Enforce bounded calls and deadlines where possible; estimates and delayed
billing are not hard spending caps. Missing price or usage attribution remains unknown.

### Source And Deployment Ownership

Feature and workflow scenario source stays with the library, beside its contract and tests.
Deployment configuration, resource lifecycle, orchestration entry points, and live receipts
stay in the owning deployment directory. Deployment imports or invokes the scenario suite;
the library runtime never imports deployment or application code.

Illustrative layout, not files installed by this playbook:

```text
libraries/<capability>/
  README.md, CONTRACT.md, USAGE.md
  pyproject.toml
  src/<public_package>/
  tests/                         offline checks
  live_tests/                    outside default offline discovery
    __init__.py
    context.py                   explicit test-only configuration and fixture context
    reporting.py                 common result serialization; no domain implementation
    features/
      __init__.py
      write_record.py
      read_record.py
    workflows/
      __init__.py
      write_then_read.py
    runner.py                    registered cases, selection, coverage, and exit status
deploy/
  deploy.sh, README.md
  env/<environment>.env          non-secret targets
  infra/                        owned declarative resource setup
  records/                      approved, payload-free live evidence
```

Reuse an existing `tests/live_tests/` directory instead of moving it to match the picture,
but ensure default test discovery cannot execute it. Live imports perform no I/O; missing
an explicit live invocation must refuse. Scripts are test assets, not runtime dependencies.

## Public-Import Feature Scripts

Each advertised feature has a structured, independently runnable Python module with explicit
provider/mode variants. Each module exposes a callable function, for example
`async def run(context) -> CaseResult`, and a thin `main()` entry point. Direct execution
and orchestrated execution use the same function and authorization/preflight checks.

Each case must:

1. Verify installed artifact identity, approved target, principal, and prerequisites before I/O.
2. Create or receive fresh synthetic fixtures with exact run/case ownership and expected values.
3. Import the installed package through public exports and perform the operation under test.
4. Inspect real outputs, item statuses, exceptions, terminal events, and usage as applicable.
5. Independently assert the contract; use fresh read/status calls when persistence is claimed.
6. Exercise the relevant denial, invalid input, conflict, boundary, or failure variants.
7. Return structured case results and reconcile/clean up owned fixtures under approved authority.

The central body must look like credible developer usage. For the current libraries that
means public imports such as `from azdata import connect, QueryRequest` or
`from llm_interface import connect`, not internal adapters, raw REST equivalents, or CLI CRUD.
Keep real library calls visible; helpers may remove setup/reporting repetition, not hide a
second implementation or a giant generic dispatcher behind the scenario's name.

Setup may use authorized native SDK/CLI operations. An independent SDK/query observer can
corroborate state. Neither counts as the library's positive feature execution. Mocks or canned
service responses cannot produce `PASS_LIVE`. Synthetic **inputs on real services** are valid;
synthetic service responses are offline evidence.

Predeclare immutable expected results before writes. Read back using a fresh client where
practical; assert values, version/ETag, absence, batch identity, or other promised semantics,
not only HTTP success or resource presence. Use bounded service-aware polling for eventual
consistency. Tests must fail nonzero under normal and optimized Python; use explicit checks
or a test framework, not only bare `assert` statements in standalone scripts.

For permissions, test local library policy refusal and actual Azure denial separately using
approved restricted identities and an authorized observer. Do not revoke a human's grants
or test unrelated production targets. Keep setup identity separate from least-privilege
runtime identity so privileged fixture creation cannot mask a missing permission.

Live model tests use bounded calls and stable structural/tool/result assertions. Quality
claims additionally need a versioned dataset, scorer, threshold, and retained case outcomes;
one plausible generated answer or exact-string sample match is not quality evidence.

## Imported, Composed Workflows

A suite runs feature cases. A workflow demonstrates meaningful composition. Import the
feature functions and pass their actual outputs to downstream calls, preserving identity,
run IDs, lifecycle, and ownership. Do not parse subprocess stdout or duplicate feature logic.

When a feature must participate in a longer workflow, separate its operation/check function
from standalone fixture ownership. The individual entry point can create and clean its own
fixture; the workflow owns the shared fixture until its final read-back and cleanup. An
intermediate feature must not delete the output the next step needs.

Select workflows from the capability's promised user outcomes. Examples:

- Data capability: write, query across pages, update, fresh read-back, delete, and verify absence.
- Model capability: invoke, validate structured output, run an authorized tool-using stream,
  consume terminal state, and retrieve the completed result without another model call.
- Cross-library workflow, only when in scope: retrieve authorized evidence, pass it into an
  agent, store its result, and independently read it back.

The workflow runner reports per-step and overall outcomes; a correct intermediate call does
not make an incorrect final result pass. Cover the promised interruption/recovery behavior
and prevent blind replay of operations that may already have taken effect.

## Coverage, Evidence, And Cleanup

Map every advertised feature/provider/mode/guarantee to required live cases and every promised
composition to a workflow. Reuse shared parameterized cases; do not invent one test per SDK
method or force unsupported services to implement identical semantics. Freeze the matrix
before execution and retain omitted cases with their reasons.

| Outcome | Meaning | Completion Effect |
| --- | --- | --- |
| `PASS_LIVE` | Installed library called the real approved service and met the positive evidence rule | Counts for that exact feature and environment |
| `PASS_REFUSAL` | Declared negative/unsupported behavior refused as expected; no unintended effect | Counts only for refusal coverage; record local versus provider-enforced denial |
| `FAIL` | Observed behavior contradicts the frozen contract/oracle | Blocks acceptance |
| `BLOCKED` | Missing authority, fixture, identity, provider support, budget, or observable evidence | Blocks acceptance for required cases |
| `NOT_RUN` | Not attempted or deliberately skipped, with reason | Blocks acceptance for required cases |

Unsupported cases cannot replace required positive cases. A scope change must be explicit;
report its excluded features without retaining their completeness claim. Controlled response
loss or fault injection against a live service is labeled hybrid resilience evidence, not
proof that Azure naturally produced that fault. Do not overload services to manufacture errors.

Each record includes case/workflow IDs, contract version, library version and artifact digest,
import origin, dependency versions, Python/OS, Azure target and non-secret principal identity,
provider/model/API versions, run/request/trace IDs, UTC start/end, requested/achieved evidence,
observed status/count/digest/version, measured latency/attempts/usage, caveats, and cleanup state.
Missing observations remain null/unknown, not zero or success. No credentials, tokens, raw
customer content, exception payloads, or unreviewed model/tool output enters the report.

Write machine-readable results plus a short human summary, including partial results on failure.
The runner exits nonzero when a required case fails, blocks, is unrun, lacks evidence, or
leaves cleanup inconsistent with the approved retention plan. Reports must retain expected,
attempted, completed, failed, blocked, and unrun denominators; never summarize only survivors.

Maintain an exact fixture/resource manifest. Reconcile after interruption; an uncertain
write may have landed. Cleanup deletes only owned resources under approved authority and
reads back absence. Teardown permission does not follow automatically from test permission.
List all remaining resources and retention/expiry responsibilities; a cleanup failure must
not erase the original test outcome or become an implicit permission for broader deletion.

## Developer-Usability Gate

Live functionality does not excuse awkward consumption. Use an independent consumer and the
public guide, without requiring private source knowledge, reference-app state, or manual SDK
event parsing for supported basic tasks. Where available, reuse the live feature/workflow
scripts as complete examples; do not make developer documentation a separate drifting copy.

Verify initial installation/configuration, normal calls, error recovery, and cleanup. For a
promised compatible provider swap, retain caller/tool/event-consumer source and change only
the documented binding and any required fresh session. Do not promise swaps across different
capabilities or native semantics.

Record documentation lookups, clarification requests, caller decisions, glue code including
host setup, failed attempts, and measured time to a correct result when claiming lower effort.
Compare equivalent tasks and safeguards with direct SDK/framework use; do not achieve fewer
lines by omitting auth, cleanup, integrity checks, or error handling. If no usability benefit
or useful additional rule is demonstrated, simplify the wrapper or prefer a recipe.

## Completion And Change Discipline

**Capability-complete requires all of the following for its advertised scope:**

- Public contract, guide, and examples describe implemented behavior and explicit limits.
- Focused offline/native-boundary checks pass; artifact installation is independently verified.
- Deployment and live runner are reproducible through the documented operator entry point.
- Every required positive feature and workflow passes live on the identified artifact.
- Matching refusal/integrity cases pass; no required case is blocked, unrun, or silently skipped.
- Developer setup and usage acceptance pass; unmeasured comparative claims remain unmeasured.
- Results are read back, reports are retained, and cleanup or approved retention is reconciled.

Label earlier milestones as research, implemented/offline-verified, artifact-verified, or
partially live-verified. Separate source evidence, artifact evidence, live environment evidence,
and publication status. Existing alphas are not retroactively certified by this document.

On code, dependency, contract, model, or deployed-configuration changes, rerun affected
acceptance and shared-boundary regressions. Tie fresh evidence to fresh artifact/environment
identity. Preserve historical results with their scope; do not relabel old wheels as tested
after a source fix. Evidence-based scope determines regression breadth, not a fixed test count.

Update the capability's authoritative contract, coverage, guide, and verification record when
their facts change. Update root project status only when the change makes it wrong. Source
retirement, consumer migration, package publication, and cloud rollout need their own stated
scope and authority. A successful live test does not automatically authorize production use.

## Agentcraft Profile And Lessons

- Use [README.md](README.md#workspace-model) for explicit uv members, shared-lock ownership,
  isolated environments, dependency extras, and release commands. Research-only directories
  are not workspace packages. Keep this playbook out of runtime dependency resolution.
- Reuse the root [deployment runbook](../deploy/README.md) for the shared connector proving
  environment. A separately owned template deployment has its own boundary; never create
  a second competing entry point for the same target. Group-only verification is not service
  provisioning or live feature acceptance.
- Extend the existing [connector live-test design](azure-data-connectors/tests/live_tests/LIVE_TEST_DESIGN.md)
  into executable public-import scenarios when implementing that suite. Its numbered cases
  are specifications, not proof of executions.
- The [connector verification record](azure-data-connectors/VERIFICATION.md#template-integration-source-only)
  records consumer-discovered authentication and redirect integration defects. Test actual
  SDK policy/transport wiring, not only mocks above it.
- The [LLM validation record](llm-interface/VALIDATION.md#low-friction-acceptance) separates
  initial setup from repeat-call usability and names unmeasured claims. Preserve that distinction.
- [Data connector contracts](azure-data-connectors/CONTRACT.md) standardize cross-provider
  semantics; [LLM contracts](llm-interface/CONTRACT.md) retain useful framework surfaces.
  Reuse their demonstrated practices without requiring every library to copy either API.

This profile supplies local entry points, not current live-status claims. Read the latest
capability evidence and approved deployment targets before executing any work.