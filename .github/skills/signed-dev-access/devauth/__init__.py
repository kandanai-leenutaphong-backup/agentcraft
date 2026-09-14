"""devauth — Ed25519 signed-request authentication for coding agents.

WHY THIS EXISTS
---------------
A coding agent cannot drive a deployed application it cannot authenticate
to. The tempting shortcuts all weaken production: a shared bypass header,
a disabled auth flag, a service account with a static password, or
``AUTH_ENABLED=false`` in a non-prod environment that later ships.

This package is the principled alternative. It adds a SECOND, independent
credential path alongside the primary one:

  - separate identity (a keypair, not a shared secret);
  - the private half never leaves the operator machine;
  - the public half is not a secret and travels as a plain env var;
  - revoked by clearing one env var — no code change, no redeploy of the
    primary auth path;
  - not mounted at all when the key is unset, so a build without the key
    has a byte-identical ASGI stack.

DOMAIN-BLIND BY CONSTRUCTION
----------------------------
This package owns crypto and transport only: canonical-string
reconstruction, Ed25519 verification, replay rejection, and the bare-401
failure shape. It does NOT know your identity type. The consumer injects
``identity_factory(slug) -> principal``; the verified principal is
attached to ``scope["devauth_user"]`` where the application's existing
auth dependency reads it. That injection is the only integration point,
and it is why this box moves between projects unchanged.

PUBLIC SURFACE
--------------
``install_signed_request_auth(app, *, public_key_b64, identity_factory,
replay_cache=None, scope_key="devauth_user")``
    Idempotent mount. No-op when ``public_key_b64`` is empty.

``SignedRequestASGIMiddleware``
    The ASGI middleware class, for consumers that construct it directly.

``ReplayCache``
    Per-process single-flight replay cache. The default.

``ReplayNonceStoreAdapter``
    Opt-in bridge to a durable, shared nonce store. Closes the
    cross-replica replay gap described in GOTCHAS.md (G6).

``verify`` / ``VerifyResult``
    The pure verifier primitive. No I/O, no logging, security-critical.

DEPENDENCIES
------------
Standard library plus ``cryptography``. Nothing else. No web framework is
imported: the middleware is pure ASGI and works under any ASGI server.

READ NEXT
---------
``README.md`` for the threat model, install, and removal procedure.
``WIRE_CONTRACT.md`` for the exact bytes that get signed.
``GOTCHAS.md`` for the failures that cost real time to rediscover.
"""

from ._middleware import (
    ReplayCache,
    ReplayNonceStoreAdapter,
    SignedRequestASGIMiddleware,
    install_signed_request_auth,
)
from ._verifier import VerifyResult, verify

__all__ = [
    "install_signed_request_auth",
    "SignedRequestASGIMiddleware",
    "ReplayCache",
    "ReplayNonceStoreAdapter",
    "verify",
    "VerifyResult",
]

__version__ = "1.0.0"
