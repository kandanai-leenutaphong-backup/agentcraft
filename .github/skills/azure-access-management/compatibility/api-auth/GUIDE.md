
# entra-api-auth

This package also includes [browser/session auth](../browser-auth/GUIDE.md): a stricter, neutral-claims
`entra_auth` API with PKCE and expiring stores. It is not a drop-in replacement for the existing
`entraauth` principal API. Prefer its fail-closed policy for new browser hosts; retain existing
consumer contracts unless deliberately migrating them, and keep record authorization in the host.

Two decisions, kept separate: **who is calling** (token validation) and **is this
record theirs** (ownership). Collapsed, a valid token reads another tenant's data.

## Decide

Use for a Python API protected by Entra ID, FastAPI or not — the core takes
headers, returns a principal.

Not for: signing a user in (client-side library), issuing your own tokens,
API-key auth. Machine identity: give the caller a service principal, read
§Service principals.

## Install

In this retained guide, `PACKAGE_ROOT` means the consolidated skill's
`compatibility/api-auth` directory. To integrate
the library, vendor `entraauth/` into the application's owned source or install
this directory as a Python package. Plugin discovery alone does not install it
into the application's interpreter.

```bash
python3 -m pip install -r "$PACKAGE_ROOT/requirements.txt"
python3 "$PACKAGE_ROOT/tests/selftest.py"
```

The core check needs no tenant. FastAPI/httpx are optional; adapter checks need
both and report a skip if unavailable. No tenant registration or credential is
created by installation.

```bash
export AUTH_ENABLED=true
export AUTH_TENANT_ID="<tenant-guid>"      # or "common" for multi-tenant
export AUTH_CLIENT_ID="<this-api's-app-id>"
```

`AUTH_ENABLED` is true only for `1`/`true`/`yes`/`on`. Anything else, typo
included, is false. Call `config.require_enabled()` at the composition root in
every deployed environment; never use the inherited development mode to pass
deployment or integration acceptance (G11).

## Use

### Wire it

```python
import entraauth as ea

config = ea.AuthConfig.from_env()
config.require_enabled()                    # in any deployed environment
validator = ea.install_auth(app, config)    # the whole integration surface
current = ea.principal_dependency(validator)
```

`install_auth` registers exception handlers, mounts `/api/auth_setup` for the
sign-in client, logs configuration warnings at startup.

### Protect a route

```python
@app.get("/api/records/{record_id}")
async def get_record(record_id: str, principal: ea.Principal = Depends(current)):
    record = store.get(record_id)
    if record is None:
        raise ea.NotFoundError(resource_id=record_id)
    ea.DEFAULT_POLICY.assert_readable(record.owner_id, principal, record_id)
    return record
```

Owner key is `principal.id`. Never the email — it changes.

### Filter a listing

```python
visible = [r for r in store.all() if policy.can_read(r.owner_id, principal)]
```

Per-item checks protect one endpoint; the list route hands over the whole table.

### Read and write

```python
policy.assert_readable(owner_id, principal, record_id)             # 404 if not theirs
policy.assert_writable(owner_id, principal, "delete", record_id)   # 404, or 403 if shared
```

404 for "not yours" is deliberate: a distinguishable 403 makes identifiers
enumerable (G4).

### Service principals

An app authenticating as itself **does** get an `oid` (the service principal's
directory object id). The default required claim admits it; `oid` absence detects
nothing. Ask for the claim that states the answer:

```python
# In the app registration: Token configuration -> Add optional claim ->
# Access -> idtyp.  Then this is a fact, not a reading.
if principal.is_service and principal.kind_certain:
    ...   # no human behind this call
```

Without `idtyp`, `kind` is inferred from token shape: `scp` present means a user
consented; `roles` alone reads as app-only, `kind_certain=False`. Never relax
`required_claims` around a misclassification — every caller missing the relaxed
claim then shares one identity (G3).

### Scopes and roles

```python
ea.require_scope("access_as_user")(principal)   # raises ForbiddenError (403)
ea.require_role("Writer")(principal)
```

### Outside HTTP

```python
claims = await validator.validate_token(raw_token)     # same rules, no request
```

## Verify

```bash
python3 tests/selftest.py          # offline
python3 examples/api.py            # ownership behaviour, self-driven

az account get-access-token --resource api://<app-id> --query accessToken -o tsv \
    | python3 scripts/diagnose.py --check-discovery
```

`diagnose.py` reports **every** rejection reason, not the first. Token comes from
stdin or a file, never an argument: command lines are visible process-wide and
land in shell history.

## Test without a tenant

Inject a fetcher; mint your own keys.

```python
async def fake_keys(_url): return {"keys": [my_jwk]}
validator = ea.TokenValidator(config, fetcher=fake_keys)
```

`tests/selftest.py` does this, hostile cases included: `alg: none`, HS256
confusion with the published public key, foreign signing keys, expired and
not-yet-valid tokens, a key id carrying newlines and escape sequences.

## Compose with another access path

A mechanism that already authenticated the request leaves a `Principal` at the
ASGI scope key; the dependency returns it unchanged:

```python
request.scope[ea.DEFAULT_SCOPE_KEY] = ea.Principal(id="agent", kind=ea.KIND_SERVICE)
```

Signed developer access, mutual TLS or a validating gateway then coexists with
Entra: no second identity model, neither path weakened.

## Symptoms

| Symptom | Read |
| --- | --- |
| Slow under load; identity provider outage becomes yours | G1 |
| Token field appears in a response or log | G2 |
| Users share an account; empty user id | G3 |
| Identifiers can be enumerated by status code | G4 |
| "Invalid audience" and the audience is right | G5 |
| Multi-tenant accepts the wrong tenant's key | G6 |
| Ownership bugs appear only in production | G7 |
| Works locally, 401 behind the load balancer | G8 |
| Sporadic "expired" on valid tokens | G9 |
| Outbound flood to the identity provider | G10 |
| Auth was disabled in production | G11 |
| `X-User-Id` honoured where it should not be | G12 |
| Route returns 422 naming `request` as missing | G13 |

## Remove

Delete `entraauth/` and the `install_auth` call; drop the dependency from route
signatures. Nothing to unwind: cached key set and config are process-local, and
no Azure resource is created.
