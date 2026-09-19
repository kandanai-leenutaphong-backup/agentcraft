# Runtime And Evidence Contracts

Status: proposed public contracts. Python/HTTP/schema implementations do not yet exist.

## Records

**OF-03 Stable records.** Persist schema versions and explicit identities. Records reference
artifacts by digest and authorized storage identifier, not arbitrary caller-controlled paths.

| Record | Required contents |
| --- | --- |
| TaskSpec | ID/version, objective/beneficiary, source data and examples, assumptions/questions with owners, collaboration policy, domain adapter ID, writable scope, starting fixture, required outcomes, invariants, registered acceptance IDs, evidence classes, stop policy |
| ExperimentSpec | Task set, baseline architecture, candidate architecture IDs, hypothesis, executor/environment pins, trial/order policy, metric version, promotion rule, authority reference |
| RunSpec | Experiment/task/trial IDs, baseline snapshot, actor/session, executor/adapter/evaluator versions, limits, timestamps and parent run if any |
| CandidateManifest | ID/parent, source/config/prompt/tool/build digests, dependencies, diff reference, hypothesis, state compatibility and restore target |
| RunEvent | Event ID, schema version, run/candidate/actor IDs, parent action, producer sequence, UTC timestamp, monotonic duration where available, kind, outcome, evidence references |
| CheckResult | Check/evaluator version, candidate digest, acceptance class, expected criterion, observed result, pass/fail/blocked/error, duration and artifact references |
| DeploymentReceipt | Candidate/build identity, target, infrastructure version, operation ID, resource inventory, actual read-back, state compatibility, recovery reference |
| RunResult | Lifecycle status, acceptance status, comparison decision, checks, metrics/coverage, submissions, deployment/recovery receipts, failures and cleanup status |

Acceptance classes MUST distinguish offline-unit, synthetic-integration, local-live,
deployed-live and human-observed evidence. A fixture response cannot satisfy a live check.
Mutable status indexes point to immutable submissions and terminal result revisions.
Correction creates a superseding result; historical evidence remains readable.

TaskSpec is the single domain handoff, not a separate discovery subsystem. Its collaboration
policy identifies domain reviewers, decision checkpoints and response bounds; additional
questions are expected. Record input, resulting decisions and domain confirmation as evidence.
Empty questions or no planned collaboration are valid when explicit. Acceptance identifies
observable outcomes and risk-appropriate checks; ExperimentSpec selects one primary objective
from the measurement contract.

Use existing RunEvent records for cooperative design, not a separate collaboration subsystem.
An SME feedback event includes contributor identity, timestamp, observation/question and
relevant evidence, task or candidate references. An agent response links to that event and
records the disposition (apply, clarify, defer or decline) and reason. Applied feedback links
to the resulting version and check results; reviewer follow-up is another attributed event.
Append corrections rather than overwriting guidance. Feedback grants no extra execution
authority and cannot modify frozen acceptance in place. CLI and dashboard use the same
authorized submit/read-back operations; duplicate requests must not duplicate feedback.

## Extension Interfaces

Host code registers collaborators through explicit public protocols:

- Executor: capability discovery, launch isolated session, stream observed events, cancel,
  settle children and report telemetry coverage. Initial adapter targets a supported Copilot
  execution interface; unsupported event formats must be detected, not guessed.
- TaskAdapter: validate prerequisites, prepare baseline/candidate environment, build/launch,
  readiness, typed result read-back, optional deploy/restore, and cleanup of owned resources.
- Evaluator: run registered frozen checks against an immutable candidate and issue receipts.
- ArtifactStore: create immutable bytes, read/verify, list authorized records, and recover
  incomplete saves without repeating computation.
- AuthorityProvider: resolve operator-supplied scope and credentials by reference, authorize
  operation, enforce available limits and report expiry. Credentials never become task data.

Documents name registered IDs and validated parameters, never arbitrary Python imports,
shell snippets or privilege escalation. Adapter implementations own executable commands.
Plugin registration itself is trusted code installation and has a separate review boundary.
Required adapter capabilities are checked before scheduling, including restore support.

## Lifecycle

Proposed run phases: `created -> preflight -> preparing -> running -> evaluating ->
deciding -> finalizing -> terminal`. Bounded repairs return from evaluation to running;
promotion or restoration is tracked under finalization with its own operation receipt.

Terminal statuses: `completed`, `failed`, `blocked`, `cancelled`, `timed_out`.
`completed` means procedure settled, not that a candidate improved. Keep separate fields:
acceptance `passed|failed|not_verified`; comparison
`improved|no_improvement|regressed|inconclusive`; cleanup `settled|retained|incomplete`.
An active worker or unresolved mutation prevents a terminal settlement claim. An interrupted
process is marked for reconciliation; it is not silently reclassified as failed-and-clean.

Repeated start with the same idempotency key returns the existing run; it never launches
another campaign. Repeated cancel/close is safe. Promotion uses expected-current-version
comparison to refuse racing assignments. New work refuses after close begins.

## Telemetry And Storage

**OF-04 Trustworthy capture.** The trusted runner observes actions, not candidate-written
summaries. Distinguish action events, tool dispatches, nested commands, application calls,
service operations and model requests with parent IDs to prevent accidental double counting.
Store attempted, completed, failed and unknown outcomes separately. Record source and
coverage for every derived metric. Payload capture is opt-in and data-policy controlled.

Monotonic clocks measure local intervals; UTC correlates hosts. Clock uncertainty is explicit.
Producer sequence and event IDs support deduplication; missing sequence ranges mark partial
coverage. Concurrent child durations cannot be summed into elapsed wall-clock time.

Initial backend: local SQLite transactions for event/run indexes plus content-addressed
artifact files. This is not a multi-host database or distributed lock claim. Schema migrations
preserve old records; metric changes do not rewrite historical values. Foreign-owner reads,
path traversal, conflicting writes and artifact hash mismatches refuse.

**OF-05 Durable evidence.** Stage completed results, commit create-if-absent-or-identical,
verify read-back, then acknowledge finalization. An unknown save preserves recoverable bytes.
Use the existing recovery capability where suitable. A damaged/missing artifact marks its
dependent evidence invalid. Reports must not silently omit failed or incomplete runs.

## Evaluation Trust Boundary

**OF-06 Independent acceptance.** Candidate workspaces cannot write evaluator tests,
expected labels, baseline receipts, authority manifests or authoritative telemetry. Run the
evaluator under separate write permissions/process isolation; separate identities or stronger
isolation are required when the worker otherwise has machine/cloud administrative access.

The worker may author application tests, but cannot replace frozen acceptance with them.
Development feedback is allowed and labeled; held-out checks remain outside the worker's
context until the final evaluation policy allows disclosure. An integrity hash detects edits
but alone is not an access boundary. If required isolation is unavailable, record a refusal
or explicitly non-independent evidence; never claim independent benchmark acceptance.

Cloud provisioning authority for the task is not authority over evaluator storage or audit
records. The dashboard reads the same authorized service as the CLI; it cannot turn a failed
check green. Human override is a separately attributed event, not automatic acceptance.