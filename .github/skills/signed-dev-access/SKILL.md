---
name: signed-dev-access
description: "Use when piloting deployed apps through browser and API with Ed25519 request signing, or diagnosing signed-request 401s. Agent identity, auth intact. Never disable auth or add bypass headers."
license: MIT
---

# Signed dev access

Remote-pilot a running application: drive the UI, call the API, exercise real
functionality, read back what happened - auth fully intact. The agent
authenticates as itself against the same deployment real users hit.

Second credential path alongside production auth. Separate identity, no shared
secret, revocable by clearing one env var, not mounted when the key is unset.

Use instead of: a bypass header, a disabled-auth flag, a shared service account,
a non-prod environment with auth off. All four also destroy the thing being
tested - an app with auth off is not the app users get.

## Decide in one line

| Situation | Action |
| --- | --- |
| Agent must call live endpoints | Install this box |
| Agent must drive the UI in a browser | Install, then `examples/browser_pilot.py` |
| Piloted browser requests 401 | Static headers cannot work; sign per request |
| Live signed probe returns 401 | Read GOTCHAS.md, start at G10 |
| Streaming endpoint hangs after mounting | G7 |
| 500 instead of 401 on odd input | G4 |
| Writing a client in another language | WIRE_CONTRACT.md only |
| Cutting over to production | Removal, below |

## Install

Resolve `SKILL_ROOT` to this client-managed skill directory. Plugin installation does not generate
a key, enable agent access or install Python packages into the consuming application. Key creation
and deployment of its public half require explicit operator approval. Runtime configuration and
private keys stay outside the plugin and repository.

Server, three steps:

```bash
cp -r "$SKILL_ROOT/devauth" <your-app>/
python3 -m pip install -r "$SKILL_ROOT/requirements.txt"
```

```python
# composition root, next to your existing auth wiring
from devauth import install_signed_request_auth

def _build_principal(slug: str):
    # YOUR identity type. This is the only integration point.
    return User(oid=f"devkey-{slug}" if slug else "__default__")

install_signed_request_auth(
    app,
    public_key_b64=os.environ.get("DEV_PUBLIC_KEY_ED25519", ""),
    identity_factory=_build_principal,
)
```

Your existing auth dependency reads `scope["devauth_user"]` and accepts it as an
authenticated principal when present. `examples/fastapi_adapter.py` is the worked
seam.

Client, two steps:

```bash
python3 scripts/dev_sign.py init        # writes ~/.devauth/dev_signing_key (0600)
                                        # prints DEV_PUBLIC_KEY_ED25519=...
# set that value as a plain env var on the deployed app, then restart
```

## Use

Pilot the API:

```bash
export APP_URL=https://your-app.example.com

python3 scripts/dev_sign.py request GET /api/sessions

echo '{"content":"hi"}' | python3 scripts/dev_sign.py request POST /api/chat/abc

python3 scripts/dev_sign.py sign GET /api/sessions      # emit headers only
python3 scripts/dev_sign.py pubkey                      # re-read public key
```

`request` exits non-zero on any non-2xx, so it composes into CI and regression
scripts directly. Streaming endpoints flush line by line, so the agent observes
progress as it happens.
Pilot the UI:

```python
from browser_pilot import install_request_signing   # examples/

install_request_signing(context, api_prefix="/api")   # Playwright context
page.goto("https://your-app.example.com/")
page.get_by_role("button", name="Run scan").click()
```

Static headers cannot work: the signature covers method, path and body, so one
header set is valid for at most one request. Each request is signed at the
network layer instead. Use `sign_headers()` from `scripts/dev_sign.py` for
anything other than Playwright.

Then observe. Assert on DOM state and API responses, never on a screenshot - a
captured frame can lag the live DOM. Confirm side effects from the server, not
from the UI element that triggered them.

## Verify the box itself

```bash
python3 tests/selftest.py         # 25 checks, no pytest needed, non-zero on failure
python3 tests/test_roundtrip.py   # proves the CLI signs what the verifier accepts
python3 -m pytest tests/ -q       # full suite (needs pytest, pytest-asyncio)
```

`selftest.py` and `test_roundtrip.py` need only `cryptography`. Run them first in
any new environment: passing means the box is functional there.

## The five rules

1. **Sign the raw wire path**, not the decoded one (G1).
2. **Skew and TTL are constants**, never configuration. An attacker who can
   influence config must not be able to widen the replay window.
3. **Never log anything** in the verifier or middleware, at any level. A failed
   verification must look identical to no attempt, including in your own logs.
   Diagnostics on the failure path destroy the property that makes this safe to
   leave mounted.
4. **Validate the slug at the boundary** (G4). Unvalidated identity input turns
   an auth path into a crash class.
5. **Public key is not a secret.** Plain env var, never a vault entry. Rotation
   is: generate, set, restart.

## Removal at production cutover

1. Clear `DEV_PUBLIC_KEY_ED25519`. The middleware stops mounting; the ASGI stack
   becomes byte-identical to a build without this box.
2. Delete the `devauth/` package and `scripts/dev_sign.py`.
3. Delete the `install_signed_request_auth` call and the identity factory.
4. Delete the local private key.

Steps 2–4 are optional; step 1 is sufficient and instantaneous.

## Reference

- `README.md` — threat model, design rationale, remote piloting, portability
- `WIRE_CONTRACT.md` — the exact signed bytes; all a new client needs
- `GOTCHAS.md` — twelve production failures, symptom-first
- `examples/fastapi_adapter.py` — the identity-injection seam, worked
- `examples/browser_pilot.py` — per-request signing for a piloted browser
