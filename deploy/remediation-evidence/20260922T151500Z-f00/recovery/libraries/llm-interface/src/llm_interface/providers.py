from __future__ import annotations

import asyncio
import inspect
import json
from dataclasses import dataclass
from typing import Any

from .config import ConnectionConfig, Policy
from .errors import LlmError
from .integrity import embedding_indices
from .runtime import ACTIVE_RUN


@dataclass
class ProviderClients:
    chat_factory: Any
    embeddings: Any
    resources: list
    native_validation: bool = True


def build_clients(config: ConnectionConfig, credential, policy: Policy, transport=None) -> ProviderClients:
    try:
        import httpx
        from openai import AsyncOpenAI
        from agent_framework.openai import OpenAIChatClient, OpenAIChatCompletionClient, OpenAIEmbeddingClient
        if config.provider == "foundry":
            from azure.ai.projects.aio import AIProjectClient
            from agent_framework.foundry import FoundryChatClient
    except ImportError:
        raise LlmError("provider_extra_missing", category="config", action="Install llm-interface[foundry] or llm-interface[openai].") from None

    class LimitedBody(httpx.AsyncByteStream):
        def __init__(self, body) -> None:
            self.body = body

        async def __aiter__(self):
            size = 0
            try:
                async for chunk in self.body:
                    size += len(chunk)
                    run = ACTIVE_RUN.get()
                    if run is not None:
                        run.wire_bytes += len(chunk)
                        if run.wire_bytes > policy.limits.max_output_bytes:
                            raise LlmError("native_run_output_limit", category="interrupted")
                    if size > policy.limits.max_output_bytes:
                        raise LlmError("native_response_limit", category="interrupted")
                    yield chunk
            finally:
                await self.body.aclose()

        async def aclose(self):
            await self.body.aclose()

    base_url = config.endpoint + "openai/v1/" if config.provider == "foundry" else config.endpoint

    class GuardedTransport(httpx.AsyncBaseTransport):
        def __init__(self):
            self.inner = transport if transport is not None else httpx.AsyncHTTPTransport(retries=0, trust_env=False)

        async def handle_async_request(self, request):
            run = ACTIVE_RUN.get()
            if run is None:
                raise LlmError("missing_run_authority", category="denied")
            suffix = str(request.url).split("?", 1)[0]
            if request.method != "POST" or suffix not in {base_url + "responses", base_url + "chat/completions", base_url + "embeddings"}:
                raise LlmError("native_target_refused", category="denied")
            if len(request.content) > policy.limits.max_input_bytes:
                raise LlmError("native_input_limit")
            payload = json.loads(request.content)
            embedding = request.url.path.endswith("/embeddings")
            if payload.get("model") != (config.embedding_model if embedding else config.model):
                raise LlmError("native_model_refused", category="denied")
            if not embedding and payload.get("store") is not False:
                raise LlmError("retention_refused", category="denied")
            response = await self.inner.handle_async_request(request)
            if 300 <= response.status_code < 400:
                await response.aclose()
                raise LlmError("redirect_refused", category="denied")
            bounded = httpx.Response(response.status_code, headers=response.headers,
                                     stream=LimitedBody(response.stream), extensions=response.extensions)
            if embedding and response.status_code < 300:
                await bounded.aread()
                embedding_indices(bounded.json().get("data"), len(payload["input"]), payload.get("dimensions"))
            return bounded

        async def aclose(self):
            if transport is None:
                await self.inner.aclose()

    if config.provider.startswith("openai"):
        token = credential
    else:
        if not callable(getattr(credential, "get_token", None)) and not callable(credential):
            raise LlmError("entra_credential_required", category="config", action="Pass an Azure Identity credential, not an API key.")
        if callable(getattr(credential, "get_token", None)):
            try:
                if inspect.iscoroutinefunction(credential.get_token):
                    from azure.identity.aio import get_bearer_token_provider
                    token = get_bearer_token_provider(credential, config.credential_scope)
                else:
                    from azure.identity import get_bearer_token_provider
                    synchronous = get_bearer_token_provider(credential, config.credential_scope)

                    async def token():
                        return await asyncio.to_thread(synchronous)
            except ImportError:
                raise LlmError("identity_extra_missing", category="config", action="Install llm-interface[foundry].") from None
        else:
            token = credential
    http = httpx.AsyncClient(transport=GuardedTransport(), follow_redirects=False,
                            trust_env=False, timeout=policy.limits.timeout_seconds)
    resources = [http]
    if config.provider == "foundry":
        class BoundProject(AIProjectClient):
            def get_openai_client(self, **options):
                if not hasattr(self, "shared_model_client"):
                    self.shared_model_client = super().get_openai_client(http_client=http,
                        api_key=token, max_retries=0, timeout=policy.limits.timeout_seconds,
                        organization="", project="")
                return self.shared_model_client

        project = BoundProject(config.endpoint.rstrip("/"), credential, logging_enable=False, retry_total=0)
        resources.append(project)
        native = project.get_openai_client()
        resources.append(native)

        def factory(middleware, enabled):
            return FoundryChatClient(model=config.model, project_endpoint=config.endpoint.rstrip("/"),
                project_client=project, middleware=middleware,
                function_invocation_configuration={"enabled": enabled, "max_iterations": policy.limits.max_model_calls,
                    "max_function_calls": policy.limits.max_tool_calls, "include_detailed_errors": False})
    else:
        native = AsyncOpenAI(base_url=base_url, api_key=token, http_client=http,
                             organization="", project="", timeout=policy.limits.timeout_seconds, max_retries=0)
        resources.append(native)
        client_type = OpenAIChatCompletionClient if config.provider.endswith("completions") else OpenAIChatClient

        def factory(middleware, enabled):
            return client_type(model=config.model, async_client=native, middleware=middleware,
                function_invocation_configuration={"enabled": enabled, "max_iterations": policy.limits.max_model_calls,
                    "max_function_calls": policy.limits.max_tool_calls, "include_detailed_errors": False})
    embeddings = OpenAIEmbeddingClient(model=config.embedding_model, async_client=native) if config.embedding_model else None
    return ProviderClients(factory, embeddings, resources)