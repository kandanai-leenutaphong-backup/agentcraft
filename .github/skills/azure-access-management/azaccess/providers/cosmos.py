"""Cosmos DB SQL role assignments — an ARM API that is not Azure RBAC.

TWO PROPERTIES THAT BREAK NAIVE CODE
------------------------------------
1. **Invisible to Azure RBAC.** A Cosmos data-plane assignment is a child of
   the account (``sqlRoleAssignments``), not a ``Microsoft.Authorization``
   assignment. It never appears in a role-assignment list and an Azure RBAC
   delete will never remove it. Revoking Azure RBAC alone leaves the principal
   still reading every document.
2. **Create is not idempotent.** PUT-ing a new GUID name for the same
   principal, scope and role mints a *second* assignment. There is no 409.
   Both then have to be removed, and code that deletes "the" assignment leaves
   access in place.

So this adapter reads before it writes, and reports duplicates rather than
silently deleting every match: deleting all of them is exactly how a shared
account loses an assignment another team made.

SCOPE IS A DATA-PLANE PATH
--------------------------
``<accountId>/dbs/<db>/colls/<container>`` — not an ARM child resource id, and
not addressable by ARM's scope machinery. The account id is recovered from the
prefix so the caller supplies one coordinate instead of two.

CREATE IS LONG-RUNNING
----------------------
``PUT …/sqlRoleAssignments/{name}`` answers ``201`` when it completes inline
and ``202 Accepted`` with an ``Azure-AsyncOperation`` header and **no body**
when it does not. Reading ``id`` off that empty body raised, recorded no
ownership, and left an assignment that later landed unrevocable by this run.
So the name is minted first, the target id is derived from it as a *cleanup
coordinate*, and the outcome is resolved by
:func:`~azaccess.providers.base.resolve_long_running_create` — which records
ownership only from a read-back that returns a real id, and raises
:class:`~azaccess.errors.OperationPending` carrying the target id when it
cannot conclude.

Reference: Azure Cosmos DB "SQL Role Assignments - Create Update" (202 +
Azure-AsyncOperation) and the ARM "Asynchronous operations" contract.
"""

from __future__ import annotations

import uuid
from typing import Any, Callable, Mapping

from azaccess.errors import CoordinateError, ProviderConflict
from azaccess.model import AccessDeclaration, AssignmentState, OwnershipRecord
from azaccess.providers.arm import ARM_ENDPOINT
from azaccess.providers.base import (
    created_id,
    page_values,
    require_ok,
    resolve_long_running_create,
)
from azaccess.transport import Transport, sanitize_detail

COSMOS_SQL_API = "2024-11-15"


def account_from_scope(scope: str) -> str:
    """The account ARM id inside a Cosmos data-plane scope."""
    text = str(scope or "").rstrip("/")
    marker = "/dbs/"
    if marker in text:
        return text.split(marker, 1)[0]
    if "/databaseAccounts/" in text:
        return text
    raise CoordinateError(
        f"not a Cosmos scope: {text[:80]!r}; expected an account id, optionally "
        f"followed by /dbs/<database>/colls/<container>"
    )


class CosmosSqlRbacProvider:
    """Cosmos SQL role assignments: read-before-write, duplicate-aware."""

    plane = "cosmos-sql-rbac"

    operations: Mapping[str, str] = {
        "list-account-assignments": "implemented",
        "create-assignment": "implemented",
        "detect-duplicates": "implemented",
        "delete-assignment": "implemented",
        "custom-sql-role-definition": "documented",
        "delete-database-or-container": "unsupported",
    }

    def __init__(
        self,
        transport: Transport,
        *,
        endpoint: str = ARM_ENDPOINT,
        api_version: str = COSMOS_SQL_API,
        name_factory: Callable[[], str] | None = None,
        max_polls: int = 30,
        sleeper: Callable[[float], None] | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._transport = transport
        self._endpoint = endpoint.rstrip("/")
        self._api = api_version
        self._names = name_factory or (lambda: str(uuid.uuid4()))
        self._max_polls = max_polls
        self._sleeper = sleeper
        self._clock = clock

    def _list_url(self, account_id: str) -> str:
        return (
            f"{self._endpoint}{account_id}/sqlRoleAssignments"
            f"?api-version={self._api}"
        )

    def list_for_account(self, account_id: str) -> tuple[AssignmentState, ...]:
        items = page_values(
            self._transport, self._list_url(account_id),
            f"listing Cosmos SQL role assignments on {account_id}",
        )
        return tuple(_state(item) for item in items)

    def list_for(self, declaration: AccessDeclaration) -> tuple[AssignmentState, ...]:
        account = account_from_scope(declaration.scope)
        return tuple(
            s for s in self.list_for_account(account)
            if s.scope.lower().rstrip("/") == declaration.scope.lower().rstrip("/")
        )

    def matches(self, declaration: AccessDeclaration) -> tuple[AssignmentState, ...]:
        return tuple(s for s in self.list_for(declaration) if s.matches(declaration))

    def build_create_body(self, declaration: AccessDeclaration) -> dict[str, Any]:
        account = account_from_scope(declaration.scope)
        role = declaration.role_definition
        return {
            "properties": {
                "roleDefinitionId": (
                    f"{account}/sqlRoleDefinitions/{role.definition_id}"
                ),
                "principalId": declaration.principal.object_id,
                "scope": declaration.scope.rstrip("/"),
            }
        }

    def create(self, declaration: AccessDeclaration, *, plan_id: str) -> OwnershipRecord:
        existing = self.matches(declaration)
        if existing:
            # Adopt rather than duplicate. The plane has no 409 to lean on, so
            # this read is the only thing standing between one assignment and
            # two identical ones.
            return OwnershipRecord(
                assignment_id=existing[0].assignment_id,
                plane=self.plane,
                plan_id=plan_id,
                fingerprint=declaration.fingerprint(),
                principal_id=declaration.principal.object_id,
                scope=declaration.scope,
                role=declaration.role,
                source="adopted",
            )
        account = account_from_scope(declaration.scope)
        # The name is minted here, so the target id is known before the PUT and
        # survives a 202 with no body. It is a cleanup coordinate; ownership is
        # still recorded only from an id the service handed back.
        target_id = f"{account}/sqlRoleAssignments/{self._names()}"
        url = f"{self._endpoint}{target_id}?api-version={self._api}"
        response = self._transport.request(
            "PUT", url, json_body=self.build_create_body(declaration)
        )
        body = resolve_long_running_create(
            self._transport, response,
            target_id=target_id, target_url=url,
            what=f"creating a Cosmos SQL role assignment on {account}",
            max_polls=self._max_polls, sleeper=self._sleeper,
            clock=self._clock,
        )
        return OwnershipRecord(
            assignment_id=created_id(body, "creating a Cosmos SQL role assignment"),
            plane=self.plane,
            plan_id=plan_id,
            fingerprint=declaration.fingerprint(),
            principal_id=declaration.principal.object_id,
            scope=declaration.scope,
            role=declaration.role,
            source="created",
        )

    def duplicates(self, declaration: AccessDeclaration) -> tuple[str, ...]:
        """Every id beyond the first that matches exactly.

        Reported, never removed automatically: on a shared account the extra
        assignment may be another team's, and this plane cannot tell.
        """
        found = self.matches(declaration)
        return tuple(s.assignment_id for s in found[1:])

    def delete(self, assignment_id: str) -> None:
        if "/sqlRoleAssignments/" not in assignment_id:
            raise ProviderConflict(
                f"refusing to delete {sanitize_detail(assignment_id, limit=120)} on "
                f"the Cosmos plane: it is not a sqlRoleAssignments id"
            )
        url = f"{self._endpoint}{assignment_id}?api-version={self._api}"
        require_ok(self._transport.request("DELETE", url),
                   f"deleting {assignment_id}", allowed=(202, 204, 404))


def _state(item: Mapping[str, Any]) -> AssignmentState:
    properties = dict(item.get("properties") or {})
    return AssignmentState(
        assignment_id=str(item.get("id") or ""),
        plane="cosmos-sql-rbac",
        principal_id=str(properties.get("principalId") or ""),
        role_definition_id=str(properties.get("roleDefinitionId") or ""),
        scope=str(properties.get("scope") or ""),
        raw_name=str(item.get("name") or ""),
    )


__all__ = ["COSMOS_SQL_API", "CosmosSqlRbacProvider", "account_from_scope"]
