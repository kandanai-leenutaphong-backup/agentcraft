# API Authentication And Compatibility

The API validates incoming tokens for its own audience; the client treats access tokens
as opaque. [Microsoft's access-token guidance](https://learn.microsoft.com/en-us/entra/identity-platform/access-tokens)
defines the issuer, audience and signature responsibility. MSAL acquires tokens; it is
not a drop-in incoming-access-token validator.

## Select An Implementation

- Prefer the hosting platform's authentication or a supported framework/JWT/OIDC stack
  when its accepted/rejected inputs and failure behavior meet the host's requirements.
- Keep identity mapping and per-record/listing authorization at the application boundary.
  A valid token, tenant membership or cloud role does not establish record ownership.
- Inject the approved tenant/audience and required scopes/roles. Do not discover trust
  from token headers or accept unverified identity headers.
- Keep credentials and tokens out of command arguments, logs and reports. The retained
  diagnostic reads a token from stdin or an operator-supplied private file.

## Preserved Contracts

| Package | Public Contract | Reason To Retain |
| --- | --- | --- |
| [API compatibility](../compatibility/api-auth/README.md) | `entraauth`, `Principal`, `OwnershipPolicy`, optional FastAPI integration | Existing signed-access composition and consumers expect these imports, statuses and ownership semantics |
| [Browser/session compatibility](../compatibility/browser-auth/python/entra_auth/README.md) | `entra_auth`, `VerifiedToken`, strict configuration, flow/store helpers | Neutral claims and fail-closed single-tenant behavior differ from the legacy API; not a rename |

Install only a required compatibility package into the consuming application's interpreter;
the packages remain independently installable under the consolidated skill. Skill discovery
alone does not install them. Their detailed guides and tests are preserved; no app source
is rewritten or implicitly enrolled in a new identity system.

**Legacy warning:** `entraauth` has a disabled development branch and warm-key-cache
fallback. Unrecognized `AUTH_ENABLED` values disable validation. Deployed hosts must call
`config.require_enabled()`. Never call that behavior fail-closed, and never use it to pass
acceptance. Prefer strict `entra_auth` for a new host that needs these compatibility helpers.

## Verification

From the consolidated skill root in an interpreter with the selected dependencies:

```bash
python3 compatibility/api-auth/tests/selftest.py
python3 compatibility/api-auth/examples/api.py
python3 -m pytest compatibility/browser-auth/tests -q -p no:cacheprovider
```

Positive and negative coverage must survive migration: own record allowed, another owner
hidden, shared record writes refused, listing filters enforced; missing/forged/expired or
wrong-audience/tenant tokens refused; `alg:none` and HS256 confusion refused before keys;
key rollover/cold-cache outage/staleness handled according to the chosen contract. Test
the real route signature and proxy boundary, not only direct validator calls.

The packages supply mechanisms, not independent human approval, refresh-token management,
automatic app registration or a complete frontend sign-in server. For the latter, read
[frontend sign-in](frontend-signin.md) and [Container Apps setup](container-apps.md).
