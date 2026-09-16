"""The same authenticated invocation contract for socket and cloud adapters."""

from __future__ import annotations

import asyncio
import json
import unittest
from unittest.mock import patch

import httpx
from test_definition import ROOT
from llm_interface import connect
from hostedagents import load_definition
from hostedagents.application import create_app, local_authorizer
from hostedagents.engine import AgentRuntime, InvocationRefused, TERMINAL_EVENTS
from hostedagents.policy import RuntimePolicy
from starlette.testclient import TestClient


class ModelFixture:
    def __init__(self):
        self.messages = []

    async def handle(self, request):
        self.messages.append(json.loads(request.content))
        if len(self.messages) == 1:
            delta = {"role": "assistant", "tool_calls": [{
                "index": 0, "id": "call-fixture", "type": "function",
                "function": {"name": "search_notes", "arguments": '{"query":"hosting"}'},
            }]}
            finish = "tool_calls"
        else:
            delta = {"role": "assistant", "content": "Hosting: Foundry hosted agents run a portable flat source bundle."}
            finish = "stop"
        chunks = [
            {"id": "fixture", "object": "chat.completion.chunk", "created": 0, "model": "example-deployment",
             "choices": [{"index": 0, "delta": value, "finish_reason": reason}]}
            for value, reason in ((delta, None), ({}, finish))
        ]
        content = "".join("data: " + json.dumps(chunk) + "\n\n" for chunk in chunks) + "data: [DONE]\n\n"
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=content)


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        blocked = patch("socket.socket.connect", side_effect=AssertionError("Network forbidden"))
        blocked.start()
        self.addCleanup(blocked.stop)

    def runtime(self, *, enabled=True, policy=None):
        definition = load_definition(ROOT / "examples/control", allowed_prefixes=("agent_tools.",))
        self.model = ModelFixture()
        policy = policy or (RuntimePolicy(allowed_tools=("search_notes", "list_topics"), allow_model=True) if enabled else RuntimePolicy())
        connection = connect(
            "https://fixture.invalid/v1", definition.spec.model, provider="openai_completions",
            credential="offline-fixture", policy=policy.execution_policy(),
            transport=httpx.MockTransport(lambda request: self.model.handle(request)),
        ) if enabled else None
        if connection is not None:
            self.addCleanup(lambda: asyncio.run(connection.aclose()))
        runtime = AgentRuntime(definition, policy, connection=connection)
        self.invocations = []
        invoke = runtime.tools.invoke

        async def counted(name, arguments):
            self.invocations.append(name)
            return await invoke(name, arguments)

        runtime.tools.invoke = counted
        return runtime

    def test_configuration_tools_and_result_readback_use_one_service(self):
        runtime = self.runtime()

        async def run():
            return [item async for item in runtime.chat_events("hosting?", principal="alice", turn_id="turn-1")]

        events = asyncio.run(run())
        self.assertEqual([event for event, _ in events if event in TERMINAL_EVENTS], ["done"])
        self.assertTrue(any(event == "tool_result" for event, _ in events))
        self.assertEqual(len(self.model.messages), 2)
        self.assertEqual(self.invocations, ["search_notes"])
        self.assertIn("Cite note titles", self.model.messages[0]["messages"][0]["content"])
        self.assertIn("portable flat source bundle", runtime.result("turn-1", principal="alice")["answer"])
        with self.assertRaises(InvocationRefused) as refused:
            runtime.result("turn-1", principal="bob")
        self.assertEqual(refused.exception.status, 404)
        with self.assertRaises(InvocationRefused):
            runtime.abort("turn-1", principal="bob")

    def test_denied_operations_do_not_reach_tools_or_model(self):
        runtime = self.runtime(enabled=False)
        with self.assertRaises(InvocationRefused):
            asyncio.run(runtime.call("list_topics", {}, principal="alice"))
        with self.assertRaises(InvocationRefused):
            runtime.prepare_chat("hello", principal="alice")
        self.assertEqual(self.model.messages, [])

    def test_http_auth_schema_refusal_recovery_and_stream(self):
        token = "offline-fixture-not-an-azure-credential-1234567890"
        runtime = self.runtime()
        with TestClient(create_app(runtime, authorize=local_authorizer(token))) as client:
            self.assertEqual(client.get("/readiness").status_code, 200)
            self.assertEqual(client.post("/invocations", json={}).status_code, 401)
            self.assertEqual(client.get("/unknown").status_code, 401)
            client.headers["Authorization"] = f"Bearer {token}"
            self.assertEqual(client.post("/invocations", json=[]).status_code, 400)
            self.assertEqual(client.post("/invocations", json={"op": "health", "token": "x"}).status_code, 400)
            self.assertEqual(client.post("/invocations", json={"op": "health"}).status_code, 200)
            response = client.post("/invocations", json={"op": "chat", "message": "hosting", "turn_id": "http-turn"})
            self.assertEqual(response.status_code, 200)
            self.assertIn("event: tool_result", response.text)
            self.assertEqual(response.text.count("event: done"), 1)
            result = client.post("/invocations", json={"op": "result", "turn_id": "http-turn"}).json()
            self.assertEqual(result["status"], "done")
            self.assertIn("portable flat source bundle", result["answer"])

    def test_model_failure_is_sanitized_and_terminal(self):
        runtime = self.runtime()

        async def failure(_request):
            raise RuntimeError("sensitive upstream body")

        self.model.handle = failure

        async def run():
            return [item async for item in runtime.chat_events("hello", principal="alice")]

        events = asyncio.run(run())
        self.assertEqual(events[-1][0], "error")
        self.assertNotIn("sensitive upstream body", json.dumps(events))

    def test_native_budget_exhaustion_does_not_start_a_second_model_request(self):
        runtime = self.runtime(policy=RuntimePolicy(
            allowed_tools=("search_notes", "list_topics"), allow_model=True, max_tool_rounds=1,
        ))

        async def run():
            return [item async for item in runtime.chat_events("hosting?", principal="alice", turn_id="budget")]

        events = asyncio.run(run())
        self.assertEqual(events[-1][0], "error")
        self.assertEqual(len(self.model.messages), 1)
        self.assertEqual(len(self.invocations), 1)
        self.assertEqual(runtime.result("budget", principal="alice")["status"], "error")

    def test_connection_policy_mismatch_refuses_before_native_io(self):
        runtime = self.runtime()
        with self.assertRaisesRegex(ValueError, "must match"):
            AgentRuntime(runtime.definition, RuntimePolicy(allow_model=True), connection=runtime.connection)
        self.assertEqual(self.model.messages, [])

    def test_close_refuses_new_work_and_preserves_a_borrowed_connection(self):
        async def run():
            runtime = self.runtime()
            await runtime.aclose()
            await runtime.aclose()
            with self.assertRaises(InvocationRefused):
                await runtime.call("list_topics", {}, principal="alice")
            with self.assertRaises(InvocationRefused):
                runtime.prepare_chat("hosting", principal="alice")
            binding = runtime.connection.agent(instructions="Borrowed connection remains caller-owned")
            self.assertIsNotNone(binding.create_session(principal="alice"))

        asyncio.run(run())

    def test_cancel_checks_owner_and_stops_an_async_model(self):
        async def run():
            runtime = self.runtime()
            entered = asyncio.Event()

            async def waiting(_request):
                entered.set()
                await asyncio.Event().wait()

            self.model.handle = waiting

            async def collect():
                return [item async for item in runtime.chat_events("hello", principal="alice", turn_id="cancel-me")]

            task = asyncio.create_task(collect())
            await asyncio.wait_for(entered.wait(), timeout=3)
            with self.assertRaises(InvocationRefused):
                runtime.abort("cancel-me", principal="bob")
            runtime.abort("cancel-me", principal="alice")
            events = await asyncio.wait_for(task, timeout=2)
            self.assertEqual([event for event, _ in events if event in TERMINAL_EVENTS], ["aborted"])
            self.assertEqual(runtime.result("cancel-me", principal="alice")["status"], "aborted")

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()