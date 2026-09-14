#!/usr/bin/env python3
"""Exercise fixture reads and scope refusals through the actual MCP process."""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import tempfile
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "vendor/azdata/src")]
from resource_explorer_api.nodes import NodeRef, encode_node

SERVER = ROOT / "scripts/mcp_server.py"


@asynccontextmanager
async def session(config: Path):
    parameters = StdioServerParameters(
        command=sys.executable, args=["-B", str(SERVER), "--config", str(config)], cwd=str(config.parent),
    )
    async with stdio_client(parameters) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream, read_timeout_seconds=timedelta(seconds=15)) as client:
            initialized = await client.initialize()
            assert initialized.serverInfo.name == "resource-explorer"
            yield client


async def check() -> None:
    with tempfile.TemporaryDirectory() as directory:
        config = Path(directory) / "config.json"
        async with session(config) as client:
            assert {tool.name for tool in (await client.list_tools()).tools} == {
                "resource_explorer_status", "resource_explorer_tree",
                "resource_explorer_content", "resource_explorer_search",
            }
            assert not (await client.call_tool("resource_explorer_status", {})).isError
            assert (await client.call_tool("resource_explorer_tree", {})).isError

        config.write_text(json.dumps({"fixtures": True}))
        async with session(config) as client:
            root = await client.call_tool("resource_explorer_tree", {})
            assert not root.isError, root
            assert json.loads(root.content[0].text)["fixtures"]
            search = await client.call_tool("resource_explorer_search", {"query": "fixture", "limit": 3})
            assert not search.isError, search
            hits = json.loads(search.content[0].text)["hits"]
            assert hits and len(hits) <= 3
            resource = next(hit for hit in hits if hit["kind"] == "resource")
            expanded = await client.call_tool("resource_explorer_tree", {"node": resource["node"]})
            assert not expanded.isError, expanded
            children = json.loads(expanded.content[0].text)["children"]
            properties = next(child for child in children if child["kind"] == "properties")
            content = await client.call_tool("resource_explorer_content", {"node": properties["id"]})
            assert not content.isError, content
            payload = json.loads(content.content[0].text)
            assert payload["fixtures"] and payload["contentKind"] == "json"
            escaped = encode_node(NodeRef(
                "estate", "properties",
                ("/subscriptions/other-subscription/resourceGroups/other/providers/Microsoft.Storage/storageAccounts/other",),
                "properties",
            ))
            for name, arguments in [
                ("resource_explorer_tree", {"node": "invalid-node"}),
                ("resource_explorer_content", {"node": escaped}),
                ("resource_explorer_tree", {"subscription_id": "other"}),
                ("resource_explorer_search", {"query": ""}),
                ("unknown_tool", {}),
            ]:
                assert (await client.call_tool(name, arguments)).isError
            assert not (await client.call_tool("resource_explorer_status", {})).isError

        config.write_text(json.dumps({"fixtures": True, "resource_group": "rg-empty"}))
        async with session(config) as client:
            escaped = encode_node(NodeRef("estate", "resource_group", ("rg-other",), "resource_group"))
            refusal = await client.call_tool("resource_explorer_tree", {"node": escaped})
            assert refusal.isError
            assert json.loads(refusal.content[0].text)["error"] == "permission_denied"

        config.write_text(json.dumps({"client_secret": "fixture-value"}))
        rejected = subprocess.run(
            [sys.executable, "-B", str(SERVER), "--config", str(config)],
            capture_output=True, text=True, timeout=15,
        )
        assert rejected.returncode == 2 and "fixture-value" not in rejected.stderr
    print("MCP selftest: PASS (explorer tree/content/search, input refusals, subscription/group scope, recovery)")


if __name__ == "__main__":
    asyncio.run(check())