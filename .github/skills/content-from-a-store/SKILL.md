---
name: content-from-a-store
description: "Use when operator-published, read-mostly web content must update without rebuilding a container image: managed identity, immutable fallback content, ETag revalidation, read-back verification."
---

# Immutable shell, mutable content

This is a guidance skill with an offline-tested Python example, not a hosted content service.
Commands below are ingredients for the consuming project's authorized `deploy/deploy.sh`, not
installation actions. Source-era timings are illustrative; measure the target environment.

**Problem.** Rebuilding an image to change a paragraph costs 45–90s plus a revision rollout.
**Fix.** Deploy the renderer once, keep content in a store. Publish becomes a data write (~2s).

```
image  = server + gate + fallback copy of content   (changes rarely)
store  = content                                    (changes constantly)
publish = write to store + invalidate cache
```

## Decision table

| Store | Auth | Publish | Query | Use when |
| --- | --- | --- | --- | --- |
| **Blob** | Managed identity, RBAC | `az storage blob upload-batch` ~2s | none | Default. Documents, assets, JSON. |
| **Cosmos serverless** | Managed identity, RBAC | SDK write | rich | Content needs filtering/joins per request. |
| **Table Storage** | Managed identity | SDK write | key+range | Many small records, no keys, cheapest. |
| **App Configuration** | Managed identity | `az appconfig kv set` | key | Config/flags only. 10KB limit. Not documents. |
| Azure Files mount | **Shared key only** | file copy, no fetch code | n/a | Only where policy permits shared key. |
| Git raw fetch | PAT (a secret) | `git push` | none | Avoid. Adds a secret and a third party. |

Blob wins: no keys, negligible per-request cost, ETag revalidation built in, content already files.

## Shape

1. **Boot**: read `CONTENT_URL` + identity. Baked-in copy is last-known-good.
2. **Serve**: cache older than TTL → revalidate with `If-None-Match`. `304` → serve cache, bump
   timestamp. `200` → replace cache. Error → serve last good, log once.
3. **Publish**: upload, then signed `POST /admin/purge` drops TTL to zero.

TTL 10s publishes near-instantly without hammering the store; purge makes it exact.

## Fetch with managed identity, no SDK

```python
import json
import os, time, urllib.request

_tok = {"v": "", "exp": 0.0}

def _token() -> str:
    if _tok["exp"] - 60 > time.time():
        return _tok["v"]
    ep, hdr = os.environ["IDENTITY_ENDPOINT"], os.environ["IDENTITY_HEADER"]
    cid = os.environ["AZURE_CLIENT_ID"]                       # user-assigned identity
    url = f"{ep}?api-version=2019-08-01&resource=https://storage.azure.com/&client_id={cid}"
    req = urllib.request.Request(url, headers={"X-IDENTITY-HEADER": hdr})
    with urllib.request.urlopen(req, timeout=5) as r:
        data = json.load(r)
    _tok.update(v=data["access_token"], exp=float(data["expires_on"]))
    return _tok["v"]

def fetch(url: str, etag: str = "") -> tuple[bytes | None, str]:
    """Returns (None, etag) on 304."""
    h = {"Authorization": f"Bearer {_token()}",
         "x-ms-version": "2021-08-06"}
    if etag:
        h["If-None-Match"] = etag
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=5) as r:
            return r.read(), r.headers.get("ETag", "")
    except urllib.error.HTTPError as e:
        if e.code == 304:
            return None, etag
        raise
```

On VM/AKS the token endpoint is `http://169.254.169.254/metadata/identity/oauth2/token` with header
`Metadata: true`; everything else is identical.

## Provision

```bash
az storage account create -g $RG -n $SA -l $LOC --kind StorageV2 --sku Standard_LRS \
  --allow-blob-public-access false --min-tls-version TLS1_2
az storage container create --account-name $SA -n content --auth-mode login
az role assignment create --assignee-object-id $(az identity show -g $RG -n $ID --query principalId -o tsv) \
  --assignee-principal-type ServicePrincipal --role "Storage Blob Data Reader" \
  --scope $(az storage account show -g $RG -n $SA --query id -o tsv)
az containerapp update -g $RG -n $APP --set-env-vars \
  CONTENT_URL="https://$SA.blob.core.windows.net/content" AZURE_CLIENT_ID=$(az identity show -g $RG -n $ID --query clientId -o tsv)
```

Publish:

```bash
az storage blob upload-batch --account-name $SA -d content -s ./site --auth-mode login --overwrite
```

Writer gets `Storage Blob Data Contributor`; the app gets **Reader** only. Separate identities.

## Rules

- **Reader-only at runtime.** A compromised renderer must not rewrite what it serves.
- **Ship a fallback copy in the image.** Store outage degrades to stale, not to a 500.
- **Content is data, never code.** No `eval`, no template execution from the store. CSP stays strict
  (`script-src 'self'`) so injected markup cannot execute.
- **Escape on render** unless the store is operator-authored only. State which it is.
- **Cache-Control: no-store, private** on confidential responses; store headers do not reach the
  browser.
- **Read back after write.** GET after publish, compare ETag or content hash.
- **One writer.** Concurrent publishes need `If-Match` or a lease; otherwise last write wins
  silently.

## Failure modes seen

| Symptom | Cause | Fix |
| --- | --- | --- |
| `KeyBasedAuthenticationNotPermitted` | policy forces `allowSharedKeyAccess=false` | use `--auth-mode login`; abandon Azure Files mounts |
| Blob 403 from app, works from CLI | RBAC not propagated | wait 5 min; confirm role on the *account* scope |
| Data plane unreachable, `publicNetworkAccess=Disabled` | Azure Policy `Modify` | exemption at MG scope, or VNet-integrate the app + private endpoint |
| Content updates invisible | browser cache, not server | `no-store`, and verify with a cache-busting query |
| Stale content on one replica only | per-replica cache, no purge fan-out | purge must hit all replicas, or keep TTL short and accept skew |

## Verify before trusting it

From this skill's directory, run the snippet against injected offline responses:

```bash
python3 tests/selftest.py
```

This checks the example, not Azure permissions or a deployed content cache. Live checks
belong in the consuming project's authorized `deploy/deploy.sh verify` sequence:

```bash
az storage blob upload --account-name $SA -c content -n probe.txt --data "$(date +%s)" --auth-mode login --overwrite
curl -s $APP/probe.txt          # within TTL, must show the new value
az containerapp revision restart ...   # cold start must still serve (fallback path works)
```

## When this technique does not apply

Content that is transactional, per-user, or app-written is a database with an application, not this
pattern. This is for **operator-published, read-mostly** content.

When tenant policy blocks every data plane — shared key and public network access both — no
near-instant path exists. Split the image instead so publishes copy one layer: 93s → ~46s.
The optional `deploy-container-apps` skill describes that deployment workflow; this skill does
not read its files or require it to be installed.