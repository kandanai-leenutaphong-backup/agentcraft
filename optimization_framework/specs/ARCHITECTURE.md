# Architecture And Deliverable Map

## Boundaries

**OF-09 Modular framework.** Build one cohesive package initially, not a service fleet.
CLI and HTTP are adapters over one run service. Dashboard and reporting consume the same
results and metric calculations. Generic contracts know no Investigation types.

Dependency direction: interface adapters -> run service -> contracts and injected execution,
evaluation, storage and authority collaborators. Investigation adapter depends on public
framework contracts and invokes the application's declared surfaces. Investigation never
imports the optimization composition root. The composition root registers trusted adapters.

Framework application authorization applies equally to CLI/API automation and UI callers.
Local versus cloud host configuration must be explicit; no production auth bypass is a
development convenience. A substantial operation is callable and its result readable back.

## Proposed Code Artifacts

Paths are relative to the framework root (the parent of this specs folder) unless identified otherwise. These are implementation
destinations, not files delivered by this specification. Small modules may be combined if
ownership and public contracts remain explicit; avoid a one-file-per-class framework.

| Artifact | Owner and responsibility | Verification |
| --- | --- | --- |
| `src/optimization_framework/contracts.py` | Versioned typed records and collaborator protocols | Round trips, unsupported versions, invalid/refused input |
| `src/optimization_framework/service.py` | Lifecycle, bounded iterations, promotion policy and authorization | Positive lifecycle, stop/cancel, concurrency and no-new-work-after-close |
| `src/optimization_framework/workspaces.py` | Isolated snapshots, candidate boundaries, diff capture | Dirty checkout preserved; foreign paths and secrets excluded |
| `src/optimization_framework/executors/copilot.py` | Supported native execution and event adapter | Real executor probe, child settlement, incomplete telemetry |
| `src/optimization_framework/evaluation.py` | Frozen independent acceptance | Known-good passes, deliberately wrong candidate fails, tampering refuses |
| `src/optimization_framework/metrics.py` | Versioned metric derivation | Golden events including failures, concurrency and gaps |
| `src/optimization_framework/store.py` | Owner-scoped SQLite index and immutable artifacts | Read-back, wrong-owner refusal, interrupted/conflicting saves |
| `src/optimization_framework/versions.py` | Source/definition/build/deployment/state manifests | Identity resolution and incompatible restore refusal |
| `src/optimization_framework/recovery.py` | Reconciliation and adapter-driven restore | Ambiguous-operation read-back and exact-version recovery |
| `src/optimization_framework/authority.py` | Scope validation, operation authorization and enforceable bounds | Allowed operation plus out-of-scope/expired refusal |
| `src/optimization_framework/handoff.py` | Fresh-session launch envelope and adoption assessment | No inherited conversation; supported role/executor identity recorded |
| `src/optimization_framework/reporting.py` | JSON, CSV and self-contained HTML export | Same facts as API; failed/incomplete evidence retained |
| `src/optimization_framework/cli.py`, `api.py` | Thin callers of shared service | Same decision and result read-back through both |
| `frontend/src/` | Dashboard views and API client | Real controls, accessible/responsive browser journeys |
| `adapters/investigation/` | App lifecycle, build, readiness, deployment, results and restore | Exact-artifact local and authorized deployed acceptance |
| `tasks/investigation/` | Four versioned task packs | Requirement-to-check mapping and held-out variants |
| `skills/optimization-experiment/SKILL.md` | Native-discoverable process entry point | Clean-session discovery and execution |
| `tests/` | Framework, metric, browser and handoff tests | Frozen acceptance outside candidate write authority |
| `deploy/deploy.sh`, `deploy/README.md` | Framework setup, launch, test, verification and owned teardown | New operator follows one documented sequence |
| `pyproject.toml`, lockfile, frontend package metadata | Reproducible installed runtime and build | Fresh isolated install; no author-machine path dependencies |

Application release code stays in Investigation's existing deployment directory. Framework
deployment scripts deploy the framework, not a duplicate implementation of app deployment.
An adapter invokes the relevant owner's entry point and records its evidence.

## Existing Owners

Source-reviewed references; no tests or live campaigns were run for this specification:

- [Existing optimizer](../../.github/skills/agent-optimization/README.md) and
  [contract](../../.github/skills/agent-optimization/CONTRACT.md): reuse compatible evidence,
  immutable-generation and replay contracts; do not inherit detector-specific lifecycle.
- [Recovery capability](../../.github/skills/recoverable-jobs/SKILL.md): reuse completed-output
  save/recommit semantics, not scheduling or automatic model retries.
- [Agent configuration](../../libraries/modular-agents/README.md): extend existing `agentconfig`
  ownership for reusable definitions and tool metadata rather than a second agent registry.
- [Model execution](../../libraries/llm-interface/README.md): retain the single model execution
  owner. A coding-session adapter must not become a second application agent loop.
- [Investigation owner map](../../template_apps/investigation_app/docs/ARCHITECTURE_OVERVIEW.md)
  and [runbook](../../template_apps/investigation_app/deploy/README.md): first host adapter;
  current launcher is local-only and does not implement the proposed cloud release path.
- [Custom Optimizer](../../template_apps/custom_optimizer/README.md): separate existing host,
  not copied into this framework. Historical state and receipts remain unchanged.

Public API suitability must be verified before import. Reuse is not a commitment to copy
research code or force a domain-specific abstraction into a generic process. Shared source
viewing, rendering, authentication and event-stream mechanisms keep their existing owners.

Custom Optimizer provides useful workflow patterns: show data context beside versioned tools,
agent definitions and measured outcomes; require a measured baseline before optimization;
link each candidate's hypothesis and changes to parent evidence; inspect retained case replays
without rerunning models. Reuse these patterns inside the existing views, not an extra dashboard.
Its [guidance ledger](../../.github/skills/agent-optimization/src/agent_optimization/service.py)
already preserves operator input. Extend that concept to attributed SME feedback linked to
the affected decision, candidate and verification result, with a simple submission control.
Do not inherit fixed generation quotas, classification-only scoring or repeated evaluation
as an untouched holdout. Recorded examples are inspection evidence, not full execution replay.

## Dashboard And Reports

**OF-10 Unified visualization.** Ship four views:

1. Comparison: tasks/architectures, success rate, time, retries, actions, footprint, cost and
   telemetry coverage; show sample size, failed trials and evidence class.
2. Run timeline: phase intervals, actions, submissions, failures, collaboration and recovery.
3. Candidate evidence: source/config/prompt diff, check output, screenshots, deployment and
   persisted-result identity; navigable to baseline and previous known-good version.
4. Experiment report: decision, thresholds, limitations, construction cost, fresh-agent
   handoff result and outstanding cloud resources. Export without repeating experiments.

Start/cancel/restore controls use the shared authorized API, indicate pending operations,
surface refusals and prevent duplicate requests. Restore is never a silent destructive click.
Keep task/data context, selected tool/agent versions and outcomes linked across these views.
Add one feedback form to candidate evidence: submit an SME observation, show its recorded
author and disposition, and follow links to the resulting change and checks. No extra view
or approval workflow is required; review checkpoints remain task-defined.

Recorded-case inspection shows retained inputs, instructions, tool evidence, response and
evaluation, with capture coverage and unscored fields explicit. Include success and failure
examples where available; never present selected examples as the whole cohort or historical
inspection as a fresh execution. Restrict held-out details according to evaluator policy.
Progress may stream or poll the public API; reconnection recovers from stored sequence IDs.
Verify desktop/mobile geometry, keyboard operation, loading/empty/error states and persisted
read-back. Avoid a decorative landing page. Every plotted number traces to events and receipts.

## Agent Structure Hypothesis

**OF-11 Architecture experiment.** Compare current structure against capability-oriented
composition: agent definitions select versioned prompts, tools and policies; capabilities
own typed contracts, implementation, authorization, tests and optional UI contribution.
Backend/frontend build boundaries remain intact, with one traceable capability owner.

First candidate improvements: single-source tool metadata, explicit capability selection,
source discovery, dependency-aware removal, direct authorized tool tests and development
reload. Discovery must not automatically grant a new tool to every agent. Agent-controlled UI
uses typed authorized resource updates, never generated executable DOM or arbitrary code.

These are falsifiable hypotheses, not mandatory broad refactors. Change one factor at a time,
measure equivalent variations and account for construction cost. Preserve existing tests and
public contracts unless the task explicitly permits changing them. Demonstrate portability
with a non-Investigation task before declaring the design domain-neutral.