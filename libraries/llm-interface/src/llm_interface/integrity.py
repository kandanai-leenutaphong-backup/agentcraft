from __future__ import annotations

import math
from typing import Any

from .errors import LlmError
from .runtime import ACTIVE_RUN


def embedding_indices(data: Any, count: int, dimensions: int | None = None) -> None:
    if not isinstance(data, list) or len(data) != count:
        raise LlmError("embedding_count_mismatch", category="failed")
    seen = set()
    width = dimensions
    for item in data:
        if not isinstance(item, dict):
            raise LlmError("invalid_embedding", category="failed")
        index = item.get("index")
        if type(index) is not int or not 0 <= index < count or index in seen:
            raise LlmError("embedding_index_mismatch", category="failed")
        seen.add(index)
        vector = item.get("embedding")
        if (not isinstance(vector, list) or not vector
                or any(type(value) not in (float, int) or not math.isfinite(value) for value in vector)):
            raise LlmError("invalid_embedding_vector", category="failed")
        width = len(vector) if width is None else width
        if len(vector) != width:
            raise LlmError("embedding_dimensions_mismatch", category="failed")


def finish_reason(result) -> str | None:
    reason = getattr(result, "finish_reason", None)
    return getattr(reason, "value", reason)


def completion_state(result) -> str:
    reason = finish_reason(result)
    if reason == "length":
        return "incomplete"
    if reason == "content_filter" or any(
        content.additional_properties.get("model_output_kind") == "refusal"
        for message in getattr(result, "messages", ()) for content in message.contents
    ):
        return "refused"
    return "tool_calls" if reason == "tool_calls" else "completed"


def check_response(result) -> None:
    raw = getattr(result, "raw_representation", None)
    status = getattr(raw, "status", None)
    if status in {"failed", "cancelled"}:
        raise LlmError("model_response_failed", category="failed")
    reason = finish_reason(result)
    if reason == "error":
        raise LlmError("model_response_failed", category="failed")
    if reason is None:
        raise LlmError("missing_terminal_event", category="interrupted", action="Partial output is not a completed response; inspect before retrying.")
    if reason == "length":
        if any(content.type == "function_call" for message in getattr(result, "messages", ()) for content in message.contents):
            raise LlmError("incomplete_tool_call", category="interrupted", action="No tool from this incomplete model call was executed.")


class StreamEvidence:
    def __init__(self) -> None:
        self.terminal = False
        self.failure = None

    def observe(self, update):
        run = ACTIVE_RUN.get()
        if run:
            run.native_events += 1
            if run.native_events > run.limits.max_events:
                self.failure = LlmError("native_event_limit", category="interrupted")
        raw = getattr(update, "raw_representation", None)
        event_type = getattr(raw, "type", "")
        if event_type in {"error", "response.failed"}:
            self.failure = LlmError("model_stream_failed", category="failed")
        if finish_reason(update) is not None:
            self.terminal = True
        return update

    def finalize(self, result):
        if self.failure:
            raise self.failure
        if not self.terminal:
            raise LlmError("missing_terminal_event", category="interrupted", action="The stream ended without completion evidence.")
        check_response(result)
        return result