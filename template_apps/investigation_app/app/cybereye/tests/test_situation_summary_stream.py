"""The situation summary stream: same envelope as the JSON route, delivered as it is made."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from unittest import mock

import httpx

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


def event(type_name: str, **fields: Any) -> SimpleNamespace:
    return SimpleNamespace(type=type_name, **fields)


class ResponseTransportTests(unittest.IsolatedAsyncioTestCase):
    def service(self, attempts: list[list[Any]]) -> AgentService:
        agent = AgentService.__new__(AgentService)

        def replay(items: list[Any]):
            for item in items:
                if isinstance(item, BaseException):
                    raise item
                yield item

        agent.client = SimpleNamespace(responses=SimpleNamespace(create=mock.Mock(
            side_effect=[replay(items) for items in attempts],
        )))
        return agent

    async def test_transport_failure_before_output_retries_the_same_request_once(self) -> None:
        created = event("response.created", response=SimpleNamespace(id="unfinished"))
        completed = event("response.completed", response=SimpleNamespace(id="complete"))
        for preliminary in ([], [created, event("response.in_progress")],
                    [created, event("response.output_item.added", item=SimpleNamespace(type="reasoning"))]):
            with self.subTest(preliminary=len(preliminary)):
                agent = self.service([
                    [*preliminary, httpx.RemoteProtocolError("incomplete chunked read")],
                    [completed],
                ])
                request = {"model": "model", "previous_response_id": "prior",
                           "input": [{"type": "function_call_output", "call_id": "call-1", "output": "{}"}]}
                collected = [item async for item in agent._response_events(**request)]
                self.assertEqual(collected, [*preliminary, completed])
                self.assertEqual(agent.client.responses.create.call_args_list,
                                 [mock.call(**request, stream=True)] * 2)

    async def test_second_transport_failure_is_not_retried(self) -> None:
        agent = self.service([
            [httpx.RemoteProtocolError("first")],
            [httpx.RemoteProtocolError("second")],
        ])
        with self.assertRaisesRegex(httpx.RemoteProtocolError, "second"):
            _ = [item async for item in agent._response_events(model="model")]
        self.assertEqual(agent.client.responses.create.call_count, 2)

    async def test_visible_output_prevents_transport_replay(self) -> None:
        for kind in ("response.output_text.delta", "response.output_item.added",
                     "response.reasoning_summary_text.delta"):
            with self.subTest(kind=kind):
                visible = event(kind, item=SimpleNamespace(type="function_call"))
                agent = self.service([[visible, httpx.RemoteProtocolError("after output")]])
                collected = []
                with self.assertRaisesRegex(httpx.RemoteProtocolError, "after output"):
                    async for item in agent._response_events(model="model"):
                        collected.append(item)
                self.assertEqual(collected, [visible])
                self.assertEqual(agent.client.responses.create.call_count, 1)

    async def test_non_transport_failure_is_not_retried(self) -> None:
        agent = self.service([[ValueError("invalid response")]])
        with self.assertRaisesRegex(ValueError, "invalid response"):
            _ = [item async for item in agent._response_events(model="model")]
        self.assertEqual(agent.client.responses.create.call_count, 1)


class StreamSummaryTests(unittest.IsolatedAsyncioTestCase):
    def service(self, events: list[Any]) -> AgentService:
        agent = AgentService.__new__(AgentService)
        agent.spec = SimpleNamespace(model="gpt-5.6-luna", reasoning_effort="none",
                                     agent_id="cyber", name="CyberDefender", config_version=1)

        async def replay(**_: Any):
            for item in events:
                yield item

        agent._response_events = replay  # type: ignore[method-assign]
        return agent

    async def collect(self, events: list[Any]) -> list[tuple[str, dict[str, Any]]]:
        return [item async for item in self.service(events).stream_summary(situation())]

    async def test_tokens_are_the_models_own_deltas_and_end_in_one_envelope(self) -> None:
        response = SimpleNamespace(id="resp-1", output_text="Thirty explicit credential events.")
        collected = await self.collect([
            event("response.created", response=response),
            event("response.output_text.delta", delta="Thirty explicit "),
            event("response.output_text.delta", delta="credential events."),
            event("response.completed", response=response),
        ])
        names = [name for name, _ in collected]
        self.assertEqual(names.count("token"), 2)
        self.assertEqual(names[-2:], ["summary", "done"])
        payload = dict(collected[-2][1])
        self.assertEqual(payload["summary"], "Thirty explicit credential events.")
        self.assertEqual(payload["situation_id"], "sit-1")
        self.assertTrue(payload["historical_replay"])
        self.assertIsInstance(payload["elapsed_ms"], int)

    async def test_a_status_is_emitted_before_any_token(self) -> None:
        response = SimpleNamespace(id="resp-2", output_text="x")
        collected = await self.collect([
            event("response.created", response=response),
            event("response.output_text.delta", delta="x"),
            event("response.completed", response=response),
        ])
        names = [name for name, _ in collected]
        self.assertEqual(names[0], "status")
        self.assertLess(names.index("status"), names.index("token"))

    async def test_a_failed_stream_is_an_error_event_not_an_empty_summary(self) -> None:
        collected = await self.collect([
            event("response.created", response=SimpleNamespace(id="resp-3", output_text="")),
            event("response.failed", response=SimpleNamespace(error="model unavailable")),
        ])
        self.assertEqual(collected[-1][0], "error")
        self.assertNotIn("summary", [name for name, _ in collected])


class StreamTurnReasoningTests(unittest.IsolatedAsyncioTestCase):
    """Reasoning summary parts, as the installed SDK names them, become stream frames."""

    def service(self, events: list[Any]) -> tuple[AgentService, dict[str, Any]]:
        agent = AgentService.__new__(AgentService)
        agent.spec = AgentSpec(
            config_id="cfg", config_version=1, config_digest="0", agent_id="cyber",
            name="CyberDefender", description="", model="gpt-5.6-luna",
            reasoning_effort="high", reasoning_summary="auto", max_output_tokens=900,
            max_tool_iterations=1, diagnosis_max_output_tokens=900,
            diagnosis_max_tool_iterations=1, parallel_tool_calls=True,
            instructions="go", tools=(),
        )
        agent.tools = {}
        seen: dict[str, Any] = {}

        async def replay(**request: Any):
            seen.update(request)
            for item in events:
                yield item

        agent._response_events = replay  # type: ignore[method-assign]
        return agent, seen

    async def test_summary_parts_are_streamed_and_the_request_asks_for_them(self) -> None:
        done = SimpleNamespace(id="resp-9", output=[], output_text="answer")
        agent, seen = self.service([
            event("response.created", response=done),
            event("response.reasoning_summary_part.added", item_id="rs_1", summary_index=0),
            event("response.reasoning_summary_text.delta", item_id="rs_1", summary_index=0,
                  delta="Weighing the "),
            event("response.reasoning_summary_text.delta", item_id="rs_1", summary_index=0,
                  delta="logon burst."),
            event("response.reasoning_summary_text.done", item_id="rs_1", summary_index=0,
                  text="Weighing the logon burst."),
            event("response.output_text.delta", delta="answer"),
            event("response.completed", response=done),
        ])
        collected = [item async for item in agent.stream_turn(
            "go", previous_response_id=None, situation=None)]
        self.assertEqual(seen["reasoning"], {"effort": "high", "summary": "auto"})
        reasoning = [(name, data) for name, data in collected if name.startswith("reasoning")]
        self.assertEqual([name for name, _ in reasoning],
                         ["reasoning_start", "reasoning_delta", "reasoning_delta",
                          "reasoning_end"])
        # One id per summary part, so two parts never braid into one block.
        self.assertEqual({data["id"] for _, data in reasoning}, {"rs_1:0"})
        self.assertEqual("".join(data["delta"] for name, data in reasoning
                                 if name == "reasoning_delta"), "Weighing the logon burst.")

    async def test_a_turn_with_no_summary_emits_no_reasoning_frames(self) -> None:
        done = SimpleNamespace(id="resp-10", output=[], output_text="answer")
        agent, _ = self.service([
            event("response.created", response=done),
            event("response.output_text.delta", delta="answer"),
            event("response.completed", response=done),
        ])
        collected = [item async for item in agent.stream_turn(
            "go", previous_response_id=None, situation=None)]
        self.assertEqual([name for name, _ in collected if name.startswith("reasoning")], [])


class RouteTests(unittest.TestCase):
    def test_both_the_streaming_and_the_json_summary_routes_are_registered(self) -> None:
        from app.cybereye.backend import main

        paths = {getattr(route, "path", "") for route in main.app.routes}
        self.assertIn("/api/cyber/situations/summary", paths)
        self.assertIn("/api/cyber/situations/summary/stream", paths)
        route = next(item for item in main.app.routes
                     if getattr(item, "path", "") == "/api/cyber/situations/summary/stream")
        self.assertEqual(sorted(route.methods), ["POST"])


if __name__ == "__main__":
    unittest.main()
