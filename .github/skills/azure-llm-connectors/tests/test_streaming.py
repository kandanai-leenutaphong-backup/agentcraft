"""Streaming: deltas arrive, and a mid-stream provider failure is not silence."""

from __future__ import annotations

import pytest

from azllm import LlmError
from fakes import FakeAsyncClient, FakeClient, FakeEvent, error_event, failed_event, text_delta

DELTAS = [text_delta("Hel"), text_delta("lo "), text_delta("world")]


def test_stream_text_yields_only_text_deltas(connector, fake_client: FakeClient) -> None:
    fake_client.responses.stream_events = [
        FakeEvent("response.created"),
        *DELTAS,
        FakeEvent("response.output_text.done", text="Hello world"),
        FakeEvent("response.completed"),
    ]
    assert "".join(connector.stream_text("hi")) == "Hello world"


def test_stream_sets_stream_true_and_keeps_store_false(connector, fake_client: FakeClient) -> None:
    fake_client.responses.stream_events = DELTAS
    list(connector.stream_text("hi", deployment="chat-batch"))
    call = fake_client.responses.calls[0]
    assert call["stream"] is True
    assert call["store"] is False
    assert call["model"] == "chat-batch"


def test_stream_error_event_raises_instead_of_ending_quietly(
    connector, fake_client: FakeClient
) -> None:
    fake_client.responses.stream_events = [text_delta("Hel"), error_event("server_error")]
    with pytest.raises(LlmError) as caught:
        list(connector.stream_text("hi"))
    err = caught.value
    assert err.category == "stream"
    assert err.code == "server_error"
    assert err.retryable is False


def test_response_failed_event_raises_with_the_provider_code(
    connector, fake_client: FakeClient
) -> None:
    fake_client.responses.stream_events = [text_delta("He"), failed_event("content_filter")]
    with pytest.raises(LlmError) as caught:
        list(connector.stream_text("hi"))
    assert caught.value.category == "stream"
    assert caught.value.code == "content_filter"


def test_stream_failure_message_carries_no_provider_text(connector, fake_client: FakeClient) -> None:
    from fakes import LEAKY_MESSAGE

    fake_client.responses.stream_events = [error_event()]
    with pytest.raises(LlmError) as caught:
        list(connector.stream_text("hi"))
    assert LEAKY_MESSAGE not in str(caught.value)
    assert "patient" not in str(caught.value)


def test_stream_is_closed_when_iteration_finishes(connector, fake_client: FakeClient) -> None:
    fake_client.responses.stream_events = DELTAS
    list(connector.stream_text("hi"))
    assert fake_client.responses.last_stream.closed is True


def test_stream_is_closed_when_the_consumer_abandons_it(connector, fake_client: FakeClient) -> None:
    fake_client.responses.stream_events = DELTAS
    stream = connector.stream_text("hi")
    next(stream)
    stream.close()
    assert fake_client.responses.last_stream.closed is True


def test_stream_events_hands_back_the_raw_feed(connector, fake_client: FakeClient) -> None:
    fake_client.responses.stream_events = [FakeEvent("response.created"), *DELTAS, error_event()]
    events = list(connector.stream_events(input="hi"))
    # Raw feed: nothing is filtered, and the error event is data, not an exception.
    assert [event.type for event in events] == [
        "response.created",
        "response.output_text.delta",
        "response.output_text.delta",
        "response.output_text.delta",
        "error",
    ]


async def test_async_stream_text_yields_deltas(
    async_connector, fake_async_client: FakeAsyncClient
) -> None:
    fake_async_client.responses.stream_events = [FakeEvent("response.created"), *DELTAS]
    chunks = [chunk async for chunk in async_connector.stream_text("hi")]
    assert "".join(chunks) == "Hello world"
    assert fake_async_client.responses.calls[0]["stream"] is True


async def test_async_stream_error_event_raises(
    async_connector, fake_async_client: FakeAsyncClient
) -> None:
    fake_async_client.responses.stream_events = [text_delta("He"), error_event("rate_limit_exceeded")]
    with pytest.raises(LlmError) as caught:
        [chunk async for chunk in async_connector.stream_text("hi")]
    assert caught.value.category == "stream"
    assert caught.value.code == "rate_limit_exceeded"


async def test_async_stream_events_are_unfiltered(
    async_connector, fake_async_client: FakeAsyncClient
) -> None:
    fake_async_client.responses.stream_events = [FakeEvent("response.created"), failed_event()]
    events = [event async for event in async_connector.stream_events(input="hi")]
    assert [event.type for event in events] == ["response.created", "response.failed"]


async def test_async_stream_is_closed_after_iteration(
    async_connector, fake_async_client: FakeAsyncClient
) -> None:
    fake_async_client.responses.stream_events = DELTAS
    [chunk async for chunk in async_connector.stream_text("hi")]
    assert fake_async_client.responses.last_stream.closed is True


def test_api_failure_before_the_stream_opens_is_classified(
    connector, fake_client: FakeClient
) -> None:
    import openai

    from fakes import status_error

    fake_client.responses.raises = status_error(openai.RateLimitError, 429)
    with pytest.raises(LlmError) as caught:
        list(connector.stream_text("hi"))
    assert caught.value.category == "rate_limit"
