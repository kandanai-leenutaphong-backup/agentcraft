from __future__ import annotations

import asyncio
import logging
import math
import os
from dataclasses import asdict
from collections.abc import Awaitable, Mapping, Sequence
from typing import Any, Literal, overload

from agent_framework import ChatMiddleware, ChatResponse, ChatResponseUpdate, FunctionTool, GeneratedEmbeddings, Message
from jsonschema import Draft202012Validator
from jsonschema.validators import validator_for
from referencing import Registry

from .config import Capabilities, ConnectionConfig, Limits, Policy
from .errors import LlmError
from .integrity import StreamEvidence, check_response, completion_state, embedding_indices
from .providers import ProviderClients, build_clients
from .runtime import ACTIVE_RUN, ManagedStream, RunState, close_owned, json_size, messages_snapshot, options_snapshot, safe_error, settle_stream


def _tool_schema_validator(schema):
    try:
        validator = validator_for(schema, default=None if "$schema" in schema else Draft202012Validator)
        if validator is None:
            raise ValueError()
        validator.check_schema(schema)
        return validator(schema, registry=Registry())
    except Exception:
        raise LlmError("invalid_tool_schema", category="config") from None


class CallGuard(ChatMiddleware):
    def __init__(self, connection) -> None:
        self.connection = connection

    async def process(self, context, call_next):
        self.connection._check_open()
        run = ACTIVE_RUN.get()
        if run is None:
            raise LlmError("missing_run_authority", category="denied")
        context.options = self.connection._validate(context.messages, context.options, stream=context.stream, internal=True)
        run.model_attempt()
        await call_next()
        if context.stream:
            evidence = StreamEvidence()
            context.result.with_transform_hook(evidence.observe).with_result_hook(evidence.finalize)
            context.result.with_result_hook(self._check_tools)
        else:
            check_response(context.result)
            await self._check_tools(context.result)

    async def _check_tools(self, result):
        run = ACTIVE_RUN.get()
        if run.fault:
            raise run.fault
        run.model_status = completion_state(result)
        prepared = []
        for message in getattr(result, "messages", ()):
            for content in message.contents:
                if content.type != "function_call":
                    continue
                if content.name not in self.connection.policy.allowed_tools:
                    raise LlmError("tool_not_granted", category="denied")
                if run.tools:
                    candidate = run.tools.get(content.name)
                    if candidate is None:
                        raise LlmError("tool_not_registered", category="denied")
                    try:
                        import json
                        arguments = json.loads(content.arguments) if isinstance(content.arguments, str) else content.arguments
                        if not isinstance(arguments, dict) or set(arguments) - set(candidate.parameters().get("properties", {})):
                            raise ValueError()
                        if candidate.input_model is not None:
                            candidate.input_model.model_validate(arguments, strict=True)
                        else:
                            _tool_schema_validator(candidate.parameters()).validate(arguments)
                    except Exception:
                        raise LlmError("invalid_tool_arguments", category="invalid", action="No tool was executed from the invalid call.") from None
                    if content.call_id in run.tool_call_ids:
                        raise LlmError("duplicate_tool_call", category="denied")
                    run.tool_call_ids.add(content.call_id)
                    prepared.append((content, arguments))
        if len(prepared) + run.tool_calls > run.limits.max_tool_calls:
            raise LlmError("tool_budget_exhausted", category="denied")
        for content, arguments in prepared:
            key = (content.name, json.dumps(arguments, sort_keys=True))
            run.tool_requests.setdefault(key, []).append(content.call_id)
            if run.emit:
                await run.emit("tool.call.ready", {"call_id": content.call_id, "name": content.name, "arguments": arguments})
        return result


class Chat:
    """Single model calls; function execution is disabled on this surface."""

    def __init__(self, connection) -> None:
        self.connection = connection

    @overload
    def get_response(self, messages: str | Message | Sequence[Message], *, stream: Literal[False] = False,
                     options: Mapping[str, Any] | None = None) -> Awaitable[ChatResponse]: ...

    @overload
    def get_response(self, messages: str | Message | Sequence[Message], *, stream: Literal[True],
                     options: Mapping[str, Any] | None = None) -> ManagedStream[ChatResponseUpdate, ChatResponse]: ...

    def get_response(self, messages, *, stream: bool = False, options=None):
        """Return a model response, or stream native framework updates and read its final response."""
        connection = self.connection
        connection._check_open()
        messages = messages_snapshot(messages)
        options = connection._validate(messages, options_snapshot(options), stream=stream)

        async def produce(emit):
            async with connection._slot():
                native = connection._clients().chat_factory([CallGuard(connection)], False)
                if not stream:
                    result = await native.get_response(messages, options=options)
                    ACTIVE_RUN.get().output(result.to_dict())
                    return result
                source = native.get_response(messages, stream=True, options=options)
                finished = False
                try:
                    async for update in source:
                        ACTIVE_RUN.get().output(update.to_dict())
                        await emit(update)
                    result = await source.get_final_response()
                    finished = True
                    return result
                finally:
                    if not finished:
                        await settle_stream(source)

        return connection._execute(produce, stream=stream)


class Embeddings:
    def __init__(self, connection) -> None:
        self.connection = connection

    async def get_embeddings(self, values: Sequence[str], *, options: Mapping[str, Any] | None = None) -> GeneratedEmbeddings:
        """Return text embeddings in verified input order; options may specify dimensions."""
        connection = self.connection
        connection._check_open()
        connection._grant()
        if not connection.capabilities.embeddings or connection.config.embedding_model is None:
            raise LlmError("embeddings_not_configured", category="unsupported", action="Set embedding_model on its owning endpoint, or use a separate connection.")
        if not isinstance(values, (tuple, list)) or not values or len(values) > 2048 or any(not isinstance(value, str) or not value.strip() for value in values):
            raise LlmError("invalid_embedding_inputs", action="Supply a nonempty bounded list of nonempty strings.")
        values = list(values)
        options = options_snapshot(options)
        if set(options) - {"dimensions"}:
            raise LlmError("embedding_option_unsupported", category="unsupported")
        dimensions = options.get("dimensions")
        if dimensions is not None and (type(dimensions) is not int or dimensions <= 0):
            raise LlmError("invalid_dimensions")
        if json_size(values) > connection.policy.limits.max_input_bytes:
            raise LlmError("input_limit")

        async def produce(emit):
            async with connection._slot():
                clients = connection._clients()
                if clients.embeddings is None:
                    raise LlmError("embeddings_unsupported", category="unsupported")
                if not clients.native_validation:
                    raise LlmError("native_embedding_evidence_required", category="unsupported", action="The adapter must validate indices before normalization.")
                ACTIVE_RUN.get().model_attempt()
                result = await clients.embeddings.get_embeddings(values, options={**options, "encoding_format": "float"})
                embedding_indices([{"index": index, "embedding": item.vector} for index, item in enumerate(result)], len(values), dimensions)
                ACTIVE_RUN.get().output([item.vector for item in result])
                return result

        return await connection._execute(produce, stream=False)


class Connection:
    """One fixed model target and policy; construct with connect(), close with async with."""
    def __init__(self, config: ConnectionConfig, *, credential, policy: Policy,
                 capabilities: Capabilities | None = None, transport=None, clients: ProviderClients | None = None) -> None:
        self.config = config
        self.policy = policy
        self.capabilities = capabilities or Capabilities(embeddings=config.embedding_model is not None)
        self.chat = Chat(self)
        self.embeddings = Embeddings(self)
        self._credential = credential
        self._transport = transport
        self._bundle = clients
        self._closed = False
        self._loop = None
        self._semaphore = asyncio.Semaphore(policy.limits.max_concurrency)
        self._streams: set[ManagedStream] = set()
        self._tasks: set[asyncio.Task] = set()

    def describe(self) -> dict:
        return {"provider": self.config.provider, "endpoint": self.config.endpoint, "model": self.config.model,
                "embedding_model": self.config.embedding_model, "capabilities": asdict(self.capabilities),
                "capability_evidence": "operator-declared; model support is not live-verified",
                "granted": self.policy.allow_model_calls, "allowed_tools": sorted(self.policy.allowed_tools),
                "limits": asdict(self.policy.limits), "config_digest": self.config.digest, "policy_digest": self.policy.digest,
                "closed": self._closed, "availability": "unverified", "retention": "store=False", "retries": 0,
                "native_enforcement": "adapter-owned" if self._credential is None else "built-in transport"}

    def agent(self, *, instructions: str, tools=(), **options):
        from .agents import bind_agent
        return bind_agent(connection=self, instructions=instructions, tools=tools, **options)

    def _check_open(self) -> None:
        if self._closed:
            raise LlmError("connection_closed", category="config", action="Construct a new connection.")

    def _grant(self) -> None:
        if not self.policy.allow_model_calls:
            raise LlmError("model_calls_denied", category="denied", action="The operator must explicitly set allow_model_calls=True.")

    def _clients(self) -> ProviderClients:
        if self._bundle is None:
            self._bundle = build_clients(self.config, self._credential, self.policy, self._transport)
        return self._bundle

    def _slot(self):
        self._check_open()
        check_logging()
        loop = asyncio.get_running_loop()
        if self._loop is not None and self._loop is not loop:
            raise LlmError("event_loop_changed", category="config", action="Use one connection per event loop.")
        self._loop = loop
        return self._semaphore

    def _validate(self, messages, options, *, stream=False, internal=False) -> dict:
        self._grant()
        if type(stream) is not bool:
            raise LlmError("invalid_stream")
        if not self.capabilities.chat or stream and not self.capabilities.streaming:
            raise LlmError("capability_unsupported", category="unsupported")
        options = dict(options or {})
        allowed = {"max_tokens", "temperature", "top_p", "response_format", "store", "model", "tools", "reasoning", "tool_choice", "parallel_tool_calls"}
        if internal:
            allowed.add("instructions")
        if set(options) - allowed:
            raise LlmError("option_unsupported", category="unsupported", action="Use options listed in CONTRACT.md; request-level SDK overrides are unavailable.")
        if options.get("model", self.config.model) != self.config.model or options.get("store", False) is not False:
            raise LlmError("binding_override_denied", category="denied")
        maximum = options.get("max_tokens", self.policy.limits.max_output_tokens)
        if type(maximum) is not int or not 0 < maximum <= self.policy.limits.max_output_tokens:
            raise LlmError("output_token_limit")
        for name in ("temperature", "top_p"):
            value = options.get(name)
            ceiling = 2 if name == "temperature" else 1
            if value is not None and (type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= ceiling):
                raise LlmError("invalid_sampling_option")
        if options.get("response_format") is not None and not self.capabilities.structured_output:
            raise LlmError("structured_output_unsupported", category="unsupported")
        if options.get("reasoning") and not self.capabilities.reasoning:
            raise LlmError("reasoning_unsupported", category="unsupported", action="Declare reasoning capability for the selected deployment before requesting it.")
        if options.get("reasoning"):
            reasoning = options["reasoning"]
            if (not isinstance(reasoning, dict) or set(reasoning) - {"effort", "summary"}
                    or reasoning.get("effort", "none") not in {"none", "low", "medium", "high", "xhigh"}
                    or reasoning.get("summary", "auto") not in {"auto", "concise", "detailed"}):
                raise LlmError("reasoning_option_unsupported", category="unsupported")
        for message in messages:
            for content in message.contents:
                if content.type not in {"text", "function_call", "function_result", "text_reasoning", "usage"}:
                    raise LlmError("content_type_unsupported", category="unsupported", action="This profile supports text and local function content only.")
        if json_size([[message.to_dict() for message in messages], options.get("instructions", "")]) > self.policy.limits.max_input_bytes:
            raise LlmError("input_limit")
        tools = options.get("tools") or []
        if tools and not self.capabilities.tools:
            raise LlmError("tools_unsupported", category="unsupported")
        for candidate in tools:
            if not isinstance(candidate, FunctionTool) or candidate.name not in self.policy.allowed_tools:
                raise LlmError("tool_not_granted", category="denied", action="Register and explicitly grant a local function tool; hosted tools are unsupported.")
        options.update(store=False, max_tokens=maximum, model=self.config.model)
        return options

    def _execute(self, produce, *, stream: bool, principal="operator"):
        state = RunState(self.policy.limits, principal=principal)

        async def execute(emit):
            token = ACTIVE_RUN.set(state)
            current = asyncio.current_task()
            self._tasks.add(current)
            failure = None
            try:
                self._check_open()
                result = await produce(emit)
                state.status = state.model_status or "completed"
                properties = getattr(result, "additional_properties", None)
                if isinstance(properties, dict):
                    properties["llm_interface"] = state.metadata()
                return result
            except asyncio.CancelledError:
                state.status = "cancelled"
                state.mark_unknown()
                raise
            except Exception as error:
                failure = safe_error(error)
                if failure.category in {"interrupted", "failed", "unavailable"}:
                    state.mark_unknown()
            finally:
                self._tasks.discard(current)
                ACTIVE_RUN.reset(token)
            raise failure

        if stream:
            result = ManagedStream(execute, limits=self.policy.limits)
            self._streams.add(result)
            result.with_cleanup_hook(lambda: self._streams.discard(result))
            return result

        async def once():
            failure = None
            try:
                async with asyncio.timeout(self.policy.limits.timeout_seconds):
                    return await execute(None)
            except Exception as error:
                failure = safe_error(error)
            raise failure

        return once()

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        for stream in list(self._streams):
            await stream.aclose()
        self._streams.clear()
        tasks = [task for task in self._tasks if task is not asyncio.current_task()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        if self._bundle:
            await close_owned(self._bundle.resources)

    async def __aenter__(self):
        self._check_open()
        return self

    async def __aexit__(self, *args):
        await self.aclose()


def connect(endpoint: str | ConnectionConfig, model: str | None = None, *, credential,
            allow_model_calls: bool = False, policy: Policy | None = None, provider: str = "auto",
            embedding_model: str | None = None, allowed_hosts=None, credential_scope=None,
            capabilities: Capabilities | None = None, transport=None, allowed_tools=(), limits: Limits | None = None) -> Connection:
    """Bind an explicit endpoint/model/identity. No token or network call occurs until use.

    A /api/projects/<project> endpoint selects Foundry; an account origin selects
    Azure OpenAI. Set allow_model_calls=True as the operator's explicit inference grant.
    Tools additionally require their exact names in allowed_tools.
    """
    config = endpoint if isinstance(endpoint, ConnectionConfig) else ConnectionConfig(endpoint, model, provider,
        embedding_model, allowed_hosts, credential_scope)
    if policy is not None and (allow_model_calls or allowed_tools or limits is not None):
        raise LlmError("ambiguous_policy", category="config", action="Supply either Policy or allow_model_calls, not both.")
    if policy is not None and not isinstance(policy, Policy):
        raise LlmError("invalid_policy", category="config")
    if capabilities is not None and not isinstance(capabilities, Capabilities):
        raise LlmError("invalid_capabilities", category="config")
    if credential is None:
        raise LlmError("credential_required", category="config")
    if config.provider.startswith("openai") and not ((isinstance(credential, str) and credential.strip()) or callable(credential)):
        raise LlmError("provider_credential_required", category="config", action="Supply the provider's credential or token callable at construction.")
    if not config.provider.startswith("openai") and not callable(getattr(credential, "get_token", None)) and not callable(credential):
        raise LlmError("entra_credential_required", category="config", action="Supply an Azure Identity credential or token provider.")
    if config.provider == "foundry" and not callable(getattr(credential, "get_token", None)):
        raise LlmError("project_identity_required", category="config", action="Pass an Azure Identity credential to the Foundry project client.")
    if config.provider == "custom":
        raise LlmError("custom_factory_required", category="config", action="Use from_clients() for caller-owned provider integration.")
    if os.environ.get("AZURE_AI_PROJECTS_CONSOLE_LOGGING", "").lower() in {"1", "true"}:
        raise LlmError("unsafe_console_logging", category="config", action="Disable Azure AI Projects console payload logging.")
    check_logging()
    return Connection(config, credential=credential, policy=policy or Policy(allow_model_calls=allow_model_calls,
                      allowed_tools=allowed_tools, limits=limits or Limits()),
                      capabilities=capabilities, transport=transport)


def check_logging() -> None:
    from agent_framework.observability import OBSERVABILITY_SETTINGS
    names = {"openai", "httpx", "agent_framework", "azure.ai.projects"}
    names.update(name for name in logging.Logger.manager.loggerDict
                 if name.startswith(("openai.", "agent_framework.", "azure.ai.projects.")))
    if any(logging.getLogger(name).isEnabledFor(logging.DEBUG) for name in names):
        raise LlmError("unsafe_debug_logging", category="config", action="Disable payload-capable SDK/framework DEBUG logging before connecting.")
    if OBSERVABILITY_SETTINGS.SENSITIVE_DATA_ENABLED:
        raise LlmError("sensitive_telemetry_enabled", category="config", action="Disable sensitive payload capture in Agent Framework observability.")


def from_clients(config: ConnectionConfig, *, chat_factory, embedding_client=None,
                 policy: Policy, capabilities: Capabilities, owned_resources=(),
                 native_embedding_validation: bool = False) -> Connection:
    """Adapter-author API: inject a framework client factory(middleware, enabled).

    The factory must attach the supplied middleware and configure exactly one native
    function loop when enabled. Target, retries and pre-normalization checks are its
    responsibility. Dependencies are borrowed unless listed in owned_resources.
    """
    if (not isinstance(config, ConnectionConfig) or not isinstance(policy, Policy)
            or not isinstance(capabilities, Capabilities) or not callable(chat_factory)):
        raise LlmError("invalid_provider_binding", category="config")
    if type(native_embedding_validation) is not bool:
        raise LlmError("invalid_embedding_evidence_flag", category="config")
    check_logging()
    bundle = ProviderClients(chat_factory, embedding_client, list(owned_resources), native_embedding_validation)
    return Connection(config, credential=None, policy=policy, capabilities=capabilities, clients=bundle)