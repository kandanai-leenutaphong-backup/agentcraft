from __future__ import annotations

import asyncio
import time

import aiohttp
from gremlin_python.driver.transport import AbstractBaseTransport

from ..transport import OperationFault


class GremlinTransport(AbstractBaseTransport):
    def __init__(self, url, deadline, max_response_bytes):
        self.url = url
        self.deadline = deadline
        self.max_response_bytes = max_response_bytes
        self._loop = asyncio.new_event_loop()
        self._session = None
        self._socket = None

    def _call(self, operation):
        async def bounded():
            async with asyncio.timeout(max(0, self.deadline - time.monotonic())):
                return await operation
        try:
            return self._loop.run_until_complete(bounded())
        except aiohttp.ClientError:
            raise OSError("gremlin_network_failure") from None

    def connect(self, url, headers=None):
        if url != self.url:
            raise OperationFault("denied", "gremlin_target_outside_scope")
        async def connect():
            async def refuse_redirect(*args):
                raise OperationFault("denied", "gremlin_redirect_refused")
            trace = aiohttp.TraceConfig()
            trace.on_request_redirect.append(refuse_redirect)
            self._session = aiohttp.ClientSession(trace_configs=[trace], trust_env=False)
            self._socket = await self._session.ws_connect(url, headers=headers, ssl=True,
                max_msg_size=self.max_response_bytes,
                timeout=aiohttp.ClientWSTimeout(ws_receive=max(0.001, self.deadline - time.monotonic()), ws_close=1))
        try:
            self._call(connect())
        except BaseException:
            self.close()
            raise

    def write(self, message):
        self._call(self._socket.send_bytes(message))

    def read(self):
        message = self._call(self._socket.receive())
        if message.type == aiohttp.WSMsgType.TEXT:
            payload = message.data.encode("utf-8")
        elif message.type == aiohttp.WSMsgType.BINARY:
            payload = message.data
        else:
            raise OSError("gremlin_stream_closed")
        if len(payload) > self.max_response_bytes:
            raise OSError("gremlin_frame_too_large")
        return payload

    def close(self):
        if self._loop.is_closed():
            return
        async def close():
            try:
                if self._socket is not None:
                    await asyncio.wait_for(self._socket.close(), timeout=1)
            finally:
                if self._session is not None:
                    await self._session.close()
        try:
            self._loop.run_until_complete(close())
        finally:
            self._loop.close()

    @property
    def closed(self):
        return self._loop.is_closed() or self._socket is None or self._socket.closed