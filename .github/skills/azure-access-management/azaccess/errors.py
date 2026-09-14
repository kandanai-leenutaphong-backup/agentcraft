"""The only failures that escape this package.

Every error carries a *category*, because the four things that produce a 403
need four different responses and are routinely conflated: authentication
(who you are), authorization (what you may do), network reachability (whether
the request arrived), and policy (whether governance reverted or refused it).
Diagnosing the fourth is never permission to bypass it.

DEPENDENCIES
------------
Standard library only.
"""

from __future__ import annotations


class AccessError(RuntimeError):
    """Base class. ``category`` says which plane the failure belongs to."""

    category = "access"


class CoordinateError(AccessError):
    """A tenant, principal, scope or role coordinate is malformed."""

    category = "coordinate"


class AuthorizationRefused(AccessError):
    """This process refused to build or send the request.

    Raised by the local authority policy, never by a service. A refusal here
    means the plan asked for something outside the runtime allowlist, above
    the authorised tier, or without a valid confirmation token.
    """

    category = "authorization"


class AuthenticationError(AccessError):
    """No usable credential, or the credential was rejected (401)."""

    category = "authentication"


class TransportError(AccessError):
    """The request did not complete, or the response was not usable."""

    category = "transport"


class ProviderConflict(AccessError):
    """The remote state disagrees with what a single-writer plan assumed."""

    category = "conflict"


class PolicyRevertSuspected(AccessError):
    """A write reported success and the read-back at exact scope disagreed.

    Not a synonym for failure: governance ``Modify`` effects return HTTP 200
    and then revert the field. Treated as its own category so an operator is
    told to look at policy rather than at their own permissions.
    """

    category = "policy"


class OperationPending(AccessError):
    """A mutation was accepted and its outcome is genuinely unknown.

    Raised where the naive alternatives are both wrong. "It failed" leaks the
    assignment, because a Cosmos or Kusto ``202 Accepted`` usually does land.
    "It succeeded" invents an id nobody read back. So the outcome is its own
    category, and it carries ``target_id`` — the id this run PUT — so an
    operator can look for the assignment and remove it by hand.
    """

    category = "pending"

    def __init__(self, message: str, *, target_id: str = "", status: int = 0) -> None:
        super().__init__(message)
        self.target_id = target_id
        self.status = status


__all__ = [
    "AccessError",
    "AuthenticationError",
    "AuthorizationRefused",
    "CoordinateError",
    "OperationPending",
    "PolicyRevertSuspected",
    "ProviderConflict",
    "TransportError",
]
