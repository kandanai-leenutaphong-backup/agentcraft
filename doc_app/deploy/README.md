# Deploying the site

## Current Status

Live: **https://ca-agentcraft-writeup.wonderfulmoss-6cbdac9f.eastus2.azurecontainerapps.io**.
Only the writeup and required hosting resources are deployed in `rg-agentcraft-testing`.
The root [writeup deployment runbook](../../deploy/README.md#writeup-deployment) owns the
current CLI, configuration, native ID-token-only sign-in limitation, and live verification.
Human sign-in is pinned to the Microsoft corporate tenant; interactive sign-in/consent has
not yet been completed. Local and signed-browser checks pass.

The former `rg-singtel-ticket-poc` deployment and all resources in the group were deleted
under the user's explicit authorization and independently verified absent on 2026-09-16. The root
[deployment runbook](../../deploy/README.md#legacy-singtel-retirement) owns execution and
read-back evidence. Its initially empty replacement group now hosts the writeup above.
Keep working locally through [the app setup](../README.md).

The `existing-writeup` environment and commands below are **historical, not active**.
The imported CLI refuses every command against that environment before any Azure call,
including `infra`, so it cannot accidentally recreate the retired group. Releases now use
the root `deploy/deploy.sh writeup` entry point.
Entra tenant-level registrations and the operator's local signing key were not deleted.

Former URL: **https://ca-writeup-agent-loop.kindsmoke-35b5bc1b.eastus2.azurecontainerapps.io**
Historical governing issue: han-microsoft/dev-capability#4

## Import-Time Target (2026-09-16)

Source and deployment tooling now live under `doc_app/`. Read-only ARM inspection confirmed
the existing deployment in `rg-singtel-ticket-poc`; no RG name matched `contoso` in the attached
subscription. No cloud resources, images, credentials, grants, or auth settings were changed.

- Subscription: `67255afe-8670-4401-a1b8-df6ca63a3516` (`ME-M365x21900035-hchoong-1`).
- Resource tenant: `c79ab2bb-79cb-47f1-b4da-b6852fe45ff7`; cloud: `AzureCloud`.
- Location: `eastus2`; shared environment: `cae-singtel-ticket-poc`.
- Ready revision: `ca-writeup-agent-loop--0000038`; ARM running status: `Running`.
- Entra client ID: `3fd722c8-ff1a-4978-81db-a97bcdb107a1`; issuer tenant:
  `72f988bf-86f1-41af-91ab-2d7cd011db47`. The existing secret reference is
  `aad-client-secret`; its value was not retrieved.

The committed [environment target](env/existing-writeup.env) is the CLI configuration authority.
The [dated read-back record](records/import-2026-09-16.json) preserves observations and limitations.
The CLI rejects a mismatched active subscription, tenant, or cloud; it does not switch accounts or
install Azure extensions. It selects the named registry, never the first registry in the shared RG.

## Historical Operator Sequence

Start with the [local setup and build](../README.md#local-development). Azure CLI must already be
signed into the resource tenant and the subscription above, with the `containerapp` extension
installed. Signed verification requires `cryptography` and the existing operator key at
`~/.writeup/dev_signing_key`; no command below creates a key or reads a secret value.

From the repository root:

```bash
cd doc_app
./deploy/deploy.sh -e existing-writeup verify
```

Expected: health `200`, anonymous browser `302`, anonymous document and asset `401`, and signed
request admitted when the existing key is available. A failed expectation now exits nonzero.
Missing key is explicitly reported as unverified. On a target mismatch, select the documented
account in your own CLI session; on `401` for the signed request, check existing key ownership and
the deployed public verifier. Do not create a key, rotate credentials, or change auth to pass a check.

Only after separate release authorization:

```bash
./deploy/deploy.sh -e existing-writeup publish
./deploy/deploy.sh -e existing-writeup verify
```

`publish` stages the kiosk, builds the site, builds a uniquely tagged content image in the named ACR,
then updates the existing Container App. On a build failure, no rollout occurs. On a rollout failure,
inspect the ready revision and image before retrying. `base` rebuilds `writeup-base:1` and requires
separate approval too. The source import lacked `deploy/app/requirements.txt`; its restored manifest
declares the server's actual imports. Those local dependencies are not a claim about the packages
installed in the currently deployed image.

`infra`, `all`, `auth`, `devkey`, and `revoke` are retained legacy operations, not migration steps.
They need a reviewed resource/access plan before use. In particular, the inherited auth bootstrap
creates/rotates an Entra client secret and is not an idempotent native-auth migration. No such
operation was exercised here. Initial deployment still needs the exposure-window review below.
Both `teardown` and `destroy` now refuse: the RG and environment are shared. Resource-specific
cleanup needs an explicit ownership inventory and separate authorization; never delete the RG.

## Historical Deployment Notes

Originally deployed 2026-08-21 into the same resource group and Container Apps environment.
Historical timings, policy observations and interactive-sign-in limitations below are retained;
they were not re-measured during import.

## What runs

| Piece | Detail |
| --- | --- |
| Container App | `ca-writeup-agent-loop`, external ingress `:8080`, scale 0–2 |
| Image (read back 2026-09-16) | `acrwriteupagentloopi3kym645cr2eg.azurecr.io/writeup:20260824150321` |
| Registry | ACR Basic, **admin user disabled**, anonymous pull disabled |
| Pull identity | `id-writeup-agent-loop` (user-assigned) with AcrPull — no registry credentials exist |
| Environment | reused, so no second Log Analytics workspace was created |
| Server | Starlette + uvicorn serving static files, with the auth gate in-process |

## Two ways in

Both enforced by the app process, not by the platform. `main.bicep` provisions no auth; it is
applied post-deploy because a client secret must never be written into a template.

### 1. Entra (how people read it)

Container Apps built-in auth runs the OIDC flow at `/.auth/login/aad` and injects
`X-MS-CLIENT-PRINCIPAL-*`. Platform action is **AllowAnonymous** so requests still reach the app —
the app refuses anonymous readers itself. That is what makes path 2 possible at all; with the
platform refusing at the edge, a signed request would never reach the container.

Issuer is pinned to `72f988bf-…` (Microsoft corp), so only corporate accounts pass token
validation even though the registration is multi-tenant.

### 2. Ed25519 signed requests (how the agent pilots it)

Wire shape copied from gridiq `AUTODEV.md` §4.2, so one signing scheme works against both systems.
The server holds **only the public verifier**; the private key never leaves the operator machine
(`~/.writeup/dev_signing_key`, mode 0600). Remove `DEV_PUBLIC_KEY_ED25519` and the path ceases to
exist.

| Header | Contents |
| --- | --- |
| `X-Request-Timestamp` | RFC 3339 UTC. Rejected beyond 5 minutes of skew. |
| `X-Request-Signature` | base64(Ed25519.sign(`METHOD\npath?query\nts\nslug\nsha256_hex(body)`)) |
| `X-Request-Context` | optional identity slug |

```bash
python3 deploy/dev_sign.py init                      # once; prints the public verifier
./deploy/deploy.sh devkey                            # push the verifier to Azure
export APP_URL="https://ca-writeup-agent-loop.kindsmoke-35b5bc1b.eastus2.azurecontainerapps.io"
python3 deploy/dev_sign.py request GET /index.html   # signed fetch
python3 deploy/dev_sign.py session --minutes 30      # cookie, for driving a real browser
```

A browser loads CSS, JS and images as separate requests, each of which would need its own
signature. `session` mints a short-lived cookie signed over `SESSION\n<expiry>` instead. It is
stateless — verified against the same public key, bounded by an expiry inside the signed string —
so it survives replica scaling and needs no server-side session store.

## Rebuild and redeploy

```bash
cd doc_app
./deploy/deploy.sh -e existing-writeup publish
./deploy/deploy.sh -e existing-writeup verify
```

`base` rebuilds the dependency image and is only needed when `requirements.txt` changes.

### How fast can content changes go live?

Measured on this deployment:

| Loop | Time |
| --- | --- |
| Local preview (`python3 -m http.server`, edit and refresh) | instant |
| `publish` — single-layer content build on a cached base | **~46-60s** |
| Naive rebuild (deps reinstalled every time) | 93s |

The split into `Dockerfile.base` + `Dockerfile` is what removed half the time: dependencies are
installed once into `writeup-base`, and a routine publish copies one thin layer. Of what remains,
roughly 28s is the ACR build and 18s is the Container Apps rollout.

**Near-instant publishing was attempted and is not possible in this subscription.** Two approaches
were tried and both were blocked by tenant Azure Policy using the `Modify` effect — the ARM write
returns success and the setting silently reverts:

- *Azure Files volume mount*, which would let a file copy update the site with no build at all,
  needs shared-key auth (Container Apps does not support identity-based access to file shares).
  `allowSharedKeyAccess` is forced to `false`.
- *Blob container read via managed identity* needs a reachable data plane.
  `publicNetworkAccess` is forced to `Disabled`, and the Container Apps environment in use is not
  VNet-integrated, so a private endpoint would not help it either.

Unblocking either one needs a policy exemption (`az policy exemption create --exemption-category
Waiver`, requires Owner/UAA at the management group the assignment lives on) or moving the app into
the VNet-integrated environment `cae-singtel-evidence` with a private endpoint. Until then, author
against the local preview and treat `publish` as the release step.

The historical whole-resource-group teardown command is disabled in this copy. The resource group
is **shared** with the singtel POC; even individual-resource removal needs separate scoped approval.

## Historical Live Verification (Before Import)

| Check | Result |
| --- | --- |
| Anonymous browser request | 302 to `/.auth/login/aad` |
| Anonymous API-style request | 401, zero bytes |
| Anonymous asset request | 401, zero bytes |
| Correctly signed request | 200 with content |
| Signature replayed on a different path | 401 |
| Signature replayed on the same path | 401 (replay cache) |
| Forged session cookie | 401 |
| Valid session cookie | 200 |
| Corp authorize endpoint | returns a sign-in page, no `AADSTS` error |
| Browser render | all 3 figures load, hover cards and lightbox work |
| Forged `X-MS-CLIENT-PRINCIPAL-ID` header | 401 — the platform strips inbound principal headers |
| Expired session cookie | 401 |
| `/.auth/logout` | 200 |

Sign-out is a link in the masthead to `/.auth/logout?post_logout_redirect_uri=%2F`, which clears the
auth cookie, drops the token from the store, and signs out server-side at the identity provider.

## Decisions and their reasons

- **The gate is in the app, not the platform.** EasyAuth alone would have been simpler and needs no
  application code, and that is what was built first. It was replaced because it refuses at the
  edge, which makes signed agent access impossible. The tradeoff: a bug in `server.py` is now what
  stands between the document and the internet, so the gate defaults to deny and every path is
  tested above.
- **The registration lives in the demo tenant, not corp.** Creating it in corp tenant
  `72f988bf-…` was attempted and blocked: `AADSTS530084`, conditional-access token protection,
  which requires an interactive device-bound sign-in. The registration was therefore created as
  multi-tenant in `c79ab2bb-…` — the same pattern the accelerator's own `pathfinderiq`
  registration uses — with the **issuer pinned to corp**, which restores the corp-only restriction.
- **Ingress was disabled mid-deploy.** Between the first image rollout and auth being configured,
  the site served the document publicly. Ingress was disabled for that window and re-enabled once
  auth was in place.

## Not verified

**No corporate user has completed an interactive sign-in.** The authorize endpoint accepts the
application and returns a sign-in page, but a multi-tenant app being used in a tenant that does not
own it may prompt for consent on first use, and corp policy may route that to an administrator.
The first Microsoft employee to open the link will find out. If they are blocked, the fix is an
admin consent grant, or re-registering the app in corp tenant from a session that satisfies the
token-protection policy.
