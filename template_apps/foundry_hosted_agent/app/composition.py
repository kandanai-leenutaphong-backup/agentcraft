"""Agent composition from configuration.yaml through agentconfig's public API."""

from pathlib import Path

from agentconfig import AgentSpec, load_agent_config, load_instructions, resolve_tools

ROOT = Path(__file__).resolve().parent
TOOL_MODULE = "agent_tools"
REQUIRED_FIELDS = frozenset({"name", "model", "instructions"})
AGENT_FIELDS = REQUIRED_FIELDS | {"description", "tools"}


def load_spec(path: Path = ROOT / "configuration.yaml") -> AgentSpec:
    """Exactly one default agent; tools only from `agent_tools`; anything else refuses."""
    config = load_agent_config(path, strict=True)
    if set(config) != {"agents", "prompts_dir"} or config["prompts_dir"] != "prompts":
        raise ValueError("unexpected configuration keys or prompts directory")
    roster = config["agents"]
    default = roster.get("default") if isinstance(roster, dict) else None
    if not isinstance(default, str) or set(roster) != {"default", default}:
        raise ValueError("exactly one default agent required")
    agent = roster[default]
    if not isinstance(agent, dict) or not REQUIRED_FIELDS <= set(agent) <= AGENT_FIELDS:
        raise ValueError("unexpected agent fields")
    for key in ("name", "model"):
        if not isinstance(agent[key], str) or not agent[key].strip():
            raise ValueError(f"agent {key} is required")
    tools = agent.get("tools", [])
    if not isinstance(tools, list) or any(not isinstance(item, str) or not item.startswith(TOOL_MODULE + ":")
                                          for item in tools):
        raise ValueError("unknown tool refused")
    try:
        resolved = resolve_tools(tools, allowed_prefixes=(TOOL_MODULE,))
    except (ImportError, AttributeError, TypeError) as error:
        raise ValueError("unknown tool refused") from error
    instructions = load_instructions(agent["instructions"], path.parent / config["prompts_dir"], strict=True)
    return AgentSpec(agent_id=default, name=agent["name"], description=agent.get("description", ""),
                     model=agent["model"], instructions=instructions, tools=tuple(resolved), surface="hidden")
