"""Client construction and auth wiring — the part that must not be frozen.

These tests build a *real* ``openai.OpenAI`` object. That is not a live
call: constructing a client opens no socket. It is the only way to assert
that this library hands the SDK a callable rather than a token string.
"""

from __future__ import annotations

import pytest

from azllm import FoundryConfig, connect, connect_async
from azllm.aio import AsyncFoundryConnector
from azllm.auth import async_bearer_token_provider, bearer_token_provider, default_async_credential
from azllm.connector import FoundryConnector
from fakes import CountingAsyncTokenProvider, CountingTokenProvider, FakeClient

ENDPOINT = "https://acct.openai.azure.com/"


@pytest.fixture
def cfg() -> FoundryConfig:
    return FoundryConfig(endpoint=ENDPOINT, deployment="chat", timeout_secs=33.0, max_retries=1)


def test_sync_client_is_built_from_config(cfg: FoundryConfig) -> None:
    provider = CountingTokenProvider()
    conn = FoundryConnector(cfg, token_provider=provider)
    try:
        client = conn.client
        assert str(client.base_url).rstrip("/") == cfg.base_url.rstrip("/")
        assert client.max_retries == 1
        assert client.timeout == 33.0
    finally:
        conn.close()


def test_the_sdk_receives_a_callable_not_a_token(cfg: FoundryConfig) -> None:
    provider = CountingTokenProvider()
    conn = FoundryConnector(cfg, token_provider=provider)
    try:
        # openai stores a callable api_key as `_api_key_provider` and calls it
        # on every request; a frozen string would land in `api_key` instead.
        assert conn.client._api_key_provider is provider
        assert conn.client.api_key == ""
    finally:
        conn.close()


def test_constructing_the_connector_mints_no_token(cfg: FoundryConfig) -> None:
    provider = CountingTokenProvider()
    conn = FoundryConnector(cfg, token_provider=provider)
    try:
        assert provider.calls == 0
    finally:
        conn.close()


def test_a_frozen_token_is_never_introduced(cfg: FoundryConfig) -> None:
    """Negative test for the classic bug: one token captured at startup.

    The SDK re-invokes the provider per request. Simulating two requests must
    therefore produce two distinct tokens; if any code path ever replaced the
    callable with ``credential.get_token(...).token`` this assertion breaks.
    """
    provider = CountingTokenProvider()
    conn = FoundryConnector(cfg, token_provider=provider)
    try:
        stored = conn.client._api_key_provider
        assert callable(stored)
        first, second = stored(), stored()
        assert first != second
        assert provider.calls == 2
        assert not isinstance(conn.token_provider, str)
    finally:
        conn.close()


async def test_async_client_receives_an_awaitable_provider(cfg: FoundryConfig) -> None:
    provider = CountingAsyncTokenProvider()
    conn = AsyncFoundryConnector(cfg, token_provider=provider)
    try:
        stored = conn.client._api_key_provider
        assert stored is provider
        assert await stored() != await stored()
        assert provider.calls == 2
    finally:
        await conn.aclose()


async def test_default_async_credential_has_its_runtime_transport(cfg: FoundryConfig) -> None:
    """Regression: azure.identity.aio constructs aiohttp transport eagerly."""
    credential = default_async_credential(cfg)
    await credential.close()


def test_client_and_provider_are_cached_for_the_connector_lifetime(cfg: FoundryConfig) -> None:
    provider = CountingTokenProvider()
    conn = FoundryConnector(cfg, token_provider=provider)
    try:
        assert conn.client is conn.client
        assert conn.token_provider is provider
    finally:
        conn.close()


def test_injected_client_bypasses_credential_construction(cfg: FoundryConfig) -> None:
    # No Azure login exists in CI; if a credential were built this would be
    # the test that hangs or fails.
    fake = FakeClient()
    conn = connect(cfg, client=fake)
    assert conn.client is fake
    assert conn.token_provider is None
    conn.close()


def test_connect_defaults_config_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AZURE_LLM_ENDPOINT", ENDPOINT)
    monkeypatch.setenv("AZURE_LLM_DEPLOYMENT", "chat-batch")
    conn = connect(client=FakeClient())
    assert conn.config.deployment == "chat-batch"
    conn.close()


async def test_connect_async_defaults_config_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    from fakes import FakeAsyncClient

    monkeypatch.setenv("AZURE_LLM_ENDPOINT", ENDPOINT)
    monkeypatch.setenv("AZURE_LLM_DEPLOYMENT", "chat-alternate")
    conn = connect_async(client=FakeAsyncClient())
    assert conn.config.deployment == "chat-alternate"
    await conn.aclose()


def test_bearer_token_provider_asks_the_credential_for_the_configured_scope(
    cfg: FoundryConfig,
) -> None:
    seen: list[tuple] = []

    class RecordingCredential:
        def get_token(self, *scopes, **kwargs):
            seen.append(scopes)

            class Token:
                token = "fake"
                expires_on = 4102444800  # far future, so no refresh occurs

            return Token()

    provider = bearer_token_provider(cfg, RecordingCredential())
    assert provider() == "fake"
    assert seen == [(cfg.credential_scope,)]


async def test_async_bearer_token_provider_is_a_coroutine_factory(cfg: FoundryConfig) -> None:
    class RecordingAsyncCredential:
        async def get_token(self, *scopes, **kwargs):
            class Token:
                token = "fake-async"
                expires_on = 4102444800

            return Token()

    provider = async_bearer_token_provider(cfg, RecordingAsyncCredential())
    awaited = provider()
    assert hasattr(awaited, "__await__")
    assert await awaited == "fake-async"
