# Agentcraft Azure Deployment

**Scope: standalone protected writeup deployment, owned testing resource-group lifecycle,
explicitly authorized legacy-group retirement,
exact existing-Perth ADX keep-running lifecycle,
plus opt-in existing-source read acceptance.** The
`live` subcommand runs approved public-library ADX and Search cases; it does not provision services,
grant access, write telemetry, invoke models or tear down borrowed resources. The intended
consumer is [the connector library](../libraries/azure-data-connectors/README.md).

## Public Investigation Data

`bash deploy/deploy.sh public-data --evidence PATH {acquire|verify|normalize|checks}` forwards
to Investigation's single [public-data owner/runbook](../template_apps/investigation_app/deploy/README.md#public-data-local-package).
It acquires pinned public Splunk/MITRE inputs and produces a locally verified three-store package;
no Azure calls, grants, secrets, auth changes or model requests. Optional `public-data-runtime`
installs an existing transport wheel into ignored app-local storage without a venv. Exact sequence,
failure recovery, input rights, output paths and expected counts are in that runbook.
`rg-agentcraft-dev` is a requested future target, not an implemented deployment command.

## Project Testing Group

The project-wide target is [env/agentcraft-testing.env](env/agentcraft-testing.env):
`rg-agentcraft-testing`, subscription `67255afe-8670-4401-a1b8-df6ca63a3516`, tenant
`c79ab2bb-79cb-47f1-b4da-b6852fe45ff7`, cloud `AzureCloud`, metadata region `eastus2`.
Created and independently read back empty on 2026-09-16; the [creation record](records/agentcraft-testing-created-20260916.json)
contains timestamps, commands and project ownership tags. No service, image, identity, role grant
or writeup deployment was created in that initial group-only operation. The group now hosts
the [standalone writeup](#writeup-deployment). Region selection matches the former writeup's region; future
service/SKU availability and cost still require review. `data-policy=operator-approved` is a label,
not a data-access grant or permission to upload data.

Run from the repository root:

```bash
python3 -B -m unittest discover -s deploy/tests -p 'test_*resource_group.py' -v
bash deploy/deploy.sh -e agentcraft-testing plan
bash deploy/deploy.sh -e agentcraft-testing create \
   --confirm /subscriptions/67255afe-8670-4401-a1b8-df6ca63a3516/resourceGroups/rg-agentcraft-testing
bash deploy/deploy.sh -e agentcraft-testing verify
```

Expected: tests `OK`, plan names the exact target, create returns `created` or `unchanged`,
verify returns `Succeeded`, matching tags and actual contents. No implicit account switch,
retagging, service provisioning or permission grant occurs. Existing `azdata-live` behavior and
tags remain unchanged. Empty-group teardown stays separately authorized and refuses child resources.

## Writeup Deployment

The app and active deployment tooling moved on 2026-09-18 to
`/home/hanchoong/han-ops-center/agentcraft_doc app`. Quote the path's space.
Use that app's `deploy/WRITEUP.md` and `deploy/deploy.sh writeup` entry point.
This repository's writeup entry point now refuses before any Azure call; the section below
and retained runner/configuration/receipts are historical evidence. No cloud change occurred.
Commands below must be run from the new app directory, not this repository.

Live: **https://ca-agentcraft-writeup.wonderfulmoss-6cbdac9f.eastus2.azurecontainerapps.io**.
Latest release independently verified on 2026-09-17: image
`acragentcraftwriteup.azurecr.io/writeup:20260917124457`. The
[deployment receipt](records/writeup-deploy-20260917-release.json) and
[independent verification](records/writeup-verify-20260917-release.json) own current evidence.
Production build, dataset synchronization, signed content digest and unauthorized-access checks
passed. Live browser checks at 1440x900 and 390x844 loaded all three homepage images, four dataset
JSON regions, the source PDF and bundled demo, then returned home without JavaScript exceptions.
Anonymous browsers reached Microsoft sign-in; interactive employee sign-in remains unverified.
The group contains exactly four resources and one application; the bundled demo is static content,
not another deployed app. Microsoft corporate sign-in is required for human readers.

The [writeup target](env/writeup.json), [Bicep template](infra/writeup.bicep) and
[runner](writeup.py) historically deployed only the relocated writeup app to
`rg-agentcraft-testing`: `ca-agentcraft-writeup`, `cae-agentcraft-writeup`,
`acragentcraftwriteup` (Basic), and `id-agentcraft-writeup` with registry-scoped `AcrPull`.
No database, model, separate demo backend, Log Analytics workspace, or other template app is
provisioned. The kiosk remains a static route in the same image. ACR has a standing charge;
Container Apps uses consumption resources (0.25 CPU, 0.5 GiB, 0-1 replicas). Cost was not measured.

Run from the relocated app directory. Requires Azure CLI/Bicep, Node.js 22, installed app/demo npm
dependencies, Python with `cryptography`, and the existing private operator key outside the repo.
The runner never generates a missing key or creates a client secret.

```bash
python3 -B -m unittest discover -s deploy/tests -p test_writeup.py -v
az bicep build --file deploy/infra/writeup.bicep --outfile /tmp/agentcraft-writeup-template.json
bash deploy/deploy.sh writeup plan --record deploy/records/writeup-plan-20260916.json
bash deploy/deploy.sh writeup deploy \
   --confirm /subscriptions/67255afe-8670-4401-a1b8-df6ca63a3516/resourceGroups/rg-agentcraft-testing \
   --record deploy/records/writeup-deploy-20260916.json
bash deploy/deploy.sh writeup verify --record deploy/records/writeup-verify-20260916.json
```

Use a new receipt filename on each run. Expected: tests `OK`, Bicep compilation, a four-resource
plan, `deployed` with an HTTPS URL, then independent `verified`. The runner checks project ownership
and account, builds locally, provisions hosting, appends only its new callback to the retained
registration, builds images in ACR, deploys with private ingress, reads back auth, and exposes
ingress only for live positive/refusal checks. Failed live verification disables ingress again.
No account switch, new operator privilege, credential retrieval, or broad access grant occurs.
Existing resources with different owner tags refuse adoption. Repeated callback setup is a no-op;
published images use unique tags and therefore create a new release.

Authentication retains the app's default-deny gate and the existing Ed25519 operator verifier,
with native Easy Auth pinned to corporate tenant `72f988bf-86f1-41af-91ab-2d7cd011db47`.
The old client secret was deleted with the legacy Container App. This static reader uses the
documented [ID-token-only mode](https://learn.microsoft.com/en-us/azure/container-apps/authentication-entra#enable-microsoft-entra-id-in-your-container-app)
without a client secret. **This uses OAuth implicit flow, which Microsoft discourages when more
secure alternatives are viable.** It requests no downstream API permissions or access/refresh
tokens. Restoring confidential-client code/hybrid flow requires an operator-owned Key Vault
credential reference and separate credential handling; no token-flow equivalence is claimed.
The existing registration's audience and other callbacks remain unchanged. The new callback is
read back after writing. No new app registration or API permission is created.

Each revision has a single-replica maximum; the inherited replay cache is still process-local.
Restarts and possible revision overlap are not covered by that limit. No auth-disabled test or bypass header is used.
Verification checks health, anonymous document/asset/unknown-path refusal, forged principal and
cookie refusal, signed content SHA-256 against the local build, signature replay/wrong-path refusal,
and the native tenant/audience/callback/state/nonce redirect. Interactive employee sign-in and
first-use corporate consent remain user-owned acceptance, not a claim inferred from that redirect.

On build/deployment failure, inspect the recorded phase and Azure state before retrying. Never
re-enable public ingress around a failed auth check. The retired app-local deployment CLI remains
disabled. Resource-specific teardown must preserve the project RG and any other future workloads;
it is not authorized by this deployment request. No backup purge or Entra-registration deletion is
implied. Live browser checks at 1440x900 and 390x844 reached the Microsoft sign-in page without
an AADSTS error, rendered authenticated content through the existing signed operator path,
loaded images and dataset PDF, and navigated the demo back to Overview. No JavaScript exceptions
or homepage horizontal overflow were observed. The inherited demo's cramped mobile controls
remain outside deployment scope.

The [first attempt](records/writeup-deploy-20260916.json) failed Azure provider validation:
`appLogsConfiguration.destination=none` is not an accepted string. The corrected template omits
logging configuration and passed both Bicep and Azure validation before the successful second
attempt. No Log Analytics workspace was added. Historical failure evidence is retained.

## Legacy Singtel Retirement

User authorization on 2026-09-16 explicitly covers **`rg-singtel-ticket-poc` and every resource
and service's data within it**, not just the writeup. The [retirement target](env/singtel-retirement.json)
pins the same subscription/tenant, region and observed legacy tags. No backup of other service
data was requested or created. The local writeup source now lives in
`/home/hanchoong/han-ops-center/agentcraft_doc app`.
Entra registrations and resources outside the named group are not directly deleted; Azure may
clean up provider-managed infrastructure when deleting its owning Container Apps environment.

The initial read-only inventory contained 27 ARM resources: three Container Apps, two managed
environments, five jobs, two Cosmos DB accounts, two identities, one ACR, one Log Analytics
workspace and networking. No group or subscription locks were present. The runner freezes a fresh
inventory before deletion and refuses changed IDs, ownership, resource sets or locks. The inventory
checksum guards accidental substitution; it is not a grant or independent proof of consent.

Run only through [deploy.sh](deploy.sh), with new receipt paths for each attempt:

```bash
bash deploy/deploy.sh retire plan --record deploy/records/singtel-retirement-plan-20260916.json
bash deploy/deploy.sh retire delete \
   --inventory deploy/records/singtel-retirement-plan-20260916.json \
   --confirm-inventory '<inventory_sha256 from the reviewed plan>' \
   --confirm /subscriptions/67255afe-8670-4401-a1b8-df6ca63a3516/resourceGroups/rg-singtel-ticket-poc \
   --record deploy/records/singtel-retirement-delete-20260916.json
bash deploy/deploy.sh retire verify --record deploy/records/singtel-retirement-verify-20260916.json
```

Expected: plan records exact resources; delete uses native group deletion, which stops/removes
contained workloads, then a bounded native waiter; verify independently reports `verified_absent`.
No separate scale-to-zero toggle is used, and Cosmos/registry contents are deleted with their
services. `read_back_verified: true` after absence is the completion evidence, not acceptance of
the deletion request. Receipt paths refuse overwrite. If deletion or waiting times out, do not
issue another mutation blindly: inspect and run `retire wait --record deploy/records/NEW-NAME.json`
to wait without another delete. Locks or permission/policy refusal require operator resolution;
the runner never removes a lock, grants itself access, or purges soft-deleted backups.

Completed on 2026-09-16. The [frozen inventory](records/singtel-retirement-plan-20260916.json)
contains 27 resources; [deletion](records/singtel-retirement-delete-20260916.json) completed at
`07:19:48 UTC`, and [independent verification](records/singtel-retirement-verify-20260916.json)
confirmed the group absent at `07:20:16 UTC`. The provider-managed group
`ME_cae-singtel-evidence_rg-singtel-ticket-poc_eastus2` is also absent; a subscription resource
listing found no remaining resources in either group. No direct deletion outside the named
legacy RG was issued.

The [completion record](records/agentcraft-rg-transition-complete-20260916.json) includes those
observations and a fresh verification of `rg-agentcraft-testing`: `Succeeded`, matching tags,
zero resources at `07:20:20 UTC`. Entra registrations and the operator's local signing key
remain untouched. Provider-retained backups were not purged; retention and residual charges
were not assessed. That group-transition record predates the later, separately authorized
[writeup deployment](#writeup-deployment).

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