"""Lifecycle: what gets closed, what does not, and what a closed connector does."""

from __future__ import annotations

import pytest

from azllm import FoundryConfig, LlmError, connect, connect_async
from azllm.aio import AsyncFoundryConnector
from azllm.connector import FoundryConnector
from fakes import (
    CountingAsyncTokenProvider,
    CountingTokenProvider,
    FakeAsyncClient,
    FakeAsyncCredential,
    FakeClient,
    FakeCredential,
)

CFG = FoundryConfig(endpoint="https://acct.openai.azure.com/")


def test_context_manager_closes_the_client() -> None:
    client = FakeClient()
    with connect(CFG, client=client) as conn:
        assert conn.ask("hi").text
    assert client.closed is True


def test_close_is_idempotent() -> None:
    client = FakeClient()
    conn = connect(CFG, client=client)
    conn.close()
    conn.close()
    assert client.closed is True


@pytest.mark.parametrize("call", ["ask", "respond", "parse", "stream_text", "stream_events", "client"])
def test_a_closed_connector_refuses_work(call: str) -> None:
    conn = connect(CFG, client=FakeClient())
    conn.close()
    with pytest.raises(LlmError) as caught:
        if call == "client":
            conn.client
        elif call == "ask":
            conn.ask("hi")
        elif call == "respond":
            conn.respond(input="hi")
        elif call == "parse":
            conn.parse("hi", text_format=dict)
        elif call == "stream_text":
            conn.stream_text("hi")
        else:
            conn.stream_events(input="hi")
    assert caught.value.category == "config"
    assert caught.value.retryable is False


def test_an_injected_credential_is_not_closed() -> None:
    credential = FakeCredential()
    conn = FoundryConnector(
        CFG, token_provider=CountingTokenProvider(), credential=credential, owns_credential=False
    )
    conn.close()
    assert credential.closed is False


def test_a_credential_the_connector_made_is_closed() -> None:
    credential = FakeCredential()
    conn = FoundryConnector(
        CFG, token_provider=CountingTokenProvider(), credential=credential, owns_credential=True
    )
    conn.close()
    assert credential.closed is True


def test_connect_never_takes_ownership_of_a_caller_credential() -> None:
    credential = FakeCredential()
    conn = connect(CFG, client=FakeClient(), credential=credential)
    conn.close()
    assert credential.closed is False


async def test_async_context_manager_closes_the_client() -> None:
    client = FakeAsyncClient()
    async with connect_async(CFG, client=client) as conn:
        assert (await conn.ask("hi")).text
    assert client.closed is True


async def test_aclose_is_idempotent_and_closes_an_owned_async_credential() -> None:
    credential = FakeAsyncCredential()
    conn = AsyncFoundryConnector(
        CFG,
        token_provider=CountingAsyncTokenProvider(),
        credential=credential,
        owns_credential=True,
    )
    await conn.aclose()
    await conn.aclose()
    assert credential.closed is True


async def test_a_closed_async_connector_refuses_work() -> None:
    conn = connect_async(CFG, client=FakeAsyncClient())
    await conn.aclose()
    with pytest.raises(LlmError):
        await conn.ask("hi")


def test_close_survives_a_client_that_raises_on_close() -> None:
    class AngryClient(FakeClient):
        def close(self) -> None:
            raise RuntimeError("no")

    conn = connect(CFG, client=AngryClient())
    conn.close()  # shutdown must not raise
