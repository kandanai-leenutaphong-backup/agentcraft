# Content Understanding Reference Host

**Retired locally, 2026-09-16.** The Function source, testbed client, uv environment,
deployment commands, verifier and derived packages were removed at the user's request.
Use the [standalone native SDK skill](../../../.github/skills/azure-content-understanding/SKILL.md)
for new extraction. No active deployment entry point remains in this testbed.

This directory preserves targets, infrastructure definitions and prior cloud records
for separately authorized cleanup. **No Azure resources, roles or Entra objects were
deleted.** Last observed resources included the Function/hosting/network/storage,
CU service and retired DI account. Current cloud liveness was not queried during
filesystem retirement; ongoing cost remains unknown.

[Frozen removal/recovery record](./records/20260916-function-wrapper-retirement.json):
8,733 files and 267,535,451 logical bytes removed; 445 protected files unchanged.
The former tooling and manuals are in the verified external archive
`/home/hanchoong/datacrafting-function-retirement-20260916.oolU5R/retired-wrapper.tar.gz`.
SHA-256: `25436025799509e508115afa27fd56290e9fe6d8b930e3a406b397dd73ef976c`.

## Recovery For Cleanup

For future authorized cloud cleanup, verify the archive hash, restore into a new
external recovery directory and review the preserved target, inventory and owner
guards before using the restored lifecycle owner. The archive stores repository-
relative paths; retained `env/`, `infra/` and `records/` supply the corresponding
operational evidence. Do not blindly restore over this checkout or execute old
deployment commands. Group-wide deletion would also remove the CU resource needed
by the native skill and must not be inferred from wrapper retirement.

## Historical Runbook

Everything below records the former host and is **not runnable from this checkout**.
References to shell commands require the separately restored archived tooling.
Keep exact resource/identity facts for operator review; do not treat this runbook
as present authority to provision, publish or delete anything.

> Current status, 2026-09-16 08:15 UTC: **CU-only publication and live acceptance passed.**
> [Dated publication evidence](#cu-only-publication-2026-09-16) supersedes the earlier blocked-status
> statements retained below. Historical receipts are unchanged.

**CU-only source/package verified; live release blocked by undeclared resources.** The retained source uses only
GA `2025-11-01/prebuilt-layout`. Two original successful CU receipts are unchanged; the live app was not updated.
[Historical three-method acceptance](./records/20260916T065843550937Z-acceptance.json)
is prior evidence, not proof of the new release. No local SDK fallback.

Sole lifecycle: `bash testbeds/datacrafting/deploy/deploy.sh ACTION`, repository root as working directory.
[Target](./env/experiment.json), [dedicated caller identity](./env/identity.json), [live endpoints/MI](./env/runtime.json).
Never switch the shared CLI account. Subscription `67255afe-8670-4401-a1b8-df6ca63a3516`, tenant
`c79ab2bb-79cb-47f1-b4da-b6852fe45ff7`, AzureCloud, East US. Only the two immutable manifest PDFs are accepted.

## Existing-Host Release

Prerequisites: `az` 2.83.0, Bicep 0.40.2, `uv` 0.9.30, Python 3.12, existing authorized Azure CLI login.
All Python environments and release installs use uv with frozen locks. No install credential, secret file,
account key, connection string, publishing password or host key is required or fetched.

```bash
bash testbeds/datacrafting/deploy/deploy.sh offline
bash testbeds/datacrafting/deploy/deploy.sh verify-results
bash testbeds/datacrafting/deploy/deploy.sh build
bash testbeds/datacrafting/deploy/deploy.sh check-package
bash testbeds/datacrafting/deploy/deploy.sh release
bash testbeds/datacrafting/deploy/deploy.sh verify
```

- `offline`: test positives/refusals and the isolated CU CLI; expected unittest OK and one help output.
    Documentation validation reports the parent-owned canonical skill as pending if promotion is not yet present.
- `verify-results`: two fixed CU receipts, source hashes, native equality, GA analyzer identity,
    frozen artifact hashes, 32 narrative facts and six native row associations. No cloud call or baseline dependency.
- `build`/`check-package`: read back security, export the frozen lock, install with uv into the package, verify
    exact ZIP/source equality and three bindings: `ContentUnderstanding`, `ExtractionStatus`, `ExtractionHealth`.
    No PDFs, DI hosts or legacy DI configuration are included in the deployment ZIP.
- `release`: validates the exact package and existing Easy Auth, requires the Function already active, then uses
    Entra bearer with native SCM `/api/publish?RemoteBuild=false` and bounded Azure Core LRO polling.
    No auth, ingress, activation, role or service changes. A disabled/private site stops for separate authorization.
    A completed identical package is reused; an unconfirmed/active publication refuses duplicate upload.
- `verify`: exact live three-function inventory, authenticated health, anonymous/forged/wrong-audience refusal,
    retired routes returning 404 with no job, invalid CU PDF refusal, query-target refusal, both persisted CU
    results, completed-job replay, conflicting-document 409 and no CU model deployments. No new analysis job.

Each failure exits nonzero and writes a bounded record under [records](./records/).
Account mismatch: operator must restore the exact authorized CLI context; this runner never switches it.
Package mismatch: rerun `build` and `check-package`, not an old multi-method ZIP.
Unconfirmed publish: inspect the recorded deployment before retrying. Never disable auth or use keys.

When fresh security readback is blocked, local packaging remains available without cloud calls:

```bash
bash testbeds/datacrafting/deploy/deploy.sh build --local-only
bash testbeds/datacrafting/deploy/deploy.sh check-package
```

This validates cached exact targets and the owned caller identity; it does not attest current cloud security
or authorize deployment. `--local-only` refuses on every action except `build`. Release always performs
fresh strict ownership/auth readback. Old build packages remain historical, not valid CU release inputs.

## Separately Authorized Actions

These are not part of filesystem cleanup or the CU-only release sequence:

- `research`: verify archived official documentation under [references](./references/) against URL/hash/time
    provenance. Offline, not a live refresh. The original shared fetcher was removed by concurrent workspace work;
    deployment replay has no dependency on it. A refused URL stays a refusal; do not bypass access controls.
- `inspect`/`plan`: account, group/name collisions, native SKUs, Python runtime, permissions, Bicep and what-if.
    Unknown ownership refuses. Provider registration is already present; a newly missing registration stops preflight.
- `configure-caller`: creates only the tagged dedicated API registration/service principal. Azure CLI is
    preauthorized on this API's delegated scope; no shared app, tenant-wide consent or credentials are changed.
- `check-caller`: obtains OAuth in memory and validates signature/audience/tenant/principal/client/scope.
    Mismatch or missing login stops before paid resource apply.
- `apply`: repeats preflight/what-if, applies owned Bicep, independently reads inventory. Initial site is disabled
    with ingress disabled. Reapply preserves an already authenticated active site's state. No deletion in apply.
    Current template provisions no DI account or DI grant. A new installation's activation needs its own reviewed
    lifecycle change; this bounded existing-host release does not silently open ingress.
- `run --method content-understanding --document yallourn|murray|all`: uploads only the exact selected manifest
    PDF through the CU adapter. Every fresh attempt creates a new paid analysis and UTC receipt directory.
    Retired methods and the old `--method all` selector refuse. Failures exit nonzero.

For an already working installation, use `verify` to inspect it without reprocessing PDFs. `verify-results`
checks local artifacts offline. `run` intentionally creates new paid analysis jobs, not a verification shortcut.

## Results

| Method / Native API | Yallourn: 7 pages | Murray: 6 pages | Markdown / Tables |
| --- | --- | --- | --- |
| CU Layout, GA `2025-11-01/prebuilt-layout` | [11.076666 s](../content-understanding/results/yallourn/20260916T065358185028Z/receipt.json) | [7.997588 s](../content-understanding/results/murray/20260916T065409548693Z/receipt.json) | yes / 5, 3 |

Times are measured client wall durations for these runs, including OAuth/request/poll/artifact overhead, not
benchmarks. Per-function durations and polling counts are beside each receipt. Complete native service JSON
is preserved. CU usage reports 7 + 6 `documentPagesStandard`.
Raw content is never repaired. Layout text files preserve provider Markdown, including HTML tables.
The verifier selects these exact receipt directories, not newer successes. Competing raw results,
original method guides, failed attempts and comparison executable exist only in the
[external verified recovery archive](../content-understanding/evidence/selection/cleanup.json).
[Historical assessment and renders](../content-understanding/evidence/selection/ASSESSMENT.md) remain local.

Live Python 3.12.13; local Python 3.12.3. Azure Core 1.41.0, Identity 1.25.3, Functions 1.25.0,
Storage Blob 12.30.1, PyJWT 2.14.0. Full transitive pins live in the host and CU adapter uv locks.

## Authentication And Resources

Endpoint: `https://func-agentcraft-pdf-20260916.azurewebsites.net/api`.
CU-only bindings: `ContentUnderstanding`, `ExtractionStatus`, `ExtractionHealth`.
[Archived callable contract and ownership](./records/20260916-function-wrapper-retirement.json).

Caller: Entra operator object `b06960e4-56e1-4780-85b5-cdb0dc3b10c4`; API client ID
`4c930454-cb9c-43b8-95f8-1783fdc3f513`; Azure CLI client `04b07795-8ddb-461a-bbee-02f9e1bf7b46`;
delegated scope `access_as_user`. The API validates its own audience, not an ARM token. Forged principal
headers are ignored. Native bindings omit function keys; mandatory platform Entra plus validated JWT stay on.

Workload MI: `id-agentcraft-pdf-20260916`, client `d3d3164d-7337-478b-85d2-645491d4dca0`, principal
`0f8d045c-f0b7-4803-800f-95503d01565e`. Never used as the incoming caller identity.

Group: `rg-agentcraft-datacrafting-20260916`; owner tag `agentcraft-datacrafting-20260916`.
[Exact IDs, security properties and assignments](./records/20260916T065804327660Z-security-readback.json).

| Resource | Configuration / Lifetime |
| --- | --- |
| `func-agentcraft-pdf-20260916`, `plan-agentcraft-pdf-20260916` | Flex Consumption FC1, 512 MB, maximum 40 instances, HTTP concurrency 1, no always-ready instances |
| `stdcpdf26091667255` | Standard_LRS, public network disabled, shared keys disabled, private blob containers for package/host/jobs |
| `id-agentcraft-pdf-20260916` | Runtime requires Blob Data Owner on this storage and Cognitive Services User on CU; historical DI grant retained, not revoked |
| `di-agentcraft-pdf-20260916` | **Retired but still allocated.** Historical FormRecognizer S0, local/key auth disabled. Not provisioned, contacted or required for CU runtime verification; separate scoped approval required for deletion/grant cleanup |
| `cu-agentcraft-pdf-20260916` | AIServices S0, local/key auth disabled; no model deployment or provisioned throughput |
| `vnet-agentcraft-pdf-20260916`, `pe-agentcraft-pdf-blob-20260916` | Dedicated Functions subnet, private endpoint subnet, managed endpoint NIC |
| `privatelink.blob.core.windows.net`, `datacrafting-network` | Owned private DNS zone and virtual-network link |
| `log-agentcraft-pdf-20260916`, `owned-function-errors` | Log Analytics PerGB2018, 30 days, configured 0.1 GB/day ingestion cap, local auth disabled; FunctionAppLogs export |
| `agentcraft-datacrafting-pdf-api-20260916` | Dedicated secret-free Entra API registration and service principal outside ARM group; included in guarded teardown |

All remain allocated for experiment replay/inspection. Dollar cost and ongoing charges are **unknown**, not
zero. Consumption analysis/execution, storage, private endpoint/DNS and log ingestion can charge; configured
caps are not a monetary ceiling. No production/shared workloads or subscription-wide grants were changed.
Legacy DI name remains only in the owner target/inventory/teardown support. It is stripped from runtime
configuration and no DI service or grant check is required to build, release or run CU. Prior operational
records remain unchanged. Filesystem retirement deletes no cloud resource, grant or Entra object.

## Recovery And Limits

`check-job --job-id UUID` reads a prior invocation before retry. Provider submission timeouts are deliberately
unconfirmed and not automatically resubmitted. Native complete results persist in private blob storage and locally.
`diagnose`, `logs`, `sync-functions`, and `restart` are bounded host troubleshooting actions. Restart/sync mutate
only this owned Function. Logs may be delayed or empty; empty telemetry proves no runtime success.

Initial decorator discovery returned zero Functions despite native deployment success. Explicit supported Python
configuration bindings resolved it. A local Azure Core `logging_enable` option leak was fixed and tested against
the real requests signature. The failed DI receipt remains in the external recovery archive; its original
[absent-job readback](./records/20260916T065059127550Z-job-readback.json) remains local. No hidden fallback.

No global quality winner, diagram-topology audit, repeated latency benchmark, live different-user token journey, browser
sign-in, load test or cancellation endpoint is claimed. No generative CU fields/summaries/figure descriptions or
embedding models were used. Figure image references remain native references; no figure binaries are downloaded.
The 900-second client polling bound can leave a provider job running; use its recorded ID, not blind resubmission.
Source PDFs/reference are read-only. Root deployment/README/specs and unrelated changes remain outside this lifecycle's writes.

## Current Evidence

- [48 offline tests passed](./records/20260916T080327723230Z-offline-verification.json), including retired-method
    refusal before HTTP calls/job writes, auth/ownership/integrity negatives and guarded local packaging.
    CU CLI help and owned documentation links passed. uv reports an inherited `VIRTUAL_ENV` mismatch and
    correctly uses the isolated CU project; no dependency environment is borrowed.
- [Local receipts verified](./records/20260916T075835824049Z-results-verification.json): two fixed CU runs,
    13 pages, 32 narrative facts and six row associations; native/receipt/text/Markdown frozen hashes match.
- Bicep compiled through `deploy.sh compile`; no template apply or cloud mutation was performed.
- [Local-only release ZIP](./records/20260916T080115020625Z-release-package.json): 7,226,867 bytes,
    SHA-256 `c1c0fcea746850d6bfc63199b82401383eab5ee5ec74e5aaf973e16b7ed17d23`.
    [Exact package check](./records/20260916T080138142316Z-package-check.json) imports three CU/status/health
    bindings from bundled dependencies and rejects retired bindings or DI runtime configuration.
- Existing live CU jobs remain readable: [Yallourn](./records/20260916T080123555221Z-job-readback.json) and
    [Murray](./records/20260916T080130272800Z-job-readback.json) returned HTTP 200, `Succeeded`, original source
    hashes and GA analyzer identity. These are metadata readbacks from the unchanged live app, not post-release acceptance.
- [Live build refusal](./records/20260916T075842254745Z-refusal.json) stopped before publication.
    [Current inventory](./records/20260916T080012371955Z-inspection.json) contains 15 resources, including
    `vnet-agentcraft-pdf-20260916-private-endpoints-nsg-eastus`,
    `vnet-agentcraft-pdf-20260916-functions-nsg-eastus`, and untagged Event Grid system topic
    `stdcpdf26091667255-b3c45fcb-ca1a-4930-8531-b4ff98f754b0`, outside the declared ownership set.
    Their adoption or removal requires operator review/authorization; the guard was not weakened.
- Live code release was not attempted. Anonymous/forged caller checks, retired-route 404/no-job proof,
    full native equality and replay/conflict acceptance remain unverified for a CU-only live release.
    Treat the old live DI routes as not retired until a separately unblocked release passes `verify`.
- No resource, grant or Entra object was deleted/revoked, no auth/ingress changed, and no paid analysis ran.
    The retired DI account remains allocated. Parent-owned canonical skill promotion is independent and may remain pending.

[Cleanup/recovery record](../content-understanding/evidence/selection/cleanup.json) owns exact filesystem counts,
archive digest, protected hashes and the deletion receipt. Old derived multi-method build packages are retained
inside the owned build directory; the active release pointer must reference the newly verified CU-only ZIP.

## Teardown

**Not authorized by filesystem cleanup and not executed.** Run only after separate explicit operator
approval for the exact resource group, its remaining DI allocation and dedicated Entra objects:

```bash
bash testbeds/datacrafting/deploy/deploy.sh teardown --confirm-group /subscriptions/67255afe-8670-4401-a1b8-df6ca63a3516/resourceGroups/rg-agentcraft-datacrafting-20260916
```

Checks frozen account, exact group/children ownership, locks, and exact tagged Entra object IDs before deletion.
Unknown resources/identities or locks refuse. Deletes only this group and its dedicated caller registration/service
principal; verifies absence. Group-scoped grants disappear with their resources. Local receipts and ARM deployment
history remain. Cloud deletion is unexecuted; confirmation/refusal/idempotence paths are tested offline.

## CU-Only Publication 2026-09-16

**Complete:** native deployment `bf404d06-0df2-42a1-bc39-7fbe9f72f588` completed at
`2026-09-16T08:14:22.8548237Z`; [post-release acceptance](./records/20260916T081528584957Z-acceptance.json)
passed. This dated update supersedes earlier live-publication blockers without rewriting their receipts.

The [archived release validator](./records/20260916-function-wrapper-retirement.json) separated exact reference-host dependencies from whole-group
lifecycle ownership. Every required site, MI, storage, CU, plan, VNet, private endpoint, private DNS zone/link
and log workspace must occur once with the exact ID, type, name and owner. Missing, mismatched, duplicate,
wrong-group or unowned dependencies refuse. Full inventory is retained before security readback.
`preflight`/`apply`/`teardown` still use the original whole-group unknown-resource refusal.

[Fresh inventory](./records/20260916T081435843128Z-reference-host-inventory.json) contains 15 resources:
10 validated dependencies and five observations outside this package release. The retired DI allocation,
managed endpoint NIC, two NSGs and Event Grid topic are explicitly `observed-not-owned/unmodified` for
release authority, with their actual owner tags retained. Both NSGs have exact owner
`agentcraft-datacrafting-20260916`; Event Grid has null tags, not ownership inferred from its name.
No observation grants adoption, mutation or deletion authority. Unknown additions still block whole-group teardown.

Executed only through this entry point, with the outer uv invocation now frozen as well:

| Command After `bash testbeds/datacrafting/deploy/deploy.sh` | Result / Receipt |
| --- | --- |
| `offline --test-pattern test_lifecycle.py` | [19 passed](./records/20260916T081130232036Z-offline-targeted-verification.json), immediately after the first edit |
| `offline` | [52 passed](./records/20260916T081147434529Z-offline-verification.json), isolated CU CLI and documentation checks passed |
| `verify-results` | [Two frozen receipts](./records/20260916T081229965557Z-results-verification.json), 13 pages, 32 narrative facts, six row associations |
| `build` | [Fresh security-backed package](./records/20260916T081228666098Z-release-package.json) |
| `check-package` | [Exact ZIP/source equality](./records/20260916T081244937270Z-package-check.json), three native bindings, no PDFs or DI configuration |
| `release` | [Native status 4, complete and active](./records/20260916T081424559060Z-publish-status.json), package only |
| `verify` | [Live acceptance passed](./records/20260916T081528584957Z-acceptance.json), no new analysis |

Package: `build/release-20260916T081227681014Z/function.zip`, 7,226,867 bytes,
SHA-256 `7708fcefddeee3698b52925243039a0b24fad65c6add17afea6da63dc5c2eccf`.
[Prior deployment readback](./records/20260916T081319361008Z-prior-publish-readback.json) confirmed the old
deployment succeeded before the new upload; no blind resubmission. Build/pending/published pointers are retained;
the pending ledger now names the confirmed successful deployment, not an unresolved publication.

[Live access](./records/20260916T081517711796Z-access-verification.json): exactly `ContentUnderstanding`,
`ExtractionStatus`, `ExtractionHealth`; authorized health 200; anonymous, forged headers/bearer,
host-file/unknown-path and valid wrong-audience token all 401. Invalid CU input and query-target injection
returned 403. DI Read/Layout, PyMuPDF and MarkItDown routes each returned 404 with job readback 404.
Both original persisted jobs returned 200 with complete native/text/Markdown equality. Completed Murray
replay returned 200 with original timestamps; conflicting Yallourn reuse returned 409 and left native data unchanged.
CU model deployments remain empty. No new paid analysis was submitted.

[Before](./records/20260916T081227678314Z-security-readback.json) and
[after](./records/20260916T081448096785Z-security-readback.json) local receipt comparison proved identical
resource IDs/types/names/tags, Entra settings, workload identity, storage/CU properties, required grants,
publishing policies, ingress, plan/subnet and Function configuration. No auth, ingress, role, NSG, Event Grid,
resource creation/deletion/retagging or Entra mutation occurred. No account switch or network workaround.

At `2026-09-16T08:17:10.176Z`, all 340 protected files (11,500,690 logical bytes), recovery archive and
both manifests matched their frozen hashes. User project/lock edits, source/reference, retained CU outputs
and old deployment receipts are preserved. Exact preservation/status is appended to the
[cleanup record](../content-understanding/evidence/selection/cleanup.json).
No process was left running and no cleanup, agents or commits were created by this publication.

**Remaining:** DI S0 and its historical grant were not removed or revoked; DI remains allocated, outside
CU runtime requirements. Grant presence was not freshly queried for this release. Dollar cost remains unknown.
No publication blocker remains. Browser sign-in, live different-user/wrong-tenant/expired-token journeys and
load/cost testing remain unverified. Parent skill/catalogues/root README/specs were not changed.