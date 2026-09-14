"""entra_composition — compose signed dev access with the entra-api-auth box.

The two boxes are deliberately independent: `devauth` knows crypto and
transport, `entraauth` knows tokens and ownership, and neither imports the
other. Composition is the consumer's job, and it is this file — about ten lines
of substance, kept as an example precisely so it stays optional.

WHAT THE SEAM ACTUALLY IS
-------------------------
Two constants have to agree, and by default they do not:

    devauth  attaches its principal to  scope["devauth_user"]
    entraauth reads its principal from  scope["auth_principal"]

So a signed request verifies, attaches a principal nobody reads, and the Entra
dependency then asks for a bearer token that an agent does not have. The symptom
is a 401 on a request whose signature was perfectly valid.

The fix is to name the key once and hand back the type the other side already
understands:

    scope_key       = ea.DEFAULT_SCOPE_KEY        (not devauth's default)
    identity_factory returns ea.Principal(...)    (not a local User)

`entraauth.principal_dependency` checks `isinstance(existing, Principal)` before
trusting a scope value, so returning anything else fails closed — silently, and
looking exactly like a missing token.

WHAT THIS DELIBERATELY DOES NOT DO
----------------------------------
The principal it mints carries **no scopes and no roles**. A signed request is
proof that the operator's private key signed it; it is not a grant. Every
`require_scope`/`require_role` guard therefore refuses it by default, and
ownership applies to it exactly as to a human: `devkey-alice` may read
`devkey-alice`'s records and gets 404 for anyone else's. Handing this identity a
blanket role would turn a debugging affordance into the widest credential in the
system.

`kind` is `service`, because no human is behind the call, and `kind_certain` is
True, because this box knows what it minted.

WHERE TO PUT IT
---------------
The composition root of your application, next to where you build the FastAPI
app — never inside a capability. See `fastapi_adapter.py` for the
framework-neutral version that keeps your own principal type.
"""

from __future__ import annotations

import os
from pathlib import Path

from devauth import install_signed_request_auth


def entraauth_path() -> Path:
    """Directory holding the explicitly installed optional `entraauth` package."""
    return Path(_import_entraauth().__file__).resolve().parent.parent


def _import_entraauth():
    try:
        import entraauth
    except ModuleNotFoundError as error:
        if error.name != "entraauth":
            raise
        raise ModuleNotFoundError(
            "Optional composition needs entraauth installed in this interpreter. "
            "Install the entra-api-auth Python package explicitly; sibling skills "
            "and ENTRA_API_AUTH_PATH are not searched."
        ) from error
    return entraauth


# Namespacing keeps signed-access principals distinguishable from real Entra
# object ids in logs, in storage, and in an audit trail after the fact.
OID_PREFIX = "devkey-"
DEFAULT_SLUG = "default"


def principal_for_slug(slug: str):
    """Map a verified context slug to an `entraauth.Principal`.

    The slug arrives verified and normalised — lowercase, stripped, matched
    against `[a-z0-9_-]{0,64}`. Empty means the caller sent no context header,
    which maps to one shared identity rather than to an unowned one.
    """
    ea = _import_entraauth()
    name = slug or DEFAULT_SLUG
    return ea.Principal(
        id=f"{OID_PREFIX}{name}",
        name=f"signed dev access ({name})",
        kind=ea.KIND_SERVICE,
        kind_certain=True,
        scopes=(),
        roles=(),
        claims={"devauth_slug": name},
    )


def install(app, *, public_key_b64: str | None = None) -> bool:
    """Mount signed dev access so `entraauth` reads its principal. Idempotent.

    Returns True when mounted. An empty key is the off switch: nothing enters
    the ASGI stack, so a deployment without the key is byte-identical to one
    built without this file.

    Args:
        app: The FastAPI/ASGI application.
        public_key_b64: The operator's Ed25519 public key. Defaults to
            `DEV_PUBLIC_KEY_ED25519` from the environment.
    """
    ea = _import_entraauth()
    key = (public_key_b64 if public_key_b64 is not None
           else os.environ.get("DEV_PUBLIC_KEY_ED25519", ""))
    return install_signed_request_auth(
        app,
        public_key_b64=key,
        identity_factory=principal_for_slug,
        scope_key=ea.DEFAULT_SCOPE_KEY,
    )


__all__ = ["install", "principal_for_slug", "entraauth_path",
           "OID_PREFIX", "DEFAULT_SLUG"]
