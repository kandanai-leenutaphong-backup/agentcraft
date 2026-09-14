"""Regressions for defects found by review, each reproduced before it was fixed.

    pip install -r requirements-dev.txt && python3 -m pytest tests

Every check here failed against the code as reviewed. The asyncio ones drive
the **real** ``AsyncOpenAI`` client over ``httpx.MockTransport``, because the
defect they cover — cancellation being absorbed into ``ModelError`` — is only
observable at a real await point. Nothing sleeps to wait for state: an
``asyncio.Event`` reports when the handler has been entered.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest
from openai import AsyncOpenAI, OpenAI

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modelaccess import (  # noqa: E402
    ConfigError,
    FakeAsyncClient,
    FakeClient,
    ModelConfig,
    ModelError,
    connect,
    connect_async,
    fake_embedding_response,
    fake_text_response,
)

ENDPOINT = "https://example-account.openai.azure.com/"
OTHER_ENDPOINT = "https://example-embeddings-account.openai.azure.com/"


def make_config(**overrides: Any) -> ModelConfig:
    fields: dict[str, Any] = {
        "endpoint": ENDPOINT,
        "deployment": "my-chat-deployment",
        "embedding_deployment": "my-embedding-deployment",
        "timeout_secs": 5.0,
        "max_retries": 0,
    }
    fields.update(overrides)
    return ModelConfig(**fields)


def completed_body(text: str = "pong") -> dict[str, Any]:
    return {
        "id": "resp_1",
        "object": "response",
        "created_at": 0,
        "model": "my-chat-deployment",
        "status": "completed",
        "output": [
            {
                "type": "message",
                "id": "msg_1",
                "status": "completed",
                "role": "assistant",
                "content": [{"type": "output_text", "text": text, "annotations": []}],
            }
        ],
        "parallel_tool_calls": False,
        "tool_choice": "auto",
        "tools": [],
    }


async def async_provider() -> str:
    """AsyncOpenAI awaits its api_key provider; a plain callable is a TypeError."""
    return "token-static"


def build_async(handler: Any, config: ModelConfig) -> AsyncOpenAI:
    return AsyncOpenAI(
        base_url=config.base_url,
        api_key=async_provider,
        timeout=config.timeout_secs,
        max_retries=config.max_retries,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


class _Blocking:
    """A transport handler that parks the request until it is released."""

    def __init__(self) -> None:
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.cancelled = False

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        self.entered.set()
        try:
            await self.release.wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        return httpx.Response(200, json=completed_body())


# ------------------------------------------------------- F1 cancellation


async def test_task_cancel_stays_cancelled_and_is_not_reclassified() -> None:
    handler = _Blocking()
    config = make_config()
    client = connect_async(config, client=build_async(handler, config))
    task = asyncio.create_task(client.ask("hello"))
    await asyncio.wait_for(handler.entered.wait(), timeout=5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert task.cancelled() is True
    assert handler.cancelled is True
    await client.aclose()


async def test_wait_for_raises_timeout_error_not_model_error() -> None:
    handler = _Blocking()
    config = make_config()
    client = connect_async(config, client=build_async(handler, config))
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(client.ask("hello"), timeout=0.05)
    await client.aclose()


async def test_cancelling_a_stream_releases_it() -> None:
    class Stream:
        def __init__(self) -> None:
            self.opened = asyncio.Event()
            self.closed = False

        def __aiter__(self) -> "Stream":
            return self

        async def __anext__(self) -> Any:
            self.opened.set()
            await asyncio.Event().wait()  # never resolves; only cancellation ends it
            raise AssertionError("unreachable")

        async def close(self) -> None:
            self.closed = True

    stream = Stream()

    class Client(FakeAsyncClient):
        async def _acreate(self, **kwargs: Any) -> Any:  # type: ignore[override]
            return stream

    client = connect_async(make_config(), client=Client())

    async def drain() -> None:
        async for _ in client.stream_text("hello"):
            pass

    task = asyncio.create_task(drain())
    await asyncio.wait_for(stream.opened.wait(), timeout=5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert task.cancelled() is True
    assert stream.closed is True


# ------------------------------------------------- F2 sync interruptions


@pytest.mark.parametrize("interrupt", [KeyboardInterrupt, SystemExit, GeneratorExit])
def test_sync_interrupts_propagate_unchanged(interrupt: type[BaseException]) -> None:
    client = FakeClient(responses=[interrupt()])
    with connect(make_config(), client=client) as model:
        with pytest.raises(interrupt):
            model.ask("hello")


# --------------------------------------------- F6 cross-account embedding


def test_explicit_deployment_does_not_bypass_the_cross_account_guard() -> None:
    config = make_config(embedding_endpoint=OTHER_ENDPOINT)
    client = FakeClient(embeddings=[fake_embedding_response([[0.1, 0.2]])])
    with connect(config, client=client) as model:
        with pytest.raises(ConfigError) as caught:
            model.embed("hello", deployment="my-embedding-deployment")
    assert "not on this client's account" in str(caught.value)
    assert client.requests == []


def test_same_account_explicit_deployment_is_allowed() -> None:
    config = make_config(embedding_endpoint=ENDPOINT)
    client = FakeClient(embeddings=[fake_embedding_response([[0.1, 0.2]])])
    with connect(config, client=client) as model:
        result = model.embed("hello", deployment="another-embedding-deployment")
    assert result.vector == (0.1, 0.2)
    assert client.requests[0]["model"] == "another-embedding-deployment"


def test_embed_raw_carries_the_documented_escape_hatch() -> None:
    config = make_config(embedding_endpoint=OTHER_ENDPOINT)
    client = FakeClient(embeddings=[fake_embedding_response([[0.3]])])
    with connect(config, client=client) as model:
        with pytest.raises(ConfigError):
            model.embed_raw(input="hello")
        model.embed_raw(input="hello", allow_foreign_account=True)
    assert "allow_foreign_account" not in client.requests[-1]


# -------------------------------------------------- F7 client ownership


def test_an_injected_client_is_not_closed_by_either_connector() -> None:
    shared = FakeClient(responses=[fake_text_response("a"), fake_text_response("b")])
    first = connect(make_config(), client=shared)
    second = connect(make_config(), client=shared)
    first.close()
    assert shared.closed is False
    assert second.ask("hello").text == "a"
    second.close()
    assert shared.closed is False


def test_an_injected_client_is_closed_when_ownership_is_transferred() -> None:
    shared = FakeClient(responses=[])
    model = connect(make_config(), client=shared, owns_client=True)
    model.close()
    assert shared.closed is True


def test_an_internal_client_is_still_closed() -> None:
    config = make_config()
    built = OpenAI(
        base_url=config.base_url,
        api_key=lambda: "token-static",
        http_client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200))),
    )
    model = connect(config, client=built, owns_client=True)
    model.close()
    assert built.is_closed() is True


async def test_an_injected_async_client_is_not_closed_by_either_connector() -> None:
    shared = FakeAsyncClient(responses=[fake_text_response("a")])
    first = connect_async(make_config(), client=shared)
    second = connect_async(make_config(), client=shared)
    await first.aclose()
    assert shared.closed is False
    assert (await second.ask("hello")).text == "a"
    await second.aclose()
    assert shared.closed is False


# ------------------------------------------------ F9 conflicting options


def test_stream_events_refuses_a_conflicting_stream_option() -> None:
    client = FakeClient(streams=[[]])
    with connect(make_config(), client=client) as model:
        with pytest.raises(ConfigError) as caught:
            list(model.stream_events(input="hello", stream=False))
    assert "stream" in str(caught.value)


def test_stream_events_accepts_a_redundant_stream_true() -> None:
    client = FakeClient(streams=[[]])
    with connect(make_config(), client=client) as model:
        assert list(model.stream_events(input="hello", stream=True)) == []
    assert client.requests[0]["stream"] is True


async def test_async_stream_events_refuses_a_conflicting_stream_option() -> None:
    client = FakeAsyncClient(streams=[[]])
    model = connect_async(make_config(), client=client)
    with pytest.raises(ConfigError):
        model.stream_events(input="hello", stream=False)
    await model.aclose()


# ------------------------------------------------- F10 small corrections


async def test_async_streams_refuse_eagerly_on_a_closed_client() -> None:
    model = connect_async(make_config(), client=FakeAsyncClient())
    await model.aclose()
    with pytest.raises(ModelError):
        model.stream_text("hello")
    with pytest.raises(ModelError):
        model.stream_events(input="hello")


def test_a_model_error_from_below_is_not_its_own_cause() -> None:
    original = ModelError("already classified", category="stream")
    client = FakeClient(responses=[original])
    with connect(make_config(), client=client) as model:
        with pytest.raises(ModelError) as caught:
            model.ask("hello")
    assert caught.value is original
    assert caught.value.__cause__ is not caught.value


# ----------------------------------------------- F8 endpoint host limits


def test_an_endpoint_outside_the_allowlist_is_refused() -> None:
    with pytest.raises(ConfigError) as caught:
        ModelConfig(
            endpoint="https://attacker.example.com/",
            deployment="my-chat-deployment",
            allowed_hosts=("example-account.openai.azure.com",),
        )
    assert "allowed_hosts" in str(caught.value)


def test_an_allowlisted_endpoint_is_accepted_including_the_embedding_account() -> None:
    config = ModelConfig(
        endpoint=ENDPOINT,
        deployment="my-chat-deployment",
        embedding_deployment="my-embedding-deployment",
        embedding_endpoint=OTHER_ENDPOINT,
        allowed_hosts=(
            "example-account.openai.azure.com",
            "example-embeddings-account.openai.azure.com",
        ),
    )
    assert config.account_host == "example-account.openai.azure.com"

    with pytest.raises(ConfigError):
        config.with_overrides(embedding_endpoint="https://example-elsewhere.openai.azure.com/")


def test_json_body_still_carries_no_allowlist_field(tmp_path: Path) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=completed_body())

    config = ModelConfig(
        endpoint=ENDPOINT,
        deployment="my-chat-deployment",
        max_retries=0,
        allowed_hosts=("example-account.openai.azure.com",),
    )
    sdk = OpenAI(
        base_url=config.base_url,
        api_key=lambda: "token-static",
        max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    with connect(config, client=sdk, owns_client=True) as model:
        model.ask("ping")
    assert "allowed_hosts" not in json.loads(seen[0].content)
