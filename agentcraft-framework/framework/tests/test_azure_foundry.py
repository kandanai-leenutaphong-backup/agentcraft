import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from openai import AsyncOpenAI

import azure_foundry


class FoundryTests(unittest.TestCase):
    def run_call(self, *, status="completed", refusal=False, endpoint="https://fixture.openai.azure.com"):
        requests = []

        def handle(request):
            import json

            requests.append(request)
            payload = json.loads(request.content)
            self.assertEqual(payload["model"], "fixture-model")
            self.assertEqual(payload["input"], "Hello")
            self.assertEqual(payload["max_output_tokens"], 128)
            self.assertIs(payload["store"], False)
            self.assertEqual(request.headers["authorization"], "Bearer synthetic-token")
            content = ({"type": "refusal", "refusal": "No"} if refusal else
                       {"type": "output_text", "text": "OK", "annotations": []})
            return httpx.Response(200, json={
                "id": "resp_fixture", "object": "response", "created_at": 0,
                "model": "fixture-model", "status": status,
                "output": [{"id": "msg_fixture", "type": "message",
                            "role": "assistant", "status": "completed", "content": [content]}],
            })

        def client(**options):
            options["http_client"] = httpx.AsyncClient(transport=httpx.MockTransport(handle))
            return AsyncOpenAI(**options)

        path = Path(__file__).resolve().parents[2] / "tooling/functions/llm/azure-foundry/call.py"
        spec = importlib.util.spec_from_file_location("foundry_call", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        credential = SimpleNamespace(get_token=AsyncMock(return_value=SimpleNamespace(
            token="synthetic-token", expires_on=4102444800,
        )))
        with patch.object(azure_foundry, "AsyncOpenAI", side_effect=client):
            result = module.call("Hello", endpoint=endpoint, deployment="fixture-model", credential=credential)
        self.assertEqual(len(requests), 1)
        credential.get_token.assert_awaited_once_with("https://cognitiveservices.azure.com/.default")
        return result

    def test_script_returns_text_through_native_sdk(self):
        self.assertEqual(self.run_call(), "OK")

    def test_incomplete_response_refused(self):
        with self.assertRaisesRegex(RuntimeError, "did not complete"):
            self.run_call(status="incomplete")

    def test_model_refusal(self):
        with self.assertRaisesRegex(RuntimeError, "refused"):
            self.run_call(refusal=True)

    def test_invalid_target_refused_before_auth(self):
        with patch.object(azure_foundry, "get_bearer_token_provider") as token:
            with self.assertRaises(ValueError):
                self.run_call(endpoint="https://untrusted.example")
            token.assert_not_called()