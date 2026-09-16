"""Legacy Responses tool iteration with caller-owned tools and wire metadata."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from typing import Any


async def stream_tool_turn(*, events: Callable[..., AsyncIterator[Any]],
                           execute_tool: Callable[[str, dict[str, Any]], Any],
                           input: Any, model: str, instructions: str,
                           tools: Sequence[dict[str, Any]], reasoning: Mapping[str, Any],
                           parallel_tool_calls: bool, max_output_tokens: int,
                           max_tool_iterations: int, previous_response_id: str | None = None,
                           metadata: Mapping[str, Any] | None = None,
                           tool_metadata: Mapping[str, Mapping[str, Any]] | None = None,
                           result_metadata: Mapping[str, Any] | None = None,
                           ) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    if (type(max_tool_iterations) is not int or max_tool_iterations < 1
            or type(max_output_tokens) is not int or max_output_tokens < 1):
        raise ValueError("positive_model_and_iteration_limits_required")
    labels = tool_metadata or {}

    def detail(name):
        return {"display_name": name, "fallback": False, **labels.get(name, {})}

    next_input = input
    response_id = previous_response_id
    for iteration in range(max_tool_iterations):
        yield "status", {"phase": "model", "label": "Connecting to model\u2026" if iteration == 0
                         else "Reasoning from tool evidence\u2026"}
        response = None
        incomplete = ""
        item_to_call: dict[str, str] = {}
        started_calls: set[str] = set()
        stream = events(model=model, instructions=instructions, input=next_input,
                        previous_response_id=response_id, tools=list(tools), reasoning=dict(reasoning),
                        parallel_tool_calls=parallel_tool_calls, max_output_tokens=max_output_tokens)
        try:
            async for event in stream:
                event_type = event.type
                if event_type == "response.created":
                    response_id = event.response.id
                    yield "metadata", {"response_id": response_id, "model": model, **(metadata or {})}
                elif event_type == "response.output_item.added" and event.item.type == "function_call":
                    call_id = event.item.call_id
                    item_to_call[event.item.id] = call_id
                    started_calls.add(call_id)
                    yield "tool_call_start", {"id": call_id, "name": event.item.name, **detail(event.item.name)}
                elif event_type == "response.function_call_arguments.delta":
                    yield "tool_call_delta", {"id": item_to_call.get(event.item_id, event.item_id),
                                               "arguments_delta": event.delta}
                elif event_type == "response.function_call_arguments.done":
                    yield "tool_call_end", {"id": item_to_call.get(event.item_id, event.item_id),
                        "name": event.name, "arguments": json.loads(event.arguments or "{}"), **detail(event.name)}
                elif event_type == "response.output_text.delta":
                    yield "token", {"token": event.delta}
                elif event_type == "response.reasoning_summary_part.added":
                    yield "reasoning_start", {"id": f"{event.item_id}:{event.summary_index}"}
                elif event_type == "response.reasoning_summary_text.delta":
                    yield "reasoning_delta", {"id": f"{event.item_id}:{event.summary_index}", "delta": event.delta}
                elif event_type == "response.reasoning_summary_text.done":
                    yield "reasoning_end", {"id": f"{event.item_id}:{event.summary_index}", "text": event.text}
                elif event_type in {"response.completed", "response.incomplete"}:
                    response = event.response
                    response_id = response.id
                    if event_type == "response.incomplete":
                        incomplete = str(getattr(getattr(response, "incomplete_details", None), "reason", "") or "unknown")
                elif event_type in {"response.failed", "error"}:
                    raise RuntimeError(f"model stream ended with {event_type}")
        finally:
            close = getattr(stream, "aclose", None)
            if close is not None:
                await close()
        if response is None:
            raise RuntimeError("model stream ended without response.completed")
        calls = [item for item in response.output if item.type == "function_call"]
        if not calls:
            if incomplete:
                yield "status", {"phase": "model", "label": f"Answer truncated at the output cap ({incomplete})."}
            yield "done", {"response_id": response.id, "incomplete": incomplete}
            return

        async def invoke(call):
            arguments = json.loads(call.arguments or "{}")
            try:
                result = await asyncio.to_thread(execute_tool, call.name, arguments)
            except Exception as error:
                result = {"error": type(error).__name__, "detail": str(error)}
            return call, result, bool(detail(call.name)["fallback"])

        for call in calls:
            arguments = json.loads(call.arguments or "{}")
            fallback = bool(detail(call.name)["fallback"])
            if call.call_id not in started_calls:
                yield "tool_call_start", {"id": call.call_id, "name": call.name, **detail(call.name)}
                yield "tool_call_end", {"id": call.call_id, "name": call.name,
                                       "arguments": arguments, "fallback": fallback}
            yield "status", {"phase": "tool", "label": f"Running {call.name}\u2026"}
        outputs = []
        pending = [asyncio.create_task(invoke(call)) for call in calls]
        try:
            for completed in asyncio.as_completed(pending):
                call, result, fallback = await completed
                yield "tool_result", {"id": call.call_id, "name": call.name, "result": result,
                                      "fallback": fallback, **(result_metadata or {})}
                outputs.append({"type": "function_call_output", "call_id": call.call_id,
                                "output": json.dumps(result, default=str)})
        finally:
            await asyncio.gather(*pending, return_exceptions=True)
        next_input = outputs
    yield "error", {"error": f"agent exceeded {max_tool_iterations} tool iterations"}