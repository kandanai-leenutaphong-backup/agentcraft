# Operator-Published Content

Use installed azdata v4 (`azdata[blobs]` for Blob Storage), not an inline identity
endpoint/token cache or urllib client. The [data guide](azure-data-connectors.md)
owns public requests, results, errors, bounds and resource lifetime. This is a
host composition pattern, not another content server or cache package.

## Ownership And Flow

Keep the renderer, auth gate and immutable fallback content in the image. Publish
operator-authored data separately. Runtime identity receives only the required
read permission; an independently authorized publisher holds write permission.
No installation or skill load provisions storage, obtains secrets or grants roles.

Read explicit store coordinates and identity once at the composition root. Use
bounded `ReadRequest` through a target/host-bound `connect("blobs", ...)`. Keep
content bytes and returned version as host cache state. Validate new data before
replacing last-known-good content; content never names executable code. Escape
untrusted values and preserve strict CSP and caller authorization on fallback too.

ETag/version checks, TTL, invalidation, atomic cache replacement and immutable
fallback selection are host-owned. **V4 does not expose request-level
`If-None-Match`/304 conditional reads.** Compare returned versions where useful,
but do not claim a skipped download or recreate the retired token/fetch engine.
A future conditional-read addition belongs to the canonical data owner, not here.

Authentication/authorization failure must remain a refusal, never a refreshed or
cached-content success. Do not turn 403 into an unchanged 304. An authorized host
may separately render its known-safe fallback on a store outage, while retaining
the failure/freshness state; no cache path may bypass its auth gate or cross owners.

Publish through the host's authorized deployment/operator entry point. Read back
the exact bytes or requested content/hash and version after a write. A signed
purge endpoint, if a host needs one, calls the same cache owner and requires
explicit authorization/replay protection through `signed_dev_access`; this guide
creates no endpoint, signing credential or admin grant.

## Concurrency, Errors And Limits

Use a single publication owner, conditional native writes or an explicitly owned
lease where supported. Never silently accept last-writer-wins as a concurrency
guarantee. A purge of one replica is not global invalidation; choose bounded TTL
skew, a shared invalidation mechanism or fan-out and verify that chosen contract.

V4 returns standard results, including denied/failed/partial/pending/unknown;
acceptance is not persistence. `ConfigurationError` is structural refusal, not
service outage. Do not log content, tokens or raw provider errors. Keep confidential
HTTP responses `Cache-Control: no-store, private`; do not forward store cache headers
unchecked to browsers. Use cache-busting/wire checks to distinguish browser caching.

Default data limits are 30 seconds, 100 items, 1 MiB input/output and one native
attempt. Hosts choose finite cache TTL and fallback age explicitly; old timing
examples are not measured guarantees. Use async context management/`aclose()`;
the connector closes owned clients, while the host closes borrowed credentials.

## Retained Operational Findings

- Prefer Blob for file-like documents/assets; use Cosmos or Table when their
  supported query/key model is required. Configuration/flags are not documents.
- Shared-key prohibition is not solved with an account key, SAS or Azure Files
  mount. Select authorized identity/native access instead.
- A workload 403 may be identity, exact role scope, propagation, service auth mode
  or network policy. Diagnose before changing anything; an arbitrary wait is not proof.
- A policy-reverted `publicNetworkAccess` setting needs an authorized governance
  or network design decision, not another write or secret fallback.
- No reachable store means this pattern is unavailable. A separately authorized
  image-layer release remains a host option; no old elapsed-time claim transfers.

## Retirement And Evidence

The handwritten `IDENTITY_ENDPOINT`/`IDENTITY_HEADER` token client and fetch
implementation were removed from the native skill, along with its executable
snippet selftest. Native Azure Identity owns refresh and canonical data access
owns bounded reads/refusals. No obsolete source was moved under docs.
[Exact retired file and original guide hash](content-from-a-store-retirement.json)
identify external recovery; the native name/triggers and MIT notice remain.

```bash
PYTHONPATH=libraries/azure-data-connectors/src python -B -m unittest discover \
  -s libraries/azure-data-connectors/tests -t libraries/azure-data-connectors \
  -p test_storage.py -q
```

Existing Storage tests cover canonical bytes, limits, non-overwrite and mutation
conditions. Host cache/ETag/304 behavior, multi-replica invalidation, deployed
fallback/auth and live permissions are not proved by these tests. No cloud,
service/model call, credential generation, grant or publication ran here.