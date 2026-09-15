"""Adversarial contract tests for the chat session lifecycle.

The agent itself is never called: `stream_turn` is replaced with scripted async generators so
that every failure mode is deterministic and no Azure OpenAI request is made.
"""

from __future__ import annotations

import asyncio
import json
import time
import unittest
from collections.abc import AsyncIterator
from typing import Any
from unittest import mock

from fastapi.testclient import TestClient

from app.cybereye.backend import main as backend
from app.cybereye.backend.api import chat as chat_api
from app.cybereye.backend.models import ChatRequest
from app.cybereye.backend.security import ChatSession, SessionStore

import _auth_support

OWNER = _auth_support.DEFAULT.id
SECOND = _auth_support.OTHER.id


def frames(body: str) -> list[tuple[str, dict[str, Any]]]:
    """Parse an SSE body into (event, data) pairs."""
    parsed: list[tuple[str, dict[str, Any]]] = []
    for block in body.replace("\r\n", "\n").split("\n\n"):
        event, payload = "", ""
        for line in block.split("\n"):
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("data:"):
                payload += line[5:].strip()
        if event and payload:
            parsed.append((event, json.loads(payload)))
    return parsed


class FakeAgent:
    """Scripted stand-in for AgentService.stream_turn."""

    def __init__(self, script) -> None:
        self.script = script
        self.calls: list[str | None] = []

    async def stream_turn(self, message: str, *, previous_response_id, situation):
        self.calls.append(previous_response_id)
        async for item in self.script(self, message, previous_response_id):
            yield item


async def happy(agent: FakeAgent, message: str, previous: str | None) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    yield "status", {"phase": "model", "label": "Connecting to model…"}
    yield "metadata", {"response_id": f"resp_{len(agent.calls)}", "model": "test-model"}
    yield "token", {"token": "ok"}
    yield "done", {}


def client_with(agent: Any) -> TestClient:
    """A TestClient whose lifespan is real except that the agent and ADX are stubbed.

    The authorization gate is real too: the client authenticates through the same resolver
    seam Entra will use, so nothing here proves a route works with the gate switched off.
    """
    _auth_support.install(backend.app)
    client = TestClient(backend.app)
    client.__enter__()
    client.app.state.agent = agent
    return client


class SessionStoreTests(unittest.TestCase):
    def test_unknown_and_malformed_ids_are_rejected_not_created(self) -> None:
        store = SessionStore()
        for candidate in ["", " ", "../../etc/passwd", "a" * 4096, "%00", "null", "0"]:
            self.assertIsNone(store.get(candidate, OWNER), candidate)
        self.assertEqual(len(store), 0)

    def test_store_is_bounded_and_evicts_the_least_recently_used(self) -> None:
        store = SessionStore(max_sessions=3)
        first = store.create(OWNER)
        second = store.create(OWNER)
        third = store.create(OWNER)
        self.assertIsNotNone(store.get(first, OWNER))  # refresh first, making second the LRU
        fourth = store.create(OWNER)
        self.assertEqual(len(store), 3)
        self.assertIsNone(store.get(second, OWNER))
        for survivor in (first, third, fourth):
            self.assertIsNotNone(store.get(survivor, OWNER))

    def test_idle_sessions_expire_and_are_not_resurrected(self) -> None:
        store = SessionStore(idle_seconds=0.0)
        session_id = store.create(OWNER)
        time.sleep(0.01)
        self.assertIsNone(store.get(session_id, OWNER))
        self.assertEqual(len(store), 0)
        self.assertIsNone(store.get(session_id, OWNER))

    def test_created_ids_are_unique_and_opaque(self) -> None:
        store = SessionStore(max_sessions=500)
        ids = {store.create(OWNER) for _ in range(400)}
        self.assertEqual(len(ids), 400)
        self.assertTrue(all(len(value) == 32 and value.isalnum() for value in ids))

    def test_another_caller_gets_the_same_answer_as_a_session_that_never_existed(self) -> None:
        store = SessionStore()
        session_id = store.create(OWNER)
        self.assertIsNone(store.get(session_id, SECOND))
        self.assertIsNone(store.get("never-existed", SECOND))
        # Denial must not consume the session for its real owner.
        self.assertIsNotNone(store.get(session_id, OWNER))

    def test_a_session_needs_an_owner(self) -> None:
        store = SessionStore()
        with self.assertRaises(ValueError):
            store.create("")
        session_id = store.create(OWNER)
        self.assertIsNone(store.get(session_id, ""))


class StaleThreadTests(unittest.TestCase):
    def test_marker_matches_only_a_stale_previous_response(self) -> None:
        stale = [
            Exception("Previous response with id 'resp_1' not found."),
            Exception("The previous response has expired"),
        ]
        other = [
            Exception("rate limit exceeded"),
            Exception("previous response was long"),
            Exception("not found"),
            asyncio.TimeoutError(),
        ]
        for exc in stale:
            self.assertTrue(chat_api._stale_thread(exc), exc)
        for exc in other:
            self.assertFalse(chat_api._stale_thread(exc), exc)


class ChatRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        patcher = mock.patch.object(backend, "ReadOnlyAdx")
        self.addCleanup(patcher.stop)
        patcher.start()
        scanner = mock.patch.object(backend, "Scanner")
        self.addCleanup(scanner.stop)
        scanner.start()
        service = mock.patch.object(backend, "AgentService")
        self.addCleanup(service.stop)
        service.start()

    def open_client(self, agent: Any) -> TestClient:
        client = client_with(agent)
        self.addCleanup(client.__exit__, None, None, None)
        return client

    def test_unknown_session_is_404_and_never_auto_creates(self) -> None:
        agent = FakeAgent(happy)
        client = self.open_client(agent)
        response = client.post("/api/chat/deadbeef", json={"message": "hello"})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "unknown session")
        self.assertEqual(len(client.app.state.sessions), 0)
        self.assertEqual(agent.calls, [])

    def test_a_fresh_session_carries_the_response_id_forward(self) -> None:
        agent = FakeAgent(happy)
        client = self.open_client(agent)
        session_id = client.post("/api/sessions").json()["session_id"]
        client.post(f"/api/chat/{session_id}", json={"message": "one"})
        client.post(f"/api/chat/{session_id}", json={"message": "two"})
        self.assertEqual(agent.calls, [None, "resp_1"])

    def test_sessions_are_isolated_from_one_another(self) -> None:
        agent = FakeAgent(happy)
        client = self.open_client(agent)
        first = client.post("/api/sessions").json()["session_id"]
        second = client.post("/api/sessions").json()["session_id"]
        self.assertNotEqual(first, second)
        client.post(f"/api/chat/{first}", json={"message": "one"})
        client.post(f"/api/chat/{second}", json={"message": "two"})
        self.assertEqual(agent.calls, [None, None])

    def test_a_stale_response_id_is_dropped_and_the_turn_replays_clean(self) -> None:
        async def stale_once(agent: FakeAgent, message: str, previous: str | None):
            if previous is not None:
                raise RuntimeError("Previous response with id 'resp_1' not found.")
            async for item in happy(agent, message, previous):
                yield item

        agent = FakeAgent(stale_once)
        client = self.open_client(agent)
        session_id = client.post("/api/sessions").json()["session_id"]
        client.post(f"/api/chat/{session_id}", json={"message": "one"})
        body = client.post(f"/api/chat/{session_id}", json={"message": "two"}).text
        events = [event for event, _ in frames(body)]
        self.assertNotIn("error", events)
        self.assertIn("done", events)
        self.assertEqual(agent.calls, [None, "resp_1", None])
        self.assertEqual(sum(1 for event, _ in frames(body) if event == "token"), 1)

    def test_a_stale_failure_after_visible_output_is_reported_not_replayed(self) -> None:
        async def late_failure(agent: FakeAgent, message: str, previous: str | None):
            yield "token", {"token": "partial"}
            raise RuntimeError("Previous response with id 'resp_1' not found.")

        agent = FakeAgent(late_failure)
        client = self.open_client(agent)
        session_id = client.post("/api/sessions").json()["session_id"]
        body = client.post(f"/api/chat/{session_id}", json={"message": "one"}).text
        events = [event for event, _ in frames(body)]
        self.assertEqual(events.count("token"), 1)
        self.assertIn("error", events)
        self.assertEqual(len(agent.calls), 1)

    def test_an_unrelated_failure_is_surfaced_without_a_retry(self) -> None:
        async def blows_up(agent: FakeAgent, message: str, previous: str | None):
            raise RuntimeError("rate limit exceeded")
            yield  # pragma: no cover - generator marker

        agent = FakeAgent(blows_up)
        client = self.open_client(agent)
        session_id = client.post("/api/sessions").json()["session_id"]
        body = client.post(f"/api/chat/{session_id}", json={"message": "one"}).text
        errors = [data for event, data in frames(body) if event == "error"]
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]["error"], "RuntimeError")
        self.assertEqual(errors[0]["detail"], "rate limit exceeded")
        self.assertEqual(len(agent.calls), 1)

    def test_a_failed_turn_leaves_the_session_usable(self) -> None:
        state = {"fail": True}

        async def fail_then_recover(agent: FakeAgent, message: str, previous: str | None):
            if state["fail"]:
                state["fail"] = False
                raise RuntimeError("transient upstream error")
            async for item in happy(agent, message, previous):
                yield item

        agent = FakeAgent(fail_then_recover)
        client = self.open_client(agent)
        session_id = client.post("/api/sessions").json()["session_id"]
        client.post(f"/api/chat/{session_id}", json={"message": "one"})
        body = client.post(f"/api/chat/{session_id}", json={"message": "two"}).text
        self.assertIn("done", [event for event, _ in frames(body)])

    def test_oversized_and_empty_messages_are_rejected_before_the_agent(self) -> None:
        agent = FakeAgent(happy)
        client = self.open_client(agent)
        session_id = client.post("/api/sessions").json()["session_id"]
        for payload in [{"message": ""}, {"message": "x" * 8001}, {}, {"message": None}]:
            response = client.post(f"/api/chat/{session_id}", json=payload)
            self.assertEqual(response.status_code, 422, payload)
        self.assertEqual(agent.calls, [])

    def test_a_malformed_situation_envelope_is_rejected_not_forwarded(self) -> None:
        agent = FakeAgent(happy)
        client = self.open_client(agent)
        session_id = client.post("/api/sessions").json()["session_id"]
        response = client.post(
            f"/api/chat/{session_id}",
            json={"message": "hi", "situation": {"situation_id": "x"}},
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(agent.calls, [])


class ConcurrencyTests(unittest.IsolatedAsyncioTestCase):
    async def test_the_session_lock_serialises_overlapping_turns(self) -> None:
        session = ChatSession(owner_id=OWNER)
        order: list[str] = []

        async def turn(name: str) -> None:
            async with session.lock:
                order.append(f"{name}-start")
                await asyncio.sleep(0.01)
                order.append(f"{name}-end")

        await asyncio.gather(turn("a"), turn("b"))
        self.assertEqual(order, ["a-start", "a-end", "b-start", "b-end"])

    async def test_cancelling_a_turn_releases_the_lock_and_leaves_the_id_intact(self) -> None:
        session = ChatSession(owner_id=OWNER)
        session.previous_response_id = "resp_keep"

        async def never_ends(message: str, *, previous_response_id, situation):
            yield "status", {"label": "working"}
            await asyncio.Event().wait()

        agent = mock.Mock()
        agent.stream_turn = never_ends
        body = ChatRequest(message="one")

        async def consume() -> None:
            async with session.lock:
                async for _ in chat_api.run_chat_turn(agent, session, body, "sid"):
                    pass

        task = asyncio.create_task(consume())
        await asyncio.sleep(0.02)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertFalse(session.lock.locked())
        self.assertEqual(session.previous_response_id, "resp_keep")


if __name__ == "__main__":
    unittest.main()
