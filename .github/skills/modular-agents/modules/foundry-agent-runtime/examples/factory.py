#!/usr/bin/env python3
"""The integration seam, worked: a declarative roster becomes running agents.

Runs with no Azure account and no SDK installed. When ``FOUNDRY_PROJECT_ENDPOINT``
and ``FOUNDRY_MODEL_DEPLOYMENT`` are set it wires the real Foundry client
instead; the roster, the tools and the build call are identical either way.
That substitutability is the point — an agent that only exists when the cloud is
reachable cannot be tested, and one that behaves differently offline is not the
agent that ships.

    python3 examples/factory.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import foundryagent as fa


# ── tools ───────────────────────────────────────────────────────────────────
# Plain functions with a stamp. No SDK import, so these are unit-testable by
# calling them, and they bind to whatever client the agent is built on.


@fa.tool
def lookup_status(asset_id: str) -> dict:
    """Return the current status of an asset by its identifier."""
    return {"asset_id": asset_id, "status": "nominal", "checked": "2026-01-01"}


@fa.tool(approval_mode="always_require")
def schedule_maintenance(asset_id: str, window: str) -> dict:
    """Book a maintenance window. Requires approval before it runs."""
    return {"asset_id": asset_id, "window": window, "booked": True}


# ── roster ──────────────────────────────────────────────────────────────────
# Plain data. In production this comes from a config file; the builder does not
# care where it came from, only that the fields are present.

ROSTER: dict[str, dict] = {
    "inspector": {
        "name": "Inspector",
        "description": "Answers questions about asset state.",
        "instructions": "You inspect assets. Use the tools; never guess a status.",
        "tools": [lookup_status],
        "model": "",  # empty = the config's default deployment
    },
    "planner": {
        "name": "Planner",
        "description": "Schedules maintenance.",
        "instructions": "You schedule maintenance windows.",
        "tools": [lookup_status, schedule_maintenance],
        "model": "fast",  # alias -> model_deployment_fast, if configured
        "parallel_tool_calls": True,
    },
}


# ── the stub client ─────────────────────────────────────────────────────────


class StubAgent:
    """Answers without a model. Enough to prove the wiring end to end."""

    def __init__(self, name: str, model: str, tools: list) -> None:
        self.name = name
        self.model = model
        self.tools = tools or []

    async def run(self, message: str) -> str:
        names = ", ".join(getattr(t, "__name__", str(t)) for t in self.tools)
        return f"[{self.name}/{self.model}] would answer {message!r} using: {names or 'no tools'}"


class StubClient:
    """Satisfies the one method the builder calls: ``as_agent``.

    Not an Agent Framework client, so ``bind_tools`` leaves the callables raw —
    which is exactly why the same roster runs here.
    """

    def as_agent(self, *, name, description, instructions, tools,
                 default_options, middleware, context_providers):
        return StubAgent(name, default_options["model_id"], list(tools or []))


# ── composition ─────────────────────────────────────────────────────────────


def build_roster() -> tuple[fa.FoundryConfig, dict[str, object], str]:
    """Build every agent in the roster. Returns (config, agents, mode)."""
    if os.environ.get("FOUNDRY_PROJECT_ENDPOINT"):
        config = fa.FoundryConfig.from_env()
        pool = fa.ClientPool(fa.foundry_agent_client(config))
        mode = "foundry"
    else:
        config = fa.FoundryConfig(
            project_endpoint="https://example-resource.services.ai.azure.com"
                             "/api/projects/example",
            model_deployment="model-default",
            model_deployment_fast="model-mini",
            fallback_models=("model-backup",),
        )
        stub = StubClient()
        pool = fa.ClientPool(lambda: stub)
        mode = "stub (set FOUNDRY_PROJECT_ENDPOINT to use Foundry)"

    for problem in config.warnings():
        print(f"  config warning: {problem}")

    # Tracing is optional and degrades to [] without the SDK, so this line is
    # safe in both modes.
    middleware = fa.build_tracing_middleware(on_event=_trace) or None

    agents = {
        agent_id: fa.build_agent(
            spec,
            pool.client_for(agent_id),
            config,
            agent_id=agent_id,
            middleware=middleware,
        )
        for agent_id, spec in ROSTER.items()
    }
    return config, agents, mode


def _trace(event: dict) -> None:
    """Where tool timings would go in a real deployment."""
    print(f"  trace: {event}")


async def main() -> int:
    config, agents, mode = build_roster()
    print(f"mode: {mode}")
    print(f"config: {config.redacted()}")
    print(f"model queue: {config.model_queue()}\n")

    for agent_id, agent in agents.items():
        # Every turn goes through the retry/fallback loop. In stub mode nothing
        # fails, so it returns on the first attempt and costs nothing.
        answer = await fa.run_with_fallback(
            lambda _model, a=agent: a.run("what is the status of unit 7?"),
            config,
            context=agent_id,
        )
        print(f"{agent_id}: {answer}")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
