"""Testbed composition over the repository's public configuration APIs."""

from pathlib import Path

from agentconfig import AgentSpec, load_agent_config, load_instructions, resolve_tools

ROOT = Path(__file__).resolve().parent
TOOL_SPECS = ("proof_tools:nonce_digest", "proof_tools:nonce_statistics")


def load_spec(path: Path = ROOT / "configuration.yaml") -> AgentSpec:
    config = load_agent_config(path, strict=True)
    if set(config) != {"agents", "prompts_dir"} or config["prompts_dir"] != "prompts":
        raise ValueError("unexpected configuration keys or prompts directory")
    agents = config["agents"]
    if set(agents) != {"default", "foundry-tool-proof"} or agents["default"] != "foundry-tool-proof":
        raise ValueError("unexpected agent roster")
    agent = agents["foundry-tool-proof"]
    if not isinstance(agent, dict) or set(agent) != {"name", "description", "model", "instructions", "tools"}:
        raise ValueError("unexpected agent fields")
    if agent["name"] != "foundry-tool-proof" or not isinstance(agent["description"], str) or agent["instructions"] != ["proof.md"]:
        raise ValueError("unexpected agent metadata or prompt")
    if agent["tools"] != list(TOOL_SPECS):
        raise ValueError("unknown tool refused")
    if not isinstance(agent["model"], str) or not agent["model"].strip():
        raise ValueError("model deployment is required")
    instructions = load_instructions(agent["instructions"], path.parent / "prompts", strict=True)
    return AgentSpec(
        agent_id="foundry-tool-proof", name=agent["name"], description=agent["description"],
        model=agent["model"], instructions=instructions,
        tools=tuple(resolve_tools(agent["tools"], allowed_prefixes=("proof_tools",))), surface="hidden",
    )