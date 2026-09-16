"""Resolve the existing YAML and tool contracts without importing a cloud SDK."""

from __future__ import annotations

import asyncio
import inspect
import json
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, get_type_hints

import agentconfig
from pydantic import BaseModel, ConfigDict, Field, ValidationError, create_model
from toolshape import ToolSpec

_CONFIG_LOCK = threading.RLock()
_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}\Z")


class DefinitionError(ValueError):
    """A configuration or callable cannot be represented by the hosted contract."""


@dataclass(frozen=True)
class _BoundTool:
    name: str
    reference: str
    function: Callable[..., Any]
    arguments: type[BaseModel]
    schema: dict[str, Any]


def _bind(function: Any) -> _BoundTool:
    if not inspect.isfunction(function):
        raise DefinitionError("hosted tools must be importable Python functions")
    for marker in ("__agentconfig_tool__", "__agent_tool__"):
        metadata = getattr(function, marker, {})
        if metadata.get("approval_mode", "never_require") != "never_require":
            raise DefinitionError("tools requiring interactive approval cannot run in the headless hosted adapter")
    original = inspect.unwrap(function)
    if original.__qualname__ != original.__name__:
        raise DefinitionError("nested functions and bound methods cannot be packaged")
    shaped = getattr(function, "__toolspec__", None)
    name = shaped.name if isinstance(shaped, ToolSpec) else function.__name__
    if not _NAME.fullmatch(name):
        raise DefinitionError("tool names must be Python identifiers of at most 64 characters")
    description = inspect.getdoc(function) or ""
    if not description:
        raise DefinitionError(f"{name}: a tool description is required")
    signature = inspect.signature(function)
    try:
        hints = get_type_hints(original, include_extras=True)
    except (NameError, TypeError) as failure:
        raise DefinitionError(f"{name}: parameter annotations must resolve") from failure
    fields: dict[str, Any] = {}
    for parameter in signature.parameters.values():
        if parameter.name.lower() in {
            "credential", "credentials", "password", "token", "access_token", "api_key",
            "client_secret", "connection_string", "authorization",
        }:
            raise DefinitionError("credentials belong at the composition edge, never in tool arguments")
        if parameter.kind not in (
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        ):
            raise DefinitionError(f"{name}: variadic and positional-only parameters are unsupported")
        if parameter.name not in hints or hints[parameter.name] is Any:
            raise DefinitionError(f"{name}.{parameter.name}: a concrete annotation is required")
        declared = shaped.param(parameter.name) if isinstance(shaped, ToolSpec) else None
        default = parameter.default if parameter.default is not inspect.Parameter.empty else ...
        if declared is not None:
            if declared.required != (default is ...) or (
                not declared.required and declared.default != default
            ):
                raise DefinitionError(f"{name}.{parameter.name}: ToolSpec and signature defaults differ")
        fields[parameter.name] = (
            hints[parameter.name],
            Field(default=default, description=declared.describe() if declared else None),
        )
    if isinstance(shaped, ToolSpec) and {item.name for item in shaped.params} != set(fields):
        raise DefinitionError(f"{name}: ToolSpec parameters must match the function signature")
    try:
        arguments = create_model(
            f"{name}_arguments",
            __config__=ConfigDict(extra="forbid", strict=True, validate_default=True),
            **fields,
        )
        parameters = arguments.model_json_schema()
    except Exception as failure:
        raise DefinitionError(f"{name}: parameters must have a JSON schema") from failure
    return _BoundTool(
        name=name,
        reference=f"{function.__module__}:{function.__name__}",
        function=function,
        arguments=arguments,
        schema={
            "type": "function",
            "function": {"name": name, "description": description, "parameters": parameters},
        },
    )


class ToolRegistry:
    """One schema and validated invocation path for both direct and model calls."""

    def __init__(self, functions: tuple[Any, ...], *, max_result_bytes: int = 60_000) -> None:
        if not 256 <= max_result_bytes <= 1_000_000:
            raise DefinitionError("max_result_bytes must be between 256 and 1000000")
        self._tools: dict[str, _BoundTool] = {}
        self._max_result_bytes = max_result_bytes
        for function in functions:
            bound = _bind(function)
            if bound.name in self._tools:
                raise DefinitionError(f"duplicate hosted tool name: {bound.name}")
            self._tools[bound.name] = bound

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self._tools)

    @property
    def references(self) -> tuple[str, ...]:
        return tuple(bound.reference for bound in self._tools.values())

    @property
    def schemas(self) -> list[dict[str, Any]]:
        return json.loads(json.dumps([bound.schema for bound in self._tools.values()]))

    def native_tools(self, names: tuple[str, ...]) -> tuple[Any, ...]:
        from llm_interface import tool

        if set(names) - set(self.names):
            raise DefinitionError("native tool binding names an unknown tool")

        def bind(bound: _BoundTool):
            async def invoke(**arguments):
                return await self.invoke(bound.name, arguments)

            return tool(
                invoke, name=bound.name, description=bound.schema["function"]["description"],
                schema=bound.arguments, approval_mode="never_require",
            )

        return tuple(bind(bound) for bound in self._tools.values() if bound.name in names)

    async def invoke(self, name: str, arguments: Any) -> dict[str, Any]:
        bound = self._tools.get(name)
        if bound is None:
            return {"refused": True, "parameter": "tool", "accepted": list(self.names)}
        if not isinstance(arguments, dict):
            return {"refused": True, "parameter": "arguments", "accepted": "a JSON object"}
        try:
            validated = bound.arguments.model_validate(arguments)
        except ValidationError as failure:
            errors = failure.errors(include_input=False, include_url=False)
            return {
                "refused": True,
                "parameter": ".".join(map(str, errors[0]["loc"])) or "arguments",
                "problem": errors[0]["type"],
                "accepted": "Match this tool's published parameter schema.",
            }
        try:
            values = {name: getattr(validated, name) for name in bound.arguments.model_fields}
            if inspect.iscoroutinefunction(bound.function):
                result = await bound.function(**values)
            else:
                result = await asyncio.to_thread(bound.function, **values)
            if isinstance(result, str):
                try:
                    result = json.loads(result)
                except ValueError:
                    result = {"text": result}
            if not isinstance(result, dict):
                result = {"value": result}
            payload = json.dumps(result, allow_nan=False)
            if len(payload.encode("utf-8")) > self._max_result_bytes:
                return {"error": True, "detail": "tool result exceeds the configured byte limit"}
            return json.loads(payload)
        except Exception as failure:
            return {"error": True, "detail": f"tool failed ({type(failure).__name__})"}


@dataclass(frozen=True)
class Definition:
    """The original AgentSpec plus the hosted representation of its exact tools."""

    spec: agentconfig.AgentSpec
    tools: ToolRegistry

    @classmethod
    def from_spec(cls, spec: agentconfig.AgentSpec) -> Definition:
        if not spec.agent_id or not spec.model:
            raise DefinitionError("agent id and an explicit model deployment are required")
        return cls(spec=spec, tools=ToolRegistry(spec.tools))


def load_definition(
    control_dir: Path,
    *,
    agent_id: str | None = None,
    allowed_prefixes: tuple[str, ...] = (),
) -> Definition:
    """Build the whole roster before selecting one agent; imports default to denied."""
    with _CONFIG_LOCK:
        agentconfig.configure(Path(control_dir))
        agentconfig.set_allowed_tool_prefixes(allowed_prefixes)
        agentconfig.set_default_agent("")
        agentconfig.invalidate_config_cache()
        specs = agentconfig.build_all_specs(allowed_prefixes=allowed_prefixes)
        selected = agent_id or agentconfig.default_agent_id()
        if selected not in specs:
            raise DefinitionError("selected agent is absent from the roster")
        definitions = {name: Definition.from_spec(spec) for name, spec in specs.items()}
        return definitions[selected]