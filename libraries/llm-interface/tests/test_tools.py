import json
import unittest
from unittest.mock import patch

import httpx

from llm_interface import Limits, LlmError, connect
from test_framework_comparison import response_value


def tool_response(arguments, *, name="lookup", status="completed"):
    call = {"id": "fc", "type": "function_call", "call_id": "call", "name": name,
            "arguments": arguments, "status": "completed"}
    payload = response_value("resp", [call], status)
    if status == "incomplete":
        payload["incomplete_details"] = {"reason": "max_output_tokens"}
    return payload


class ToolSafetyTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        blocker = patch("socket.socket.connect", side_effect=AssertionError("Network forbidden"))
        blocker.start()
        self.addCleanup(blocker.stop)

    async def test_invalid_or_ungranted_calls_never_execute(self):
        for name, arguments, status in (("lookup", '{"value":"wrong type"}', "completed"),
                                         ("lookup", '{"value":1,"extra":true}', "completed"),
                                         ("foreign", '{"value":1}', "completed"),
                                         ("lookup", '{"value":1}', "incomplete")):
            calls = []
            requests = []
            def lookup(value: int) -> dict:
                """Return the fixture value."""
                calls.append(value)
                return {"value": value}
            async def handle(request):
                requests.append(request)
                return httpx.Response(200, json=tool_response(arguments, name=name, status=status))
            async with connect("https://fixture.invalid/v1", "fixture-model", provider="openai", credential="offline-fixture",
                               allow_model_calls=True, allowed_tools=("lookup",), transport=httpx.MockTransport(handle)) as model:
                with self.assertRaises(LlmError):
                    await model.agent(instructions="Use the tool.", tools=[lookup]).run("fixture")
            self.assertEqual(calls, [])
            self.assertEqual(len(requests), 1)

    async def test_tool_error_is_sanitized_and_prevents_replay(self):
        requests = []
        def lookup(value: int) -> dict:
            """Return the fixture value."""
            raise RuntimeError("private-tool-fixture-payload")
        async def handle(request):
            requests.append(request)
            return httpx.Response(200, json=tool_response('{"value":1}'))
        async with connect("https://fixture.invalid/v1", "fixture-model", provider="openai", credential="offline-fixture",
                           allow_model_calls=True, allowed_tools=("lookup",), transport=httpx.MockTransport(handle)) as model:
            agent = model.agent(instructions="Use the tool.", tools=[lookup])
            session = agent.create_session()
            with self.assertLogs("agent_framework", level="WARNING") as captured:
                with self.assertRaises(LlmError) as failed:
                    await agent.run("fixture", session=session)
            self.assertEqual(failed.exception.code, "tool_failed")
            self.assertNotIn("private-tool-fixture-payload", "\n".join(captured.output))
            with self.assertRaises(LlmError) as replay:
                agent.run("retry", session=session)
            self.assertEqual(replay.exception.code, "session_interrupted")
        self.assertEqual(len(requests), 1)

    async def test_tool_result_limit_and_missing_grant(self):
        def lookup(value: int) -> dict:
            """Return the fixture value."""
            return {"value": "x" * 2000}
        async def handle(request):
            return httpx.Response(200, json=tool_response('{"value":1}'))
        async with connect("https://fixture.invalid/v1", "fixture-model", provider="openai", credential="offline-fixture",
                           allow_model_calls=True, allowed_tools=("lookup",), limits=Limits(max_tool_result_bytes=100),
                           transport=httpx.MockTransport(handle)) as model:
            with self.assertRaises(LlmError) as failed:
                await model.agent(instructions="Use the tool.", tools=[lookup]).run("fixture")
            self.assertEqual(failed.exception.code, "tool_result_limit")
        async with connect("https://fixture.invalid/v1", "fixture-model", provider="openai", credential="offline-fixture") as model:
            with self.assertRaises(LlmError) as failed:
                model.agent(instructions="Use the tool.", tools=[lookup])
            self.assertEqual(failed.exception.code, "tool_not_granted")