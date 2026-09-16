# Provenance — `entra_auth`

Adopted, not written here. This records where it came from, exactly which bytes were read,
what was taken, what was changed and why, and what was deliberately left behind.

## Origin

| | |
| --- | --- |
| Repository | `azure-hillclimbing-harness`, working copy at `/home/hanchoong/azure-agent-loop` |
| Revision | `b3ba7f485db7961a1f9a36bd32a7ab85808e8724` |
| Path | `hillclimber/reference_skills/harness/access/entra-api-auth` |
| Read | 2026-09-06 |
| Upstream package name | `entraauth` |

A byte-identical copy was held under `reference_skills/harness/access/entra-api-auth/`,
verified with `diff -rq` on the date above. The expanded reference tree was retired on
2026-09-13; Git history and the verified private cleanup archive retain that snapshot.
Commands below record the original comparison, not a dependency on a current reference checkout.

**This is a copy, not a dependency.** Nothing here imports, links to, builds against or
downloads from that repository, and no such edge may be added. The component is verified by
this repository's own tests and moves with this repository.

## Licence — MIT

**The upstream box is licensed MIT**, declared in the YAML frontmatter of its `SKILL.md`:

```yaml
license: MIT
```

There is no `LICENSE` file anywhere in that repository. The frontmatter declaration is the
grant, and MIT's one condition is that the notice travels with the code, so it travels here:

```
MIT License

Copyright (c) the authors of azure-hillclimbing-harness

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

**assumes:** no copyright holder is named upstream, so the line above attributes the work to
its authors rather than inventing a name. If upstream publishes a `LICENSE` naming one, this
notice is replaced by that file's text verbatim. The same correction was applied to
`app/components/signed_dev_access/PROVENANCE.md`, which had recorded that no obligation
existed.

## Upstream files read, with hashes

SHA-256 of each upstream file as read. These are the inputs; **none of them was copied
verbatim** — every module here was rewritten against them.

| Upstream file | SHA-256 |
| --- | --- |
| `.gitignore` | `599e8d09a18b6bac6f70ed12bf96f67e49c4d992ee2601bc173d92fbcb64b11d` |
| `CONTRACT.md` | `d094fdc3f02a6ebb4e2fefd43b6187bf09255740ea4690d307e9ac9ffac4d7e5` |
| `GOTCHAS.md` | `d6cf4b1c561d2c292cb874b5e7ee07ff331bcda0244c9f10af2a824c98c16535` |
| `README.md` | `04f7c0cdf1fcf1fa58c6be5276c50d62111a88fdabced7d0bbd82996d86c0bb2` |
| `SKILL.md` | `6e7e4d35537aaaddeedef0913724ef8a171b5c111c5efec3ff13452cf4ce7c5e` |
| `entraauth/__init__.py` | `8c74b4c6c3fb860a1eda281ace2d256d2d8acf2eb0918f2578063924df2b66e6` |
| `entraauth/_config.py` | `cdc91023f9e93090c8c081ff16e0bd91cbf1ed99f3cc535bad0a5040a8ed434c` |
| `entraauth/_errors.py` | `202b2249764af1d18139f4aa94468c781de38d861d3d4e141f2f39243bef2fbf` |
| `entraauth/_fastapi.py` | `d86c526b7337760ff770b45949086bdcc6941dd69f4af3717af70fbb55bd1bff` |
| `entraauth/_jwks.py` | `5334fdf6f494cbc4424bcb25d08a6d426c2742c28730420f71105529c8fa826c` |
| `entraauth/_ownership.py` | `9e4ba8b006c9ec95d03c9249c587f53b2752f7e2cef5ceafef368c5c0218f6ae` |
| `entraauth/_principal.py` | `cb032b606a788f6182da08efbd4efd6fbf0f4b664581345d617ed67c399b5a9f` |
| `entraauth/_validator.py` | `900c8ba943e2bc2f60583774bba5931a82188114e8a814119b1d3cd07f1f4c7b` |
| `examples/api.py` | `9d648c2f6c4911d86574156e3d851bad840501e45322d7842e9b1afbedc94981` |
| `requirements.txt` | `e6c375a67760515667885302586f995c9ef913e5c11e76a17d3a530898d22547` |
| `scripts/diagnose.py` | `3503d33c377289961e385e5e1ebb7fb232d2569875709e8b3e2483b7a4f7f7ab` |
| `tests/selftest.py` | `51b89a34621f868e52ca081fda72bd52dcbaf7483038b624632f1469d34ce537` |

Reproduce with:

```bash
cd reference_skills/harness/access/entra-api-auth && find . -type f | sort | xargs sha256sum
```

## What was taken

The **design**, not the text. Every module here is a rewrite against the upstream file of the
same role, keeping the decisions that were right and changing four that were not.

| This file | Upstream counterpart | Relationship |
| --- | --- | --- |
| `_config.py` | `entraauth/_config.py` | Same job, different trust model. See changes 1 and 2 |
| `_errors.py` | `entraauth/_errors.py` | Same rule kept verbatim in spirit: a public message is selected from a table by reason code, never built from input |
| `_jwks.py` | `entraauth/_jwks.py` | Same TTL / cooldown / single-flight policy, plus a staleness ceiling. See change 3 |
| `_validator.py` | `entraauth/_validator.py` | Same check order, cheapest first. Two checks added, one return type changed. See changes 2 and 4 |
| `_signin.py` | — | New. Upstream has no sign-in half at all |
| `_store.py` | — | New. Upstream keeps no server-side state |

## What was changed, and why

**1. There is no disabled mode.** Upstream carries `AuthConfig.enabled`, and with it a branch
that returns a `developer` principal built from `X-User-Id`, `X-User-Email` and `X-User-Name`.
That branch is genuinely useful for exercising ownership rules locally, and it is also a lever
whose accidental position is the open one. Its `from_env` reads:

```python
raw_enabled = (source.get(f"{prefix}ENABLED") or "").strip().lower()
enabled = raw_enabled in {"1", "true", "yes", "on"}
```

so **any unrecognised value — a typo, an empty string, `"enabled"` — yields `enabled=False`**,
which is the mode that grants every caller a self-asserted identity. Upstream's own `SKILL.md`
states this correctly; its `GOTCHAS.md` G11 states the opposite, claiming that "anything
unrecognised fails **closed** to enabled-and-strict". Measured against the source at the hash
above, **G11 is wrong and the `SKILL.md` is right.**

Neither behaviour is adopted. There is no `enabled` field, no development header branch and no
`developer` kind. A config either names a real tenant and a real audience or cannot be
constructed, and a deployment that does not configure Entra simply has no Entra resolver —
CyberEye's authorization gate then refuses everyone. `test_entra_auth.py` asserts the field
does not exist, and `test_authorization_gate.py` scans this repository's security package for
the names such a switch travels under.

**2. Single tenant, and caller kind is policy.** Upstream accepts `tenant_id="common"` and
hardens it with a key-issuer cross-check. This component refuses `common`, `organizations` and
`consumers` at construction: the data behind it belongs to one tenant. The cross-check is kept
anyway, because it costs one string comparison.

Upstream treats `required_claims=("oid",)` as the service-principal control, on the stated
premise that "an application authenticating as itself has **no `oid`**". **That premise is
false for v2 tokens**: a client-credentials token carries the service principal's own object
id, so requiring `oid` rejects nothing. This component decides caller kind from `idtyp`, `scp`
and `roles`, and refuses a service principal unless `allow_service_principals` is set *and* the
token carries one of `required_roles` — a configuration that itself refuses to be constructed
without those roles. A human must additionally hold one of `required_scopes`, default
`access_as_user`. `test_entra_auth.py` proves the `oid` premise wrong directly.

**3. Staleness is bounded.** Upstream's `JWKSCache._refresh` returns the cached set on any
fetch failure, with no age limit, for the life of the process. That converts a discovery
outage into indefinite acceptance of keys that may since have been revoked. Here a set older
than `jwks_max_stale_seconds` — six hours by default — fails closed with reason `jwks_stale`.

**4. The validator returns claims, not an identity.** Upstream returns its own `Principal` and
ships `_ownership.py` with `assert_readable` / `assert_writable`. CyberEye already has one
`Principal` and its own owner-bound `SessionStore` with the same 404-for-not-yours rule, and a
second identity type is how two ownership checks appear and the second one is wrong. This
component returns `VerifiedToken` — verified claims, reduced — and the application maps it in
`app/cybereye/backend/security/entra.py`, the same injection shape `signed_dev_access` uses.

## What was deliberately left behind

- **`entraauth/_fastapi.py`** — `install_auth`, `principal_dependency`, and the
  `/api/auth_setup` route. CyberEye authenticates at the ASGI edge, before routing, because a
  FastAPI dependency runs after routing, path parsing and body parsing, leaving all of that
  reachable to an anonymous caller. Its G13 annotation-rebinding fix is not needed here for the
  same reason: nothing in this component is a framework dependency.
- **`entraauth/_principal.py`** and **`entraauth/_ownership.py`** — see change 4.
- **`examples/api.py`** and **`scripts/diagnose.py`** — the equivalents live in
  `deploy/verify_entra_access.py`, which probes the deployed application with a real token and
  reports every reason a near-miss was refused.
- **`tests/selftest.py`** — its 144 offline checks were used as a specification, not copied.
  `app/components/tests/test_entra_auth.py` covers the same hostile cases (`alg: none`, HS256
  confusion with the published public key, foreign keys, foreign tenants, expiry in both
  directions, hostile key ids) plus the four changes above, in this repository's pytest style.

## Verified here

```bash
python3 -m pytest app/components/tests/test_entra_auth.py -q     # 68 checks, offline
python3 -m pytest app/cybereye/tests/test_entra_signin.py -q     # 43 checks, offline
```

Neither needs a tenant, a network or an Azure identity: the fetcher is injected and the signing
keys are minted in-process.
