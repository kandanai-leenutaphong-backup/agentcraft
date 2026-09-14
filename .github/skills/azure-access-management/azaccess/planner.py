"""From declarations to a plan, and from a plan to a diff.

WHY PLANNING IS SEPARATE FROM APPLYING
--------------------------------------
Everything that can be refused should be refused before anything is sent. The
planner reads current state, decides one action per declaration, and records
every authorisation refusal as *data* rather than raising — so an operator sees
the whole picture, including the parts that will not be attempted, in one
read-only pass. Nothing in this module mutates.

THE THREE OUTCOMES THAT LOOK LIKE ONE
-------------------------------------
* an exact assignment exists — nothing to do;
* nothing exists — create;
* the principal already has the access *inherited from an ancestor* — the
  declaration is still unsatisfied, because it asked for an assignment here.

The third is the one that is routinely mistaken for the first, and it is the
mistake that makes a "least privilege" migration a no-op: the code sees
effective access, calls the desired state met, and the subscription-wide
Contributor stays exactly where it was.
"""

from __future__ import annotations

import uuid
from typing import Any, Callable, Mapping, Sequence

from azaccess.authorization import AuthorityPolicy
from azaccess.errors import AccessError, AuthorizationRefused
from azaccess.model import (
    AccessDeclaration,
    AssignmentState,
    Completeness,
    DiffReport,
    Plan,
    PlanStep,
    UNEVALUATED_SEMANTICS,
)
from azaccess.providers.base import require_provider
from azaccess.roles import role_identity_matches
from azaccess.scopes import normalize_scope, scope_depth


class Planner:
    """Turns desired state into an ordered, refusable plan."""

    def __init__(
        self,
        providers: Mapping[str, Any],
        *,
        policy: AuthorityPolicy,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._providers = dict(providers)
        self._policy = policy
        self._ids = id_factory or (lambda: uuid.uuid4().hex[:12])

    def provider_for(self, declaration: AccessDeclaration) -> Any:
        plane = declaration.plane
        try:
            provider = self._providers[plane]
        except KeyError:
            raise AccessError(
                f"no adapter registered for plane '{plane}'; register one or "
                f"follow the documented procedure for that plane"
            ) from None
        # Checked here as well as at registration, because a provider mapping
        # can be handed in from anywhere and an AttributeError from three
        # frames down is not an answer.
        return require_provider(provider, plane)

    # -- read-only state --------------------------------------------------

    def observed(self, declaration: AccessDeclaration) -> tuple[AssignmentState, ...]:
        self._policy.authorize_read(declaration.scope, what="reading assignments")
        return tuple(self.provider_for(declaration).matches(declaration))

    def inherited(self, declaration: AccessDeclaration) -> tuple[AssignmentState, ...]:
        """Assignments of the same role for the same principal at an ancestor.

        Only the Azure RBAC plane inherits; the native planes do not, and
        reporting inheritance for them would invent a semantic they lack.
        """
        provider = self.provider_for(declaration)
        if declaration.plane != "azure-rbac" or not hasattr(provider, "list_inherited"):
            return ()
        self._policy.authorize_read(declaration.scope, what="reading inherited access")
        role = declaration.role_definition
        principal = declaration.principal.object_id.lower()
        out: list[AssignmentState] = []
        for state in provider.list_inherited(declaration.scope):
            if state.principal_id.lower() != principal:
                continue
            if not role_identity_matches(state.role_definition_id, role):
                continue
            out.append(state)
        return tuple(out)

    # -- plan -------------------------------------------------------------

    def plan(self, declarations: Sequence[AccessDeclaration], *,
             action: str = "create") -> Plan:
        plan_id = self._ids()
        steps: list[PlanStep] = []
        refusals: list[dict[str, Any]] = []
        for declaration in _ordered(declarations):
            try:
                existing = self.observed(declaration)
            except AccessError as exc:
                refusals.append(_refusal(declaration, exc))
                continue
            step = self._step_for(declaration, existing, action)
            try:
                if step.action in ("create", "revoke"):
                    self._policy.authorize(step)
            except AuthorizationRefused as exc:
                refusals.append(_refusal(declaration, exc))
                continue
            steps.append(step)
        return Plan(plan_id=plan_id, steps=tuple(steps), refusals=tuple(refusals))

    def _step_for(self, declaration: AccessDeclaration,
                  existing: Sequence[AssignmentState], action: str) -> PlanStep:
        tier = declaration.role_definition.tier
        confirm = self._policy.needs_confirmation(tier)
        if action == "revoke":
            if not existing:
                return PlanStep("noop", declaration, "no exact assignment to revoke")
            return PlanStep(
                "revoke", declaration,
                f"{len(existing)} exact assignment(s) present",
                requires_confirmation=confirm,
                existing_id=existing[0].assignment_id,
            )
        if existing:
            return PlanStep(
                "noop", declaration,
                "exact assignment already present at this scope",
                existing_id=existing[0].assignment_id,
            )
        inherited = self.inherited(declaration)
        reason = "no assignment at this exact scope"
        if inherited:
            reason = (
                f"no assignment at this exact scope; access is currently "
                f"inherited from {inherited[0].scope} and would disappear if "
                f"that assignment were removed"
            )
        return PlanStep("create", declaration, reason, requires_confirmation=confirm)

    # -- diff -------------------------------------------------------------

    def diff(self, declarations: Sequence[AccessDeclaration], *,
             include_excess_at: Sequence[str] = ()) -> DiffReport:
        """Desired versus observed, with inherited access reported separately."""
        missing: list[AccessDeclaration] = []
        satisfied: list[AccessDeclaration] = []
        inherited_only: list[AccessDeclaration] = []
        for declaration in _ordered(declarations):
            if self.observed(declaration):
                satisfied.append(declaration)
            elif self.inherited(declaration):
                inherited_only.append(declaration)
            else:
                missing.append(declaration)
        excess = self._excess(declarations, include_excess_at)
        return DiffReport(
            missing=tuple(missing),
            satisfied=tuple(satisfied),
            inherited_only=tuple(inherited_only),
            excess=tuple(excess),
            # Exact assignments were read in full; effective access was not.
            completeness=Completeness.EXACT if not include_excess_at
            else Completeness.PARTIAL,
            unevaluated=UNEVALUATED_SEMANTICS,
        )

    def _excess(self, declarations: Sequence[AccessDeclaration],
                scopes: Sequence[str]) -> list[AssignmentState]:
        """Assignments present at named scopes that no declaration asked for."""
        if not scopes:
            return []
        provider = self._providers.get("azure-rbac")
        if provider is None:
            return []
        wanted = {
            (
                d.principal.object_id.lower(),
                d.role_definition.definition_id.lower(),
                normalize_scope(d.scope).lower(),
                d.condition.strip(),
            )
            for d in declarations
            if d.plane == "azure-rbac"
        }
        out: list[AssignmentState] = []
        for scope in scopes:
            self._policy.authorize_read(scope, what="reading excess assignments")
            for state in provider.list_exact(scope):
                key = (
                    state.principal_id.lower(),
                    state.role_definition_id.rsplit("/", 1)[-1].lower(),
                    state.scope.lower().rstrip("/"),
                    state.condition.strip(),
                )
                if key not in wanted:
                    out.append(state)
        return out


def _ordered(declarations: Sequence[AccessDeclaration]) -> list[AccessDeclaration]:
    """Broad scopes first, so a plan reads the way an estate is built."""
    return sorted(declarations, key=lambda d: (scope_depth(d.scope), d.role, d.scope))


def _refusal(declaration: AccessDeclaration, exc: Exception) -> dict[str, Any]:
    return {
        "fingerprint": declaration.fingerprint(),
        "role": declaration.role,
        "scope": declaration.scope,
        "category": getattr(exc, "category", "error"),
        "reason": str(exc),
    }


__all__ = ["Planner"]
