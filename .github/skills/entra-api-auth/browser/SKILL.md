---
name: entra-browser-auth
description: "Use when Entra token validation must return neutral verified claims and support browser PKCE flows or expiring session/flow stores. This stricter API has no disabled-auth mode, distinguishes users from service principals, and leaves application identity and per-record authorization with the host."
---

# Entra Browser And Session Auth

This embedded capability extends `entra-api-auth`; it does not silently replace the existing
`entraauth` API or its principal model. Install this `browser` directory as `entra-browser-auth`
and import `entra_auth`. The [source contract](python/entra_auth/README.md) defines the claims,
PKCE helpers and expiring in-process/Azure Table stores. Existing consumers remain unchanged.

`EntraAuthConfig` is single-tenant, requires an audience and has no disabled mode. `TokenValidator`
returns `VerifiedToken`, not an application principal. Map it once at the host edge and separately
authorize record ownership. `new_flow` and `authorize_url` supply protocol data, not HTTP routes,
cookies or automatic token redemption. Refresh tokens and live auth deployment are not provided.

`python -m pytest "$SKILL_ROOT/tests" -q -p no:cacheprovider` with this capability's `python`
directory on `PYTHONPATH` exercises 68 offline positive/refusal cases. Injected keys and stores
require no tenant, cloud identity or live data. Choose one validator API deliberately for each host;
do not stack two validators or assume their return types and policies are interchangeable.