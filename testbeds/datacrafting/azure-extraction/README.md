# Azure Extraction Shared Contract

> Current status, 2026-09-16: **CU-only host published and verified.**
> [Fresh publication evidence](../deploy/README.md#cu-only-publication-2026-09-16) supersedes the
> earlier blocked-status text retained below; no historical receipt was rewritten.

One implementation owner for the retained Content Understanding reference host.
No dependency on retired methods, comparison code, the promoted skill, root deployment,
shared reference cache, or application libraries.

CU-only source and exact local package are verified. Live publication is blocked by
undeclared group resources; the previous live app has not been replaced. See the
[current runbook evidence](../deploy/README.md#current-evidence).

## Capability Catalogue

| Outcome | Owner / Public Surface | Callers | Dependencies | Verification |
| --- | --- | --- | --- | --- |
| Immutable two-PDF and target validation | `azure_extraction.contracts` | Function, CLI, receipt verifier | Python standard library | `deploy.sh offline` |
| Entra JWT and explicit caller authorization | `azure_extraction.auth.JwtGate` | Function handler | PyJWT/cryptography, pinned tenant JWKS | `deploy.sh offline`, `deploy.sh verify` |
| Native CU submission and retrieval | `azure_extraction.provider.NativeProvider` | `ExtractionJobs` only, inside Azure | Azure Core, injected managed identity; GA `2025-11-01/prebuilt-layout` only | fake HTTP and retired-method refusal tests; two frozen CU receipts |
| Durable idempotent extraction jobs | `azure_extraction.jobs.ExtractionJobs` | Function handler | native provider, blob job store | offline ownership/failure tests, live replay/refusal |
| Function-only CLI and artifact receipts | `azure_extraction.client.run_cli` | CU adapter only | Azure CLI OAuth, Azure Core bounded LRO | isolated uv locks, receipt and persisted-result verification |
| Cloud lifecycle | `../deploy/deploy.sh` | operator | Bicep, Azure CLI, locked shared Python environment | native preflight/what-if, security readback, live acceptance |

Entries are implemented; current verification evidence lives in the deployment runbook.
Configuration enters through the deployment edge;
the Function receives a non-secret frozen configuration and stripped input manifest. Its sole environment
read is the injected workload managed-identity client ID. The CLI resolves the immutable source paths and
the deployment-generated runtime target, never a request-provided service endpoint.

## Function API

Base: `https://func-agentcraft-pdf-20260916.azurewebsites.net/api`.

| Method | Route | Input | Result |
| --- | --- | --- | --- |
| GET | `/health` | Entra bearer token | methods, caller tenant/object ID, workload client ID |
| POST | `/extract/content-understanding/{document_id}/{job_id}` | `application/pdf`, exact approved bytes | 202 + Function `Operation-Location`, or existing completed result |
| GET | `/jobs/{job_id}` | same authorized caller | running state or complete native/text/Markdown output |

`document_id` is `yallourn` or `murray`. `job_id` is a canonical UUID and the idempotency key.
No query options, arbitrary URL inputs, analyzers, output paths, or credential values are accepted.
The source manifest limits requests to 586,748 or 623,685 immutable bytes; the server also caps input at 1 MB.

Job responses contain `id`, `method`, `document_id`, `sha256`, `status`, UTC timestamps, provider versions,
installed package versions and bounded errors. Success adds complete `native`, unmodified `text`, optional
`markdown`, and observed `pages`. Client receipts follow [the result contract](../RESULT_CONTRACT.md) exactly;
invocation and Function timing metadata live beside the receipt rather than extending its schema.

401: invalid/missing token. 403: tenant/principal/client/scope/input/target refusal. 404: missing or other-owner
job or retired route. 409: idempotency conflict. 502: bounded native-provider HTTP failure. 500: internal failure, never empty success.
A provider terminal failure returns a failed job with its native evidence. A timeout during submission becomes
unconfirmed state and is never automatically resubmitted. Read the recorded job ID before choosing recovery.

## Security And Persistence

- Platform Easy Auth requires Entra on all paths, including unknown paths and static files; Return401,
  no exclusions, no token store, exact tenant, operator object ID and Azure CLI application allowlists.
- The handler independently validates RS256 signature, issuer, API audience, expiry, not-before, tenant,
  principal, Azure CLI client and delegated `access_as_user` scope. No forwarded principal header is trusted.
- Native HTTP bindings use `authLevel=anonymous` only to avoid function keys. They are not anonymously
  reachable: platform Entra and application JWT authorization remain mandatory and are tested live.
- Workload MI is distinct from caller OAuth. Runtime requires resource-scoped Blob Data Owner on storage
  and Cognitive Services User on CU. Storage is private/keyless and CU disables local/key auth.
  The historical DI account/grant remain allocated but are not runtime dependencies; retirement is not revocation.
- State creation is insert-only; state updates use ETags. Complete native JSON is write-once and compared on
  races, then read back through the Function. Provider POSTs are not automatically retried. SDK polling is
  bounded to 900 seconds; individual native calls have connection/read bounds. No shell polling loop.
- Authenticated responses carry `Cache-Control: no-store, private`. The artifact store contains approved
  document-derived results, not source PDF duplicates. Request bodies and tokens are not logged.

## Runtime And Limits

One named Python configuration-based extraction Function and health/status share one handler:
`ContentUnderstanding`, `ExtractionStatus`, `ExtractionHealth`. Retired methods fail before provider
calls or job creation and have no bindings. The initial decorator package deployed but discovered zero Functions; explicit native
bindings produced the verified runtime. This is a hosting adaptation, not a local-service fallback.

Local Python 3.12.3; live Python 3.12.13. Azure Core 1.41.0, Identity 1.25.3, Functions 1.25.0,
Storage Blob 12.30.1, PyJWT 2.14.0. [uv.lock](./uv.lock) pins the host dependencies; the CU adapter has its own lock.
The current [pyproject.toml](./pyproject.toml) remains a non-package uv project without a build backend.

CU uses GA `2025-11-01/prebuilt-layout`; no language/embedding model deployments, generated
summaries, generative fields or figure descriptions. Markdown image references remain provider references;
figure images are not downloaded. Output counts are not quality scores. The retained source review covers
32 narrative facts and six row associations on two PDFs, not general accuracy. No
load test, browser sign-in, other-user live token journey or cancellation endpoint is claimed.

Replay, resources, exact evidence and manual teardown: [deployment runbook](../deploy/README.md).

## Publication Update 2026-09-16

[Live acceptance](../deploy/records/20260916T081528584957Z-acceptance.json) confirms exactly three CU/status/health
bindings, both persisted native/text/Markdown outputs unchanged, mandatory Entra refusals, retired routes
404 with no jobs, completed replay 200 and conflicting-document 409. No new paid analysis.
Deployment `bf404d06-0df2-42a1-bc39-7fbe9f72f588` changed only the existing Function package.

Release readback validates all 10 exact owned host dependencies and retains the full 15-resource inventory;
out-of-scope additions are observed unmodified, never adopted or authorized for deletion. Whole-group
provisioning/teardown refusal remains unchanged. The runner uses `uv --frozen`; project and lock hashes
remain unchanged. Lifecycle tests: 19 passed; full offline suite: 52 passed. DI stays allocated, not required.