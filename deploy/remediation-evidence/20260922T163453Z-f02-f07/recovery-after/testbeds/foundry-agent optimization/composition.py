"""Classifier configuration through agentconfig; llm_interface remains model owner."""

from pathlib import Path
from dataclasses import replace

from agentconfig import AgentSpec, load_agent_config, load_instructions

ROOT = Path(__file__).resolve().parent


def load_spec(path=ROOT / "configuration.yaml"):
    config = load_agent_config(path, strict=True)
    if set(config) != {"agents", "prompts_dir"} or config["prompts_dir"] != "prompts":
        raise ValueError("unexpected configuration surface")
    roster = config["agents"]
    if set(roster) != {"default", "iris-classifier"} or roster["default"] != "iris-classifier":
        raise ValueError("unknown agent refused")
    agent = roster["iris-classifier"]
    if set(agent) != {"name", "description", "model", "instructions", "tools"}:
        raise ValueError("unexpected agent fields")
    if agent["name"] != "agentcraft-iris-optimization" or agent["tools"] != []:
        raise ValueError("foreign agent or tools refused")
    if agent["model"] != "gpt-5.6-luna" or agent["instructions"] != ["classifier.md"]:
        raise ValueError("frozen model or prompt path drift")
    return AgentSpec(agent_id="iris-classifier", name=agent["name"], description=agent["description"],
                     model=agent["model"], instructions=load_instructions(agent["instructions"], path.parent / "prompts", strict=True),
                     tools=(), surface="hidden")


def compose(model, spec):
    return model.agent(name=spec.name, instructions=spec.instructions, tools=spec.tools)


def apply_optimization(spec, config):
    if config is None:
        raise ValueError("native optimization configuration missing")
    if not isinstance(config.skills, list) or not isinstance(config.tool_definitions, list):
        raise ValueError("native skills and tools must be lists")
    if (config.model not in (None, spec.model) or config.skills or config.tool_definitions
            or config.temperature is not None or getattr(config, "skills_dir", None)
            or getattr(config, "has_skills", False)):
        raise ValueError("only instructions may change in this comparison")
    if not isinstance(config.instructions, str) or not config.instructions.strip():
        raise ValueError("native instructions missing")
    return replace(spec, instructions=config.instructions)