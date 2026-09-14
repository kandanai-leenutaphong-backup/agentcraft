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
from azure.core.pipeline.transport import AsyncHttpResponse, AsyncHttpTransport
from azure.core.rest import HttpRequest as NativeRequest

from .contracts import Limits, plain, positive
from .transport import HttpRequest, HttpResponse, OperationFault, check_response

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
        response = await super().send(request)
        if mutation or context.session.service == "cosmos":
            check_response(HttpResponse(response.http_response.status_code), mutation=mutation)
        return response


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
        if mutation and request.method not in {"GET", "HEAD"}:
            if context.write_submitted:
                raise OperationFault("unknown", "sdk_write_retry_refused")
            context.write_submitted = True
        context.attempts += 1
        context.submitted = True
        remaining = max(0.001, context.deadline - time.monotonic())
        if self._injected is not None:
            body = json.loads(request.body) if request.body else None
            result = await self._injected.request(HttpRequest(request.method, request.url, request.headers, body,
                                                              remaining, context.limits.max_output_bytes))
        else:
            if self._native is None:
                from azure.core.pipeline.transport import AioHttpTransport

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
    def __init__(self, adapter, credential, transport, concurrency):
        self.adapter = adapter
        self.service = adapter.service
        self.config = adapter.config
        self.closed = False
        self.gate = asyncio.Semaphore(concurrency)
        self._transport = Transport(self.config, transport)
        self._clients = {}
        self.credential = Credential(credential, self.config.scope or adapter.scope)
        self._ready = False
        self._setup_lock = asyncio.Lock()

    def client_options(self):
        return dict(transport=self._transport, retry_policy=RetryPolicy(),
                    redirect_policy=AsyncRedirectPolicy(permit_redirects=False), logging_enable=False)

    def client(self, kind):
        if kind not in self._clients:
            try:
                self._clients[kind] = self.adapter.create_client(self, kind)
            except ImportError:
                raise OperationFault("failed", f"missing_dependency_{self.service}") from None
        return self._clients[kind]

    async def prepare(self):
        async with self._setup_lock:
            if not self._ready:
                await self.adapter.prepare(self)
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
        self.write_submitted = False
        binding = ACTIVE_CALL.set((self, mutation))
        try:
            async with asyncio.timeout(self.deadline - time.monotonic()), self.session.gate:
                await self.session.prepare()
                return await callback()
        except HttpResponseError as error:
            if allow_empty and error.status_code == 204:
                return None
            check_response(HttpResponse(error.status_code or 0), mutation=mutation)
            raise OperationFault("unknown", "invalid_provider_response") from None
        except (TimeoutError, OSError, AzureError):
            raise OperationFault("unknown" if mutation and self.submitted else "failed", "transport_unavailable") from None
        finally:
            ACTIVE_CALL.reset(binding)