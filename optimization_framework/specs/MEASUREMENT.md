# Measurement And Experimental Design

## Objective And Decision

**OF-07 Measured improvement.** Select one primary objective per experiment. Use two layers:
outcome and constraints (did requested behavior improve safely?), and delivery effort (what
did achieving it take?). Investigation's modularity benchmark keeps time to verified acceptance
as primary, with application quality/security as constraints. An operational task may instead
optimize diagnosis quality. Business-improvement claims require an observed domain metric.
Ease uses observable effort proxies; do not optimize lines or calls in isolation. Add secondary
metrics only when they could change the decision; no universal business scorecard is required.

Each experiment MUST freeze its primary metric, acceptable quality bounds, minimum effect,
trial count, timeout, aggregation and comparison rule before candidate evaluation. Missing
policy blocks a comparative improvement claim. No arbitrary default gain is claimed here.

Report a metric vector, not a universal weighted score. A faster but unreliable system cannot
win by excluding its failures. A result may be inconclusive. Where timing is the objective,
report success rate alongside successful-run timing and time-to-event censoring at the limit;
timeouts never masquerade as completed tasks or disappear from the denominator.

## Metric Dictionary

| Metric | Definition and unit |
| --- | --- |
| Time to verified acceptance | Seconds from measured task release to completion of its last required passing check on the accepted digest; unsuccessful trials are censored at stop |
| Time to first useful workflow | For brief-to-workflow tasks, seconds from brief release through required domain confirmation and executable acceptance; includes clarification, data connection and setup, not a production-readiness claim |
| Total run elapsed | Seconds from run admission through settled reporting/cleanup, whether successful or not |
| Phase time | Setup, discovery, editing, validation, deployment, recovery and blocked intervals; record overlap and show elapsed interval unions |
| First-pass success | First formal submission passes every required check; rate denominator is all admitted valid-preflight trials, including later cancellation/timeouts |
| Acceptance rate | Trials reaching required acceptance divided by all admitted valid-preflight trials; separately show preflight-blocked counts and causes |
| Repair cycles | Number of revised formal submissions following a failed formal submission; exploratory test calls reported separately |
| Coding actions | Observable read, search, edit, command, browser, delegation and collaboration events, grouped by type and actor |
| Discrete calls | Separately counted coding-tool dispatches, child command invocations, coding-model requests, application-model requests, application-tool calls and service operations |
| Change footprint | Final files and ownership boundaries touched; lines added/deleted split into source, tests, configuration, prompts, docs, generated output and dependency locks |
| Rework | Sum of consecutive captured edit deltas, including reverted edits, compared with final baseline-to-candidate diff; capture granularity reported |
| Domain collaboration | SME examples, corrections and review decisions, their provenance and resulting task/candidate changes; report active/waiting time for planning, not as a penalty |
| Framework support | Documentation questions, runner repairs and manual workarounds, recorded as usability evidence rather than automatic disqualification |
| Cost | Observed provider usage/currency and cloud charges where available; estimates and delayed/incomplete billing separately labeled |
| Recovery | Restore attempts, success/refusal, elapsed time, lost or incompatible state, and verification results |
| Process completion | Required lifecycle settles with valid telemetry, acceptance and collaboration evidence, regardless of whether useful human input was needed |

No zero-assistance target applies. Judge collaboration by how domain input informs decisions
and verified outcomes, not by minimizing questions. Keep measurement and checks automated;
human judgment is attributed evidence, not a substitute for missing executable acceptance.

An observed call counts at dispatch even if it fails. A batch call and its child operations
are separate hierarchy levels, never combined into a misleading single total. Missing
model internals are `unobserved`, not zero. Large shell commands are not assumed one action's
worth of work: record child invocations when supported and disclose unsupported internals.

Preserve all formal submissions. An unchanged recheck is a test retry, not a repair; record
both and the reason. Never retry a flaky acceptance check until green without retaining
failures and applying the predeclared flake policy. A changed evaluator starts a new series.

## Fair Comparison

**OF-08 Comparable trials.** Architecture A and B receive equivalent tasks, fixtures,
acceptance, model/settings, tool access, resource limits and environment. Pin all observable
versions; provider nondeterminism and unavailable seeds remain limitations.

- Use fresh coding sessions and isolated state per trial. No candidate solution in baseline
  context. Record cache warmth, setup state and resource contention; separate cold/warm runs.
- Pair task variants across architectures and randomize/counterbalance order with recorded
  schedule. Fix sample count in advance; show raw points, medians/tails where supported,
  dispersion and sample counts. Do not claim significance from a single success.
- Freeze evaluators and collect a working-system baseline before architecture changes.
  Measure baseline task implementation effort, not merely existing app startup latency.
- Keep development tasks distinct from held-out tasks. Prompt quality includes repeated
  behavioral checks, not string matching alone or an uncalibrated model-judge score.
- Retain failures, cancellations and environmental interruptions with causes. Any exclusion
  rule is predeclared and reported; publish all enrolled trial outcomes beside filtered views.
- If parallelism differs, treat it as an experimental variable and report total child work,
  elapsed time and resource use. Never hide extra workers behind a shorter parent timeline.
- Architecture, harness, skill and adapter construction costs are separate measured work.
  Report adoption/setup overhead and amortization; do not attribute it to free infrastructure.

## Promotion Rule

Promotion requires required checks on the exact candidate artifact, quality bounds, valid
telemetry for primary metrics, policy-defined improvement and an available verified recovery
target. Measurement success alone is not permission to deploy. Inconclusive evidence leaves
the known-good version selected. Improvements to the framework require its own regression
checks before use; pin the measurement version for a comparison or remeasure both arms.

Dashboards and reports use the same metric implementation and evidence IDs. Exports include
units, denominators, versions, coverage, exclusions and uncertainty. No chart invents values
to fill gaps. See [acceptance](ACCEPTANCE.md) for golden-event metric checks.