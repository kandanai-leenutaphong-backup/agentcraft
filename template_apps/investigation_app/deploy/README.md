# Local Migration Runbook

One entry point: `./deploy/deploy.sh`, run from this template root. Local development only;
no provisioning, release, ingress, grant, start/stop-cluster or teardown command is provided.
The source deployment remains the owner of existing Azure resources.

## Current Scope

Optimizer, GUIDE and native CLI moved to [Custom Optimizer](../../custom_optimizer/deploy/README.md).
Investigation's launcher accepts no optimizer/data/sandbox state settings. Its three workspaces
and five cloud datasource slots remain; authored Investigator versions still live here.
The shared local-process launcher changes no application authorization decision.

## Authorized End-To-End Checks

Cluster start belongs to the source deployment: from that checkout, run
`./deploy/deploy.sh data-start -e prod` only with explicit authorization to resume compute
charges. The command refuses transitional states and reads back `Running`. Starting ADX
grants no new data, model, role or deployment permission. User authorized this start and
the copied application's live end-to-end checks on 2026-09-15.

From the template, after ADX is running:

```bash
./deploy/deploy.sh verify --scan
./deploy/deploy.sh browser-verify investigation
./deploy/deploy.sh browser-verify editor-live
./deploy/deploy.sh browser-verify inventory
```

Run browser suites sequentially: the local principal and Investigator assignment are shared.
`investigation` operates scan, automatic diagnosis, evidence sequences, summary and chat.
`editor-live` additionally verifies saved instruction versions against the model and restores
the prior Investigator assignment. `inventory` reads the existing data stores. Optimization
commands now belong to the standalone optimizer. Live investigation suites invoke the model and incur usage;
they are not part of default offline `test` or default `browser-verify editor`.

Each suite writes to its own ignored `artifacts/browser/<suite>/` directory. A failed test
remains a failure; do not replace live evidence with fixtures or relax an assertion to pass.

## Prerequisites

- Linux, Python 3.12 at `/usr/bin/python3`, uv 0.9.30, Node 20+ and npm.
- Existing Azure CLI login with read access for optional cloud-backed features. Credentials
  stay in the operator's credential store, never copied into the template or a receipt.
- Either `--source-root /home/hanchoong/perth_cyber`, or `--env-file` naming non-secret
  coordinates following [the configuration example](../app/cybereye/.env.example).
- Chromium installed for the frontend's pinned Playwright version. If browser launch names a
  missing executable, install that browser through the owning frontend toolchain first.
- GUIDE and Bubblewrap are no longer Investigation prerequisites. No model run or source-state
  import happens on local startup.

## Sequence

```bash
./deploy/deploy.sh setup
./deploy/deploy.sh test
./deploy/deploy.sh local --source-root /home/hanchoong/perth_cyber --check
./deploy/deploy.sh local --source-root /home/hanchoong/perth_cyber
```

`setup` uses the template uv lock and frontend npm lock, independently of the library workspace
environment. `test` runs application/launcher tests, frontend unit tests and the production
build. Missing dependencies fail before launch; no install command changes the source project.
Preflight prints configured key names and data availability, not secrets, and makes no cloud call.
Launch prints actual frontend/API URLs. Defaults 5174/9011 avoid the source app; an occupied
port selects the next free one. Ctrl-C stops both child process groups and closes the ADX client.

In a second terminal, using the printed ports:

```bash
./deploy/deploy.sh verify
./deploy/deploy.sh browser-verify
# Only when the existing ADX cluster is running and reads are authorized:
./deploy/deploy.sh verify --scan
```

Override API with `verify --api http://127.0.0.1:<port>` and browser with
`CYBEREYE_URL=http://127.0.0.1:<port> ./deploy/deploy.sh browser-verify`.
Verifiers refuse non-loopback origins. `verify` checks actual identity/refusals and configuration;
optimizer/ GUIDE routes are absent; `--scan` performs
a read-only historical query and evidence read-back. Failed checks exit nonzero. No model is called.
Reports live under ignored `artifacts/verification/`; browser screenshots and receipts under
`artifacts/browser/agent-editor/`. These are local evidence, not distributable datasets.

The existing editor browser journey writes new test agents into this template's local state,
checks immutable versions and simulated save-error recovery, and restores the prior Investigator
assignment. It does not delete authored records or run optimization. Repeated runs create new
owned test records; they are not byte-identical/idempotent state mutations.

## Configuration And Safety

The launcher parses (never sources) the source project's committed production coordinates and
optional application environment file, copying only named connection settings. Other keys are
discarded. Credentialed service URLs refuse. Existing loopback authentication is reused in code;
the deployed `backend/main.py` gate is unchanged and has no bypass setting.

Agent versions stay under this template's ignored `app/cybereye/.local/agents/`, regardless of
source state-directory settings. Optimizer state moved to its standalone app. No source dependency directory or application code
is imported. The source project and shared deployment are never synchronization destinations.

## Historical ADX Check

2026-09-15: local ADX scan returned 502 with `transport_unavailable`; health returned
`200/degraded`. Independent Azure ARM read found `adxperthcyber01` in
`rg-perth-airport-cybersec`, subscription `67255afe-8670-4401-a1b8-df6ca63a3516`, tenant
`c79ab2bb-79cb-47f1-b4da-b6852fe45ff7`, state `Stopped`, provisioning `Succeeded`, public
network `Enabled`. No cluster start was attempted. This is not successful live ADX acceptance.

That observation predates the separately authorized cluster start. Use current resource read-back,
not this historical state, for operational decisions. Then rerun
`verify --scan` and compare source/template scan and evidence. Do not disable auth, load data,
grant access, restart shared infrastructure, or substitute fixture data to report a live pass.