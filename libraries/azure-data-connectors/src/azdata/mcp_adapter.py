"""Optional MCP tools over an operator-created, fixed-target DataConnector.

Non-success bodies retain OperationResult verbatim plus ``failures``: operation
errors first, then unsuccessful items in native order. ``field`` addresses the
native error/item; operation-level effects summarize all items, item effects
remain exact. Absent errors use the native non-success status as code.
The host stamps capability_id, tool operation and run_id on these mappings.
Native retryable=True means unspecified, never replay authority. Possible writes
require read-back even when retryable=False; unsupported requests never retry.
The public tool set remains query/status only; no mutation grant is introduced.
"""

from __future__ import annotations

import json
from dataclasses import replace
from typing import Any

from mcp import types

from azdata import DataConnector, ErrorInfo, QueryRequest


TOOLS = [
    types.Tool(name="data_status", description="Describe the configured data target and support without I/O.",
               inputSchema={"type": "object", "properties": {}, "additionalProperties": False}),
    types.Tool(name="data_query", description="Query one configured target using its native dialect, grants and limits.",
               inputSchema={"type": "object", "properties": {
                   "dialect": {"type": "string", "minLength": 1, "maxLength": 64},
                   "expression": {"type": "string", "maxLength": 12000},
                   "parameters": {"type": "object", "maxProperties": 100},
                   "projection": {"type": "array", "maxItems": 100, "uniqueItems": True,
                                  "items": {"type": "string", "minLength": 1, "maxLength": 256}},
                   "limits": {"type": "object", "properties": {
                       "timeout_seconds": {"type": "number", "exclusiveMinimum": 0},
                       "max_items": {"type": "integer", "minimum": 1},
                       "max_input_bytes": {"type": "integer", "minimum": 1},
                       "max_output_bytes": {"type": "integer", "minimum": 1},
                       "max_attempts": {"type": "integer", "minimum": 1},
                   }, "additionalProperties": False},
               }, "required": ["dialect", "expression"], "additionalProperties": False}),
]


def _failure(error: ErrorInfo, *, effect: str, mutation: bool, field: str) -> dict[str, Any]:
    category = {
        "unknown": "failed", "partial": "failed", "pending": "failed",
        "not_found": "failed", "conflict": "failed", "rate_limit": "rate-limit",
    }.get(error.category, error.category)
    if error.code == "rate_limited":
        category = "rate-limit"
    elif error.code.endswith("transport_unavailable"):
        category = "unavailable"
    elif error.code == "deadline_before_request":
        category = "interrupted"
    if category == "unsupported":
        retry, action = "never", "Use a supported operation and guarantee."
    elif mutation and effect != "none":
        retry, action = "read_back_first", "Read back affected items before another write."
    elif category in {"config", "invalid", "denied"}:
        retry, action = "safe_after_correction", "Correct the request or ask the host to review its grants and bounds."
    elif error.retryable:
        retry, action = "unspecified", "Review the native retry policy and remaining budget before another attempt."
    else:
        retry, action = "never", "Inspect the native failure; no replay is authorized."
    return {"code": error.code, "category": category, "field": field,
            "effect": effect, "retry": retry, "action": action}


def _failures(result) -> list[dict[str, Any]]:
    mutation = result.operation not in {"read", "query", "status"}
    effects = {item.effect for item in result.items}
    if "unknown" in effects or result.status == "unknown":
        effect = "unknown"
    elif "accepted" in effects:
        effect = "accepted"
    elif mutation and not result.items and (result.status == "pending" or (
        result.status == "failed" and result.metrics.get("attempts", 0) > 0
    )):
        effect = "unknown"
    else:
        effect = "none"
    failures = [_failure(error, effect=effect, mutation=mutation, field=f"errors[{index}]")
                for index, error in enumerate(result.errors)]
    failures.extend(
        _failure(item.error or ErrorInfo(item.status, item.status), effect=item.effect,
                 mutation=mutation, field=f"items[{position}]")
        for position, item in enumerate(result.items) if item.error or item.status != "success"
    )
    return failures or [_failure(ErrorInfo(result.status, result.status), effect=effect,
                                 mutation=mutation, field="status")]


def bind_tools(connector: DataConnector):
    """Return native SDK schemas and handlers; the host owns tool grants/lifetime."""
    if not isinstance(connector, DataConnector):
        raise TypeError("data binding requires DataConnector")

    def status() -> dict[str, Any]:
        return {"configured": True, **connector.describe().to_dict()}

    async def query(
        dialect: str, expression: str, parameters: dict[str, Any] | None = None,
        projection: list[str] | None = None, limits: dict[str, Any] | None = None,
    ) -> types.CallToolResult:
        request = QueryRequest(
            dialect=dialect, expression=expression, parameters=parameters or {},
            projection=tuple(projection or ()),
            limits=replace(connector.describe().limits, **limits) if limits is not None else None,
        )
        result = await connector.query(request)
        payload = result.to_dict()
        if result.status != "success":
            payload["failures"] = _failures(result)
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=json.dumps(payload, allow_nan=False))],
            structuredContent=payload, isError=result.status != "success",
        )

    return TOOLS, {"data_status": status, "data_query": query}