"""The SDK's own contract, driven over an in-process HTTP transport.

    pip install -r requirements-dev.txt && python3 -m pytest tests

Every other suite injects a fake client, which proves this package's logic and
nothing about the SDK's. These tests use the **real** ``openai`` client with
``httpx.MockTransport`` in place of a socket, so what is asserted is the shape
of the request that would have gone on the wire and the behaviour of the SDK
this package depends on. No network, no cloud sign-in, no credential.

The framework-free ``tests/selftest.py`` covers the same identity claim; this
file goes further into streaming, retries, structured output and the async
client, where a framework earns its keep.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Callable

import httpx
import pytest
from openai import AsyncOpenAI, OpenAI

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modelaccess import ModelConfig, ModelError, connect, connect_async  # noqa: E402

ENDPOINT = "https://example-account.openai.azure.com/"


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


def sse(events: list[dict[str, Any]]) -> bytes:
    """Server-sent events exactly as the Responses API streams them."""
    return "".join(
        f"event: {event['type']}\ndata: {json.dumps(event)}\n\n" for event in events
    ).encode()


def build(handler: Callable[[httpx.Request], httpx.Response], config: ModelConfig) -> OpenAI:
    return OpenAI(
        base_url=config.base_url,
        api_key=lambda: "token-static",
        timeout=config.timeout_secs,
        max_retries=config.max_retries,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def test_request_path_and_body_match_the_documented_shape() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=completed_body())

    config = make_config()
    with connect(config, client=build(handler, config)) as model:
        model.ask("ping", instructions="be terse")

    assert str(seen[0].url) == ENDPOINT + "openai/v1/responses"
    assert seen[0].method == "POST"
    body = json.loads(seen[0].content)
    # `model` carries the *deployment* name, which is the whole Azure trap.
    assert body["model"] == "my-chat-deployment"
    assert body["input"] == "ping"
    assert body["instructions"] == "be terse"
    assert body["store"] is False


def test_token_callable_is_invoked_once_per_request_not_frozen() -> None:
    issued: list[str] = []
    headers: list[str] = []

    def provider() -> str:
        issued.append(f"token-{len(issued)}")
        return issued[-1]

    def handler(request: httpx.Request) -> httpx.Response:
        headers.append(request.headers["authorization"])
        return httpx.Response(200, json=completed_body())

    config = make_config()
    sdk = OpenAI(
        base_url=config.base_url,
        api_key=provider,
        timeout=config.timeout_secs,
        max_retries=config.max_retries,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    with connect(config, client=sdk) as model:
        for _ in range(3):
            model.ask("ping")

    assert issued == ["token-0", "token-1", "token-2"]
    assert headers == ["Bearer token-0", "Bearer token-1", "Bearer token-2"]
    assert len(set(headers)) == 3


def test_streamed_text_is_assembled_from_real_sse_frames() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=sse(
                [
                    {"type": "response.output_text.delta", "delta": "Hel", "sequence_number": 1},
                    {"type": "response.output_text.delta", "delta": "lo", "sequence_number": 2},
                    {"type": "response.completed", "sequence_number": 3,
                     "response": completed_body("Hello")},
                ]
            ),
        )

    config = make_config()
    with connect(config, client=build(handler, config)) as model:
        assert list(model.stream_text("ping")) == ["Hel", "lo"]


def test_an_error_event_inside_a_200_stream_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=sse(
                [
                    {"type": "response.output_text.delta", "delta": "par", "sequence_number": 1},
                    {"type": "error", "code": "content_filter", "sequence_number": 2,
                     "message": "the prompt 'patient 12345' was filtered", "param": None},
                ]
            ),
        )

    config = make_config()
    collected: list[str] = []
    with connect(config, client=build(handler, config)) as model:
        with pytest.raises(ModelError) as caught:
            for chunk in model.stream_text("ping"):
                collected.append(chunk)

    assert collected == ["par"]
    assert caught.value.category == "stream"
    assert caught.value.code == "content_filter"
    assert "patient 12345" not in str(caught.value)


def test_status_errors_are_classified_and_carry_no_provider_body() -> None:
    cases = {
        401: ("auth", False),
        403: ("auth", False),
        404: ("not_found", False),
        400: ("bad_request", False),
        429: ("rate_limit", True),
        500: ("server", True),
    }
    for status, (category, retryable) in cases.items():
        def handler(request: httpx.Request, status: int = status) -> httpx.Response:
            return httpx.Response(
                status,
                json={"error": {"code": "the_code",
                                "message": "prompt 'patient 12345 has a rash' refused"}},
                headers={"x-request-id": "req-9"},
            )

        config = make_config()
        with connect(config, client=build(handler, config)) as model:
            with pytest.raises(ModelError) as caught:
                model.ask("patient 12345 has a rash")

        assert caught.value.category == category, status
        assert caught.value.status_code == status
        assert caught.value.retryable is retryable
        assert caught.value.request_id == "req-9"
        assert "patient 12345" not in str(caught.value)
        # The original is still reachable for a debugger.
        assert caught.value.__cause__ is not None


def test_max_retries_is_the_ceiling_the_config_set() -> None:
    attempts: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        return httpx.Response(500, json={"error": {"code": "server_error", "message": "boom"}})

    config = make_config(max_retries=2)
    sdk = OpenAI(
        base_url=config.base_url,
        api_key=lambda: "token-static",
        timeout=config.timeout_secs,
        max_retries=config.max_retries,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    with connect(config, client=sdk) as model:
        with pytest.raises(ModelError) as caught:
            model.ask("ping")

    assert caught.value.category == "server"
    assert caught.value.retryable is True
    # One attempt plus two retries. More retries against a 5xx is a queue.
    assert len(attempts) == 3


def test_a_client_timeout_is_a_timeout_not_an_unknown() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("read timed out", request=request)

    config = make_config()
    with connect(config, client=build(handler, config)) as model:
        with pytest.raises(ModelError) as caught:
            model.ask("ping")

    assert caught.value.category == "timeout"
    assert caught.value.retryable is True


def test_a_connection_failure_is_reported_as_one() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("name resolution failed", request=request)

    config = make_config()
    with connect(config, client=build(handler, config)) as model:
        with pytest.raises(ModelError) as caught:
            model.ask("ping")

    assert caught.value.category == "connection"
    assert caught.value.retryable is True


def test_structured_output_sends_a_json_schema_and_validates_the_answer() -> None:
    pydantic = pytest.importorskip("pydantic")

    class Severity(pydantic.BaseModel):
        level: str
        confidence: float

    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        body = completed_body('{"level":"high","confidence":0.82}')
        return httpx.Response(200, json=body)

    config = make_config()
    with connect(config, client=build(handler, config)) as model:
        result = model.parse("classify", text_format=Severity)

    sent = json.loads(seen[0].content)
    # The SDK derived the schema from the class; the server enforces it.
    assert sent["text"]["format"]["type"] == "json_schema"
    assert set(sent["text"]["format"]["schema"]["properties"]) == {"level", "confidence"}
    assert isinstance(result.parsed, Severity)
    assert result.parsed.level == "high"
    assert result.refused is False


def test_a_refusal_leaves_parsed_none_without_raising() -> None:
    pydantic = pytest.importorskip("pydantic")

    class Severity(pydantic.BaseModel):
        level: str

    def handler(request: httpx.Request) -> httpx.Response:
        body = completed_body()
        body["output"] = [
            {
                "type": "message",
                "id": "msg_1",
                "status": "completed",
                "role": "assistant",
                "content": [{"type": "refusal", "refusal": "I can't help with that."}],
            }
        ]
        return httpx.Response(200, json=body)

    config = make_config()
    with connect(config, client=build(handler, config)) as model:
        result = model.parse("classify", text_format=Severity)

    assert result.parsed is None
    assert result.refused is True
    assert result.refusal == "I can't help with that."
    assert result.complete is True


def test_embeddings_go_to_the_embeddings_route_and_align() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "object": "list",
                "model": "my-embedding-deployment",
                # Deliberately shuffled: alignment is by index, not arrival.
                "data": [
                    {"object": "embedding", "index": 1, "embedding": [2.0, 2.5]},
                    {"object": "embedding", "index": 0, "embedding": [1.0, 1.5]},
                ],
                "usage": {"prompt_tokens": 4, "total_tokens": 4},
            },
        )

    config = make_config()
    with connect(config, client=build(handler, config)) as model:
        result = model.embed(["first", "second"])

    assert str(seen[0].url) == ENDPOINT + "openai/v1/embeddings"
    assert json.loads(seen[0].content)["model"] == "my-embedding-deployment"
    assert result.vectors == ((1.0, 1.5), (2.0, 2.5))
    assert result.usage["total_tokens"] == 4


@pytest.mark.asyncio
async def test_async_client_awaits_its_token_provider() -> None:
    issued: list[str] = []
    headers: list[str] = []

    async def provider() -> str:
        issued.append(f"token-{len(issued)}")
        return issued[-1]

    async def handler(request: httpx.Request) -> httpx.Response:
        headers.append(request.headers["authorization"])
        return httpx.Response(200, json=completed_body())

    config = make_config()
    sdk = AsyncOpenAI(
        base_url=config.base_url,
        api_key=provider,
        timeout=config.timeout_secs,
        max_retries=config.max_retries,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    async with connect_async(config, client=sdk) as model:
        assert (await model.ask("ping")).text == "pong"
        assert (await model.ask("ping")).text == "pong"

    assert headers == ["Bearer token-0", "Bearer token-1"]


@pytest.mark.asyncio
async def test_async_streaming_reports_an_in_band_failure() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=sse(
                [
                    {"type": "response.output_text.delta", "delta": "a", "sequence_number": 1},
                    {"type": "response.failed", "sequence_number": 2,
                     "response": dict(completed_body(), status="failed",
                                      error={"code": "server_error", "message": "boom"})},
                ]
            ),
        )

    async def token() -> str:
        # AsyncOpenAI *awaits* its provider; a sync callable fails on
        # `await "eyJ..."` before a request is ever made.
        return "token-static"

    config = make_config()
    sdk = AsyncOpenAI(
        base_url=config.base_url,
        api_key=token,
        timeout=config.timeout_secs,
        max_retries=config.max_retries,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    collected: list[str] = []
    async with connect_async(config, client=sdk) as model:
        with pytest.raises(ModelError) as caught:
            async for chunk in model.stream_text("ping"):
                collected.append(chunk)

    assert collected == ["a"]
    assert caught.value.category == "stream"
    assert caught.value.code == "server_error"


@pytest.mark.asyncio
async def test_a_sync_token_provider_on_the_async_client_fails_sanitised() -> None:
    """The mismatch G5 exists for, proven rather than asserted in prose."""

    async def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("no request should be made: the provider fails first")

    config = make_config()
    sdk = AsyncOpenAI(
        base_url=config.base_url,
        api_key=lambda: "token-static",  # sync callable, awaited by AsyncOpenAI
        timeout=config.timeout_secs,
        max_retries=config.max_retries,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    async with connect_async(config, client=sdk) as model:
        with pytest.raises(ModelError) as caught:
            await model.ask("ping")

    assert caught.value.category == "unknown"
    assert caught.value.retryable is False
    assert isinstance(caught.value.__cause__, TypeError)
