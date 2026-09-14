#!/usr/bin/env python3
"""Serve the explorer's existing read service over MCP with operator-owned scope."""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server
from pydantic import BaseModel, ConfigDict, Field

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "vendor/azdata/src")]

from azdata import AzureDataConfig, resource_group_of, subscription_of
from resource_explorer_api.discovery import build_access
from resource_explorer_api.fixtures import SUBSCRIPTION
from resource_explorer_api.nodes import InvalidNode, decode_node, is_root
from resource_explorer_api.settings import Settings
from resource_explorer_api.tree import ExplorerService, InvalidQuery


class McpSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    fixtures: bool = False
    allow_live_reads: bool = False
    subscription_id: str = Field(default="", max_length=64, pattern=r"^[A-Za-z0-9-]*$")
    resource_group: str = Field(default="", max_length=90)
    max_children: int = Field(default=100, ge=1, le=500)
    max_content_rows: int = Field(default=50, ge=1, le=100)
    max_content_bytes: int = Field(default=262144, ge=1, le=1048576)


class ExplorerTools:
    def __init__(self, config: McpSettings) -> None:
        self.config = config
        if config.allow_live_reads and not config.fixtures and not config.subscription_id:
            raise ValueError("Live reads require a subscription")
        self.subscription_id = SUBSCRIPTION if config.fixtures else config.subscription_id
        settings = Settings(
            azure=AzureDataConfig(subscription_id=self.subscription_id, resource_group=config.resource_group),
            fake_discovery=config.fixtures, max_children=config.max_children,
            max_content_rows=config.max_content_rows, max_content_bytes=config.max_content_bytes,
        )
        self.service = ExplorerService(settings=settings, access=build_access(settings))

    def status(self) -> dict[str, Any]:
        return {
            "configured": bool(self.subscription_id), "fixtures": self.config.fixtures,
            "allow_live_reads": self.config.allow_live_reads, "read_only": True,
            "subscription_id": self.subscription_id, "resource_group": self.config.resource_group,
        }

    def authorize(self, token: str | None = None) -> None:
        if not self.config.fixtures and not self.config.allow_live_reads:
            raise PermissionError("Live reads require allow_live_reads in operator configuration")
        if not self.subscription_id:
            raise PermissionError("No subscription configured")
        if is_root(token):
            return
        reference = decode_node(str(token))
        if reference.service == "estate" and reference.level in {"resource_group", "type"}:
            group = reference.path[0] if reference.path else ""
        else:
            resource_id = reference.path[0] if reference.path else ""
            if subscription_of(resource_id).casefold() != self.subscription_id.casefold():
                raise PermissionError("Node is outside the configured subscription")
            group = resource_group_of(resource_id)
        if self.config.resource_group and group.casefold() != self.config.resource_group.casefold():
            raise PermissionError("Node is outside the configured resource group")


TOOLS = [
    types.Tool(
        name="resource_explorer_status", description="Report explorer scope and grants without contacting Azure.",
        inputSchema={"type": "object", "properties": {}, "additionalProperties": False},
    ),
    types.Tool(
        name="resource_explorer_tree", description="Expand one node in the configured Azure resource tree.",
        inputSchema={"type": "object", "properties": {
            "node": {"type": "string", "minLength": 1, "maxLength": 8192},
        }, "additionalProperties": False},
    ),
    types.Tool(
        name="resource_explorer_content", description="Read a bounded node payload, preserving content kind and degradation status.",
        inputSchema={"type": "object", "properties": {
            "node": {"type": "string", "minLength": 1, "maxLength": 8192},
        }, "required": ["node"], "additionalProperties": False},
    ),
    types.Tool(
        name="resource_explorer_search", description="Search the configured estate and return node IDs usable by the tree.",
        inputSchema={"type": "object", "properties": {
            "query": {"type": "string", "minLength": 1, "maxLength": 200},
            "limit": {"type": "integer", "minimum": 1, "maximum": 200},
        }, "required": ["query"], "additionalProperties": False},
    ),
]


def create_server(application: ExplorerTools, config_path: Path) -> Server:
    server = Server("resource-explorer", version="0.1.0")

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        return TOOLS

    @server.call_tool(validate_input=True)
    async def call_tool(name: str, arguments: dict[str, Any]) -> types.CallToolResult:
        try:
            if name == "resource_explorer_status":
                payload = {**application.status(), "config_file": str(config_path)}
            elif name in {"resource_explorer_tree", "resource_explorer_content"}:
                node = arguments.get("node")
                application.authorize(node)
                response = (await application.service.expand(node) if name == "resource_explorer_tree"
                            else await application.service.read_content(node))
                payload = response.model_dump(mode="json", by_alias=True)
            elif name == "resource_explorer_search":
                application.authorize()
                response = await application.service.search(arguments["query"], arguments.get("limit"))
                for hit in response.hits:
                    application.authorize(hit.node)
                payload = response.model_dump(mode="json", by_alias=True)
            else:
                payload = {"error": "unknown_tool"}
            failed = name not in {tool.name for tool in TOOLS}
        except PermissionError as error:
            payload, failed = {"error": "permission_denied", "detail": str(error)}, True
        except (InvalidNode, InvalidQuery):
            payload, failed = {"error": "invalid_input"}, True
        except Exception:
            payload, failed = {"error": "operation_failed"}, True
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=json.dumps(payload, allow_nan=False))], isError=failed,
        )

    return server


async def serve(application: ExplorerTools, config_path: Path) -> None:
    server = create_server(application, config_path)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--selftest", action="store_true")
    options = parser.parse_args()
    if options.selftest:
        return subprocess.call([sys.executable, "-B", str(ROOT / "tests/mcp_smoke.py")])
    if options.config is None:
        parser.error("--config is required; the plugin client supplies its persistent path")
    try:
        values = json.loads(options.config.read_text()) if options.config.exists() else {}
        application = ExplorerTools(McpSettings.model_validate(values))
    except (OSError, ValueError):
        parser.exit(2, "Invalid MCP configuration; only documented non-secret fields are accepted\n")
    asyncio.run(serve(application, options.config.resolve()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())