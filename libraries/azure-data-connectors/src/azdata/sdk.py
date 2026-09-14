from __future__ import annotations

import asyncio
import inspect
import json
import time
from contextvars import ContextVar
from urllib.parse import urlsplit

from azure.core.credentials import AccessToken
from azure.core.exceptions import AzureError, HttpResponseError
from azure.core.pipeline.policies import AsyncRedirectPolicy, AsyncRetryPolicy
from azure.core.pipeline.transport import AioHttpTransport, AsyncHttpResponse, AsyncHttpTransport
from azure.core.rest import HttpRequest as NativeRequest

from .contracts import Limits, plain, positive
from .transport import HttpRequest, HttpResponse, OperationFault

ACTIVE_CALL = ContextVar("azdata_sdk_call")


class Credential:
    def __init__(self, credential, scope):
        self._credential = credential
        self._scope = scope

    async def get_token(self, *scopes, **kwargs):
        try:
            scopes = (self._scope,)
            method = self._credential.get_token
            access = await method(*scopes) if inspect.iscoroutinefunction(method) else await asyncio.to_thread(method, *scopes)
            if inspect.isawaitable(access):
                access = await access
            if (not isinstance(access.token, str) or not access.token or any(char in access.token for char in "\r\n")
                    or not positive(access.expires_on) or access.expires_on <= time.time()):
                raise ValueError()
            return AccessToken(access.token, access.expires_on)
        except Exception:
            raise OperationFault("denied", "credential_unavailable") from None


class RetryPolicy(AsyncRetryPolicy):
    async def send(self, request):
        context, mutation = ACTIVE_CALL.get()
        budget = 0 if mutation else context.limits.max_attempts - 1
        request.context.options.update(retry_total=budget, retry_connect=budget, retry_read=budget,
                                       retry_status=budget, retry_on_methods=frozenset({"GET", "POST", "PUT", "DELETE"}))
        return await super().send(request)


class Response(AsyncHttpResponse):
    def __init__(self, request, response):
        super().__init__(request, None)
        self.status_code = response.status
        self.headers = {name.lower(): value for name, value in response.headers.items()}
        self.headers.setdefault("content-type", "application/json")
        self.content_type = self.headers["content-type"]
        self.reason = ""
        self._body = json.dumps(plain(response.body), allow_nan=False).encode() if response.body is not None else b""

    def body(self):
        return self._body


class Transport(AsyncHttpTransport):
    def __init__(self, config, injected):
        self._config = config
        self._injected = injected
        self._native = None

    async def open(self):
        return None

    async def close(self):
        if self._native is not None:
            await self._native.close()
            self._native = None

    async def __aexit__(self, *args):
        await self.close()

    async def send(self, request, **kwargs):
        context, mutation = ACTIVE_CALL.get()
        parsed = urlsplit(request.url)
        if (parsed.scheme, parsed.netloc) != ("https", urlsplit(self._config.endpoint).netloc):
            raise OperationFault("denied", "sdk_target_outside_scope")
        if context.session.closed:
            raise OperationFault("failed", "connector_closed")
        context.attempts += 1
        context.submitted = True
        remaining = max(0.001, context.deadline - time.monotonic())
        if self._injected is not None:
            body = json.loads(request.body) if request.body else None
            result = await self._injected.request(HttpRequest(request.method, request.url, request.headers, body,
                                                              remaining, context.limits.max_output_bytes))
        else:
            if self._native is None:
                self._native = AioHttpTransport()
            response = await self._native.send(NativeRequest(request.method, request.url, headers=request.headers,
                                                            content=request.body), stream=True, allow_redirects=False,
                                               connection_timeout=remaining, read_timeout=remaining)
            try:
                payload = bytearray()
                if 200 <= response.status_code < 300:
                    async for chunk in response.iter_bytes():
                        payload.extend(chunk)
                        if len(payload) > context.limits.max_output_bytes:
                            raise OperationFault("unknown" if mutation else "failed", "response_too_large")
                result = HttpResponse(response.status_code, json.loads(payload) if payload else None, response.headers)
            except (ValueError, UnicodeError):
                raise OperationFault("unknown" if mutation else "failed", "invalid_provider_json") from None
            finally:
                await response.close()
        if not isinstance(result, HttpResponse) or type(result.status) is not int:
            raise OperationFault("unknown", "invalid_provider_response")
        return Response(request, result)


class Session:
    def __init__(self, service, config, credential, transport, concurrency):
        self.service = service
        self.config = config
        self.closed = False
        self.gate = asyncio.Semaphore(concurrency)
        self._transport = Transport(config, transport)
        self._clients = {}
        self._credential = Credential(credential, config.scope or (
            "https://search.azure.com/.default" if service == "search" else "https://cosmos.azure.com/.default"))
        self._ready = False
        self._setup_lock = asyncio.Lock()

    def client(self, kind):
        if kind not in self._clients:
            config = self.config
            options = dict(transport=self._transport, retry_policy=RetryPolicy(),
                           redirect_policy=AsyncRedirectPolicy(permit_redirects=False), logging_enable=False)
            if kind == "cosmos":
                try:
                    from azure.cosmos.aio import CosmosClient
                except ImportError:
                    raise OperationFault("failed", "missing_dependency_cosmos") from None
                options.pop("retry_policy")
                self._clients[kind] = CosmosClient(config.endpoint, self._credential, connection_retry_policy=RetryPolicy(),
                    retry_total=0, retry_write=0, enable_endpoint_discovery=False, **options)
                return self._clients[kind]
            try:
                from azure.search.documents.aio import SearchClient
                from azure.search.documents.indexes.aio import SearchIndexClient
            except ImportError:
                raise OperationFault("failed", "missing_dependency_search") from None
            options.update(api_version=config.api_version, audience=(config.scope or "https://search.azure.com/.default").removesuffix("/.default"))
            self._clients[kind] = (SearchClient(config.endpoint, config.target.coordinates["index"], self._credential, **options)
                                   if kind == "documents" else SearchIndexClient(config.endpoint, self._credential, **options))
        return self._clients[kind]

    async def prepare(self):
        async with self._setup_lock:
            if not self._ready:
                await self.client("cosmos").__aenter__()
                self._ready = True

    async def aclose(self):
        self.closed = True
        for client in self._clients.values():
            await client.close()
        await self._transport.close()


class CallContext:
    def __init__(self, session: Session, limits: Limits):
        self.session = session
        self.limits = limits
        self.started = time.monotonic()
        self.deadline = self.started + limits.timeout_seconds
        self.attempts = 0

    async def invoke(self, callback, *, mutation=False, allow_empty=False):
        if self.deadline <= time.monotonic():
            raise OperationFault("failed", "deadline_before_request")
        self.submitted = False
        binding = ACTIVE_CALL.set((self, mutation))
        try:
            async with asyncio.timeout(self.deadline - time.monotonic()), self.session.gate:
                if self.session.service == "cosmos":
                    await self.session.prepare()
                return await callback()
        except HttpResponseError as error:
            if allow_empty and error.status_code == 204:
                return None
            from .transport import check_response

            check_response(HttpResponse(error.status_code or 0), mutation=mutation)
            raise OperationFault("unknown", "invalid_provider_response") from None
        except (TimeoutError, OSError, AzureError):
            raise OperationFault("unknown" if mutation and self.submitted else "failed", "transport_unavailable") from None
        finally:
            ACTIVE_CALL.reset(binding)