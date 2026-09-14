#!/usr/bin/env python3
"""Real stdio round trips with fake model clients and explicit negative cases."""

import asyncio
import json
import subprocess
import sys
import tempfile
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

SERVER = Path(__file__).resolve().parents[1] / "scripts/mcp_server.py"
sys.path.insert(0, str(SERVER.parent))
import mcp_server as adapter


@asynccontextmanager
async def session(config):
    parameters = StdioServerParameters(command=sys.executable,
        args=["-B", str(SERVER), "--config", str(config), "--fixtures"], cwd=str(config.parent))
    async with stdio_client(parameters) as streams:
        async with ClientSession(*streams, read_timeout_seconds=timedelta(seconds=15)) as client:
            assert (await client.initialize()).serverInfo.name == "managed-identity-model-clients"
            yield client


async def check():
    application = adapter.ModelTools(adapter.Settings(
        endpoint="https://same.example.invalid", deployment="chat", embedding_deployment="embedding",
    ))
    with patch.object(adapter, "connect_async", side_effect=lambda config: object()):
        embedded = application.client(adapter.embedding_config(application.config))
        chat = application.client(application.config)
        assert chat is not embedded
        assert application.client(application.config) is chat
    with tempfile.TemporaryDirectory() as directory:
        config = Path(directory) / "config.json"
        async with session(config) as client:
            assert len((await client.list_tools()).tools) == 3
            assert not (await client.call_tool("modelaccess_status", {})).isError
            assert (await client.call_tool("modelaccess_ask", {"prompt": "fixture"})).isError
        config.write_text(json.dumps({
            "endpoint": "https://chat.example.invalid", "deployment": "chat",
            "embedding_endpoint": "https://embed.example.invalid", "embedding_deployment": "embedding",
            "allowed_hosts": ["chat.example.invalid", "embed.example.invalid"],
            "allow_model_calls": True, "max_calls": 2, "max_output_tokens": 32,
        }))
        async with session(config) as client:
            for arguments in [{}, {"prompt": "fixture", "allow_model_calls": True},
                              {"prompt": "fixture", "max_output_tokens": 64}]:
                assert (await client.call_tool("modelaccess_ask", arguments)).isError
            answer = await client.call_tool("modelaccess_ask", {"prompt": "fixture"})
            assert not answer.isError, answer
            assert json.loads(answer.content[0].text)["text"] == "fixture answer"
            result = await client.call_tool("modelaccess_embed", {"texts": ["one", "two"], "dimensions": 3})
            assert not result.isError, result
            assert len(json.loads(result.content[0].text)["vectors"]) == 2
            assert (await client.call_tool("modelaccess_ask", {"prompt": "exhausted"})).isError
            assert (await client.call_tool("unknown", {})).isError
            assert not (await client.call_tool("modelaccess_status", {})).isError
        for values in [{"api_key": "not-a-secret-fixture"},
                       {"endpoint": "https://outside.example.invalid", "deployment": "chat",
                        "allowed_hosts": ["allowed.example.invalid"]}]:
            config.write_text(json.dumps(values))
            process = subprocess.run([sys.executable, "-B", str(SERVER), "--config", str(config)],
                                     capture_output=True, text=True, timeout=15)
            assert process.returncode == 2 and "not-a-secret-fixture" not in process.stderr
    print("MCP selftest: PASS (modelaccess grants, chat, cross-account embeddings, budgets, refusals)")


if __name__ == "__main__":
    asyncio.run(check())