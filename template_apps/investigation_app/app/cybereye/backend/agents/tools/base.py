"""Declarative contracts and bounded envelopes for CyberEye agent tools."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from ...config import settings
from ...data import ReadOnlyAdx
from ...investigation import Scanner


def bind(query: str) -> str:
    """Bind a declared query to the configured table.

    Queries carry `{TABLE}` rather than a literal, and KQL's own braces rule out an f-string.
    """
    return query.replace("{TABLE}", settings.table)


EVIDENCE_COLUMNS = (
    "source_time", "resource_id", "event_type_recovered", "product", "target_user_name",
    "target_host_name", "source_address", "destination_address", "query_name",
    "win_event_id", "service_name", "application_name", "flow_action",
)


def evidence_query(ids: list[str]) -> tuple[str, dict[str, str]]:
    """One row-citation projection, shared by the HTTP route and the agent tool."""
    names = [f"rid{index}" for index in range(len(ids))]
    query = bind(
        "{TABLE}\n"
        f"| where resource_id in ({', '.join(names)})\n"
        f"| project {', '.join(EVIDENCE_COLUMNS)}\n"
        "| order by source_time asc, resource_id asc"
    )
    return query, dict(zip(names, ids))


@dataclass(frozen=True, slots=True)
class ToolContext:
    adx: ReadOnlyAdx
    scanner: Scanner


@dataclass(frozen=True, slots=True)
class ToolMetadata:
    name: str
    description: str
    parameters: dict[str, Any]
    category: str
    fallback: bool = False
    datasource: str | tuple[str, ...] = "unknown"

    def openai_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "strict": True,
        }


def agent_tool(*, name: str, description: str, parameters: dict[str, Any], category: str,
               fallback: bool = False, datasource: str | tuple[str, ...] = "unknown") -> Callable[[Callable[..., dict[str, Any]]], Callable[..., dict[str, Any]]]:
    """Attach one source of truth for runtime resolution and OpenAI schemas."""
    def decorate(function: Callable[..., dict[str, Any]]) -> Callable[..., dict[str, Any]]:
        function.__cybereye_tool__ = ToolMetadata(  # type: ignore[attr-defined]
            name=name,
            description=description.strip(),
            parameters=parameters,
            category=category,
            fallback=fallback,
            datasource=datasource,
        )
        return function
    return decorate


def metadata(function: Callable[..., Any]) -> ToolMetadata:
    value = getattr(function, "__cybereye_tool__", None)
    if not isinstance(value, ToolMetadata):
        raise TypeError(f"tool {function!r} has no declarative CyberEye metadata")
    return value


def parse_window(start: str, end: str) -> tuple[datetime, datetime]:
    def parse(value: str) -> datetime:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("tool times must include a UTC offset")
        return parsed.astimezone(timezone.utc)

    lower, upper = parse(start), parse(end)
    if upper <= lower:
        raise ValueError("end must be after start")
    if (upper - lower).total_seconds() > 48 * 3600:
        raise ValueError("tool window is capped at 48 hours")
    return lower, upper


def query_envelope(tool: str, category: str, result: Any, scope: dict[str, Any], *,
                   fallback: bool = False) -> dict[str, Any]:
    """Convert a QueryResponse into a categorical, bounded model-facing object."""
    rows = [dict(zip(result.columns, row)) for row in result.model_dump(mode="json")["rows"]]
    return {
        "kind": "cybereye_tool_result",
        "tool": tool,
        "category": category,
        "scope": {**scope, "row_count": len(rows), "max_rows": result.max_rows},
        "columns": list(result.columns),
        "rows": rows,
        "truncated": bool(result.truncated),
        "historical_replay": True,
        "fallback": fallback,
    }


def object_schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


WINDOW_PROPERTIES = {
    "start": {"type": "string", "description": "ISO-8601 timestamp with UTC offset; window start."},
    "end": {"type": "string", "description": "ISO-8601 timestamp with UTC offset; window end, no more than 48 hours later."},
}
