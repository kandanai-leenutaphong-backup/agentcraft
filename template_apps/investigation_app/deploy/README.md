# Local Investigation Runbook

One entry point: [deploy.sh](deploy.sh), run as `./deploy/deploy.sh` from this template root.
Local development only;
no provisioning, release, ingress, grant, start/stop-cluster or teardown command is provided.
The source deployment remains the owner of existing Azure resources.

## Current Scope

Investigation's launcher accepts no optimizer/data/sandbox state settings. Its three workspaces
and five cloud datasource slots remain; authored Investigator versions still live here.
The shared local-process launcher changes no application authorization decision.

Model execution uses `llm_interface`, native sessions and OpenAI 3.13.x. Local launch always
defaults inference to denied, including when the invoking shell carries an old grant.
Only separately authorized `local --allow-model-calls` enables bounded inference. It is not
part of `verify --scan --data`. Changed/interrupted chat sessions are never silently replayed.
Current results and evidence limits: [migration record](../docs/LIBRARY_MIGRATION.md#current-acceptance).

For an explicitly approved bounded live session, launch with both attempt ceilings:

```bash
./deploy/deploy.sh local --env-file ../../deploy/env/existing-perth-m1.env \
  --allow-model-calls --max-model-calls 20 --max-data-calls 100
```

These example ceilings require operator approval; they are not a default grant.
`GET /api/local/budget` reads process-wide limits, reservations and unknown attempts
through the unchanged local auth gate, without contacting services. Native model/data
attempts and the exact-target Cosmos read-only-key lookup consume this shared budget.
Unknown attempts are not refunded. Per-request native limits and a 600-second context
deadline still apply; request counts are not a currency or billing cap.

A restart creates a new process budget. Preserve the old counters and pass only unused
allowances when continuing one approval; never silently replenish an exhausted grant.
Explicit `--max-model-calls 0 --max-data-calls 0` preserves an exhausted allowance on
restart. A scan with fewer available data requests than enabled rules refuses before
starting rules: JSON returns 403; SSE reports `data_budget_exhausted` with the remaining
allowance and required minimum. This is not a zero-hit scan or an Azure query failure.
Default startup without `--allow-model-calls` continues to deny inference. ADX start/stop
belongs to the root deployment runner and has separate ongoing compute charges.

The [2026-09-17 live activation record](../../../deploy/records/investigation-live-verification-20260917.json)
records real ADX scan/evidence, Cosmos graph, MITRE Search, model chat, summary and
diagnosis observations. Batching known sequence-recording calls avoids a separate
model round trip per step. Verification consumed its approved 20 model requests;
continuing that session requires a new allowance, not an automatic budget reset.

## Offline Native Browser

Goal: operate Investigation, query results, chat, knowledge, graph and Agent Editor with
real loopback HTTP and signed requests, using **SYNTHETIC service fixtures**. No Azure
login, provider call, customer data or production configuration is used. The test composition
owns service lifecycle; it does not execute the production ASGI lifespan.

1. Requirements: Linux, Python 3.12 virtualenv with Investigation dependencies including
  `pytest` and `pytest-asyncio`, uv 0.9.30, Node 20+, installed frontend dependencies and
  its Playwright Chromium. For a fresh setup, choose a new absolute external environment:

  ```bash
  cd template_apps/investigation_app
  umask 077
  export UV_PROJECT_ENVIRONMENT=/absolute/private/investigation-env
  export LIVE_PYTHON="$UV_PROJECT_ENVIRONMENT/bin/python"
  ./deploy/deploy.sh setup
  ```

  `setup` synchronizes the app's uv lock and frontend npm lock. It can download packages;
  it grants no cloud/model access. For an already installed isolated environment, set both
  variables to that same environment and skip setup. This sweep did not run setup.

2. Choose a new private absolute artifact directory outside the checkout, then run:

  ```bash
  export ARTIFACT_DIR=/absolute/private/new-investigation-browser
  ./deploy/deploy.sh browser-verify native-offline --help
  ./deploy/deploy.sh browser-verify native-offline
  ```

  Interpreter precedence: `LIVE_PYTHON`, then `VIRTUAL_ENV/bin/python`, then this app's
  `.venv/bin/python`. No automatic install/sync occurs in this runner; another template's
  interpreter refuses. External paths are validated without requiring a `/tmp` prefix.
  The runner builds the frontend and creates synthetic state under a fresh `run-*`
  directory inside `ARTIFACT_DIR`; it starts an ephemeral loopback server itself.

3. Read that run's `report.json`: `status: PASS`, seven passing phases, 42 checks, no
  browser errors, `browser_closed: true`, fixture cleanup and server exit 0. Desktop
  1440x900 and mobile 390x844 screenshots stay beside it. Expected matching refusals:
  anonymous 401, foreign-owner 404, replay and signature tampering 401. The signing key
  is ephemeral in memory; do not print it, export it or substitute a human credential.

Failure recovery: inspect the named failed phase and retained logs. Missing interpreter,
wrong Python/dependencies, checkout artifact paths, unavailable Chromium or unknown arguments
must be corrected before retrying in a new artifact directory. Never bypass auth, fill a
missing service response with customer data, or broaden live grants to fix a fixture test.
On exit the runner closes browser/server and native fixture services. Retain failed evidence;
when finished, remove only the exact owned synthetic run/environment, never authored agents,
ontology inputs, historical receipts or shared caches. No cleanup command removes real data.

Verification class: exact `--help` executed during this sweep; the full browser command's
existing receipt is read back in the migration record, not rerun here. All Bash examples
are syntax-checked only unless explicitly identified as executed or reused evidence.

## Genuine Ontology Tests

Both variables are required for the original-data gate. The following original locations
were found, not generated:

```bash
export CYBEREYE_ONTOLOGY_TEST_INPUTS=/home/hanchoong/perth_cyber/app/data/output
export CYBEREYE_ONTOLOGY_TEST_RAW='/home/hanchoong/perth_cyber/app/data/raws/perth/events_search_2026-08-13T08_51_46 (1).csv'
./deploy/deploy.sh test
```

Use the same `UV_PROJECT_ENVIRONMENT` as setup; `test` uses uv, not `LIVE_PYTHON`.
It runs backend/launcher tests, frontend tests and build. The
[ontology tests](../app/cybereye/tests/test_ontology_graph.py) verify five pinned hashes,
canonical absolute paths, no symlinks and inputs outside the checkout. Both unset skips
the original-data cases; partial/empty configuration or changed hashes fail. Do not
overwrite or regenerate source inputs to make a mismatch pass. Round-trip output uses
an owned external temporary directory, removed on exit. Current installed acceptance is
572 backend/deploy tests passed, including all 42 ontology tests, with zero skips. The
[migration record](../docs/LIBRARY_MIGRATION.md#current-acceptance) links exact artifacts.

## Authorized Live Reads

**LIVE, not run in this documentation sweep.** Exact targets, read authority and budgets
are prerequisites; no model/data mutation grant is implied.

With the app running and existing Perth/Cosmos/MITRE reads authorized:

```bash
./deploy/deploy.sh verify --scan --data --api http://127.0.0.1:9011
CYBEREYE_DATA_WORKFLOWS=1 CYBEREYE_URL=http://127.0.0.1:5174 \
  ./deploy/deploy.sh browser-verify scanner
```

Use the printed ports. `--data` adds existing graph overview/core/search/two-hop/selection,
MITRE preview/keyed read-back and matching missing/disabled refusals. It cannot be combined
with the historical `--baseline` artifact comparison. No model or data writes run.
The browser option is loopback-only and admits the graph plus the selected MITRE node;
automatic model requests are aborted, never faked. Normal app behavior and auth stay intact.
Frozen-candidate `CYBEREYE_READ_ONLY_ACCEPTANCE` restrictions remain stricter and unchanged.

HISTORY: 23 API and 72 browser checks passed at 1440/900/390px on the earlier artifact.
The sync graph-probe blocker is resolved in current source; these historical counts still
do not certify current live services. Error exits remain nonzero; retain failed evidence.
Keep screenshots private because they contain existing data. Output defaults remain ignored
under `artifacts/`; `ARTIFACT_DIR` may point to an external private directory.

For installed-wheel verification, set `LIVE_PYTHON` to the explicit independent app interpreter
for `local` and `verify`; no synchronization or editable path is selected. The historical run used
`/tmp/agentcraft-migration-resume-20260916/wheel-env/bin/python`, verified protected package
identity against wheel bytes, then passed the same API/browser checks. That temporary path
is local evidence, not a permanent installation prerequisite. See the
[current migration record](../docs/LIBRARY_MIGRATION.md) for ownership, source reduction and limits.

The root [Perth lifecycle owner](../../../deploy/README.md) now maintains disabled idle
auto-stop. Do not run the earlier source-project lifecycle commands below for this increment.
Continuous billing applies; no automated restarts or claims against external stop schedules.

## History: Earlier End-To-End Scope

**HISTORY / LIVE, not rerun.** Earlier authority is not a new grant. The following commands
require fresh explicit scope for compute changes, live model use and authored-state writes.

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

## Service-Backed Launch

- Use the isolated setup above. Existing Azure CLI login needs read access for optional cloud-backed features. Credentials
  stay in the operator's credential store, never copied into the template or a receipt.
- Either `--source-root /home/hanchoong/perth_cyber`, or `--env-file` naming non-secret
  coordinates following [the configuration example](../app/cybereye/.env.example).
- Chromium installed for the frontend's pinned Playwright version. If browser launch names a
  missing executable, install that browser through the owning frontend toolchain first.
- GUIDE and Bubblewrap are no longer Investigation prerequisites. No model run or source-state
  import happens on local startup.

```bash
./deploy/deploy.sh local --source-root /home/hanchoong/perth_cyber --check
./deploy/deploy.sh local --source-root /home/hanchoong/perth_cyber
```

`LIVE_PYTHON` selects the existing interpreter for `local`, `verify` and `replay-baseline`;
unset means `uv run --locked`. A selected missing interpreter fails without uv fallback.
**SOURCE-VERIFIED, not launched here:**
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
Default reports go to ignored artifacts directories; use a new private external
`ARTIFACT_DIR` for browser output and `verify --output` for API reports. These are local
evidence, not distributable datasets.

The existing editor browser journey writes new test agents into this template's local state,
checks immutable versions and simulated save-error recovery, and restores the prior Investigator
assignment. It does not delete authored records or run optimization. Repeated runs create new
owned test records; they are not byte-identical/idempotent state mutations.

## Historical Artifact Comparison Procedure

**LIVE, source-verified only here.** The verifier supports `--baseline`, `--candidate-wheel` and `--candidate-sha256` with
`--scan`. These are real-service reads and remain subject to the applicable approved scope.
Example after an independently established baseline and candidate-backed server are ready:

```bash
./deploy/deploy.sh verify --scan --baseline /absolute/private/frozen-baseline.json \
  --candidate-wheel /absolute/candidate/azdata-4.0.0a3-py3-none-any.whl \
  --candidate-sha256 APPROVED_WHEEL_SHA256 --output artifacts/verification/UNIQUE_RUN.json
```

Baseline schema: exactly `schema_version: 1`, `configuration_digest`, `window` with UTC
`start/end`, full `scan` response, and `evidence` keyed by every situation ID. The file is at
most 2 MiB, the window at most 48 hours, and at most 20 unique situations have complete
evidence. Keep customer evidence private; do not commit the baseline. It must originate from
an independently frozen source/expected result, not from the candidate being checked.

Before scanning, the verifier checks the configuration digest and protected
`/api/cyber/library-identity`. Backend code digest and distribution version must match the
wheel; editable imports and injected transport are refused. This endpoint reads a startup
snapshot of package metadata/files and lock-protected known/unknown query-attempt totals,
without service I/O, through the unchanged authorization gate. Restart the
backend with an independently installed candidate in an immutable external environment before
comparison; the normal editable development launcher is not an artifact-acceptance environment.
The separate root library runner verifies full installed artifact bytes and dependencies.

Comparison preserves row/column order, event timestamps, counts and truncation. Only
`scan.summary.elapsed_ms`, each rule execution's `elapsed_ms` and `observation.elapsed_ms`,
and each evidence response's `elapsed_ms/client_request_id` are ignored. All other fields remain
strict. Reports contain digests/checks, not evidence rows;
baseline runs require a new output path and cannot overwrite prior receipts.

Optional `--observed-out /absolute/private/NEW.json` retains full candidate responses for
diagnosis without another query. It requires a baseline, refuses checkout/existing paths,
caps output at 2 MiB and creates it mode 0600. Never point it at tracked receipts.

HISTORY: the 2026-09-15 continuation recorded 15 API comparison checks and 62 browser checks
against the identified wheel. Its `library-integration-continuation-20260915.md` receipt
is unavailable in this checkout; no replacement is fabricated or advertised as current proof.
The recorded native baseline was captured before the
candidate, not copied from its output; the accepted window ends at `03:40:00Z`, matching the
browser's minute-resolution controls, not the scenario's separate `03:40:59Z` endpoint.
The existing runbook's earlier source-app authorization is not a new library mutation/grant or
fixture-cleanup authority. The first canary runner creates no remote state.

### Independent Native Baseline

Use an isolated candidate environment via `LIVE_PYTHON` for every command; this bypasses
environment synchronization, not authentication. The native observer additionally requires
`azure-kusto-data[aio]==5.0.5`; a plain `kusto` extra does not install its `asgiref` prerequisite.
Capture protected `/api/cyber/detector/configuration` before scanning and retain it privately.

1. `deploy.sh replay-baseline rules --plan <existing-perth-plan> --configuration <frozen-config> --start <UTC> --end <UTC> --output <private-new-plan>` prepares five bounded queries without I/O.
2. Root [deployment runner](../../../deploy/README.md) `live observe` captures the exact plan
  through the native SDK under conversation/target/interval preflight; its `--baseline-out`
  must be a new private path. Native observations never receive library-pass credit.
3. `deploy.sh replay-baseline evidence` takes the observed rule plan with the same
  configuration/window/options and prepares exact evidence queries. Observe that new plan
  through the root runner, preserving its separate receipt.
4. `deploy.sh replay-baseline assemble` takes the observed rules, `--evidence <observed-evidence>`,
  and unchanged configuration/window to create the complete private baseline. It uses existing
  app synthesis and bounds, refuses missing/changed observations, and makes no service call.
5. Run `verify --scan --baseline ...` with the pinned wheel and a new receipt/observed output.

All three assembler actions require `--plan`, `--configuration`, `--start`, `--end` and
`--output`. Default host row cap is 99 plus one truncation sentinel, within 100 native rows.
The canonical configuration, window and meaningful ordering are never rewritten for equality.

### Read-Only Browser Acceptance

```bash
CYBEREYE_READ_ONLY_ACCEPTANCE=1 CYBEREYE_URL=http://127.0.0.1:5261 \
  ARTIFACT_DIR=/absolute/ignored/private/NEW \
  ./deploy/deploy.sh browser-verify scanner
```

This explicitly scoped verifier admits scan/evidence and no-I/O host routes, and aborts health,
graph, summary/diagnosis and other unapproved requests before server delivery. It records paths
and refusals without faking service results or disabling authentication. The normal UI has no
auto-inference off control; never browse it unguarded under a read-only/no-secret grant.
Normal full-workflow alert checks remain unchanged outside this verifier mode.
Screenshots/detailed logs may contain customer evidence and must stay ignored/private; redirect
console output to a private file. Reports retain real evidence counts, installed identity,
attempt counters and geometry. A local gate pass is not deployed Entra/signed-agent acceptance.

## Authorized Budgeted Read Verification

**LIVE, not rerun here.** Search/catalogue verification uses `browser-verify inventory`,
`verify-current-catalogue.mjs`. It is import-safe and guards Node fetches before browser
creation as well as every browser context before navigation. Service workers and sockets
are blocked. Health, graph, model/embedding, summary, diagnosis, classification, chat and
unreviewed mutations are aborted, never fulfilled with fake results. Authentication stays intact.

Use only a new external stage and isolated candidate interpreter; `setup`/`uv sync` must
not mutate the accepted M1 environments. Start through this template's existing launcher:

```bash
LIVE_PYTHON=/absolute/candidate/app-environment/bin/python \
bash /absolute/staged/investigation_app/deploy/deploy.sh local \
  --env-file /home/hanchoong/agentcraft/deploy/env/existing-perth-m1.env \
  --backend-port 9162 --frontend-port 5262
```

Use the ports actually printed. No `/api/health` request is needed; protected
`/api/cyber/library-identity` returns existing identity plus `read_surfaces.knowledge`
and `read_surfaces.catalogue.adx/search` counters without data/secret/model I/O.
The [production composition](../app/cybereye/backend/main.py) closes async probes, knowledge,
graph, agent and ADX before the borrowed credential exits, including startup rollback.
Offline test-owned lifecycle does not prove that production path.

```bash
LIVE_PYTHON=/absolute/candidate/app-environment/bin/python \
CYBEREYE_READ_ONLY_ACCEPTANCE=1 CYBEREYE_URL=http://127.0.0.1:5262 \
CYBEREYE_READ_RUNNER=/home/hanchoong/agentcraft/deploy/live.py \
CYBEREYE_READ_BASELINE=/absolute/private/frozen-browser-baseline.json \
CYBEREYE_READ_LEDGER=/absolute/private/read-ledger.json \
ARTIFACT_DIR=/absolute/private/NEW-browser-output \
bash /absolute/staged/investigation_app/deploy/deploy.sh browser-verify inventory
```

The baseline is mode 0600 under a 0700 directory. It identifies the candidate, approved
principal/expiry, root-ledger binding and exact protected runtime identity. Each approved
ADX/Search source has its validated node, independently frozen `metadata` and `content`
wire results with only `observedAt` excluded, and `limit: 25`, matching the existing UI.
Only `perth.adx.events_unified`, `ait.adx.events` and `cyberkb.search.mitre_attack` are admitted;
graph slots can be listed but never probed. Output directory must not already exist.

The verifier reserves worst-case source calls before read delivery, serializes read-producing
actions and reconciles protected canonical counters afterward. Missing/expired baseline,
candidate mismatch, exhausted ledger or unknown counter state refuses. Unknown delivery
retains its reservation. See [root ledger sequence](../../../deploy/README.md#child-search-and-catalogue-reads).

Three widths are required: 1440x900, 900x800 and 390x844. Checks compare metadata/schema,
preview wire values and rendered cells, operate keyboard/checkbox/all/none, reload and
narrowing recovery, measure overflow/targets and preserve private screenshots. Separate tabs
prove tab isolation only; they remain the same local principal, not distinct users.

Callable entry points are `deploy.verify.run_knowledge_read(context)` for retrieval/status/keyed
reads and async `deploy.verify.run_catalogue_read(context)` for existing service resource/content
envelopes. Context supplies exact candidate/target/operation/arguments, independent expected digest,
credential and host `preflight`, `reserve(maximum)`, `reconcile(reservation, metrics)` callbacks.
The host binds these callbacks to root `ReadLedger` and current approval. Counter unknowns never
become zero.

Live ToolBoard citation acceptance still requires an authentic reachable stored result and
missing/unavailable variants reusable without inference. The signed offline task proves its
synthetic citation journey only. Restricted-provider identity and distinct approved live
principals remain separate prerequisites; a fixture cannot supply live acceptance.

Stop only owned local servers with launcher Ctrl-C; verify printed ports are closed. Keep
private fixtures/artifacts for reproduction and leave accepted M1 environments/state untouched.

## Configuration And Safety Details

The launcher parses (never sources) the source project's committed production coordinates and
optional application environment file, copying only named connection settings. Other keys are
discarded. Credentialed service URLs refuse. Existing loopback authentication is reused in code;
the [production gate](../app/cybereye/backend/main.py) remains separate from fixture composition.

Agent versions stay under this template's ignored `.local` agents directory, regardless of
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