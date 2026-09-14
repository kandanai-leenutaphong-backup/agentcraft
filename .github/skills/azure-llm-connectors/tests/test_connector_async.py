"""The async call surface mirrors the sync one, awaits aside."""

from __future__ import annotations

import pytest

from azllm import ConfigError, FoundryConfig, connect_async
from fakes import FakeAsyncClient, FakeResponse


async def test_ask_returns_text_and_metadata(async_connector, fake_async_client: FakeAsyncClient) -> None:
    result = await async_connector.ask("hello")
    assert result.text == "hello"
    assert result.response_id == "resp_fake_1"
    assert result.deployment == "chat"
    assert result.usage["total_tokens"] == 10
    assert fake_async_client.responses.calls[0]["store"] is False


async def test_per_call_deployment_override(async_connector, fake_async_client: FakeAsyncClient) -> None:
    result = await async_connector.ask("hello", deployment="chat-batch")
    assert fake_async_client.responses.calls[0]["model"] == "chat-batch"
    assert result.deployment == "chat-batch"


async def test_arbitrary_options_pass_through(async_connector, fake_async_client: FakeAsyncClient) -> None:
    await async_connector.ask("hello", tools=[{"type": "web_search"}], reasoning={"effort": "low"})
    call = fake_async_client.responses.calls[0]
    assert call["tools"] == [{"type": "web_search"}]
    assert call["reasoning"] == {"effort": "low"}


async def test_reserved_options_are_refused(async_connector) -> None:
    with pytest.raises(ConfigError):
        await async_connector.ask("hello", model="chat-batch")


async def test_respond_is_a_raw_pass_through(async_connector, fake_async_client: FakeAsyncClient) -> None:
    response = await async_connector.respond(input="hi", store=True)
    assert fake_async_client.responses.calls[0] == {
        "model": "chat",
        "input": "hi",
        "store": True,
    }
    assert response is fake_async_client.responses.response


async def test_parse_returns_the_validated_object(async_connector, fake_async_client: FakeAsyncClient) -> None:
    from pydantic import BaseModel

    class Answer(BaseModel):
        ok: bool

    result = await async_connector.parse("hello", text_format=Answer)
    assert result.parsed == {"ok": True}
    assert fake_async_client.responses.parse_calls[0]["text_format"] is Answer


async def test_default_output_cap_is_applied(fake_async_client: FakeAsyncClient) -> None:
    cfg = FoundryConfig(endpoint="https://acct.openai.azure.com/", default_max_output_tokens=32)
    async with connect_async(cfg, client=fake_async_client) as conn:
        await conn.ask("hello")
    assert fake_async_client.responses.calls[0]["max_output_tokens"] == 32


async def test_incomplete_status_is_reported_not_hidden(
    async_connector, fake_async_client: FakeAsyncClient
) -> None:
    fake_async_client.responses.response = FakeResponse(status="incomplete", output_text="par")
    result = await async_connector.ask("hello")
    assert result.status == "incomplete"
    assert result.complete is False
