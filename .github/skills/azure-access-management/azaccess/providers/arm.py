"""Azure RBAC role assignments — the only plane ARM's assignment APIs cover.

WHAT THIS PLANE IS
------------------
``Microsoft.Authorization/roleAssignments`` at any scope in the ARM hierarchy.
Create is idempotent in effect but not in name: PUT-ing a *new* GUID name for
an assignment that already exists answers ``409 RoleAssignmentExists``, which
is success in the world and a conflict on the wire. This adapter treats it as
adopt-and-record, never as failure and never as a fresh creation.

EXACT SCOPE, ALWAYS
-------------------
The list URL uses ``$filter=atScope()``, which *includes inherited*
assignments. Every match here re-checks ``properties.scope`` textually, so an
Owner assignment inherited from the subscription can never satisfy a check for
a Reader assignment on one container.

CONDITIONS ARE PART OF IDENTITY
-------------------------------
An assignment with an ABAC condition is a different assignment from the
unconditional one with the same role, principal and scope. Conflating them
either reports access that is conditional as unconditional, or deletes a
narrow assignment believing it is the broad one.

DENY ASSIGNMENTS
----------------
Readable, never writable: deny assignments are created only by Azure Blueprints
and Managed Applications. They are listed here because an effective-access
answer that ignores them is wrong in the dangerous direction, and refused for
write because nothing else is possible.
"""

from __future__ import annotations

import uuid
from typing import Any, Callable, Mapping

from azaccess.authorization import refuse_embedded_authority
from azaccess.errors import ProviderConflict, TransportError
from azaccess.model import AccessDeclaration, AssignmentState, OwnershipRecord
from azaccess.providers.base import created_id, page_values, require_ok
from azaccess.scopes import Scope
from azaccess.transport import UNKNOWN_STATUS, Transport, sanitize_detail

ARM_ENDPOINT = "https://management.azure.com"
ROLE_ASSIGNMENT_API = "2022-04-01"
DENY_ASSIGNMENT_API = "2022-04-01"


class ArmRbacProvider:
    """Azure RBAC assignments: list at exact scope, create, adopt, delete."""

    plane = "azure-rbac"

    operations: Mapping[str, str] = {
        "list-at-scope": "implemented",
        "list-inherited": "implemented",
        "list-deny-assignments": "implemented",
        "create-assignment": "implemented",
        "create-conditional-assignment": "implemented",
        "delete-assignment": "implemented",
        "custom-role-definition-lifecycle": "documented",
        "pim-eligible-assignment": "documented",
        "create-deny-assignment": "unsupported",
    }

    def __init__(
        self,
        transport: Transport,
        *,
        subscription_id: str,
        endpoint: str = ARM_ENDPOINT,
        api_version: str = ROLE_ASSIGNMENT_API,
        name_factory: Callable[[], str] | None = None,
    ) -> None:
        self._transport = transport
        self._subscription = subscription_id
        self._endpoint = endpoint.rstrip("/")
        self._api = api_version
        self._names = name_factory or (lambda: str(uuid.uuid4()))

    # -- read -------------------------------------------------------------

    def _list_url(self, scope: str) -> str:
        return (
            f"{self._endpoint}{scope}/providers/Microsoft.Authorization"
            f"/roleAssignments?api-version={self._api}&$filter=atScope()"
        )

    def list_at_scope(self, scope: str) -> tuple[AssignmentState, ...]:
        """Every assignment visible at ``scope``, inherited ones included."""
        parsed = Scope.parse(scope)
        items = page_values(
            self._transport, self._list_url(parsed.value),
            f"listing role assignments at {parsed.value}",
        )
        return tuple(_state(item) for item in items)

    def list_exact(self, scope: str) -> tuple[AssignmentState, ...]:
        """Only assignments written at exactly ``scope``."""
        parsed = Scope.parse(scope)
        return tuple(
            state for state in self.list_at_scope(parsed.value)
            if state.scope.lower().rstrip("/") == parsed.value.lower()
        )

    def list_inherited(self, scope: str) -> tuple[AssignmentState, ...]:
        parsed = Scope.parse(scope)
        return tuple(
            state for state in self.list_at_scope(parsed.value)
            if state.scope.lower().rstrip("/") != parsed.value.lower()
        )

    def list_for(self, declaration: AccessDeclaration) -> tuple[AssignmentState, ...]:
        return self.list_exact(declaration.scope)

    def matches(self, declaration: AccessDeclaration) -> tuple[AssignmentState, ...]:
        """Assignments that are exactly what the declaration asked for."""
        return tuple(s for s in self.list_exact(declaration.scope)
                     if s.matches(declaration))

    def list_deny_assignments(self, scope: str) -> tuple[AssignmentState, ...]:
        parsed = Scope.parse(scope)
        url = (
            f"{self._endpoint}{parsed.value}/providers/Microsoft.Authorization"
            f"/denyAssignments?api-version={DENY_ASSIGNMENT_API}"
        )
        items = page_values(self._transport, url,
                            f"listing deny assignments at {parsed.value}")
        states: list[AssignmentState] = []
        for item in items:
            properties = dict(item.get("properties") or {})
            for principal in properties.get("principals") or [{}]:
                states.append(
                    AssignmentState(
                        assignment_id=str(item.get("id") or ""),
                        plane="azure-rbac-deny",
                        principal_id=str(principal.get("id") or ""),
                        role_definition_id=str(properties.get("denyAssignmentName") or ""),
                        scope=str(properties.get("scope") or parsed.value),
                        raw_name=str(item.get("name") or ""),
                    )
                )
        return tuple(states)

    # -- write ------------------------------------------------------------

    def build_create_body(self, declaration: AccessDeclaration) -> dict[str, Any]:
        """The request body, built here so a test can assert its shape."""
        role = declaration.role_definition
        body: dict[str, Any] = {
            "properties": {
                "roleDefinitionId": role.arm_definition_id(self._subscription),
                "principalId": declaration.principal.object_id,
                # Explicit: without it ARM does a directory lookup that fails
                # for a principal created seconds ago (GOTCHAS.md, G3).
                "principalType": declaration.principal.principal_type,
            }
        }
        if declaration.condition:
            body["properties"]["condition"] = declaration.condition
            body["properties"]["conditionVersion"] = (
                declaration.condition_version or "2.0"
            )
        return body

    def create(self, declaration: AccessDeclaration, *, plan_id: str) -> OwnershipRecord:
        refuse_embedded_authority(dict(declaration.target))
        scope = Scope.parse(declaration.scope).value
        name = self._names()
        url = (
            f"{self._endpoint}{scope}/providers/Microsoft.Authorization"
            f"/roleAssignments/{name}?api-version={self._api}"
        )
        response = self._transport.request(
            "PUT", url, json_body=self.build_create_body(declaration)
        )
        if not response.status_exact:
            raise TransportError(
                f"granting {declaration.role} at {scope} used a transport that "
                f"cannot report the HTTP status; 201 Created and 409 "
                f"RoleAssignmentExists are not distinguishable, so this create "
                f"is refused rather than guessed"
            )
        if response.status in (200, 201):
            body = response.json_body()
            return OwnershipRecord(
                assignment_id=created_id(body, "creating a role assignment"),
                plane=self.plane,
                plan_id=plan_id,
                fingerprint=declaration.fingerprint(),
                principal_id=declaration.principal.object_id,
                scope=scope,
                role=declaration.role,
                source="created",
            )
        if response.status == 409:
            return self._adopt(declaration, plan_id=plan_id)
        if response.status == UNKNOWN_STATUS:
            raise TransportError(
                f"granting {declaration.role} at {scope} failed and the backend "
                f"could not determine the HTTP status; refusing to treat it as "
                f"an existing assignment: "
                f"{sanitize_detail(str(response.body), limit=300)}"
            )
        raise TransportError(
            f"granting {declaration.role} at {scope} answered HTTP "
            f"{response.status}: {sanitize_detail(str(response.body), limit=300)}"
        )

    def _adopt(self, declaration: AccessDeclaration, *, plan_id: str) -> OwnershipRecord:
        """Record a pre-existing assignment as adopted, with its real id.

        Adoption is idempotency done honestly: the id is read back from the
        service, and ``source='adopted'`` says this run did not create it — so
        a later teardown can decline to remove somebody else's grant.
        """
        existing = self.matches(declaration)
        if not existing:
            raise ProviderConflict(
                f"ARM reported the assignment already exists, and no exact match "
                f"is readable at {declaration.scope}; another writer may hold a "
                f"conditional or differently-scoped assignment"
            )
        return OwnershipRecord(
            assignment_id=existing[0].assignment_id,
            plane=self.plane,
            plan_id=plan_id,
            fingerprint=declaration.fingerprint(),
            principal_id=declaration.principal.object_id,
            scope=Scope.parse(declaration.scope).value,
            role=declaration.role,
            source="adopted",
        )

    def delete(self, assignment_id: str) -> None:
        url = f"{self._endpoint}{assignment_id}?api-version={self._api}"
        response = self._transport.request("DELETE", url)
        # 404 is success: the desired end state is absence.
        require_ok(response, f"deleting {assignment_id}", allowed=(204, 404))


def _state(item: Mapping[str, Any]) -> AssignmentState:
    properties = dict(item.get("properties") or {})
    return AssignmentState(
        assignment_id=str(item.get("id") or ""),
        plane="azure-rbac",
        principal_id=str(properties.get("principalId") or ""),
        role_definition_id=str(properties.get("roleDefinitionId") or ""),
        scope=str(properties.get("scope") or ""),
        condition=str(properties.get("condition") or ""),
        condition_version=str(properties.get("conditionVersion") or ""),
        principal_type=str(properties.get("principalType") or ""),
        raw_name=str(item.get("name") or ""),
    )


__all__ = ["ARM_ENDPOINT", "ArmRbacProvider", "DENY_ASSIGNMENT_API",
           "ROLE_ASSIGNMENT_API"]
