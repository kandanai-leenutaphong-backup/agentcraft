from __future__ import annotations

import asyncio
import copy
import hashlib
import inspect
import json
from collections.abc import Awaitable, Mapping, Sequence
from dataclasses import dataclass, field
from functools import wraps
from typing import Any, Literal, overload

from agent_framework import Agent, AgentResponse, AgentSession, FunctionTool, InMemoryHistoryProvider, Message, tool

from .connection import CallGuard
from .errors import LlmError
from .runtime import ACTIVE_RUN, ACTIVE_TOOL, ManagedStream, json_size, messages_snapshot, options_snapshot, safe_error, settle_stream


@dataclass(frozen=True)
class RunEvent:
    kind: str
    run_id: str
    sequence: int
    data: dict = field(repr=False)
    schema_version: int = 1

    @property
    def text(self) -> str:
        return self.data.get("text", "") if self.kind == "text.delta" else ""

    def to_dict(self) -> dict:
        return {"schema_version": self.schema_version, "kind": self.kind, "run_id": self.run_id,
                "sequence": self.sequence, "data": copy.deepcopy(self.data)}


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: dict = field(repr=False)
    principal: str = "operator"
    run_id: str = ""
    call_id: str = ""


class Session:
    """In-memory owner-bound history and the last completed result, not a durable store."""
    def __init__(self, principal: str, binding: str) -> None:
        self.principal = principal
        self.binding = binding
        self._native = AgentSession()
        self._lock = asyncio.Lock()
        self._result = None
        self._tainted = False

    @property
    def id(self) -> str:
        return self._native.session_id

    def result(self, *, principal: str = "operator"):
        if principal != self.principal:
            raise LlmError("session_not_found", category="denied")
        return copy.deepcopy(self._result)


async def report_progress(data: dict) -> None:
    """Emit a bounded progress record from an executing async tool during a streamed run."""
    run = ACTIVE_RUN.get()
    if run is None or run.emit is None or ACTIVE_TOOL.get() is None:
        raise LlmError("progress_outside_stream", category="config")
    if not isinstance(data, dict) or json_size(data) > run.limits.max_tool_result_bytes:
        raise LlmError("progress_limit")
    await run.emit("tool.progress", {"call_id": ACTIVE_TOOL.get(), "progress": copy.deepcopy(data)})


class AgentBinding:
    """Reusable definition; each run creates isolated framework execution state."""
    def __init__(self, connection, *, instructions: str, tools=(), name: str = "assistant",
                 authorize_tool=None, required_capabilities=()) -> None:
        connection._check_open()
        if not isinstance(instructions, str) or not instructions.strip():
            raise LlmError("instructions_required", category="config")
        if not isinstance(name, str) or not name or len(name) > 128:
            raise LlmError("invalid_agent_name", category="config")
        self.connection = connection
        self.instructions = instructions
        self.name = name
        self.authorize_tool = authorize_tool
        if authorize_tool is not None and not callable(authorize_tool):
            raise LlmError("invalid_tool_authorizer", category="config")
        for capability in required_capabilities:
            if not isinstance(capability, str) or not getattr(connection.capabilities, capability, False):
                raise LlmError("required_capability_unsupported", category="unsupported")
        self._tools = []
        names = set()
        for function in tools:
            if not isinstance(function, FunctionTool) and not callable(function):
                raise LlmError("local_function_required", category="unsupported")
            candidate = function if isinstance(function, FunctionTool) else tool(function)
            if candidate.name in names or candidate.name not in connection.policy.allowed_tools:
                raise LlmError("tool_not_granted", category="denied", action="List each registered tool name in connect(allowed_tools=...).")
            if candidate.approval_mode not in (None, "never_require"):
                raise LlmError("interactive_approval_unsupported", category="unsupported", action="Use the explicit host tool authorizer; interactive approval is not implemented.")
            if not callable(candidate.func):
                raise LlmError("callable_tool_required", category="config")
            names.add(candidate.name)
            self._tools.append(candidate)
        if self._tools and not connection.capabilities.tools:
            raise LlmError("tools_unsupported", category="unsupported")
        self.binding = hashlib.sha256(json.dumps([connection.config.digest, connection.policy.digest,
            instructions, name, [(candidate.name, candidate.parameters()) for candidate in self._tools]], sort_keys=True).encode()).hexdigest()

    def create_session(self, *, principal: str = "operator") -> Session:
        self._principal(principal)
        return Session(principal, self.binding)

    @staticmethod
    def _principal(principal):
        if not isinstance(principal, str) or not principal.strip() or len(principal) > 256:
            raise LlmError("principal_required", category="denied")

    def _bind_tools(self):
        bound = []
        for candidate in self._tools:
            def wrap(original):
                @wraps(original.func)
                async def invoke(**arguments):
                    run = ACTIVE_RUN.get()
                    if run is None:
                        raise LlmError("missing_run_authority", category="denied")
                    failure = None
                    request_key = (original.name, json.dumps(arguments, sort_keys=True))
                    requested = run.tool_requests.get(request_key, [])
                    if not requested:
                        raise LlmError("unverified_tool_call", category="denied")
                    call_id = requested.pop(0)
                    context_token = ACTIVE_TOOL.set(call_id)
                    try:
                        if run.fault:
                            raise run.fault
                        if self.authorize_tool:
                            allowed = self.authorize_tool(ToolCall(original.name, copy.deepcopy(arguments), run.principal, run.run_id, call_id))
                            if inspect.isawaitable(allowed):
                                allowed = await allowed
                            if allowed is not True:
                                raise LlmError("tool_authorization_denied", category="denied")
                        if run.fault:
                            raise run.fault
                        if run.tool_calls >= run.limits.max_tool_calls:
                            raise LlmError("tool_budget_exhausted", category="denied")
                        run.tool_calls += 1
                        if run.emit:
                            await run.emit("tool.started", {"name": original.name, "call_id": call_id})
                        if inspect.iscoroutinefunction(original.func):
                            result = await original.func(**arguments)
                        else:
                            result = await asyncio.to_thread(original.func, **arguments)
                            if inspect.isawaitable(result):
                                result = await result
                        if json_size(result) > run.limits.max_tool_result_bytes:
                            raise LlmError("tool_result_limit", category="failed")
                        run.tool_results[call_id] = copy.deepcopy(result)
                        return result
                    except asyncio.CancelledError:
                        raise
                    except Exception as error:
                        failure = error if isinstance(error, LlmError) else LlmError("tool_failed", category="failed")
                        run.fault = failure
                        if run.emit:
                            await run.emit("tool.failed", {"name": original.name, "call_id": call_id, **failure.metadata()})
                    finally:
                        ACTIVE_TOOL.reset(context_token)
                    raise failure
                return invoke
            bound.append(FunctionTool(name=candidate.name, description=candidate.description, func=wrap(candidate),
                                      input_model=candidate.input_model, approval_mode="never_require"))
        return bound

    @overload
    def run(self, messages: str | Message | Sequence[Message], *, session: Session | None = None,
            principal: str = "operator", stream: Literal[False] = False,
            options: Mapping[str, Any] | None = None) -> Awaitable[AgentResponse]: ...

    @overload
    def run(self, messages: str | Message | Sequence[Message], *, session: Session | None = None,
            principal: str = "operator", stream: Literal[True],
            options: Mapping[str, Any] | None = None) -> ManagedStream[RunEvent, AgentResponse]: ...

    def run(self, messages, *, session: Session | None = None, principal: str = "operator", stream: bool = False, options=None):
        """Run the native tool loop; optionally stream portable events and read the final result.

        principal comes from trusted host authentication, never directly from request JSON.
        Omit session for a fresh one-turn conversation.
        """
        self._principal(principal)
        self.connection._check_open()
        self.connection._grant()
        if type(stream) is not bool:
            raise LlmError("invalid_stream")
        messages = messages_snapshot(messages)
        options = self.connection._validate(messages, options_snapshot(options), stream=stream)
        if options.get("tools"):
            raise LlmError("run_tool_override_denied", category="denied")
        session = session if session is not None else self.create_session(principal=principal)
        if not isinstance(session, Session) or session.principal != principal:
            raise LlmError("session_not_found", category="denied")
        if session.binding != self.binding:
            raise LlmError("session_binding_changed", category="denied", action="Create a fresh session for the new agent or model connection.")
        if session._tainted:
            raise LlmError("session_interrupted", category="interrupted", action="Inspect prior tool effects and start a fresh session.")

        async def produce(emit):
            run = ACTIVE_RUN.get()

            async def event(kind, data):
                run.event_count += 1
                if run.event_count > run.limits.max_events:
                    raise LlmError("event_limit", category="interrupted")
                run.output(data)
                await emit(RunEvent(kind, run.run_id, run.event_count, copy.deepcopy(data)))

            run.emit = event if stream else None
            async with session._lock:
                if session._tainted:
                    raise LlmError("session_interrupted", category="interrupted")
                async with self.connection._slot():
                    bound = self._bind_tools()
                    run.tools = {candidate.name: candidate for candidate in bound}
                    client = self.connection._clients().chat_factory([CallGuard(self.connection)], True)
                    agent = Agent(client=client, instructions=self.instructions, name=self.name, tools=bound,
                                  default_options=options, context_providers=[InMemoryHistoryProvider(source_id="llm-interface")])
                    failure = None
                    source = None
                    finished = False
                    try:
                        if stream:
                            await event("run.started", {"agent": self.name, "session_id": session.id})
                            source = agent.run(messages, session=session._native, stream=True)
                            async for update in source:
                                for content in update.contents:
                                    if content.type == "text":
                                        await event("text.delta", {"text": content.text or ""})
                                    elif content.type == "text_reasoning":
                                        await event("reasoning.summary.delta", {"text": content.text or "", "id": content.id})
                                    elif content.type == "function_call":
                                        await event("tool.call.delta", {"call_id": content.call_id, "name": content.name,
                                                                       "arguments": content.arguments})
                                    elif content.type == "function_result":
                                        await event("tool.result", {"call_id": content.call_id,
                                                    "result": run.tool_results.get(content.call_id, content.result)})
                                    elif content.type == "usage":
                                        await event("usage", dict(content.usage_details or {}))
                            result = await source.get_final_response()
                            finished = True
                        else:
                            result = await agent.run(messages, session=session._native)
                        if run.fault:
                            raise run.fault
                        if run.model_status == "tool_calls":
                            raise LlmError("agent_loop_incomplete", category="interrupted", action="The run stopped with unresolved tool work.")
                        run.status = run.model_status or "completed"
                        result.additional_properties["llm_interface"] = run.metadata()
                        session._result = copy.deepcopy(result)
                        if stream:
                            await event("run." + run.status, {"agent": self.name, "session_id": session.id,
                                                         "model_calls": run.model_calls, "tool_calls": run.tool_calls})
                        return result
                    except asyncio.CancelledError:
                        session._tainted = True
                        raise
                    except Exception as error:
                        session._tainted = True
                        failure = safe_error(error)
                        if stream:
                            run.event_count += 1
                            await emit(RunEvent("run.failed", run.run_id, run.event_count, failure.metadata()))
                    finally:
                        if source is not None and not finished:
                            await settle_stream(source)
                    raise failure

        return self.connection._execute(produce, stream=stream, principal=principal)


def bind_agent(*, connection, instructions: str, tools=(), **options) -> AgentBinding:
    return AgentBinding(connection, instructions=instructions, tools=tools, **options)