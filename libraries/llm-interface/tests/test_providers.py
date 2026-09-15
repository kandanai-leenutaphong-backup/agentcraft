import unittest
from unittest.mock import patch

import httpx
from openai import AsyncOpenAI
from agent_framework.openai import OpenAIChatClient

from llm_interface import Capabilities, ConnectionConfig, LlmError, Policy, from_clients
from test_safety import answer


class ProviderTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        blocker = patch("socket.socket.connect", side_effect=AssertionError("Network forbidden"))
        blocker.start()
        self.addCleanup(blocker.stop)

    async def test_injected_provider_uses_guard_and_borrows_native_client(self):
        async def handle(request):
            return httpx.Response(200, json=answer())
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
            async with AsyncOpenAI(base_url="https://fixture.invalid/v1/", api_key="offline-fixture", http_client=http, max_retries=0) as native:
                def factory(middleware, enabled):
                    return OpenAIChatClient(model="fixture-model", async_client=native, middleware=middleware,
                                            function_invocation_configuration={"enabled": enabled})
                config = ConnectionConfig("https://fixture.invalid", "fixture-model", provider="custom")
                async with from_clients(config, chat_factory=factory, policy=Policy(allow_model_calls=True),
                                        capabilities=Capabilities(embeddings=False)) as model:
                    result = await model.chat.get_response("fixture")
                    self.assertEqual(result.text, "fixture")
                self.assertFalse(native.is_closed())
                async with from_clients(config, chat_factory=factory, policy=Policy(), capabilities=Capabilities()) as model:
                    with self.assertRaises(LlmError):
                        model.chat.get_response("denied")

    async def test_owned_resources_close_once(self):
        class Resource:
            calls = 0
            async def aclose(self):
                self.calls += 1
        resource = Resource()
        model = from_clients(ConnectionConfig("https://fixture.invalid", "fixture-model", provider="custom"),
                             chat_factory=lambda middleware, enabled: None, policy=Policy(), capabilities=Capabilities(),
                             owned_resources=[resource, resource])
        await model.aclose()
        await model.aclose()
        self.assertEqual(resource.calls, 1)