# Provenance — `signed_dev_access`

Adopted, not written here. This records where it came from, exactly which bytes were read,
what was taken, what was changed and why, and what was deliberately left behind.

## Origin

| | |
| --- | --- |
| Repository | `azure-hillclimbing-harness`, working copy at `/home/hanchoong/azure-agent-loop` |
| Revision | `b3ba7f485db7961a1f9a36bd32a7ab85808e8724` |
| Path | `hillclimber/reference_skills/harness/access/signed-dev-access` |
| Read | 2026-09-06 |
| Upstream package name | `devauth`, version `1.0.0` |

A byte-identical copy was held under `reference_skills/harness/access/signed-dev-access/`,
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

Verified 2026-09-06 at revision `b3ba7f485db7961a1f9a36bd32a7ab85808e8724`; the sibling
`entra-api-auth` and `bicep-managed-identity` boxes declare the same.

There is no `LICENSE` file anywhere in that repository — not at its root, not in the harness
tree, not in the box — and an earlier revision of this file drew the wrong conclusion from
that absence, recording that no licence obligation existed to carry forward. The frontmatter
declaration *is* the grant, and MIT's one condition is that the notice travels with the code.
It therefore travels here, reproduced in full:

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

**assumes:** no copyright holder is named in the upstream repository, so the line above
attributes the work to its authors rather than inventing a name. If upstream later publishes a
`LICENSE` naming one, this notice is replaced by that file's text verbatim.

Both repositories belong to the same author, and upstream's `README.md` states the intent
plainly — *"Copy it, run its selftest, use it. No imports from this repository, no dependencies
between boxes, no network access to the origin needed."* That intent and the MIT grant agree;
neither removes the obligation to carry the notice.

## Upstream files read, with hashes

SHA-256 of each upstream file as read. These are the inputs; none of them was copied verbatim.

| Upstream file | SHA-256 |
| --- | --- |
| `devauth/__init__.py` | `3fcbcf22fd865895fb77cc74c0172af5eda47f18f64de31ea2607c6a5d864947` |
| `devauth/_middleware.py` | `b1bccf753143cfb2fe740012e8434bf2597eb995a91bbbf24f93177635ba2ba3` |
| `devauth/_verifier.py` | `349420474a4539621f7ef31f10f61d944b653837aade51143daab6ce2d358200` |
| `scripts/dev_sign.py` | `20e8d7230fa90beff6c452683180178256d0f8f0ea021cc5d98c1f394e8ba038` |
| `examples/browser_pilot.py` | `bee1aeeabf90bfa5f96143d37f56d339d1a757c27a593ac23f0ae78b2b2ea4e1` |
| `examples/fastapi_adapter.py` | `83e4cd7d43ce205106351bf67e7ace578ddecfe9cc93e6fbb9975a8f0ea11315` |
| `tests/selftest.py` | `aaad3261a2c46e911ab7baa3b75e184cd92b5e400fde67f255c1f849e46c5fe2` |
| `tests/test_middleware.py` | `856e8ea3cb7e2b14778e864b4c72a4134d62cfa3ddaa05d3fdd76dbb2ea572b8` |
| `tests/test_roundtrip.py` | `642f9e529e53a6fb41ad19df8f9ad75612f0c1e007c412a47a1b459be54a5d18` |
| `tests/test_verifier.py` | `16a88d7d080bcbf17f1c74800e1bb05e55f148605235ca42523d9e4958ec5a59` |
| `WIRE_CONTRACT.md` | `9406d40fed7c680505dd35a5c2b7d555580091285b9f3379d658cddd02dcf846` |
| `GOTCHAS.md` | `e63f47d65e76ea5bca8ab569e432551a4c4e70f2b4ca7229be0844c15c6b6b73` |
| `README.md` | `79c7fe0b377a37bfaa2d36b092258b5add709249f2375f8408c30b4b4799bcd8` |
| `SKILL.md` | `7543e31f9a68e2cea5110abbac9c8ba77d162e5648cc959349eb3e79e9adfa6e` |
| `requirements.txt` | `554528b97532a94d2e03e16155da116b092bdb7c3f160c7014d182c91ca34945` |
| `.gitignore` | `862263fa1f46c20f0d1e4dac5ffcc75abd55c08211b2c3864c5f8764b9d87793` |

Reproduce with:

```bash
cd reference_skills/harness/access/signed-dev-access && find . -type f | sort | xargs sha256sum
```

## Taken unchanged

The **wire contract** is preserved byte for byte, so a client written against the upstream
document authenticates here and vice versa:

- the three header names, `X-Request-Timestamp`, `X-Request-Signature`, `X-Request-Context`;
- the five-field newline-delimited canonical string, in the same order, ASCII-encoded;
- reconstruction of the path from ASGI `raw_path` rather than the decoded `path`;
- the 300-second skew window, module-private with no environment override;
- the slug allowlist `^[a-z0-9_-]{0,64}$`, applied after strip-and-lowercase;
- the bare-401 failure shape, and the rule that nothing in the component logs;
- the pure-ASGI middleware shape and single body replay, delegating later `receive` calls to
  the real transport so genuine disconnects still reach the framework;
- the identity-factory seam and the ASGI scope hand-off.

## Changed, and why

Each of these is a defect found by reading the upstream code against this deployment, not a
matter of taste. Upstream documents the first as a known limitation; the rest are new.

| Change | Why |
| --- | --- |
| **The replay ledger key is `sha256(decoded signature)`, not the base64 header text.** | Sixty-four bytes encode as 88 base64 characters whose 86th carries four ignored bits, so sixteen distinct texts decode to the same signature. Upstream's `ReplayCache` keys on the header string and therefore admits fifteen replays of a signature it has already accepted. Proved and regression-tested in `test_a_re_encoded_replay_is_refused`. |
| **Retention runs to `signed timestamp + 300 s`.** | Upstream's TTL is 300 s from first sight, and its own `WIRE_CONTRACT.md` claims the TTL "must equal the skew window exactly". It does not: the window is two-sided, so a timestamp 300 s in the future stays verifiable for 600 s from now, and the entry is evicted with 300 s of validity left. `VerifyResult.expires_at` now carries the instant after which the signature can never verify, and the ledger holds the key until then. |
| **`replay_ledger` is a required argument; the module-level default cache is gone.** | Upstream defaults to a shared per-process `ReplayCache`. On a deployment with `maxReplicas: 2` that is replay protection in name only, and nothing tells the operator. Requiring the argument turns a silent hole into a decision that has to be made and recorded. |
| **`ReplayLedger` is an async protocol with two implementations, one durable.** | Upstream leaves the distributed case as a documented seam (`ReplayNonceStoreAdapter`) with no implementation. `AzureTableReplayLedger` fills it using the atomic entity-insert conflict, and `InProcessReplayLedger` declares `durable = False` so a composition root can refuse it where it does not fit. |
| **A full in-process ledger raises instead of evicting.** | Upstream evicts opportunistically. Evicting a key whose signature still verifies reopens the hole under exactly the memory pressure an attacker can produce; refusing is the conservative direction. |
| **Duplicated signing headers are refused.** | Upstream's `_header` returns the first match. Proxies disagree about which duplicate wins, so a request whose signed material is ambiguous was being resolved by guessing. |
| **The request body is capped at 1 MiB and 4096 chunks.** | Upstream buffers the whole body before verifying anything, so an unauthenticated caller can spend unbounded server memory; a malformed chunked stream of empty chunks never terminates at all. |
| **Header and path lengths are bounded before parsing.** | Same class of problem, cheaper to exploit: an oversized header bought parsing work before any check. |
| **A non-ASCII field is refused rather than raised.** | Upstream's `_canonical` calls `.encode("ascii")` outside any `try`, so a raw path with a byte above 127 produces `UnicodeEncodeError` — an HTTP 500 where the contract promises a 401. |
| **Constructing the middleware with an empty key raises.** | Upstream documents as gotcha G11 that the empty-key off switch lives in the installer, not the class, so direct construction with no key rejects everything instead of passing through. Raising removes the trap. |
| **`http.disconnect` during the body read returns without a response.** | Upstream sends a 401 to a client that has already gone. |
| **The 401 carries `Cache-Control: no-store, private`.** | A refusal cached by a shared proxy is a refusal served to the wrong person later. |
| **The default scope key is `auth_principal`, not `devauth_user`.** | This application has one principal model. Two mechanisms writing two scope keys is how an ownership check ends up reading the wrong one. |
| **`public_key_fingerprint` added.** | Identities are namespaced `devkey:<fingerprint>:<slug>`, so rotating the key retires exactly the identities it minted rather than silently transferring them to the new one. |
| **`canonical_string` is exported.** | Three client implementations exist (the Python CLI, the Node browser pilot, and the verification battery). Exporting the primitive lets `deploy/verify_signed_access.py --self-test` prove all three produce the same bytes as the server, rather than assuming it. |

## Deliberately not adopted

- **`examples/fastapi_adapter.py`** — the identity seam is written for this application in
  `app/cybereye/backend/security/composition.py`, against this repository's `Principal`.
- **`scripts/dev_sign.py`** — replaced by `deploy/devauth_cli.py`, which keeps the wire
  contract and adds a project-scoped key path, a refusal to write inside any working tree, a
  refusal to follow redirects with signing headers attached, a refusal to sign plaintext to a
  remote host, monotonic timestamps, and a body cap matching the server's.
- **`examples/browser_pilot.py`** — replaced by `deploy/browser_pilot.py` and
  `deploy/browser_pilot.mjs`. Upstream signs only paths under an `api_prefix`, which cannot
  work here: the authorization gate protects the document and every asset too. The
  replacements sign all same-origin requests, strip signing headers from anything leaving the
  origin, and force cache revalidation.
- **`ReplayNonceStoreAdapter`** — an adapter over an interface that upstream never defines.
  `ReplayLedger` is that interface, so the adapter has nothing left to bridge.
- **Upstream's `tests/`** — three pytest modules and a framework-free `selftest.py`. This
  repository runs `unittest`, and the invariants they cover are reimplemented and extended in
  `app/components/tests/test_signed_dev_access_auth.py`, which adds the cases the changes above
  exist for.
- **`SKILL.md`, `README.md`, `WIRE_CONTRACT.md`, `GOTCHAS.md`** — the durable content is folded
  into this component's `README.md`. The originals remain readable at
  `reference_skills/harness/access/signed-dev-access/`.
