"""Ed25519 signed-request access — a second credential path that weakens no primary one.

A coding agent cannot drive a deployed application it cannot authenticate to, and every
tempting shortcut weakens production: a shared bypass header, a disabled-auth flag, a service
account with a static password. This component is the alternative:

- a separate identity, a keypair rather than a shared secret;
- the private half never leaves the operator machine;
- the public half is not a secret and travels as a plain environment variable;
- revoked by clearing that one variable, with no code change and no effect on the primary
  authentication path;
- not mounted at all when the variable is empty, so a build without it has no signed
  authorizing path whatsoever.

**Domain-blind by construction.** This component owns canonical-string reconstruction,
verification, replay rejection and the bare-401 failure shape. It knows nothing about the
consuming application's identity type: the consumer injects ``identity_factory(slug)`` and the
resulting principal is attached to ``scope["auth_principal"]``, where the application's own
authorization gate reads it. That injection is the whole integration surface.

Public surface
--------------
``install_signed_request_auth(app, *, public_key_b64, identity_factory, replay_ledger,
scope_key="auth_principal", max_body_bytes=MAX_SIGNED_BODY_BYTES) -> bool``
``SignedRequestASGIMiddleware`` — the middleware class, for direct construction.
``verify`` / ``VerifyResult`` / ``canonical_string`` / ``public_key_fingerprint`` — the pure
verification primitives.
``ReplayLedger`` / ``InProcessReplayLedger`` / ``AzureTableReplayLedger`` /
``ReplayLedgerUnavailable`` / ``claim_or_deny`` — the shared claim-once store and its
implementations.
``TIMESTAMP_HEADER`` / ``SIGNATURE_HEADER`` / ``CONTEXT_HEADER`` / ``MAX_SKEW_SECONDS`` /
``MAX_SIGNED_BODY_BYTES`` — the wire constants.

Dependencies are ``cryptography`` and the standard library. No web framework is imported: the
middleware is pure ASGI. ``AzureTableReplayLedger`` imports the Azure SDK lazily, so a
deployment that configures a different ledger never needs it installed.

Contract: ``README.md``. Origin and what changed: ``PROVENANCE.md``.
"""

from ._middleware import (
    CONTEXT_HEADER,
    DEFAULT_SCOPE_KEY,
    MAX_SIGNED_BODY_BYTES,
    MAX_SIGNED_BODY_CHUNKS,
    SIGNATURE_HEADER,
    TIMESTAMP_HEADER,
    SignedRequestASGIMiddleware,
    install_signed_request_auth,
)
from ._replay import (
    AzureTableReplayLedger,
    InProcessReplayLedger,
    ReplayLedger,
    ReplayLedgerUnavailable,
    claim_or_deny,
)
from ._verifier import (
    MAX_SKEW_SECONDS,
    VerifyResult,
    canonical_string,
    public_key_fingerprint,
    verify,
)
from ._client import RequestSigner, SignedResponse, SigningError, load_private_key, sign_headers
from ._browser import BodyNotSignable, BrowserSigning, install_request_signing, new_piloted_context, request_body

__all__ = [
    "install_signed_request_auth",
    "SignedRequestASGIMiddleware",
    "verify",
    "VerifyResult",
    "canonical_string",
    "public_key_fingerprint",
    "ReplayLedger",
    "InProcessReplayLedger",
    "AzureTableReplayLedger",
    "ReplayLedgerUnavailable",
    "claim_or_deny",
    "TIMESTAMP_HEADER",
    "SIGNATURE_HEADER",
    "CONTEXT_HEADER",
    "DEFAULT_SCOPE_KEY",
    "MAX_SKEW_SECONDS",
    "MAX_SIGNED_BODY_BYTES",
    "MAX_SIGNED_BODY_CHUNKS",
    "SigningError",
    "load_private_key",
    "sign_headers",
    "RequestSigner",
    "SignedResponse",
    "BodyNotSignable",
    "BrowserSigning",
    "install_request_signing",
    "new_piloted_context",
    "request_body",
]

__version__ = "1.0.0"
