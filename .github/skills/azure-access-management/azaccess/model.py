"""The value types every stage of the interface passes around.

Frozen dataclasses, no behaviour beyond validation and serialisation, so a
plan can be printed, diffed, stored and re-read without the objects that made
it. ``to_dict`` on every type is the wire form the CLI prints.

COMPLETENESS IS A FIRST-CLASS FIELD
-----------------------------------
An access answer that does not say what it could not evaluate is a lie with
good intentions. :class:`Completeness` therefore has no ``complete`` member
for effective access: PIM eligibility, deny assignments, transitive group
membership and ABAC conditions are not evaluated by this package, so an
effective-access answer is at best ``partial`` and names what it skipped.
``exact`` is available and means one narrow thing — the set of assignments
written *at this exact scope* on this plane was read in full.

FROZEN MEANS FROZEN
-------------------
``@dataclass(frozen=True)`` freezes the *bindings*, not what they point at. An
audit of this package mutated a caller's ``target`` dict after construction
and changed the declaration's fingerprint — so a reviewed plan was not the
plan that ran, and a confirmation token bound to a fingerprint was bound to
nothing stable. Every mapping and every sequence of mappings on these types is
therefore deep-copied and wrapped read-only at construction. Handing one of
these objects to untrusted code no longer risks the identity it was approved
under.

DEPENDENCIES
------------
Standard library only.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from azaccess.errors import CoordinateError
from azaccess.identity import IdentityRef
from azaccess.roles import RoleDefinition, lookup_role, role_identity_matches
from azaccess.scopes import Scope, normalize_scope


def freeze_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    """A read-only, deep-copied view of ``value``.

    Nested mappings and sequences are frozen too, because a caller who keeps a
    reference to an inner dict can otherwise still change what a plan says
    after it was approved.
    """
    return MappingProxyType({str(k): _freeze(v) for k, v in dict(value).items()})


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return freeze_mapping(value)
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(v) for v in value)
    return value


def _plain(value: Any) -> Any:
    """The mutable, JSON-serialisable form of a frozen structure."""
    if isinstance(value, Mapping):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, tuple):
        return [_plain(v) for v in value]
    return value

#: Semantics this package does not evaluate. Reported alongside every
#: effective-access answer so the gap is visible rather than assumed absent.
UNEVALUATED_SEMANTICS: tuple[str, ...] = (
    "pim-eligible-assignments",
    "deny-assignments",
    "transitive-group-membership",
    "abac-role-assignment-conditions",
    "management-group-ancestry",
    "entra-directory-roles",
)


class Completeness:
    """How much of the truth an answer covers."""

    EXACT = "exact"          # every assignment written at this exact scope
    PARTIAL = "partial"      # effective access, with named gaps
    UNKNOWN = "unknown"      # the read did not complete

    ALL = (EXACT, PARTIAL, UNKNOWN)


@dataclass(frozen=True)
class AccessDeclaration:
    """The desired state for one principal, one role, one scope.

    ``target`` carries the extra coordinates the native planes need — the
    Cosmos account id, the Kusto database, the SQL schema and table — because
    those planes do not address their assignment by ARM scope alone.
    """

    principal: IdentityRef
    role: str
    scope: str
    target: Mapping[str, str] = field(default_factory=dict)
    #: An ABAC condition expression. Present or absent changes identity: a
    #: conditional assignment is NOT the unconditional one.
    condition: str = ""
    condition_version: str = ""
    justification: str = ""

    def __post_init__(self) -> None:
        # Deep-copied and frozen: the caller keeps their dict, this object
        # keeps an identity nothing outside it can move.
        object.__setattr__(self, "target", freeze_mapping(self.target))
        # Validated here so a malformed or traversal-carrying scope is refused
        # at construction, before a plan, an allowlist check or a request.
        # Structural, not ARM-shaped: two of the five planes address a target
        # that is not an ARM resource id, and ARM shape is enforced by the ARM
        # adapter where it is actually required.
        normalize_scope(self.scope)
        if self.condition_version and not self.condition:
            raise CoordinateError(
                "condition_version was given with no condition; an ABAC version "
                "without an expression names no assignment"
            )

    @property
    def role_definition(self) -> RoleDefinition:
        return lookup_role(self.role)

    @property
    def plane(self) -> str:
        return self.role_definition.plane

    @property
    def parsed_scope(self) -> Scope:
        return Scope.parse(self.scope)

    @property
    def effective_condition_version(self) -> str:
        """The version ARM will store, so identity uses what will exist."""
        if not self.condition:
            return ""
        return self.condition_version or "2.0"

    def fingerprint(self) -> str:
        """Stable identity of *what is being asked for*.

        Binds a confirmation token to a target. Deliberately excludes anything
        a caller could vary without changing the effect (justification), and
        includes everything that changes it — including the ABAC condition
        *version*, because a v1.0 and a v2.0 expression are evaluated by
        different rules and sharing one identity let a token minted for one
        confirm the other.
        """
        material = "|".join(
            [
                self.plane,
                self.role_definition.definition_id,
                normalize_scope(self.scope).lower(),
                self.principal.object_id,
                self.condition.strip(),
                self.effective_condition_version,
                ";".join(f"{k}={v}" for k, v in sorted(dict(self.target).items())),
            ]
        )
        return hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]

    def to_dict(self) -> dict[str, Any]:
        return {
            "principal": self.principal.describe(),
            "role": self.role,
            "plane": self.plane,
            "tier": self.role_definition.tier,
            "scope": self.scope,
            "target": _plain(self.target),
            "condition": self.condition,
            "condition_version": self.effective_condition_version,
            "fingerprint": self.fingerprint(),
        }


@dataclass(frozen=True)
class AssignmentState:
    """One assignment as the service reports it, on any plane."""

    assignment_id: str
    plane: str
    principal_id: str
    role_definition_id: str
    scope: str
    condition: str = ""
    principal_type: str = ""
    raw_name: str = ""
    condition_version: str = ""

    def matches(self, declaration: AccessDeclaration) -> bool:
        """Exact match: same principal, same role, same scope, same condition."""
        role = declaration.role_definition
        if self.plane != role.plane:
            return False
        if self.principal_id.lower() != declaration.principal.object_id.lower():
            return False
        # Per-plane exact identity. A suffix test elevates on the word-keyed
        # planes: 'UnrestrictedViewer'.endswith('Viewer') is True and the two
        # roles are not the same grant.
        if not role_identity_matches(self.role_definition_id, role):
            return False
        # Textual, not parsed: three of the five planes address an assignment
        # by a path that is not an ARM resource id at all.
        if self.scope.lower().rstrip("/") != declaration.scope.lower().rstrip("/"):
            return False
        if self.condition.strip() != declaration.condition.strip():
            return False
        # An ABAC condition is evaluated by its version's rules, so a v1.0
        # assignment does not satisfy a v2.0 declaration.
        observed_version = self.condition_version.strip() if self.condition.strip() else ""
        wanted_version = declaration.effective_condition_version
        if observed_version and wanted_version:
            return observed_version.lower() == wanted_version.lower()
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "assignment_id": self.assignment_id,
            "plane": self.plane,
            "principal_id": self.principal_id,
            "role_definition_id": self.role_definition_id,
            "scope": self.scope,
            "condition": self.condition,
            "condition_version": self.condition_version,
        }


@dataclass(frozen=True)
class PlanStep:
    """One action, with the reason it is in the plan."""

    action: str  # create | adopt | noop | revoke
    declaration: AccessDeclaration
    reason: str
    requires_confirmation: bool = False
    existing_id: str = ""

    ACTIONS = ("create", "adopt", "noop", "revoke")

    def __post_init__(self) -> None:
        if self.action not in self.ACTIONS:
            raise CoordinateError(f"'{self.action}' is not a plan action")

    @property
    def tier(self) -> str:
        return self.declaration.role_definition.tier

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "reason": self.reason,
            "requires_confirmation": self.requires_confirmation,
            "existing_id": self.existing_id,
            **self.declaration.to_dict(),
        }


@dataclass(frozen=True)
class Plan:
    """An ordered, reviewable set of steps plus everything refused."""

    plan_id: str
    steps: tuple[PlanStep, ...] = ()
    refusals: tuple[Mapping[str, Any], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "refusals", tuple(freeze_mapping(r) for r in self.refusals)
        )

    @property
    def mutating(self) -> tuple[PlanStep, ...]:
        return tuple(s for s in self.steps if s.action in ("create", "revoke"))

    def digest(self) -> str:
        """The identity of *this exact plan's effects*, for offline review.

        Excludes ``plan_id``, which is minted per run and would make every
        review one-shot. Includes every field that changes what happens, so an
        operator can approve a digest they read and an ``apply`` can refuse a
        plan that is not the one approved.
        """
        material = json.dumps(
            [s.to_dict() for s in self.steps], sort_keys=True, separators=(",", ":")
        )
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "digest": self.digest(),
            "steps": [s.to_dict() for s in self.steps],
            "refusals": [_plain(r) for r in self.refusals],
            "mutating_steps": len(self.mutating),
            "confirmation_required": sorted(
                s.declaration.fingerprint()
                for s in self.mutating
                if s.requires_confirmation
            ),
        }


@dataclass(frozen=True)
class OwnershipRecord:
    """Where an assignment came from, and therefore whether it may be deleted.

    ``assignment_id`` is copied from the id the service returned on the create
    response, or from a read-back of the exact target this run PUT. Ownership
    is never inferred from a deterministic name, from a listing difference, or
    from a description string — all three attribute somebody else's assignment
    to this run and then delete it.

    ``source`` is load-bearing, not decorative:

    ``created``            this run wrote it. Revocable.
    ``adopted``            it already existed; this run found it and recorded
                           the real id so a plan could report ``noop``. **Not**
                           revocable — an audit reproduced ``revoke`` deleting
                           an adopted assignment, which is another team's grant
                           removed by a teardown that never made it.
    ``ledger-unverified``  rehydrated from a durable ledger file after a crash.
                           Evidence for a human, never authority for a delete.
    ``pending``            a long-running create was accepted and its outcome is
                           unknown. Carries the target id so cleanup is possible.
    """

    assignment_id: str
    plane: str
    plan_id: str
    fingerprint: str
    principal_id: str
    scope: str
    role: str
    created_at: str = ""
    source: str = "created"  # created | adopted | ledger-unverified | pending
    detail: str = ""

    SOURCES = ("created", "adopted", "ledger-unverified", "pending")

    def __post_init__(self) -> None:
        if self.source not in self.SOURCES:
            raise CoordinateError(f"'{self.source}' is not an ownership source")

    @property
    def revocable(self) -> bool:
        """Only what this run actually wrote may be deleted without an id."""
        return self.source == "created"

    def to_dict(self) -> dict[str, Any]:
        return {
            "assignment_id": self.assignment_id,
            "plane": self.plane,
            "plan_id": self.plan_id,
            "fingerprint": self.fingerprint,
            "principal_id": self.principal_id,
            "scope": self.scope,
            "role": self.role,
            "source": self.source,
            "revocable": self.revocable,
            "created_at": self.created_at,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class VerificationResult:
    """Present, absent, or honestly unknown — never optimistically present."""

    fingerprint: str
    status: str  # present | absent | unknown | revert-suspected
    scope: str
    plane: str
    waited_secs: float = 0.0
    detail: str = ""
    duplicates: tuple[str, ...] = ()

    STATUSES = ("present", "absent", "unknown", "revert-suspected")

    def __post_init__(self) -> None:
        if self.status not in self.STATUSES:
            raise CoordinateError(f"'{self.status}' is not a verification status")

    def to_dict(self) -> dict[str, Any]:
        return {
            "fingerprint": self.fingerprint,
            "status": self.status,
            "scope": self.scope,
            "plane": self.plane,
            "waited_secs": round(self.waited_secs, 3),
            "detail": self.detail,
            "duplicates": list(self.duplicates),
        }


@dataclass(frozen=True)
class EffectiveAccess:
    """What a principal appears to have here, and what was not evaluated."""

    principal_id: str
    scope: str
    exact: tuple[AssignmentState, ...] = ()
    inherited: tuple[AssignmentState, ...] = ()
    completeness: str = Completeness.PARTIAL
    unevaluated: tuple[str, ...] = UNEVALUATED_SEMANTICS

    def to_dict(self) -> dict[str, Any]:
        return {
            "principal_id": self.principal_id,
            "scope": self.scope,
            "exact": [a.to_dict() for a in self.exact],
            "inherited": [a.to_dict() for a in self.inherited],
            "completeness": self.completeness,
            "unevaluated": list(self.unevaluated),
        }


@dataclass(frozen=True)
class DiffReport:
    """Desired versus observed, with inherited access kept separate."""

    missing: tuple[AccessDeclaration, ...] = ()
    satisfied: tuple[AccessDeclaration, ...] = ()
    #: Desired at this exact scope, but only present via an ancestor. NOT
    #: satisfied: revoking the ancestor would remove it, and the plan asked for
    #: an assignment here.
    inherited_only: tuple[AccessDeclaration, ...] = ()
    #: Present, not declared. Reported, never auto-deleted.
    excess: tuple[AssignmentState, ...] = ()
    completeness: str = Completeness.EXACT
    unevaluated: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "missing": [d.to_dict() for d in self.missing],
            "satisfied": [d.to_dict() for d in self.satisfied],
            "inherited_only": [d.to_dict() for d in self.inherited_only],
            "excess": [a.to_dict() for a in self.excess],
            "completeness": self.completeness,
            "unevaluated": list(self.unevaluated),
        }


@dataclass(frozen=True)
class ApplyReport:
    """What was created or adopted, what was refused, what verified."""

    plan_id: str
    ownership: tuple[OwnershipRecord, ...] = ()
    refusals: tuple[Mapping[str, Any], ...] = ()
    verifications: tuple[VerificationResult, ...] = ()
    #: Long-running creates whose outcome is unknown. Never empty silently:
    #: an accepted 202 that could not be polled to a conclusion is reported
    #: here with the target id, because the alternative is an orphan.
    pending: tuple[OwnershipRecord, ...] = ()
    #: Assignments that were created and whose ownership record could not be
    #: persisted. The cloud write already happened, so the id is reported here
    #: rather than lost to an exception.
    ledger_failures: tuple[Mapping[str, Any], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "refusals", tuple(freeze_mapping(r) for r in self.refusals)
        )
        object.__setattr__(
            self, "ledger_failures",
            tuple(freeze_mapping(r) for r in self.ledger_failures),
        )

    @property
    def ok(self) -> bool:
        return (
            not self.refusals
            and not self.pending
            and not self.ledger_failures
            and all(v.status == "present" for v in self.verifications)
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "ok": self.ok,
            "ownership": [o.to_dict() for o in self.ownership],
            "refusals": [_plain(r) for r in self.refusals],
            "pending": [o.to_dict() for o in self.pending],
            "ledger_failures": [_plain(r) for r in self.ledger_failures],
            "verifications": [v.to_dict() for v in self.verifications],
        }


@dataclass(frozen=True)
class RevokeReport:
    """Deleted, refused, and the read-back that proves absence."""

    deleted: tuple[str, ...] = ()
    refused: tuple[Mapping[str, Any], ...] = ()
    verifications: tuple[VerificationResult, ...] = ()
    #: Cleanup coordinates deliberately kept: a delete that was accepted but
    #: whose target could not be proved gone. Dropping the record here is how a
    #: real assignment becomes unfindable.
    retained: tuple[Mapping[str, Any], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "refused", tuple(freeze_mapping(r) for r in self.refused)
        )
        object.__setattr__(
            self, "retained", tuple(freeze_mapping(r) for r in self.retained)
        )

    @property
    def ok(self) -> bool:
        return (
            not self.retained
            and all(v.status == "absent" for v in self.verifications)
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "deleted": list(self.deleted),
            "refused": [_plain(r) for r in self.refused],
            "retained": [_plain(r) for r in self.retained],
            "verifications": [v.to_dict() for v in self.verifications],
        }


def declarations_from_records(records: Sequence[Mapping[str, Any]],
                              principal: IdentityRef) -> tuple[AccessDeclaration, ...]:
    """Build declarations from plain dicts, e.g. parsed from a config file."""
    out: list[AccessDeclaration] = []
    for record in records:
        out.append(
            AccessDeclaration(
                principal=principal,
                role=str(record["role"]),
                scope=str(record["scope"]),
                target={k: str(v) for k, v in dict(record.get("target") or {}).items()},
                condition=str(record.get("condition") or ""),
                condition_version=str(record.get("condition_version") or ""),
                justification=str(record.get("justification") or ""),
            )
        )
    return tuple(out)


__all__ = [
    "AccessDeclaration",
    "ApplyReport",
    "AssignmentState",
    "Completeness",
    "DiffReport",
    "EffectiveAccess",
    "OwnershipRecord",
    "Plan",
    "PlanStep",
    "RevokeReport",
    "UNEVALUATED_SEMANTICS",
    "VerificationResult",
    "declarations_from_records",
    "freeze_mapping",
]
