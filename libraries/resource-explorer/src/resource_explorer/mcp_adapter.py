"""Optional MCP adapter for one host-declared inventory, never estate discovery.

Refusals/read failures retain native models/statuses plus sibling ``failure``.
Invalid-node and disabled-source models have no status: their literal error is
the code. Other codes use the native call status, never provider detail text.
Only diagnostic ``error`` prose is replaced; rows, provenance, child statuses
and all other authorized output survive. Reads have no mutation effect; the
host stamps capability_id, tool operation and run_id. Empty remains success.
"""

from __future__ import annotations

import json

from mcp import types

from resource_explorer import (
    DEFAULT_PREVIEW_ROWS, MAX_PREVIEW_ROWS, MAX_TOKEN_CHARS, ROOT_ID,
    InvalidNode, InvalidNodeError, InventoryService, SourceDisabled,
    SourceDisabledError, parse_selection,
)


TOOLS = [
    types.Tool(name="inventory_status", description="Describe the declared inventory without probing sources.",
               inputSchema={"type": "object", "properties": {}, "additionalProperties": False}),
    types.Tool(name="inventory_tree", description="Expand a declared inventory node; no live probes or estate search.",
               inputSchema={"type": "object", "properties": {
                   "node": {"type": "string", "minLength": 1, "maxLength": MAX_TOKEN_CHARS},
               }, "additionalProperties": False}),
    types.Tool(name="inventory_content", description="Read bounded content from a declared source node, never a caller URL.",
               inputSchema={"type": "object", "properties": {
                   "node": {"type": "string", "minLength": 1, "maxLength": MAX_TOKEN_CHARS},
                   "limit": {"type": "integer", "minimum": 1, "maximum": MAX_PREVIEW_ROWS},
               }, "required": ["node"], "additionalProperties": False}),
]


def _result(response, *, failed: bool = False) -> types.CallToolResult:
    payload = response.model_dump(mode="json", by_alias=True)
    for child in payload.get("children", ()):
        if child.get("error"):
            child["error"] = child["status"]
    if failed:
        code = response.error if isinstance(response, (InvalidNodeError, SourceDisabledError)) else response.status
        category = {"invalid_node": "invalid", "source_disabled": "denied", "forbidden": "denied",
                    "unconfigured": "config", "unreachable": "unavailable", "unavailable": "unavailable"}[code]
        correction = category in {"invalid", "denied", "config"}
        if payload.get("error"):
            payload["error"] = code
        payload["failure"] = {
            "code": code, "category": category,
            "field": "node" if code in {"invalid_node", "source_disabled"} else None,
            "effect": "none", "retry": "safe_after_correction" if correction else "unspecified",
            "action": "Review the declared source, selection and host access policy." if correction else
                      "Check the configured source reader and its availability before another read.",
        }
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=json.dumps(payload, allow_nan=False))],
        structuredContent=payload, isError=failed,
    )


def bind_tools(service: InventoryService):
    """Borrow a pre-authorized service; its host still owns probe lifetimes."""
    if not isinstance(service, InventoryService):
        raise TypeError("inventory binding requires InventoryService")
    selection = parse_selection(None, allowed=service.registry.source_ids())

    def status():
        return {"configured": True, "availability": "unverified", "estate_search": False,
                "use_case_count": len(service.registry.use_cases),
                "source_count": len(service.registry.source_ids()), "max_preview_rows": MAX_PREVIEW_ROWS}

    async def tree(node: str = ROOT_ID):
        try:
            response = await service.tree(node, selection)
            return _result(response, failed=response.status not in {"ok", "empty"})
        except InvalidNode:
            return _result(InvalidNodeError(), failed=True)

    async def content(node: str, limit: int = DEFAULT_PREVIEW_ROWS):
        try:
            response = await service.content(node, selection, limit=limit)
            return _result(response, failed=response.status not in {"ok", "empty"})
        except InvalidNode:
            return _result(InvalidNodeError(), failed=True)
        except SourceDisabled:
            return _result(SourceDisabledError(), failed=True)

    return TOOLS, {"inventory_status": status, "inventory_tree": tree, "inventory_content": content}