"""Who the caller is, once something has proved it.

One immutable record, produced by an authentication mechanism and consumed by everything
downstream. Routes receive this; they never see a header, a token, a signature or a claim.

Two mechanisms will produce it — signed developer access today, Microsoft Entra ID next — and
they converge on this one type on purpose. Two principal models means two ownership checks,
and the second one is always the one that is wrong.

Identifier namespaces are disjoint by construction:

    devkey:<key-fingerprint>:<slug>     signed developer access
    entra:<tenant-id>:<object-id>       Microsoft Entra ID

so a resource owned by a developer key can never be addressed by an Entra identity, and
revoking the key retires exactly the identities that key minted. No identifier here is ever
taken from a client-supplied header: an identity that asserts itself is not an identity.
"""

from __future__ import annotations

from dataclasses import dataclass

#: A human signed in through the primary identity provider.
KIND_USER = "user"
#: A non-human caller: automation, a coding agent, another service.
KIND_SERVICE = "service"

#: Issuers. The value records which mechanism believed the caller, not what it may do.
ISSUER_SIGNED_DEV = "signed-dev-access"
ISSUER_ENTRA = "entra"

_DEV_NAMESPACE = "devkey"
_ENTRA_NAMESPACE = "entra"
#: Slug used when a signed caller sent no context header.
DEFAULT_DEV_SLUG = "default"


@dataclass(frozen=True, slots=True)
class Principal:
    """An authenticated caller.

    Attributes:
        id: Stable, namespaced identifier. This is the owner key for anything the caller
            creates; nothing else is.
        kind: ``user`` or ``service``. Code that assumes a human — a per-user quota, an
            attribution line — must check rather than assume.
        issuer: The mechanism that authenticated this caller.
        display: Best available label. May be empty. Never used for authorization.
        tenant_id: Home tenant, when the issuer has one.
        scopes: Delegated permissions.
        roles: Assigned application roles.
    """

    id: str
    kind: str = KIND_USER
    issuer: str = ""
    display: str = ""
    tenant_id: str = ""
    scopes: tuple[str, ...] = ()
    roles: tuple[str, ...] = ()

    @property
    def is_signed_developer(self) -> bool:
        """True when this identity came from a developer signing key rather than a person."""
        return self.issuer == ISSUER_SIGNED_DEV

    def log_fields(self) -> dict[str, str]:
        """Identity fields safe to put in a log line. No display name, no tenant secret."""
        return {"principal_id": self.id, "principal_kind": self.kind, "issuer": self.issuer}


def signed_developer_principal(*, fingerprint: str, slug: str) -> Principal:
    """Build the principal a verified signature stands for.

    The fingerprint is part of the identifier so that rotating the signing key rotates the
    identities with it: sessions and cached results belonging to the retired key become
    unaddressable rather than inherited by the new one.
    """
    if not fingerprint:
        raise ValueError("a signed identity needs the fingerprint of the key that signed it")
    tag = slug.strip().lower() or DEFAULT_DEV_SLUG
    return Principal(
        id=f"{_DEV_NAMESPACE}:{fingerprint}:{tag}",
        kind=KIND_SERVICE,
        issuer=ISSUER_SIGNED_DEV,
        display=f"signed developer access ({tag})",
    )


def entra_principal(
    *,
    tenant_id: str,
    object_id: str,
    display: str = "",
    kind: str = KIND_USER,
    scopes: tuple[str, ...] = (),
    roles: tuple[str, ...] = (),
) -> Principal:
    """Build the principal a validated Entra token stands for.

    Provided here, unused today, so the identifier shape is fixed before the token validator
    exists rather than invented alongside it. The caller must have already verified the
    signature, issuer, audience and tenant of the token these values came from.
    """
    if not tenant_id or not object_id:
        raise ValueError("an Entra identity needs both a tenant id and an object id")
    return Principal(
        id=f"{_ENTRA_NAMESPACE}:{tenant_id}:{object_id}",
        kind=kind,
        issuer=ISSUER_ENTRA,
        display=display,
        tenant_id=tenant_id,
        scopes=scopes,
        roles=roles,
    )
