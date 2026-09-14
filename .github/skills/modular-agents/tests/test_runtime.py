"""The same authenticated invocation contract for socket and cloud adapters."""

from __future__ import annotations

import asyncio
import json
import unittest

from test_definition import ROOT
from hostedagents import load_definition
from hostedagents.application import create_app, local_authorizer
from hostedagents.engine import AgentRuntime, InvocationRefused, TERMINAL_EVENTS
from hostedagents.policy import RuntimePolicy
from starlette.testclient import TestClient


class ModelFixture:
    def __init__(self):
        self.messages = []

    async def complete(self, **kwargs):
        self.messages.append(json.loads(json.dumps(kwargs)))
        if len(self.messages) == 1:
            return {"tool_calls": [{
                "id": "call-fixture", "type": "function",
                "function": {"name": "search_notes", "arguments": '{"query":"hosting"}'},
            }]}
        return {"content": "Hosting: Foundry hosted agents run a portable flat source bundle."}


class RuntimeTests(unittest.TestCase):
    def runtime(self, *, enabled=True):
        definition = load_definition(ROOT / "examples/control", allowed_prefixes=("agent_tools.",))
        self.model = ModelFixture()
        policy = RuntimePolicy(allowed_tools=("search_notes", "list_topics"), allow_model=True) if enabled else RuntimePolicy()
        return AgentRuntime(definition, policy, model=self.model if enabled else None)

    def test_configuration_tools_and_result_readback_use_one_service(self):
        runtime = self.runtime()

        async def run():
            return [item async for item in runtime.chat_events("hosting?", principal="alice", turn_id="turn-1")]

        events = asyncio.run(run())
        self.assertEqual([event for event, _ in events if event in TERMINAL_EVENTS], ["done"])
        self.assertTrue(any(event == "tool_result" for event, _ in events))
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

        async def failure(**_kwargs):
            raise RuntimeError("sensitive upstream body")

        runtime.model.complete = failure

        async def run():
            return [item async for item in runtime.chat_events("hello", principal="alice")]

        events = asyncio.run(run())
        self.assertEqual(events[-1][0], "error")
        self.assertNotIn("sensitive upstream body", json.dumps(events))

    def test_cancel_checks_owner_and_stops_an_async_model(self):
        async def run():
            runtime = self.runtime()
            entered = asyncio.Event()

            async def waiting(**_kwargs):
                entered.set()
                await asyncio.Event().wait()

            runtime.model.complete = waiting

            async def collect():
                return [item async for item in runtime.chat_events("hello", principal="alice", turn_id="cancel-me")]

            task = asyncio.create_task(collect())
            await entered.wait()
            with self.assertRaises(InvocationRefused):
                runtime.abort("cancel-me", principal="bob")
            runtime.abort("cancel-me", principal="alice")
            events = await asyncio.wait_for(task, timeout=2)
            self.assertEqual([event for event, _ in events if event in TERMINAL_EVENTS], ["aborted"])
            self.assertEqual(runtime.result("cancel-me", principal="alice")["status"], "aborted")

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()