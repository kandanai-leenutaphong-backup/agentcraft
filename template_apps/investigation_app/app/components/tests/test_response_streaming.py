"""The Responses stream bridge: what is replayed after a transport error, and what is not.

Driven with a fake SDK `create` callable and no application import, which is the whole
point of the helper living here: it knows nothing about who is calling it.
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from typing import Any
from unittest import mock

import httpx

from template_foundations.azure_llm import response_events


def event(type_name: str, **fields: Any) -> SimpleNamespace:
    return SimpleNamespace(type=type_name, **fields)


class ClosingReplay:
    """A stream that records that it was closed, as the SDK's own stream must be."""

    def __init__(self, items: list[Any]) -> None:
        self.items = items
        self.closed = False

    def __iter__(self):
        for item in self.items:
            if isinstance(item, BaseException):
                raise item
            yield item

    def close(self) -> None:
        self.closed = True


def create_returning(*attempts: list[Any]) -> tuple[Any, list[ClosingReplay]]:
    streams = [ClosingReplay(items) for items in attempts]
    return mock.Mock(side_effect=list(streams)), streams


CREATED = event("response.created", response=SimpleNamespace(id="unfinished"))
COMPLETED = event("response.completed", response=SimpleNamespace(id="complete"))


class ResponseEventsTests(unittest.IsolatedAsyncioTestCase):
    async def test_events_reach_the_caller_in_order_and_the_stream_is_closed(self) -> None:
        create, streams = create_returning([CREATED, COMPLETED])
        collected = [item async for item in response_events(create, model="m", input="hello")]
        self.assertEqual(collected, [CREATED, COMPLETED])
        self.assertEqual(create.call_args_list,
                         [mock.call(model="m", input="hello", stream=True)])
        self.assertTrue(streams[0].closed)

    async def test_a_transport_failure_before_visible_output_is_replayed_once(self) -> None:
        for preliminary in ([], [CREATED, event("response.in_progress")],
                            [CREATED, event("response.output_item.added",
                                            item=SimpleNamespace(type="reasoning"))]):
            with self.subTest(preliminary=len(preliminary)):
                create, _ = create_returning(
                    [*preliminary, httpx.RemoteProtocolError("incomplete chunked read")],
                    [COMPLETED],
                )
                request = {"model": "m", "previous_response_id": "prior"}
                collected = [item async for item in response_events(create, **request)]
                self.assertEqual(collected, [*preliminary, COMPLETED])
                self.assertEqual(create.call_args_list,
                                 [mock.call(**request, stream=True)] * 2)

    async def test_visible_output_prevents_the_replay(self) -> None:
        for kind in ("response.output_text.delta", "response.output_item.added",
                     "response.reasoning_summary_text.delta"):
            with self.subTest(kind=kind):
                visible = event(kind, item=SimpleNamespace(type="function_call"))
                create, _ = create_returning(
                    [visible, httpx.RemoteProtocolError("after output")], [COMPLETED])
                collected = []
                with self.assertRaisesRegex(httpx.RemoteProtocolError, "after output"):
                    async for item in response_events(create, model="m"):
                        collected.append(item)
                self.assertEqual(collected, [visible])
                self.assertEqual(create.call_count, 1)

    async def test_a_second_transport_failure_is_not_replayed(self) -> None:
        create, _ = create_returning([httpx.RemoteProtocolError("first")],
                                     [httpx.RemoteProtocolError("second")])
        with self.assertRaisesRegex(httpx.RemoteProtocolError, "second"):
            _ = [item async for item in response_events(create, model="m")]
        self.assertEqual(create.call_count, 2)

    async def test_any_other_failure_is_not_replayed(self) -> None:
        create, _ = create_returning([ValueError("invalid response")], [COMPLETED])
        with self.assertRaisesRegex(ValueError, "invalid response"):
            _ = [item async for item in response_events(create, model="m")]
        self.assertEqual(create.call_count, 1)

    async def test_a_failure_raised_by_create_itself_is_replayed_once(self) -> None:
        create = mock.Mock(side_effect=[httpx.ConnectError("refused"),
                                        ClosingReplay([COMPLETED])])
        collected = [item async for item in response_events(create, model="m")]
        self.assertEqual(collected, [COMPLETED])
        self.assertEqual(create.call_count, 2)


class ReusabilityTests(unittest.TestCase):
    def test_the_helper_imports_nothing_from_the_application(self) -> None:
        import template_foundations.azure_llm.streaming as streaming

        source = open(streaming.__file__, encoding="utf-8").read()
        self.assertNotIn("app.cybereye", source)
        self.assertNotIn("import os", source)


if __name__ == "__main__":
    unittest.main()
