"""Embeddings: routing, validation, alignment and safety — all offline.

Every test here injects a fake ``client``, so nothing reaches Azure. The
questions being asked are the ones a real account cannot answer cheaply: is
the *right* deployment chosen, is the request rejected before transport when
it is decidably wrong, and is a misaligned response ever returned as if it
were fine.
"""

from __future__ import annotations

import pytest

from azllm import (
    DEFAULT_EMBEDDING_DEPLOYMENT,
    ConfigError,
    EmbeddingResult,
    FoundryConfig,
    LlmError,
    connect,
    connect_async,
    embedding_config,
)
from fakes import (
    LEAKY_MESSAGE,
    FakeAsyncClient,
    FakeClient,
    FakeEmbeddingItem,
    FakeEmbeddingResponse,
    FakeUsage,
    status_error,
)

TEST_ENDPOINT = "https://acct.openai.azure.com/"


def make(client: FakeClient, **overrides: object):
    config = FoundryConfig(endpoint=TEST_ENDPOINT, deployment="chat")
    if overrides:
        config = config.with_overrides(**overrides)
    return connect(config, client=client)


# ------------------------------------------------------------- happy path


def test_single_string_returns_one_vector(connector, fake_client: FakeClient) -> None:
    result = connector.embed("hello")

    assert isinstance(result, EmbeddingResult)
    assert result.count == 1
    assert result.dimensions == 3
    assert result.vector == result.vectors[0]
    assert all(isinstance(value, float) for value in result.vector)
    assert fake_client.embeddings.calls[0]["input"] == "hello"


def test_batch_returns_vectors_in_input_order(connector, fake_client: FakeClient) -> None:
    fake_client.embeddings.response = FakeEmbeddingResponse(
        vectors=[(1.0, 1.0), (2.0, 2.0), (3.0, 3.0)]
    )

    result = connector.embed(["a", "b", "c"])

    assert result.count == 3
    assert result.vectors == ((1.0, 1.0), (2.0, 2.0), (3.0, 3.0))
    assert fake_client.embeddings.calls[0]["input"] == ["a", "b", "c"]


async def test_async_single_and_batch(fake_async_client: FakeAsyncClient) -> None:
    config = FoundryConfig(endpoint=TEST_ENDPOINT, deployment="chat")
    async with connect_async(config, client=fake_async_client) as llm:
        one = await llm.embed("hello")
        many = await llm.embed(["a", "b"])

    assert one.count == 1
    assert many.count == 2
    assert fake_async_client.embeddings.calls[1]["input"] == ["a", "b"]


def test_usage_and_model_survive(connector, fake_client: FakeClient) -> None:
    fake_client.embeddings.response = FakeEmbeddingResponse(
        model="text-embedding-3-large",
        usage=FakeUsage(prompt_tokens=11, total_tokens=11),
    )

    result = connector.embed("hello")

    assert result.model == "text-embedding-3-large"
    assert result.usage == {"prompt_tokens": 11, "total_tokens": 11}
    assert result.raw is fake_client.embeddings.response


# --------------------------------------------------------------- routing


def test_the_default_is_the_embedding_deployment_not_the_chat_one(
    connector, fake_client: FakeClient
) -> None:
    connector.embed("hello")

    assert connector.config.deployment == "chat"
    assert fake_client.embeddings.calls[0]["model"] == DEFAULT_EMBEDDING_DEPLOYMENT


def test_a_configured_embedding_deployment_is_honoured(fake_client: FakeClient) -> None:
    with make(fake_client, deployment="text-embedding-3-small") as llm:
        result = llm.embed("hello")

    assert fake_client.embeddings.calls[0]["model"] == "text-embedding-3-small"
    assert result.deployment == "text-embedding-3-small"


def test_per_call_override_does_not_mutate_the_connector(
    connector, fake_client: FakeClient
) -> None:
    connector.embed("hello", deployment="text-embedding-3-small")
    connector.embed("hello")

    models = [call["model"] for call in fake_client.embeddings.calls]
    assert models == ["text-embedding-3-small", DEFAULT_EMBEDDING_DEPLOYMENT]
    assert connector.config.deployment == "chat"


def test_a_blank_override_is_refused(connector) -> None:
    with pytest.raises(ConfigError):
        connector.embed("hello", deployment="   ")


def test_embedding_config_routes_each_deployment_to_its_own_account() -> None:
    small = embedding_config("text-embedding-3-small", endpoint="https://secondary.example.invalid")
    large = embedding_config(endpoint="https://primary.example.invalid")

    assert small.deployment == "text-embedding-3-small"
    assert small.account_host == "secondary.example.invalid"
    assert large.deployment == DEFAULT_EMBEDDING_DEPLOYMENT
    assert large.account_host == "primary.example.invalid"


def test_embedding_config_rejects_an_unknown_deployment_without_an_endpoint() -> None:
    with pytest.raises(ConfigError) as caught:
        embedding_config("text-embedding-9-imaginary")

    assert "not a known embedding deployment" in caught.value.message
    assert caught.value.category == "config"


def test_embedding_config_accepts_an_unknown_deployment_with_an_endpoint() -> None:
    config = embedding_config("text-embedding-9-imaginary", endpoint=TEST_ENDPOINT)

    assert config.deployment == "text-embedding-9-imaginary"
    assert config.account_host == "acct.openai.azure.com"


def test_embedding_config_keeps_the_base_settings() -> None:
    base = FoundryConfig(endpoint=TEST_ENDPOINT, timeout_secs=7.5, max_retries=0)
    config = embedding_config("text-embedding-3-small", endpoint="https://secondary.example.invalid", base=base)

    assert (config.timeout_secs, config.max_retries) == (7.5, 0)
    assert config.account_host == "secondary.example.invalid"


def test_connecting_through_embedding_config_reaches_the_right_account(
    fake_client: FakeClient,
) -> None:
    config = embedding_config("text-embedding-3-small", endpoint="https://secondary.example.invalid")
    with connect(config, client=fake_client) as llm:
        llm.embed("hello")

    assert llm.config.base_url == "https://secondary.example.invalid/openai/v1/"
    assert fake_client.embeddings.calls[0]["model"] == "text-embedding-3-small"


# ------------------------------------------------- validation before wire


def test_dimensions_is_forwarded(connector, fake_client: FakeClient) -> None:
    connector.embed("hello", dimensions=256)

    assert fake_client.embeddings.calls[0]["dimensions"] == 256


def test_dimensions_is_absent_when_not_asked_for(connector, fake_client: FakeClient) -> None:
    connector.embed("hello")

    assert "dimensions" not in fake_client.embeddings.calls[0]


@pytest.mark.parametrize("bad", [0, -1, True, False, 1.5, "512"])
def test_bad_dimensions_never_reaches_the_wire(
    connector, fake_client: FakeClient, bad: object
) -> None:
    with pytest.raises(ConfigError):
        connector.embed("hello", dimensions=bad)

    assert fake_client.embeddings.calls == []


@pytest.mark.parametrize("bad", [None, 7, 1.5, True, b"bytes", {"a": "b"}, object()])
def test_bad_input_types_never_reach_the_wire(
    connector, fake_client: FakeClient, bad: object
) -> None:
    with pytest.raises(ConfigError):
        connector.embed(bad)

    assert fake_client.embeddings.calls == []


@pytest.mark.parametrize("bad", ["", "   ", ["ok", ""], ["ok", "  "], ["ok", 3], [None]])
def test_empty_or_non_string_entries_are_refused(
    connector, fake_client: FakeClient, bad: object
) -> None:
    with pytest.raises(ConfigError):
        connector.embed(bad)

    assert fake_client.embeddings.calls == []


def test_an_empty_batch_is_refused(connector, fake_client: FakeClient) -> None:
    with pytest.raises(ConfigError) as caught:
        connector.embed([])

    assert "nothing to embed" in caught.value.message
    assert fake_client.embeddings.calls == []


def test_the_batch_ceiling_is_enforced_locally(connector, fake_client: FakeClient) -> None:
    with pytest.raises(ConfigError) as caught:
        connector.embed(["x"] * 2049)

    assert "2048" in caught.value.message
    assert fake_client.embeddings.calls == []


def test_exactly_the_ceiling_is_allowed(connector, fake_client: FakeClient) -> None:
    result = connector.embed(["x"] * 2048)

    assert result.count == 2048


@pytest.mark.parametrize("reserved", ["model", "input", "dimensions"])
def test_reserved_options_collide_loudly(
    connector, fake_client: FakeClient, reserved: str
) -> None:
    with pytest.raises(ConfigError) as caught:
        connector.embed("hello", **{reserved: "x"})

    assert reserved in caught.value.message
    assert fake_client.embeddings.calls == []


def test_arbitrary_options_pass_through(connector, fake_client: FakeClient) -> None:
    connector.embed("hello", encoding_format="float", user="analyst-1", extra_headers={"a": "b"})

    call = fake_client.embeddings.calls[0]
    assert call["encoding_format"] == "float"
    assert call["user"] == "analyst-1"
    assert call["extra_headers"] == {"a": "b"}


def test_a_generator_is_snapshotted(connector, fake_client: FakeClient) -> None:
    result = connector.embed(str(i) for i in range(3))

    assert fake_client.embeddings.calls[0]["input"] == ["0", "1", "2"]
    assert result.count == 3


def test_mutating_the_caller_list_afterwards_cannot_desynchronise(
    connector, fake_client: FakeClient
) -> None:
    inputs = ["a", "b"]
    sent = connector.embed(inputs)
    inputs.append("c")

    assert sent.count == 2
    assert fake_client.embeddings.calls[0]["input"] == ["a", "b"]


# --------------------------------------------------------- response shape


def test_out_of_order_indexes_are_sorted_back_into_input_order(
    connector, fake_client: FakeClient
) -> None:
    fake_client.embeddings.response = FakeEmbeddingResponse(
        vectors=[(2.0,), (0.0,), (1.0,)], indexes=[2, 0, 1]
    )

    result = connector.embed(["a", "b", "c"])

    assert result.vectors == ((0.0,), (1.0,), (2.0,))


def test_integer_components_are_coerced_to_float(connector, fake_client: FakeClient) -> None:
    fake_client.embeddings.response = FakeEmbeddingResponse(vectors=[(0, 1, -1)])

    result = connector.embed("hello")

    assert result.vector == (0.0, 1.0, -1.0)
    assert all(isinstance(value, float) for value in result.vector)


@pytest.mark.parametrize(
    "response",
    [
        FakeEmbeddingResponse(vectors=[(1.0,), (2.0,)], indexes=[0, 0]),
        FakeEmbeddingResponse(vectors=[(1.0,), (2.0,)], indexes=[0, 5]),
        FakeEmbeddingResponse(vectors=[(1.0,), (2.0,)], indexes=[0, -1]),
        FakeEmbeddingResponse(vectors=[(1.0,), (2.0, 3.0)]),
        FakeEmbeddingResponse(vectors=[(1.0,), ()]),
        FakeEmbeddingResponse(vectors=[(1.0,), (float("nan"),)]),
        FakeEmbeddingResponse(vectors=[(1.0,), (float("inf"),)]),
        FakeEmbeddingResponse(vectors=[(1.0,), ("0.5",)]),
        FakeEmbeddingResponse(vectors=[(1.0,), (True,)]),
        FakeEmbeddingResponse(vectors=[(1.0,), (None,)]),
        FakeEmbeddingResponse(data=[FakeEmbeddingItem(0, (1.0,))]),
        FakeEmbeddingResponse(data=[FakeEmbeddingItem("0", (1.0,)), FakeEmbeddingItem(1, (2.0,))]),
        FakeEmbeddingResponse(data=[FakeEmbeddingItem(0, None), FakeEmbeddingItem(1, (2.0,))]),
        FakeEmbeddingResponse(data=None),
        FakeEmbeddingResponse(data="not-a-list"),
    ],
)
def test_a_response_that_cannot_be_aligned_raises_rather_than_misleading(
    connector, fake_client: FakeClient, response: object
) -> None:
    fake_client.embeddings.response = response

    with pytest.raises(LlmError) as caught:
        connector.embed(["a", "b"])

    assert caught.value.category == "unknown"
    assert caught.value.retryable is False
    assert "malformed" in caught.value.message


def test_base64_vectors_say_so_instead_of_failing_obscurely(
    connector, fake_client: FakeClient
) -> None:
    fake_client.embeddings.response = FakeEmbeddingResponse(vectors=["ZmFrZQ=="])

    with pytest.raises(ConfigError) as caught:
        connector.embed("hello")

    assert "base64" in caught.value.message


def test_dict_shaped_items_are_accepted(connector, fake_client: FakeClient) -> None:
    fake_client.embeddings.response = FakeEmbeddingResponse(
        data=[{"index": 1, "embedding": [2.0]}, {"index": 0, "embedding": [1.0]}]
    )

    result = connector.embed(["a", "b"])

    assert result.vectors == ((1.0,), (2.0,))


# ---------------------------------------------------------------- result


def test_vector_refuses_to_guess_on_a_batch(connector) -> None:
    result = connector.embed(["a", "b"])

    with pytest.raises(ConfigError) as caught:
        _ = result.vector

    assert "2 vectors" in caught.value.message


def test_metadata_and_repr_carry_no_vectors(connector, fake_client: FakeClient) -> None:
    fake_client.embeddings.response = FakeEmbeddingResponse(vectors=[(0.123456, 0.98765)])

    result = connector.embed("hello")
    metadata = result.metadata()
    text = repr(result)

    assert set(metadata) == {"deployment", "model", "count", "dimensions", "usage"}
    assert metadata["count"] == 1
    assert metadata["dimensions"] == 2
    assert "0.123456" not in str(metadata)
    assert "0.123456" not in text
    assert "hello" not in text


def test_the_result_is_immutable(connector) -> None:
    result = connector.embed("hello")

    with pytest.raises(Exception):
        result.vectors = ()  # type: ignore[misc]
    assert isinstance(result.vectors, tuple)


# ----------------------------------------------------------------- errors


def test_provider_errors_are_translated_and_sanitised(
    connector, fake_client: FakeClient
) -> None:
    import openai

    fake_client.embeddings.raises = status_error(openai.NotFoundError, 404)

    with pytest.raises(LlmError) as caught:
        connector.embed("hello")

    exc = caught.value
    assert exc.category == "not_found"
    assert exc.status_code == 404
    assert exc.deployment == DEFAULT_EMBEDDING_DEPLOYMENT
    assert LEAKY_MESSAGE not in str(exc)
    assert "hello" not in str(exc)
    assert isinstance(exc.__cause__, openai.NotFoundError)


async def test_async_provider_errors_are_translated(
    fake_async_client: FakeAsyncClient,
) -> None:
    import openai

    fake_async_client.embeddings.raises = status_error(openai.RateLimitError, 429)
    config = FoundryConfig(endpoint=TEST_ENDPOINT)
    async with connect_async(config, client=fake_async_client) as llm:
        with pytest.raises(LlmError) as caught:
            await llm.embed("hello")

    assert caught.value.category == "rate_limit"
    assert caught.value.retryable is True
    assert LEAKY_MESSAGE not in str(caught.value)


def test_a_closed_connector_refuses_to_embed(config, fake_client: FakeClient) -> None:
    llm = connect(config, client=fake_client)
    llm.close()

    with pytest.raises(LlmError) as caught:
        llm.embed("hello")
    with pytest.raises(LlmError):
        llm.embed_raw(input="hello")

    assert caught.value.category == "config"
    assert fake_client.embeddings.calls == []


async def test_a_closed_async_connector_refuses_to_embed(
    config, fake_async_client: FakeAsyncClient
) -> None:
    llm = connect_async(config, client=fake_async_client)
    await llm.aclose()

    with pytest.raises(LlmError):
        await llm.embed("hello")

    assert fake_async_client.embeddings.calls == []


def test_embedding_does_not_disturb_the_chat_path(connector, fake_client: FakeClient) -> None:
    connector.embed("hello")
    answer = connector.ask("hi")

    assert answer.deployment == "chat"
    assert fake_client.responses.calls[0]["model"] == "chat"
    assert fake_client.embeddings.calls[0]["model"] == DEFAULT_EMBEDDING_DEPLOYMENT


# -------------------------------------------------------------- embed_raw


def test_embed_raw_defaults_only_the_deployment(connector, fake_client: FakeClient) -> None:
    response = connector.embed_raw(input="hello", encoding_format="base64")

    call = fake_client.embeddings.calls[0]
    assert call["model"] == DEFAULT_EMBEDDING_DEPLOYMENT
    assert call["encoding_format"] == "base64"
    assert response is fake_client.embeddings.response or response is not None


def test_embed_raw_honours_an_explicit_model(connector, fake_client: FakeClient) -> None:
    connector.embed_raw(input="hello", model="text-embedding-3-small")

    assert fake_client.embeddings.calls[0]["model"] == "text-embedding-3-small"


def test_embed_raw_refuses_a_blank_model(connector, fake_client: FakeClient) -> None:
    with pytest.raises(ConfigError):
        connector.embed_raw(input="hello", model="  ")

    assert fake_client.embeddings.calls == []


async def test_async_embed_raw(fake_async_client: FakeAsyncClient) -> None:
    config = FoundryConfig(endpoint=TEST_ENDPOINT)
    async with connect_async(config, client=fake_async_client) as llm:
        await llm.embed_raw(input="hello")

    assert fake_async_client.embeddings.calls[0]["model"] == DEFAULT_EMBEDDING_DEPLOYMENT
