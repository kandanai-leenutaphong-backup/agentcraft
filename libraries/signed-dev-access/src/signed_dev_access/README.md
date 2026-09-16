# `signed_dev_access` — Ed25519 signed-request access

A second credential path that weakens no primary one. A coding agent cannot drive a deployed
application it cannot authenticate to, and every convenient shortcut — a shared bypass header,
a disable-auth flag, a service account with a static password — makes production weaker for
the sake of a development loop. This is the alternative: a keypair whose private half never
leaves the operator's machine and whose public half is not a secret at all.

Domain-blind. It owns canonical-string reconstruction, verification, replay rejection and the
failure shape; it knows nothing about the consuming application's identity type. The consumer
injects `identity_factory(slug)`, the resulting principal is attached to the ASGI scope, and
the consumer's own authorization gate reads it there. That injection is the whole integration
surface, which is why this component moves between projects unchanged.

Origin and what was changed here: [PROVENANCE.md](PROVENANCE.md).

## Install

```python
from signed_dev_access import (
    AzureTableReplayLedger, install_signed_request_auth,
)

install_signed_request_auth(
    app,
    public_key_b64=os.environ.get("DEV_PUBLIC_KEY_ED25519", ""),
    identity_factory=lambda slug: MyPrincipal(id=f"devkey:{fingerprint}:{slug or 'default'}"),
    replay_ledger=AzureTableReplayLedger(endpoint=..., table_name="devauthreplay"),
)
```

An empty public key mounts nothing: the ASGI stack is identical to a build that never carried
this component, and the deployment has no signed authorizing path. Revocation is clearing one
environment variable — no code change, no redeploy of the primary authentication path.

## Public surface

Canonical client signing, private-key loading, bound requests, browser interception
and the module CLI are documented in the [client contract](../../docs/skills/signed-dev-access.md).
They reuse `canonical_string`; the verifier, middleware and replay implementations
below remain the only server owner. The old `devauth` import is retired.

| Name | Kind | What it does |
| --- | --- | --- |
| `install_signed_request_auth(app, *, public_key_b64, identity_factory, replay_ledger, scope_key="auth_principal", max_body_bytes=1048576) -> bool` | function | Mounts the middleware, or declines when the key is empty. Returns whether it mounted |
| `SignedRequestASGIMiddleware(app, *, public_key_b64, identity_factory, replay_ledger, scope_key, max_body_bytes)` | class | The middleware itself. Refuses construction with an empty key or no ledger |
| `verify(*, public_key_b64, method, path_and_query, ts, sig_b64, body, user_slug="") -> VerifyResult` | function | The pure primitive. No I/O, no logging |
| `VerifyResult(ok, user_slug, replay_key, expires_at)` | dataclass | Everything a caller learns. On failure every field is empty |
| `canonical_string(*, method, path_and_query, timestamp, context_slug, body_sha256_hex) -> bytes` | function | The exact bytes signed. A client in any language needs only this |
| `public_key_fingerprint(public_key_b64) -> str` | function | 16 hex characters, for namespacing identities. Empty when the key does not decode |
| `ReplayLedger` | protocol | `async claim(key, expires_at) -> bool`, atomic |
| `InProcessReplayLedger(*, max_entries=8192)` | class | Correct for one process, and says so: `durable = False` |
| `AzureTableReplayLedger(*, endpoint, table_name, partition_key="sig", client_factory=None)` | class | Durable, shared, identity-authenticated. `durable = True` |
| `ReplayLedgerUnavailable` | exception | The ledger could not decide. Callers deny |
| `claim_or_deny(ledger, key, expires_at) -> bool` | function | Claim, treating every unavailability as a denial |
| `TIMESTAMP_HEADER`, `SIGNATURE_HEADER`, `CONTEXT_HEADER` | constants | `X-Request-Timestamp`, `X-Request-Signature`, `X-Request-Context` |
| `MAX_SKEW_SECONDS`, `MAX_SIGNED_BODY_BYTES`, `MAX_SIGNED_BODY_CHUNKS`, `DEFAULT_SCOPE_KEY` | constants | 300, 1 MiB, 4096, `auth_principal` |

## The wire contract

Three headers. The names deliberately resemble ordinary API request signing; nothing in them
says `dev`, `key` or `bypass`, so captured traffic teaches an observer nothing.

| Header | Required | Value |
| --- | --- | --- |
| `X-Request-Timestamp` | yes | RFC 3339 UTC, e.g. `2026-09-06T04:11:07.123456Z` |
| `X-Request-Signature` | yes | base64 of the 64-byte Ed25519 signature |
| `X-Request-Context` | no | caller slug, `[a-z0-9_-]{0,64}` |

Five fields, newline-delimited, ASCII, order frozen:

```
METHOD \n PATH_AND_QUERY \n TIMESTAMP \n CONTEXT_SLUG \n BODY_SHA256_HEX
```

`PATH_AND_QUERY` is the path **as sent on the wire**, still percent-encoded, with `?query`
appended verbatim. Adding, removing or reordering a field is wire-incompatible; rotate keys
rather than negotiate versions.

Verification, in order, every step producing the same failure:

1. inputs within their length bounds;
2. public key decodes to exactly 32 bytes;
3. timestamp parses with a zone and `|now − ts| ≤ 300 s`;
4. signature decodes to exactly 64 bytes;
5. normalised slug matches `^[a-z0-9_-]{0,64}$`;
6. Ed25519 verification of the canonical string succeeds;
7. the replay ledger claims the signature for the first time.

## The failure shape

```
HTTP/1.1 401
content-length: 0
cache-control: no-store, private
```

No body, no `WWW-Authenticate`, no reason code, and **no log line at any level, including
debug, anywhere in this component**. A failed verification is indistinguishable from a request
that never attempted authentication, from every vantage point including the server's own logs.

That silence is the feature, and it costs something: a misconfigured key, a wrong signature and
an ingress that stripped a header all look identical. Keep one known-good signed request as a
canary and run it first after every deployment; diagnose by bisecting environments, never by
adding a diagnostic to the failure path.

## Replay, and why the ledger is not optional

The canonical string carries no nonce, so a captured signature is replayable for the whole skew
window unless something remembers it. `replay_ledger` is a required argument with no default,
because the only default available would be per-process — and a per-process ledger is defeated
by a second replica, by a cold start, and by the overlap window of a revision swap. A security
hole nobody chose is worse than one somebody did.

Three properties the ledger must have, each of which was a real defect in the design this was
adopted from:

- **The key is the decoded signature, not the header text.** Sixty-four bytes encode as 88
  base64 characters whose 86th carries two significant bits and four ignored ones, so sixteen
  distinct texts decode to the same signature. A ledger keyed on the header string accepts
  fifteen replays of something it has already seen.
- **Retention runs to `signed timestamp + 300 s`, not 300 s from first sight.** A timestamp up
  to 300 s in the future is inside the skew window and stays verifiable for up to 600 s from
  now; a fixed 300 s TTL evicts the entry while the signature still works.
- **Unavailable means denied.** `claim` raises `ReplayLedgerUnavailable` rather than returning
  `True` on doubt, and `InProcessReplayLedger` refuses when full rather than evicting a live
  key — eviction under memory pressure is exactly the condition an attacker can create.

`AzureTableReplayLedger` uses the primitive Table Storage gives directly: inserting an entity
whose `(PartitionKey, RowKey)` already exists fails atomically with `ResourceExistsError`, so
there is no read-then-write race. It authenticates with `DefaultAzureCredential` and holds no
account key; the SDK is imported lazily, so a deployment using a different ledger never needs
it installed. Stored rows are `{PartitionKey, RowKey, ExpiresAt}` and nothing else: the row key
is already a digest, so an operator reading the table learns only that some signature was
spent. Table Storage has no server-side TTL, so `purge_expired()` is housekeeping; purging late
is harmless, because a row is only removed once its signature can no longer verify.

## Bounds

Everything an unauthenticated caller can spend server work on is capped before the work
happens: header lengths before parsing, the path before hashing, the body at 1 MiB, and the
number of body chunks at 4096 — a malformed chunked stream of empty chunks never reaches the
byte cap and would otherwise loop forever.

`MAX_SKEW_SECONDS` is module-private with no environment override, deliberately: an attacker
who can influence configuration must not be able to widen the replay window.

## Rules this component keeps

- Standard library plus `cryptography`. No web framework: the middleware is pure ASGI, never
  `BaseHTTPMiddleware`, which buffers response bodies and would break every event stream.
- No configuration is read at import time, and no client is built until first use.
- Nothing here imports the application, and nothing here logs.

## Tests

Offline, no Azure account, no network, no browser. Keys are generated in memory and discarded.

```bash
/usr/bin/python3 -m unittest discover -s app/components/tests -t .
```

The signed-access battery is `app/components/tests/test_signed_dev_access_auth.py`: 50 checks,
most of them negative — tampered fields, wrong keys, stale and future clocks, re-encoded
signatures, duplicated headers, hostile slugs, oversized and endless bodies, ledger outages and
concurrent claims.

## Known limits

- **`AzureTableReplayLedger` has never run against a real storage account.** It is proved
  against an injected fake with the service's conflict semantics. Reachability in this tenant
  is an open question: Azure Policy forces `publicNetworkAccess=Disabled` on storage accounts
  here, so a Container App outside a VNet cannot reach the table data plane. Whoever provisions
  it must confirm reachability first; the alternative is a VNet-integrated environment with a
  private endpoint, or a policy exemption.
- **The context header may not survive an ingress.** The signature covers the slug, so a
  stripped header silently invalidates every signature that carried one. Test header
  preservation during environment bring-up; if it does not survive, sign with an empty slug and
  accept the shared default identity. Do not respond by weakening the primary path.
- **Percent-encoded path segments are risky through a managed ingress.** Some ingresses decode
  them before forwarding, so the application never sees the bytes the client signed. Prefer a
  query parameter or the body.
