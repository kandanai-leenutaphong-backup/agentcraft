# Local Framework Runbook

Use `deploy/deploy.sh` as the single operator entry point. All paths below are relative to
the framework root unless absolute. Script resolves its own root regardless of caller cwd;
relative `--root`, `--output`, `--receipt` and `--target` values belong to caller cwd.
Use absolute paths for repeatable operations. Never put secrets in arguments, feedback or reports.

## Prerequisites And Sequence

Linux/Bash, Python 3.12+, Node.js/npm. Python runtime uses standard library only; tests need
pytest installed for `python3` (`python3 -m pip install pytest` in an approved environment).
No virtual environment is created or activated. Frontend setup needs npm registry access and
executes dependency installation scripts; use trusted source/lockfile and approved network access.

```bash
./deploy/deploy.sh setup
./deploy/deploy.sh test
./deploy/deploy.sh verify --receipt /tmp/optimization-verification.json
./deploy/deploy.sh describe --root /tmp/optimization-demo
./deploy/deploy.sh run --root /tmp/optimization-demo \
  --task csv-export-transformation --idempotency-key csv-demo-v1
```

Expected, in order: Vite build completes; pytest passes; verification returns `complete`;
describe lists both tasks and `allow_model_calls: false`; run returns `completed`,
`acceptance: passed`, `decision: inconclusive`. Keep returned `id` as `RUN_ID`.
Same task/executor/idempotency key reuses its recorded run; changed request under that key refuses.
Use a new key for a genuinely new run, never to hide failed attempts.

| Command | Scope and failure response |
| --- | --- |
| `setup` | `npm install --package-lock=false --no-audit --no-fund`, then `npm run build`; source package lock untouched. Fix missing Node/npm, registry access or reported build errors; do not weaken checks. |
| `test` | Core, executor, native-service, task registry, credential and packaging tests. No live model/cloud calls. Investigation app tests and browser tests are separate. |
| `verify [--receipt PATH]` | Shell syntax, no-grant describe, both deterministic tasks, failure/repair history, restart, idempotency, three report formats/read-back and refusal checks. Temporary root is removed; optional payload-free receipt retained. |
| `local --port N --root PATH` | Foreground loopback service plus built UI, default port 8765. Occupied port: choose another. Missing UI: run setup. Busy storage: stop its owner or choose another root. |
| `report --root PATH --run ID --format json\|csv\|html --output PATH` | Export persisted facts, exclusive new file, read-back/hash receipt. Existing path refuses; choose a new path. No model grant accepted. |
| `native-run --allow-model-calls ...` | Explicitly authorized config-only native trial. No flag means blocked before any model call. |
| `install-skill --client vscode --target PROJECT` | Portable source/runtime/reference export and native registration. Unsupported client, symlink or changed existing file refuses. |
| `cloud`, `deploy`, `teardown` | Exit 2, `cloud_not_implemented`; no cloud or local data deletion. |

Wrapper/CLI usage or refusal exits 2; CLI failed/blocked/timed-out run exits 1; interrupted CLI
exits 130. Preserve JSON evidence even on nonzero exit. `verify` emits a receipt only on success;
no receipt is not success. Setup/test propagate failing command status.

## Reports And SME Feedback

After setting `RUN_ID` to the actual returned run ID:

```bash
./deploy/deploy.sh status --root /tmp/optimization-demo --run "$RUN_ID"
./deploy/deploy.sh feedback --root /tmp/optimization-demo --run "$RUN_ID" \
  --text 'Preserve embedded commas and newlines in exported names.' \
  --idempotency-key csv-review-v1
```

Feedback returns the updated run. Set `FEEDBACK_ID` from its `feedback` entry and
`CANDIDATE_ID` from the passing candidate actually addressing the observation. Record only
an evidence-backed disposition; `apply` does not itself edit a task or launch a new run:

```bash
./deploy/deploy.sh respond --root /tmp/optimization-demo --run "$RUN_ID" \
  --feedback-id "$FEEDBACK_ID" --disposition apply --candidate-id "$CANDIDATE_ID" \
  --reason 'Linked passing candidate has csv-roundtrip acceptance evidence.' \
  --idempotency-key csv-response-v1
./deploy/deploy.sh report --root /tmp/optimization-demo --run "$RUN_ID" \
  --format json --output /tmp/csv-demo-reviewed.json
./deploy/deploy.sh report --root /tmp/optimization-demo --run "$RUN_ID" \
  --format html --output /tmp/csv-demo-reviewed.html
```

Other dispositions: `clarify`, `defer`, `decline`, each requiring a reason. `apply` requires
a passing candidate; inspect its checks. Feedback is attributed to the fixed local operator,
not independently authenticated SMEs. Changed objectives/evaluators require versioned task work
and a new comparison series; current service has no task-authoring endpoint.

JSON preserves the run; CSV includes structured records; HTML embeds escaped full evidence.
All retain failures and limitations. `model_requests: null` means unobserved. Actual timings
vary. `synthetic-integration` is not `local-live` or `deployed-live`; none proves improvement
without valid comparison policy and measured baseline effort. Export never calls a model.

## Local UI And HTTP

```bash
./deploy/deploy.sh local --port 8765 --root /tmp/optimization-ui
```

Open `http://127.0.0.1:8765`. Stop with Ctrl-C; do not run a second CLI against that root.
Use a second terminal for the API; POST requires exact Origin matching Host:

```bash
curl --fail-with-body http://127.0.0.1:8765/api/health
curl --fail-with-body http://127.0.0.1:8765/api/tasks
curl --fail-with-body -H 'Origin: http://127.0.0.1:8765' \
  -H 'Content-Type: application/json' \
  --data '{"task_id":"csv-export-transformation","executor":"deterministic","idempotency_key":"http-csv-v1"}' \
  http://127.0.0.1:8765/api/runs
```

POST may return `running`, not completion. Poll `GET /api/runs/{id}` until terminal and
inspect acceptance. `GET /api/runs` lists recorded runs; `GET /api/runs/{id}/report?format=json`
downloads evidence without new computation. Unknown routes refuse. All responses use
`Cache-Control: no-store, private`.

POST bodies require exactly these fields (including explicit `null` for optional candidate):

| Route | JSON body |
| --- | --- |
| `/api/runs/{id}/cancel` | `{}` |
| `/api/runs/{id}/restore` | `candidate_id`, `idempotency_key` |
| `/api/runs/{id}/feedback` | `text`, `candidate_id` (string or null), `idempotency_key` |
| `/api/runs/{id}/feedback/{feedback_id}/respond` | `disposition`, `reason`, `candidate_id` (string or null), `idempotency_key` |

Every POST uses the same Origin/Content-Type headers as start. Read back feedback and
restorations via GET. Missing/wrong Origin, nonloopback bind/peer and supplied identity headers
refuse. Do not send `Authorization` or `X-Owner` headers. This trusted same-user local boundary
is not a credentialed multi-user service. Never tunnel, expose or proxy it as a cloud service.

CLI and HTTP use [OptimizationService](../src/optimization_framework/service.py).
Python callers supply an explicit owner and use its context manager; HTTP/CLI select the fixed
local operator. Direct service ownership checks are not nonlocal caller authentication.

## Native Trials: Separate Authorization

Not part of setup/test/verify. Requires explicitly approved model/data/cost scope, executable
`$HOME/.local/bin/copilot`, authentication supplied privately, and CLI support for
the currently fixed `gpt-6-astra` model and `max` effort. This wrapper cannot select another
model. Missing prerequisites refuse or produce a retained blocked/failed attempt.
Do not put credential values in configuration, commands or reports.

Native sessions use an isolated home. Supply an existing credential through the caller's
environment, or explicitly pass `--github-cli-auth` to borrow the current `gh` login in memory.
The latter invokes `gh auth token --hostname github.com` with captured output; no token is
printed or written to framework state. It requires the separate model-call grant and refuses
when the existing login is unavailable. Never paste a token into the terminal command.

```bash
./deploy/deploy.sh native-run --allow-model-calls --github-cli-auth --root /tmp/optimization-native \
  --task csv-export-transformation --native-max-attempts 1 \
  --native-timeout-seconds 60 --idempotency-key authorized-native-v1
```

The default CLI registers two tasks; Python hosts may inject additional typed TaskAdapters.
Frozen source stays trusted; model authors bounded JSON
configuration, with all native tools denied. Limits: 1-2 attempts, positive timeout <=120 seconds
per attempt. No arbitrary code execution workflow, independent OS sandbox or hidden-request
accounting is claimed. Provider-side cancellation/settlement and effective effort remain limited.
Private native state under `/tmp` is retained for separately authorized operator cleanup.
`local --allow-model-calls` grants native availability for that service process only when explicitly
requested; ordinary `local` does not. Stop the process to end that process grant.

## Recovery And Cleanup

`cancel --root PATH --run ID` records cancellation; wait for terminal status. A serving process
owns its live worker, so cancel through HTTP when it holds the root. CLI cancellation after an
interruption is not remote process control. Reopening interrupted `running` records marks them
blocked and retains evidence; it does not resume or replay model work.

```bash
./deploy/deploy.sh restore --root /tmp/optimization-demo --run "$RUN_ID" \
  --candidate-id "$KNOWN_GOOD_ID" --idempotency-key restore-v1
./deploy/deploy.sh status --root /tmp/optimization-demo --run "$RUN_ID"
```

Choose `KNOWN_GOOD_ID` from the run, not a guessed ID. Restore requires terminal state and
passing known-good candidate, verifies pins, re-evaluates trusted source/config and reads back
the digest. It adds history; it does not delete failed evidence or restore an external app.
No automated data teardown: preserve private roots/reports until retention owner approves deletion.
Verification owns only its temporary directory and removes it after checking. No server is
started by setup, test packaging checks, verify, report or installation (core tests may bind
short-lived loopback fixtures and close them).

## Portable Skill And Remaining Gates

```bash
./deploy/deploy.sh install-skill --client vscode --target /path/to/target-project
```

Open that project in a VS Code client supporting `.github/skills` discovery, then invoke
`/optimization-experiment`. Exported entry points at its bundled primary skill. Its framework
entry supports setup/test/verify without the original checkout. `bundle.json` inventories hashes;
repeat identical install safely, use a fresh target for changed contents. Installation copies
neither `node_modules`/build artifacts nor reports, credentials, repository agent instructions,
Investigation adapters/app or user state. Spec references to other repository owners are
historical design context, not bundled implementation dependencies or portable capabilities.

An install/read-back test proves layout and local execution, not fresh-client discovery or
fresh-overseer adoption. Held-out evaluation, comparative improvement and required
Investigation/cloud journeys remain separately tracked under [acceptance](../specs/ACCEPTANCE.md).
`preflight --experiment DOCUMENT` and `run --experiment DOCUMENT` validate registered config-only
task documents; see [API contract](../API_CONTRACT.json). Python hosts inject a `TaskRegistry`
into `OptimizationService`; documents cannot import code or grant model calls. `recover`
remains unavailable. Cloud work needs nonlocal authentication first; no cloud command
here is a substitute. Existing spec files are deliberately not rewritten as completed gates.