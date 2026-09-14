"""Exact-scope, reader-grade ARM grants; other data permission planes are explicit exclusions."""

from __future__ import annotations

import asyncio
import re
import uuid
from typing import Any, Callable

import httpx
from pydantic import BaseModel, ConfigDict, field_validator, model_validator

ARM_SCOPE = "https://management.azure.com/.default"
ROLE_API = "2022-04-01"
ROLES = {
    "Cognitive Services OpenAI User": "5e0bd9bd-7b93-4f28-af87-19fc36ad61bd",
    "Search Index Data Reader": "1407120a-92aa-4202-b7e9-c0e197c71c8f",
    "Storage Blob Data Reader": "2a2b9908-6ea1-4ae2-8e65-a410df84e7d1",
}


class GrantError(RuntimeError):
    pass


class Grant(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    role: str
    scope: str

    @field_validator("role")
    @classmethod
    def reader_only(cls, value: str) -> str:
        if value not in ROLES:
            raise ValueError("only the declared ARM data-reader/inference roles are supported")
        return value

    @model_validator(mode="after")
    def exact_scope(self) -> Grant:
        suffixes = {
            "Cognitive Services OpenAI User": r"Microsoft\.CognitiveServices/accounts/[A-Za-z0-9_.-]+",
            "Search Index Data Reader": r"Microsoft\.Search/searchServices/[A-Za-z0-9_.-]+",
            "Storage Blob Data Reader": r"Microsoft\.Storage/storageAccounts/[A-Za-z0-9_.-]+/blobServices/default/containers/[A-Za-z0-9_.-]+",
        }
        pattern = r"/subscriptions/[0-9a-fA-F-]{36}/resourceGroups/[A-Za-z0-9_.()-]+/providers/" + suffixes[self.role]
        if not re.fullmatch(pattern, self.scope, flags=re.IGNORECASE):
            raise ValueError("grant scope must be the exact service or blob container resource id")
        return self


def assignment_matches(body: dict[str, Any], grant: Grant, principal: str) -> bool:
    properties = body.get("properties") or {}
    return (
        str(properties.get("principalId", "")).lower() == principal.lower()
        and str(properties.get("scope", "")).lower() == grant.scope.lower()
        and str(properties.get("roleDefinitionId", "")).lower().endswith("/" + ROLES[grant.role])
    )


class GrantBroker:
    def __init__(self, credential: Any, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.credential = credential
        self.transport = transport

    async def _request(self, method: str, path: str, *, expected: tuple[int, ...], **kwargs: Any) -> httpx.Response:
        issued = await asyncio.to_thread(self.credential.get_token, ARM_SCOPE)
        async with httpx.AsyncClient(transport=self.transport, timeout=60, follow_redirects=False) as client:
            response = await client.request(
                method, "https://management.azure.com" + path, params={"api-version": ROLE_API},
                headers={"Authorization": f"Bearer {issued.token}"}, **kwargs,
            )
        if response.status_code not in expected:
            raise GrantError(f"ARM {method} failed (HTTP {response.status_code})")
        return response

    def assignment(self, grant: Grant, principal: str) -> str:
        uuid.UUID(principal)
        name = uuid.uuid5(uuid.NAMESPACE_URL, f"modular-agents:{principal.lower()}:{grant.scope.lower()}:{ROLES[grant.role]}")
        return f"{grant.scope}/providers/Microsoft.Authorization/roleAssignments/{name}"

    async def ensure(
        self, grant: Grant, principal: str, *, before_write: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        path = self.assignment(grant, principal)
        before = await self._request("GET", path, expected=(200, 404))
        created = before.status_code == 404
        record = {"grant": grant.model_dump(), "assignment_id": path, "created": created}
        if created:
            if before_write is not None:
                before_write(record)
            subscription = grant.scope.split("/")[2]
            await self._request("PUT", path, expected=(200, 201), json={"properties": {
                "principalId": principal, "principalType": "ServicePrincipal",
                "roleDefinitionId": f"/subscriptions/{subscription}/providers/Microsoft.Authorization/roleDefinitions/{ROLES[grant.role]}",
            }})
        observed = await self._request("GET", path, expected=(200,))
        if not assignment_matches(observed.json(), grant, principal):
            raise GrantError("grant read-back does not match the exact principal, scope and role")
        return record

    async def verify(self, grant: Grant, principal: str) -> None:
        observed = await self._request("GET", self.assignment(grant, principal), expected=(200,))
        if not assignment_matches(observed.json(), grant, principal):
            raise GrantError("grant no longer matches its exact scope")

    async def revoke(self, record: dict[str, Any], principal: str) -> None:
        if not record.get("created"):
            return
        grant = Grant.model_validate(record["grant"])
        path = self.assignment(grant, principal)
        if record.get("assignment_id") != path:
            raise GrantError("receipt assignment does not match the recorded grant")
        response = await self._request("GET", path, expected=(200, 404))
        if response.status_code == 404:
            return
        if not assignment_matches(response.json(), grant, principal):
            raise GrantError("refusing to revoke an assignment that changed ownership")
        await self._request("DELETE", path, expected=(200, 202, 204, 404))
        observed = await self._request("GET", path, expected=(200, 404))
        if observed.status_code != 404:
            raise GrantError("revoked assignment remains visible; retry before deleting the identity")