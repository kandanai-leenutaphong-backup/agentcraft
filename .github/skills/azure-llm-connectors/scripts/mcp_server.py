#!/usr/bin/env python3
"""Bounded, explicitly authorized access to azllm through the official MCP SDK."""

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
sys.path.insert(0, str(ROOT / "src"))

from azllm import FoundryConfig, LlmError, connect_async


class McpSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    endpoint: str = ""
    deployment: str = ""
    embedding_endpoint: str = ""
    embedding_deployment: str = ""
    managed_identity_client_id: str | None = None
    allow_model_calls: bool = False
    max_calls: int = Field(default=10, ge=1, le=1000)
    max_output_tokens: int = Field(default=512, ge=1, le=4096)
    max_input_characters: int = Field(default=32000, ge=1, le=64000)
    timeout_secs: float = Field(default=30.0, gt=0, le=120, allow_inf_nan=False)


class LlmTools:
    def __init__(self, settings: McpSettings, *, fixtures: bool = False) -> None:
        self.settings = settings
        self.fixtures = fixtures
        self.calls = 0
        self.connectors: dict[str, Any] = {}
        self.config = None
        if settings.endpoint or settings.deployment or settings.allow_model_calls:
            self.config = FoundryConfig(
                endpoint=settings.endpoint, deployment=settings.deployment,
                timeout_secs=settings.timeout_secs, max_retries=0,
                managed_identity_client_id=settings.managed_identity_client_id,
                default_max_output_tokens=settings.max_output_tokens,
            )
        if settings.embedding_endpoint:
            FoundryConfig(endpoint=settings.embedding_endpoint, deployment="embedding")

    def status(self) -> dict[str, Any]:
        return {
            "configured": self.config is not None,
            "fixtures": self.fixtures,
            "allow_model_calls": self.settings.allow_model_calls,
            "remaining_calls": self.settings.max_calls - self.calls,
            "max_output_tokens": self.settings.max_output_tokens,
        }

    def _grant(self, characters: int) -> None:
        if not self.settings.allow_model_calls:
            raise PermissionError("Model calls require allow_model_calls in operator configuration")
        if self.config is None:
            raise PermissionError("No model target configured")
        if characters > self.settings.max_input_characters:
            raise PermissionError("Input exceeds the configured character budget")
        if self.calls >= self.settings.max_calls:
            raise PermissionError("The configured per-process call budget is exhausted")
        self.calls += 1

    def _connector(self, endpoint: str = "") -> Any:
        assert self.config is not None
        key = endpoint or self.config.endpoint
        if key not in self.connectors:
            config = self.config.with_overrides(endpoint=key)
            arguments = {}
            if self.fixtures:
                sys.path.insert(0, str(ROOT / "tests"))
                from fakes import FakeAsyncClient
                arguments["client"] = FakeAsyncClient()
            self.connectors[key] = connect_async(config, **arguments)
        return self.connectors[key]

    async def ask(self, prompt: str, max_output_tokens: int | None = None) -> dict[str, Any]:
        cap = max_output_tokens if max_output_tokens is not None else self.settings.max_output_tokens
        if cap > self.settings.max_output_tokens:
            raise PermissionError("Requested output exceeds the configured token cap")
        self._grant(len(prompt))
        result = await self._connector().ask(prompt, max_output_tokens=cap)
        return {"fixtures": self.fixtures, "text": result.text, **result.metadata()}

    async def embed(self, texts: list[str], dimensions: int | None = None) -> dict[str, Any]:
        if not self.settings.embedding_deployment:
            raise PermissionError("No embedding deployment configured")
        self._grant(sum(len(text) for text in texts))
        result = await self._connector(self.settings.embedding_endpoint).embed(
            texts, deployment=self.settings.embedding_deployment, dimensions=dimensions,
        )
        return {"fixtures": self.fixtures, "vectors": result.vectors, **result.metadata()}

    async def aclose(self) -> None:
        for connector in self.connectors.values():
            await connector.aclose()


TOOLS = [
    types.Tool(
        name="azllm_status", description="Report local configuration and model-call grants without contacting Azure.",
        inputSchema={"type": "object", "properties": {}, "additionalProperties": False},
    ),
    types.Tool(
        name="azllm_ask", description="Ask the configured deployment within operator-defined input, output and call budgets.",
        inputSchema={"type": "object", "properties": {
            "prompt": {"type": "string", "minLength": 1, "maxLength": 64000},
            "max_output_tokens": {"type": "integer", "minimum": 1, "maximum": 4096},
        }, "required": ["prompt"], "additionalProperties": False},
    ),
    types.Tool(
        name="azllm_embed", description="Embed a bounded batch using the operator-configured embedding deployment.",
        inputSchema={"type": "object", "properties": {
            "texts": {"type": "array", "minItems": 1, "maxItems": 64,
                      "items": {"type": "string", "minLength": 1, "maxLength": 8192}},
            "dimensions": {"type": "integer", "minimum": 1, "maximum": 3072},
        }, "required": ["texts"], "additionalProperties": False},
    ),
]


def create_server(application: LlmTools, config_path: Path) -> Server:
    server = Server("azure-llm-connectors", version="0.1.0")

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        return TOOLS

    @server.call_tool(validate_input=True)
    async def call_tool(name: str, arguments: dict[str, Any]) -> types.CallToolResult:
        try:
            if name == "azllm_status":
                payload = {**application.status(), "config_file": str(config_path)}
            elif name == "azllm_ask":
                payload = await application.ask(**arguments)
            elif name == "azllm_embed":
                payload = await application.embed(**arguments)
            else:
                payload = {"error": "unknown_tool"}
        except PermissionError as error:
            payload = {"error": "permission_denied", "detail": str(error)}
        except LlmError as error:
            payload = {"error": error.category, "retryable": error.retryable, "status_code": error.status_code}
        except Exception:
            payload = {"error": "operation_failed"}
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=json.dumps(payload, allow_nan=False))],
            isError=bool(payload.get("error")),
        )

    return server


async def serve(application: LlmTools, config_path: Path) -> None:
    server = create_server(application, config_path)
    try:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())
    finally:
        await application.aclose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--fixtures", action="store_true", help="Use injected fake clients; every result is marked")
    parser.add_argument("--selftest", action="store_true")
    options = parser.parse_args()
    if options.selftest:
        return subprocess.call([sys.executable, "-B", str(ROOT / "tests/mcp_smoke.py")])
    if options.config is None:
        parser.error("--config is required; the plugin client supplies its persistent path")
    try:
        values = json.loads(options.config.read_text()) if options.config.exists() else {}
        application = LlmTools(McpSettings.model_validate(values), fixtures=options.fixtures)
    except (OSError, ValueError, LlmError):
        parser.exit(2, "Invalid MCP configuration; only documented non-secret fields are accepted\n")
    asyncio.run(serve(application, options.config.resolve()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())