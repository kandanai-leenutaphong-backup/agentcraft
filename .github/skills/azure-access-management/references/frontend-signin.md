# Native Frontend Sign-In And The Investigation App

Source assessment: 2026-09-15, read-only. The investigation application's `entra_auth`
component was intended for browser sign-in, but it supplies only mechanisms. The host
owns the working sign-in sequence. No application source or deployment is changed by
the skill consolidation.

## Observed Host Contract

| Surface In The Investigation App | Actual Responsibility |
| --- | --- |
| `app/components/entra_auth` | Strict token validation, JWKS, PKCE/state/nonce/URL helpers, opaque identifiers and expiring in-process/Table stores; no HTTP routes or cookies |
| `app/cybereye/backend/security/signin_routes.py` | `/auth/login`, `/auth/callback`, `/auth/session`, `/auth/signed-out`; browser code redemption for its SPA redirect, flow checks and session minting |
| `app/cybereye/backend/security/entra.py` | Bearer/cookie resolvers, `BrowserSessions`, expiry/revocation and `CookieCrossSiteGuard`; neutral claims mapped into one host principal |
| `app/cybereye/backend/security/composition.py` | Default-deny gate, permitted sign-in routes, resolvers and authorization composition |
| `app/cybereye/frontend/src/shared/api/api.ts` | 401 navigation to the login route and POST logout before provider sign-out |

The component's Python source matches the retained
[strict compatibility package](../compatibility/browser-auth/python/entra_auth/README.md).
The application imports its own component, not a source skill path. Its provenance now
points to that retained owner; deleting old skill folders does not replace the app's code.

## Native Alternative

[Easy Auth](https://learn.microsoft.com/en-us/azure/container-apps/authentication) can own
provider redirects, token validation, authenticated sessions and identity headers for the
private frontend. Use its `/.auth/*` routes and `RequireAuthentication` when the host's
requirements fit. [MSAL Python](https://learn.microsoft.com/en-us/entra/msal/python/getting-started/acquiring-tokens)
provides supported client flows when an application owns sign-in; it does not remove the
API's validation and authorization duties.

Native is preferable to custom protocol code, but not a drop-in replacement here:

- The observed host uses public-client PKCE and a SPA callback, without a client secret.
  The documented Easy Auth web-provider configuration may require confidential-client
  credentials; explicitly compare current supported configuration and Key Vault handling.
- The host uses a custom signed-agent path. Provider-token headless auth can work through
  native enforcement, but custom signatures are verified only after reaching application code.
- The frontend expects API 401s and a specific host login/logout contract. Platform routes
  and global redirect behavior require coordinated frontend/backend changes.
- The host revokes its own session before provider logout and limits session life by token
  expiry and its configured ceiling. Native cookie, refresh and revocation parity is unknown.
- The host uses managed-identity Table storage. Native session/token-store availability,
  replica behavior and network/identity requirements require live verification.

## Migration Acceptance

Keep these as a separate authorized application change, not a folder cleanup:

1. Own the frontend and API auth contract together, including registration platform,
   callbacks, sign-out, `whoami`, cookies and persisted session/owner identifiers.
2. Verify the actual gate protects assets, APIs and unknown paths, with no prefix-matching
   public-path escape or direct-origin bypass. Reject forged platform identity headers.
3. Test missing/invalid/expired tokens, wrong tenant/audience/scope, invented/revoked cookies,
   foreign `return_to`, invalid callback state and replayed flows.
4. Test Secure/HttpOnly/SameSite cookie attributes, no-store responses, unsafe cross-site
   requests and forms, session lifetime and logout read-back using a fresh browser URL.
5. Verify any custom signed path's method/path/body integrity, expiry and replay defense
   against the deployed proxy and replica arrangement. Both callers reach the same policy.
6. Only then retire obsolete host routes, flow/session stores or the copied component.

Offline helper tests are retained. The actual frontend workflow, native migration and
live auth configuration remain under Pending Testing; no user interface test is claimed
from preserving package tests or reading Microsoft documentation.
