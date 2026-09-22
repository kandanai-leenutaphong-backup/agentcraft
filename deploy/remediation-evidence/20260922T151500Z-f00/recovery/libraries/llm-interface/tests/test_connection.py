import json
import unittest
from unittest.mock import patch

import httpx
from azure.core.credentials import AccessToken

from llm_interface import Limits, LlmError, Policy, connect
from test_framework_comparison import response_value


class Credential:
    def __init__(self):
        self.calls = 0

    async def get_token(self, *scopes, **kwargs):
        self.calls += 1
        return AccessToken("synthetic-identity", 4_000_000_000)


class ConnectionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        blocker = patch("socket.socket.connect", side_effect=AssertionError("Network forbidden"))
        blocker.start()
        self.addCleanup(blocker.stop)

    async def test_few_line_response_and_borrowed_credential(self):
        calls = []
        credential = Credential()

        async def handle(request):
            calls.append(json.loads(request.content))
            self.assertIn("synthetic-identity", request.headers["authorization"])
            message = {"id": "message", "type": "message", "role": "assistant", "status": "completed",
                       "content": [{"type": "output_text", "text": "fixture", "annotations": [], "logprobs": []}]}
            return httpx.Response(200, json=response_value("resp", [message]))

        connection = connect("https://fixture.invalid", "fixture-model", credential=credential,
                             allow_model_calls=True, transport=httpx.MockTransport(handle))
        self.assertEqual(credential.calls, 0)
        self.assertEqual(connection.describe()["availability"], "unverified")
        async with connection:
            answer = await connection.chat.get_response("fixture prompt")
            self.assertEqual(answer.text, "fixture")
            self.assertEqual(answer.additional_properties["llm_interface"]["model_calls"], 1)
        self.assertEqual(len(calls), 1)
        self.assertIs(calls[0]["store"], False)
        self.assertEqual(calls[0]["max_output_tokens"], 1024)
        with self.assertRaises(LlmError):
            connection.chat.get_response("after close")

    async def test_denied_and_overrides_make_no_call(self):
        credential = Credential()
        connection = connect("https://fixture.invalid", "fixture-model", credential=credential)
        with self.assertRaises(LlmError) as denied:
            connection.chat.get_response("fixture")
        self.assertEqual(denied.exception.category, "denied")
        await connection.aclose()
        async with connect("https://fixture.invalid", "fixture-model", credential=credential,
                           allow_model_calls=True) as connection:
            for options in ({"store": True}, {"model": "other"}, {"extra_headers": {}}, {"max_tokens": 999999}):
                with self.subTest(options=options), self.assertRaises(LlmError):
                    connection.chat.get_response("fixture", options=options)
        self.assertEqual(credential.calls, 0)

    async def test_foundry_project_uses_official_client_path(self):
        observed = []

        async def handle(request):
            observed.append(request.url)
            self.assertEqual(request.url.path, "/api/projects/demo/openai/v1/responses")
            self.assertEqual(str(request.url.query, "ascii"), "")
            message = {"id": "message", "type": "message", "role": "assistant", "status": "completed",
                       "content": [{"type": "output_text", "text": "foundry fixture", "annotations": [], "logprobs": []}]}
            return httpx.Response(200, json=response_value("resp", [message]))

        async with connect("https://fixture.invalid/api/projects/demo", "fixture-model", credential=Credential(),
                           allow_model_calls=True, transport=httpx.MockTransport(handle)) as connection:
            result = await connection.chat.get_response("fixture")
            self.assertEqual(result.text, "foundry fixture")
        self.assertEqual(len(observed), 1)

    async def test_native_embedding_indices_checked_before_mapping(self):
        mode = ["valid"]

        async def handle(request):
            indices = [1, 0] if mode[0] == "valid" else [0, 0]
            return httpx.Response(200, json={"object": "list", "model": "vectors", "data": [
                {"object": "embedding", "index": index, "embedding": [float(index), 1.0]} for index in indices],
                "usage": {"prompt_tokens": 2, "total_tokens": 2}})

        async with connect("https://fixture.invalid", "fixture-model", credential=Credential(),
                           embedding_model="vectors", allow_model_calls=True, transport=httpx.MockTransport(handle)) as connection:
            result = await connection.embeddings.get_embeddings(["first", "second"])
            self.assertEqual([item.vector[0] for item in result], [0.0, 1.0])
            mode[0] = "invalid"
            with self.assertRaises(LlmError) as failed:
                await connection.embeddings.get_embeddings(["first", "second"])
            self.assertEqual(failed.exception.code, "embedding_index_mismatch")