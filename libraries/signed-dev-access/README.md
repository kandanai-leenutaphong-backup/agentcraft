# Signed Dev Access

Independent `signed-dev-access==1.0.0` distribution, public import `signed_dev_access`.
The [contract](src/signed_dev_access/README.md) and [provenance](src/signed_dev_access/PROVENANCE.md)
are preserved from the Investigation component at baseline
`00c76c6bb55190877c3d4d4b5b3a14e55bce2cb4`.

Public API includes `install_signed_request_auth`, `SignedRequestASGIMiddleware`,
`verify`, `canonical_string` and replay-ledger types. The host supplies the public key,
identity factory, replay ledger and common authorization gate. Installation generates
no credential and enables no caller. Replay, expiry, tamper and body bounds are unchanged.

Tests: `uv run --project template_apps/investigation_app --locked python -B -m pytest libraries/signed-dev-access/tests`.
Cross-contract store races are test-only dependencies on `entra_auth`, not a runtime edge.
Live proxy byte preservation and deployed Azure Table replay remain outside this migration.
