"""Bridge a synchronous Responses stream onto an asyncio event loop, with one safe retry.

The SDK's streaming call is blocking and iterated on a worker thread; events cross to the
caller's loop through a queue. The retry is deliberately narrow: a transport error is
replayed once and only while nothing the caller could already have shown has arrived.
Envelope events (``response.created``, ``response.in_progress``, and the empty reasoning
item envelope) are bookkeeping, so a failure after them is still safe to replay. Anything
else — a text delta, a reasoning summary delta, a function call item — means output exists,
and a second attempt would duplicate it. Nothing but a transport error is retried.

Domain-blind: the caller supplies the SDK ``create`` callable and the whole request.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import closing
from typing import Any

import httpx

logger = logging.getLogger(__name__)

#: Event types that carry no output a caller could already have rendered.
ENVELOPE_EVENTS = frozenset({"response.created", "response.in_progress"})


def _is_bookkeeping(event: Any) -> bool:
    event_type = getattr(event, "type", "")
    if event_type in ENVELOPE_EVENTS:
        return True
    return (
        event_type == "response.output_item.added"
        and getattr(getattr(event, "item", None), "type", "") == "reasoning"
    )


async def response_events(
    create: Callable[..., Any], /, **request: Any,
) -> AsyncIterator[Any]:
    """Yield the events of ``create(**request, stream=True)`` on the running loop."""
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[Any] = asyncio.Queue()
    finished = object()

    def produce() -> None:
        try:
            for attempt in range(2):
                progressed = False
                try:
                    stream = create(**request, stream=True)
                    with closing(stream):
                        for event in stream:
                            progressed = progressed or not _is_bookkeeping(event)
                            loop.call_soon_threadsafe(queue.put_nowait, event)
                    return
                except httpx.TransportError:
                    if progressed or attempt:
                        raise
                    logger.warning("azure_llm.responses.transport_retry attempt=%s", attempt + 1)
        except BaseException as exc:
            loop.call_soon_threadsafe(queue.put_nowait, exc)
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, finished)

    producer = asyncio.create_task(asyncio.to_thread(produce))
    try:
        while True:
            event = await queue.get()
            if event is finished:
                break
            if isinstance(event, BaseException):
                raise event
            yield event
    finally:
        await producer
