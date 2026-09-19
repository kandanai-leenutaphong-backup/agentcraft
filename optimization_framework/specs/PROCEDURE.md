# Cooperative Optimization Procedure

Status: normative specification; command names below are proposed and not executable yet.

## Operating Contract

**OF-01 Portable procedure.** A new coding agent MUST run the same lifecycle for a supplied
use case without importing Investigation internals or relying on the author's chat history.
SMEs and operators contribute objectives, authority, examples, corrections and review.
The agent uses the documented procedure to handle technical execution and measurement.

**OF-02 Automatic execution.** The runner MUST capture lifecycle and observable actions,
evaluate candidates, persist results, and enforce stop conditions automatically. Skill text
and agent self-reports cannot substitute for instrumentation or acceptance checks.

Minimum operator inputs:

- Objective and target repository/artifact, including explicitly writable boundaries.
- Versioned task pack or permission to author one before measurement; required outcome and
  quality/security invariants; held-out acceptance controlled by the evaluator.
- Registered executor, adapter, evaluator, environment and model configuration.
- Execution authority from [RECOVERY_AND_AUTHORITY.md](RECOVERY_AND_AUTHORITY.md).
- Trial policy, improvement rule, budgets, deadlines, storage root and retention policy.

Intake is bounded to one useful experiment. The agent may turn a brief, source data and SME
examples into the task pack; SMEs confirm domain meaning, not technical design. Record
assumptions, unresolved questions and their owners. No exhaustive requirements phase is needed.
After clarification, missing required inputs produce an exact report and `blocked` status,
not an improvised grant, fabricated measurement, or infinite retry.

Domain clarification and review are normal collaboration, including questions discovered
during a run. Record the input and resulting decision; track framework support separately
to expose usability friction, not penalize human involvement. Never disclose held-out answers.
Changed objectives or acceptance require a new task version and comparison series, not edited
criteria within the current experiment.

## Procedure

| Step | Automated action | Exit evidence |
| --- | --- | --- |
| 1. Discover and clarify | Load skill, inspect capabilities, resolve bounded domain questions and prepare task pack; validate adapter compatibility | Discovery receipt, task version, assumptions and domain confirmation where required |
| 2. Preflight | Validate permissions, credentials by safe probes, dependencies, telemetry support, quotas, evaluator isolation and recovery prerequisites | Ready receipt or field-addressed refusal; no mutation on failed preflight |
| 3. Freeze | Pin baseline bytes, task, evaluator, fixtures, environment and comparison policy; protect existing user changes | Immutable experiment manifest and recoverable baseline |
| 4. Establish baseline | Verify starting system, then perform the task on current architecture in an isolated measured session | Baseline change-effort run plus functional evidence, not just an unchanged-app test |
| 5. Form candidate | State one falsifiable improvement hypothesis and smallest scoped change; start from the pinned comparison baseline | Candidate ID, parent, hypothesis, limits and writable paths |
| 6. Execute | Launch coding agent; collect reads, edits, commands, delegated work and observed calls; allow exploratory checks | Append-only events, code/config/prompt changes and exploratory results |
| 7. Submit and verify | Freeze submitted bytes, run trusted acceptance, launch exact artifact as required, inspect UI and read back stored output | Candidate digest, per-check results, deployment/result receipts |
| 8. Repair or stop | Return bounded development feedback; repair within budget, or preserve failed/blocked/cancelled result | Each submission and repair retained; no silent rerun |
| 9. Compare | Compute metrics, quality gates and uncertainty using frozen policy | Improved, no improvement, regressed, or inconclusive decision with evidence |
| 10. Promote or restore | Promote verified candidate only when policy allows; otherwise restore known-good version when target was changed | Read-back of artifact identity, application behavior and compatible state |
| 11. Report and settle | Export results, reconcile resources, close workers, retain recovery evidence and apply owned cleanup policy | Final report, telemetry coverage, resource inventory and settled lifecycle |

Do not start comparative optimization before a valid baseline measurement is recorded.
Where useful, run a small development probe before expensive acceptance, using existing
checks and the resolved candidate configuration. A probe tests execution viability, not
improvement; retain failures and count probe effort without presenting it as formal acceptance.
Use task budgets and observed results to stop, not mandatory generation or diversity quotas.

Cooperative design follows observation -> clarification -> decision -> versioned change ->
verification -> review. Show the SME representative recorded cases and limitations, not just
an aggregate score. Feedback may be applied, questioned or declined with an evidence-backed
reason; it never substitutes for required checks.

The next outer iteration begins only after the prior iteration's writers and mutations
are settled. Parallel independent runs require separate workspaces, data namespaces and
resources; shared targets serialize. A live deployment never runs while its candidate is
still being edited. A meaningful artifact change creates a new candidate digest.

## Failure And Stop Rules

- Stop on expired authority, exhausted limits, deadline, unsafe migration, integrity failure,
  unauthorized path changes or unaccounted external mutations. Preserve evidence.
- A failed test permits a bounded repair, not weaker tests or broader authority.
- Provider/command failures are observations; never silently retry a non-idempotent operation.
- Cancellation signals workers, settles children, reads ambiguous external effects, and records
  incomplete cleanup. A process still running is not a completed run.
- Save recovery recommits completed evidence without rerunning models or application work.
- Pause for missing authority, prerequisites or domain decisions. Ask the relevant person
  and record the answer; do not guess to preserve an autonomy score.
- A valid no-improvement result is preferable to a manufactured success. A new hypothesis
  needs remaining budget; it cannot extend a campaign indefinitely.

## Proposed User Interface

One CLI fronts the service. These signatures define future behavior; they were not run:

```text
optimization describe --json
optimization preflight --experiment <document>
optimization run --experiment <document>
optimization status --run <id> --json
optimization cancel --run <id>
optimization restore --run <id> --version <known-good-id>
optimization report --run <id> --format json|csv|html
optimization recover --run <id>
```

`run` owns the full procedure, including configured iterations and acceptance. Users should
not need to manually issue one command per phase. `recover` reconciles recorded state and
pending evidence; it does not blindly repeat unfinished computation. Structured responses
include status, IDs, evidence references and actionable refusal codes. Help and errors expose
the same contract as the dashboard. Accepted asynchronous work is not reported as completed.

## Skill Deliverable

One primary skill, proposed at `skills/optimization-experiment/SKILL.md`, MUST provide:

1. Trigger description for measured iterative improvement in any supported domain.
2. Required inputs, capability discovery, preflight and the single run entry point.
3. Links to procedure, metrics, authority and recovery references; no duplicated rules.
4. Interpretation of reports, repair feedback, stop conditions and promotion decisions.
5. A small domain-neutral example and guidance for implementing a missing task adapter.

Installation MUST register the skill in the target coding agent's native discovery system
and resolve bundled reference paths independently of this checkout. Merely placing a file
inside this folder does not count as discoverability. Unsupported clients refuse clearly.
Keep optional adapter guidance separate; do not require a large skill chain for normal runs.

The fresh-overseer test in [ACCEPTANCE.md](ACCEPTANCE.md#fresh-overseer-test) proves actual
discovery and execution. Record documentation gaps and support needed so the procedure can
improve; helpful SME participation does not make a run fail.

Keep additions justified by an experiment that cannot run or a conclusion that cannot be
trusted without them. Reuse this loop; no separate domain-intake service or extra dashboard
is required. Acceptance depth follows the task's consequences and deployment scope.