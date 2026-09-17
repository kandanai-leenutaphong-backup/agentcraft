# `entra_auth`

Microsoft Entra ID access-token validation and browser sign-in, with no knowledge of the
application that uses it.

Two decisions, kept apart: **who is calling** — token validation — and **what may they see**,
which belongs to the consumer and is not modelled here. Collapsing them is how a valid token
from one tenant ends up reading another tenant's data.

## Public surface

Everything reachable is exported from `__init__.py`. Nothing else is API.

| Name | What it is |
| --- | --- |
| `EntraAuthConfig` | The trust boundary as data: tenant, audience, claim rules, cache intervals. Frozen at construction |
| `EntraConfigurationError` | Raised when a configuration cannot describe a safe boundary |
| `TokenValidator` | The one place a bearer token becomes a believed identity |
| `VerifiedToken` | What a valid token proves. **Not** an identity type |
| `AuthError` | Every refusal. `.reason` is a code, `.public_message` is a constant |
| `JWKSCache`, `build_rsa_pem`, `default_fetcher`, `Fetcher` | The signing keys and their refresh policy |
| `new_flow`, `SignInFlow`, `authorize_url`, `logout_url` | Authorization Code + PKCE, server-side |
| `new_session_id`, `session_lookup_key`, `constant_time_equals` | Opaque session identifiers and their digests |
| `RecordStore`, `InProcessRecordStore`, `AzureTableRecordStore`, `RecordStoreUnavailable` | The shared expiring store flows and sessions live in |
| `SessionService` | Atomic flow claims and token-bounded sessions over host-serialized string maps |
| `extract_bearer`, `first_header` | Case-insensitive header reading |
| `GUID_PATTERN` | Shared compiled GUID syntax; callers retain their validation errors and policy |
| `KIND_USER`, `KIND_SERVICE`, `ALLOWED_ALGORITHMS`, `MAX_TOKEN_BYTES`, the `DEFAULT_*` intervals | Constants |

Dependencies: `pyjwt`, `cryptography`, and the standard library. No web framework is imported.
`AzureTableRecordStore` imports the Azure SDK lazily, so a deployment configuring a different
store never needs it installed.

## Using it

```python
from entra_auth import EntraAuthConfig, TokenValidator

validator = TokenValidator(EntraAuthConfig(tenant_id=TENANT, client_id=CLIENT))
verified = await validator.validate_token(token)      # raises AuthError on any refusal
principal = my_app.principal_from(verified)           # the consumer owns its identity type
```

Token validation returns `VerifiedToken` — verified claims, reduced — and never a principal. The
consumer maps it in one place it owns, so the application has exactly one identity model and
this component can move to another consumer unchanged. Session storage accepts that host's
serialized identity without interpreting its fields.

Testing needs no tenant and no network: inject a fetcher.

```python
async def keys(_url): return {"keys": [my_jwk]}
validator = TokenValidator(config, fetcher=keys)
```

[Token and store tests](../../tests/test_entra_auth.py) do this, including matching refusals.

## What a token must satisfy

Checked in this order, cheapest first, so a malformed or hostile token is refused without
spending network or public-key mathematics on it.

| # | Check | Refusal reason |
| --- | --- | --- |
| 1 | Non-empty, under `MAX_TOKEN_BYTES` (16 KiB) | `empty_token`, `oversized` |
| 2 | `alg` in `("RS256",)` — an allowlist, never read from the token | `bad_algorithm` |
| 3 | `kid` resolves to a key in the cached set | `unknown_kid`, `jwks_stale`, `jwks_unavailable` |
| 4 | Signature, audience (`<client-id>` **or** `api://<client-id>`), `exp`, `nbf` | `bad_signature`, `bad_audience`, `expired`, `not_yet_valid` |
| 5 | `iss` is exactly one of the configured tenant's v1/v2 forms | `bad_issuer` |
| 6 | The signing key's own `issuer` names the same tenant | `key_issuer_mismatch` |
| 7 | `tid` equals the configured tenant | `bad_tenant` |
| 8 | `exp` and `iat` present; `iat` not in the future | `missing_claim`, `not_yet_valid` |
| 9 | Every claim in `required_claims` present and non-empty (`oid`, `tid`) | `missing_claim` |
| 10 | A person holds one of `required_scopes`; an application is refused unless `allow_service_principals` **and** it holds one of `required_roles` | `missing_scope`, `service_principal_refused` |

## Four properties worth stating

**There is no disabled mode.** A config either names a real tenant and a real audience or
cannot be constructed. There is no `enabled` flag, no development identity header, and no
branch that returns a self-asserted principal — so no configuration mistake can reach one. A
deployment that fails to configure Entra simply has no Entra resolver, and the consumer's own
authorization gate then refuses everyone.

**Single tenant only.** `common`, `organizations` and `consumers` are refused at construction,
by name, so the refusal can say which convenience was attempted. "Any Entra tenant with a
matching audience" is not an authorization decision anyone makes deliberately.

**Staleness is bounded.** A key set whose refresh keeps failing is served for
`jwks_max_stale_seconds` (six hours by default) and then fails closed. Serving a stale set
indefinitely keeps a revoked signing key acceptable for as long as the process runs, which
turns an availability nicety into a revocation failure.

**A rejection message is selected, never built.** `AuthError` maps a reason code to a constant
string. Nothing derived from a token can reach a response, a log line or a terminal; operators
get a key id's *length*, which distinguishes a plausible rotation miss from a padding attack,
and never its value.

## Browser sign-in

`new_flow()` mints the flow id, `state`, `nonce` and PKCE verifier server-side;
`authorize_url()` builds the redirect from configuration alone. Nothing in either is taken
from a request parameter, so no caller can aim a sign-in at an authority of their choosing.

Generating the verifier here rather than in the browser keeps it out of web storage: it is
held against an `HttpOnly` flow cookie and released once, to the same-origin callback page, so
its life is the seconds a redirect takes rather than the life of a tab.

These PKCE helpers perform no HTTP or storage operation. Token validation and the selected
record store have their own I/O. The consumer owns routes, cookies and store configuration;
[Investigation sign-in](../../../../template_apps/investigation_app/app/cybereye/backend/security/signin_routes.py)
is an immediate caller, not proof of live sign-in acceptance.

## Session Records

`SessionService(*, store: RecordStore, flow_store: RecordStore, max_lifetime: timedelta,
clock: Callable[[], datetime] = UTC_now)` owns the record mechanics. The clock returns
timezone-aware UTC datetimes. It reads no environment and selects no store or partition.

| Async method | Contract |
| --- | --- |
| `start_flow(flow: SignInFlow, *, ttl: timedelta) -> None` | Store `flow.to_record()` under `flow.flow_id` until `clock() + ttl` |
| `claim_flow(flow_id: str, state: str) -> dict[str, str] \| None` | Bound and validate both values before storage; atomic `consume`, then constant-time state comparison. A well-formed wrong state spends the flow. At most one claimant receives the record |
| `create(identity: Mapping[str, str], *, token_expires_at: datetime) -> tuple[str, datetime]` | Store the already-validated host record unchanged under the SHA-256 session digest. Expiry is the earlier of the token expiry and `clock() + max_lifetime`; expired credentials raise `AuthError("expired", "token expires too soon to mint a session")` before any write |
| `resolve(session_id: str) -> dict[str, str] \| None` | Read by digest; empty, missing or expired session returns `None` |
| `revoke(session_id: str) -> None` | Delete by digest; empty or absent session is success |
| `purge_expired() -> int` | Sum expired records removed from both stores |

All `RecordStoreUnavailable` failures propagate. The host must refuse admission when a lookup
fails; it owns logging, HTTP/error responses, principal validation/mapping, tenant and issuer
authorization, cookies, CSRF and routes. The service does not validate or authorize the identity
map. Never pass tokens or unverified caller data as an identity.

Stores retain their existing read-time expiry and atomic-consume obligations. No disk encoding,
Azure Table entity shape, partition name, flow payload or host identity field is changed.
The Investigation adapter continues to use `flow` and `session` partitions and its existing
six-field principal payload. Existing records remain readable without migration or dual writes.

## Known limits

- **The token endpoint is not called here.** With a SPA-platform redirect URI, Entra issues
  codes for cross-origin redemption from a browser and refuses server-side redemption of them,
  so the code exchange happens in the callback page. This component supplies the authorize URL
  and the verifier; the exchange is the consumer's.
- **`AzureTableRecordStore` uses injected fake service semantics in unit tests.** Earlier
  deployment observations are historical; this package exposes no `auth-provision` entry
  point. Live Table/identity acceptance requires the host's authorized runbook and read-back.
- **Expiry is enforced on read, and purging is separate.** Table Storage has no server-side
  TTL, so `purge_expired` is housekeeping an operator schedules. A late purge costs storage,
  never correctness: `get` refuses anything past its expiry whether or not the row is gone.
- **Refresh tokens are not handled at all.** A session ends when its access token would have
  expired, or at the configured ceiling, whichever is sooner. Extending a session means
  signing in again.

Origin, upstream hashes, and every change made: [PROVENANCE.md](PROVENANCE.md).

Setup and recorded verification: [package guide](../../README.md). Source examples require
host-supplied tenant/audience/token and authorization; no live command ran in this sweep.
