# Azure Connector Live-Test Infrastructure

**Scope: owned resource-group lifecycle, exact existing-Perth ADX keep-running lifecycle,
plus opt-in existing-source read acceptance.** The
`live` subcommand runs approved public-library ADX and Search cases; it does not provision services,
grant access, write telemetry, invoke models or tear down borrowed resources. The intended
consumer is [the connector library](../libraries/azure-data-connectors/README.md).

## Existing Perth ADX

The `adx` subcommand owns only the lifecycle authorized on 2026-09-16 for the existing
`adxperthcyber01` cluster. [The target](env/existing-perth-adx-lifecycle.json) pins tenant,
subscription, group, region, cluster, database and endpoint. No resource is created or
adopted for teardown. No data, role, identity, networking or other cluster setting is changed.

Keeping the cluster running causes continuous compute billing; price is unmeasured here.
Disabling `enableAutoStop` removes ADX inactivity auto-stop, not external schedules, later
operator actions or service outages. External stop schedules are **unknown**; indefinite
availability is not guaranteed. No heartbeat query is used.

Run from the repository root, in order:

```bash
PATH="$PWD/libraries/.venv/bin:$PATH" bash deploy/deploy.sh test
bash deploy/deploy.sh adx plan
bash deploy/deploy.sh adx keep-running \
   --confirm /subscriptions/67255afe-8670-4401-a1b8-df6ca63a3516/resourceGroups/rg-perth-airport-cybersec/providers/Microsoft.Kusto/clusters/adxperthcyber01 \
   --record deploy/records/perth-adx-keep-running-20260916-v2.json
bash deploy/deploy.sh adx verify \
   --record deploy/records/perth-adx-verify-20260916-v1.json
```

Expected: offline `OK`; read-only plan names exact ID and billing; mutation and independent
verification both report `state: Running`, `provisioningState: Succeeded`,
`enableAutoStop: false`, `read_back_verified: true`. Receipts contain actual CLI argv and UTC
observations, never credentials or event payloads. Existing receipt files refuse overwrite;
use a new versioned name for another run. Repeating `keep-running` on matching state is a no-op.

Prerequisites: Python 3.11+, Azure CLI with the `kusto` extension, an Enabled `AzureCloud`
account matching the target, and reported cluster-scoped read/write permission; a stopped
cluster additionally needs `Microsoft.Kusto/clusters/start/action`. No account switch or
permission grant occurs automatically. Permission inspection is not a complete access audit.
The full offline suite uses the existing library environment with its declared extras;
system Python without `azdata` cannot run the adjacent library acceptance tests. This
sequence neither syncs nor modifies that environment or the parent-owned workspace lock.

`Starting` is handled only by supported `az kusto cluster wait --custom`, bounded to 1800
seconds per transition, before the update. A stopped cluster starts without stopping it
first; `Running` with an in-progress operation waits. Unsupported transitions, unknown
auto-stop state, failed provisioning, wrong target and missing confirmation refuse before
mutation. Timeout or a reverted setting never reports success: retain the failed receipt,
run `adx plan` to inspect current state, resolve the named blocker, then use a new receipt.
Do not repeat a timed-out write blindly. There is no stop, delete or teardown subcommand.

The update uses `az rest --method patch` against the pinned cluster API `2022-02-01`,
with exactly `{"properties":{"enableAutoStop":false}}`. The installed generated
`az kusto cluster update` handler also injects unrelated default fields, including network
settings, so it is not used. Offline tests assert the complete PATCH body; before/after
read-back compares the protected settings independently. A policy-reverted auto-stop field
fails after lifecycle completion, without waiting indefinitely for the field to change.

Observed on this run: [the corrected PATCH](records/perth-adx-keep-running-20260916-v2.json)
read back `Running`, `Succeeded`, `enableAutoStop=false`, with every projected protected field
equal before and after. [Independent verification](records/perth-adx-verify-20260916-v1.json)
confirmed the same state at `2026-09-15T17:41:41.602874+00:00` (UTC; record names use the
operator's 2026-09-16 date). The existing restart had completed before this owner first inspected
the cluster; this run did not issue another start or any stop.

The [first generic-CLI attempt](records/perth-adx-keep-running-20260916-v1.json) did not persist
the desired auto-stop setting and is retained as failure, never relabeled success. Offline
inspection of that installed extension's prepared request proved it included unrelated defaults.
Current streaming/purge remained enabled in the [diagnostic snapshot](records/perth-adx-protected-settings-20260916-v1.json),
but their pre-attempt values were not captured, so the initial unrelated-field delta is unknown.
No restoration was guessed. Subsequent writes use only the literal one-property PATCH above.

## Target Authority

[env/azdata-live.env](env/azdata-live.env) is the authoritative non-secret target. It contains
the exact tenant, subscription, group and metadata location. The file is strict data, never
sourced as shell code. No credentials belong in it.

- Environment: `azdata-live`.
- Group: `rg-agentcraft-azdata-live-tests`.
- Metadata location: `eastus2`; future service locations/SKUs require their own availability check.
- Ownership tags: `managed-by=agentcraft-deploy`, `capability=azure-data-connectors`,
  `purpose=live-crud-tests`, `data-policy=synthetic-only`, `lifecycle=explicit-teardown`.
- Current status: created and independently verified on 2026-09-14. Last recorded state:
   `Succeeded`, matching required tags, zero child resources; repeat creation was `unchanged`.
- Empty resource-group ownership is not evidence of data-plane access or working CRUD.

The dated [creation and verification record](records/azdata-live-resource-group-2026-09-14.json)
contains the exact resource ID, observed timestamps, commands and verification limits. It is
historical evidence, not a substitute for running `verify` before future use. No services,
access grants, sample data or live CRUD tests were created or run in this change.

## Run Order

Run from this repository root using only [deploy.sh](deploy.sh). Python 3.11+ and a logged-in
Azure CLI are prerequisites. The script is invoked through Bash, so an executable file mode
is not required.

1. Run the offline safety checks. No Azure CLI call occurs:

   ```bash
   bash deploy/deploy.sh test
   ```

   Expected: unittest `OK`. Stop on failure before any cloud mutation.

2. Inspect the plan:

   ```bash
   bash deploy/deploy.sh -e azdata-live plan
   ```

   Expected: JSON with `action: plan`, the exact target, `would_create` and required confirmation.
   A matching group is reported, not rewritten. Another owner/location fails closed.

3. Create only after explicit authorization, confirming the full ID printed by the plan:

   ```bash
   bash deploy/deploy.sh -e azdata-live create --confirm '<full-resource-id-from-plan>'
   ```

   Replace the placeholder with the exact plan value. Expected: `created` or `unchanged`,
   `read_back_verified: true`, `provisioning_state: Succeeded` and actual resource inventory.
   A repeat with an owned matching group performs no second write.

4. Independently verify current state:

   ```bash
   bash deploy/deploy.sh -e azdata-live verify
   ```

   Expected: `verified`, ownership/location match and actual group contents. The current
   resource count should be zero until service provisioning is separately authorized.
   A later nonzero count is an observation to review, not a claim all children are owned.

The preflight refuses a different active tenant/subscription/cloud, disabled account,
unreported required permission or unavailable metadata region. CLI commands use explicit
subscription selection when the installed command supports it. No script silently changes
the shared Azure CLI context or grants itself permissions.

## Failure Handling

| Result | Next Action |
| --- | --- |
| Missing CLI/Python | Install prerequisites; no interactive privilege escalation is performed here. |
| Wrong active subscription | Operator runs the exact `az account set --subscription ...` printed by preflight. |
| Wrong tenant or expired login | Operator authenticates directly in their own terminal with the documented tenant; no password/token passes through an agent. |
| Missing permission | Review required resource-group action with an administrator. No automatic role grant. |
| Policy/lock refusal | Inspect the named policy or lock; do not disable or delete governance controls to make a test pass. |
| Existing owner/location mismatch | Preserve the resource; review target selection. Never silently adopt or retag it. |
| CLI timeout or failed read-back | Outcome may be unknown. Run `verify` before another mutation. No rollback is inferred. |
| Unexpected child resources | Stop before deletion and review their ownership. Group creation may not be the only subscription policy activity. |

Reported permission actions are not a complete effective-access audit. Azure Policy, deny
assignments, conditions, locks, quota and concurrent changes can still refuse an operation.
One writer owns this resource-group target; the existence check is not an atomic reservation.

## Teardown

Not authorized by the creation request. A future operator may run, after separately approving
deletion of this exact empty group:

```bash
bash deploy/deploy.sh -e azdata-live teardown --confirm '<full-resource-id-from-plan>'
```

This verifies owner/location, refuses any child resource or lock, deletes only the configured
group and reads back absence. It does not remove locks, grant roles or recursively retire
future paid services. Do not run it while another writer could populate the group.

## Next Live-Test Stage

The target group is for opt-in E2E connector checks using **synthetic data only**.
[The numbered live-test design](../libraries/azure-data-connectors/tests/live_tests/LIVE_TEST_DESIGN.md)
records the service coverage and acceptance cases. A read-only ADX feature and guarded runner
are now implemented and offline-tested; broader service cases remain planned. No live positive
case or fixture write has run in this increment; the group receipt remains historical evidence.

Before provisioning services or executing those cases, agree the instances, SKUs, regions, cost ceiling,
lifetime, network restrictions and least-privilege data-plane identity. Account-key or SAS
fallback is not a shortcut. Resource-group permission is not data-plane permission.

Live setup may use Azure CLI infrastructure APIs, but CRUD tests must call the library itself.
Use per-run IDs, a seed manifest and exact cleanup ownership. Cover native supported CRUD,
read-back of updated values, conflict/partition/permission failures and explicit unsupported
guarantees. Search atomic create and Cosmos merge are currently unsupported; a correct
refusal is part of interface coverage, not a reason to silently change operation semantics.

A live pass should produce dated non-secret evidence naming versions, resource IDs, run IDs,
operations, outcomes, verification and remaining sample data. Do not label the library live
verified until these checks actually run. Empty-group verification is infrastructure evidence only.

## Read-Only ADX Acceptance

Implemented owner: [live.py](live.py), reached only through `deploy.sh live`. Library calls
are visible in [the ADX feature](../libraries/azure-data-connectors/tests/live_tests/features/adx_query.py).
It uses public `azdata` imports and accepts host preflight/configuration; no runtime library
imports deployment or template code. A one-case plan selects an individual feature. Standalone
feature-module CLI authoring and broader composed consumer workflows remain pending.

First run the offline suite and inspect a plan; neither command calls Azure:

```bash
bash deploy/deploy.sh test
bash deploy/deploy.sh live plan --plan-file deploy/env/investigation-adx.example.json
```

Expected: unittest `OK`; plan JSON with `execution_enabled: false`, `status: BLOCKED`, exact
target, case IDs and `plan_sha256`. The example contains synthetic coordinates, a nonexistent
artifact path and an all-zero digest. It is not a usable or approved live target.

Before an operator authorizes `run`, provide a reviewed plan based on that schema with actual
subscription, tenant, principal, cluster/database resource ID and matching endpoint, candidate
wheel/path/hash/version, independent expected result, unique run ID, data classification and
call/row/byte/time bounds. File-based approval additionally states tolerated cost and its active
interval. The conversation-authority alternative below does not invent a user cost ceiling.
For historical replay, freeze the real window/configuration/evidence baseline independently;
the `print` example is only a transport canary, not scan/evidence parity.

For the file-based route, the operator supplies a private, non-group/world-writable JSON approval file **outside the
checkout**, containing exactly: `schema_version: 1`, `plan_sha256`, `approval_reference`,
`approved_by`, `not_before`, `expires_at`, `operations: ["query"]`, `max_cost_usd`, `resource_id`
and `principal_id`. The operator reviews it and supplies its canonical JSON SHA-256 separately
to `--approval-sha256`. Canonicalization is sorted keys, compact separators, ASCII JSON and no
non-finite values, matching `live.digest`. No approval file is generated by this runner or agent.
The validity interval is at most 24 hours. Unknown fields, changed plan/digest, other operations,
expired approval or missing cost authorization refuse.

This is a **trusted local operator workflow**, not a multi-user approval service or OS sandbox.
File ownership and the separately acknowledged digest protect against accidental substitution;
the checksum and `approved_by` text are not an independent signature or proof of human consent.
The executing operator is responsible for the external approval reference. A coding agent must
not mint that file/approval for itself, infer approval from CLI access, or use the example as a grant.

Only after exact approval, with an external environment containing the installed wheel and
`kusto,identity` dependencies:

```bash
LIVE_PYTHON=/absolute/operator-selected/environment/bin/python \
   bash deploy/deploy.sh live run --plan-file /absolute/reviewed-plan.json \
   --approval /absolute/operator-owned/approval.json \
   --approval-sha256 APPROVED_CANONICAL_SHA256 \
   --report deploy/records/UNIQUE_RUN_ID.json
```

This documented command is a template, not an action executed in this increment. The launcher
verifies the wheel hash, installed version, every packaged `azdata` file and import origin;
editable or checkout-resolved packages refuse. Identity preflight supports the active Azure CLI
**user** only: tenant/subscription/cloud plus signed-in object ID must match the plan. It does
not switch accounts; service-principal/managed-identity runner profiles remain unsupported.
Identity lookup uses bounded CLI reads; the library borrows the created credential and closes
its own connector. Plan limits cap data operations and whole execution time; SDK retries are
disabled for these cases. Credential acquisition has its bounded native process timeout.

Each approved query compares actual columns/ordered rows/truncation against frozen expected
values. Reports contain counts, digests and bounded metadata, never query text, parameters or
raw rows. Controlled transport tests produce `PASS_OFFLINE`, never a live pass. A local refusal
is distinguished from an attempted provider refusal. No model-quality or broad data-profile
coverage is inferred from a successful case.

Reports are exclusively created and atomically checkpointed with all required cases. A failing
case retains the unrun tail; interrupted attempt counts are null with a reason. Reusing a report
path refuses without overwriting evidence. Nonzero exit means blocked/failed/incomplete; zero
requires every planned case's expected positive/refusal outcome. The runner creates no remote
fixtures, so cleanup is `no_remote_state_created`; broader mutation/teardown remains unsupported.
Costs stay null until independently observed, and a cost authorization is not a billing cap.

Known remaining gates: approval/readiness outside the existing-source read scope,
standalone/composed feature entry points, additional service profiles, provider negatives and
full independent developer acceptance. The bounded M1 application parity/browser outcome now
passes; its exclusions and receipts are recorded below.

## Conversation-Authorized Existing Reads

The user's exact statement, "Live testing authorized against all existing deployed data
sou4ces on Azure. Proceed.", is sufficient provenance for the bounded existing-source reads
in this programme. It does not authorize provisioning, starts/stops, permissions, secret
retrieval, writes/deletion, model/embedding inference or auth/network changes. Do not create
an operator-authored approval file or signature on the user's behalf.

The current runner supports `live plan`, `observe`, `run`, `derive-search-reads` and `inventory`.
`observe` uses an independent native SDK and writes full expected values only to a new private
`--baseline-out` outside the checkout. It receives no library-pass credit. `run` calls the
installed public library. `derive-search-reads` is offline; `inventory` performs bounded ARM
metadata reads, not data-plane parity or automatic estate-wide adoption.

Exact existing targets are in [Perth ADX](env/existing-perth-adx.json),
[AIT ADX](env/existing-ait-adx.json), [MITRE Search](env/existing-mitre-search.json) and
[MITRE queries](env/existing-mitre-queries.json). Their null expected values require an
independent `observe` pass before `run`; never fill them from candidate output.
Native ADX observation needs `azure-kusto-data[aio]`, in addition to the installed candidate.

Use the actual new plan's canonical SHA-256 from `live plan`. Continuing a shared call budget
requires `--require-ledger --ledger /absolute/private/read-ledger.json`; initialize it through
the [ledger sequence](#child-search-and-catalogue-reads).
Example invocation, after choosing a fresh reviewed interval and private output paths:

```bash
LIVE_PYTHON=/absolute/isolated/environment/bin/python \
   bash deploy/deploy.sh live observe --plan-file /absolute/private/read-plan.json \
   --require-ledger --ledger /absolute/private/read-ledger.json \
   --conversation-statement 'Live testing authorized against all existing deployed data sou4ces on Azure. Proceed.' \
   --conversation-reference conversation:2026-09-15:definitive-continuation \
   --plan-sha256 FROZEN_PLAN_SHA256 --not-before EXECUTOR_UTC_START --expires-at EXECUTOR_UTC_END \
   --report deploy/records/UNIQUE_NATIVE_RUN.json --baseline-out /absolute/private/NEW-observations.json
```

For `run`, use the resulting observed plan and its digest; omit `--baseline-out`. The trusted
local executor records `origin: conversation-user`, the exact statement/reference and its own
interval, not a purported independent human signature. Wrong principal/target, changed digest,
expired interval, mutations, editable artifacts and excess bounds still refuse. Billing and
`user_cost_ceiling_usd` stay unknown/null; executor ceilings are not user spending commitments.
This continuation permits at most 100 total reserved data calls, sequential sources, 30 seconds per
query and 100 rows/1 MiB per generic result. Retain known/unknown attempts across all receipts,
including native observers and failed attempts; do not reset the aggregate budget per plan.

The installed-wheel M1 comparison passed 15 API checks and 62 read-only browser checks with
independent native rule/evidence capture. The [historical continuation record](records/library-integration-continuation-20260915.md)
retains exact observations, artifact identity, private paths, accounting and cleanup. The
[template runbook](../template_apps/investigation_app/deploy/README.md) owns baseline assembly,
candidate API comparison and the browser guard. Do not call legacy `/api/health` or browse
automatic model/graph flows unguarded under this grant. Existing passing canaries are reused;
the programme is not complete and no required blocked/unrun case has become a pass.

Historical records preserve original commands and retired coordination labels as evidence,
not current setup instructions. Use this runbook for new executions.

## Child Search And Catalogue Reads

Child implementation extends this same runner with `search-citation`, a persistent `ReadLedger`,
strict ordinal ADX schema/typed sample comparisons, and local `reconcile`. No new resource,
grant, secret, model, write or teardown workflow is part of this sequence. Root README and
cross-feature coordination remain `overseer`-owned. The
[case manifest](records/m2-search-catalogue-case-manifest.json) retains required acceptance rows.

1. Install the exact non-editable candidate set recorded by the child candidate receipt,
   outside this checkout, and run offline contracts/public examples. Both staged apps must
   import the same foundations/azdata wheels; Python/SDK cohorts have separate transport tests.
   The [public Search guide](../template_apps/shared/README.md) owns ordinary caller setup.
2. Create the single private ledger once from the retained continuation, never from a fresh
   allocation. Directory mode 0700, files 0600, new absolute paths only:

```bash
LIVE_PYTHON=/absolute/candidate/environment/bin/python \
bash deploy/deploy.sh live ledger-init \
  --plan-file /home/hanchoong/agentcraft/deploy/records/library-integration-continuation-20260915.json \
  --ledger /absolute/private/read-ledger.json
```

Expected: 26 known, one unknown, 27 reserved, 73 remaining. Repeated initialization refuses
without overwriting. `live ledger-status --ledger ...` reads the same ledger. `ledger-reserve`
and `ledger-settle` are the browser/callable adapters' serialized accounting interface,
not permission to replace measured usage with zero. Unknown delivery keeps its full reservation.

3. Freeze all required case/target/consumer/viewport/evidence rows before candidate reads.
   Include native capture, consumer relaxation/counts, cold metadata/preview, developer and
   browser calls. A required cohort that cannot fit stays BLOCKED pending reservation expansion;
   never reset per plan or silently omit a required row. Seed `expected: null` is not an oracle.
4. Run `live plan`, then independently `observe`, then `run` with the returned frozen plan:

```bash
LIVE_PYTHON=/absolute/candidate/environment/bin/python \
bash deploy/deploy.sh live observe --plan-file /absolute/private/native-input.json \
   --require-ledger --ledger /absolute/private/read-ledger.json \
  --conversation-statement 'Live testing authorized against all existing deployed data sou4ces on Azure. Proceed.' \
  --conversation-reference conversation:2026-09-15:complete-child-implement \
  --plan-sha256 EXACT_PLAN_DIGEST --not-before EXECUTOR_UTC_START --expires-at EXECUTOR_UTC_END \
  --report /absolute/new/payload-free-native-receipt.json --baseline-out /absolute/private/frozen-read.json
```

`live plan --plan-file /absolute/private/frozen-read.json` prints that exact plan's digest.
Use it with `live run`, the same authority/ledger flags and a new report path; omit
`--baseline-out`. The native observer writes `baseline_binding` with exact input, target,
principal, artifact and expected-result digests and capture time. Candidate launch refuses
missing/stale/mismatched bindings before credentials. Capture validity is at most 24 hours;
an executor interval references actual user authority, never an invented human approval.

ADX catalogue schema uses one ordinal-packed `getschema` query, not old alphabetic receipts.
`comparison: typed-multiset` is permitted only for declared unordered samples; column order
and typed membership remain exact. Search query/count/read/schema use their public feature
functions. `workflow: search-citation` requires frozen `reads` and `missing` step cases;
actual query output supplies keyed reads and shared projected content/provenance must match.
Observe its constituent features first; the workflow cannot derive its oracle from itself.

Every query is <=30 seconds, metadata count+schema <=20 seconds overall, one attempt,
<=100 rows and <=1 MiB. No automatic paging or hidden retries. Provider denial is distinct
from local refusal; no restricted identity means BLOCKED, not permission to create one.
Original failed/unknown rows remain in receipts. Raw observations stay private.

5. Run both callable consumers and the [guarded browser sequence](../template_apps/investigation_app/deploy/README.md#child-read-verification)
   against the same candidate. Independent developer follows this guide plus the public Search
   guide and approved frozen inputs; source-author rehearsal is not independent evidence.
6. Reconcile hashed receipts locally, without credentials or service calls:

```bash
LIVE_PYTHON=/absolute/candidate/environment/bin/python \
bash deploy/deploy.sh live reconcile --plan-file /absolute/private/case-manifest.json \
  --report /absolute/new/acceptance.json --summary /absolute/new/acceptance.md
```

Every manifest row names a stable `SCR-` ID, family, required flag, evidence class, absolute
receipt path/file hash and receipt case ID, or an explicit blocker. Receipt candidate digest
must match the manifest. Duplicate/missing/incompatible evidence cannot pass. Exit 2 retains
required FAIL/BLOCKED/NOT_RUN rows; exit 0 requires every declared required row's evidence.
No remote state created is the cleanup claim, not teardown or whole-programme completion.

## Procedure Reference

[azure-cli-infra-management](../.github/skills/azure-cli-infra-management/SKILL.md) documents the
reusable procedure. This deployment directory, not the skill, owns this project's real targets,
runner and operational record. [tests/test_resource_group.py](tests/test_resource_group.py)
proves the target/policy/ownership guards with fake CLI responses; it does not use Azure.