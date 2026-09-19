---
name: optimization-experiment
description: "Use for measured iterative improvement in a supported domain: local deterministic or explicitly authorized Copilot config-only trials, SME feedback, persisted comparisons and report export. Unsupported domains block pending an adapter; no implicit model or cloud permission."
---

# Optimization Experiment

Use the [framework runbook](../../deploy/README.md) and [current support](../../README.md).
Resolve framework root as two directories above this primary skill, independent of caller cwd.
Installed bundle preserves that layout. Its `deploy/deploy.sh` is the operator entry point;
do not infer commands from proposed signatures in specifications.

## Intake And Capability Check

Collect one objective, authorized target/writable paths, task/version, representative SME
examples, required checks, data scope, executor/model permission, private storage root,
attempt/time/cost bounds, retention owner and comparison policy. Missing required inputs:
name the field, responsible owner and blocked action. Discovery grants no execution authority.

Read [procedure](../../specs/PROCEDURE.md), [measurement](../../specs/MEASUREMENT.md) and
[authority/recovery](../../specs/RECOVERY_AND_AUTHORITY.md). Treat normative requirements as
requirements, not observations. Current CLI supports only `agent-tool-availability` and
`csv-export-transformation`, both synthetic tasks, with deterministic or Copilot config-only
authoring. Arbitrary repository/domain changes are not currently registered capabilities.

Preflight includes operator checks: verify authorized scope, Python
3.12+/Node/npm, writable private external root, exclusive root ownership, required test
dependency and acceptable local-only boundary. Run `deploy/deploy.sh describe --root PATH`;
without explicit model grant it advertises deterministic only. Do not call a model to probe
credentials unless separately authorized. Setup uses network access for npm dependencies.
For a registered task document, `preflight --experiment DOCUMENT` performs strict validation;
`run --experiment DOCUMENT` executes it. Neither imports arbitrary code nor grants authority.

## One Supported Experiment

From the resolved framework root, with approved dependency installation:

```bash
./deploy/deploy.sh setup
./deploy/deploy.sh test
./deploy/deploy.sh verify --receipt /tmp/optimization-check.json
./deploy/deploy.sh describe --root /tmp/optimization-example
./deploy/deploy.sh run --root /tmp/optimization-example \
  --task csv-export-transformation --idempotency-key example-csv-v1
```

Domain-neutral example: uppercase names in a batch CSV export while preserving quoting,
commas and embedded newlines. SME confirms meaning and reviews recorded cases. One `run`
records baseline, bad submission, repair and acceptance automatically; no manual metric entry.
Its baseline is a synthetic working fixture, not measured human/coding-agent change effort.
Do not describe this as unrestricted brief-to-application generation or independent domain transfer.

Use the returned run ID, then:

```bash
./deploy/deploy.sh status --root /tmp/optimization-example --run "$RUN_ID"
./deploy/deploy.sh report --root /tmp/optimization-example --run "$RUN_ID" \
  --format json --output /tmp/optimization-example-report.json
```

Use new report/receipt paths; existing paths refuse. Reports do not rerun work. While a local
server owns a root, use its HTTP API rather than another CLI process. The runbook covers
`local --port`, Origin-protected POSTs, cancellation, SME `feedback`/`respond`, read-back
and known-good `restore`. Applied feedback must link a passing candidate and verified checks;
record clarifications/declines honestly. No feedback endpoint automatically changes objectives.

Native trials require a separate explicit grant and prerequisites from the runbook:
`native-run --allow-model-calls --github-cli-auth --task ID --root PATH --native-max-attempts 1`.
`--github-cli-auth` explicitly borrows the existing `gh` login in memory for the isolated native
session; omit it only when credential environment is already supplied. Never print/store tokens.
Default setup/test/verify/local never grant model calls. Never add that flag merely to make
a blocked experiment proceed. Native tools are denied; only bounded configuration is authored.

## Interpretation, Stops And Extension

- Read `status`, `acceptance`, `decision`, evidence class, failed submissions, telemetry coverage
  and limitations together. `completed`/`passed` never establishes improvement.
- Current decisions remain `inconclusive`; missing model requests are null/unobserved. No fair
  repeated-trial comparison, independent holdout or automatic comparative promotion is implemented.
- Stop at exhausted authority/budget, failed integrity, unknown side effects or missing prerequisite.
  Keep failures, blocked results and private recovery state; do not weaken acceptance or retry silently.
- Restore only recorded known-good synthetic snapshots. Application rollback, save recovery CLI,
  resumable computation and cloud teardown remain unavailable. Cloud reports blocked.
- For another domain, use [contracts](../../specs/CONTRACTS.md) and
  [architecture](../../specs/ARCHITECTURE.md) to propose a narrow task adapter with versioned
  fixtures, owning capability, trusted evaluator, positive/negative checks, authority and recovery.
  Hosts register a typed `TaskAdapter` through `TaskRegistry` without changing core; the default
  CLI includes two adapters. Implementation and registration require explicit writable scope;
  documents cannot name imports or shell commands. Config-only extensibility does not establish
  arbitrary application coding or operational portability.
- Follow [acceptance](../../specs/ACCEPTANCE.md) for remaining gates. Installed references and
  deterministic smoke tests do not prove fresh-overseer adoption, arbitrary-domain transfer,
  Investigation acceptance, measured improvement or deployed nonlocal authentication.

Return status, run/evidence IDs, exact commands/check results, SME dispositions, limitations,
retained artifacts/processes, cleanup and next missing input. Never publish credential values,
private native session files or held-out answers. No new notebook/report beyond necessary
experiment evidence; no spec gate changes based only on this local demonstration.