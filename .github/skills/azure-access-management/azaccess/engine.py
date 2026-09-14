"""The one entry point: inspect, plan, diff, apply, verify, revoke.

WHY THESE SIX AND IN THIS ORDER
-------------------------------
Access work fails in the gaps between the verbs, not inside them. Applying
without a plan hides what changed; planning without inspecting plans against
imagined state; applying without verifying believes a write that governance
reverted; and a run that cannot revoke what it made is a leak with a
changelog. So the six are one object, sharing one authority policy, one set of
plane adapters and one ownership ledger.

READ-ONLY BY DEFAULT
--------------------
:meth:`AccessManager.apply` refuses unless the policy says otherwise and the
step carries a valid confirmation token. Constructing the manager grants
nothing; the default policy from
:func:`~azaccess.authorization.bounded_policy` is read-only.

PROPAGATION IS BOUNDED, AND SILENCE IS NOT SUCCESS
--------------------------------------------------
A directory change is visible when it is visible. Verification polls to a
budget and then reports ``absent`` or ``revert-suspected`` with the elapsed
time — never ``present`` on the grounds that it probably landed by now, and
never an unbounded wait. ``unknown`` exists for the case where the read itself
failed, because "we could not tell" is a different answer from "it is not
there" and conflating them is how a teardown reports clean.

REVOKE ONLY WHAT THIS RUN CREATED
---------------------------------
Every deletion needs an ownership record whose ``source`` is ``created`` — this
run's own write — or an id the caller explicitly named. Deleting "everything
that matches" is how a teardown removes another team's grant on a shared
account, and so is deleting what this run merely *adopted*: an audit reproduced
exactly that, with ARM's 409 path and with the Cosmos and Kusto adapters, which
adopt on every pre-existing match. Adoption exists so a plan can say ``noop``.
It is not a licence to delete.

OWNERSHIP MAY OUTLIVE THE PROCESS, BUT NEVER GRANTS AUTHORITY
-------------------------------------------------------------
An optional :class:`~azaccess.ledger.OwnershipLedger` writes each created
record to a file as it is made, so a crash leaves a trail. Records read back
out of that file arrive as ``ledger-unverified`` and are *not* revocable: a
file anyone can append to must not be able to direct a delete.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Iterable, Mapping, Sequence

from azaccess.authorization import AuthorityPolicy, ConfirmationLedger
from azaccess.errors import (
    AccessError,
    AuthorizationRefused,
    OperationPending,
    TransportError,
)
from azaccess.ledger import OwnershipLedger
from azaccess.model import (
    AccessDeclaration,
    ApplyReport,
    AssignmentState,
    Completeness,
    DiffReport,
    EffectiveAccess,
    OwnershipRecord,
    Plan,
    PlanStep,
    RevokeReport,
    UNEVALUATED_SEMANTICS,
    VerificationResult,
)
from azaccess.planner import Planner
from azaccess.providers.base import require_provider
from azaccess.transport import sanitize_detail

#: Defaults chosen from published propagation behaviour and one measured
#: session: data-plane grants land in minutes, revocations in under a minute.
#: Overridable per call; never unbounded.
DEFAULT_PROPAGATION_BUDGET_SECS = 90.0
DEFAULT_POLL_INTERVAL_SECS = 5.0


class AccessManager:
    """The adoption boundary. One object, six verbs, one authority policy."""

    def __init__(
        self,
        providers: Mapping[str, Any],
        *,
        policy: AuthorityPolicy,
        ledger: ConfirmationLedger | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
        id_factory: Callable[[], str] | None = None,
        ownership_ledger: OwnershipLedger | None = None,
    ) -> None:
        # Checked at registration, so a half-implemented adapter is a sentence
        # here rather than an AttributeError from inside plan().
        self._providers = {
            plane: require_provider(provider, plane)
            for plane, provider in dict(providers).items()
        }
        self._policy = policy
        self._ledger = ledger or ConfirmationLedger(clock=clock)
        self._clock = clock
        self._sleep = sleeper
        self._planner = Planner(self._providers, policy=policy, id_factory=id_factory)
        self._owned: dict[str, OwnershipRecord] = {}
        self._ownership_ledger = ownership_ledger

    # -- properties -------------------------------------------------------

    @property
    def policy(self) -> AuthorityPolicy:
        return self._policy

    @property
    def ledger(self) -> ConfirmationLedger:
        return self._ledger

    @property
    def ownership(self) -> tuple[OwnershipRecord, ...]:
        """Everything this run created or adopted, in order."""
        return tuple(self._owned.values())

    @property
    def revocable(self) -> tuple[OwnershipRecord, ...]:
        """The subset this run actually wrote, and may therefore delete."""
        return tuple(r for r in self._owned.values() if r.revocable)

    def adopt_from_ledger(self, ledger: OwnershipLedger) -> tuple[OwnershipRecord, ...]:
        """Load a previous run's records as *evidence*, never as authority.

        Every record comes back ``source='ledger-unverified'``, so ``revoke``
        still refuses it. The point is to hand an operator the ids a crashed
        run left behind, not to let a file on disk direct a deletion.
        """
        loaded = ledger.read_all()
        for record in loaded:
            self._owned.setdefault(record.fingerprint, record)
        return loaded

    # -- 1. inspect -------------------------------------------------------

    def inspect(self, principal_id: str, scope: str) -> EffectiveAccess:
        """What the principal has here: exact, inherited, and what was skipped.

        Completeness is ``partial`` by construction. Group-derived access, PIM
        eligibility, deny assignments and ABAC conditions are not evaluated, and
        an answer that omitted them and called itself complete would be worse
        than no answer.
        """
        provider = self._providers.get("azure-rbac")
        if provider is None:
            raise AccessError("inspect needs an azure-rbac adapter")
        # Reads are bounded too: this is a disclosure and it carries a token.
        self._policy.authorize_read(scope, what="inspect")
        principal = str(principal_id).lower()
        try:
            everything = provider.list_at_scope(scope)
        except TransportError as exc:
            return EffectiveAccess(
                principal_id=principal_id, scope=scope,
                completeness=Completeness.UNKNOWN,
                unevaluated=UNEVALUATED_SEMANTICS + (f"read-failed: {exc.category}",),
            )
        mine = [s for s in everything if s.principal_id.lower() == principal]
        exact = tuple(
            s for s in mine if s.scope.lower().rstrip("/") == str(scope).lower().rstrip("/")
        )
        inherited = tuple(s for s in mine if s not in exact)
        return EffectiveAccess(
            principal_id=principal_id,
            scope=scope,
            exact=exact,
            inherited=inherited,
            completeness=Completeness.PARTIAL,
            unevaluated=UNEVALUATED_SEMANTICS,
        )

    # -- 2. plan / 3. diff ------------------------------------------------

    def plan(self, declarations: Sequence[AccessDeclaration], *,
             action: str = "create") -> Plan:
        return self._planner.plan(declarations, action=action)

    def diff(self, declarations: Sequence[AccessDeclaration], *,
             include_excess_at: Sequence[str] = ()) -> DiffReport:
        return self._planner.diff(declarations, include_excess_at=include_excess_at)

    # -- 4. apply ---------------------------------------------------------

    def confirm(self, plan: Plan, *,
                fingerprints: Iterable[str] | None = None) -> dict[str, str]:
        """Mint one token per step that needs one, keyed by fingerprint.

        Deliberately a separate call: an operator (or an outer approval flow)
        decides to mint, and the token is bound to that exact target. There is
        no code path in which :meth:`apply` mints its own confirmation.

        ``fingerprints`` names exactly which targets are being approved. It is
        the difference between an operator approving *these three grants* and a
        caller writing ``confirmations=manager.confirm(plan)`` in the same
        expression as ``apply`` — which is what the shipped CLI did, turning a
        boolean flag into blanket approval of every step including
        ``administrative`` ones. Omitting it approves every mutating step and is
        only appropriate where the caller has already reviewed the plan digest.
        """
        required = {
            step.declaration.fingerprint()
            for step in plan.mutating
            if step.requires_confirmation
        }
        if fingerprints is None:
            wanted = required
        else:
            wanted = {str(f) for f in fingerprints}
            unknown = sorted(wanted - required)
            if unknown:
                raise AuthorizationRefused(
                    f"asked to confirm {unknown}, which this plan does not "
                    f"contain as a step needing confirmation"
                )
        return {
            fingerprint: self._ledger.mint(plan.plan_id, fingerprint)
            for fingerprint in sorted(wanted)
        }

    def apply(
        self,
        plan: Plan,
        *,
        confirmations: Mapping[str, str] | None = None,
        verify_budget_secs: float = DEFAULT_PROPAGATION_BUDGET_SECS,
    ) -> ApplyReport:
        """Execute the create steps, then read every one of them back."""
        tokens = dict(confirmations or {})
        ownership: list[OwnershipRecord] = []
        pending: list[OwnershipRecord] = []
        ledger_failures: list[dict[str, Any]] = []
        refusals: list[dict[str, Any]] = [dict(r) for r in plan.refusals]
        verifications: list[VerificationResult] = []
        for step in plan.steps:
            if step.action != "create":
                continue
            try:
                self._authorize_step(plan, step, tokens)
            except AuthorizationRefused as exc:
                refusals.append(_refusal(step, exc))
                continue
            provider = self._planner.provider_for(step.declaration)
            try:
                record = provider.create(step.declaration, plan_id=plan.plan_id)
            except OperationPending as exc:
                # Accepted, outcome unknown. Reported with the target id so it
                # can be cleaned up; never dropped, never claimed as absent.
                stuck = OwnershipRecord(
                    assignment_id=exc.target_id,
                    plane=step.declaration.plane,
                    plan_id=plan.plan_id,
                    fingerprint=step.declaration.fingerprint(),
                    principal_id=step.declaration.principal.object_id,
                    scope=step.declaration.scope,
                    role=step.declaration.role,
                    source="pending",
                    detail=sanitize_detail(str(exc), limit=300),
                )
                pending.append(stuck)
                failure = self._record_ownership(stuck, track=False)
                if failure is not None:
                    ledger_failures.append(failure)
                refusals.append(_refusal(step, exc))
                continue
            except AccessError as exc:
                refusals.append(_refusal(step, exc))
                continue
            failure = self._record_ownership(record)
            if failure is not None:
                ledger_failures.append(failure)
            ownership.append(record)
            verifications.append(
                self.verify_one(step.declaration, budget_secs=verify_budget_secs,
                                expect="present", wrote=record.source == "created")
            )
        return ApplyReport(
            plan_id=plan.plan_id,
            ownership=tuple(ownership),
            refusals=tuple(refusals),
            verifications=tuple(verifications),
            pending=tuple(pending),
            ledger_failures=tuple(ledger_failures),
        )

    def _record_ownership(self, record: OwnershipRecord, *,
                          track: bool = True) -> dict[str, Any] | None:
        """Track the record, persist it, and never lose an id to an OSError.

        The cloud write has already happened by the time this runs. A full
        disk or a read-only ledger directory must therefore be reported as an
        outcome carrying the assignment id — raising here would abandon a real
        grant with no record of what to clean up.
        """
        if track:
            self._owned[record.fingerprint] = record
        if self._ownership_ledger is None:
            return None
        try:
            self._ownership_ledger.append(record)
        except OSError as exc:
            return {
                "fingerprint": record.fingerprint,
                "assignment_id": record.assignment_id,
                "plane": record.plane,
                "scope": record.scope,
                "role": record.role,
                "source": record.source,
                "category": "ledger",
                "reason": (
                    f"the assignment was created and the ownership ledger could "
                    f"not be written: {sanitize_detail(str(exc), limit=200)}. "
                    f"Record this id by hand; it is the only cleanup coordinate"
                ),
            }
        return None

    def _authorize_step(self, plan: Plan, step: PlanStep,
                        tokens: Mapping[str, str]) -> None:
        self._policy.authorize(step)
        if not step.requires_confirmation:
            return
        fingerprint = step.declaration.fingerprint()
        token = tokens.get(fingerprint)
        if not token:
            raise AuthorizationRefused(
                f"{step.declaration.role} at {step.declaration.scope} is tier "
                f"'{step.tier}' and needs a confirmation token bound to this "
                f"exact target"
            )
        self._ledger.consume(token, plan.plan_id, fingerprint)

    # -- 5. verify --------------------------------------------------------

    def verify_one(
        self,
        declaration: AccessDeclaration,
        *,
        budget_secs: float = DEFAULT_PROPAGATION_BUDGET_SECS,
        poll_secs: float = DEFAULT_POLL_INTERVAL_SECS,
        expect: str = "present",
        wrote: bool = False,
    ) -> VerificationResult:
        """Poll the exact scope to a budget, then answer honestly."""
        self._policy.authorize_read(declaration.scope, what="verify")
        provider = self._planner.provider_for(declaration)
        started = self._clock()
        waited = 0.0
        last_error = ""
        while True:
            try:
                found: Sequence[AssignmentState] = provider.matches(declaration)
                duplicates = tuple(s.assignment_id for s in found[1:])
                present = bool(found)
                if present == (expect == "present"):
                    return VerificationResult(
                        fingerprint=declaration.fingerprint(),
                        status="present" if present else "absent",
                        scope=declaration.scope,
                        plane=declaration.plane,
                        waited_secs=waited,
                        detail=(
                            f"{len(found)} exact match(es) at this scope"
                            if present else "no exact match at this scope"
                        ),
                        duplicates=duplicates,
                    )
            except AccessError as exc:
                last_error = sanitize_detail(str(exc), limit=200)
            waited = self._clock() - started
            if waited >= budget_secs:
                break
            self._sleep(min(poll_secs, max(budget_secs - waited, 0.0)))
            waited = self._clock() - started
        if last_error:
            return VerificationResult(
                fingerprint=declaration.fingerprint(), status="unknown",
                scope=declaration.scope, plane=declaration.plane,
                waited_secs=waited,
                detail=f"read-back did not complete: {last_error}",
            )
        if expect == "present" and wrote:
            return VerificationResult(
                fingerprint=declaration.fingerprint(), status="revert-suspected",
                scope=declaration.scope, plane=declaration.plane,
                waited_secs=waited,
                detail=(
                    f"the write reported success and no assignment is readable at "
                    f"this exact scope after {waited:.0f}s: either a governance "
                    f"policy reverted it or propagation is still in flight — check "
                    f"policy assignments before re-granting"
                ),
            )
        return VerificationResult(
            fingerprint=declaration.fingerprint(),
            status="absent" if expect == "present" else "present",
            scope=declaration.scope, plane=declaration.plane, waited_secs=waited,
            detail=f"expected {expect} and the read-back disagreed after {waited:.0f}s",
        )

    def verify(self, declarations: Sequence[AccessDeclaration], *,
               budget_secs: float = DEFAULT_PROPAGATION_BUDGET_SECS,
               expect: str = "present") -> tuple[VerificationResult, ...]:
        return tuple(
            self.verify_one(d, budget_secs=budget_secs, expect=expect)
            for d in declarations
        )

    # -- 6. revoke --------------------------------------------------------

    def revoke(
        self,
        declarations: Sequence[AccessDeclaration],
        *,
        authorized_ids: Iterable[str] = (),
        budget_secs: float = DEFAULT_PROPAGATION_BUDGET_SECS,
    ) -> RevokeReport:
        """Delete assignments this run *created*, or ids explicitly named.

        Three independent conditions have to hold before a delete is built, and
        each of them was a reproduced defect:

        1. the ownership record exists **and** ``source == "created"``. An
           ``adopted`` record \u2014 ARM's 409 path, or Cosmos and Kusto finding a
           pre-existing match \u2014 means somebody else made this grant. Being in
           ``_owned`` was the old test and it deleted other teams' state;
        2. the id currently readable at this scope equals the id that was
           recorded. An adapter is caller-supplied and mutable, so id
           immutability is an assumption, not a guarantee;
        3. the assignment still matches the declaration exactly \u2014 same
           principal, same role, same scope, same condition and version \u2014 so a
           role that changed underneath a stale record is not deleted on the
           strength of an id alone.

        Anything else is refused with the reason, and left in place.

        A record is dropped only once the **exact id** is proved gone. A
        delete that was accepted (202), or whose read-back is unknown or still
        shows the target, keeps its ownership record and its ledger file and is
        reported in ``RevokeReport.retained``: those are the only cleanup
        coordinates that exist, and deleting them on the strength of an
        accepted DELETE is how a live assignment becomes unfindable.
        """
        allowed = {str(i) for i in authorized_ids}
        deleted: list[str] = []
        refused: list[dict[str, Any]] = []
        retained: list[dict[str, Any]] = []
        verifications: list[VerificationResult] = []
        for declaration in declarations:
            fingerprint = declaration.fingerprint()
            step = PlanStep("revoke", declaration, "revocation requested",
                            requires_confirmation=False)
            try:
                self._policy.authorize(step)
            except AuthorizationRefused as exc:
                refused.append(_refusal(step, exc))
                continue
            provider = self._planner.provider_for(declaration)
            record = self._owned.get(fingerprint)
            try:
                present = provider.matches(declaration)
            except AccessError as exc:
                refused.append(_refusal(step, exc))
                continue
            targets: list[str] = []
            observed = tuple(s.assignment_id for s in present)
            if (
                record is not None
                and record.revocable
                and record.assignment_id not in observed
            ):
                # A previous run's delete landed after all. Absence is proved by
                # this read, so the coordinate is no longer needed.
                self._owned.pop(fingerprint, None)
                if self._ownership_ledger is not None:
                    try:
                        self._ownership_ledger.remove(record.assignment_id)
                    except OSError as exc:
                        retained.append(
                            _retained(declaration, record.assignment_id,
                                      "ledger-write",
                                      sanitize_detail(str(exc), limit=160))
                        )
            for state in present:
                decision = _may_delete(state, declaration, record, allowed,
                                       identity_matches=getattr(
                                           provider, "identity_matches", None))
                if decision is None:
                    targets.append(state.assignment_id)
                else:
                    refused.append(
                        {
                            "fingerprint": fingerprint,
                            "assignment_id": state.assignment_id,
                            "category": "ownership",
                            "reason": decision,
                        }
                    )
            for assignment_id in targets:
                try:
                    provider.delete(assignment_id)
                except OperationPending as exc:
                    # Accepted, not finished. The record is the only cleanup
                    # coordinate, so it stays until absence is proven.
                    refused.append(_refusal(step, exc))
                    retained.append(
                        _retained(declaration, assignment_id, "delete-pending",
                                  sanitize_detail(str(exc), limit=200))
                    )
                    continue
                except AccessError as exc:
                    refused.append(_refusal(step, exc))
                    continue
                deleted.append(assignment_id)
                status, detail, others = self._target_absent(
                    declaration, assignment_id, budget_secs=budget_secs)
                if status != "absent":
                    retained.append(
                        _retained(declaration, assignment_id,
                                  f"target-{status}", detail)
                    )
                    continue
                # Proven gone. Foreign duplicates at the same scope are
                # reported, never a reason to keep this run's coordinate.
                if others:
                    refused.append(
                        {
                            "fingerprint": fingerprint,
                            "assignment_id": ", ".join(others),
                            "category": "ownership",
                            "reason": (
                                "still present at this scope and not created by "
                                "this run; left in place"
                            ),
                        }
                    )
                if record is not None and record.assignment_id == assignment_id:
                    self._owned.pop(fingerprint, None)
                if self._ownership_ledger is not None:
                    try:
                        self._ownership_ledger.remove(assignment_id)
                    except OSError as exc:
                        retained.append(
                            _retained(declaration, assignment_id, "ledger-write",
                                      f"the assignment is gone and its ledger "
                                      f"record could not be removed: "
                                      f"{sanitize_detail(str(exc), limit=160)}")
                        )
            verifications.append(
                self.verify_one(declaration, budget_secs=budget_secs, expect="absent")
            )
        return RevokeReport(
            deleted=tuple(deleted), refused=tuple(refused),
            verifications=tuple(verifications), retained=tuple(retained),
        )

    def _target_absent(
        self,
        declaration: AccessDeclaration,
        assignment_id: str,
        *,
        budget_secs: float,
        poll_secs: float = DEFAULT_POLL_INTERVAL_SECS,
    ) -> tuple[str, str, tuple[str, ...]]:
        """Whether *this exact id* is gone: ``absent``, ``present`` or ``unknown``.

        Deliberately not "no assignment matches this declaration any more". A
        second team's assignment at the same scope, with the same role, is not
        this run's to wait for; requiring it to disappear would either hang the
        teardown or, worse, invite deleting it.
        """
        provider = self._planner.provider_for(declaration)
        started = self._clock()
        waited = 0.0
        last_error = ""
        others: tuple[str, ...] = ()
        while True:
            try:
                found = provider.matches(declaration)
                ids = tuple(s.assignment_id for s in found)
                others = tuple(i for i in ids if i != assignment_id)
                if assignment_id not in ids:
                    return (
                        "absent",
                        f"{assignment_id} is no longer readable at this scope",
                        others,
                    )
                last_error = ""
            except AccessError as exc:
                last_error = sanitize_detail(str(exc), limit=200)
            waited = self._clock() - started
            if waited >= budget_secs:
                break
            self._sleep(min(poll_secs, max(budget_secs - waited, 0.0)))
            waited = self._clock() - started
        if last_error:
            return (
                "unknown",
                f"the delete was accepted and the read-back did not complete "
                f"after {waited:.0f}s: {last_error}",
                others,
            )
        return (
            "present",
            f"the delete was accepted and {assignment_id} is still readable at "
            f"this scope after {waited:.0f}s",
            others,
        )


def _may_delete(
    state: AssignmentState,
    declaration: AccessDeclaration,
    record: OwnershipRecord | None,
    authorized_ids: set[str],
    *,
    identity_matches: Callable[[AssignmentState, AccessDeclaration], bool] | None = None,
) -> str | None:
    """``None`` when the delete is permitted, else the refusal reason.

    ``identity_matches`` lets a plane whose role identity is not the catalogue
    definition id — Graph carries it in ``target['app_role_id']``, SQL in the
    permission row — supply its own comparison. Without the hook the model's
    exact match is used, which is right for the three ARM-shaped planes.
    """
    still_matches = (
        identity_matches(state, declaration) if identity_matches is not None
        else state.matches(declaration)
    )
    if not still_matches:
        return (
            "the assignment currently at this scope is no longer what the "
            "declaration describes; refusing to delete on the strength of an "
            "id alone"
        )
    if state.assignment_id in authorized_ids:
        return None
    if record is None:
        return (
            "not created by this run and not explicitly authorised "
            "(--authorized-id); left in place"
        )
    if not record.revocable:
        return (
            f"recorded as '{record.source}', not created by this run, so this "
            f"teardown will not remove it; pass the id explicitly if you have "
            f"decided it is yours to delete"
        )
    if state.assignment_id != record.assignment_id:
        return (
            "the id readable at this scope is not the id this run created; the "
            "assignment was replaced by another writer and is left in place"
        )
    return None


def _retained(declaration: AccessDeclaration, assignment_id: str, reason: str,
              detail: str) -> dict[str, Any]:
    """One kept cleanup coordinate, with why it was kept."""
    return {
        "fingerprint": declaration.fingerprint(),
        "assignment_id": assignment_id,
        "plane": declaration.plane,
        "scope": declaration.scope,
        "role": declaration.role,
        "category": "cleanup",
        "reason": reason,
        "detail": detail,
    }


def _refusal(step: PlanStep, exc: Exception) -> dict[str, Any]:
    payload = {
        "fingerprint": step.declaration.fingerprint(),
        "role": step.declaration.role,
        "scope": step.declaration.scope,
        "category": getattr(exc, "category", "error"),
        "reason": sanitize_detail(str(exc), limit=300),
    }
    target = getattr(exc, "target_id", "")
    if target:
        payload["pending_target_id"] = target
    return payload


__all__ = [
    "AccessManager",
    "DEFAULT_POLL_INTERVAL_SECS",
    "DEFAULT_PROPAGATION_BUDGET_SECS",
]