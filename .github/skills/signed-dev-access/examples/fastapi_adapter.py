"""fastapi_adapter — the identity-injection seam, worked end to end.

This file is the ONLY code a consumer writes. Everything else in the box
is generic. Copy it, rename the identity type, delete the commentary.

The seam:

    devauth verifies the signature and hands over an opaque slug.
    You turn the slug into YOUR principal.
    devauth attaches it to scope["devauth_user"].
    Your existing auth dependency reads that key.

devauth never imports your identity type; you never touch its crypto.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from devauth import install_signed_request_auth

# Namespacing keeps signed-access principals distinguishable from real
# ones in logs and storage, so a stray dev session can always be attributed.
_DEFAULT_OID = "__default__"
_SLUG_OID_PREFIX = "devkey-"


@dataclass(frozen=True)
class User:
    """Stand-in for your application's existing principal type."""

    oid: str
    email: str = ""
    name: str = ""


def _build_user(slug: str) -> User:
    """Map a verified slug to a principal.

    The slug arrives already verified and normalised: lowercase, stripped,
    and matched against ``[a-z0-9_-]{0,64}``. An empty slug means the caller
    sent no context header, which maps to a shared default identity.
    """
    oid = f"{_SLUG_OID_PREFIX}{slug}" if slug else _DEFAULT_OID
    return User(oid=oid)


def install(app) -> bool:
    """Mount signed dev access. Returns True when actually mounted.

    Empty key is the off switch: nothing is added to the ASGI stack, so a
    deployment without the key behaves as if this file did not exist.
    """
    return install_signed_request_auth(
        app,
        public_key_b64=os.environ.get("DEV_PUBLIC_KEY_ED25519", ""),
        identity_factory=_build_user,
    )


# ---------------------------------------------------------------------
# Reading the principal in your existing auth dependency.
# ---------------------------------------------------------------------
#
# The middleware attaches to the raw ASGI scope rather than
# ``request.state`` so the contract does not depend on framework
# internals. A FastAPI dependency reads it like this:
#
#     from fastapi import Request, HTTPException
#
#     async def get_current_user(request: Request) -> User:
#         signed = request.scope.get("devauth_user")
#         if signed is not None:
#             return signed                    # signed-access path
#         return await verify_bearer_token(request)   # primary path
#
# Order matters only for clarity: the middleware has already returned 401
# for any request that presented signing headers and failed. Reaching this
# dependency with no ``devauth_user`` means no signing headers were sent,
# so the primary path is the correct fallback.
