"""Local authority: what this process will build a request for, and nothing else.

WHY AUTHORISATION LIVES HERE AND NOT IN THE REQUEST
---------------------------------------------------
The tempting design is a flag on the request — ``{"approved": true}`` — and it
is security fiction: whoever composes the request composes the flag. Authority
in this package is a :class:`AuthorityPolicy` object constructed by the *host*
at start-up from configuration the caller cannot reach, and every plan step is
checked against it. A request that carries an authority-shaped field is
refused outright rather than read (:func:`refuse_embedded_authority`), because
the only reason to send one is to be believed.

THREE INDEPENDENT GATES
-----------------------
1. **Runtime allowlist** — tenant and scope prefixes fixed at construction.
   Independent of the requested target, so a plan cannot widen its own bounds.
2. **Privilege tier** — roles above ``max_tier`` are refused unless the exact
   role name was authorised in advance. Privileged tiers are not banned
   generally and never automatically elevated.
3. **Confirmation** — a mutation at or above the confirmation tier needs a
   single-use token minted by this process and bound to the exact target.

SELF-GRANT
----------
Granting to your own principal is the classic escalation, so it is refused by
default and enabled only by naming the principal ids that count as "self" and
setting ``allow_self_grant``. A policy that does not know its own principal
cannot enforce this, which is why the ids are a required-to-be-explicit field
rather than something discovered at runtime.

READS ARE BOUNDED TOO
---------------------
An audit found the scope allowlist applied only to mutations: ``inspect``,
``diff`` and ``verify`` issued a GET against any scope the caller named, so a
policy advertised as "the runtime bound" bounded half the runtime. Reading who
can reach a finance resource group is a disclosure, and a read is also a
request carrying a token. So :meth:`AuthorityPolicy.authorize_read` exists and
is called before every read. ``enforce_read_bounds`` can be turned off, but
only as a deliberate, visible field on the policy — a broad auditor genuinely
needs it, and that is a different contract from the default.

DEPENDENCIES
------------
Standard library only.
"""

from __future__ import annotations

import hmac
import secrets
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping

from azaccess.errors import AuthorizationRefused, CoordinateError
from azaccess.model import PlanStep
from azaccess.roles import TIERS
from azaccess.scopes import Scope, contains_segments, normalize_scope

#: Field names that must never be read from a caller-supplied payload. Their
#: presence is treated as an attempt to self-authorise.
FORBIDDEN_REQUEST_FIELDS: tuple[str, ...] = (
    "approved",
    "authorized",
    "authorised",
    "capability",
    "elevate",
    "bypass_policy",
    "force",
    "principal_type_override",
    "confirmation_secret",
)


def refuse_embedded_authority(payload: Mapping[str, Any]) -> None:
    """Refuse any request body that tries to carry its own authorisation."""
    present = sorted(
        k for k in payload if str(k).strip().lower() in FORBIDDEN_REQUEST_FIELDS
    )
    if present:
        raise AuthorizationRefused(
            f"request carries authority-shaped field(s) {present}; authorisation "
            f"comes from the host policy, never from the request"
        )


@dataclass(frozen=True)
class AuthorityPolicy:
    """The runtime bound on every mutation this process will attempt."""

    allowed_tenants: frozenset[str] = frozenset()
    #: Scope prefixes. A step is in bounds only when one of these contains it.
    allowed_scopes: tuple[str, ...] = ()
    max_tier: str = "read"
    #: Role names permitted above ``max_tier``. Named individually, on purpose.
    authorized_roles: frozenset[str] = frozenset()
    #: Tier at which a mutation additionally needs a confirmation token.
    confirmation_tier: str = "write"
    allow_self_grant: bool = False
    self_principal_ids: frozenset[str] = frozenset()
    allowed_planes: frozenset[str] = frozenset()
    read_only: bool = True
    #: Apply the scope allowlist to reads as well as writes. Default on; a
    #: policy that wants estate-wide discovery turns it off explicitly and the
    #: describe() output says so.
    enforce_read_bounds: bool = True

    def __post_init__(self) -> None:
        if self.max_tier not in TIERS:
            raise AuthorizationRefused(f"'{self.max_tier}' is not a privilege tier")
        if self.confirmation_tier not in TIERS:
            raise AuthorizationRefused(
                f"'{self.confirmation_tier}' is not a privilege tier"
            )
        object.__setattr__(
            self,
            "allowed_scopes",
            tuple(normalize_scope(s) for s in self.allowed_scopes),
        )

    # -- individual gates -------------------------------------------------

    def scope_in_bounds(self, scope: str) -> bool:
        """True when ``scope`` is at or beneath an allowlisted scope.

        Segment-structural, and on a validated id. A raw string prefix test
        answered True for a scope whose resource name was followed by
        parent-directory segments leading into another resource group, and for
        ``rg-app`` containing ``rg-application``; both are refused now, the
        first at :func:`~azaccess.scopes.normalize_scope`.
        """
        target = normalize_scope(scope)
        return any(contains_segments(allowed, target) for allowed in self.allowed_scopes)

    def authorize_read(self, scope: str, *, what: str = "read") -> None:
        """Refuse a read outside the allowlist before a request is built."""
        if not self.enforce_read_bounds:
            return
        try:
            in_bounds = self.scope_in_bounds(scope)
        except CoordinateError as exc:
            raise AuthorizationRefused(f"{what}: {exc}") from None
        if not in_bounds:
            raise AuthorizationRefused(
                f"{what} at {scope} is outside the allowlist; reads are bounded "
                f"too, because a read is a disclosure and carries a token. Set "
                f"enforce_read_bounds=False deliberately to widen it"
            )

    def authorize_plane(self, plane: str) -> None:
        if self.allowed_planes and plane not in self.allowed_planes:
            raise AuthorizationRefused(
                f"plane '{plane}' is not enabled for this policy"
            )

    def tenant_in_bounds(self, tenant_id: str) -> bool:
        if not self.allowed_tenants:
            return False
        return str(tenant_id or "").lower() in {t.lower() for t in self.allowed_tenants}

    def tier_allowed(self, tier: str, role_name: str) -> bool:
        if role_name in self.authorized_roles:
            return True
        return TIERS.index(tier) <= TIERS.index(self.max_tier)

    def needs_confirmation(self, tier: str) -> bool:
        return TIERS.index(tier) >= TIERS.index(self.confirmation_tier)

    # -- the whole decision -----------------------------------------------

    def authorize(self, step: PlanStep) -> None:
        """Raise :class:`AuthorizationRefused` unless every gate passes."""
        declaration = step.declaration
        if step.action in ("create", "revoke") and self.read_only:
            raise AuthorizationRefused(
                f"policy is read-only; '{step.action}' refused for "
                f"{declaration.role} at {declaration.scope}"
            )
        tenant = declaration.principal.tenant_id
        if not tenant:
            raise AuthorizationRefused(
                "principal carries no tenant_id, so the tenant allowlist cannot "
                "be enforced; supply it explicitly"
            )
        if not self.tenant_in_bounds(tenant):
            raise AuthorizationRefused(
                f"tenant {tenant} is outside the allowlist "
                f"({len(self.allowed_tenants)} tenant(s) permitted)"
            )
        if not self.scope_in_bounds(declaration.scope):
            raise AuthorizationRefused(
                f"scope {declaration.scope} is outside the allowlist; the "
                f"allowlist is fixed at start-up and does not follow the request"
            )
        role = declaration.role_definition
        self.authorize_plane(role.plane)
        if not self.tier_allowed(role.tier, role.name):
            raise AuthorizationRefused(
                f"{role.name} is tier '{role.tier}', above the policy maximum "
                f"'{self.max_tier}', and was not individually authorised"
            )
        if (
            step.action == "create"
            and not self.allow_self_grant
            and declaration.principal.object_id.lower()
            in {p.lower() for p in self.self_principal_ids}
        ):
            raise AuthorizationRefused(
                "self-grant refused: the target principal is this process's own"
            )

    def with_authorized(
        self,
        *,
        roles: Iterable[str] = (),
        read_only: bool | None = None,
        max_tier: str | None = None,
        enforce_read_bounds: bool | None = None,
    ) -> "AuthorityPolicy":
        """A narrowed or deliberately widened copy, for one operation.

        Returns a new policy rather than mutating, so the widening is visible
        at the call site that decided it and cannot leak into later steps.
        """
        return AuthorityPolicy(
            allowed_tenants=self.allowed_tenants,
            allowed_scopes=self.allowed_scopes,
            max_tier=max_tier or self.max_tier,
            authorized_roles=frozenset(self.authorized_roles) | frozenset(roles),
            confirmation_tier=self.confirmation_tier,
            allow_self_grant=self.allow_self_grant,
            self_principal_ids=self.self_principal_ids,
            allowed_planes=self.allowed_planes,
            read_only=self.read_only if read_only is None else read_only,
            enforce_read_bounds=(
                self.enforce_read_bounds
                if enforce_read_bounds is None
                else enforce_read_bounds
            ),
        )

    def describe(self) -> dict[str, Any]:
        """Non-secret summary. Token material never appears here."""
        return {
            "tenants": len(self.allowed_tenants),
            "scopes": list(self.allowed_scopes),
            "max_tier": self.max_tier,
            "authorized_roles": sorted(self.authorized_roles),
            "confirmation_tier": self.confirmation_tier,
            "allow_self_grant": self.allow_self_grant,
            "read_only": self.read_only,
            "enforce_read_bounds": self.enforce_read_bounds,
        }


@dataclass
class ConfirmationLedger:
    """Mints and consumes single-use, target-bound confirmation tokens.

    The token is minted **by this process** and handed to the operator to
    return. It is never derived from the request, so an attacker who can
    compose a request cannot compose the token; and it is bound to one
    fingerprint, so a token minted for a Reader grant cannot confirm an Owner
    grant that arrives a second later.
    """

    ttl_secs: float = 300.0
    clock: Callable[[], float] = field(default=lambda: 0.0)
    _issued: dict[str, tuple[str, str, float]] = field(default_factory=dict)

    def mint(self, plan_id: str, fingerprint: str) -> str:
        token = secrets.token_urlsafe(24)
        self._issued[token] = (plan_id, fingerprint, self.clock() + self.ttl_secs)
        return token

    def consume(self, token: str, plan_id: str, fingerprint: str) -> None:
        """Validate first, then burn. A refusal never says which gate leaked.

        Order matters and used to be wrong: the token was popped *before* the
        binding was checked, so one attempt against the wrong target destroyed
        the operator's valid approval for the right one — a retry-triggered
        denial of the approval path. A mismatched or expired presentation now
        leaves a valid token exactly where it was; only a fully valid one is
        consumed, and it is consumed once.
        """
        key = str(token or "")
        record = self._issued.get(key)
        if record is None:
            raise AuthorizationRefused(
                "no valid confirmation token for this step (unknown, already "
                "used, or never minted)"
            )
        issued_plan, issued_fingerprint, expires = record
        if self.clock() > expires:
            # Expired material is useless; dropping it is not a denial path.
            self._issued.pop(key, None)
            raise AuthorizationRefused("confirmation token has expired")
        if not hmac.compare_digest(issued_plan, plan_id) or not hmac.compare_digest(
            issued_fingerprint, fingerprint
        ):
            raise AuthorizationRefused(
                "confirmation token is bound to a different target; refusing to "
                "reuse it, and leaving it valid for the target it was minted for"
            )
        self._issued.pop(key, None)

    @property
    def outstanding(self) -> int:
        return len(self._issued)


def bounded_policy(
    *,
    tenant_id: str,
    scopes: Iterable[str],
    max_tier: str = "read",
    self_principal_ids: Iterable[str] = (),
    enforce_read_bounds: bool = True,
) -> AuthorityPolicy:
    """A read-only policy bounded to one tenant and an explicit scope list.

    The default a host should start from: read-only, one tenant, no self-grant,
    reads bounded to the same scopes as writes. Widening is a separate, visible
    call to :meth:`AuthorityPolicy.with_authorized`.
    """
    return AuthorityPolicy(
        allowed_tenants=frozenset({tenant_id}),
        allowed_scopes=tuple(normalize_scope(s) for s in scopes),
        max_tier=max_tier,
        self_principal_ids=frozenset(self_principal_ids),
        read_only=True,
        enforce_read_bounds=enforce_read_bounds,
    )


__all__ = [
    "AuthorityPolicy",
    "ConfirmationLedger",
    "FORBIDDEN_REQUEST_FIELDS",
    "bounded_policy",
    "refuse_embedded_authority",
]
