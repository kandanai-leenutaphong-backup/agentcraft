# CONTRACT — entra-api-auth

Everything needed to reimplement this box against the same tenant, in any
language. Exact claim names, order, status codes.

---

## 1. Configuration

### 1.1 Environment variables

Prefix defaults to `AUTH_`, overridable so two APIs can coexist in one process.

| Variable | Required | Type | Default |
| --- | --- | --- | --- |
| `<P>ENABLED` | no | affirmative string | `false` |
| `<P>TENANT_ID` | when enabled | GUID or `common` | — |
| `<P>CLIENT_ID` | when enabled | GUID | — |
| `<P>EXTRA_AUDIENCES` | no | comma-separated | empty |

`ENABLED` is true **only** for `1`, `true`, `yes`, `on` (case-insensitive, after
stripping). Everything else is false. Deliberate asymmetry: a typo must not
produce an API that accepts every request (G11).

### 1.2 Fatal validation, when enabled

| Condition | Reason |
| --- | --- |
| no `tenant_id` | nothing to trust |
| no `client_id` | no audience to require |
| `tenant_id` neither a GUID nor `common` | not an Entra tenant |
| `leeway_seconds < 0` | negative skew is not a policy |
| empty `required_claims` | every caller collapses to one identity (G3) |

A **disabled** config skips all of it: local development must not require an
application registration to boot.

### 1.3 Derived values

```
audiences()        = [client_id, "api://" + client_id, *extra_audiences]
jwks_url()         = https://login.microsoftonline.com/<tenant>/discovery/v2.0/keys
expected_issuers() = single tenant:
                       https://login.microsoftonline.com/<tenant>/v2.0
                       https://sts.windows.net/<tenant>/
                     multi-tenant: () — checked by shape instead
```

### 1.4 Constants

| Constant | Value | Why |
| --- | --- | --- |
| accepted algorithms | `("RS256",)` | allowlist; never read from the token |
| clock skew leeway | 10 s | ordinary drift, not an excuse for a wrong clock |
| key-set TTL | 86 400 s | scheduled refresh |
| rotation refresh cooldown | 60 s | bounds unauthenticated amplification (G10) |
| maximum token size | 16 KiB | rejected before parsing |
| maximum key document | 512 KiB | rejected before decoding |
| discovery timeout | 10 s | |
| required claims | `("oid",)` | |

---

## 2. Key set retrieval

One document cached per process. Never fetch per request (G1).

```
get_key(kid):
    if empty or older than TTL:      refresh("scheduled")
    if kid present:                  return it
    if cooldown elapsed:             refresh("rotation"); if present, return it
    raise unknown_kid
```

Refresh rules:

- **Single flight.** Concurrent callers produce one fetch, not one each.
- **Cooldown applies to rotation refreshes only.** The scheduled TTL refresh is
  not caller-triggered, so it is not rate-limited.
- **Fetch failure with a warm cache is not an error.** Serve stale and log; keys
  valid a minute ago are still signed by the same provider.
- **Fetch failure with a cold cache raises `jwks_unavailable`** — a **503**, not
  a 401. The caller's credential is not in question.
- **An empty key document counts as a failed fetch**, not "no keys are valid".
- Key entries must be RSA. Any other `kty` is refused, not guessed at.

RSA public key reconstruction: base64url-decode `n` and `e` (unpadded; append
`==`), interpret big-endian, build an RSA public key, serialise to PEM
SubjectPublicKeyInfo.

---

## 3. Validation order

Cheapest first, so hostile input costs the least. Each step raises on failure;
none is skipped because a later one would also fail.

```
1.  token non-empty                    -> empty_token
2.  token <= 16 KiB                    -> malformed
3.  decode JOSE header (unverified)    -> malformed
4.  header.alg in ALLOWED_ALGORITHMS   -> bad_algorithm
5.  look up header.kid in the key set  -> unknown_kid | jwks_unavailable
6.  build PEM from the key entry       -> unknown_kid
7.  verify signature, audience, exp    -> bad_signature | bad_audience
                                          | expired | not_yet_valid
                                          | missing_claim | malformed
8.  validate issuer                    -> bad_issuer
9.  cross-check key issuer vs token    -> key_issuer_mismatch
10. required claims present, non-empty -> missing_claim
```

Step 4 precedes step 5 so `alg: none` and HS256 confusion are rejected without a
key lookup. Step 7 sets `verify_iss=False` and requires `exp`; the issuer is
checked at step 8 because a library can only exact-match, and multi-tenant
cannot.

### 3.1 Issuer rules

**Single tenant.** Exact match against either expected issuer. Both v1 and v2
forms accepted: which appears depends on how the token was requested, and
rejecting the other yields intermittent failures (G5-adjacent).

**Multi-tenant.** The issuer must match

```
^https://(login\.microsoftonline\.com|sts\.windows\.net)/<guid>(/v2\.0)?/?$
```

Shape only — the tenant is not known in advance.

### 3.2 Key-issuer cross-check

Key entries may carry an `issuer`, sometimes templated `{tenantid}`.

```
expected = key.issuer.replace("{tenantid}", claims.tid)
accept if issuer == expected
   else if tenant GUID in expected == tenant GUID in claims.iss
   else raise key_issuer_mismatch
```

Keys with no `issuer` field skip the check. Without this, a multi-tenant API
accepts a token claiming tenant A signed by tenant B's key (G6).

---

## 4. Errors

### 4.1 Reason codes and what the caller is told

The public message is **selected by reason**, never constructed. No request value
may appear in it (G2).

| Reason | Status | Public message |
| --- | --- | --- |
| `missing_header`, `empty_token` | 401 | `Missing or malformed Authorization header` |
| `malformed`, `unknown_kid`, `bad_signature`, `bad_algorithm` | 401 | `Invalid token` |
| `expired` | 401 | `Token expired` |
| `not_yet_valid` | 401 | `Invalid token` |
| `bad_audience` | 401 | `Invalid audience` |
| `bad_issuer`, `key_issuer_mismatch` | 401 | `Invalid issuer` |
| `missing_claim` | 401 | `Token missing a required claim` |
| `jwks_unavailable` | 503 | `Authentication temporarily unavailable` |
| anything else | 401 | `Authentication failed` |

Four distinct forgery failures collapse to one message: telling an attacker which
part of the forgery failed tells them what to change. `expired` is distinguished
because it is actionable.

Every 401 carries `WWW-Authenticate: Bearer` (RFC 6750).

Response body:

```json
{"error": "<reason>", "message": "<public message>"}
```

### 4.2 Log fields

One line per rejection: `reason`, `duration_ms`, box-measured context only —
lengths and flags, never raw input. An unknown key id logs `kid_len`.

---

## 5. Principal

Built only from **verified** claims.

| Field | Source, in order |
| --- | --- |
| `id` | `oid`, then `sub` |
| `email` | `preferred_username`, `email`, `upn` |
| `name` | `name`, `given_name` |
| `tenant_id` | `tid` |
| `scopes` | `scp`, split on whitespace |
| `roles` | `roles` |
| `kind` | `idtyp`, else `scp`/`roles` shape — see the table below |
| `kind_certain` | `False` when `kind` was read off the token's shape rather than stated |
| `claims` | all verified claims |

`kind` is `developer` when produced in disabled mode. Nothing else may produce a
`developer` principal, and no code should treat one as proven (G12).

### `kind` and `kind_certain`

`oid` is **not** a signal. Microsoft's
[access token claims reference](https://learn.microsoft.com/en-us/entra/identity-platform/access-token-claims-reference)
defines `oid` as the directory object id of a user **or** a service principal;
its absence says nothing about which. `idtyp` says, and is optional.

| `idtyp` | `scp` | `roles` | `kind` | `kind_certain` |
| --- | --- | --- | --- | --- |
| `"app"` | any | any | `service` | `True` |
| `"user"` | any | any | `user` | `True` |
| absent | present | any | `user` | `True` |
| absent | absent | present | `service` | `False` |
| absent | absent | absent | `user` | `False` |

Add `idtyp` to the API's optional claims in the app registration and every row
becomes `True`. Until then treat `kind_certain=False` as "not stated" and refuse
any decision a wrong answer would make expensive.

Log fields: `principal_id`, `principal_kind`, `principal_kind_certain`,
`tenant_id`. Email excluded by default — personal data on every request, and the
id is what correlates.

---

## 6. Ownership

Independent of authentication, enforced identically with auth on or off (G7).

| Owner value | Read | Write |
| --- | --- | --- |
| equals `principal.id` | yes | yes |
| in `shared_owner_ids` (default `("__default__",)`) | yes | **no** |
| empty | only if `allow_unowned_read` | no |
| any other | no | no |

Failures:

| Case | Raises | Status |
| --- | --- | --- |
| read denied | `NotFoundError` | 404 |
| write denied, not shared | `NotFoundError` | 404 |
| write denied, shared template | `ForbiddenError` | 403 |

404 for "not yours" is the point: a distinguishable 403 makes the id space
enumerable (G4). Shared templates are the exception — the caller can already read
them, so their existence is not a secret.

`ForbiddenError` is also raised by scope and role guards, and is never a 401: the
caller is authenticated, so refreshing the token cannot help.
---

## 7. Disabled mode

```
enabled == false:
    return developer principal
        id    = X-User-Id    or "anonymous"
        email = X-User-Email or "dev@localhost"
        name  = X-User-Name  or "Developer"
        kind  = "developer"
```

The branch returns **before** any header is inspected for a token, and is
unreachable when enabled: a request carrying both a token and `X-User-Id`
resolves to the token's identity (G12).

Per-caller identity in development is not a convenience. Without it every local
request is the same principal, ownership checks cannot fail, and they are first
exercised in production (G7).

## 8. Framework seam

The validator is framework-free: `authenticate(headers, dev_identity=...)` takes
any string mapping, returns a principal. Header lookup is case-insensitive (G8).

The FastAPI adapter registers three exception handlers, optionally mounts the
unauthenticated configuration endpoint, and builds a dependency that:

1. returns a `Principal` already present at the ASGI scope key, if any —
   the hand-off that lets a second access path coexist;
2. otherwise authenticates from headers.

Client configuration endpoint, unauthenticated by necessity:

```json
{"useLogin": false}
{"useLogin": true,
 "clientId": "<client id>",
 "authority": "https://login.microsoftonline.com/<tenant>",
 "scopes": ["api://<client id>/access_as_user"]}
```

Contains only values a sign-in redirect would reveal anyway. No secret is served
here.

---

<!-- api-surface:start -->

## Public surface

Every name exported by `entraauth`. Regenerate the list after changing
`__all__`, from this directory:

```bash
python3 -c "import entraauth; print(chr(10).join(sorted(entraauth.__all__)))"
```

| Name | Kind | Description |
| --- | --- | --- |
| `AuthConfig` | class | Who is trusted to issue tokens, and who they must be addressed to. |
| `ALLOWED_ALGORITHMS` | constant | ('RS256',) |
| `DEFAULT_ENV_PREFIX` | constant | 'AUTH_' |
| `MULTI_TENANT` | constant | 'common' |
| `Principal` | class | An authenticated caller. |
| `principal_from_claims` | function | Build a principal from verified claims. |
| `developer_principal` | function | Build the identity used when authentication is disabled. |
| `KIND_USER` | constant | 'user' |
| `KIND_SERVICE` | constant | 'service' |
| `KIND_DEVELOPER` | constant | 'developer' |
| `TokenValidator` | class | Validates Entra access tokens against one tenant and one audience. |
| `JWKSCache` | class | A key set, with a scheduled refresh and a rate-limited rotation refresh. |
| `build_rsa_pem` | function | Convert one JWKS entry into a PEM public key. |
| `default_fetcher` | function | Fetch a key set without blocking the event loop. |
| `OwnershipPolicy` | class | Who may read and who may modify a record, given its owner id. |
| `DEFAULT_POLICY` | constant | OwnershipPolicy(shared_owner_ids=('__default__',), allow_unowned_read=False) |
| `DEFAULT_SHARED_OWNER` | constant | '__default__' |
| `AuthError` | class | A rejected request, with an operator view and a caller view. |
| `ForbiddenError` | class | An authenticated caller acting outside their permissions. |
| `NotFoundError` | class | A resource the caller may not have, reported as absent. |
| `install_auth` | function | Wire authentication into an application. The whole integration surface. |
| `principal_dependency` | function | Build the FastAPI dependency that yields the authenticated principal. |
| `require_scope` | function | Build a guard that rejects a principal lacking a delegated permission. |
| `require_role` | function | Build a guard that rejects a principal lacking an application role. |
| `DEFAULT_SCOPE_KEY` | constant | 'auth_principal' |
| `DEFAULT_SETUP_PATH` | constant | '/api/auth_setup' |

<!-- api-surface:end -->
