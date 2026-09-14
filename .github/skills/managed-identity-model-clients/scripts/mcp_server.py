#!/usr/bin/env python3
"""Bounded modelaccess calls through an operator-configured MCP stdio process."""

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
sys.path.insert(0, str(ROOT))

from modelaccess import (
    DEFAULT_SCOPE, FakeAsyncClient, ModelConfig, ModelError, connect_async,
    embedding_config, fake_embedding_response, fake_text_response,
)


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    endpoint: str = ""
    deployment: str = ""
    embedding_endpoint: str | None = None
    embedding_deployment: str | None = None
    credential_scope: str = DEFAULT_SCOPE
    allowed_hosts: list[str] | None = None
    managed_identity_client_id: str | None = None
    allow_model_calls: bool = False
    max_calls: int = Field(default=10, ge=1, le=1000)
    max_output_tokens: int = Field(default=512, ge=1, le=4096)
    max_input_characters: int = Field(default=32000, ge=1, le=64000)
    timeout_secs: float = Field(default=30.0, gt=0, le=120, allow_inf_nan=False)


class ModelTools:
    def __init__(self, settings: Settings, *, fixtures: bool = False) -> None:
        self.settings = settings
        self.fixtures = fixtures
        self.calls = 0
        self.clients: dict[tuple[str, str], Any] = {}
        self.config = None
        if settings.endpoint or settings.deployment or settings.allow_model_calls:
            self.config = ModelConfig(
                endpoint=settings.endpoint, deployment=settings.deployment,
                embedding_endpoint=settings.embedding_endpoint,
                embedding_deployment=settings.embedding_deployment,
                credential_scope=settings.credential_scope,
                allowed_hosts=tuple(settings.allowed_hosts) if settings.allowed_hosts is not None else None,
                managed_identity_client_id=settings.managed_identity_client_id,
                timeout_secs=settings.timeout_secs, max_retries=0,
                default_max_output_tokens=settings.max_output_tokens,
            )

    def status(self) -> dict[str, Any]:
        return {"configured": self.config is not None, "fixtures": self.fixtures,
                "allow_model_calls": self.settings.allow_model_calls,
                "remaining_calls": self.settings.max_calls - self.calls}

    def reserve(self, characters: int) -> None:
        if not self.settings.allow_model_calls or self.config is None:
            raise PermissionError("Model calls need explicit operator configuration and approval")
        if characters > self.settings.max_input_characters or self.calls >= self.settings.max_calls:
            raise PermissionError("Configured input or per-process call budget exceeded")
        self.calls += 1

    def client(self, config: ModelConfig) -> Any:
        key = (config.endpoint, config.deployment)
        if key not in self.clients:
            self.clients[key] = connect_async(config)
        return self.clients[key]

    async def ask(self, prompt: str, max_output_tokens: int | None = None) -> dict[str, Any]:
        cap = max_output_tokens or self.settings.max_output_tokens
        if cap > self.settings.max_output_tokens:
            raise PermissionError("Requested output exceeds the operator's token cap")
        self.reserve(len(prompt))
        assert self.config is not None
        if self.fixtures:
            async with connect_async(self.config, client=FakeAsyncClient(
                responses=[fake_text_response("fixture answer")]), owns_client=True) as client:
                result = await client.ask(prompt, max_output_tokens=cap)
        else:
            result = await self.client(self.config).ask(prompt, max_output_tokens=cap)
        return {"fixtures": self.fixtures, "text": result.text, **result.metadata()}

    async def embed(self, texts: list[str], dimensions: int = 3) -> dict[str, Any]:
        if self.config is None or not self.settings.embedding_deployment:
            raise PermissionError("An embedding deployment must be configured by the operator")
        config = embedding_config(self.config)
        self.reserve(sum(len(text) for text in texts))
        if self.fixtures:
            response = fake_embedding_response([[float(index)] * dimensions for index in range(len(texts))])
            async with connect_async(config, client=FakeAsyncClient(embeddings=[response]), owns_client=True) as client:
                result = await client.embed(texts, dimensions=dimensions)
        else:
            result = await self.client(config).embed(texts, dimensions=dimensions)
        return {"fixtures": self.fixtures, "vectors": result.vectors, **result.metadata()}

    async def close(self) -> None:
        for client in self.clients.values():
            await client.aclose()


TOOLS = [
    types.Tool(name="modelaccess_status", description="Report model configuration and grants without calling a provider.",
               inputSchema={"type": "object", "properties": {}, "additionalProperties": False}),
    types.Tool(name="modelaccess_ask", description="Ask the operator-configured model within explicit input/output and call budgets.",
               inputSchema={"type": "object", "properties": {
                   "prompt": {"type": "string", "minLength": 1, "maxLength": 64000},
                   "max_output_tokens": {"type": "integer", "minimum": 1, "maximum": 4096}},
                   "required": ["prompt"], "additionalProperties": False}),
    types.Tool(name="modelaccess_embed", description="Embed a bounded batch using the configured embedding account.",
               inputSchema={"type": "object", "properties": {
                   "texts": {"type": "array", "minItems": 1, "maxItems": 64,
                             "items": {"type": "string", "minLength": 1, "maxLength": 8192}},
                   "dimensions": {"type": "integer", "minimum": 1, "maximum": 3072}},
                   "required": ["texts"], "additionalProperties": False}),
]


async def serve(application: ModelTools, config_path: Path) -> None:
    server = Server("managed-identity-model-clients", version="1.0.0")

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        return TOOLS

    @server.call_tool(validate_input=True)
    async def call_tool(name: str, arguments: dict[str, Any]) -> types.CallToolResult:
        try:
            if name == "modelaccess_status":
                payload = {**application.status(), "config_file": str(config_path)}
            elif name == "modelaccess_ask":
                payload = await application.ask(**arguments)
            elif name == "modelaccess_embed":
                payload = await application.embed(**arguments)
            else:
                payload = {"error": "unknown_tool"}
        except PermissionError as error:
            payload = {"error": "permission_denied", "detail": str(error)}
        except ModelError as error:
            payload = {"error": error.category, "retryable": error.retryable}
        except Exception:
            payload = {"error": "operation_failed"}
        return types.CallToolResult(content=[types.TextContent(type="text", text=json.dumps(payload, allow_nan=False))],
                                    isError=bool(payload.get("error")))

    try:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())
    finally:
        await application.close()


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
        application = ModelTools(Settings.model_validate(values), fixtures=options.fixtures)
    except (OSError, ValueError, ModelError):
        parser.exit(2, "Invalid MCP configuration; use documented non-secret fields\n")
    asyncio.run(serve(application, options.config.resolve()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())