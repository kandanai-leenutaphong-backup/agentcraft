import time
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp

from azdata.adapters.gremlin_transport import GremlinTransport
from azdata.transport import OperationFault


class GremlinTransportTests(unittest.TestCase):
    def transport(self):
        return GremlinTransport("wss://fixture.gremlin.cosmos.azure.com/gremlin", time.monotonic() + 5, 32)

    def test_tls_frame_bound_and_idempotent_owned_cleanup(self):
        transport = self.transport()
        socket = SimpleNamespace(closed=False, receive=AsyncMock(return_value=SimpleNamespace(type=aiohttp.WSMsgType.BINARY, data=b"fixture")),
                                 send_bytes=AsyncMock(), close=AsyncMock())
        session = SimpleNamespace(ws_connect=AsyncMock(return_value=socket), close=AsyncMock())
        with patch("aiohttp.ClientSession", return_value=session) as factory:
            transport.connect(transport.url)
            self.assertTrue(session.ws_connect.call_args.kwargs["ssl"])
            self.assertEqual(session.ws_connect.call_args.kwargs["max_msg_size"], 32)
            self.assertEqual(transport.read(), b"fixture")
            transport.write(b"request")
            self.assertFalse(factory.call_args.kwargs["trust_env"])
            transport.close()
            transport.close()
            self.assertTrue(transport.closed)
            session.close.assert_awaited_once()
            socket.close.assert_awaited_once()

    def test_redirect_refuses_before_follow_and_closes_session(self):
        transport = self.transport()
        session = SimpleNamespace(close=AsyncMock())
        captured = {}
        async def redirected(*args, **kwargs):
            await captured["trace"].on_request_redirect[0](None, None, None)
        session.ws_connect = AsyncMock(side_effect=redirected)
        def factory(**kwargs):
            captured["trace"] = kwargs["trace_configs"][0]
            return session
        with patch("aiohttp.ClientSession", side_effect=factory), self.assertRaises(OperationFault) as raised:
            transport.connect(transport.url)
        self.assertEqual(raised.exception.code, "gremlin_redirect_refused")
        self.assertTrue(transport.closed)
        session.close.assert_awaited_once()

    def test_foreign_url_refuses_without_session(self):
        transport = self.transport()
        with patch("aiohttp.ClientSession") as factory, self.assertRaises(OperationFault):
            transport.connect("wss://other.example/gremlin")
        factory.assert_not_called()
        transport.close()


if __name__ == "__main__":
    unittest.main()