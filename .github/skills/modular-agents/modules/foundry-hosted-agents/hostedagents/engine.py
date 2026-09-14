"""Bounded tool/model orchestration adapted from hcagent.runtime.main."""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass
from typing import Any, AsyncIterator, Protocol

from toolshape import turn

from .definition import Definition, ToolRegistry
from .policy import RuntimePolicy

TERMINAL_EVENTS = frozenset({"done", "error", "aborted"})
STREAM_EVENTS = (
    "token", "tool_call_start", "tool_call_delta", "tool_call_end", "tool_result",
    "citation", "metadata", "rate_limited", "keepalive", "done", "error", "aborted",
)


class InvocationRefused(ValueError):
    """A denied or malformed operation never reaches its collaborator."""

    def __init__(self, reason: str, *, status: int = 403) -> None:
        super().__init__(reason)
        self.status = status


class ChatModel(Protocol):
    async def complete(
        self, *, model: str, messages: list[dict[str, Any]],
        tools: list[dict[str, Any]], max_tokens: int,
    ) -> dict[str, Any]: ...


@dataclass
class _Turn:
    owner: str
    cancel: asyncio.Event
    task: asyncio.Task[Any] | None = None
    result: dict[str, Any] | None = None


class AgentRuntime:
    """One process/session; authorization, bounds and result ownership live here."""

    def __init__(
        self, definition: Definition, policy: RuntimePolicy, *,
        model: ChatModel | None = None, artifact_id: str = "local",
    ) -> None:
        if set(policy.allowed_tools) - set(definition.tools.names):
            raise ValueError("policy grants an unknown tool")
        if policy.allow_model and model is None:
            raise ValueError("model calls were granted but no model client was supplied")
        self.definition = definition
        self.policy = policy
        self.tools = ToolRegistry(definition.spec.tools, max_result_bytes=policy.max_result_bytes)
        self.model = model
        self.artifact_id = artifact_id
        self.started = time.monotonic()
        self._turns: dict[str, _Turn] = {}

    def status(self) -> dict[str, Any]:
        return {
            "ok": True, "agent": self.definition.spec.agent_id, "artifact_id": self.artifact_id,
            "model": self.definition.spec.model, "tools": list(self.tools.names),
            "policy": self.policy.model_dump(mode="json"),
            "uptime_seconds": round(time.monotonic() - self.started, 3),
            "active_turns": sum(record.result is None for record in self._turns.values()),
        }

    def authorize_tool(self, name: str) -> None:
        if name not in self.policy.allowed_tools:
            raise InvocationRefused("tool execution is not granted by operator policy")

    async def call(self, name: str, arguments: Any, *, principal: str) -> dict[str, Any]:
        if not principal:
            raise InvocationRefused("authenticated principal required", status=401)
        self.authorize_tool(name)
        async with asyncio.timeout(self.policy.turn_timeout_seconds):
            with turn(run_id=uuid.uuid4().hex):
                return await self.tools.invoke(name, arguments)

    def prepare_chat(self, message: str, *, principal: str, turn_id: str = "") -> tuple[str, _Turn]:
        if not principal:
            raise InvocationRefused("authenticated principal required", status=401)
        if not self.policy.allow_model:
            raise InvocationRefused("model calls are not granted by operator policy")
        if not isinstance(message, str) or not message.strip() or len(message.encode()) > self.policy.max_message_bytes:
            raise InvocationRefused("message is empty or exceeds the configured byte limit", status=400)
        import re

        if turn_id and not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", turn_id):
            raise InvocationRefused("invalid turn_id", status=400)
        turn_id = turn_id or uuid.uuid4().hex
        if turn_id in self._turns:
            raise InvocationRefused("turn_id already exists", status=409)
        if sum(record.result is None for record in self._turns.values()) >= self.policy.max_concurrent_turns:
            raise InvocationRefused("concurrent turn limit reached", status=429)
        while len(self._turns) >= 128:
            completed = next((key for key, record in self._turns.items() if record.result is not None), None)
            if completed is None:
                raise InvocationRefused("turn capacity reached", status=429)
            del self._turns[completed]
        record = _Turn(owner=principal, cancel=asyncio.Event())
        self._turns[turn_id] = record
        return turn_id, record

    async def _events(self, message: str, record: _Turn) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        messages = [
            {"role": "system", "content": self.definition.spec.instructions},
            {"role": "user", "content": message},
        ]
        schemas = [schema for schema in self.tools.schemas if schema["function"]["name"] in self.policy.allowed_tools]
        calls_used = 0
        assert self.model is not None
        for round_index in range(self.policy.max_tool_rounds):
            if record.cancel.is_set():
                yield "aborted", {"reason": "cancelled"}
                return
            reply = await self.model.complete(
                model=self.definition.spec.model, messages=messages, tools=schemas,
                max_tokens=self.policy.max_output_tokens,
            )
            content = reply.get("content") or ""
            if not isinstance(content, str) or len(content.encode()) > self.policy.max_result_bytes:
                yield "error", {"error": "model output exceeds the configured byte limit"}
                return
            if content:
                yield "token", {"token": content}
            calls = reply.get("tool_calls") or []
            if not isinstance(calls, list) or calls_used + len(calls) > self.policy.max_tool_calls:
                yield "error", {"error": "tool call limit reached"}
                return
            if not calls:
                yield "done", {"finish": "stop", "rounds": round_index + 1}
                return
            messages.append({"role": "assistant", "content": content or None, "tool_calls": calls})
            for call in calls:
                calls_used += 1
                function = call.get("function") or {}
                name = function.get("name", "")
                call_id = str(call.get("id") or uuid.uuid4().hex)
                raw = function.get("arguments", "{}")
                if not isinstance(raw, str) or len(raw.encode()) > self.policy.max_message_bytes:
                    arguments = None
                else:
                    try:
                        arguments = json.loads(raw)
                    except ValueError:
                        arguments = None
                yield "tool_call_start", {"id": call_id, "name": name}
                yield "tool_call_end", {"id": call_id}
                if record.cancel.is_set():
                    yield "aborted", {"reason": "cancelled"}
                    return
                if name not in self.policy.allowed_tools:
                    result = {"refused": True, "parameter": "tool", "accepted": list(self.policy.allowed_tools)}
                else:
                    result = await self.tools.invoke(name, arguments)
                serialized = json.dumps(result)
                yield "tool_result", {"id": call_id, "name": name, "result": serialized}
                messages.append({"role": "tool", "tool_call_id": call_id, "content": serialized})
        yield "error", {"error": "tool round limit reached"}

    async def chat_events(
        self, message: str, *, principal: str, turn_id: str = "", prepared: tuple[str, _Turn] | None = None,
    ) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        turn_id, record = prepared or self.prepare_chat(message, principal=principal, turn_id=turn_id)
        if record.owner != principal or self._turns.get(turn_id) is not record:
            raise InvocationRefused("turn not found", status=404)
        queue: asyncio.Queue[tuple[str, dict[str, Any]] | None] = asyncio.Queue(maxsize=16)
        delivery_closed = asyncio.Event()

        async def produce() -> None:
            try:
                async with asyncio.timeout(self.policy.turn_timeout_seconds):
                    with turn(run_id=turn_id):
                        async for item in self._events(message, record):
                            await queue.put(item)
            except asyncio.CancelledError:
                if not delivery_closed.is_set():
                    await queue.put(("aborted", {"reason": "cancelled"}))
            except TimeoutError:
                await queue.put(("error", {"error": "turn timeout"}))
            except Exception as failure:
                await queue.put(("error", {"error": f"model or tool failed ({type(failure).__name__})"}))
            finally:
                if not delivery_closed.is_set():
                    await queue.put(None)

        worker = asyncio.create_task(produce())
        record.task = worker
        answer: list[str] = []
        events: list[dict[str, Any]] = []
        terminal = "aborted"
        total_bytes = 0
        try:
            yield "metadata", {"turn_id": turn_id, "artifact_id": self.artifact_id, "model": self.definition.spec.model}
            while True:
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=15)
                except TimeoutError:
                    yield "keepalive", {}
                    continue
                if item is None:
                    break
                event, payload = item
                total_bytes += len(json.dumps(payload).encode())
                if total_bytes > 1_000_000:
                    event, payload = "error", {"error": "turn result byte limit reached"}
                if event == "token":
                    answer.append(payload["token"])
                events.append({"event": event, **payload})
                yield event, payload
                if event in TERMINAL_EVENTS:
                    terminal = event
                    break
        finally:
            delivery_closed.set()
            record.cancel.set()
            worker.cancel()
            try:
                await worker
            except asyncio.CancelledError:
                pass
            record.result = {"turn_id": turn_id, "status": terminal, "answer": "".join(answer), "events": events}
            record.task = None

    def result(self, turn_id: str, *, principal: str) -> dict[str, Any]:
        record = self._turns.get(turn_id)
        if record is None or record.owner != principal:
            raise InvocationRefused("turn not found", status=404)
        if record.result is None:
            return {"turn_id": turn_id, "status": "running"}
        return json.loads(json.dumps(record.result))

    def abort(self, turn_id: str, *, principal: str) -> dict[str, Any]:
        record = self._turns.get(turn_id)
        if record is None or record.owner != principal:
            raise InvocationRefused("turn not found", status=404)
        record.cancel.set()
        if record.task is not None:
            record.task.cancel()
        return {"turn_id": turn_id, "aborted": record.result is None}