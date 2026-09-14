#!/usr/bin/env python3
"""Prove read-only MCP access and authorization before an injected transport is reached."""

import asyncio
import json
import sys
import tempfile
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

SERVER = Path(__file__).resolve().parents[1] / "scripts/mcp_server.py"
TENANT = "11111111-1111-1111-1111-111111111111"
SUBSCRIPTION = "22222222-2222-2222-2222-222222222222"
PRINCIPAL = "33333333-3333-3333-3333-333333333333"
SCOPE = f"/subscriptions/{SUBSCRIPTION}/resourceGroups/fixture"


@asynccontextmanager
async def session(config):
    parameters = StdioServerParameters(command=sys.executable,
        args=["-B", str(SERVER), "--config", str(config), "--fixtures"], cwd=str(config.parent))
    async with stdio_client(parameters) as streams:
        async with ClientSession(*streams, read_timeout_seconds=timedelta(seconds=15)) as client:
            assert (await client.initialize()).serverInfo.name == "azure-access-management"
            yield client


async def check():
    with tempfile.TemporaryDirectory() as directory:
        config = Path(directory) / "config.json"
        async with session(config) as client:
            assert len((await client.list_tools()).tools) == 5
            assert not (await client.call_tool("azaccess_status", {})).isError
            matrix = await client.call_tool("azaccess_matrix", {})
            assert not matrix.isError, matrix
            assert json.loads(matrix.content[0].text)["live_verified"] is False
            role = await client.call_tool("azaccess_role", {"name": "Reader"})
            assert not role.isError, role
            assert json.loads(role.content[0].text)["tier"] == "read"
            scope = await client.call_tool("azaccess_scope", {"scope": SCOPE})
            assert json.loads(scope.content[0].text)["level"] == "resource-group"
            assert (await client.call_tool("azaccess_inspect", {"principal_id": PRINCIPAL, "scope": SCOPE})).isError
        config.write_text(json.dumps({"tenant_id": TENANT, "subscription_id": SUBSCRIPTION,
                                      "scopes": [SCOPE], "allow_live_reads": True}))
        async with session(config) as client:
            for name, arguments in [
                ("azaccess_inspect", {"principal_id": PRINCIPAL, "scope": SCOPE + "-outside"}),
                ("azaccess_inspect", {"principal_id": PRINCIPAL, "scope": SCOPE + "/../outside"}),
                ("azaccess_inspect", {"principal_id": PRINCIPAL, "scope": SCOPE, "write": True}),
                ("azaccess_apply", {}), ("azaccess_revoke", {}),
            ]:
                assert (await client.call_tool(name, arguments)).isError
            status = await client.call_tool("azaccess_status", {})
            assert json.loads(status.content[0].text)["fixture_requests"] == 0
            answer = await client.call_tool("azaccess_inspect", {"principal_id": PRINCIPAL, "scope": SCOPE})
            assert not answer.isError, answer
            payload = json.loads(answer.content[0].text)
            assert payload["fixtures"] and payload["completeness"] == "partial"
            assert not (await client.call_tool("azaccess_status", {})).isError
    print("MCP selftest: PASS (access metadata, explicit reads, scope refusals before transport, no mutation tools)")


if __name__ == "__main__":
    asyncio.run(check())