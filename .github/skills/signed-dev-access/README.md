# signed-dev-access

Lets a coding agent **remote-pilot a running application** — drive UI and API,
exercise real functionality, observe results directly — **while authentication
stays fully intact**.

The agent authenticates as itself via Ed25519 request signing, against the same
deployment real users hit. No auth disabled, no bypass shared, production
behaviour unchanged.

Self-contained. Copy this folder anywhere. Needs Python 3.10+ and
`cryptography`. No web framework imported.

```
signed-dev-access/
  README.md              you are here — threat model and rationale
  SKILL.md               agent-facing: decide, install, use, remove
  WIRE_CONTRACT.md       the exact signed bytes; all a new client needs
  GOTCHAS.md             ten production failures, symptom-first
  devauth/               the server half (~600 lines, pure ASGI)
    __init__.py            public surface + why it exists
    _verifier.py           pure crypto primitive, no I/O, no logging
    _middleware.py         ASGI middleware + replay cache
  scripts/
    dev_sign.py            the client half: keygen, sign, request, sign_headers
  examples/
    entra_composition.py   optional integration with an explicitly installed entraauth
    fastapi_adapter.py     the identity-injection seam, worked
    browser_pilot.py       per-request signing for a piloted browser
  tests/
    selftest.py            dependency-light end-to-end proof
    test_verifier.py       verifier invariants
    test_middleware.py     transport + replay + passthrough invariants
```

---

## 1. The problem

An agent that cannot authenticate cannot verify its own work: it writes code,
deploys, then asks a human whether the thing works. That breaks the only loop
that matters.

The capability unlocked is **remote piloting** — the agent operates the deployed
system as a user would and reads back what happened.
| What the agent does | What it needs |
| --- | --- |
| Drives the UI in a real browser as the operator | A session the app accepts |
| Calls the same endpoints the UI calls | An authenticated principal |
| Reads streamed responses as they arrive | Auth that does not buffer SSE (G7) |
| Asserts on real returned state, not mocks | The live deployment, not a stub |
| Reproduces a user-reported bug end to end | The same auth path users take |
| Confirms its own fix on the deployed build | To repeat all of the above, unattended |

Every step of that loop dies at the login screen, and every convenient fix for
the login screen weakens the system:

| Shortcut | What it actually costs |
| --- | --- |
| Shared bypass header | A single secret string, in shell history, CI logs, and screenshots. No identity, no revocation. |
| `AUTH_ENABLED=false` | A code path that behaves differently from production. It will ship one day. |
| Service account + password | A long-lived credential with production reach and rotation ceremony. |
| Non-prod with auth off | Two environments that are not the same environment. |

All four also destroy the thing being tested: an agent driving an app with auth
switched off is not exercising the app users get.

## 2. The approach

A **second, independent credential path** beside the primary one, unable to
weaken it.

| Property | How |
| --- | --- |
| Separate identity | A keypair, not a shared secret. Each operator holds their own. |
| Nothing to leak | The private half never leaves the operator machine (`0600`). The public half is not a secret. |
| Instant revocation | Clear one env var. No code change, no touching primary auth. |
| Zero footprint when off | With no key configured the middleware is not mounted; the ASGI stack is byte-identical to a build without this folder. |
| No production divergence | Primary auth is untouched and always active. This path is additive. |
| Silent under attack | Every failure is a bare 401 with no body and no log line, at any level. |

## 3. Threat model

**Protects against:** forged requests without the private key; tampered method,
path, body, or slug; replay outside a five-minute window; replay inside the
window against the same process; probing for the mechanism's existence via error
messages, timing hints, or log lines; widening the replay window through
configuration.

**Does not protect against:** an attacker holding the private key — treat it as a
production credential; replay inside the window against a *different* replica
(G6, documented seam); anything at all when the public key is misconfigured,
because the middleware then does not mount.

**Deliberate design choice.** Failure is indistinguishable from no attempt. No
reason codes, no `WWW-Authenticate`, no debug logging in verifier or middleware.
Cost: diagnostic difficulty (G10). Benefit: the mechanism is invisible to
probing, which is what makes it safe to leave mounted internet-facing.

## 4. Why it is portable

One decision: **the core never knows your identity type.**
```
your app  ──inject──>  identity_factory(slug) -> principal
                              │
devauth   ──verify──>  scope["devauth_user"] = principal
                              │
your existing auth dependency reads that key
```

The package owns crypto and transport: canonical-string reconstruction, Ed25519
verification, replay rejection, the 401 shape. It imports no domain type, no
framework, no configuration module. The consumer supplies one function.

That inversion is why this folder moves between projects unchanged; every other
property follows from it.

## 5. Design decisions worth keeping

- **Verifier isolated as a pure function.** No I/O, logging or state. A security
  review of the boundary fits on one screen; tampered-input tests are trivial.
- **Two bits cross the boundary.** `VerifyResult(ok, user_slug)`. No reason
  codes, so a caller — or an attacker — learns nothing from a `no`.
- **Generic header names.** Resembling AWS SigV4 and Stripe request signing.
  Nothing says `dev`, `key`, or `bypass` to someone reading captured traffic.
- **Skew is a private constant.** Configuration is attacker-influenced surface;
  the replay window must not be.
- **Pure ASGI, never `BaseHTTPMiddleware`.** The latter buffers responses and
  silently breaks streaming (G7).
- **Body replayed, disconnects delegated.** The first `receive` returns the
  buffered body; later calls fall through to the real transport so genuine
  `http.disconnect` still reaches the framework.
- **Activation gated twice.** Key configured *and* both headers present.
  Everything else passes straight through, no body read.
- **The replay gap is written down, not hidden.** `ReplayNonceStoreAdapter` is a
  seam with a named limitation, not a silent hole.

## 6. Remote piloting

The point of the box. Two modes, one credential.

**API piloting** - the agent calls endpoints directly and asserts on what comes
back:

```bash
python3 scripts/dev_sign.py request POST /api/situations/scan
```

Exit code is non-zero on any non-2xx, so a pilot script is a CI gate without a
wrapper. Streaming endpoints flush line by line, so the agent observes progress
as it happens.

**UI piloting** - the agent drives the real interface in a real browser while
every request the page makes carries a valid signature:

```python
from browser_pilot import install_request_signing   # examples/

install_request_signing(context, api_prefix="/api")
page.goto("https://your-app.example.com/")
page.get_by_role("button", name="Run scan").click()
```

Static headers cannot do this. The signature covers method, path, and body, so
one header set is valid for at most one request; the rest fail with a bare 401
that looks exactly like a logged-out session. Every request must be signed
individually at the network layer — what `install_request_signing` does.
`sign_headers()` in `scripts/dev_sign.py` is the public helper for anything other
than Playwright.

**Observation is the other half.** Authentication only opens the door; the loop
closes when the agent reads back what happened. Assert on DOM state and API
responses, never a screenshot - a captured frame can lag the live DOM. Confirm
side effects from the server, not the UI element that triggered them.

Unattended, this reproduces a user-reported bug end to end, fixes it, redeploys,
drives the same path again, and confirms the fix against the deployed build - all
through the auth path a real user takes, nothing disabled.

## 7. Quick start

```bash
pip install cryptography

python3 scripts/dev_sign.py init
# -> DEV_PUBLIC_KEY_ED25519=<base64>   (private key at ~/.devauth/, mode 0600)

# set that env var on the deployed app, wire install_signed_request_auth
# (see SKILL.md), restart, then:

export APP_URL=https://your-app.example.com
python3 scripts/dev_sign.py request GET /api/health
```

Prove the box works before trusting it:

```bash
python3 tests/selftest.py      # no pytest required; non-zero exit on failure
```

## 8. Provenance

Portable migration copied `core/skills/dep/signed-dev-access`; crypto and middleware
behavior are unchanged. `pyproject.toml` and `uv.lock` declare and lock runtime,
test and optional browser dependencies. Run from this directory:

```bash
uv sync --locked --no-install-project --extra test
.venv/bin/python tests/selftest.py
.venv/bin/python tests/test_roundtrip.py
.venv/bin/python -m pytest tests -q
```

The optional Entra composition example now imports an explicitly installed `entraauth`
package; it never searches sibling skills or `ENTRA_API_AUTH_PATH`. Install a reviewed
`entra-api-auth` directory into the same consumer interpreter before running that example
or `tests/browser_smoke.py`. The latter also needs the `browser` extra and matching Chromium.
No optional peer is required for the core selftest. The plugin adds no MCP server,
generates no operator key and enables no deployed access. Parked sources remain unchanged.

Extracted from a production deployment where it was the mechanism behind
agent-driven live regression: the agent piloted both the API and the operator UI
against the live service, and every entry in GOTCHAS.md was hit for real. The
hardening in G4 and G5 came from adversarial sweeps against the running service,
not from review.