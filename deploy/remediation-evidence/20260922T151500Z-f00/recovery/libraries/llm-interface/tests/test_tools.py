import json
import unittest
from unittest.mock import patch

import httpx

from llm_interface import Limits, LlmError, connect, tool
from test_framework_comparison import response_value
from test_safety import answer


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

    async def test_mapping_schema_constraints_and_local_references(self):
        schema = {"type": "object", "additionalProperties": False,
                  "$defs": {"payload": {"type": "object", "additionalProperties": False,
                      "properties": {"count": {"type": "integer", "minimum": 1},
                                     "mode": {"enum": ["include", "exclude"]}},
                      "required": ["count", "mode"]}},
                  "properties": {"payload": {"$ref": "#/$defs/payload"}}, "required": ["payload"]}
        cases = [({"payload": {"count": 1, "mode": "include"}}, True),
                 ({"payload": {"count": 0, "mode": "include"}}, False),
                 ({"payload": {"count": True, "mode": "include"}}, False),
                 ({"payload": {"count": 1, "mode": "other"}}, False),
                 ({"payload": {"count": 1}}, False),
                 ({"payload": {"count": 1, "mode": "include", "extra": True}}, False)]
        for arguments, valid in cases:
            with self.subTest(arguments=arguments):
                calls, requests = [], []

                def lookup(payload: dict) -> dict:
                    """Return the constrained fixture payload."""
                    calls.append(payload)
                    return payload

                async def handle(request):
                    requests.append(json.loads(request.content))
                    return httpx.Response(200, json=tool_response(json.dumps(arguments)) if len(requests) == 1 else answer("Fixture complete."))

                async with connect("https://fixture.invalid/v1", "fixture-model", provider="openai", credential="offline-fixture",
                                   allow_model_calls=True, allowed_tools=("lookup",), transport=httpx.MockTransport(handle)) as model:
                    agent = model.agent(instructions="Use the fixture tool.", tools=[tool(lookup, schema=schema)])
                    if valid:
                        result = await agent.run("fixture")
                        self.assertEqual(result.text, "Fixture complete.")
                    else:
                        with self.assertRaises(LlmError) as failure:
                            await agent.run("fixture")
                        self.assertEqual(failure.exception.code, "invalid_tool_arguments")
                self.assertEqual(len(calls), 1 if valid else 0)
                self.assertEqual(len(requests), 2 if valid else 1)
                self.assertEqual(requests[0]["tools"][0]["parameters"], schema)

    async def test_invalid_mapping_batch_prevents_every_tool_execution(self):
        calls = []

        def lookup(value: int) -> dict:
            """Return a bounded fixture value."""
            calls.append(value)
            return {"value": value}

        schema = {"type": "object", "properties": {"value": {"type": "integer", "minimum": 1}},
                  "required": ["value"], "additionalProperties": False}

        async def handle(_request):
            response = tool_response('{"value":1}')
            invalid = {**response["output"][0], "id": "fc2", "call_id": "call2", "arguments": '{"value":0}'}
            response["output"].append(invalid)
            return httpx.Response(200, json=response)

        async with connect("https://fixture.invalid/v1", "fixture-model", provider="openai", credential="offline-fixture",
                           allow_model_calls=True, allowed_tools=("lookup",), transport=httpx.MockTransport(handle)) as model:
            with self.assertRaises(LlmError) as failure:
                await model.agent(instructions="Use the tools.", tools=[tool(lookup, schema=schema)]).run("fixture")
            self.assertEqual(failure.exception.code, "invalid_tool_arguments")
        self.assertEqual(calls, [])

    async def test_remote_schema_reference_never_fetches_or_executes(self):
        calls, requests = [], []

        def lookup(value: int) -> dict:
            """Return a fixture value."""
            calls.append(value)
            return {"value": value}

        schema = {"type": "object", "properties": {"value": {"$ref": "https://untrusted.invalid/schema"}}, "required": ["value"]}

        async def handle(request):
            requests.append(request)
            return httpx.Response(200, json=tool_response('{"value":1}'))

        async with connect("https://fixture.invalid/v1", "fixture-model", provider="openai", credential="offline-fixture",
                           allow_model_calls=True, allowed_tools=("lookup",), transport=httpx.MockTransport(handle)) as model:
            with self.assertRaises(LlmError) as failure:
                await model.agent(instructions="Use the tool.", tools=[tool(lookup, schema=schema)]).run("fixture")
            self.assertEqual(failure.exception.code, "invalid_tool_arguments")
        self.assertEqual(len(requests), 1)
        self.assertEqual(calls, [])

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