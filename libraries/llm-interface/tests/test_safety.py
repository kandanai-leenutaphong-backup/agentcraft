import asyncio
import json
import logging
import traceback
import unittest
from unittest.mock import patch

import httpx
from pydantic import BaseModel

from llm_interface import Capabilities, Limits, LlmError, connect
from test_connection import Credential
from test_framework_comparison import response_value


def answer(text="fixture", status="completed"):
    message = {"id": "msg", "type": "message", "role": "assistant", "status": "completed",
               "content": [{"type": "output_text", "text": text, "annotations": [], "logprobs": []}]}
    payload = response_value("resp", [message], status)
    if status == "incomplete":
        payload["incomplete_details"] = {"reason": "max_output_tokens"}
    return payload


def stream_response(terminal="completed", text="fixture"):
    events = [{"type": "response.created", "response": response_value("resp", [], "in_progress")},
              {"type": "response.output_text.delta", "item_id": "msg", "output_index": 0,
               "content_index": 0, "delta": text, "logprobs": []}]
    if terminal is not None:
        events.append({"type": "response." + terminal, "response": answer(text, terminal)})
    wire = "".join("event: " + event["type"] + "\ndata: " + json.dumps({**event, "sequence_number": index}) + "\n\n"
                   for index, event in enumerate(events))
    return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=wire)


class SafetyTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        blocker = patch("socket.socket.connect", side_effect=AssertionError("Network forbidden"))
        blocker.start()
        self.addCleanup(blocker.stop)

    def connection(self, handler, **options):
        return connect("https://fixture.invalid", "fixture-model", credential=Credential(),
                       allow_model_calls=True, transport=httpx.MockTransport(handler), **options)

    async def test_direct_stream_final_and_early_eof(self):
        for terminal in ("completed", None, "failed"):
            async def handle(request):
                return stream_response(terminal)
            async with self.connection(handle) as connection:
                stream = connection.chat.get_response("fixture", stream=True)
                if terminal == "completed":
                    updates = [update async for update in stream]
                    result = await stream.get_final_response()
                    self.assertTrue(updates)
                    self.assertEqual(result.text, "fixture")
                    self.assertIs(result, await stream.get_final_response())
                else:
                    with self.assertRaises(LlmError) as failed:
                        await stream.get_final_response()
                    self.assertIn(failed.exception.code, {"missing_terminal_event", "model_stream_failed", "model_response_failed"})

    async def test_incomplete_agent_has_incomplete_terminal_event(self):
        async def handle(request):
            return stream_response("incomplete")
        async with self.connection(handle) as connection:
            stream = connection.agent(instructions="Fixture.").run("fixture", stream=True)
            events = [event async for event in stream]
            result = await stream.get_final_response()
            self.assertEqual(events[-1].kind, "run.incomplete")
            self.assertEqual(result.additional_properties["llm_interface"]["status"], "incomplete")

    async def test_structured_response_and_plain_agent(self):
        class Label(BaseModel):
            label: str
        async def handle(request):
            return httpx.Response(200, json=answer('{"label":"fixture"}'))
        async with self.connection(handle) as connection:
            result = await connection.chat.get_response("fixture", options={"response_format": Label})
            self.assertEqual(result.value.label, "fixture")
            result = await connection.agent(instructions="Return the label.").run("fixture")
            self.assertIn("fixture", result.text)

    async def test_status_errors_are_safe_and_not_retried(self):
        for status, category in ((401, "auth"), (403, "auth"), (404, "config"), (429, "rate_limit"), (500, "failed")):
            requests = []
            async def handle(request):
                requests.append(request)
                return httpx.Response(status, json={"error": {"message": "fixture-private-payload", "type": "fixture", "code": "fixture"}})
            async with self.connection(handle) as connection:
                with self.assertRaises(LlmError) as failed:
                    await connection.chat.get_response("fixture")
                self.assertEqual(failed.exception.category, category)
                self.assertNotIn("fixture-private-payload", "".join(traceback.format_exception(failed.exception)))
                self.assertIsNone(failed.exception.__cause__)
            self.assertEqual(len(requests), 1)

    async def test_redirect_and_native_byte_bounds(self):
        async def redirect(request):
            return httpx.Response(307, headers={"location": "https://foreign.invalid"})
        async with self.connection(redirect) as connection:
            with self.assertRaises(LlmError) as failed:
                await connection.chat.get_response("fixture")
            self.assertEqual(failed.exception.code, "redirect_refused")
        async def large(request):
            return httpx.Response(200, json=answer("x" * 3000))
        async with self.connection(large, limits=Limits(max_output_bytes=1500)) as connection:
            with self.assertRaises(LlmError) as failed:
                await connection.chat.get_response("fixture")
            self.assertIn(failed.exception.code, {"native_run_output_limit", "native_response_limit"})

    async def test_timeout_cancels_native_work(self):
        entered = asyncio.Event()
        stopped = asyncio.Event()
        async def handle(request):
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                stopped.set()
        async with self.connection(handle, limits=Limits(timeout_seconds=0.1)) as connection:
            with self.assertRaises(LlmError) as failed:
                await connection.chat.get_response("fixture")
            self.assertEqual(failed.exception.code, "deadline_exceeded")
        self.assertTrue(entered.is_set())
        self.assertTrue(stopped.is_set())

    async def test_stream_close_cancels_pending_provider(self):
        entered = asyncio.Event()
        stopped = asyncio.Event()
        async def handle(request):
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                stopped.set()
        async with self.connection(handle) as connection:
            stream = connection.chat.get_response("fixture", stream=True)
            waiting = asyncio.create_task(stream.get_final_response())
            await asyncio.wait_for(entered.wait(), 5)
            await stream.aclose()
            with self.assertRaises(asyncio.CancelledError):
                await waiting
            self.assertTrue(stopped.is_set())

    async def test_parallel_calls_respect_connection_gate(self):
        active = 0
        highest = 0
        entered = asyncio.Event()
        release = asyncio.Event()
        async def handle(request):
            nonlocal active, highest
            active += 1
            highest = max(highest, active)
            entered.set()
            await release.wait()
            active -= 1
            return httpx.Response(200, json=answer())
        async with self.connection(handle, limits=Limits(max_concurrency=1)) as connection:
            first = asyncio.create_task(connection.chat.get_response("first"))
            await asyncio.wait_for(entered.wait(), 5)
            second = asyncio.create_task(connection.chat.get_response("second"))
            release.set()
            results = await asyncio.gather(first, second)
            self.assertEqual(len(results), 2)
        self.assertEqual(highest, 1)

    async def test_capabilities_and_logging_refuse_locally(self):
        async def handle(request):
            raise AssertionError("must not dispatch")
        async with self.connection(handle, capabilities=Capabilities(streaming=False, structured_output=False)) as connection:
            with self.assertRaises(LlmError):
                connection.chat.get_response("fixture", stream=True)
            logger = logging.getLogger("agent_framework")
            previous = logger.level
            logger.setLevel(logging.DEBUG)
            try:
                with self.assertRaises(LlmError) as failed:
                    await connection.chat.get_response("fixture")
                self.assertEqual(failed.exception.code, "unsafe_debug_logging")
            finally:
                logger.setLevel(previous)