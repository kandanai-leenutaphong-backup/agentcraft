import unittest
from unittest.mock import patch

import httpx

from llm_interface import Limits, LlmError, connect, report_progress
from test_connection import Credential
from test_framework_comparison import ModelFixture


class AgentTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        blocker = patch("socket.socket.connect", side_effect=AssertionError("Network forbidden"))
        blocker.start()
        self.addCleanup(blocker.stop)

    async def test_same_few_line_agent_for_both_protocols(self):
        for protocol in ("responses", "completions"):
            with self.subTest(protocol=protocol):
                fixture = ModelFixture(protocol)
                calls = []

                async def lookup_fixture(asset_id: str) -> dict:
                    """Read one synthetic asset status."""
                    calls.append(asset_id)
                    await report_progress({"name": "lookup_fixture", "step": "read"})
                    return {"asset_id": asset_id, "status": "verified fixture"}

                provider = "openai" if protocol == "responses" else "openai_completions"
                async with connect("https://fixture.invalid/v1", "fixture-model", provider=provider,
                                   credential="offline-fixture", allow_model_calls=True, allowed_tools=("lookup_fixture",),
                                   transport=httpx.MockTransport(fixture.handle)) as connection:
                    agent = connection.agent(instructions="Use the registered tool.", tools=[lookup_fixture])
                    session = agent.create_session(principal="owner")
                    stream = agent.run("Check the fixture.", session=session, principal="owner", stream=True)
                    events = [event async for event in stream]
                    final = await stream.get_final_response()
                    self.assertEqual(final.text, "Fixture verified.")
                    self.assertEqual(calls, ["fixture"])
                    self.assertEqual(len(fixture.requests), 2)
                    kinds = [event.kind for event in events]
                    self.assertIn("tool.progress", kinds)
                    self.assertIn("tool.result", kinds)
                    self.assertLess(kinds.index("tool.call.delta"), kinds.index("tool.started"))
                    self.assertEqual(kinds[-1], "run.completed")
                    self.assertEqual(session.result(principal="owner").text, final.text)
                    with self.assertRaises(LlmError):
                        session.result(principal="other")

    async def test_tool_authorizer_denial_stops_next_model_call(self):
        fixture = ModelFixture("responses")
        calls = []

        async def lookup_fixture(asset_id: str) -> dict:
            """Read a synthetic fixture."""
            calls.append(asset_id)
            return {"status": "verified fixture"}

        async with connect("https://fixture.invalid/v1", "fixture-model", provider="openai",
                           credential="offline-fixture", allow_model_calls=True, allowed_tools=("lookup_fixture",),
                           transport=httpx.MockTransport(fixture.handle)) as connection:
            agent = connection.agent(instructions="Use the tool.", tools=[lookup_fixture], authorize_tool=lambda call: False)
            stream = agent.run("fixture", stream=True)
            events = []
            with self.assertRaises(LlmError) as denied:
                async for event in stream:
                    events.append(event)
            self.assertEqual(denied.exception.code, "tool_authorization_denied")
            self.assertEqual(calls, [])
            self.assertEqual(len(fixture.requests), 1)
            self.assertEqual(events[-1].kind, "run.failed")

    async def test_model_budget_is_shared_by_inner_calls(self):
        fixture = ModelFixture("responses")

        async def lookup_fixture(asset_id: str) -> dict:
            """Read a synthetic fixture."""
            return {"status": "verified fixture"}

        async with connect("https://fixture.invalid/v1", "fixture-model", provider="openai",
                           credential="offline-fixture", allow_model_calls=True, allowed_tools=("lookup_fixture",),
                           limits=Limits(max_model_calls=1), transport=httpx.MockTransport(fixture.handle)) as connection:
            stream = connection.agent(instructions="Use the tool.", tools=[lookup_fixture]).run("fixture", stream=True)
            with self.assertRaises(LlmError):
                await stream.get_final_response()
            self.assertEqual(len(fixture.requests), 1)

    async def test_owner_and_binding_refuse_before_native_io(self):
        async with connect("https://fixture.invalid", "fixture-model", credential=Credential(), allow_model_calls=True) as connection:
            agent = connection.agent(instructions="First definition.")
            session = agent.create_session(principal="owner")
            with self.assertRaises(LlmError):
                agent.run("fixture", session=session, principal="other")
            other = connection.agent(instructions="Changed definition.")
            with self.assertRaises(LlmError):
                other.run("fixture", session=session, principal="owner")