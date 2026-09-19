# Acceptance And Delivery

Status: partial: local process working; full acceptance blocked/incomplete. [Consolidated evidence](../reports/IMPLEMENTATION_REPORT.md). Specifications are not evidence that a gate passed.

## Investigation Task Pack

**OF-14 End-to-end variations.** Freeze concrete fixtures and expected outcomes before coding.
Each variation includes exploratory tests, independent acceptance, artifact identity and
persisted read-back where state changes. Retain existing required behavior and auth checks.

| Proposed task document | Change and required evidence |
| --- | --- |
| `tasks/investigation/tool_availability.yaml` | Add a registered tool, disable/remove an optional tool and replace a selection across task variants. Verify advertised schemas and actual dispatch; unavailable tool refuses. Required Investigator tools and saved-version dependencies cannot silently break. |
| `tasks/investigation/tool_definition.yaml` | Alter one tool's input/output behavior. Verify expected changed result, invalid-input refusal, relevant regression cases and implementation digest observed by runtime. |
| `tasks/investigation/prompt.yaml` | Alter a named agent behavior on fixed scenarios. Verify requested behavior, evidence grounding and preserved invariants across the frozen trial policy; reject prompt-only text checks as sufficient proof. |
| `tasks/investigation/suspect_profile.yaml` | Add a profile of the suspected user with cited historical activity. Agent calls typed authorized updates; real UI shows result, refresh retains it and API reads it back. Test foreign-owner access, unsupported citations, invalid updates and stale revisions. |

The UI task spans backend, tool, persistence, events and frontend as one vertical capability.
No fake UI success message or synthetic screenshot can satisfy live agent interaction.
Use synthetic fixtures for quick development and deterministic refusal cases. Separately
execute bounded real model/data and deployed journeys when that acceptance class is required.
Do not substitute a fixture lifecycle for the real production startup/shutdown path.

Deploy the exact accepted artifact to an authorized target and operate Investigation as a
user: invoke the changed workflow, observe feedback, read stored results, reload, and inspect
auth/refusal behavior. Capture desktop/mobile evidence, browser errors, deployment digest,
and rollback verification. Protect actual telemetry and personal data in private artifacts.

## Fresh Overseer Test

**OF-15 Fresh-agent adoption.** Launch a separate session using overseer instructions through
a supported executor. Record actual role/model/executor identity. If the client cannot launch
that role, report the limitation; do not relabel a different worker as an overseer.

Give it the objective, repository/framework access, installed discovery, task inputs,
domain collaborators and preauthorized operating scope. Do not supply author chat history
or a prepared candidate solution. Fix model/settings and record preexisting memory. The evaluator owns a
held-out task variant; detailed expected outcomes must not leak through launch context.

It must discover the skill, preflight, establish baseline effort, checkpoint, iterate, evaluate,
deploy, compare, report and settle resources using the documented framework. Within scope it
may create needed infrastructure. Missing authority remains an honest blocked result.

SME clarification, corrections and review are expected, including newly discovered questions.
Record how the input changed decisions and prevent held-out answer leakage. Framework support
is usability feedback, not an automatic failure. Verify at least one SME correction is traced
to a versioned task or candidate and checked in the resulting workflow.

The test includes a controlled bad candidate or deployment fault in an isolated target.
Prove detection, preserved failure metrics, known-good restore, state read-back and continued
operation. The fault must be reversible and cannot threaten shared production resources.

Score three independent outcomes:

- Procedure adoption: discovery and correct lifecycle through documented interfaces; support needs visible.
- Measurement integrity: required telemetry, failed attempts, immutable pins and reproducible report.
- Optimization outcome: policy-defined measurable improvement on held-out acceptance.

An honest no-improvement result can pass the first two but not the complete improvement
objective. A procedure defect triggers a versioned framework/skill repair and a new fresh-session trial;
do not erase the failed adoption attempt. Repeat according to the frozen trial policy.

## Non-Investigation Portability

**OF-16 Domain transfer.** Use a second, unrelated discrete coding task, such as changing a
batch export format with parser validation. Supply its task pack, fixtures and registered
adapter/checks only. Core runner, metrics, storage, procedure and dashboard must remain
unchanged. Domain facts belong in the adapter. If core changes are necessary, version them
and repeat portability acceptance; do not claim the earlier artifact already generalized.

Use this same portability case to test brief-to-first-useful-workflow: supply a brief,
accessible imperfect data and representative SME examples, not a finished task pack or
solution. The agent prepares the pack, obtains policy-required domain confirmation, freezes
acceptance, then builds and verifies one useful workflow through the existing runner. Record
intake/setup effort and time to domain-confirmed executable acceptance; production readiness
is separate. No extra orchestration path or additional domain portal is required.

## Framework Verification

Match checks to consequences: read-only tasks require evidence validation; consequential
actions additionally require appropriate simulation/replay, action authorization and recovery
or explicit limits on reversibility. Use deterministic checks for hard constraints; model
judges require calibrated rubrics and cannot alone certify safety. Cloud acceptance applies
when deployment is required; Investigation's existing deployed acceptance remains required.

Use golden event sequences to prove metric arithmetic, denominators, concurrency handling,
partial telemetry and failed-trial visibility. Exercise schema errors, wrong-owner reads,
unauthorized writes, expired scope, evaluator tampering, duplicate requests, cancellation,
crash reconciliation, ambiguous saves and conflicting promotion. Deliberately failing checks
must fail; a test suite whose refusal paths were never exercised is incomplete evidence.

Guard reuse of optimizer mechanics: a probe and published candidate must resolve identical
configuration defaults; changed implementation pins must refuse continuation; an unmeasured
split must remain unavailable, never inherit another split's score. Procedure completion and
successful candidate admission do not establish measured improvement or operational usefulness.

Dashboard acceptance operates real start/status/cancel/report controls, restores only under
authorized policy, reconnects without losing events, and reads persisted results after restart.
Submit SME feedback through the real control, reload it, inspect the agent's disposition and
follow the applied change to its check result. Verify wrong-owner access refuses and repeated
submission is idempotent. Missing required domain review must remain visible, not auto-approved.
Verify optimization refuses without a measured baseline; a successful development probe
cannot bypass formal acceptance. Recorded-case inspection must expose capture limitations
and retain failures without rerunning inference or revealing protected held-out answers.
Verify keyboard use, accessible names, desktop/mobile layout and error/empty/loading states.
HTML/CSV/JSON exports must agree with the service's result and remain useful without a live
dashboard. Artifact access obeys the same ownership rules as run access.

## Requirement Traceability

| Requirement | Owning specification | Acceptance evidence |
| --- | --- | --- |
| OF-01 | [Procedure](PROCEDURE.md) | Fresh-agent adoption plus unrelated-domain task |
| OF-02 | [Procedure](PROCEDURE.md) | Full run without manual metric entry or phase commands |
| OF-03 | [Contracts](CONTRACTS.md) | Versioned record round trips and invalid input refusal |
| OF-04 | [Contracts](CONTRACTS.md) | Golden events, executor trace reconciliation and explicit gaps |
| OF-05 | [Contracts](CONTRACTS.md) | Crash/save recovery and owner-checked immutable read-back |
| OF-06 | [Contracts](CONTRACTS.md) | Evaluator/telemetry tampering denied under worker permissions |
| OF-07 | [Measurement](MEASUREMENT.md) | Frozen decision reproduced from retained raw evidence |
| OF-08 | [Measurement](MEASUREMENT.md) | Paired repeated trials with all outcomes and pins reported |
| OF-09 | [Architecture](ARCHITECTURE.md) | Shared service behavior and forbidden dependency checks |
| OF-10 | [Architecture](ARCHITECTURE.md) | Browser acceptance and export/API parity |
| OF-11 | [Architecture](ARCHITECTURE.md) | Current versus capability-oriented task comparison |
| OF-12 | [Authority](RECOVERY_AND_AUTHORITY.md) | Allowed cloud operation plus scoped/expired refusal |
| OF-13 | [Recovery](RECOVERY_AND_AUTHORITY.md) | Exact-version restore with state and auth checks |
| OF-14 | [Investigation tasks](#investigation-task-pack) | All four local and required deployed journeys |
| OF-15 | [Fresh overseer](#fresh-overseer-test) | Documented discovery, SME input traceability, improvement and recovery receipts |
| OF-16 | [Domain transfer](#non-investigation-portability) | Brief-to-useful-workflow in a second domain without core modifications |

## Incremental Delivery Gates

| Gate | Independently verifiable increment | Status |
| --- | --- | --- |
| G0 | Linked specs, explicit unknowns, artifact map and complete requirement coverage | Pass: specification delivered; runtime acceptance not applicable |
| G1 | Instrumentation feasibility: real supported coding executor, reliable observable events, isolated evaluator and one passing/failing candidate | Partial: [real config-only native execution](../reports/native-service-success-20260919.json); independent OS evaluator and complete telemetry missing |
| G2 | One complete local tool-availability run, durable metrics, report and minimal working dashboard | Pass, local supported scope: [native run](../reports/native-service-success-20260919.json), [dashboard and export parity](../reports/dashboard-integration-20260919.json), [2-test smoke rerun](../reports/dashboard-integration-smoke-20260919-rerun.json) |
| G3 | All four Investigation tasks, state/auth refusals and measured baseline effort | Partial: actual tool/definition checks, [narrow live prompt](../reports/investigation-prompt-live-final.json), [offline-native profile UI/refusals](../reports/investigation-profile-local.json); integrated all-four campaign and baseline change effort missing |
| G4 | One architectural hypothesis compared fairly with current structure, construction cost reported | Pending: no fair repeated A/B comparison or measured construction cost |
| G5 | Authorized live deployment, real user journey, exact-artifact rollback and reconciled resources | Blocked: [cloud scope already authorized](../reports/cloud-investigation-20260919.json); durable profiles/agent filesystem and deployed auth proof unresolved; no production deployment/rollback |
| G6 | Installed skill and fresh overseer use the process with SME collaboration, demonstrate improvement and recover | Partial: [supported installed-skill exact-overseer adoption passed](../reports/handoff-overseer-success.json) after credential fix; no independent SME result review, measured improvement or application recovery |
| G7 | Unrelated-domain brief-to-useful-workflow proves portable procedure, domain confirmation and unchanged core | Partial: [registered config-only third-domain tests](../tests/test_registry.py); not SME-confirmed brief-to-useful-workflow |

G1 must expose telemetry/client limitations before building a large dashboard. G2 is a thin
vertical path, not permission to implement every speculative abstraction. Required checks
travel with each increment. Cloud gates depend on actual scoped authority, not this document.

## Completion Record

Final handover links spec/framework/skill versions, comparison policy, all trial receipts,
deployment/restore receipts, dashboard URL, portable exports, resource inventory, cleanup
status and remaining limitations. Every required gate has observed evidence or a named blocker.
No portfolio completion claim rests on an active worker, unverified deployment, hidden failed
trial, missing primary telemetry or an untested recovery path.