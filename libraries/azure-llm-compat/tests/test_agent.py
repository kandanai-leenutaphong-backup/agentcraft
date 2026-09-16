import json
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from azure_llm_compat import AzureLlmClient, LlmConfig, stream_tool_turn


def event(kind, **values):
    return SimpleNamespace(type=kind, **values)


class ToolTurnTests(unittest.IsolatedAsyncioTestCase):
    def turn(self, events, execute=None, **options):
        return stream_tool_turn(events=events, execute_tool=execute or MagicMock(return_value={}),
            input="fixture", model="model", instructions="instructions", tools=[], reasoning={},
            parallel_tool_calls=True, max_output_tokens=100, max_tool_iterations=options.pop("iterations", 2),
            metadata={"agent_id": "fixture"}, result_metadata={"owner": "fixture"}, **options)

    async def test_tool_result_continues_the_same_native_response_and_keeps_wire_metadata(self):
        requests, closed = [], []
        call = SimpleNamespace(type="function_call", id="item", call_id="call", name="read", arguments='{"value":7}')
        first = SimpleNamespace(id="first", output=[call])
        final = SimpleNamespace(id="final", output=[])

        async def events(**request):
            requests.append(request)
            try:
                response = first if len(requests) == 1 else final
                yield event("response.created", response=response)
                if response is first:
                    yield event("response.output_item.added", item=call)
                    yield event("response.function_call_arguments.done", item_id="item", name="read", arguments=call.arguments)
                else:
                    yield event("response.output_text.delta", delta="answer")
                yield event("response.completed", response=response)
            finally:
                closed.append(True)

        execute = MagicMock(return_value={"rows": [7]})
        frames = [frame async for frame in self.turn(events, execute, previous_response_id="prior",
                  tool_metadata={"read": {"display_name": "Read data", "fallback": True}})]
        execute.assert_called_once_with("read", {"value": 7})
        self.assertEqual(requests[0]["previous_response_id"], "prior")
        self.assertEqual(requests[1]["previous_response_id"], "first")
        self.assertEqual(json.loads(requests[1]["input"][0]["output"]), {"rows": [7]})
        self.assertEqual([data for name, data in frames if name == "tool_call_start"][0]["display_name"], "Read data")
        self.assertEqual([data for name, data in frames if name == "tool_result"][0]["owner"], "fixture")
        self.assertEqual(frames[-1], ("done", {"response_id": "final", "incomplete": ""}))
        self.assertEqual(len(closed), 2)

    async def test_iteration_limit_and_tool_denial_are_preserved(self):
        call = SimpleNamespace(type="function_call", call_id="call", name="unconfigured", arguments="{}")

        async def events(**request):
            yield event("response.completed", response=SimpleNamespace(id="response", output=[call]))

        execute = MagicMock(side_effect=ValueError("unknown or unconfigured tool"))
        frames = [frame async for frame in self.turn(events, execute, iterations=1)]
        self.assertEqual(frames[-1], ("error", {"error": "agent exceeded 1 tool iterations"}))
        self.assertEqual([data for name, data in frames if name == "tool_result"][0]["result"]["error"], "ValueError")
        execute.assert_called_once()

    async def test_truncated_or_failed_stream_never_reports_done(self):
        for failure in (None, "response.failed"):
            closed = []

            async def events(**request):
                try:
                    yield event("response.output_text.delta", delta="partial")
                    if failure:
                        yield event(failure, response=SimpleNamespace(error="private detail"))
                finally:
                    closed.append(True)

            frames = []
            with self.assertRaises(RuntimeError) as caught:
                async for frame in self.turn(events):
                    frames.append(frame)
            self.assertNotIn("private detail", str(caught.exception))
            self.assertNotIn("done", [name for name, data in frames])
            self.assertEqual(closed, [True])

    async def test_invalid_budget_refuses_before_model_or_tool(self):
        events, execute = MagicMock(), MagicMock()
        with self.assertRaises(ValueError):
            [frame async for frame in self.turn(events, execute, iterations=0)]
        events.assert_not_called()
        execute.assert_not_called()


class ClientLifetimeTests(unittest.TestCase):
    def test_close_is_lazy_idempotent_and_does_not_close_borrowed_objects(self):
        credential, borrowed = MagicMock(), MagicMock()
        for injected in (None, borrowed):
            client = AzureLlmClient(LlmConfig("https://fixture.openai.azure.com/openai/v1/"),
                                    credential=credential, client=injected)
            client.close()
            client.close()
            with self.assertRaisesRegex(RuntimeError, "closed"):
                client.client
        credential.close.assert_not_called()
        borrowed.close.assert_not_called()

    def test_close_closes_each_owned_native_client_once(self):
        client = AzureLlmClient(LlmConfig("https://fixture.openai.azure.com/openai/v1/"))
        native, embeddings = MagicMock(), MagicMock()
        client._client, client._embeddings_client = native, embeddings
        client.close()
        client.close()
        native.close.assert_called_once()
        embeddings.close.assert_called_once()