# Custom Optimizer Runbook

Run commands from the Custom Optimizer root through `./deploy/deploy.sh`.
Linux, Python 3.12, uv 0.9.30, Node 20+, npm and the frontend's Playwright Chromium are required.
No cloud lifecycle, access grant, deployment or ingestion command is exposed.

## Startup

```bash
./deploy/deploy.sh setup
./deploy/deploy.sh local --source-root /home/hanchoong/perth_cyber --check
./deploy/deploy.sh local --source-root /home/hanchoong/perth_cyber
```

`setup` resolves only this app's locked Python/npm environment. `--check` validates inputs and
prints configured key names without contacting Azure. `local` launches API 9012 and frontend
5180 on loopback, selecting a free port when occupied. Ctrl-C closes both processes, the model
client, experiment service and owned terminals. No model call happens merely from startup.

Model inference defaults denied, regardless of inherited shell values. A separately authorized
`local --allow-model-calls` grants bounded `llm_interface` execution for that process only.
Native runs carry owner-bound session/run receipts; no provider continuation or automatic
replay is used. Read-only browser acceptance never passes this flag.

`--source-root` reads only allowlisted model/Search coordinates from the existing source's
configuration, uses its prepared GUIDE directory read-only, and uses its Bubblewrap executable
when present. It never executes the environment file, imports source code, copies credentials,
or redirects output into that source. `--env-file` accepts equivalent explicit settings;
see [.env.example](../.env.example). ADX coordinates are ignored.

Missing GUIDE files or an invalid endpoint fail preflight. Missing sandbox prevents generated
Python execution; there is no unisolated fallback. Failed model/knowledge access remains an
error, never fixture output. Model calls require the operator's existing authorized identity.

## Verification

```bash
CYBEREYE_PYTHON_SANDBOX=/home/hanchoong/perth_cyber/app/cybereye/.local/tools/bubblewrap/usr/bin/bwrap \
  ./deploy/deploy.sh test
./deploy/deploy.sh browser-verify
```

`test` runs moved service/component tests, real sandbox refusal checks when configured,
standalone-host and state-transfer tests, frontend unit tests and build. An absent sandbox is
reported as skipped, not passed. Browser verification reads existing histories, changes only
view controls, checks native CLI availability without starting it, and checks Investigation's
remaining views. Override `OPTIMIZER_URL` and `INVESTIGATION_URL` if ports differ; both must be
loopback origins. Screenshots/reports go under ignored `artifacts/browser/separation/`.

Creating an experiment or running the coding agent invokes the configured model and writes
app-owned records. Those paid operations are not hidden inside `test` or `browser-verify`.
No new campaign was run to establish the separation; offline execution and saved read-back
do not claim post-extraction model performance or historical-campaign continuation parity.

## Existing State

Writable root is fixed to `app/cybereye/.local/` here, not a source-supplied override.
GUIDE inputs remain external; experiment/context files and private terminal workspaces live
under this app. Credentials/private workspaces and result payloads stay ignored.

One-time handoff, already completed for this checkout:

```bash
./deploy/deploy.sh move-state --from-template ../investigation_app --source-stopped
```

Stop the source application before acknowledging `--source-stopped`. Transfer refuses running
evaluations, existing destinations, symlinked source roots and an existing receipt. It moves
only `optimization` and `copilot-workspaces`, checks content hashes, and leaves Investigation's
authored agents untouched. Re-running is deliberately refused; no merge or overwrite occurs.
The ignored receipt is `artifacts/migration/state-move.json`.

Retired source files are retained under ignored `artifacts/migration/retired/` for rollback,
outside imports/build/test discovery. Records were not altered. Historical tool and knowledge
pins remain enforced; start a new experiment for changed standalone-host context, and a fresh
native terminal instead of reconnecting to a terminated pre-move session.