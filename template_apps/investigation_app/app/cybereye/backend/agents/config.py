"""Fail-closed resolution of versioned CyberEye agent configuration."""

from __future__ import annotations

import hashlib
import importlib
import inspect
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .tools import ToolMetadata, metadata

CONTROL_DIR = Path(__file__).resolve().parents[2] / "control"
CONFIG_PATH = CONTROL_DIR / "agent_config.yaml"
ALLOWED_TOOL_PREFIX = "app.cybereye.backend.agents.tools."
_ID = re.compile(r"^[a-z][a-z0-9_]*$")


class ConfigError(ValueError):
    """The runtime configuration is unsafe, ambiguous, or incomplete."""


class _UniqueKeyLoader(yaml.SafeLoader):
    pass


def _construct_mapping(loader: yaml.SafeLoader, node: yaml.MappingNode, deep: bool = False) -> dict[Any, Any]:
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise ConfigError(f"duplicate YAML key: {key}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping,
)


@dataclass(frozen=True, slots=True)
class ResolvedTool:
    function: Callable[..., dict[str, Any]]
    metadata: ToolMetadata
    display_name: str

    def openai_schema(self) -> dict[str, Any]:
        return self.metadata.openai_schema()


@dataclass(frozen=True, slots=True)
class AgentSpec:
    config_id: str
    config_version: int
    config_digest: str
    agent_id: str
    name: str
    description: str
    model: str
    reasoning_effort: str
    reasoning_summary: str | None
    max_output_tokens: int
    max_tool_iterations: int
    diagnosis_max_output_tokens: int
    diagnosis_max_tool_iterations: int
    parallel_tool_calls: bool
    instructions: str
    tools: tuple[ResolvedTool, ...]
    instruction_files: tuple[tuple[str, str], ...] = ()
    foundation_files: tuple[tuple[str, str], ...] = ()

    def reasoning_request(self, *, summarize: bool = False) -> dict[str, Any]:
        """The `reasoning` argument for a Responses call, with summaries only where asked.

        Measured against this deployment: summary parts are emitted at effort `high` and
        above and never at `none`, `low` or `medium`, so a summary is requested only when
        the configured effort can actually produce one.
        """
        request: dict[str, Any] = {"effort": self.reasoning_effort}
        if summarize and self.reasoning_summary:
            request["summary"] = self.reasoning_summary
        return request


def describe_agent(spec: AgentSpec, datasources: dict[str, dict[str, Any]]) -> dict[str, Any]:
    tools = []
    source_root = Path(__file__).resolve().parent / "tools"
    for tool in spec.tools:
        source: dict[str, Any] = {"available": False, "path": "", "start_line": 0,
                                  "code": "", "truncated": False}
        try:
            filename = inspect.getsourcefile(tool.function)
            if (not tool.function.__module__.startswith(ALLOWED_TOOL_PREFIX) or not filename
                    or not Path(filename).resolve().is_relative_to(source_root)):
                raise ValueError("source outside registered tool directory")
            lines, start = inspect.getsourcelines(tool.function)
            code = "".join(lines[:200])[:18000]
            source = {
                "available": True,
                "path": str(Path(filename).resolve().relative_to(source_root.parents[4])),
                "start_line": start, "code": code,
                "truncated": len(lines) > 200 or len("".join(lines)) > len(code),
            }
        except (OSError, TypeError, ValueError, AttributeError):
            pass
        bindings = tool.metadata.datasource
        names = (bindings,) if isinstance(bindings, str) else bindings
        connections = [dict(datasources.get(name, {
            "kind": "unknown", "label": "Datasource not declared", "target": "",
            "endpoint": "", "configured": False,
        })) for name in dict.fromkeys(names or ("none",))]
        for connection in connections:
            connection["target_label"] = "Default target" if tool.metadata.fallback else "Target"
        tools.append({
            "id": tool.metadata.name, "name": tool.display_name,
            "description": tool.metadata.description, "category": tool.metadata.category,
            "fallback": tool.metadata.fallback, "parameters": tool.metadata.parameters,
            "datasource": connections[0], "datasources": connections,
            "datasource_ids": list(dict.fromkeys(
                source_id for connection in connections for source_id in connection.get("source_ids", [])
            )),
            "source": source,
        })
    return {
        "id": spec.agent_id, "name": spec.name, "description": spec.description,
        "model": spec.model, "config_id": spec.config_id, "config_version": spec.config_version,
        "config_digest": spec.config_digest, "tools": tools,
    }


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ConfigError(f"configuration file not found: {path}")
    try:
        value = yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueKeyLoader)
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML in {path.name}: {exc}") from exc
    if not isinstance(value, dict):
        raise ConfigError(f"{path.name} root must be a mapping")
    return value


def _safe_relative(root: Path, value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{label} must be a non-empty relative path")
    candidate = (root / value).resolve()
    if not candidate.is_relative_to(root.resolve()):
        raise ConfigError(f"{label} escapes its configured directory: {value}")
    return candidate


def _string_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise ConfigError(f"{label} must be a list of non-empty strings")
    return list(value)


def _resolve_callable(spec: str) -> Callable[..., dict[str, Any]]:
    if ":" not in spec:
        raise ConfigError(f"invalid tool spec {spec!r}; expected module:function")
    module_name, function_name = spec.rsplit(":", 1)
    if not module_name.startswith(ALLOWED_TOOL_PREFIX) or not function_name:
        raise ConfigError(f"tool spec is outside allowed prefix {ALLOWED_TOOL_PREFIX}: {spec}")
    try:
        module = importlib.import_module(module_name)
        function = getattr(module, function_name)
    except (ImportError, AttributeError) as exc:
        raise ConfigError(f"cannot resolve tool spec {spec}: {exc}") from exc
    if not callable(function):
        raise ConfigError(f"resolved tool is not callable: {spec}")
    return function


def load_agent_spec(config_path: Path = CONFIG_PATH, agent_id: str | None = None) -> AgentSpec:
    """Resolve config, includes, prompts, callables, schemas, and display names at boot."""
    config_path = config_path.resolve()
    control_dir = config_path.parent
    base = _read_yaml(config_path)
    if base.get("version") != 1:
        raise ConfigError("agent_config.yaml version must be 1")
    config_id = base.get("config_id")
    if not isinstance(config_id, str) or not config_id.strip():
        raise ConfigError("config_id must be a non-empty string")

    agents_value = base.get("agents")
    if not isinstance(agents_value, dict):
        raise ConfigError("agents must be a mapping")
    agents = dict(agents_value)
    source_files = [config_path]
    for include in _string_list(base.get("include", []), "include"):
        path = _safe_relative(control_dir, include, "include path")
        fragment = _read_yaml(path)
        source_files.append(path)
        fragment_agents = fragment.get("agents")
        if not isinstance(fragment_agents, dict):
            raise ConfigError(f"{path.name} agents must be a mapping")
        for candidate, definition in fragment_agents.items():
            if candidate in agents:
                raise ConfigError(f"duplicate agent id: {candidate}")
            agents[candidate] = definition

    target = agent_id or agents.get("default")
    if not isinstance(target, str) or not _ID.fullmatch(target):
        raise ConfigError(f"invalid or missing agent id: {target!r}")
    definition = agents.get(target)
    if not isinstance(definition, dict):
        raise ConfigError(f"agent not found: {target}")
    for candidate in (key for key in agents if key != "default"):
        if not isinstance(candidate, str) or not _ID.fullmatch(candidate):
            raise ConfigError(f"invalid agent id: {candidate!r}")

    model = definition.get("model")
    if not isinstance(model, str) or not model.strip():
        raise ConfigError(f"agent {target} has no model")
    if model.strip() != "gpt-5.6-luna":
        raise ConfigError(f"agent {target} model must be gpt-5.6-luna")
    runtime = definition.get("runtime", {})
    if not isinstance(runtime, dict):
        raise ConfigError(f"agent {target} runtime must be a mapping")
    reasoning_effort = runtime.get("reasoning_effort", "none")
    if reasoning_effort not in {"none", "low", "medium", "high", "xhigh", "max"}:
        raise ConfigError("reasoning_effort is not supported by gpt-5.6-luna")
    reasoning_summary = runtime.get("reasoning_summary")
    if reasoning_summary is not None and reasoning_summary not in {"auto", "concise", "detailed"}:
        raise ConfigError("reasoning_summary must be auto, concise, or detailed")
    max_output_tokens = runtime.get("max_output_tokens", 900)
    if not isinstance(max_output_tokens, int) or not 256 <= max_output_tokens <= 4000:
        raise ConfigError("max_output_tokens must be an integer from 256 to 4000")
    max_tool_iterations = runtime.get("max_tool_iterations", 6)
    if not isinstance(max_tool_iterations, int) or not 1 <= max_tool_iterations <= 10:
        raise ConfigError("max_tool_iterations must be an integer from 1 to 10")
    diagnosis_max_output_tokens = runtime.get("diagnosis_max_output_tokens", max_output_tokens)
    if not isinstance(diagnosis_max_output_tokens, int) or not 256 <= diagnosis_max_output_tokens <= 4000:
        raise ConfigError("diagnosis_max_output_tokens must be an integer from 256 to 4000")
    diagnosis_max_tool_iterations = runtime.get("diagnosis_max_tool_iterations", max_tool_iterations)
    if not isinstance(diagnosis_max_tool_iterations, int) or not 1 <= diagnosis_max_tool_iterations <= 12:
        raise ConfigError("diagnosis_max_tool_iterations must be an integer from 1 to 12")
    parallel_tool_calls = runtime.get("parallel_tool_calls", True)
    if not isinstance(parallel_tool_calls, bool):
        raise ConfigError("parallel_tool_calls must be a boolean")
    prompts_dir = _safe_relative(control_dir, base.get("prompts_dir", "prompts"), "prompts_dir")
    foundation_refs = _string_list(base.get("foundation_prompts", []), "foundation_prompts")
    instruction_refs = _string_list(definition.get("instructions", []), "instructions")
    prompt_refs = [*foundation_refs, *instruction_refs]
    if not prompt_refs:
        raise ConfigError(f"agent {target} has no prompts")
    prompt_parts: list[str] = []
    for ref in prompt_refs:
        path = _safe_relative(prompts_dir, ref, "prompt path")
        if not path.is_file():
            raise ConfigError(f"prompt not found: {ref}")
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            raise ConfigError(f"prompt is empty: {ref}")
        prompt_parts.append(text)
        source_files.append(path)

    displays = base.get("tool_display_names")
    if not isinstance(displays, dict):
        raise ConfigError("tool_display_names must be a mapping")
    tool_specs = _string_list(definition.get("tools", []), "tools")
    resolved: list[ResolvedTool] = []
    seen_names: set[str] = set()
    for tool_spec in tool_specs:
        function = _resolve_callable(tool_spec)
        tool_meta = metadata(function)
        if not _ID.fullmatch(tool_meta.name):
            raise ConfigError(f"invalid tool name: {tool_meta.name!r}")
        if tool_meta.name in seen_names:
            raise ConfigError(f"duplicate resolved tool name: {tool_meta.name}")
        display = displays.get(tool_meta.name)
        if not isinstance(display, str) or not display.strip():
            raise ConfigError(f"missing display name for tool: {tool_meta.name}")
        seen_names.add(tool_meta.name)
        resolved.append(ResolvedTool(function, tool_meta, display.strip()))

    digest = hashlib.sha256()
    for path in source_files:
        digest.update(path.read_bytes())
    return AgentSpec(
        config_id=config_id.strip(), config_version=1, config_digest=digest.hexdigest()[:12],
        agent_id=target, name=str(definition.get("name") or target),
        description=str(definition.get("description") or ""), model=model.strip(),
        reasoning_effort=reasoning_effort, reasoning_summary=reasoning_summary,
        max_output_tokens=max_output_tokens,
        max_tool_iterations=max_tool_iterations, parallel_tool_calls=parallel_tool_calls,
        diagnosis_max_output_tokens=diagnosis_max_output_tokens,
        diagnosis_max_tool_iterations=diagnosis_max_tool_iterations,
        instructions="\n\n".join(prompt_parts), tools=tuple(resolved),
        foundation_files=tuple((Path(ref).name, text) for ref, text in
                               zip(foundation_refs, prompt_parts[:len(foundation_refs)])),
        instruction_files=tuple((Path(ref).name, text) for ref, text in
                                zip(instruction_refs, prompt_parts[len(foundation_refs):])),
    )
