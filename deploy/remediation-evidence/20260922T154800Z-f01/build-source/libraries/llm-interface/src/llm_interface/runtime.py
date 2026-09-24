from __future__ import annotations

import asyncio
import contextvars
import copy
import inspect
import json
import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

from agentcraft_core import ExecutionContext, FrameworkError, current_execution
from agent_framework import Message, ResponseStream

from .config import Limits
from .errors import LlmError


def json_size(value: Any) -> int:
    try:
        return len(json.dumps(value, ensure_ascii=True, allow_nan=False).encode())
    except (TypeError, ValueError, RecursionError, OverflowError):
        raise LlmError("non_json_value", action="Use bounded JSON-compatible content.") from None


def safe_error(error: Exception) -> LlmError:
    current: BaseException | None = error
    status = None
    for _depth in range(8):
        if isinstance(current, FrameworkError):
            return LlmError(current.failure.code, category=current.failure.category,
                            action=current.failure.action, field=current.failure.field)
        if isinstance(current, LlmError):
            return LlmError(current.code, category=current.category, action=current.action, field=current.field)
        status = getattr(current, "status_code", status)
        if type(current).__name__ in {"ClientAuthenticationError", "CredentialUnavailableError"}:
            return LlmError("credential_unavailable", category="auth", action="Check the explicitly selected Azure Identity credential.")
        if type(current).__name__ == "ValidationError":
            return LlmError("structured_output_invalid", category="failed", action="The model response did not satisfy the requested schema.")
        current = getattr(current, "__cause__", None)
        if current is None:
            break
    if status in (401, 403):
        return LlmError("provider_access_denied", category="auth", action="Check the selected identity, audience and data-plane role.")
    if status == 404:
        return LlmError("deployment_not_found", category="config", action="Check the configured endpoint and deployment name.")
    if status == 429:
        return LlmError("provider_throttled", category="rate_limit", action="Respect provider limits; no automatic replay was made.")
    if isinstance(error, TimeoutError) or "Timeout" in type(error).__name__:
        return LlmError("deadline_exceeded", category="interrupted", action="Inspect partial output and tool effects before another run.")
    if status in (400, 422):
        return LlmError("provider_rejected_request", category="invalid", action="Check model capabilities and supported options.")
    return LlmError("provider_failure", category="failed", action="Check provider health and request metadata; do not blindly replay tool effects.")


def messages_snapshot(value: Any) -> list[Message]:
    if isinstance(value, str):
        messages = [Message("user", [value])]
    elif isinstance(value, Message):
        messages = [value]
    elif isinstance(value, (tuple, list)) and all(isinstance(item, Message) for item in value):
        messages = list(value)
    else:
        raise LlmError("invalid_messages", action="Supply text, a Message, or a list of Message values.")
    if not messages:
        raise LlmError("empty_messages")
    return copy.deepcopy(messages)


def options_snapshot(value: Any) -> dict:
    if value is None:
        return {}
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise LlmError("invalid_options")
    return copy.deepcopy(dict(value))


@dataclass
class RunState:
    limits: Limits
    principal: str = "operator"
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    started: float = field(default_factory=time.monotonic)
    model_calls: int = 0
    tool_calls: int = 0
    wire_bytes: int = 0
    native_events: int = 0
    output_bytes: int = 0
    event_count: int = 0
    status: str = "running"
    model_status: str | None = None
    fault: LlmError | None = None
    emit: Any = None
    tools: dict = field(default_factory=dict)
    tool_call_ids: set[str] = field(default_factory=set)
    tool_requests: dict = field(default_factory=dict)
    tool_results: dict = field(default_factory=dict)
    execution: ExecutionContext | None = field(default_factory=current_execution)

    def __post_init__(self) -> None:
        if self.execution is not None:
            self.run_id = self.execution.run_id

    def model_attempt(self) -> None:
        if self.fault:
            raise self.fault
        if self.model_calls >= self.limits.max_model_calls:
            raise LlmError("model_budget_exhausted", category="denied", action="Ask the operator to review the per-run model budget.")
        self.reserve("model_calls")
        self.model_calls += 1

    def reserve(self, unit: str) -> None:
        if self.execution is not None:
            try:
                self.execution.remaining()
                self.execution.budget.reserve(unit)
            except FrameworkError as error:
                raise safe_error(error) from None

    def mark_unknown(self) -> None:
        if self.execution is not None and self.model_calls:
            self.execution.budget.mark_unknown("model_calls")

    def output(self, value: Any) -> None:
        self.output_bytes += json_size(value)
        if self.output_bytes > self.limits.max_output_bytes:
            raise LlmError("output_limit", category="interrupted", action="Use a smaller response or tool result.")

    def metadata(self) -> dict:
        return {"run_id": self.run_id, "model_calls": self.model_calls, "tool_calls": self.tool_calls,
                "status": self.status, "elapsed_ms": round((time.monotonic() - self.started) * 1000, 3),
                "persistence": "not_configured"}


ACTIVE_RUN: contextvars.ContextVar[RunState | None] = contextvars.ContextVar("llm_interface_run", default=None)
ACTIVE_TOOL: contextvars.ContextVar[str | None] = contextvars.ContextVar("llm_interface_tool", default=None)


Update = TypeVar("Update")
Result = TypeVar("Result")


class ManagedStream(ResponseStream[Update, Result], Generic[Update, Result]):
    """Framework stream with explicit async close and bounded producer lifetime."""
    def __init__(self, produce, *, limits: Limits) -> None:
        self._queue = asyncio.Queue(maxsize=16)
        self._producer = produce
        self._limits = limits
        self._task = None
        self._result = None
        self._failure: BaseException | None = None
        self._finished = False
        self._closed_locally = False
        self._iterator_source = self._iterate()
        super().__init__(self._iterator_source, finalizer=self._finalize)

    async def _produce(self) -> None:
        try:
            async with asyncio.timeout(self._limits.timeout_seconds):
                self._result = await self._producer(self._emit)
        except asyncio.CancelledError:
            self._failure = asyncio.CancelledError()
            raise
        except Exception as error:
            self._failure = safe_error(error)
        finally:
            self._finished = True

    async def _emit(self, update) -> None:
        await self._queue.put(update)

    async def _iterate(self):
        if self._closed_locally:
            raise LlmError("stream_closed", category="interrupted")
        self._task = asyncio.create_task(self._produce())
        try:
            while True:
                if not self._queue.empty():
                    yield self._queue.get_nowait()
                    continue
                if self._task.done():
                    break
                receive = asyncio.create_task(self._queue.get())
                try:
                    done, _pending = await asyncio.wait((receive, self._task), return_when=asyncio.FIRST_COMPLETED)
                    if receive in done:
                        yield receive.result()
                finally:
                    if not receive.done():
                        receive.cancel()
                        try:
                            await receive
                        except asyncio.CancelledError:
                            pass
            if self._failure:
                raise self._failure
        finally:
            if not self._task.done():
                self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    def _finalize(self, updates):
        if self._failure:
            raise self._failure
        if self._closed_locally and not self._finished:
            raise LlmError("stream_closed", category="interrupted")
        return self._result

    async def get_final_response(self) -> Result:
        if self._failure:
            raise self._failure
        if self._closed_locally and not self._finished:
            raise LlmError("stream_closed", category="interrupted")
        return await super().get_final_response()

    async def aclose(self) -> None:
        if self._closed_locally:
            return
        self._closed_locally = True
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if not self._iterator_source.ag_running:
            await self._iterator_source.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.aclose()


async def close_owned(resources) -> None:
    seen = set()
    for resource in reversed(resources):
        if id(resource) in seen:
            continue
        seen.add(id(resource))
        closer = getattr(resource, "aclose", None) or getattr(resource, "close", None)
        if closer:
            result = closer()
            if inspect.isawaitable(result):
                await result


async def settle_stream(source) -> None:
    run = ACTIVE_RUN.get()
    if run is not None and run.fault is None:
        run.fault = LlmError("stream_abandoned", category="interrupted")
    try:
        async with asyncio.timeout(1):
            async for _update in source:
                pass
    except (Exception, asyncio.CancelledError):
        pass