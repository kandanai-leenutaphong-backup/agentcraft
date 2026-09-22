import asyncio
import json
import unittest
from typing import Annotated
from unittest.mock import patch

import httpx
from pydantic import BaseModel, ConfigDict, Field

from llm_interface import Capabilities, LlmError, connect, report_progress, tool
from test_framework_comparison import ModelFixture, response_value
from test_safety import answer, stream_response
from test_tools import tool_response


def native_events(events):
    wire = "".join("event: " + event["type"] + "\ndata: "
                   + json.dumps({**event, "sequence_number": index}) + "\n\n"
                   for index, event in enumerate(events))
    return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=wire)


def native_tool_stream(arguments, *, name="lookup", status="completed"):
    payload = tool_response(arguments, name=name, status=status)
    call = payload["output"][0]
    return native_events([
        {"type": "response.created", "response": response_value("resp", [], "in_progress")},
        {"type": "response.output_item.added", "output_index": 0,
         "item": {**call, "arguments": "", "status": "in_progress"}},
        {"type": "response.function_call_arguments.delta", "item_id": "fc", "output_index": 0,
         "delta": arguments},
        {"type": "response.function_call_arguments.done", "item_id": "fc", "output_index": 0,
         "name": name, "arguments": arguments},
        {"type": "response.output_item.done", "output_index": 0, "item": call},
        {"type": "response." + status, "response": payload},
    ])


class InvestigationCompatibilityTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        blocker = patch("socket.socket.connect", side_effect=AssertionError("Network forbidden"))
        blocker.start()
        self.addCleanup(blocker.stop)

    async def test_fixed_instructions_and_supported_options_reach_native_requests(self):
        fixture = ModelFixture("responses")
        instructions = "Use only the supplied historical replay evidence."

        async def lookup_fixture(asset_id: str) -> dict:
            """Read one synthetic asset status."""
            return {"asset_id": asset_id, "status": "verified fixture"}

        async with connect("https://fixture.invalid/v1", "fixture-model", provider="openai",
                           credential="offline-fixture", allow_model_calls=True,
                           allowed_tools=("lookup_fixture",),
                       capabilities=Capabilities(reasoning=True, embeddings=False),
                           transport=httpx.MockTransport(fixture.handle)) as connection:
            agent = connection.agent(instructions=instructions, tools=[lookup_fixture],
                             required_capabilities=("reasoning",))
            stream = agent.run("Check the selected situation.", stream=True,
                         options={"max_tokens": 128, "parallel_tool_calls": False,
                                "reasoning": {"effort": "high", "summary": "detailed"}})
            async with stream:
                final = await stream.get_final_response()

        self.assertEqual(final.text, "Fixture verified.")
        self.assertEqual(len(fixture.requests), 2)
        for request in fixture.requests:
            self.assertEqual(request["instructions"], instructions)
            self.assertEqual(request["max_output_tokens"], 128)
            self.assertIs(request["parallel_tool_calls"], False)
            self.assertEqual(request["reasoning"], {"effort": "high", "summary": "detailed"})
            self.assertIs(request["store"], False)
            self.assertNotIn("previous_response_id", request)

    async def test_legacy_request_fields_and_binding_overrides_refuse_before_io(self):
        fixture = ModelFixture("responses")
        cases = [
            ({"instructions": "Replace fixed instructions."}, "option_unsupported"),
            ({"previous_response_id": "resp_old"}, "option_unsupported"),
            ({"max_output_tokens": 128}, "option_unsupported"),
            ({"extra_body": {"store": True}}, "option_unsupported"),
            ({"text": {"format": {"type": "json_object"}}}, "option_unsupported"),
            ({"max_tokens": 1200}, "output_token_limit"),
            ({"store": True}, "binding_override_denied"),
            ({"model": "another-model"}, "binding_override_denied"),
            ({"reasoning": {"effort": "max"}}, "reasoning_option_unsupported"),
        ]
        async with connect("https://fixture.invalid/v1", "fixture-model", provider="openai",
                           credential="offline-fixture", allow_model_calls=True,
                           capabilities=Capabilities(reasoning=True, embeddings=False),
                           transport=httpx.MockTransport(fixture.handle)) as connection:
            agent = connection.agent(instructions="Fixed historical replay instructions.")
            for options, code in cases:
                with self.subTest(options=options):
                    with self.assertRaises(LlmError) as failure:
                        agent.run("fixture", options=options)
                    self.assertEqual(failure.exception.code, code)
        self.assertEqual(fixture.requests, [])

    async def test_reasoning_requires_an_explicit_capability(self):
        fixture = ModelFixture("responses")
        async with connect("https://fixture.invalid/v1", "fixture-model", provider="openai",
                           credential="offline-fixture", allow_model_calls=True,
                           transport=httpx.MockTransport(fixture.handle)) as connection:
            agent = connection.agent(instructions="Fixed historical replay instructions.")
            for effort in ("none", "high"):
                with self.subTest(effort=effort):
                    with self.assertRaises(LlmError) as failure:
                        agent.run("fixture", options={"reasoning": {"effort": effort}})
                    self.assertEqual(failure.exception.code, "reasoning_unsupported")
        self.assertEqual(fixture.requests, [])

    async def test_owner_bound_history_and_result_copy_use_no_provider_thread(self):
        for streaming in (False, True):
            with self.subTest(streaming=streaming):
                requests = []

                async def handle(request):
                    requests.append(json.loads(request.content))
                    text = "First fixture answer." if len(requests) == 1 else "Second fixture answer."
                    return (stream_response(text=text) if streaming
                            else httpx.Response(200, json=answer(text)))

                async with connect("https://fixture.invalid/v1", "fixture-model", provider="openai",
                                   credential="offline-fixture", allow_model_calls=True,
                                   transport=httpx.MockTransport(handle)) as connection:
                    agent = connection.agent(instructions="Use only the historical replay.")
                    session = agent.create_session(principal="owner")
                    self.assertIsNone(session.result(principal="owner"))
                    results = []
                    for message in ("First question.", "Follow-up question."):
                        pending = agent.run(message, session=session, principal="owner", stream=streaming)
                        if streaming:
                            async with pending:
                                results.append(await pending.get_final_response())
                        else:
                            results.append(await pending)
                    self.assertNotEqual(results[0].additional_properties["llm_interface"]["run_id"],
                                        results[1].additional_properties["llm_interface"]["run_id"])
                    retained = session.result(principal="owner")
                    retained.additional_properties["llm_interface"]["status"] = "changed-copy"
                    self.assertEqual(session.result(principal="owner").text, "Second fixture answer.")
                    self.assertEqual(session.result(principal="owner").additional_properties[
                        "llm_interface"]["status"], "completed")
                    with self.assertRaises(LlmError) as run_denied:
                        agent.run("Foreign request.", session=session, principal="other")
                    with self.assertRaises(LlmError) as read_denied:
                        session.result(principal="other")
                    self.assertEqual(run_denied.exception.code, "session_not_found")
                    self.assertEqual(read_denied.exception.code, "session_not_found")

                self.assertEqual(len(requests), 2)
                history = [part["text"] for message in requests[1]["input"]
                           for part in message.get("content", [])
                           if isinstance(part, dict) and "text" in part]
                self.assertEqual(history, ["First question.", "First fixture answer.", "Follow-up question."])
                for request in requests:
                    self.assertIs(request["store"], False)
                    self.assertNotIn("previous_response_id", request)

    async def test_returned_query_error_reaches_model_as_bounded_json(self):
        requests = []
        executions = []
        expected = {"kind": "cybereye_tool_result", "error": "query_failed",
                    "detail": "Synthetic query refused."}

        def lookup(value: int) -> dict:
            """Return a synthetic recoverable query error."""
            executions.append(value)
            return dict(expected)

        async def handle(request):
            requests.append(json.loads(request.content))
            payload = tool_response('{"value":1}') if len(requests) == 1 else answer("Query unavailable.")
            return httpx.Response(200, json=payload)

        async with connect("https://fixture.invalid/v1", "fixture-model", provider="openai",
                           credential="offline-fixture", allow_model_calls=True, allowed_tools=("lookup",),
                           transport=httpx.MockTransport(handle)) as connection:
            result = await connection.agent(instructions="Use the tool.", tools=[lookup]).run("fixture")
        self.assertEqual(executions, [1])
        self.assertEqual(len(requests), 2)
        outputs = [item for item in requests[1]["input"] if item.get("type") == "function_call_output"]
        self.assertEqual(len(outputs), 1)
        self.assertEqual(outputs[0]["call_id"], "call")
        self.assertEqual(json.loads(outputs[0]["output"]), expected)
        self.assertEqual(result.text, "Query unavailable.")
        self.assertEqual(result.additional_properties["llm_interface"]["tool_calls"], 1)

    async def test_thrown_tool_error_stops_replay_and_preserves_prior_result(self):
        requests = []
        executions = []

        def lookup(value: int) -> dict:
            """Raise a synthetic unexpected tool failure."""
            executions.append(value)
            raise RuntimeError("private-query-fixture-payload")

        async def handle(request):
            requests.append(json.loads(request.content))
            payload = answer("Earlier completed answer.") if len(requests) == 1 else tool_response('{"value":1}')
            return httpx.Response(200, json=payload)

        async with connect("https://fixture.invalid/v1", "fixture-model", provider="openai",
                           credential="offline-fixture", allow_model_calls=True, allowed_tools=("lookup",),
                           transport=httpx.MockTransport(handle)) as connection:
            agent = connection.agent(instructions="Use the tool.", tools=[lookup])
            session = agent.create_session(principal="owner")
            previous = await agent.run("First question.", session=session, principal="owner")
            with self.assertLogs("agent_framework", level="WARNING") as captured:
                with self.assertRaises(LlmError) as failed:
                    await agent.run("Second question.", session=session, principal="owner")
            self.assertEqual(failed.exception.code, "tool_failed")
            self.assertIsNone(failed.exception.__cause__)
            self.assertNotIn("private-query-fixture-payload", str(failed.exception) + "\n".join(captured.output))
            with self.assertRaises(LlmError) as replay:
                agent.run("Replay request.", session=session, principal="owner")
            self.assertEqual(replay.exception.code, "session_interrupted")
            self.assertEqual(session.result(principal="owner").text, previous.text)
            self.assertEqual(session.result(principal="owner").additional_properties["llm_interface"]["run_id"],
                             previous.additional_properties["llm_interface"]["run_id"])
        self.assertEqual(executions, [1])
        self.assertEqual(len(requests), 2)

    async def test_sink_schema_context_and_result_survive_native_stream(self):
        requests = []
        authorized = []
        executions = []
        host_context = object()
        arguments = {"position": 1, "description": "Fixture account read the record.",
                     "timestamp": "2026-01-01T00:00:00Z",
                     "evidence_ids": ["resource-fixture", "unsupported-fixture"]}
        expected = {"kind": "cybereye_tool_result", "tool": "record_sequence_step",
                    "category": "sequence_step", **arguments, "historical_replay": True, "fallback": False}

        class StepArguments(BaseModel):
            model_config = ConfigDict(extra="forbid")
            position: int = Field(ge=1, le=10)
            description: str = Field(min_length=10, max_length=160)
            timestamp: str = Field(max_length=40)
            evidence_ids: list[Annotated[str, Field(max_length=200)]] = Field(max_length=4)

        @tool(name="record_sequence_step", schema=StepArguments)
        async def record_step(position: int, description: str, timestamp: str, evidence_ids: list[str]) -> dict:
            """Return a synthetic sequence sink envelope; provenance stays host-owned."""
            executions.append(host_context)
            await report_progress({"position": position})
            return {"kind": "cybereye_tool_result", "tool": "record_sequence_step", "category": "sequence_step",
                    "position": position, "description": description, "timestamp": timestamp,
                    "evidence_ids": evidence_ids, "historical_replay": True, "fallback": False}

        def authorize(call):
            authorized.append(call)
            return call.principal == "owner"

        async def handle(request):
            self.assertEqual(request.url.path, "/v1/responses")
            requests.append(json.loads(request.content))
            return (native_tool_stream(json.dumps(arguments), name="record_sequence_step")
                    if len(requests) == 1 else stream_response(text="Sequence recorded."))

        async with connect("https://fixture.invalid/v1", "fixture-model", provider="openai",
                           credential="offline-fixture", allow_model_calls=True,
                           allowed_tools=("record_sequence_step",),
                           transport=httpx.MockTransport(handle)) as connection:
            agent = connection.agent(instructions="Record the historical sequence.", tools=[record_step],
                                     authorize_tool=authorize, name="investigator-v1")
            session = agent.create_session(principal="owner")
            stream = agent.run("Record the step.", session=session, principal="owner", stream=True)
            async with stream:
                events = [event async for event in stream]
                final = await stream.get_final_response()
                self.assertIs(await stream.get_final_response(), final)
            self.assertEqual(session.result(principal="owner").text, final.text)

        self.assertEqual(executions, [host_context])
        self.assertEqual(len(authorized), 1)
        self.assertEqual((authorized[0].name, authorized[0].call_id, authorized[0].arguments),
                         ("record_sequence_step", "call", arguments))
        self.assertEqual(len(requests), 2)
        parameters = requests[0]["tools"][0]["parameters"]
        self.assertEqual(set(parameters["properties"]), set(arguments))
        self.assertEqual(parameters["properties"]["position"]["minimum"], 1)
        self.assertEqual(parameters["properties"]["evidence_ids"]["maxItems"], 4)
        self.assertIs(parameters["additionalProperties"], False)
        self.assertEqual([event.sequence for event in events], list(range(1, len(events) + 1)))
        self.assertEqual({event.run_id for event in events}, {authorized[0].run_id})
        self.assertEqual({event.schema_version for event in events}, {1})
        kinds = [event.kind for event in events]
        self.assertEqual(kinds[0], "run.started")
        self.assertEqual([kind for kind in kinds if kind.startswith("run.")], ["run.started", "run.completed"])
        for earlier, later in (("tool.call.delta", "tool.call.ready"), ("tool.call.ready", "tool.started"),
                               ("tool.started", "tool.progress"), ("tool.progress", "tool.result")):
            self.assertLess(kinds.index(earlier), kinds.index(later))
        ready = next(event for event in events if event.kind == "tool.call.ready")
        self.assertEqual(ready.data, {"call_id": "call", "name": "record_sequence_step", "arguments": arguments})
        progress = next(event for event in events if event.kind == "tool.progress")
        self.assertEqual(progress.data, {"call_id": "call", "progress": {"position": 1}})
        result_event = next(event for event in events if event.kind == "tool.result")
        self.assertEqual(result_event.data, {"call_id": "call", "result": expected})
        outputs = [item for item in requests[1]["input"] if item.get("type") == "function_call_output"]
        self.assertEqual(len(outputs), 1)
        self.assertEqual(json.loads(outputs[0]["output"]), expected)
        self.assertEqual(final.text, "Sequence recorded.")
        self.assertEqual(events[-1].data["model_calls"], 2)
        self.assertEqual(events[-1].data["tool_calls"], 1)

    async def test_incomplete_tool_call_never_executes_in_either_mode(self):
        for streaming in (False, True):
            with self.subTest(streaming=streaming):
                requests = []
                executions = []

                def lookup(value: int) -> dict:
                    """Return a synthetic tool value."""
                    executions.append(value)
                    return {"value": value}

                async def handle(request):
                    requests.append(json.loads(request.content))
                    return (native_tool_stream('{"value":1}', status="incomplete") if streaming
                            else httpx.Response(200, json=tool_response('{"value":1}', status="incomplete")))

                async with connect("https://fixture.invalid/v1", "fixture-model", provider="openai",
                                   credential="offline-fixture", allow_model_calls=True, allowed_tools=("lookup",),
                                   transport=httpx.MockTransport(handle)) as connection:
                    agent = connection.agent(instructions="Use the tool.", tools=[lookup])
                    session = agent.create_session(principal="owner")
                    pending = agent.run("fixture", session=session, principal="owner", stream=streaming)
                    events = []
                    with self.assertRaises(LlmError) as failure:
                        if streaming:
                            async with pending:
                                async for event in pending:
                                    events.append(event)
                        else:
                            await pending
                    self.assertEqual(failure.exception.code, "incomplete_tool_call")
                    if streaming:
                        self.assertEqual(events[-1].kind, "run.failed")
                        self.assertEqual(events[-1].data["code"], "incomplete_tool_call")
                        self.assertFalse(any(event.kind in {"tool.started", "tool.result"} for event in events))
                    self.assertIsNone(session.result(principal="owner"))
                    with self.assertRaises(LlmError) as replay:
                        agent.run("retry", session=session, principal="owner")
                    self.assertEqual(replay.exception.code, "session_interrupted")
                self.assertEqual(executions, [])
                self.assertEqual(len(requests), 1)

    async def test_raw_and_typed_schemas_preserve_bounds_and_refuse_invalid_arguments(self):
        schema = {"type": "object", "additionalProperties": False,
                  "properties": {"value": {"type": "integer", "minimum": 1}}, "required": ["value"]}

        class LookupArguments(BaseModel):
            model_config = ConfigDict(extra="forbid")
            value: int = Field(ge=1)

        for declaration in (schema, LookupArguments):
            typed = declaration is LookupArguments
            with self.subTest(typed=typed):
                requests = []
                executions = []

                def lookup(value: int) -> dict:
                    """Return a synthetic constrained value."""
                    executions.append(value)
                    return {"value": value}

                declared = tool(lookup, schema=declaration)
                self.assertEqual(declared.parameters()["properties"]["value"]["minimum"], 1)

                async def handle(request):
                    requests.append(json.loads(request.content))
                    payload = tool_response('{"value":0}') if len(requests) == 1 else answer("Fixture finished.")
                    return httpx.Response(200, json=payload)

                async with connect("https://fixture.invalid/v1", "fixture-model", provider="openai",
                                   credential="offline-fixture", allow_model_calls=True, allowed_tools=("lookup",),
                                   transport=httpx.MockTransport(handle)) as connection:
                    agent = connection.agent(instructions="Use the constrained tool.", tools=[declared])
                    with self.assertRaises(LlmError) as refused:
                        await agent.run("fixture")
                    self.assertEqual(refused.exception.code, "invalid_tool_arguments")
                native = requests[0]["tools"][0]["parameters"]["properties"]["value"]
                self.assertEqual(native["minimum"], 1)
                self.assertEqual(executions, [])
                self.assertEqual(len(requests), 1)

    async def test_incomplete_text_and_quiet_eof_have_distinct_session_outcomes(self):
        for terminal in ("incomplete", None):
            with self.subTest(terminal=terminal):
                requests = []

                async def handle(request):
                    requests.append(json.loads(request.content))
                    return stream_response(terminal, text="Partial fixture answer.")

                async with connect("https://fixture.invalid/v1", "fixture-model", provider="openai",
                                   credential="offline-fixture", allow_model_calls=True,
                                   transport=httpx.MockTransport(handle)) as connection:
                    agent = connection.agent(instructions="Use the historical replay.")
                    session = agent.create_session(principal="owner")
                    stream = agent.run("fixture", session=session, principal="owner", stream=True)
                    events = []
                    async with stream:
                        if terminal:
                            events = [event async for event in stream]
                            result = await stream.get_final_response()
                            self.assertEqual(events[-1].kind, "run.incomplete")
                            self.assertEqual(result.text, "Partial fixture answer.")
                            retained = session.result(principal="owner")
                            self.assertEqual(retained.additional_properties["llm_interface"]["status"], "incomplete")
                            self.assertNotIn("reason", events[-1].data)
                            self.assertNotIn("response_id", events[-1].data)
                        else:
                            with self.assertRaises(LlmError) as failed:
                                async for event in stream:
                                    events.append(event)
                            self.assertEqual(failed.exception.code, "missing_terminal_event")
                            self.assertEqual(events[-1].kind, "run.failed")
                            self.assertIsNone(session.result(principal="owner"))
                            with self.assertRaises(LlmError) as replay:
                                agent.run("retry", session=session, principal="owner")
                            self.assertEqual(replay.exception.code, "session_interrupted")
                    self.assertEqual("".join(event.text for event in events), "Partial fixture answer.")
                self.assertEqual(len(requests), 1)

    async def test_in_flight_binding_is_pinned_and_changed_binding_needs_fresh_session(self):
        requests = []
        entered = asyncio.Event()
        release = asyncio.Event()

        async def handle(request):
            requests.append(json.loads(request.content))
            if len(requests) == 1:
                entered.set()
                await release.wait()
            return httpx.Response(200, json=answer("Pinned fixture answer."))

        async with connect("https://fixture.invalid/v1", "fixture-model", provider="openai",
                           credential="offline-fixture", allow_model_calls=True,
                           transport=httpx.MockTransport(handle)) as connection:
            first = connection.agent(instructions="Version one instructions.", name="investigator-v1")
            session = first.create_session(principal="owner")
            pending = asyncio.create_task(first.run("Old version question.", session=session, principal="owner"))
            try:
                await asyncio.wait_for(entered.wait(), 5)
                second = connection.agent(instructions="Version two instructions.", name="investigator-v2")
                with self.assertRaises(LlmError) as changed:
                    second.run("Changed version question.", session=session, principal="owner")
                self.assertEqual(changed.exception.code, "session_binding_changed")
                self.assertEqual(len(requests), 1)
            finally:
                release.set()
                await pending
            fresh = second.create_session(principal="owner")
            result = await second.run("Fresh version question.", session=fresh, principal="owner")
            self.assertNotEqual(fresh.id, session.id)
            self.assertEqual(fresh.result(principal="owner").text, result.text)

        self.assertEqual(len(requests), 2)
        self.assertEqual(requests[0]["instructions"], "Version one instructions.")
        self.assertEqual(requests[1]["instructions"], "Version two instructions.")
        history = [part["text"] for message in requests[1]["input"]
                   for part in message.get("content", []) if isinstance(part, dict) and "text" in part]
        self.assertEqual(history, ["Fresh version question."])

    async def test_stream_close_cancels_local_request_and_blocks_session_replay(self):
        requests = []
        entered = asyncio.Event()
        stopped = asyncio.Event()

        async def handle(request):
            requests.append(json.loads(request.content))
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                stopped.set()

        async with connect("https://fixture.invalid/v1", "fixture-model", provider="openai",
                           credential="offline-fixture", allow_model_calls=True,
                           transport=httpx.MockTransport(handle)) as connection:
            agent = connection.agent(instructions="Use the historical replay.")
            session = agent.create_session(principal="owner")
            stream = agent.run("fixture", session=session, principal="owner", stream=True)
            async with stream:
                pending = asyncio.create_task(stream.get_final_response())
                try:
                    await asyncio.wait_for(entered.wait(), 5)
                    await stream.aclose()
                    with self.assertRaises(asyncio.CancelledError):
                        await asyncio.wait_for(pending, 5)
                finally:
                    await stream.aclose()
                    pending.cancel()
                    await asyncio.gather(pending, return_exceptions=True)
            self.assertTrue(stopped.is_set())
            self.assertIsNone(session.result(principal="owner"))
            with self.assertRaises(LlmError) as replay:
                agent.run("retry", session=session, principal="owner")
            self.assertEqual(replay.exception.code, "session_interrupted")
        self.assertEqual(len(requests), 1)

    async def test_reasoning_summary_uses_portable_delta_without_legacy_boundaries(self):
        requests = []
        reasoning = {"id": "reasoning-fixture", "type": "reasoning",
                     "summary": [{"type": "summary_text", "text": "Fixture public summary."}]}

        async def handle(request):
            requests.append(json.loads(request.content))
            return native_events([
                {"type": "response.created", "response": response_value("resp", [], "in_progress")},
                {"type": "response.output_item.added", "output_index": 0, "item": {**reasoning, "summary": []}},
                {"type": "response.reasoning_summary_part.added", "item_id": "reasoning-fixture",
                 "output_index": 0, "summary_index": 0, "part": {"type": "summary_text", "text": ""}},
                {"type": "response.reasoning_summary_text.delta", "item_id": "reasoning-fixture",
                 "output_index": 0, "summary_index": 0, "delta": "Fixture public summary."},
                {"type": "response.reasoning_summary_text.done", "item_id": "reasoning-fixture",
                 "output_index": 0, "summary_index": 0, "text": "Fixture public summary."},
                {"type": "response.output_item.done", "output_index": 0, "item": reasoning},
                {"type": "response.output_text.delta", "item_id": "msg", "output_index": 1,
                 "content_index": 0, "delta": "Fixture answer.", "logprobs": []},
                {"type": "response.completed",
                 "response": response_value("resp", [reasoning, *answer("Fixture answer.")["output"]])},
            ])

        async with connect("https://fixture.invalid/v1", "fixture-model", provider="openai",
                           credential="offline-fixture", allow_model_calls=True,
                           capabilities=Capabilities(reasoning=True, embeddings=False),
                           transport=httpx.MockTransport(handle)) as connection:
            stream = connection.agent(instructions="Use the historical replay.").run(
                "fixture", stream=True, options={"reasoning": {"effort": "high", "summary": "detailed"}})
            async with stream:
                events = [event async for event in stream]
                await stream.get_final_response()
        summaries = [event for event in events if event.kind == "reasoning.summary.delta"]
        self.assertEqual([event.data for event in summaries],
                         [{"text": "", "id": "reasoning-fixture"},
                          {"text": "Fixture public summary.", "id": "reasoning-fixture"}])
        self.assertFalse(any(event.kind in {"reasoning_start", "reasoning_end"} for event in events))
        self.assertEqual(events[-1].kind, "run.completed")
        self.assertEqual(len(requests), 1)


if __name__ == "__main__":
    unittest.main()