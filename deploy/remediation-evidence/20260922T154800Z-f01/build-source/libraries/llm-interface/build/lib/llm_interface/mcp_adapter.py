"""Optional bounded text-chat and embedding tools for a fixed Connection.

Failures retain native ``error`` code/category with bounded field/action
diagnostics, plus sibling ``failure`` effect/retry metadata. The host stamps
capability_id, tool operation and run_id. Only identified local pre-dispatch
refusals prove effect=none; provider errors (even config/invalid responses) and
incomplete paid output remain unknown with no automatic replay. Native
rate_limit is mapped to common rate-limit only in the sibling metadata.
"""

from __future__ import annotations

import json
from typing import Any

from mcp import types

from llm_interface import Connection, LlmError, Message


TOOLS = [
    types.Tool(name="model_status", description="Describe the configured model and grants without inference.",
               inputSchema={"type": "object", "properties": {}, "additionalProperties": False}),
    types.Tool(name="model_chat", description="Request bounded text chat from the fixed model; no tool execution or storage.",
               inputSchema={"type": "object", "properties": {
                   "messages": {"type": "array", "minItems": 1, "maxItems": 128,
                                "items": {"type": "object", "properties": {
                                    "role": {"type": "string", "enum": ["system", "user", "assistant"]},
                                    "text": {"type": "string", "minLength": 1, "maxLength": 128000},
                                }, "required": ["role", "text"], "additionalProperties": False}},
                   "max_tokens": {"type": "integer", "minimum": 1},
                   "temperature": {"type": "number", "minimum": 0, "maximum": 2},
                   "top_p": {"type": "number", "minimum": 0, "maximum": 1},
               }, "required": ["messages"], "additionalProperties": False}),
    types.Tool(name="model_embed", description="Embed bounded text using the configured embedding deployment in verified input order.",
               inputSchema={"type": "object", "properties": {
                   "values": {"type": "array", "minItems": 1, "maxItems": 2048,
                              "items": {"type": "string", "minLength": 1, "maxLength": 128000}},
                   "dimensions": {"type": "integer", "minimum": 1},
               }, "required": ["values"], "additionalProperties": False}),
]


_PRE_DISPATCH = frozenset({
    "connection_closed", "model_calls_denied", "event_loop_changed",
    "invalid_messages", "empty_messages", "invalid_options", "invalid_stream",
    "binding_override_denied", "output_token_limit", "invalid_sampling_option",
    "input_limit", "invalid_embedding_inputs", "invalid_dimensions",
    "budget_exhausted", "model_budget_exhausted", "missing_run_authority",
    "native_target_refused", "native_input_limit", "native_model_refused", "retention_refused",
    "provider_extra_missing", "identity_extra_missing", "unsafe_debug_logging", "sensitive_telemetry_enabled",
})
_FIELDS = frozenset({
    "messages", "options", "max_tokens", "temperature", "top_p", "values", "dimensions",
    "timeout_seconds", "model_calls", "tool_calls", "max_model_calls", "max_tool_calls",
    "max_output_tokens", "max_input_bytes", "max_output_bytes", "max_concurrency",
})


def _failure(error: LlmError) -> types.CallToolResult:
    unsupported = error.category == "unsupported"
    before_dispatch = unsupported or error.code in _PRE_DISPATCH
    effect = "none" if before_dispatch else "unknown"
    retry = "never" if unsupported else "safe_after_correction" if before_dispatch else "unspecified"
    action = ("Use a supported model capability and configured deployment." if unsupported else
              "Correct the request or ask the host to review its model grant and bounds." if before_dispatch else
              "Inspect prior output and usage before another paid attempt; no automatic replay was made.")
    metadata = {**error.metadata(), "field": error.field if error.field in _FIELDS else None, "action": action}
    payload = {"error": metadata, "failure": {
        **metadata, "category": "rate-limit" if error.category == "rate_limit" else error.category,
        "effect": effect, "retry": retry,
    }}
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=json.dumps(payload))],
        structuredContent=payload, isError=True,
    )


def bind_tools(connection: Connection):
    """Return native SDK schemas and handlers; never create clients or grant calls."""
    if not isinstance(connection, Connection):
        raise TypeError("model binding requires Connection")

    def status() -> dict[str, Any]:
        return {"configured": True, **connection.describe()}

    async def chat(messages: list[dict[str, str]], max_tokens: int | None = None,
                   temperature: float | None = None, top_p: float | None = None):
        options = {key: value for key, value in {
            "max_tokens": max_tokens, "temperature": temperature, "top_p": top_p,
        }.items() if value is not None}
        try:
            response = await connection.chat.get_response(
                [Message(message["role"], [message["text"]]) for message in messages], options=options,
            )
            return response.to_dict()
        except LlmError as error:
            return _failure(error)

    async def embed(values: list[str], dimensions: int | None = None):
        try:
            result = await connection.embeddings.get_embeddings(
                values, options={"dimensions": dimensions} if dimensions is not None else None,
            )
            return {"vectors": [item.vector for item in result], "usage": result.usage,
                    "metadata": result.additional_properties}
        except LlmError as error:
            return _failure(error)

    return TOOLS, {"model_status": status, "model_chat": chat, "model_embed": embed}