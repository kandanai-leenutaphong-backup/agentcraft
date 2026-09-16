# Signed Dev Access

Independent `signed-dev-access==1.0.0` distribution, public import `signed_dev_access`.
The [contract](src/signed_dev_access/README.md) and [provenance](src/signed_dev_access/PROVENANCE.md)
are preserved from the Investigation component at baseline
`00c76c6bb55190877c3d4d4b5b3a14e55bce2cb4`.

Public API includes `install_signed_request_auth`, `SignedRequestASGIMiddleware`,
`verify`, `canonical_string` and replay-ledger types. The host supplies the public key,
identity factory, replay ledger and common authorization gate. Installation generates
no credential and enables no caller. Replay, expiry, tamper and body bounds are unchanged.

The selected client API/CLI formerly shipped with `devauth` now belongs here:
`sign_headers`, `load_private_key`, `RequestSigner`, `SignedResponse`, and optional
Chromium `BrowserSigning` / `install_request_signing` / `new_piloted_context`.
The [client guide](docs/skills/signed-dev-access.md) owns current usage, bounds,
private-file safeguards and `python -m signed_dev_access request`. CLI output is
metadata only; no key creation, header dumping or implicit request is retained.
The skill now contains guidance and its notice, not another verifier or replay cache.

Tests: `uv run --project template_apps/investigation_app --locked python -B -m pytest libraries/signed-dev-access/tests`.
Cross-contract store races are test-only dependencies on `entra_auth`, not a runtime edge.
Live proxy byte preservation and deployed Azure Table replay remain outside this migration.
Browser client checks use synthetic CDP sessions, not a new live Chromium acceptance run.
