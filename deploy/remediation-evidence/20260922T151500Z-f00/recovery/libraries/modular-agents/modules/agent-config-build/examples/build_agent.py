"""build_agent — the injection seam, worked end to end.

This file is the ONLY code a consumer writes. Everything else in the box is
generic. Copy it, replace the factory body with your SDK's constructor, delete
the commentary.

Run it directly to see the resolved roster:

    python3 examples/build_agent.py
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))   # the box, for `agentconfig`
sys.path.insert(0, str(_HERE))          # this dir, so `my_tools.*` is importable

import agentconfig
from agentconfig import AgentSpec


# ---------------------------------------------------------------------
# 1. Composition root: point the loader at the control tree and declare the
#    import allowlist. Do this once, at startup, before anything resolves.
# ---------------------------------------------------------------------
agentconfig.configure(
    _HERE / "control",
    # Fail-closed: only modules under this prefix may be imported from config.
    # Without it nothing resolves, which is the intended default -- config must
    # never be able to import an arbitrary module path.
    allowed_tool_prefixes=("my_tools.",),
    # Used only if the config omits `default`. The example config sets it.
    default_agent="researcher",
)


# ---------------------------------------------------------------------
# 2. The factory. Replace this dataclass with your SDK's agent constructor.
# ---------------------------------------------------------------------
@dataclass
class FakeAgent:
    """Stand-in for a real SDK agent, so the example runs with no dependency."""

    name: str
    model: str
    instructions: str
    tools: list


def make_agent(spec: AgentSpec) -> FakeAgent:
    """Turn a resolved spec into a concrete agent.

    A real implementation is the same shape::

        return ChatAgent(
            name=spec.name,
            instructions=spec.instructions,
            tools=[bind(t) for t in spec.tools],
            model=spec.model,
        )

    ``spec.tools`` holds plain callables carrying the ``agentconfig`` stamp.
    Bind them to your SDK here -- that keeps the SDK out of every tool module,
    so a framework change is one edit in this function.
    """
    return FakeAgent(
        name=spec.name,
        model=spec.model,
        instructions=spec.instructions,
        tools=list(spec.tools),
    )


def main() -> int:
    # Building every agent at boot means a typo in any definition fails the
    # process now, rather than when a user first selects that agent.
    agents = agentconfig.build_agents(make_agent)

    print(f"default agent: {agentconfig.default_agent_id()}\n")
    for agent_id, agent in agents.items():
        spec = agentconfig.build_spec(agent_id)
        visibility = "hidden" if spec.is_hidden else "visible"
        print(f"{agent_id}  [{visibility}]")
        print(f"  name         {agent.name}")
        print(f"  model        {agent.model}")
        print(f"  instructions {len(agent.instructions)} chars")
        print(f"  tools        {[t.__name__ for t in agent.tools] or 'none'}")
        # Keys this package does not understand survive here untouched, which
        # is how the consumer's own schema travels in the same file.
        if spec.extra:
            print(f"  extra        {sorted(spec.extra)}")
        print()

    # Consumer-defined blocks live on the raw config, alongside the roster.
    raw = agentconfig.load_agent_config()
    print(f"display names: {agentconfig.get_tool_display_names()}")
    print(f"top-level keys: {sorted(raw)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
