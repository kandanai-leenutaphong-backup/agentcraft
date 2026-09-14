#!/usr/bin/env python3
"""Offline access reference and explicitly granted read-only ARM inspection over MCP."""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any
from uuid import UUID

from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server
from pydantic import BaseModel, ConfigDict, Field

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from azaccess import (
    AccessError, AccessManager, ArmRbacProvider, AzureCliTransport, RecordingTransport,
    Response, Scope, bounded_policy, cloud_by_name, lookup_role, support_matrix,
)


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    tenant_id: str = ""
    subscription_id: str = ""
    scopes: list[str] = Field(default_factory=list, max_length=32)
    cloud: str = "AzureCloud"
    allow_live_reads: bool = False
    timeout_secs: float = Field(default=30.0, gt=0, le=120, allow_inf_nan=False)


class AccessTools:
    def __init__(self, settings: Settings, *, fixtures: bool = False) -> None:
        self.settings = settings
        self.fixtures = fixtures
        self.manager = None
        self.transport = None
        cloud = cloud_by_name(settings.cloud)
        if settings.tenant_id or settings.subscription_id or settings.scopes or settings.allow_live_reads:
            UUID(settings.tenant_id)
            UUID(settings.subscription_id)
            if not settings.scopes:
                raise ValueError("At least one configured scope is required")
            for value in settings.scopes:
                if Scope.parse(value).subscription_id.lower() != settings.subscription_id.lower():
                    raise ValueError("Scope is outside the configured subscription")
            self.transport = (RecordingTransport(responses={
                ("GET", "roleAssignments"): [Response(200, {"value": []})],
            }) if fixtures else AzureCliTransport(cloud=cloud, timeout_secs=settings.timeout_secs))
            self.manager = AccessManager(
                {"azure-rbac": ArmRbacProvider(self.transport, subscription_id=settings.subscription_id)},
                policy=bounded_policy(tenant_id=settings.tenant_id, scopes=settings.scopes, max_tier="read"),
            )

    def status(self) -> dict[str, Any]:
        return {"configured": self.manager is not None, "fixtures": self.fixtures,
                "allow_live_reads": self.settings.allow_live_reads, "mutations_exposed": False,
                "inspection_plane": "azure-rbac",
                "fixture_requests": len(self.transport.calls) if self.fixtures and self.transport else None}

    def inspect(self, principal_id: str, scope: str) -> dict[str, Any]:
        if not self.settings.allow_live_reads or self.manager is None:
            raise PermissionError("Inspection requires operator-configured tenant, subscription, scopes and read grant")
        UUID(principal_id)
        Scope.parse(scope)
        self.manager.policy.authorize_read(scope, what="MCP inspect")
        if not self.fixtures:
            account = subprocess.run(
                ["az", "account", "show", "--subscription", self.settings.subscription_id,
                 "--query", "{tenantId:tenantId, id:id}", "--output", "json"],
                capture_output=True, text=True, timeout=self.settings.timeout_secs, check=False,
            )
            if account.returncode:
                raise PermissionError("Azure CLI cannot read the configured subscription; sign in to the configured tenant")
            coordinates = json.loads(account.stdout)
            if (str(coordinates.get("tenantId", "")).lower() != self.settings.tenant_id.lower()
                    or str(coordinates.get("id", "")).lower() != self.settings.subscription_id.lower()):
                raise PermissionError("Azure CLI identity does not match the configured tenant and subscription")
        result = self.manager.inspect(principal_id, scope).to_dict()
        return {**result, "fixtures": self.fixtures}


TOOLS = [
    types.Tool(name="azaccess_status", description="Report configured inspection scope and grants without contacting Azure.",
               inputSchema={"type": "object", "properties": {}, "additionalProperties": False}),
    types.Tool(name="azaccess_matrix", description="Read the library's five-plane support matrix and evidence limits, offline.",
               inputSchema={"type": "object", "properties": {}, "additionalProperties": False}),
    types.Tool(name="azaccess_role", description="Look up a public built-in role and its privilege tier without contacting Azure.",
               inputSchema={"type": "object", "properties": {"name": {"type": "string", "minLength": 1, "maxLength": 200}},
                   "required": ["name"], "additionalProperties": False}),
    types.Tool(name="azaccess_scope", description="Parse an ARM scope locally. Parsing does not establish authorization.",
               inputSchema={"type": "object", "properties": {"scope": {"type": "string", "minLength": 1, "maxLength": 2048}},
                   "required": ["scope"], "additionalProperties": False}),
    types.Tool(name="azaccess_inspect", description="Inspect exact and inherited ARM assignments within an operator-approved scope. Effective access remains partial.",
               inputSchema={"type": "object", "properties": {
                   "principal_id": {"type": "string", "minLength": 36, "maxLength": 36},
                   "scope": {"type": "string", "minLength": 1, "maxLength": 2048}},
                   "required": ["principal_id", "scope"], "additionalProperties": False}),
]


async def serve(application: AccessTools, config: Path) -> None:
    server = Server("azure-access-management", version="1.1.0")

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        return TOOLS

    @server.call_tool(validate_input=True)
    async def call_tool(name: str, arguments: dict[str, Any]) -> types.CallToolResult:
        try:
            if name == "azaccess_status":
                payload = {**application.status(), "config_file": str(config)}
            elif name == "azaccess_matrix":
                payload = {"planes": [asdict(row) for row in support_matrix()], "live_verified": False}
            elif name == "azaccess_role":
                payload = asdict(lookup_role(arguments["name"]))
            elif name == "azaccess_scope":
                payload = asdict(Scope.parse(arguments["scope"]))
            elif name == "azaccess_inspect":
                payload = await asyncio.to_thread(application.inspect, **arguments)
            else:
                payload = {"error": "unknown_tool"}
        except PermissionError as error:
            payload = {"error": "permission_denied", "detail": str(error)}
        except AccessError as error:
            payload = {"error": type(error).__name__}
        except Exception:
            payload = {"error": "operation_failed"}
        return types.CallToolResult(content=[types.TextContent(type="text", text=json.dumps(payload))],
                                    isError=bool(payload.get("error")))

    async with stdio_server() as streams:
        await server.run(*streams, server.create_initialization_options())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--fixtures", action="store_true")
    parser.add_argument("--selftest", action="store_true")
    options = parser.parse_args()
    if options.selftest:
        return subprocess.call([sys.executable, "-B", str(ROOT / "tests/mcp_smoke.py")])
    if options.config is None:
        parser.error("--config is required")
    try:
        values = json.loads(options.config.read_text()) if options.config.exists() else {}
        application = AccessTools(Settings.model_validate(values), fixtures=options.fixtures)
    except (OSError, ValueError, AccessError):
        parser.exit(2, "Invalid access MCP configuration; use documented non-secret fields\n")
    asyncio.run(serve(application, options.config.resolve()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())