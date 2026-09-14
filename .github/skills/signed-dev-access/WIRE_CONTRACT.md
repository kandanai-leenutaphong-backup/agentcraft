# WIRE_CONTRACT.md — signed-dev-access

The exact bytes. Everything else in this box implements this document. A correct
client in any language needs only this page.
---

## 1. Headers

| Header | Required | Value |
| --- | --- | --- |
| `X-Request-Timestamp` | yes | RFC 3339 UTC with `Z` suffix, e.g. `2026-08-22T04:11:07.123456Z` |
| `X-Request-Signature` | yes | base64 of the 64-byte Ed25519 signature |
| `X-Request-Context` | no | caller slug, `[a-z0-9_-]{0,64}` |

Header names deliberately resemble generic API request signing (AWS SigV4,
Stripe). Nothing says `dev`, `key`, or `bypass`, so someone reading captured
traffic learns nothing about the mechanism.

The middleware activates only when a public key is configured **and** both
required headers are present. Anything else passes straight through to the
application's primary auth path.

## 2. Canonical string

Five fields, newline-delimited, fixed order, ASCII-encoded:

```
METHOD \n PATH_AND_QUERY \n TIMESTAMP \n CONTEXT_SLUG \n BODY_SHA256_HEX
```

| Field | Encoding |
| --- | --- |
| `METHOD` | uppercase ASCII verb (`GET`, `POST`, ...) |
| `PATH_AND_QUERY` | path **as sent on the wire**, still percent-encoded, with `?query` appended verbatim when present |
| `TIMESTAMP` | byte-identical to the `X-Request-Timestamp` header |
| `CONTEXT_SLUG` | normalised slug (strip, lowercase) — empty string when absent |
| `BODY_SHA256_HEX` | 64 lowercase hex chars; SHA-256 of the raw body, empty body hashes as SHA-256 of zero bytes |

The `\n` delimiter is unambiguous because no encoded field can contain a
newline: method is a verb, path is percent-encoded (`%0A`), timestamp has fixed
shape, slug is allowlisted, digest is hex.

**Field order is frozen.** Adding, removing, or reordering a field is a
wire-incompatible change; rotate keys rather than negotiate versions.

**Both sides must normalise the slug identically** — strip, then lowercase,
*before* it enters the canonical string.

## 3. Signature

```
signature = Ed25519_sign(private_key, canonical_string_bytes)
header    = base64(signature)          # 64 raw bytes -> 88 base64 chars
```

## 4. Key material

| Half | Storage | Secret? |
| --- | --- | --- |
| Private | operator machine only, `~/.devauth/dev_signing_key`, mode `0600` | yes, never transmitted |
| Public | server env var `DEV_PUBLIC_KEY_ED25519`, base64 of 32 raw bytes | **no** — plain env var, never a vault entry |

A public key in a secret store is a category error: rotation ceremony for
nothing. Rotation: generate, set env var, restart. Revocation: clear the env var.

## 5. Verification algorithm

Every step returns the same failure. No step reports why.

1. Public key present, decodes from base64, is exactly 32 bytes.
2. Timestamp parses as RFC 3339 with a timezone, and `|now - ts| <= 300s`.
3. Signature decodes from base64 and is exactly 64 bytes.
4. Normalised slug matches `^[a-z0-9_-]{0,64}$`.
5. Ed25519 verification of the canonical string succeeds.
6. Signature has not been seen before within the TTL window.

On success the verified slug goes to `identity_factory(slug)` and the resulting
principal is attached to `scope["devauth_user"]`.

## 6. Failure shape

```
HTTP/1.1 401
content-length: 0
```

No body. No `WWW-Authenticate`. No reason code. No log line - not at any level,
not even debug, in verifier or middleware. A failed verification is
indistinguishable from a request that never attempted authentication, from every
vantage point including the server's own logs.

## 7. Constants

| Constant | Value | Why it is not configurable |
| --- | --- | --- |
| Max clock skew | 300 s | An attacker who can influence configuration must not be able to widen the replay window. Module-private, no env override. |
| Replay TTL | 300 s | Must equal the skew window exactly. Shorter leaves a gap after eviction; longer wastes memory on signatures that can no longer verify. |
| Slug pattern | `^[a-z0-9_-]{0,64}$` | Validated at the trust boundary; see GOTCHAS.md G4. |

## 8. Reference client

Fifteen lines, standard library plus `cryptography`:

```python
import base64, hashlib
from datetime import datetime, timezone
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

def sign(private_key: Ed25519PrivateKey, method: str, path_and_query: str,
         body: bytes = b"", context: str = "") -> dict[str, str]:
    ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    slug = context.strip().lower()
    canonical = (
        f"{method.upper()}\n{path_and_query}\n{ts}\n{slug}\n"
        f"{hashlib.sha256(body).hexdigest()}"
    ).encode("ascii")
    return {
        "X-Request-Timestamp": ts,
        "X-Request-Signature": base64.b64encode(
            private_key.sign(canonical)
        ).decode("ascii"),
        "X-Request-Context": slug,
    }
```

Sign the path you are about to put on the wire. If your HTTP client re-encodes
the URL, sign the re-encoded form — see GOTCHAS.md G1.

---

<!-- api-surface:start -->

## Public surface

Every name exported by `devauth`. Regenerate the list after changing `__all__`,
from this directory:

```bash
python3 -c "import devauth; print(chr(10).join(sorted(devauth.__all__)))"
```

| Name | Kind | Description |
| --- | --- | --- |
| `install_signed_request_auth` | function | Idempotent mount of the signed-request middleware. |
| `SignedRequestASGIMiddleware` | class | Pure ASGI middleware. Verifies signed requests, stays out of the |
| `ReplayCache` | class | Single-flight replay-protection cache. |
| `ReplayNonceStoreAdapter` | class | Bridge a coordination ``ReplayNonceStore`` to the middleware call site. |
| `verify` | function | Verify an Ed25519-signed request. |
| `VerifyResult` | class | Outcome of a verification attempt. |

<!-- api-surface:end -->
