#!/usr/bin/env python3
"""Round-trip the actual stdio server with denied and explicitly granted fixture clients."""

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

SERVER = Path(__file__).resolve().parents[1] / "scripts/mcp_server.py"


@asynccontextmanager
async def session(config: Path):
    parameters = StdioServerParameters(
        command=sys.executable, args=["-B", str(SERVER), "--config", str(config), "--fixtures"],
        cwd=str(config.parent),
    )
    async with stdio_client(parameters) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream, read_timeout_seconds=timedelta(seconds=15)) as client:
            initialized = await client.initialize()
            assert initialized.serverInfo.name == "azure-llm-connectors"
            yield client


async def check() -> None:
    with tempfile.TemporaryDirectory() as directory:
        config = Path(directory) / "config.json"
        async with session(config) as client:
            assert {tool.name for tool in (await client.list_tools()).tools} == {
                "azllm_status", "azllm_ask", "azllm_embed",
            }
            status = await client.call_tool("azllm_status", {})
            assert not status.isError
            assert json.loads(status.content[0].text)["configured"] is False
            refused = await client.call_tool("azllm_ask", {"prompt": "fixture"})
            assert refused.isError
            assert json.loads(refused.content[0].text)["error"] == "permission_denied"

        config.write_text(json.dumps({
            "endpoint": "https://model.example.invalid", "deployment": "chat",
            "embedding_deployment": "text-embedding-3-small", "allow_model_calls": True,
            "max_calls": 2, "max_output_tokens": 32,
        }))
        async with session(config) as client:
            for name, arguments in [
                ("azllm_ask", {}),
                ("azllm_ask", {"prompt": "fixture", "endpoint": "https://other.example.invalid"}),
                ("azllm_ask", {"prompt": "fixture", "max_output_tokens": 64}),
                ("azllm_embed", {"texts": []}),
                ("not_a_tool", {}),
            ]:
                assert (await client.call_tool(name, arguments)).isError
            answer = await client.call_tool("azllm_ask", {"prompt": "fixture"})
            assert not answer.isError, answer
            payload = json.loads(answer.content[0].text)
            assert payload["fixtures"] and payload["text"] == "hello"
            embedded = await client.call_tool("azllm_embed", {"texts": ["one", "two"], "dimensions": 3})
            assert not embedded.isError, embedded
            assert len(json.loads(embedded.content[0].text)["vectors"]) == 2
            assert (await client.call_tool("azllm_ask", {"prompt": "over budget"})).isError
            assert not (await client.call_tool("azllm_status", {})).isError

        config.write_text(json.dumps({"api_key": "fixture-value"}))
        rejected = subprocess.run(
            [sys.executable, "-B", str(SERVER), "--config", str(config)],
            capture_output=True, text=True, timeout=15,
        )
        assert rejected.returncode == 2
        assert "fixture-value" not in rejected.stderr
    print("MCP selftest: PASS (LLM grants, bounded fixture chat/embeddings, schema refusals, budget, recovery)")


if __name__ == "__main__":
    asyncio.run(check())