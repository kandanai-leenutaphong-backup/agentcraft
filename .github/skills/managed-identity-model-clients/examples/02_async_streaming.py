"""Worked example 2 — asyncio, streamed text, and streamed raw events.

Run it: ``python3 examples/02_async_streaming.py``.

The point of the streaming half is the failure case. A streamed call returns
HTTP 200 on its first byte and can still fail three tokens later, in-band, as
an ``error`` or ``response.failed`` event. ``stream_text`` raises on those.
``stream_events`` does not — holding the raw feed means owning its semantics.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modelaccess import (  # noqa: E402
    FakeAsyncClient,
    ModelConfig,
    ModelError,
    connect_async,
    fake_text_response,
    stream_failed_event,
    text_delta_event,
)

config = ModelConfig(
    endpoint="https://example-account.openai.azure.com/",
    deployment="my-chat-deployment",
)


async def main() -> None:
    transport = FakeAsyncClient(
        responses=[fake_text_response("async answer", response_id="resp_a")],
        streams=[
            [text_delta_event("Hel"), text_delta_event("lo"), text_delta_event("!")],
            [text_delta_event("par"), stream_failed_event("content_filter")],
            [text_delta_event("x"), text_delta_event("y"), text_delta_event("z")],
        ],
    )

    async with connect_async(config, client=transport) as model:
        answer = await model.ask("say hello")
        assert answer.text == "async answer"
        assert answer.response_id == "resp_a"

        # 1. A stream that completes.
        chunks = [chunk async for chunk in model.stream_text("say hello")]
        assert chunks == ["Hel", "lo", "!"]
        assert "".join(chunks) == "Hello!"
        assert transport.streams_opened[0].closed is True

        # 2. A stream that fails after the connection succeeded. The partial
        #    text is kept by the caller; the failure is not silently an
        #    empty-but-successful answer.
        partial: list[str] = []
        try:
            async for chunk in model.stream_text("say something forbidden"):
                partial.append(chunk)
        except ModelError as failed:
            assert failed.category == "stream"
            assert failed.code == "content_filter"
            assert failed.retryable is False
        else:  # pragma: no cover
            raise AssertionError("an in-stream failure must raise")
        assert partial == ["par"]
        assert transport.streams_opened[1].closed is True

        # 3. Abandoning a stream early still releases the connection: the
        #    generator's finally block runs when it is closed.
        events = model.stream_events(input="count")
        first = await events.__anext__()
        assert first.type == "response.output_text.delta"
        await events.aclose()
        assert transport.streams_opened[2].closed is True

    # aclose() released this object's own resources. The injected client is
    # the caller's and is left open; pass owns_client=True to hand it over.
    assert transport.closed is False
    adopted = connect_async(config, client=transport, owns_client=True)
    await adopted.aclose()
    assert transport.closed is True


asyncio.run(main())
print("02_async_streaming: ok")
