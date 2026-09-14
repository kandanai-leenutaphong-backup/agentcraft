"""Ownership guards — the check between "who you are" and "what is yours".

Module role:
    Authentication says the caller is who they claim. It says nothing about
    whether this particular record belongs to them. These two guards are that
    second question, kept out of route handlers so the answer cannot vary by
    endpoint.

Why a missing resource and a forbidden one look identical:
    Returning 403 for "exists but not yours" and 404 for "does not exist" turns
    any identifier space into a directory an attacker can enumerate: probe ids,
    and the status code reports which ones are real. Both answer 404 here (G4).
    The distinction survives in the log, where the operator can see it and the
    caller cannot.

Why shared templates are readable but not writable:
    A demo or default record that every caller can open is a common and
    reasonable design. Letting any of them *edit* it is not, and the two are one
    conditional apart — which is exactly why they are separate methods rather
    than one flag.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from ._errors import ForbiddenError, NotFoundError
from ._principal import Principal

logger = logging.getLogger(__name__)

# Conventional owner id for a record shared with every caller, read-only.
DEFAULT_SHARED_OWNER = "__default__"


@dataclass(frozen=True)
class OwnershipPolicy:
    """Who may read and who may modify a record, given its owner id.

    Attributes:
        shared_owner_ids: Owner values meaning "readable by everyone". Records
            carrying one are templates: readable, never writable.
        allow_unowned_read: Whether a record with no owner at all is readable.
            Defaults to ``False``. Records predating an ownership column are the
            usual source, and treating them as public is how a migration becomes
            a disclosure.
    """

    shared_owner_ids: tuple[str, ...] = (DEFAULT_SHARED_OWNER,)
    allow_unowned_read: bool = False

    def is_shared(self, owner_id: str) -> bool:
        """True when the record is a shared template."""
        return owner_id in self.shared_owner_ids

    def can_read(self, owner_id: str, principal: Principal) -> bool:
        """True when the principal may read a record with this owner."""
        if self.is_shared(owner_id):
            return True
        if not owner_id:
            return self.allow_unowned_read
        return owner_id == principal.id

    def can_write(self, owner_id: str, principal: Principal) -> bool:
        """True when the principal may modify a record with this owner."""
        if self.is_shared(owner_id):
            return False
        if not owner_id:
            return False
        return owner_id == principal.id

    def assert_readable(
        self, owner_id: str, principal: Principal, resource_id: str = ""
    ) -> None:
        """Raise :class:`NotFoundError` unless the principal may read.

        Args:
            owner_id: The record's owner. Compared against ``principal.id``.
            principal: The authenticated caller.
            resource_id: For the log line only. Never returned to the caller.
        """
        if self.can_read(owner_id, principal):
            return
        logger.warning(
            "auth.ownership.denied",
            extra={"resource_id": resource_id, "owner_id": owner_id,
                   **principal.log_fields()},
        )
        raise NotFoundError(resource_id=resource_id, owner_id=owner_id,
                            principal_id=principal.id)

    def assert_writable(
        self,
        owner_id: str,
        principal: Principal,
        action: str,
        resource_id: str = "",
    ) -> None:
        """Raise unless the principal may modify.

        Raises:
            NotFoundError: When the record is not theirs — the same answer a
                non-existent record gets.
            ForbiddenError: When the record is a shared template. This one is
                *not* disguised: the caller can already read it, so its
                existence is not a secret, and 403 is the honest answer to
                "may I change this".
        """
        if self.is_shared(owner_id):
            logger.warning(
                "auth.shared_resource.write_blocked",
                extra={"resource_id": resource_id, "action": action,
                       **principal.log_fields()},
            )
            raise ForbiddenError(
                "shared_resource_immutable",
                f"{action} refused on a shared template",
                resource_id=resource_id, action=action,
            )
        self.assert_readable(owner_id, principal, resource_id)


# The policy most consumers want: one shared template id, no unowned reads.
DEFAULT_POLICY = OwnershipPolicy()


__all__ = ["OwnershipPolicy", "DEFAULT_POLICY", "DEFAULT_SHARED_OWNER"]
