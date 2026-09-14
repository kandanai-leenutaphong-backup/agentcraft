# Browser Authentication Design

This note describes the maintained `entra_auth` implementation, not a particular application's
deployment or a private-source comparison. The embedded [skill](../../GUIDE.md) and
[contract](README.md) are the portable integration entry points.

## Distribution Boundary

The repository's license governs its authored implementation. This note creates no additional
license grant or assumed copyright attribution. PyJWT, cryptography and optional Azure SDKs are
installed as dependencies under their own terms; their implementations are not copied here.
Customer tokens, tenant configuration, deployment receipts and source-review fingerprints are
not part of this distribution.

## Decisions Preserved

**No disabled mode.** Configuration must name a single tenant and valid audience. No `enabled`
switch or development header can manufacture a principal. A host with no configured resolver
must refuse access through its own authorization gate. A typo must not turn strict validation
into self-asserted identity.

**Caller kind is explicit policy.** Service-principal tokens can contain `oid`; requiring that
claim is not sufficient to identify a human. The validator considers `idtyp`, `scp` and `roles`.
An application caller needs an explicit service-principal grant and one of the required roles;
a human caller needs an allowed scope. Broad multi-tenant authority aliases are refused.

**Key staleness is bounded.** A refresh failure may use cached signing keys only within the
configured staleness ceiling. Indefinitely serving stale keys would prevent revocation from
taking effect. Cooldown and single-flight refresh behavior prevent a hostile key ID from
causing an unbounded number of discovery requests.

**Verified claims are not application authorization.** `VerifiedToken` contains reduced,
verified claims. The host maps it to its one principal model and separately enforces record
ownership. This library does not create an additional identity or ownership layer.

**Browser flow state has one owner.** PKCE verifier, state and nonce originate server-side.
The host owns secure cookies, callback routes, code exchange and the expiring store. Store
expiry is checked on read; delayed purging must not extend a session's validity.

**Refusal messages are constants.** Public errors are selected by reason code. A rejected token,
key identifier or claim value must not be interpolated into a response or log message.

## Verification

From the `browser` directory:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=python python3 -m pytest tests -q -p no:cacheprovider
```

Tests use injected key discovery, locally generated signing keys and fake stores. They cover
algorithm confusion, wrong issuers/audiences/tenants, expiry, caller policy, bounded key refresh,
PKCE flows and expiring records. Offline checks do not establish live tenant or storage access.
