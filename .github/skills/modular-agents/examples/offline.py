"""Configuration -> SDK factory -> hosted service -> tool -> readable result, offline."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from _bootstrap import SKILL_ROOT

import agentconfig
import foundryagent
from hostedagents import load_definition
from hostedagents.engine import AgentRuntime
from hostedagents.policy import RuntimePolicy


class ModelFixture:
    def __init__(self):
        self.calls = 0

    async def complete(self, **_kwargs):
        self.calls += 1
        if self.calls == 1:
            return {"tool_calls": [{"id": "example-call", "type": "function", "function": {
                "name": "search_notes", "arguments": '{"query":"hosting"}',
            }}]}
        return {"content": "The Hosting note describes a portable flat source bundle on Foundry."}


class FactoryFixture:
    def as_agent(self, **values):
        return values


async def main() -> None:
    definition = load_definition(ROOT / "examples/control", allowed_prefixes=("agent_tools.",))
    client_agent = foundryagent.build_agent(
        definition.spec, FactoryFixture(), foundryagent.FoundryConfig(
            project_endpoint="https://example.services.ai.azure.com/api/projects/example",
            model_deployment=definition.spec.model,
        ),
        markers=(agentconfig.TOOL_MARKER, foundryagent.TOOL_MARKER),
    )
    assert client_agent["instructions"] == definition.spec.instructions
    runtime = AgentRuntime(
        definition, RuntimePolicy(allowed_tools=definition.tools.names, allow_model=True), model=ModelFixture(),
    )
    async for _event, _payload in runtime.chat_events("hosting?", principal="offline-example", turn_id="example-turn"):
        pass
    result = runtime.result("example-turn", principal="offline-example")
    assert result["status"] == "done"
    assert any(event["event"] == "tool_result" for event in result["events"])
    print(json.dumps({"mode": "offline fixture", "agent": definition.spec.agent_id, "result": result}, indent=2))


if __name__ == "__main__":
    asyncio.run(main())