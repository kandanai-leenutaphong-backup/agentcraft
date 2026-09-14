"""Offline dependency comparison, not an llm-interface runtime implementation."""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch

import httpx
from openai import AsyncOpenAI
from pydantic import BaseModel
from agent_framework import Agent, AgentSession, ChatMiddleware, FunctionMiddleware, Message, tool
from agent_framework.openai import OpenAIChatClient, OpenAIChatCompletionClient, OpenAIEmbeddingClient


def response_value(identifier: str, output: list, status: str = "completed") -> dict:
    return {
        "id": identifier, "object": "response", "created_at": 1,
        "model": "fixture-model", "status": status,
        "error": None, "incomplete_details": None, "instructions": None,
        "metadata": {}, "parallel_tool_calls": True, "tool_choice": "auto",
        "tools": [], "temperature": 1, "top_p": 1, "output": output,
        "usage": {"input_tokens": 3, "output_tokens": 2, "total_tokens": 5,
                  "input_tokens_details": {"cached_tokens": 0},
                  "output_tokens_details": {"reasoning_tokens": 0}},
    }


class ModelFixture:
    def __init__(self, protocol: str) -> None:
        self.protocol = protocol
        self.requests: list[dict] = []

    async def handle(self, request: httpx.Request) -> httpx.Response:
        assert request.url.host == "fixture.invalid"
        body = json.loads(request.content)
        self.requests.append(body)
        assert body["stream"] is True
        assert body["store"] is False
        assert len(self.requests) <= 2
        first = len(self.requests) == 1
        if self.protocol == "responses":
            assert request.url.path == "/v1/responses"
            return self.responses(body, first)
        assert request.url.path == "/v1/chat/completions"
        return self.completions(body, first)

    def responses(self, body: dict, first: bool) -> httpx.Response:
        if first:
            assert any(candidate.get("name") == "lookup_fixture" for candidate in body["tools"])
            call = {"id": "fc_fixture", "type": "function_call", "call_id": "call_fixture",
                    "name": "lookup_fixture", "arguments": '{"asset_id":"fixture"}',
                    "status": "completed"}
            events = [
                {"type": "response.created", "response": response_value("resp_tool", [], "in_progress")},
                {"type": "response.output_item.added", "output_index": 0,
                 "item": {**call, "arguments": "", "status": "in_progress"}},
                {"type": "response.function_call_arguments.delta", "item_id": "fc_fixture",
                 "output_index": 0, "delta": '{"asset_id":'},
                {"type": "response.function_call_arguments.delta", "item_id": "fc_fixture",
                 "output_index": 0, "delta": '"fixture"}'},
                {"type": "response.function_call_arguments.done", "item_id": "fc_fixture",
                 "output_index": 0, "name": "lookup_fixture", "arguments": call["arguments"]},
                {"type": "response.output_item.done", "output_index": 0, "item": call},
                {"type": "response.completed", "response": response_value("resp_tool", [call])},
            ]
        else:
            results = [item for item in body["input"] if item.get("type") == "function_call_output"]
            assert len(results) == 1 and results[0]["call_id"] == "call_fixture"
            assert "verified fixture" in json.dumps(results[0]["output"])
            message = {"id": "msg_fixture", "type": "message", "role": "assistant",
                       "status": "completed", "content": [{"type": "output_text",
                       "text": "Fixture verified.", "annotations": [], "logprobs": []}]}
            events = [
                {"type": "response.created", "response": response_value("resp_answer", [], "in_progress")},
                {"type": "response.output_text.delta", "item_id": "msg_fixture", "output_index": 0,
                 "content_index": 0, "delta": "Fixture verified.", "logprobs": []},
                {"type": "response.completed", "response": response_value("resp_answer", [message])},
            ]
        wire = "".join("event: " + event["type"] + "\ndata: "
                       + json.dumps({**event, "sequence_number": index}) + "\n\n"
                       for index, event in enumerate(events))
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=wire)

    def completions(self, body: dict, first: bool) -> httpx.Response:
        if first:
            assert any(candidate.get("function", {}).get("name") == "lookup_fixture" for candidate in body["tools"])
            deltas = [
                ({"role": "assistant", "tool_calls": [{"index": 0, "id": "call_fixture",
                  "type": "function", "function": {"name": "lookup_fixture", "arguments": '{"asset_id":'}}]}, None),
                ({"tool_calls": [{"index": 0, "function": {"arguments": '"fixture"}'}}]}, None),
                ({}, "tool_calls"),
            ]
        else:
            results = [message for message in body["messages"] if message.get("role") == "tool"]
            assert len(results) == 1 and results[0]["tool_call_id"] == "call_fixture"
            assert "verified fixture" in json.dumps(results[0]["content"])
            deltas = [({"role": "assistant", "content": "Fixture verified."}, None), ({}, "stop")]
        chunks = [{"id": "chat_fixture", "object": "chat.completion.chunk", "created": 1,
                   "model": "fixture-model", "choices": [{"index": 0, "delta": delta,
                   "finish_reason": reason}]} for delta, reason in deltas]
        wire = "".join("data: " + json.dumps(chunk) + "\n\n" for chunk in chunks) + "data: [DONE]\n\n"
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=wire)


class FrameworkComparison(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        blocker = patch("socket.socket.connect", side_effect=AssertionError("Network forbidden"))
        blocker.start()
        self.addCleanup(blocker.stop)

    async def test_same_agent_and_tool_with_two_client_bindings(self) -> None:
        reports = []
        for protocol, client_type in (("responses", OpenAIChatClient), ("completions", OpenAIChatCompletionClient)):
            with self.subTest(protocol=protocol):
                fixture = ModelFixture(protocol)
                executions = []
                lifecycle = []
                updates = []
                model_attempts = []

                @tool
                async def lookup_fixture(asset_id: str) -> dict:
                    """Read one synthetic asset status."""
                    self.assertEqual(asset_id, "fixture")
                    self.assertTrue(any(content.type == "function_call" for content in updates))
                    executions.append(asset_id)
                    return {"asset_id": asset_id, "status": "verified fixture"}

                class Lifecycle(FunctionMiddleware):
                    async def process(self, context, call_next):
                        lifecycle.append((context.function.name, "started"))
                        await call_next()
                        lifecycle.append((context.function.name, "finished"))

                class ModelAttempts(ChatMiddleware):
                    async def process(self, context, call_next):
                        model_attempts.append(len(fixture.requests))
                        await call_next()

                async with httpx.AsyncClient(transport=httpx.MockTransport(fixture.handle)) as transport:
                    async with AsyncOpenAI(base_url="https://fixture.invalid/v1/", api_key="offline-fixture",
                                           http_client=transport, max_retries=0) as native:
                        client = client_type(model="fixture-model", async_client=native,
                                             function_invocation_configuration={"enabled": True, "max_iterations": 4})
                        agent = Agent(client=client, name="fixture-investigator", instructions="Use the registered tool.",
                                      tools=[lookup_fixture], middleware=[Lifecycle(), ModelAttempts()], default_options={"store": False})
                        stream = agent.run("Check the fixture asset.", session=AgentSession(), stream=True)
                        async for update in stream:
                            updates.extend(update.contents)
                        final = await stream.get_final_response()
                self.assertEqual(executions, ["fixture"])
                self.assertEqual(lifecycle, [("lookup_fixture", "started"), ("lookup_fixture", "finished")])
                self.assertEqual(final.text, "Fixture verified.")
                self.assertTrue(any(content.type == "function_result" and content.call_id == "call_fixture" for content in updates))
                self.assertEqual(len(fixture.requests), 2)
                self.assertEqual(model_attempts, [0, 1])
                reports.append((final.text, executions, lifecycle))
        self.assertEqual(reports[0], reports[1])

    async def test_framework_responses_structured_output_and_explicit_retention(self) -> None:
        class Label(BaseModel):
            label: str

        requests = []

        async def handle(request):
            body = json.loads(request.content)
            requests.append(body)
            text = '{"label":"fixture"}' if len(requests) == 2 else "fixture answer"
            message = {"id": "msg_fixture", "type": "message", "role": "assistant",
                       "status": "completed", "content": [{"type": "output_text", "text": text,
                       "annotations": [], "logprobs": []}]}
            return httpx.Response(200, json=response_value("resp_fixture", [message]))

        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as transport:
            async with AsyncOpenAI(base_url="https://fixture.invalid/v1/", api_key="offline-fixture",
                                   http_client=transport, max_retries=0) as native:
                client = OpenAIChatClient(model="fixture-model", async_client=native,
                                          function_invocation_configuration={"enabled": False})
                answer = await client.get_response([Message("user", ["fixture"])])
                self.assertEqual(answer.text, "fixture answer")
                self.assertEqual(answer.usage_details["input_token_count"], 3)
                self.assertNotIn("store", requests[0])
                answer = await client.get_response([Message("user", ["fixture"])],
                                                   options={"response_format": Label, "store": False})
                self.assertEqual(answer.value.label, "fixture")
                self.assertIs(requests[1]["store"], False)

    async def test_framework_embeddings_sort_without_strict_index_integrity(self) -> None:
        cases = {
            "reversed": [{"index": 1, "embedding": [1.0, 2.0]}, {"index": 0, "embedding": [0.0, 2.0]}],
            "duplicate": [{"index": 0, "embedding": [1.0, 2.0]}, {"index": 0, "embedding": [3.0, 4.0]}],
            "missing": [{"index": 0, "embedding": [1.0, 2.0]}],
            "unequal_width": [{"index": 0, "embedding": [1.0]}, {"index": 1, "embedding": [2.0, 3.0]}],
        }
        for name, data in cases.items():
            with self.subTest(case=name):
                async def handle(request):
                    self.assertEqual(json.loads(request.content)["input"], ["first", "second"])
                    return httpx.Response(200, json={"object": "list", "model": "fixture-embedding",
                        "data": [{"object": "embedding", **item} for item in data],
                        "usage": {"prompt_tokens": 2, "total_tokens": 2}})

                async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as transport:
                    async with AsyncOpenAI(base_url="https://fixture.invalid/v1/", api_key="offline-fixture",
                                           http_client=transport, max_retries=0) as native:
                        client = OpenAIEmbeddingClient(model="fixture-embedding", async_client=native)
                        result = await client.get_embeddings(["first", "second"], options={"encoding_format": "float"})
                        expected = [item["embedding"] for item in sorted(data, key=lambda item: item["index"])]
                        self.assertEqual([item.vector for item in result], expected)

    async def test_framework_eof_without_terminal_event_has_no_finish_reason(self) -> None:
        async def handle(request):
            events = [
                {"type": "response.created", "response": response_value("resp_fixture", [], "in_progress")},
                {"type": "response.output_text.delta", "item_id": "msg_fixture", "output_index": 0,
                 "content_index": 0, "delta": "unfinished", "logprobs": []},
            ]
            wire = "".join("event: " + event["type"] + "\ndata: "
                           + json.dumps({**event, "sequence_number": index}) + "\n\n"
                           for index, event in enumerate(events))
            return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=wire)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as transport:
            async with AsyncOpenAI(base_url="https://fixture.invalid/v1/", api_key="offline-fixture",
                                   http_client=transport, max_retries=0) as native:
                client = OpenAIChatClient(model="fixture-model", async_client=native,
                                          function_invocation_configuration={"enabled": False})
                stream = client.get_response([Message("user", ["fixture"])], stream=True, options={"store": False})
                updates = [update async for update in stream]
                final = await stream.get_final_response()
                self.assertTrue(updates)
                self.assertEqual(final.text, "unfinished")
                self.assertIsNone(final.finish_reason)

    async def test_chat_middleware_can_refuse_before_native_transport(self) -> None:
        fixture = ModelFixture("responses")

        class Deny(ChatMiddleware):
            async def process(self, context, call_next):
                raise PermissionError("fixture policy refusal")

        async with httpx.AsyncClient(transport=httpx.MockTransport(fixture.handle)) as transport:
            async with AsyncOpenAI(base_url="https://fixture.invalid/v1/", api_key="offline-fixture",
                                   http_client=transport, max_retries=0) as native:
                client = OpenAIChatClient(model="fixture-model", async_client=native,
                                          middleware=[Deny()], function_invocation_configuration={"enabled": False})
                with self.assertRaises(PermissionError):
                    await client.get_response([Message("user", ["fixture"])])
        self.assertEqual(fixture.requests, [])

    async def test_native_response_hook_can_refuse_before_embedding_normalization(self) -> None:
        observed = []

        async def handle(request):
            return httpx.Response(200, json={"object": "list", "model": "fixture-embedding", "data": [
                {"object": "embedding", "index": 0, "embedding": [1.0]},
                {"object": "embedding", "index": 0, "embedding": [2.0]}],
                "usage": {"prompt_tokens": 2, "total_tokens": 2}})

        async def observe(response):
            await response.aread()
            indices = [item["index"] for item in response.json()["data"]]
            observed.extend(indices)
            if sorted(indices) != [0, 1]:
                raise ValueError("fixture embedding alignment refusal")

        async with httpx.AsyncClient(transport=httpx.MockTransport(handle), event_hooks={"response": [observe]}) as transport:
            async with AsyncOpenAI(base_url="https://fixture.invalid/v1/", api_key="offline-fixture",
                                   http_client=transport, max_retries=0) as native:
                client = OpenAIEmbeddingClient(model="fixture-embedding", async_client=native)
                with self.assertRaises(Exception) as failure:
                    await client.get_embeddings(["first", "second"], options={"encoding_format": "float"})
        self.assertTrue(observed == [0, 0])
        chain = failure.exception
        while chain.__cause__ is not None:
            chain = chain.__cause__
        self.assertIsInstance(chain, ValueError)
        self.assertEqual(str(chain), "fixture embedding alignment refusal")


if __name__ == "__main__":
    unittest.main()