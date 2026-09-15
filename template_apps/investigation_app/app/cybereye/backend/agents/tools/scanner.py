"""Deterministic scanner exposed as a purpose-built agent tool."""

from __future__ import annotations

from typing import Any

from ...models import ScanRequest
from ...config import settings
from .base import bind, ToolContext, WINDOW_PROPERTIES, agent_tool, object_schema, parse_window


@agent_tool(
    name="scan_situations",
    datasource="adx",
    category="orientation",
    description=bind("""
Run the deterministic target-specific scanner over {TABLE} and return ranked
historical situation envelopes. Prefer this first for open-ended orientation; it
covers the replay's known correlated patterns without model-authored KQL.
"""),
    parameters=object_schema(dict(WINDOW_PROPERTIES), ["start", "end"]),
)
def scan_situations(context: ToolContext, *, start: str, end: str) -> dict[str, Any]:
    lower, upper = parse_window(start, end)
    result = context.scanner.scan(ScanRequest(start=lower, end=upper)).model_dump(mode="json")
    return {
        "tool": "scan_situations",
        "category": "orientation",
        "scope": {"start": start, "end": end, "situation_count": len(result["situations"])},
        "result": result,
        "historical_replay": True,
        "fallback": False,
    }
