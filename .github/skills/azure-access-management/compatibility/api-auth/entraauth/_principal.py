"""Principal — who the caller is, once the token has been believed.

Module role:
    One small immutable record produced by validation and consumed by
    everything downstream. Routers receive this; they never see claims, headers
    or tokens.

Why a distinct type rather than the claims dict:
    A claims dict invites reaching for whatever field is convenient at the call
    site, and every such reach is an undocumented dependency on a token format
    you do not control. A named record makes the dependency explicit and keeps
    the claim vocabulary in one file.

Why the human/service distinction is first-class:
    A service principal token is a valid token with no user behind it. Code that
    assumes a human — sending mail, attributing an audit entry, applying a
    per-user quota — behaves incorrectly rather than failing when handed one.

Why the distinction also carries a certainty flag:
    Entra does not always say. ``oid`` is present for a user *and* for a service
    principal, so its absence proves nothing, and ``idtyp`` — the claim that
    does state the answer — is optional and off by default. See
    https://learn.microsoft.com/en-us/entra/identity-platform/access-token-claims-reference.
    Rather than guess silently, this module records how it decided, so a caller
    whose decision is expensive can refuse an uncertain one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Claim names, in preference order, that carry the stable identity.
_ID_CLAIMS = ("oid", "sub")
_EMAIL_CLAIMS = ("preferred_username", "email", "upn")
_NAME_CLAIMS = ("name", "given_name")

# Identity kinds.
KIND_USER = "user"
KIND_SERVICE = "service"
KIND_DEVELOPER = "developer"

# Values Entra puts in the optional ``idtyp`` claim. It is the only claim that
# states the answer rather than implying it.
_IDTYP_APP = "app"
_IDTYP_USER = "user"


@dataclass(frozen=True)
class Principal:
    """An authenticated caller.

    Attributes:
        id: Stable identifier. The Entra object id for a human. Use this as the
            owner key on stored resources — never the email, which changes.
        email: Best available address. May be empty for a service principal.
        name: Display name. May be empty.
        tenant_id: Home tenant. Meaningful when the API is multi-tenant.
        kind: ``user``, ``service`` or ``developer``.
        scopes: Delegated permissions from the ``scp`` claim.
        roles: Application roles from the ``roles`` claim.
        claims: The remaining verified claims, for consumers who genuinely need
            one this box does not model. Read-only by convention.
        kind_certain: False when ``kind`` was inferred from the shape of the
            token rather than stated by a claim. See :func:`principal_from_claims`
            for the table, and enable the optional ``idtyp`` claim to make it
            always True.
    """

    id: str
    email: str = ""
    name: str = ""
    tenant_id: str = ""
    kind: str = KIND_USER
    scopes: tuple[str, ...] = field(default_factory=tuple)
    roles: tuple[str, ...] = field(default_factory=tuple)
    claims: dict[str, Any] = field(default_factory=dict)
    kind_certain: bool = True

    @property
    def is_service(self) -> bool:
        """True when no human is behind this call.

        Check :attr:`kind_certain` too before anything a wrong answer would make
        expensive; without the ``idtyp`` claim this is a reading of the token's
        shape, not a statement Entra made.
        """
        return self.kind == KIND_SERVICE

    @property
    def is_developer(self) -> bool:
        """True when this identity came from disabled-auth mode, not a token.

        Worth checking before anything irreversible. A developer principal is
        self-asserted: it proves nothing at all.
        """
        return self.kind == KIND_DEVELOPER

    def has_scope(self, scope: str) -> bool:
        """True when the delegated permission was granted."""
        return scope in self.scopes

    def has_role(self, role: str) -> bool:
        """True when the application role was assigned."""
        return role in self.roles

    def log_fields(self) -> dict[str, Any]:
        """Structured identity fields for a log line.

        The email is omitted: it is personal data, it appears on every request,
        and the id is what correlates. Emit the email deliberately, where the
        record justifies it, rather than by default everywhere.
        """
        return {"principal_id": self.id, "principal_kind": self.kind,
                "principal_kind_certain": self.kind_certain,
                "tenant_id": self.tenant_id}


def _classify_kind(claims: dict[str, Any]) -> tuple[str, bool]:
    """Decide user or service, and say whether the token stated it.

    The supported contract, in order. Nothing below is inferred from ``oid``:
    Entra issues ``oid`` for a service principal as well as for a user, so its
    absence is not an app-only signal.

    ==============  ==========  ==========  ==========  ==============
    ``idtyp``       ``scp``     ``roles``   kind        ``kind_certain``
    ==============  ==========  ==========  ==========  ==============
    ``"app"``       any         any         service     True
    ``"user"``      any         any         user        True
    absent          present     any         user        True
    absent          absent      present     service     False
    absent          absent      absent      user        False
    ==============  ==========  ==========  ==========  ==============

    ``idtyp`` is authoritative and is the only row that needs no reading between
    the lines. It is an optional claim: add it to the API's optional-claims list
    in the app registration and every row becomes certain.

    A delegated token carries ``scp``, because that is what the user consented
    to, so ``scp`` present means a human authorised the call. The converse is
    weaker — an app-only token has ``roles`` and no ``scp``, but so does a
    delegated token for an API that exposes no scopes — which is why the last
    two rows are marked uncertain rather than resolved by guesswork. Roles alone
    are not an app-only signal: app roles are assignable to users.
    """
    idtyp = str(claims.get("idtyp", "")).strip().lower()
    if idtyp == _IDTYP_APP:
        return KIND_SERVICE, True
    if idtyp == _IDTYP_USER:
        return KIND_USER, True
    if claims.get("scp"):
        return KIND_USER, True
    if claims.get("roles"):
        return KIND_SERVICE, False
    return KIND_USER, False


def principal_from_claims(claims: dict[str, Any]) -> Principal:
    """Build a principal from verified claims.

    Assumes the signature, audience, issuer and required claims have already
    been checked. This function does not validate; calling it with unverified
    claims produces a fully-formed principal from a forged token.
    """
    identity = ""
    for name in _ID_CLAIMS:
        if claims.get(name):
            identity = str(claims[name])
            break

    email = ""
    for name in _EMAIL_CLAIMS:
        if claims.get(name):
            email = str(claims[name])
            break

    display = ""
    for name in _NAME_CLAIMS:
        if claims.get(name):
            display = str(claims[name])
            break

    kind, certain = _classify_kind(claims)

    return Principal(
        id=identity,
        email=email,
        name=display,
        tenant_id=str(claims.get("tid", "")),
        kind=kind,
        scopes=tuple(str(claims.get("scp", "")).split()) if claims.get("scp") else (),
        roles=tuple(claims.get("roles") or ()),
        claims=dict(claims),
        kind_certain=certain,
    )


def developer_principal(
    principal_id: str = "anonymous",
    email: str = "dev@localhost",
    name: str = "Developer",
) -> Principal:
    """Build the identity used when authentication is disabled.

    Marked ``developer`` rather than ``user`` so that downstream code, logs and
    audit records can tell a self-asserted identity from a proven one. Making it
    indistinguishable would mean a development request and a real one leave the
    same trace.
    """
    return Principal(id=principal_id, email=email, name=name, kind=KIND_DEVELOPER)


__all__ = [
    "Principal",
    "principal_from_claims",
    "developer_principal",
    "KIND_USER",
    "KIND_SERVICE",
    "KIND_DEVELOPER",
]
