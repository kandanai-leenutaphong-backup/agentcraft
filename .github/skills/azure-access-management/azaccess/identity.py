"""Typed identity coordinates.

WHY THIS EXISTS
---------------
Azure identity failures are overwhelmingly *coordinate* failures, not
permission failures: an application (client) id used where a service
principal **object** id was required, a tenant id pasted into a principal
field, a user-assigned managed identity's resource id used as its principal
id. All three answer ``PrincipalNotFound`` from ARM, which reads like a
missing grant and is not one. Every one of them is decidable locally,
before a request is built, so this module decides them locally.

A GUID is not self-describing. ``IdentityRef`` therefore carries the *kind*
alongside the id, and the ARM ``principalType`` is derived from the kind
rather than guessed by the service. Omitting ``principalType`` is a real
failure mode when the principal was created seconds ago and directory
replication has not caught up (GOTCHAS.md, G3).

DEPENDENCIES
------------
Standard library only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from azaccess.errors import CoordinateError

_GUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I
)

#: The identity kinds this skill can plan for, and the ARM ``principalType``
#: each one serialises as. ``application`` is deliberately absent from the ARM
#: mapping: an application object is not assignable, its service principal is.
PRINCIPAL_TYPES: dict[str, str] = {
    "user": "User",
    "group": "Group",
    "service-principal": "ServicePrincipal",
    "managed-identity": "ServicePrincipal",
}

IDENTITY_KINDS: tuple[str, ...] = (
    "user",
    "group",
    "service-principal",
    "managed-identity",
    "application",
)


def is_guid(value: str) -> bool:
    """True when ``value`` is a syntactically valid GUID."""
    return bool(_GUID_RE.match(str(value or "").strip()))


def require_guid(value: str, *, field: str) -> str:
    """Return ``value`` lowercased, or refuse with the field that was wrong."""
    text = str(value or "").strip()
    if not is_guid(text):
        raise CoordinateError(
            f"{field} must be a GUID; got {len(text)} character(s) that are not"
        )
    return text.lower()


@dataclass(frozen=True)
class IdentityRef:
    """One principal, named by the coordinate ARM actually assigns to.

    ``object_id`` is the directory object id of the principal — for a managed
    identity that is its *principal id*, never its client id and never the ARM
    resource id of the identity resource.
    """

    object_id: str
    kind: str
    tenant_id: str = ""
    display_name: str = ""
    #: Application (client) id. Recorded because callers hold it, and kept
    #: strictly separate from ``object_id`` so the two cannot be swapped.
    client_id: str = ""
    #: ARM resource id of a user-assigned managed identity, when known.
    resource_id: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "object_id", require_guid(self.object_id, field="object_id"))
        if self.kind not in IDENTITY_KINDS:
            raise CoordinateError(
                f"'{self.kind}' is not an identity kind; expected one of "
                f"{', '.join(IDENTITY_KINDS)}"
            )
        if self.tenant_id:
            object.__setattr__(
                self, "tenant_id", require_guid(self.tenant_id, field="tenant_id")
            )
        if self.client_id:
            object.__setattr__(
                self, "client_id", require_guid(self.client_id, field="client_id")
            )
        if self.client_id and self.client_id == self.object_id:
            raise CoordinateError(
                "client_id equals object_id — for every identity kind except a "
                "freshly created application these are different GUIDs, and "
                "assigning to the client id answers PrincipalNotFound"
            )
        if self.kind == "application":
            raise CoordinateError(
                "an application object is not assignable; assign to its service "
                "principal (kind='service-principal') in the target tenant"
            )

    @property
    def principal_type(self) -> str:
        """The ARM ``principalType`` for this kind."""
        try:
            return PRINCIPAL_TYPES[self.kind]
        except KeyError:  # pragma: no cover - guarded in __post_init__
            raise CoordinateError(f"'{self.kind}' has no ARM principalType") from None

    def describe(self) -> dict[str, str]:
        """Non-secret coordinates, safe to log."""
        return {
            "object_id": self.object_id,
            "kind": self.kind,
            "tenant_id": self.tenant_id,
            "display_name": self.display_name,
        }


def user_assigned_identity(
    *, principal_id: str, client_id: str = "", resource_id: str = "", tenant_id: str = "",
    display_name: str = "",
) -> IdentityRef:
    """A user-assigned managed identity, from the three ids ARM hands back.

    Named constructor because the ARM response calls the assignable coordinate
    ``principalId`` while every SDK calls it ``object_id``, and the two GUIDs
    beside it in that same response are not assignable.
    """
    return IdentityRef(
        object_id=principal_id,
        kind="managed-identity",
        tenant_id=tenant_id,
        display_name=display_name,
        client_id=client_id,
        resource_id=resource_id,
    )


__all__ = [
    "IDENTITY_KINDS",
    "PRINCIPAL_TYPES",
    "IdentityRef",
    "is_guid",
    "require_guid",
    "user_assigned_identity",
]
