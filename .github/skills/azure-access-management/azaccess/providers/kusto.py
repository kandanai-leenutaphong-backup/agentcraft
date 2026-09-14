"""Azure Data Explorer database principal assignments — the third plane.

Like Cosmos, and unlike Azure RBAC: a Kusto database principal assignment is a
child of the database, invisible to ``Microsoft.Authorization`` listings, and
removed only through its own API. Unlike Cosmos, the assignment *name* is
chosen by the caller and a repeat PUT with the same name is an update, so
idempotency is available if — and only if — the name is derived from something
stable. This adapter does not do that: it reads first, adopts what it finds,
and records the id the service returned, because a name-derived identity is
exactly the "infer ownership from a deterministic id" mistake that makes a
teardown delete an assignment it never made.

ROLES ARE WORDS, NOT GUIDS
--------------------------
``Viewer``, ``Ingestor``, ``Admin``, ``Monitor``, ``User``, ``UnrestrictedViewer``.
The catalogue carries them as definition ids so one vocabulary covers all
planes; nothing here parses a GUID. Because they are words, role identity is
compared **exactly** — a suffix test made a declared ``Viewer`` satisfied by a
live ``UnrestrictedViewer``, which is a strictly wider grant.

CREATE IS LONG-RUNNING
----------------------
``PUT …/principalAssignments/{name}`` answers ``202 Accepted`` with an
``Azure-AsyncOperation`` header and no body while the cluster applies it.
Handled by :func:`~azaccess.providers.base.resolve_long_running_create` for the
same reason as Cosmos: an accepted create whose id was never read back is an
assignment this run cannot revoke.

Reference: Azure Data Explorer "Database Principal Assignments - Create Or
Update" and the ARM "Asynchronous operations" contract.
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
from azaccess.transport import Transport

KUSTO_API = "2023-08-15"

#: Kusto's own principal-type vocabulary, which is not ARM's.
PRINCIPAL_TYPES: dict[str, str] = {
    "managed-identity": "App",
    "service-principal": "App",
    "user": "User",
    "group": "Group",
}


class KustoDatabaseProvider:
    """Database-scoped principal assignments on an Azure Data Explorer cluster."""

    plane = "kusto-database"

    operations: Mapping[str, str] = {
        "list-database-assignments": "implemented",
        "create-assignment": "implemented",
        "delete-assignment": "implemented",
        "cluster-scoped-assignment": "documented",
        "drop-table-or-database": "unsupported",
    }

    def __init__(
        self,
        transport: Transport,
        *,
        endpoint: str = ARM_ENDPOINT,
        api_version: str = KUSTO_API,
        name_factory: Callable[[], str] | None = None,
        max_polls: int = 30,
        sleeper: Callable[[float], None] | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._transport = transport
        self._endpoint = endpoint.rstrip("/")
        self._api = api_version
        self._names = name_factory or (lambda: f"pa{uuid.uuid4().hex[:16]}")
        self._max_polls = max_polls
        self._sleeper = sleeper
        self._clock = clock

    def _list_url(self, scope: str) -> str:
        return (
            f"{self._endpoint}{scope.rstrip('/')}/principalAssignments"
            f"?api-version={self._api}"
        )

    def list_for(self, declaration: AccessDeclaration) -> tuple[AssignmentState, ...]:
        scope = _database_scope(declaration.scope)
        items = page_values(
            self._transport, self._list_url(scope),
            f"listing Kusto principal assignments at {scope}",
        )
        return tuple(_state(item, scope) for item in items)

    def matches(self, declaration: AccessDeclaration) -> tuple[AssignmentState, ...]:
        return tuple(s for s in self.list_for(declaration) if s.matches(declaration))

    def build_create_body(self, declaration: AccessDeclaration) -> dict[str, Any]:
        kind = declaration.principal.kind
        try:
            principal_type = PRINCIPAL_TYPES[kind]
        except KeyError:
            raise CoordinateError(
                f"Kusto has no principal type for identity kind '{kind}'"
            ) from None
        return {
            "properties": {
                "principalId": declaration.principal.object_id,
                "role": declaration.role_definition.definition_id,
                "principalType": principal_type,
                "tenantId": declaration.principal.tenant_id,
            }
        }

    def create(self, declaration: AccessDeclaration, *, plan_id: str) -> OwnershipRecord:
        existing = self.matches(declaration)
        if existing:
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
        scope = _database_scope(declaration.scope)
        target_id = f"{scope}/principalAssignments/{self._names()}"
        url = f"{self._endpoint}{target_id}?api-version={self._api}"
        response = self._transport.request(
            "PUT", url, json_body=self.build_create_body(declaration)
        )
        body = resolve_long_running_create(
            self._transport, response,
            target_id=target_id, target_url=url,
            what=f"creating a principal assignment at {scope}",
            max_polls=self._max_polls, sleeper=self._sleeper,
            clock=self._clock,
        )
        return OwnershipRecord(
            assignment_id=created_id(body, "creating a Kusto principal assignment"),
            plane=self.plane,
            plan_id=plan_id,
            fingerprint=declaration.fingerprint(),
            principal_id=declaration.principal.object_id,
            scope=declaration.scope,
            role=declaration.role,
            source="created",
        )

    def delete(self, assignment_id: str) -> None:
        if "/principalAssignments/" not in assignment_id:
            raise ProviderConflict(
                "refusing to delete an id that is not a Kusto principal assignment"
            )
        url = f"{self._endpoint}{assignment_id}?api-version={self._api}"
        require_ok(self._transport.request("DELETE", url),
                   f"deleting {assignment_id}", allowed=(202, 204, 404))


def _database_scope(scope: str) -> str:
    text = str(scope or "").rstrip("/")
    if "/databases/" not in text.lower():
        raise CoordinateError(
            f"a Kusto grant is made at database scope; got {text[:80]!r}"
        )
    return text


def _state(item: Mapping[str, Any], scope: str) -> AssignmentState:
    properties = dict(item.get("properties") or {})
    return AssignmentState(
        assignment_id=str(item.get("id") or ""),
        plane="kusto-database",
        principal_id=str(properties.get("principalId") or ""),
        role_definition_id=str(properties.get("role") or ""),
        scope=scope,
        principal_type=str(properties.get("principalType") or ""),
        raw_name=str(item.get("name") or ""),
    )


__all__ = ["KUSTO_API", "KustoDatabaseProvider", "PRINCIPAL_TYPES"]
