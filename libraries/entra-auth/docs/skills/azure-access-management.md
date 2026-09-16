# Azure Access And Identity

One native task entry; existing owners only. Install `entra-auth` and import
`entra_auth` for strict token, PKCE and store mechanisms. Use native administrative
procedures in [the workflow guide](native-access-workflows.md). There is no new
access-management package. `azaccess`, `entraauth`, the skill-local `entra_auth`
copy, workflow planner, deployment-helper runtime and MCP adapter are retired.

The [package](../../README.md) and [auth contract](../../src/entra_auth/README.md)
own runtime behavior. Historical application imports in that contract are provenance;
the public installed import is `entra_auth`. No installation enables caller access,
acquires credentials, grants roles or creates resources.

## Authentication Is Not Authorization

Distinguish application caller, administrative operator and workload managed
identity. Validate incoming API tokens for the API's audience; clients treat tokens
as opaque. MSAL/Azure Identity acquire tokens; neither is automatically an incoming
API validator. Map verified identity once in the host, then authorize routes,
records and listing filters. Another owner's record stays hidden; shared records
do not become writable because authentication succeeded.

`EntraAuthConfig`, `TokenValidator`, `VerifiedToken` and `AuthError` are public.
Configuration is immutable, explicitly single-tenant and has no disabled mode.
`common`, `organizations` and `consumers` are not accepted trust boundaries.
`VerifiedToken` is reduced verified evidence, not an application principal or grant.
The retired `entraauth` disabled branch and permissive environment parsing are not
retained or emulated. Never bypass auth to obtain a passing check.

Token checks retain: 16 KiB input cap; fixed RS256 allowlist; trusted JWKS key;
signature, audience, expiry and not-before; exact tenant issuer and signing-key
issuer; tenant claim; issued-at/required claims; required user scope or explicitly
allowed service principal plus role. Unknown/stale/unavailable keys refuse.
Default maximum stale JWKS age is six hours, after which refresh failure closes
access. `AuthError.reason` is a code and `public_message` a constant; tokens,
provider exceptions and key values must not enter output or logs.

## Browser And Session Boundary

`new_flow`, `authorize_url`, `logout_url`, session identifiers/digests and
`RecordStore` mechanisms remain canonical. Flow state, nonce and PKCE verifier
are server-generated. Redirect configuration comes from the host, not request
parameters. The host owns callback routes, code exchange, secure cookies, CSRF,
session revocation, caller mapping and its common authorization decision.

Use the correct web versus SPA redirect registration. A SPA authorization code
cannot be assumed redeemable server-side. Keep verifier/state values out of web
storage, URLs, receipts and logs except the exact protocol exchange that requires
them. Consume flow/replay claims atomically and bind them to the initiating browser.
Test wrong state, replay, expiry, unsafe cross-origin requests and revoked cookies.

Expiry is enforced on read; purging is separate housekeeping. Azure Table has no
server-side TTL guarantee. Shared stores and their consistency/availability are
host-selected. `RecordStoreUnavailable` is not an empty store or implicit access.
Refresh tokens are not handled here; session lifetime cannot outlive its token or
the host ceiling. The host owns resources, store lifecycle and secret retention.

## Container Apps And Signed Callers

For a new private frontend, prefer tenant-pinned native Easy Auth with
`RequireAuthentication` when requirements fit. A supported provider-token headless
caller does not require anonymous ingress. Protect assets, scripts, unknown routes
and APIs, not only the entry page. Keep ingress closed until the gate is configured
and negatively verified. Sensitive responses and refusals are private/no-store.

Custom app-verified signing needs a separately reviewed enforcement/routing choice.
`AllowAnonymous` only defers enforcement and is acceptable only with a proven
in-process deny gate. Use installed `signed_dev_access`, not another verifier.
Preserve signed method, raw path/query, body and signature headers across proxies.
Process-local replay caches are not replica-wide defenses.

Trust forwarded `X-MS-CLIENT-PRINCIPAL-*` only after proving the edge strips forged
headers and no path bypasses that edge. Use cache-busting browser requests and wire
checks for logout/anonymous testing; cached protected HTML is not gate evidence.
An API redirect ending in login HTML is not an API 401. Where a provider credential
is necessary, reference an authorized Key Vault secret; never fetch its value into
a shell variable, repository, image or log.

## Retirement And Verification

[Exact retired paths and preserved records](azure-access-management-retirement.json).
Historical consolidation/source mapping, identity provenance/gotchas and SDK
comparison notes remain under `history/`. They describe old evidence, not installable
helpers, live acceptance, an approval service or current native capability promises.
The canonical library and native skill retain the Microsoft MIT notice.

```bash
PYTHONPATH=libraries/entra-auth/src python -B -m pytest libraries/entra-auth/tests \
  -q --import-mode=importlib -p no:cacheprovider
```

Existing tests prove token/configuration refusals, PKCE/state/store behavior and
cleanup against synthetic inputs. They do not prove host record routes, native
Easy Auth sessions, live Table Storage, tenant permissions or deployed proxy gates.
Those acceptance paths remain with the host/parent integration, as do discovery,
old `azaccess_*` MCP registrations and shared metadata. No cloud call, grant,
write, deployment or cleanup was performed by this retirement.