# Adopting the Skillpack

Adoption is deliberate work in a target application, not a side effect of extraction. This pack
introduces no import, route, dependency install, storage migration or cloud configuration.
Extracting it changes nothing in the extracting repository.

## Host Decisions

| Input | Required host decision |
| --- | --- |
| Objective and cases | What is scored, source/evidence time, labels, frozen splits and questions the data cannot answer |
| Authorization | Who may create/read/change each experiment; authenticate separately from deciding ownership |
| Model | Callable predictor/request builder, credential acquisition at the edge, fixed deployment and resource budget |
| Dataset | Bounded evidence reads and separate evaluator-only labels; preparation provenance and data license |
| Detector | Window-bound queries and processing callbacks; no silent successful empty result on failure |
| Knowledge | Optional authorized advisory lookup and explicit on/off comparison; no direct candidate network access |
| Persistence | Owner-partitioned ledger, immutable files, safe restart/retry policy and durable evidence readback |
| Frontend | API base/request transport, component alias resolution, global shell sizing/styles and domain labels |
| CLI | Installed standalone Copilot binary, private workspace outside the indexed repo, approved helper-only operations |

Import the public `agent_optimization` package from the extracted runtime source. Create
`OptimizationProfile` and `TerminalTasks` using the copied dataclass contracts; build
`OptimizationService` with host-owned `authorize` and `identify` functions and optional knowledge
and capability callbacks. Every domain fact — labels, prompts, task text, budgets, baseline and
request builder — is host-supplied. No profile for any particular dataset ships with this pack.

The dataset protocol includes `describe`, `cases`, `full_cases`, `stress_cases`, `query`,
`profiles`, `run_tool` and `profile_digest`. Joint execution adds `detector_query` and
`detector_process`. The included Python sandbox reads an isolated case SQLite file whose allowed
tables are `evidence` and `training_profile`; labels stay outside that mount. Arbitrary new tables
or domain schemas require a deliberate host/worker contract change and matching negative tests.

## HTTP And UI

The public frontend uses `createOptimizationApi(requestJson, base)` and `OptimizationApiProvider`.
The host's `requestJson` owns credentials, JSON headers, error handling and session behavior.
Changing a URL is not an authorization implementation.

The host owns its HTTP surface. Map one operation per service method: snapshot, experiment
creation/read/cancel, capabilities, detector/probe operations, full-stage measurement, replay
exemplars and terminal lifecycle. Reproduce ownership refusals as well as positive paths. A
local-preview identity is never deployed authentication.

For React, preserve the public frontend barrel import and point `@components/` at the extracted
`runtime/` directory in TypeScript and the bundler (`frontend-check.tsconfig.json` and
`frontend-check.mjs` show the exact mapping). Supply an active-view flag so polling stops when the
workspace is hidden. The optimizer reuses `rex-` explorer classes and a source-code renderer;
supply those styles from your own host or restyle the classes consciously. Give the workspace a
bounded flex/grid height and verify empty/error/loading states, scrolling, code wrapping and
mobile replays.

The library build recipe proves source and dependency closure, not finished host layout.

## Fixed Optimization Sequence

1. Read source capabilities and a completed parent's development failures. Distinguish registered,
   configured, reachable, authorized, used and helpful; these are different facts.
2. Record question, data, view, selected tool, interpretation and limits. Explicitly record
   `code_changes`, `agent_changes`, `held_fixed` and acceptance/disconfirmation checks.
3. Use small `./opt draft` patches. Match actual source/output to the stated plan; names and
   distinct AST hashes alone do not prove semantic diversity.
4. Probe the exact proposed detector/tools/prompt on two to four contrasting development cases.
   Passing admission means no execution/response errors and varying detector summaries, not
   correct predictions on every probe.
5. Publish by receipt ID. Changing even a prompt word requires a new receipt and breaks a
   claimed exact-parent control unless explicitly included in the experiment.
6. Train on the full frozen development cohort, then evaluate on the frozen evaluation cohort.
   Keep all failures and regressions. Repeated evaluation is adaptive feedback, not an untouched test.
7. Continue until the selected protocol's counts and creative coverage pass. `joint-12` is
   baseline generation zero plus twelve successors: 13 versions, not twelve total.
8. Finish through the service gate, audit saved artifacts, then operate the integrated UI.
   A task-complete message or submitted job is not a finished campaign.

The fixed evaluator currently schedules detector -> all pinned tools -> optional knowledge ->
one model response. It is not an adaptive model-selected tool loop or a remediation engine.
Keep that limitation explicit when choosing which agent strategies can actually be tested.

## Safety And Recovery

- Keep native CLI control same-origin/loopback where the copied transport requires it. A deployed
  adapter needs a reviewed caller-authentication design, not disabled checks.
- The host supplies provider credentials; candidate tool code receives neither credentials,
  host home, network, labels nor arbitrary subprocess access. Bubblewrap/libseccomp failures
  are blockers, never reasons to switch to unisolated execution.
- Keep model, scorer, case membership, worker limits and creative skill identity fixed. Frozen
  live experiments cannot be silently resumed with altered measurement code.
- A restart retains the interrupted attempt and starts an explicitly authorized retry under
  a new run ID. Refresh parent feedback IDs, never append to the partial JSONL.
- The stage coordinator watches saved state; the helper reuses existing stages rather than
  remeasuring them. Do not select a repeat merely because it scored better.
- Keep scratch restores, CLI homes and generated dependency/cache trees outside broad indexing.
  Accepted ledgers and baseline hashes are not disposable caches.

## Acceptance In a New Host

Use the copied unit/negative tests first, then the actual host service and authorized browser
journey. Verify all three levers, controlled comparisons, exact probe publication, stage ordering,
case counts, error accounting, source lineage and best/worst replay authenticity. Confirm a wrong
owner cannot read or mutate another experiment. Check desktop/mobile geometry, not just DOM
presence. Run new model work only with the user's authority and provider prerequisites.

No historical outcome ledger, dataset or model transcript ships with this pack. The synthetic
`example/` records show record shape only and must never be used as a performance reference.
