"""The situation summary stream: same envelope as the JSON route, delivered as it is made."""

from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from unittest import mock

import httpx
from llm_interface import LlmError, RunEvent, connect
from app.cybereye.backend.agents.config import load_agent_spec
from app.cybereye.tests.test_native_agent import completion

from app.cybereye.backend.agents.service import AgentService
from app.cybereye.backend.agents.config import AgentSpec
from app.cybereye.backend.models import Pattern, Situation

FIRST = datetime(2026, 8, 13, 2, 30, tzinfo=timezone.utc)
LAST = datetime(2026, 8, 13, 3, 40, tzinfo=timezone.utc)


def situation() -> Situation:
    return Situation(
        situation_id="sit-1", host="svpmn082", principal="admLRhodes", severity="critical",
        confidence="high", first_seen=FIRST, last_seen=LAST, detector_count=1,
        patterns=[Pattern(
            detector="cybereye", rule_id="explicit_credential_burst", rule_version="1.0.0",
            label="Explicit credential use", description="Five or more event 4648 records.",
            observed_fact="30 event-4648 records", count=30, score=35, confidence="high",
            role="anchor", behaviour_class="credential_use", first_seen=FIRST, last_seen=LAST,
            summary="Explicit credential use observed on one host.",
            evidence_columns=["resource_id"], evidence_ids=["r1"],
            evidence_semantics="Sampled resource ids.", derivation={},
        )],
    )


class RouteTests(unittest.TestCase):
    def test_both_the_streaming_and_the_json_summary_routes_are_registered(self) -> None:
        from app.cybereye.backend import main

        paths = {getattr(route, "path", "") for route in main.app.routes}
        self.assertIn("/api/cyber/situations/summary", paths)
        self.assertIn("/api/cyber/situations/summary/stream", paths)
        route = next(item for item in main.app.routes
                     if getattr(item, "path", "") == "/api/cyber/situations/summary/stream")
        self.assertEqual(sorted(route.methods), ["POST"])


class NativeSummaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_native_deltas_form_one_summary_and_completed_terminal(self):
        requests = []

        async def handle(request):
            requests.append(request)
            return completion([({"role": "assistant", "content": "Thirty explicit "}, None),
                               ({"content": "credential events."}, None), ({}, "stop")])

        async with connect("https://fixture.invalid/v1", "fixture-model", provider="openai_completions",
                           credential="offline-fixture", allow_model_calls=True,
                           transport=httpx.MockTransport(handle)) as connection:
            service = AgentService(object(), object(), replace(load_agent_spec(), model="fixture-model", tools=()),
                                   connection=connection)
            events = [item async for item in service.stream_summary(situation(), principal="owner")]
            self.assertEqual([name for name, _ in events][-2:], ["summary", "done"])
            self.assertEqual(events[-2][1]["summary"], "Thirty explicit credential events.")
            self.assertEqual(events[-1][1]["status"], "completed")
            self.assertEqual(len(requests), 1)

    async def test_native_transport_failure_never_retries_or_emits_summary(self):
        requests = []

        async def handle(request):
            requests.append(request)
            raise httpx.ReadError("private-provider-context")

        async with connect("https://fixture.invalid/v1", "fixture-model", provider="openai_completions",
                           credential="offline-fixture", allow_model_calls=True,
                           transport=httpx.MockTransport(handle)) as connection:
            service = AgentService(object(), object(), replace(load_agent_spec(), model="fixture-model", tools=()),
                                   connection=connection)
            events = []
            with self.assertRaises(LlmError) as failure:
                async for item in service.stream_summary(situation(), principal="owner"):
                    events.append(item)
            self.assertNotIn("private-provider-context", str(failure.exception))
            self.assertNotIn("summary", [name for name, _ in events])
            self.assertEqual(len(requests), 1)

    def test_native_reasoning_summary_closes_at_terminal_without_duplicate_text(self):
        service = AgentService.__new__(AgentService)
        names, reasoning = {}, {}
        events = [RunEvent("reasoning.summary.delta", "run", 1, {"id": "summary", "text": "Observed "}),
                  RunEvent("reasoning.summary.delta", "run", 2, {"id": "summary", "text": "events."}),
                  RunEvent("run.completed", "run", 3, {"session_id": "session"})]
        frames = [frame for event in events for frame in service._frames(event, names, reasoning)]
        self.assertEqual([name for name, _ in frames],
                         ["reasoning_start", "reasoning_delta", "reasoning_delta", "reasoning_end", "done"])
        self.assertEqual(frames[-2][1]["text"], "Observed events.")


if __name__ == "__main__":
    unittest.main()
