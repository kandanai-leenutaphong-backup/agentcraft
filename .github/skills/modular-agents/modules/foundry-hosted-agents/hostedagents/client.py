"""Foundry hosted-agent data plane adapted from hcagent.foundry."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

FOUNDRY_SCOPE = "https://ai.azure.com/.default"
API_VERSION = "v1"


class FoundryError(RuntimeError):
    def __init__(self, operation: str, *, status: int = 0) -> None:
        super().__init__(f"{operation} failed" + (f" (HTTP {status})" if status else ""))
        self.status = status


def identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", value):
        raise ValueError("invalid Foundry agent or version identifier")
    return value


def project_endpoint(value: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https" or parsed.username or parsed.password
        or parsed.port not in (None, 443) or parsed.query or parsed.fragment
        or not re.fullmatch(r"[a-z0-9-]+\.services\.ai\.azure\.com", parsed.hostname or "")
        or not re.fullmatch(r"/api/projects/[A-Za-z0-9][A-Za-z0-9_-]{0,63}/?", parsed.path)
    ):
        raise ValueError("expected an Azure public-cloud Foundry project HTTPS endpoint")
    return value.rstrip("/")


def session_key(principal: str, agent: str, *, purpose: str = "consumer") -> str:
    if not principal or not purpose:
        raise ValueError("principal and session purpose are required")
    digest = hashlib.sha256(json.dumps([purpose, principal, agent]).encode()).hexdigest()
    return ("mac" if purpose == "consumer" else "mao") + digest[:48]


def current_version(agent: dict[str, Any]) -> str:
    latest = (agent.get("versions") or {}).get("latest") or {}
    return str(latest.get("version") or agent.get("version") or "")


def instance_principal_id(agent: dict[str, Any]) -> str:
    latest = (agent.get("versions") or {}).get("latest") or {}
    identity = agent.get("instance_identity") or latest.get("instance_identity") or {}
    return str(identity.get("principal_id") or "")


class FoundryClient:
    """Credential and transport are caller-owned; response bodies never enter errors."""

    def __init__(self, endpoint: str, credential: Any, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.endpoint = project_endpoint(endpoint)
        self.credential = credential
        self.transport = transport
        self._cached_token: tuple[str, float] = ("", 0)
        self._token_lock = asyncio.Lock()

    async def _headers(self) -> dict[str, str]:
        async with self._token_lock:
            value, expires = self._cached_token
            if not value or expires - 300 <= time.time():
                issued = await asyncio.to_thread(self.credential.get_token, FOUNDRY_SCOPE)
                value = issued.token
                self._cached_token = (value, float(issued.expires_on))
            return {"Authorization": f"Bearer {value}"}

    async def _request(
        self, method: str, path: str, *, expected: tuple[int, ...],
        params: dict[str, str] | None = None, timeout: float = 120, **kwargs: Any,
    ) -> httpx.Response:
        headers = await self._headers()
        headers.update(kwargs.pop("headers", {}))
        async with httpx.AsyncClient(transport=self.transport, follow_redirects=False, timeout=timeout) as client:
            response = await client.request(
                method, self.endpoint + path, params={"api-version": API_VERSION, **(params or {})},
                headers=headers, **kwargs,
            )
        if response.status_code not in expected:
            raise FoundryError(f"Foundry {method}", status=response.status_code)
        return response

    async def get_agent(self, name: str) -> dict[str, Any] | None:
        response = await self._request("GET", f"/agents/{identifier(name)}", expected=(200, 404))
        return None if response.status_code == 404 else response.json()

    async def version_status(self, name: str, version: str) -> dict[str, Any]:
        response = await self._request(
            "GET", f"/agents/{identifier(name)}/versions/{identifier(version)}", expected=(200,),
        )
        return response.json()

    async def upload(
        self, *, name: str, metadata: dict[str, Any], zip_path: Path, sha256: str, update: bool = False,
    ) -> dict[str, Any]:
        identifier(name)
        payload = zip_path.read_bytes()
        if hashlib.sha256(payload).hexdigest() != sha256:
            raise FoundryError("artifact digest verification")
        headers = {"x-ms-code-zip-sha256": sha256}
        if not update:
            headers["x-ms-agent-name"] = name
        response = await self._request(
            "POST", f"/agents/{name}" if update else "/agents", expected=(200, 201), timeout=300,
            headers=headers,
            files={
                "metadata": ("metadata.json", json.dumps(metadata).encode(), "application/json"),
                "code": (f"{name}.zip", payload, "application/zip"),
            },
        )
        return response.json()

    async def invoke(self, name: str, session: str, body: dict[str, Any], *, timeout: float = 120) -> tuple[int, Any]:
        if not re.fullmatch(r"[A-Za-z0-9_-]{8,64}", session):
            raise ValueError("invalid session identifier")
        response = await self._request(
            "POST", f"/agents/{identifier(name)}/endpoint/protocols/invocations",
            expected=(200, 400, 401, 403, 404, 409, 424, 429, 500, 502, 503, 504),
            params={"agent_session_id": session}, json=body, timeout=timeout,
        )
        try:
            return response.status_code, response.json()
        except ValueError:
            return response.status_code, {"error": "non-JSON invocation response"}

    async def warm(self, name: str, session: str, *, budget: float = 240, interval: float = 8) -> dict[str, Any]:
        deadline = time.monotonic() + budget
        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            status, result = await self.invoke(name, session, {"op": "health"}, timeout=min(60, max(0.1, remaining)))
            if status == 200 and isinstance(result, dict) and result.get("ok"):
                return result
            if status not in (409, 424, 429, 502, 503, 504):
                raise FoundryError("warming hosted agent", status=status)
            await asyncio.sleep(min(interval, max(0, deadline - time.monotonic())))
        raise FoundryError("warm deadline")

    async def delete_agent(self, name: str) -> None:
        await self._request("DELETE", f"/agents/{identifier(name)}", expected=(200, 202, 204, 404), params={"force": "true"})