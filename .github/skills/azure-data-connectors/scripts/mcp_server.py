#!/usr/bin/env python3
"""Serve the azdata read plane through the official MCP SDK and explicit configuration."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import tempfile
from datetime import timedelta
from pathlib import Path
from typing import Any

from mcp import ClientSession, types
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_ROOT / "src"))

from azdata import AzureDataConfig, connect

SERVER_INFO = {"name": "azure-data-connectors", "version": "3.4.0"}

_TEXT_FIELDS = ("chunk", "content", "text", "body")
CONFIG_KEYS = {
    "AZDATA_GREMLIN_ENDPOINT", "AZDATA_GREMLIN_DATABASE", "AZDATA_GREMLIN_GRAPH",
    "AZDATA_KQL_QUERY_URI", "AZDATA_KQL_DATABASE", "AZDATA_SEARCH_ENDPOINT",
    "AZDATA_FABRIC_API_URL", "AZDATA_FABRIC_WORKSPACE_ID", "AZDATA_FABRIC_GRAPH_MODEL_ID",
    "AZDATA_FABRIC_SCOPE", "AZDATA_MAX_CONCURRENT", "AZDATA_MAX_ROWS",
}


def _log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


# ---------------------------------------------------------------------------
# Wiring. Deferred so the process starts and answers tools/list even when no
# AZDATA_* variable is set — an agent should be told what is unconfigured,
# not handed a stack trace at startup.
# ---------------------------------------------------------------------------

_state: dict[str, Any] = {
    "config": AzureDataConfig(), "config_path": None, "connectors": None, "error": None,
}


def load_config(path: Path) -> AzureDataConfig:
    values = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if not isinstance(values, dict) or not set(values) <= CONFIG_KEYS:
        raise ValueError("MCP config must contain only supported non-secret AZDATA_* settings")
    if not all(isinstance(value, str) for value in values.values()):
        raise ValueError("MCP config values must be strings")
    return AzureDataConfig.from_env(env=values)


def _wire() -> tuple[Any, Any] | None:
    if _state["connectors"] is not None or _state["error"] is not None:
        return (
            (_state["config"], _state["connectors"])
            if _state["error"] is None
            else None
        )
    try:
        config = _state["config"]
        _state["connectors"] = connect(config)
    except Exception as exc:  # noqa: BLE001 - reported to the caller as data
        _state["error"] = f"{type(exc).__name__}: {exc}"
        return None
    return _state["config"], _state["connectors"]


def _unavailable(detail: str) -> str:
    return json.dumps({"error": True, "detail": detail})


# ---------------------------------------------------------------------------
# Tools. Every one returns a JSON string; a failure is a return value.
# ---------------------------------------------------------------------------


async def tool_status(_: dict[str, Any]) -> str:
    wired = _wire()
    if wired is None:
        return json.dumps(
            {"wired": False, "detail": _state["error"], "configured": {}}
        )
    config, connectors = wired
    return json.dumps(
        {
            "wired": True,
            "configured": connectors.configured(),
            "planes_served": ["read"],
            "planes_withheld": ["write", "deploy"],
            "location": getattr(config, "location", None),
            "config_file": str(_state["config_path"]) if _state["config_path"] else None,
        }
    )


async def tool_query_kql(args: dict[str, Any]) -> str:
    wired = _wire()
    if wired is None:
        return _unavailable(_state["error"] or "not wired")
    _, connectors = wired

    def project(shaped: dict) -> dict:
        return {
            "fields": [column["name"] for column in shaped["columns"]],
            "records": shaped["rows"],
            "record_count": len(shaped["rows"]),
        }

    return await connectors.kql.execute(args["query"], project=project)


async def tool_query_gremlin(args: dict[str, Any]) -> str:
    wired = _wire()
    if wired is None:
        return _unavailable(_state["error"] or "not wired")
    _, connectors = wired
    return await connectors.gremlin.execute(args["query"])


async def tool_query_graph(args: dict[str, Any]) -> str:
    wired = _wire()
    if wired is None:
        return _unavailable(_state["error"] or "not wired")
    _, connectors = wired
    result = await connectors.graph.execute(args["query"])
    if result.get("error"):
        return json.dumps(result)
    return json.dumps({"rows": result["data"], "row_count": len(result["data"])})


async def tool_search(args: dict[str, Any]) -> str:
    wired = _wire()
    if wired is None:
        return _unavailable(_state["error"] or "not wired")
    _, connectors = wired

    def project_doc(doc: dict) -> dict:
        text = next((str(doc[f]) for f in _TEXT_FIELDS if doc.get(f)), "")
        return {
            "title": doc.get("title") or doc.get("filename") or "untitled",
            "text": text[:2000],
            "score": round(float(doc.get("@search.score", 0.0)), 3),
        }

    # The SDK is synchronous; keep it off the event loop.
    return await asyncio.to_thread(
        connectors.search.execute,
        args["question"],
        index_name=args["index_name"],
        semantic_config=args.get("semantic_config"),
        project_doc=project_doc,
        top_k=args.get("top_k", 5),
    )


TOOLS: list[dict[str, Any]] = [
    {
        "name": "azdata_status",
        "description": (
            "Report which Azure data services this process can reach and which "
            "planes are served. Performs no I/O and contacts nothing. Use first "
            "to find out what is configured before issuing a query."
        ),
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "handler": tool_status,
    },
    {
        "name": "azdata_query_kql",
        "description": (
            "Run a KQL query against Fabric Eventhouse or Azure Data Explorer. "
            "Read-only: a row cap is injected and the query is bounded."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "KQL query text."}},
            "required": ["query"],
            "additionalProperties": False,
        },
        "handler": tool_query_kql,
    },
    {
        "name": "azdata_query_gremlin",
        "description": (
            "Run a Gremlin traversal against Cosmos DB Gremlin. Mutating steps "
            "are refused and a limit is injected."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Gremlin traversal."}},
            "required": ["query"],
            "additionalProperties": False,
        },
        "handler": tool_query_gremlin,
    },
    {
        "name": "azdata_query_graph",
        "description": "Run a GQL query against a Fabric GraphModel over HTTPS.",
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "GQL query text."}},
            "required": ["query"],
            "additionalProperties": False,
        },
        "handler": tool_query_graph,
    },
    {
        "name": "azdata_search",
        "description": (
            "Retrieve documents from an Azure AI Search index, projected to "
            "title, text and score."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "question": {"type": "string"},
                "index_name": {"type": "string"},
                "semantic_config": {"type": "string"},
                "top_k": {"type": "integer", "minimum": 1, "maximum": 50},
            },
            "required": ["question", "index_name"],
            "additionalProperties": False,
        },
        "handler": tool_search,
    },
]

_BY_NAME = {tool["name"]: tool for tool in TOOLS}
server = Server(SERVER_INFO["name"], version=SERVER_INFO["version"])


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(**{key: value for key, value in tool.items() if key != "handler"})
        for tool in TOOLS
    ]


@server.call_tool(validate_input=True)
async def call_tool(name: str, arguments: dict[str, Any]) -> types.CallToolResult:
    tool = _BY_NAME.get(name)
    if tool is None:
        return types.CallToolResult(
            content=[types.TextContent(type="text", text="Unknown tool")], isError=True,
        )
    payload = await tool["handler"](arguments)
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=payload)],
        isError=bool(json.loads(payload).get("error")),
    )


async def serve() -> None:
    try:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())
    finally:
        if _state["connectors"] is not None:
            await _state["connectors"].aclose()


def _selftest() -> int:
    async def run() -> int:
        with tempfile.TemporaryDirectory() as directory:
            parameters = StdioServerParameters(
                command=sys.executable,
                args=["-B", str(Path(__file__).resolve()), "--config", str(Path(directory) / "config.json")],
                cwd=directory,
            )
            async with stdio_client(parameters) as (read_stream, write_stream):
                async with ClientSession(
                    read_stream, write_stream, read_timeout_seconds=timedelta(seconds=15),
                ) as session:
                    init = await session.initialize()
                    assert init.serverInfo.name == SERVER_INFO["name"]
                    listed = await session.list_tools()
                    assert {tool.name for tool in listed.tools} == set(_BY_NAME)
                    called = await session.call_tool("azdata_status", {})
                    assert not called.isError
                    payload = json.loads(called.content[0].text)
                    assert not any(payload["configured"].values())
                    assert payload["planes_withheld"] == ["write", "deploy"]
                    for name, arguments in [
                        ("no_such_tool", {}),
                        ("azdata_query_kql", {}),
                        ("azdata_query_kql", {"query": "print 1", "allow_write": True}),
                        ("azdata_search", {"question": "test", "index_name": "test", "top_k": 100}),
                        ("azdata_query_kql", {"query": "print 1"}),
                    ]:
                        refused = await session.call_tool(name, arguments)
                        assert refused.isError, (name, refused)
                    assert not (await session.call_tool("azdata_status", {})).isError
            settings = Path(directory) / "settings.json"
            settings.write_text(json.dumps({"AZDATA_SEARCH_ENDPOINT": "https://example.search.windows.net"}))
            assert load_config(settings).search_endpoint == "https://example.search.windows.net"
            for values in [{"AZDATA_CLIENT_SECRET": "test-value"}, {"AZDATA_MAX_ROWS": 50}]:
                settings.write_text(json.dumps(values))
                try:
                    load_config(settings)
                except ValueError:
                    pass
                else:
                    raise AssertionError("Invalid MCP configuration was accepted")
        _log("MCP selftest: PASS (SDK handshake, five tools, status, refusals, recovery, config validation)")
        return 0

    return asyncio.run(run())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, help="Non-secret JSON settings outside the plugin package")
    parser.add_argument("--selftest", action="store_true", help="Exercise an offline MCP session")
    options = parser.parse_args()
    if options.selftest:
        raise SystemExit(_selftest())
    if options.config is None:
        parser.error("--config is required; the plugin client supplies its persistent data path")
    try:
        _state["config"] = load_config(options.config)
    except (OSError, ValueError) as exc:
        parser.exit(2, f"MCP configuration rejected ({type(exc).__name__}); check the JSON settings file\n")
    _state["config_path"] = options.config.resolve()
    asyncio.run(serve())
