# entra-api-auth

Validate **Entra ID** access tokens on an API, and decide what belongs to whom.
JWKS with a rotation-aware cache, RS256-only verification, single- and
multi-tenant issuer rules, required-claim enforcement, ownership guards that
answer 404 rather than 403.

Self-contained. Copy this folder anywhere. Python 3.10+, two dependencies. The
core imports no web framework; the selftest mints its own RSA keys and tokens,
offline, no tenant, no network.
```
entra-api-auth/
  README.md            you are here — threat model and design decisions
  SKILL.md             agent-facing: wire it, verify it, remove it
  CONTRACT.md          exact claims, order, status codes, constants
  GOTCHAS.md           thirteen failures, symptom-first, six of them security
  entraauth/           the mechanism
    _config.py           AuthConfig — tenant, audience, policy. The only env read
    _errors.py           reason codes, and the public message they map to
    _jwks.py             key retrieval, TTL cache, rate-limited rotation refresh
    _validator.py        the decision: header, algorithm, key, signature, claims
    _principal.py        Principal — who the caller is, once believed
    _ownership.py        who may read and who may modify
    _fastapi.py          the framework seam, imported lazily
  scripts/
    diagnose.py          explain a 401 — every reason, not the first
  examples/
    api.py               a protected API with ownership, runnable
  tests/
    selftest.py          core and optional adapter checks, no network
```

---

## 1. The problem

Token validation looks finished long before it is correct. The library verifies
the signature in one call, the endpoint returns 200, and the rest of the work is
invisible — every unfinished piece fails **open**, silently, for requests nobody
makes yet.
| What is skipped | What it costs | Symptom |
| --- | --- | --- |
| Requiring the identity claim | Every service token shares one identity | Users see each other's data (G3) |
| Pinning the algorithm | The token chooses how it is verified | None — forged tokens are accepted |
| Caching the key set | An outbound HTTPS call per request | Latency, then a shared outage (G1) |
| Bounding rotation refresh | Anonymous callers flood the identity provider | Throttling, then failed logins (G10) |
| Cross-checking key and token issuer | Multi-tenant accepts the wrong tenant's key | None (G6) |
| Distinguishing 403 from 404 | Identifiers become enumerable | None (G4) |
| Keeping token fields out of errors | Log injection, escape sequences, markup (G2) | None |
| Separating auth from ownership | Ownership is first tested in production (G7) | Wrong data, or none |

Seven of those eight have no symptom. A capability whose failures are invisible
cannot be verified by using it.

## 2. The approach

Two decisions, kept apart.

```
authentication          authorisation
"who is calling"        "is this record theirs"
TokenValidator     +    OwnershipPolicy
```

Collapsed, an API serves one tenant's data to another's valid token. A token
proves identity. It says nothing about this row.

| Property | How |
| --- | --- |
| Algorithm cannot be chosen by the caller | `RS256` allowlist, checked before key lookup |
| Identity claim cannot be absent | `required_claims`, non-empty by construction |
| Key set is cached, rotation still works | TTL refresh, plus rotation refresh behind a cooldown |
| Key-service outage is survivable | Stale keys served; cold-cache failure is 503, not 401 |
| Errors disclose nothing | Public message selected by reason, never constructed |
| Existence is not leaked | Read denial and absence are the same 404 |
| Dev mode cannot reach production | Bypass lives inside `if not enabled`, returns before headers |
| Testable without a tenant | Framework-free core; keys and tokens minted in the test |

## 3. Threat model

**Defended.** Forged signatures. `alg: none`. RS256/HS256 confusion, the
published public key offered as an HMAC secret. Tokens from another tenant or for
another audience. Expired and not-yet-valid tokens. Tokens missing the identity
claim. Unknown-key probing as an amplifier against the identity provider. Log and
terminal injection through token fields. Resource enumeration through status
codes. Oversized tokens and key documents. Development identity headers in
production.

**Not defended.** A stolen valid token — expiry and conditional access cover
that. A compromised tenant. Authorisation beyond ownership: roles and scopes are
exposed on the principal, their meaning is the consumer's policy. Transport
security, the platform's. Replay within the token's lifetime; single-use needs a
nonce protocol, not this.

**Assumed.** TLS terminates in front of the app. The clock is roughly right — ten
seconds of leeway covers drift, not a broken host (G9).

## 4. Why it is portable, despite being Azure-native

The core is a function of headers. `TokenValidator.authenticate(headers)` takes
any string mapping and returns a `Principal`; no web framework, no Azure SDK, no
HTTP client imported. `install_auth(app, config)` adapts it to FastAPI in one
call, importing the framework **inside** the function so the box installs and
selftests without it.

Two consequences:

- **A non-HTTP caller validates by the same rules.** WebSocket handshake, queue
  consumer, test — all call `validate_token` directly instead of reimplementing
  the checks, which is how a second implementation drifts.
- **Another access path can coexist.** A mechanism that already authenticated the
  request leaves a `Principal` at an ASGI scope key and the dependency returns it
  unchanged. Signed agent access, mutual TLS or a validating gateway sit beside
  Entra, neither weakened, no second identity model.

## 5. Design decisions worth keeping

- **Algorithm checked before the key is fetched.** Rejecting `alg: none` after a
  network round trip is correct and wasteful; this ordering makes hostile input
  cheapest.
- **Four forgery failures, one message.** Separating malformed, unknown-key and
  bad-signature tells an attacker what to change next. `expired` stays distinct
  because a client acts on it.
- **Cold-cache key failure is 503.** A 401 blames the caller's credential for
  your dependency's outage, and dashboards read as a spike in bad credentials.
- **Rotation refresh is rate-limited, scheduled refresh is not.** Only the
  caller-triggered path is an amplifier.
- **Stale keys served when discovery fails.** Valid a minute ago, same provider.
  Failing closed converts someone else's wobble into your outage.
- **`enabled` fails closed on anything unrecognised.** The dangerous value must
  be hard to set by accident.
- **The development principal is marked `developer`.** Self-asserted and proven
  identities must not leave the same audit trace.
- **Ownership enforced in development too.** Per-tab identities make two tabs two
  users, so the rules run locally as they will live.
- **Unowned records are private by default.** Rows predating an ownership column
  are the usual source; public-by-default turns a migration into a disclosure.
- **Listing filters rather than checks.** A per-item check on the detail route
  protects one endpoint and hands the whole table over on another.

## 6. Quick start

```bash
uv sync --locked --no-install-project --extra fastapi
.venv/bin/python tests/selftest.py
.venv/bin/python examples/api.py
```

Wire it:

```python
config    = ea.AuthConfig.from_env()
config.require_enabled()
validator = ea.install_auth(app, config)
current   = ea.principal_dependency(validator)

@app.get("/api/records/{record_id}")
async def get_record(record_id: str, principal: ea.Principal = Depends(current)):
    record = store.get(record_id)
    if record is None:
        raise ea.NotFoundError(resource_id=record_id)
    ea.DEFAULT_POLICY.assert_readable(record.owner_id, principal, record_id)
    return record
```

In any deployed environment, call `config.require_enabled()` at startup. One line
turns the box's worst configuration mistake from a silent exposure into a failed
boot (G11).

When a token is rejected and the reason is not obvious:

```bash
az account get-access-token --resource api://<app-id> --query accessToken -o tsv \
    | python3 scripts/diagnose.py --check-discovery
```

Reports **every** failure reason, not just the first. Token comes from stdin or a
file, never an argument — command lines are visible to every process on the host
and written to shell history.

## 7. Removal

1. Delete `entraauth/` and the `install_auth` call.
2. Remove the dependency from route signatures, or swap in another validator —
   CONTRACT.md suffices to write one.

No state to unwind: cached key set and configuration are process-local, nothing is
created in Azure. Application registration and role assignments are provisioned
elsewhere and unaffected.

## 8. Provenance

Portable migration copied `core/skills/dep/entra-api-auth` without changing its
mechanism. `pyproject.toml` makes `entraauth` installable; `uv.lock` fixes the
runtime and optional FastAPI check dependencies. Use a consumer-owned environment;
plugin installation creates no application environment, credentials or tenant state.
The parked source remains unchanged. Offline tests do not prove live Entra or proxy setup.

Extracted from a deployed API behind Entra ID, with signed agent access running
against it continuously and adversarial probes against the auth surface. G2 came
from a probe; G3, G4, G5, G7, G8 and G9 from production.

**Changed during extraction**, disclosed because packaging should not silently
alter behaviour:

- **Rotation-refresh cooldown is new (G10).** The origin forced a key-set fetch
  per unrecognised key id, letting an unauthenticated caller drive one outbound
  request per request. Shipping a known amplifier because "the origin did it"
  misreads "do not change behaviour while packaging". It has its own test, and
  the origin should adopt it.
- **Single-flight refresh is new.** The origin could issue N concurrent fetches
  on a cold cache. Same reasoning, smaller blast radius.
- **Cold-cache key failure is now 503, not 401.** The origin reported every
  failure as a credential problem, including its own dependency's.
- **HTTP client dependency dropped.** Key retrieval uses the standard library off
  the event loop, fetcher injectable for consumers wanting their own retry, proxy
  or telemetry policy. One call to one well-known endpoint did not justify the
  box's largest dependency.
- **`User` became `Principal`, with a `kind`.** The origin could not distinguish
  a service principal from a human, or a development identity from a proven one.
  Both distinctions are load-bearing (G3, G12).
- **Ownership generalised from sessions to any owned record**, guards became a
  policy object so shared-template ids are configurable rather than literal.
- **G13 was found while writing this box**, not in production: the FastAPI
  dependency returned 422 instead of 401 because postponed annotations plus a
  function-local import left the framework unable to resolve the type. The
  selftest caught it on the first run of the adapter tests.
