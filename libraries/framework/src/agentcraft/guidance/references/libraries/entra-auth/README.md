# Entra Auth

Independent `entra-auth==1.0.0` distribution, public import `entra_auth`.
The [contract](src/entra_auth/README.md) and [provenance](src/entra_auth/PROVENANCE.md)
are preserved from the Investigation component at baseline
`00c76c6bb55190877c3d4d4b5b3a14e55bce2cb4`.

`EntraAuthConfig`, `TokenValidator`, PKCE helpers and expiring record stores retain their
existing API. The host owns callback routes, cookies, caller mapping and authorization.
No disabled mode, ambient tenant selection or access grant is introduced. The `table`
extra supports the existing injected Azure Table store; installation acquires no credential.

Tests: `uv run --project template_apps/investigation_app --locked python -B -m pytest libraries/entra-auth/tests`.
The app gate, browser-session and session-hardening suites also exercise this installed package.
Local/offline checks do not prove deployed Entra or live Azure Table behavior.
