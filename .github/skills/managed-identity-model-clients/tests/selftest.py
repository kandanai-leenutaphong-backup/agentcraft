#!/usr/bin/env python3
"""selftest.py — proves this box works here, with no test framework installed.

    python3 tests/selftest.py

Every check is offline. The only third-party requirement is the declared
dependency surface; the SDK-protocol checks at the end are skipped, loudly, if
``openai``/``httpx`` are absent, and everything else still runs on a bare
interpreter.

Exit code 0 means every check passed. Any failure prints the traceback and
exits 1.
"""

from __future__ import annotations

import asyncio
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modelaccess import (  # noqa: E402
    MAX_EMBEDDING_INPUTS,
    AsyncModelClient,
    ConfigError,
    EmbeddingResult,
    FakeAsyncClient,
    FakeClient,
    ModelClient,
    ModelConfig,
    ModelError,
    ParsedResult,
    TextResult,
    connect,
    connect_async,
    embedding_config,
    fake_embedding_response,
    fake_parsed_response,
    fake_text_response,
    normalize_endpoint,
    stream_error_event,
    stream_failed_event,
    text_delta_event,
)
from modelaccess.errors import classify, stream_error  # noqa: E402
from modelaccess.invoke import (  # noqa: E402
    convenience_request,
    embedding_raw_request,
    raw_request,
)
from modelaccess.results import usage_dict  # noqa: E402

ENDPOINT = "https://example-account.openai.azure.com/"
OTHER_ENDPOINT = "https://example-embeddings-account.openai.azure.com/"

CHECKS: list = []
SKIPPED: list[str] = []


def check(fn):
    CHECKS.append(fn)
    return fn


def config(**overrides) -> ModelConfig:
    fields = {"endpoint": ENDPOINT, "deployment": "my-chat-deployment"}
    fields.update(overrides)
    return ModelConfig(**fields)


def refuses(exc_type, fn, *, contains: str = "") -> BaseException:
    try:
        fn()
    except exc_type as raised:
        if contains:
            assert contains in str(raised), f"{contains!r} not in {raised!s}"
        return raised
    raise AssertionError(f"expected {exc_type.__name__}, nothing was raised")


# ----------------------------------------------------------------- config


@check
def endpoint_normalisation_is_idempotent_and_accepts_every_paste() -> None:
    want = "https://example-account.openai.azure.com/openai/v1/"
    for raw in (
        "example-account.openai.azure.com",
        "https://example-account.openai.azure.com",
        "https://example-account.openai.azure.com/",
        "https://example-account.openai.azure.com/openai",
        "https://example-account.openai.azure.com/openai/v1",
        "https://example-account.openai.azure.com/openai/v1/",
        "  https://EXAMPLE-account.openai.azure.com/  ",
    ):
        assert normalize_endpoint(raw) == want, raw
    assert normalize_endpoint(want) == want
    # A gateway path in front of the account is preserved.
    assert (
        normalize_endpoint("https://example-gateway.internal/models/openai")
        == "https://example-gateway.internal/models/openai/v1/"
    )


@check
def endpoint_refuses_everything_undecidable_later() -> None:
    refuses(ConfigError, lambda: normalize_endpoint(""), contains="MODEL_ENDPOINT")
    refuses(ConfigError, lambda: normalize_endpoint("http://example-account.local"),
            contains="must be https")
    refuses(ConfigError, lambda: normalize_endpoint("https://u:p@example-account.local"),
            contains="must not embed credentials")
    refuses(ConfigError, lambda: normalize_endpoint("https://example-account.local?k=1"),
            contains="query string")
    refuses(ConfigError, lambda: normalize_endpoint("https://example-account.local/a b"),
            contains="whitespace")
    refuses(ConfigError, lambda: normalize_endpoint("https://example-account.local/../x"),
            contains="'..'")


@check
def config_requires_an_endpoint_and_a_deployment() -> None:
    refuses(TypeError, lambda: ModelConfig())  # type: ignore[call-arg]
    refuses(ConfigError, lambda: config(deployment=""), contains="deployment is empty")
    refuses(ConfigError, lambda: config(deployment="bad name!"), contains="not allowed")
    refuses(ConfigError, lambda: config(deployment="x" * 65), contains="longer than 64")


@check
def config_validates_scope_timeout_retries_and_caps() -> None:
    refuses(ConfigError, lambda: config(credential_scope="https://x/"), contains="/.default")
    refuses(ConfigError, lambda: config(credential_scope="http://x/.default"), contains="https")
    refuses(ConfigError, lambda: config(timeout_secs=0), contains="positive finite")
    refuses(ConfigError, lambda: config(timeout_secs=float("inf")), contains="positive finite")
    refuses(ConfigError, lambda: config(timeout_secs="30"), contains="must be a number")
    refuses(ConfigError, lambda: config(max_retries=True), contains="must be an int")
    refuses(ConfigError, lambda: config(max_retries=11), contains="between 0 and 10")
    refuses(ConfigError, lambda: config(max_retries=-1), contains="between 0 and 10")
    refuses(ConfigError, lambda: config(managed_identity_client_id="  "), contains="blank")
    refuses(ConfigError, lambda: config(default_max_output_tokens=0), contains="positive int")
    assert config(max_retries=0).max_retries == 0


@check
def config_is_frozen_and_overrides_are_validated() -> None:
    base = config()
    refuses(Exception, lambda: setattr(base, "deployment", "other"))
    refuses(ConfigError, lambda: base.with_overrides(nope=1), contains="unknown config field")
    refuses(ConfigError, lambda: base.with_overrides(max_retries=99), contains="between 0 and 10")
    assert base.with_overrides(deployment="second").deployment == "second"
    assert base.deployment == "my-chat-deployment", "with_overrides must not mutate the original"
    assert base.account_host == "example-account.openai.azure.com"


@check
def from_env_names_the_variable_it_needs() -> None:
    refuses(ConfigError, lambda: ModelConfig.from_env(env={}), contains="MODEL_ENDPOINT is not set")
    refuses(
        ConfigError,
        lambda: ModelConfig.from_env(env={"MODEL_ENDPOINT": ENDPOINT}),
        contains="MODEL_DEPLOYMENT is not set",
    )
    built = ModelConfig.from_env(
        env={
            "MODEL_ENDPOINT": ENDPOINT,
            "MODEL_DEPLOYMENT": "my-chat-deployment",
            "MODEL_EMBEDDING_DEPLOYMENT": "my-embedding-deployment",
            "MODEL_EMBEDDING_ENDPOINT": OTHER_ENDPOINT,
            "MODEL_TIMEOUT_SECONDS": "45.5",
            "MODEL_MAX_RETRIES": "3",
            "MODEL_CLIENT_ID": "00000000-0000-0000-0000-000000000000",
            "MODEL_MAX_OUTPUT_TOKENS": "512",
        }
    )
    assert built.timeout_secs == 45.5
    assert built.max_retries == 3
    assert built.embedding_deployment == "my-embedding-deployment"
    assert built.embeddings_are_local is False
    assert built.default_max_output_tokens == 512
    refuses(
        ConfigError,
        lambda: ModelConfig.from_env(
            env={"MODEL_ENDPOINT": ENDPOINT, "MODEL_DEPLOYMENT": "d",
                 "MODEL_MAX_RETRIES": "many"}
        ),
        contains="must be an integer",
    )


@check
def from_env_refuses_key_authentication_loudly() -> None:
    base = {"MODEL_ENDPOINT": ENDPOINT, "MODEL_DEPLOYMENT": "my-chat-deployment"}
    for key in ("MODEL_API_KEY", "MODEL_KEY", "AZURE_OPENAI_API_KEY", "OPENAI_API_KEY"):
        refuses(
            ConfigError,
            lambda k=key: ModelConfig.from_env(env=dict(base, **{k: "unset-placeholder"})),
            contains=key,
        )


@check
def embedding_config_points_at_the_owning_account() -> None:
    refuses(ConfigError, lambda: embedding_config(config()), contains="no embedding deployment")
    split = config(
        embedding_deployment="my-embedding-deployment", embedding_endpoint=OTHER_ENDPOINT
    )
    second = embedding_config(split)
    assert second.base_url == OTHER_ENDPOINT + "openai/v1/"
    assert second.deployment == "my-embedding-deployment"
    assert second.embeddings_are_local is True
    # Timeouts and retries survive; the caller's tuning is not discarded.
    tuned = embedding_config(split.with_overrides(max_retries=5, timeout_secs=9.0))
    assert (tuned.max_retries, tuned.timeout_secs) == (5, 9.0)
    named = embedding_config(config(), deployment="other-embeddings", endpoint=OTHER_ENDPOINT)
    assert named.deployment == "other-embeddings"


# --------------------------------------------------------------- requests


@check
def convenience_requests_are_shaped_once_and_refuse_ambiguity() -> None:
    cfg = config(default_max_output_tokens=64)
    request = convenience_request(
        cfg, prompt="p", deployment=None, instructions="be terse", options={"tools": []}
    )
    assert request == {
        "model": "my-chat-deployment",
        "input": "p",
        "store": False,
        "instructions": "be terse",
        "max_output_tokens": 64,
        "tools": [],
    }
    for reserved in ("model", "stream", "input"):
        refuses(
            ConfigError,
            lambda r=reserved: convenience_request(
                cfg, prompt="p", deployment=None, instructions=None, options={r: "x"}
            ),
            contains="set by the method itself",
        )
    # An explicit store=True is the caller's decision and is honoured.
    opted_in = convenience_request(
        cfg, prompt="p", deployment=None, instructions=None, options={"store": True}
    )
    assert opted_in["store"] is True


@check
def raw_requests_default_only_the_deployment() -> None:
    cfg = config(default_max_output_tokens=64)
    assert raw_request(cfg, {"input": "x"}) == {"input": "x", "model": "my-chat-deployment"}
    assert raw_request(cfg, {"model": "other"})["model"] == "other"
    refuses(ConfigError, lambda: raw_request(cfg, {"model": "  "}), contains="model is blank")
    # No convenience defaults leak into the raw door.
    assert "store" not in raw_request(cfg, {"input": "x"})
    assert "max_output_tokens" not in raw_request(cfg, {"input": "x"})


@check
def embedding_requests_validate_before_a_socket_opens() -> None:
    cfg = config(embedding_deployment="my-embedding-deployment")
    model = connect(cfg, client=FakeClient())
    refuses(ConfigError, lambda: model.embed(""), contains="is empty")
    refuses(ConfigError, lambda: model.embed([]), contains="nothing to embed")
    refuses(ConfigError, lambda: model.embed(["a", 2]), contains="input[1] must be a string")
    refuses(ConfigError, lambda: model.embed(b"bytes"), contains="must be a string")
    refuses(ConfigError, lambda: model.embed({"a": 1}), contains="must be a string")
    refuses(ConfigError, lambda: model.embed(5), contains="must be a string")
    refuses(
        ConfigError,
        lambda: model.embed(["x"] * (MAX_EMBEDDING_INPUTS + 1)),
        contains="at most 2048",
    )
    refuses(ConfigError, lambda: model.embed("x", dimensions=0), contains="positive int")
    refuses(ConfigError, lambda: model.embed("x", dimensions=1.5), contains="must be an int")
    refuses(ConfigError, lambda: model.embed("x", model="y"), contains="set by the method itself")
    refuses(ConfigError, lambda: model.embed("x", deployment=" "), contains="blank")
    assert embedding_raw_request(cfg, {})["model"] == "my-embedding-deployment"
    refuses(ConfigError, lambda: embedding_raw_request(cfg, {"model": ""}), contains="blank")
    refuses(
        ConfigError,
        lambda: embedding_raw_request(config(), {}),
        contains="no embedding deployment is configured",
    )


# ---------------------------------------------------------------- results


@check
def usage_survives_every_shape_the_provider_uses() -> None:
    class Dump:
        def model_dump(self):
            return {"input_tokens": 1, "output_tokens": 2}

    class Broken:
        def model_dump(self):
            raise RuntimeError("no")

    class Attrs:
        input_tokens = 3
        output_tokens = 4
        total_tokens = 7

    assert usage_dict(fake_text_response("x")) == {}
    assert usage_dict(fake_text_response("x", usage={"a": 1})) == {"a": 1}
    assert usage_dict(fake_text_response("x", usage=Dump()))["output_tokens"] == 2
    assert usage_dict(fake_text_response("x", usage=Broken())) == {}
    assert usage_dict(fake_text_response("x", usage=Attrs()))["total_tokens"] == 7


@check
def results_never_carry_content_into_a_log_line() -> None:
    private_text = "the patient's full name"
    text = TextResult.from_response(
        fake_text_response(private_text, usage={"output_tokens": 5}), deployment="d"
    )
    assert text.complete is True and text.output_tokens == 5
    assert private_text not in repr(text)
    assert private_text not in str(text.metadata())
    assert text.metadata()["text_chars"] == len(private_text)

    parsed = ParsedResult.from_response(
        fake_parsed_response(None, refusal=f"I will not repeat {private_text}"), deployment="d"
    )
    assert parsed.refused is True and parsed.parsed is None
    assert private_text not in repr(parsed)
    assert private_text not in str(parsed.metadata())

    ok = ParsedResult.from_response(fake_parsed_response({"a": 1}), deployment="d")
    assert ok.refused is False and ok.parsed == {"a": 1}


@check
def embedding_alignment_is_verified_not_assumed() -> None:
    aligned = EmbeddingResult.from_response(
        fake_embedding_response([[3.0], [1.0], [2.0]], indexes=[2, 0, 1]),
        deployment="d",
        expected_count=3,
    )
    assert aligned.vectors == ((1.0,), (2.0,), (3.0,))
    assert aligned.count == 3 and aligned.dimensions == 1
    refuses(ConfigError, lambda: aligned.vector, contains="3 vectors")

    def broken(response, expected=2):
        return lambda: EmbeddingResult.from_response(
            response, deployment="d", expected_count=expected
        )

    refuses(ModelError, broken(fake_embedding_response([[1.0]]), 2), contains="1 vectors for 2")
    refuses(
        ModelError,
        broken(fake_embedding_response([[1.0], [2.0]], indexes=[0, 0])),
        contains="appears twice",
    )
    refuses(
        ModelError,
        broken(fake_embedding_response([[1.0], [2.0]], indexes=[0, 5])),
        contains="outside 0..1",
    )
    refuses(
        ModelError,
        broken(fake_embedding_response([[1.0], [2.0]], indexes=[0, True])),
        contains="no integer index",
    )
    refuses(
        ModelError,
        broken(fake_embedding_response([[1.0], [2.0, 3.0]])),
        contains="vector lengths differ",
    )
    refuses(
        ModelError,
        broken(fake_embedding_response([[1.0], [float("nan")]])),
        contains="non-finite",
    )
    refuses(ModelError, broken(fake_embedding_response([[1.0], []])), contains="is empty")

    class NoData:
        data = "not-a-list"
        model = "m"
        usage = None

    refuses(ModelError, broken(NoData(), 1), contains="no list of vectors")

    class Base64:
        data = [type("I", (), {"index": 0, "embedding": "AAECAw=="})()]
        model = "m"
        usage = None

    refuses(ConfigError, broken(Base64(), 1), contains="base64")


# ----------------------------------------------------------- sync client


@check
def sync_client_covers_ask_respond_parse_and_embed() -> None:
    transport = FakeClient(
        responses=[
            fake_text_response("answer", response_id="r1", usage={"output_tokens": 2}),
            fake_text_response("second"),
            fake_text_response("raw"),
            fake_parsed_response({"level": "high"}),
        ],
        embeddings=[fake_embedding_response([[0.5, 0.25]])],
    )
    cfg = config(embedding_deployment="my-embedding-deployment")
    with connect(cfg, client=transport) as model:
        assert model.ask("q").text == "answer"
        assert model.ask("q2", deployment="override").deployment == "override"
        assert transport.requests[1]["model"] == "override"
        assert getattr(model.respond(input="x"), "output_text") == "raw"
        assert model.parse("q", text_format=dict).parsed == {"level": "high"}
        assert model.embed("hello").vector == (0.5, 0.25)
        assert model.client is transport
        assert model.token_provider is None
    # An injected client belongs to whoever injected it. See CONTRACT.md,
    # invariant 8, and tests/test_regressions.py for the shared-client case.
    assert transport.closed is False
    connect(cfg, client=transport, owns_client=True).close()
    assert transport.closed is True


@check
def sync_streams_yield_deltas_raise_in_band_failures_and_always_close() -> None:
    cfg = config()
    transport = FakeClient(
        streams=[
            [text_delta_event("a"), None, text_delta_event("b")],
            [text_delta_event("a"), stream_error_event("content_filter")],
            [text_delta_event("a"), stream_failed_event("server_error")],
            [text_delta_event("a"), RuntimeError("socket died")],
            [text_delta_event("x"), text_delta_event("y")],
            [text_delta_event("e1"), stream_error_event("ignored-here")],
        ]
    )
    model = connect(cfg, client=transport)

    assert list(model.stream_text("q")) == ["a", "b"]
    assert transport.streams_opened[0].closed is True

    failed = refuses(ModelError, lambda: list(model.stream_text("q")))
    assert failed.category == "stream" and failed.code == "content_filter"
    assert transport.streams_opened[1].closed is True

    failed = refuses(ModelError, lambda: list(model.stream_text("q")))
    assert failed.category == "stream" and failed.code == "server_error"
    assert transport.streams_opened[2].closed is True

    # A transport failure mid-stream is classified, not leaked raw.
    broken = refuses(ModelError, lambda: list(model.stream_text("q")))
    assert broken.category == "unknown" and isinstance(broken.__cause__, RuntimeError)
    assert transport.streams_opened[3].closed is True

    # Abandoning the iterator still closes the stream.
    partial = model.stream_text("q")
    assert next(partial) == "x"
    partial.close()
    assert transport.streams_opened[4].closed is True

    # stream_events is the raw feed: error events are yielded, not raised.
    events = list(model.stream_events(input="q"))
    assert [getattr(e, "type", None) for e in events] == [
        "response.output_text.delta",
        "error",
    ]
    assert transport.streams_opened[5].closed is True
    # `stream` is set by the method, never taken from the caller.
    assert transport.requests[-1]["stream"] is True
    model.close()


@check
def a_closed_sync_client_refuses_every_door() -> None:
    model = connect(config(embedding_deployment="e"), client=FakeClient())
    model.close()
    model.close()  # idempotent
    for call in (
        lambda: model.ask("q"),
        lambda: model.respond(input="q"),
        lambda: model.parse("q", text_format=dict),
        lambda: model.embed("q"),
        lambda: model.embed_raw(input="q"),
        lambda: model.stream_text("q"),
        lambda: model.stream_events(input="q"),
        lambda: model.client,
        lambda: model.__enter__(),
    ):
        refuses(ModelError, call, contains="client is closed")


@check
def credential_ownership_follows_who_built_it() -> None:
    class Credential:
        def __init__(self) -> None:
            self.closes = 0

        def close(self) -> None:
            self.closes += 1

    theirs = Credential()
    ModelClient(config(), client=FakeClient(), credential=theirs).close()
    assert theirs.closes == 0

    ours = Credential()
    ModelClient(config(), client=FakeClient(), credential=ours, owns_credential=True).close()
    assert ours.closes == 1

    # connect() never claims ownership of what it was handed.
    theirs2 = Credential()
    connect(config(), client=FakeClient(), credential=theirs2).close()
    assert theirs2.closes == 0

    class Angry:
        def close(self):
            raise RuntimeError("teardown failed")

    # Shutdown must not raise: a failing close is logged, not propagated.
    ModelClient(config(), client=Angry(), credential=None).close()


@check
def the_token_provider_is_stored_as_a_callable_never_a_token() -> None:
    calls: list[int] = []

    def provider() -> str:
        calls.append(1)
        return f"token-{len(calls)}"

    model = ModelClient(config(), client=FakeClient(), token_provider=provider)
    # Building the client must not call it: a token acquired here would be
    # frozen for the client's whole life.
    assert calls == []
    assert model.token_provider is provider
    assert model.token_provider() == "token-1"
    model.close()


# ---------------------------------------------------------- async client


@check
def async_client_mirrors_the_sync_contract() -> None:
    async def scenario() -> None:
        transport = FakeAsyncClient(
            responses=[
                fake_text_response("async answer"),
                fake_text_response("raw"),
                fake_parsed_response(None, refusal="no"),
            ],
            embeddings=[fake_embedding_response([[1.0], [2.0]])],
            streams=[
                [text_delta_event("a"), text_delta_event("b")],
                [text_delta_event("a"), stream_error_event("content_filter")],
                [text_delta_event("q"), text_delta_event("r")],
            ],
        )
        cfg = config(embedding_deployment="my-embedding-deployment")
        async with connect_async(cfg, client=transport) as model:
            assert (await model.ask("q")).text == "async answer"
            assert getattr(await model.respond(input="x"), "output_text") == "raw"
            assert (await model.parse("q", text_format=dict)).refused is True
            assert (await model.embed(["a", "b"])).count == 2

            assert [c async for c in model.stream_text("q")] == ["a", "b"]
            assert transport.streams_opened[0].closed is True

            partial: list[str] = []
            try:
                async for chunk in model.stream_text("q"):
                    partial.append(chunk)
            except ModelError as failed:
                assert failed.category == "stream"
            assert partial == ["a"]
            # The inner generator is closed at once, not at collection time.
            assert transport.streams_opened[1].closed is True

            events = model.stream_events(input="q")
            assert (await events.__anext__()).delta == "q"
            await events.aclose()
            assert transport.streams_opened[2].closed is True

        assert transport.closed is False
        adopted = connect_async(cfg, client=transport, owns_client=True)
        await adopted.aclose()
        assert transport.closed is True

        closed = connect_async(config(), client=FakeAsyncClient())
        await closed.aclose()
        await closed.aclose()
        # A coroutine method refuses when awaited, so the await is the test.
        try:
            await closed.respond(input="x")
        except ModelError as refused:
            assert "client is closed" in str(refused)
        else:
            raise AssertionError("a closed async client must refuse")
        # The streaming doors are plain methods, so they refuse at the call.
        for door in (lambda: closed.stream_text("q"), lambda: closed.stream_events(input="q")):
            try:
                door()
            except ModelError as refused:
                assert "client is closed" in str(refused)
            else:
                raise AssertionError("a closed async client must refuse eagerly")

    asyncio.run(scenario())


@check
def async_credential_ownership_and_awaitable_close() -> None:
    async def scenario() -> None:
        class AsyncCredential:
            def __init__(self) -> None:
                self.closes = 0

            async def close(self) -> None:
                self.closes += 1

        theirs = AsyncCredential()
        client = AsyncModelClient(config(), client=FakeAsyncClient(), credential=theirs)
        await client.aclose()
        assert theirs.closes == 0

        ours = AsyncCredential()
        client = AsyncModelClient(
            config(), client=FakeAsyncClient(), credential=ours, owns_credential=True
        )
        await client.aclose()
        assert ours.closes == 1

    asyncio.run(scenario())


# ----------------------------------------------------------------- errors


@check
def classification_is_stable_and_content_free() -> None:
    private_text = "prompt text that must not travel"

    class Named(Exception):
        pass

    Named.__name__ = "ClientAuthenticationError"
    auth = classify(Named(private_text), deployment="d")
    assert auth.category == "auth" and auth.retryable is False
    assert private_text not in str(auth)

    timed_out = classify(TimeoutError(private_text), deployment="d")
    assert timed_out.category == "timeout" and timed_out.retryable is True

    unknown = classify(ValueError(private_text), deployment="d")
    assert unknown.category == "unknown" and unknown.retryable is False
    assert "ValueError" in unknown.message and private_text not in str(unknown)

    # An already-classified error passes through unchanged.
    existing = ModelError("already", category="rate_limit")
    assert classify(existing) is existing

    in_stream = stream_error(code="content_filter", deployment="d", failed=True)
    assert in_stream.category == "stream" and in_stream.retryable is False
    assert "failed" in in_stream.message
    assert repr(in_stream).startswith("ModelError(")
    assert "deployment=d" in str(in_stream)


@check
def config_error_is_a_model_error_so_one_except_clause_is_enough() -> None:
    error = refuses(ModelError, lambda: config(max_retries=99))
    assert isinstance(error, ConfigError)
    assert error.category == "config" and error.retryable is False


# --------------------------------------------- the SDK's own contract


@check
def the_sdk_reinvokes_the_token_callable_on_every_request() -> None:
    """The identity claim, against the real SDK over an in-process transport."""
    try:
        import httpx
        from openai import OpenAI
    except ImportError:
        SKIPPED.append("SDK protocol: openai/httpx not installed")
        return

    seen: list[httpx.Request] = []
    issued: list[str] = []

    def provider() -> str:
        issued.append(f"token-{len(issued)}")
        return issued[-1]

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.endswith("/embeddings"):
            return httpx.Response(
                200,
                json={
                    "object": "list",
                    "model": "my-embedding-deployment",
                    "data": [{"object": "embedding", "index": 0, "embedding": [0.1, 0.2]}],
                    "usage": {"prompt_tokens": 2, "total_tokens": 2},
                },
            )
        if len(seen) == 3:
            return httpx.Response(
                404,
                json={"error": {"code": "DeploymentNotFound", "message": "no such deployment"}},
                headers={"x-request-id": "req-42"},
            )
        return httpx.Response(
            200,
            json={
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
                        "content": [
                            {"type": "output_text", "text": "pong", "annotations": []}
                        ],
                    }
                ],
                "parallel_tool_calls": False,
                "tool_choice": "auto",
                "tools": [],
            },
        )

    cfg = config(embedding_deployment="my-embedding-deployment", timeout_secs=5, max_retries=0)
    sdk = OpenAI(
        base_url=cfg.base_url,
        api_key=provider,
        timeout=cfg.timeout_secs,
        max_retries=cfg.max_retries,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    with connect(cfg, client=sdk) as model:
        assert model.ask("ping").text == "pong"
        assert model.ask("ping").text == "pong"
        assert str(seen[0].url).endswith("/openai/v1/responses")
        assert issued == ["token-0", "token-1"]
        assert seen[0].headers["authorization"] == "Bearer token-0"
        assert seen[1].headers["authorization"] == "Bearer token-1"

        not_found = refuses(ModelError, lambda: model.ask("ping"))
        assert not_found.category == "not_found"
        assert not_found.status_code == 404
        assert not_found.retryable is False
        assert not_found.request_id == "req-42"
        assert not_found.code == "DeploymentNotFound"

        vector = model.embed("hello").vector
        assert vector == (0.1, 0.2)
        assert str(seen[-1].url).endswith("/openai/v1/embeddings")

    # The client this package builds is wired from the config, not from the
    # SDK's defaults: a ten-minute default timeout wedges a worker.
    built = ModelClient._build_client(cfg, provider)
    assert str(built.base_url) == cfg.base_url
    assert built.max_retries == 0
    assert built.timeout == 5.0
    built.close()


# ------------------------------------------------------------ regressions


@check
def interrupts_and_cancellation_are_never_reclassified() -> None:
    """Ctrl-C, SystemExit and generator teardown are not provider failures."""
    for interrupt in (KeyboardInterrupt, SystemExit, GeneratorExit):
        model = connect(config(), client=FakeClient(responses=[interrupt()]))
        try:
            model.ask("q")
        except interrupt:
            pass
        except ModelError as wrong:  # pragma: no cover - the defect this covers
            raise AssertionError(f"{interrupt.__name__} became {wrong!r}")
        else:
            raise AssertionError(f"{interrupt.__name__} was swallowed")
        model.close()

    async def scenario() -> None:
        class Slow:
            def __init__(self) -> None:
                self.entered = asyncio.Event()

            async def create(self, **kwargs) -> None:
                self.entered.set()
                await asyncio.Event().wait()

        slow = Slow()
        transport = FakeAsyncClient()
        transport.responses.create = slow.create
        model = connect_async(config(), client=transport)
        task = asyncio.ensure_future(model.ask("q"))
        await asyncio.wait_for(slow.entered.wait(), timeout=5)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        else:
            raise AssertionError("a cancelled call must stay cancelled")
        assert task.cancelled() is True
        await model.aclose()

    asyncio.run(scenario())


@check
def an_already_classified_error_is_not_its_own_cause() -> None:
    original = ModelError("already classified", category="stream")
    model = connect(config(), client=FakeClient(responses=[original]))
    raised = refuses(ModelError, lambda: model.ask("q"))
    assert raised is original
    assert raised.__cause__ is not raised
    model.close()


@check
def an_injected_client_is_left_to_its_owner() -> None:
    shared = FakeClient(responses=[fake_text_response("a")])
    first = connect(config(), client=shared)
    second = connect(config(), client=shared)
    first.close()
    assert shared.closed is False
    assert second.ask("q").text == "a"
    second.close()
    assert shared.closed is False
    connect(config(), client=shared, owns_client=True).close()
    assert shared.closed is True


@check
def the_cross_account_embedding_guard_survives_an_explicit_deployment() -> None:
    cfg = config(
        embedding_deployment="my-embedding-deployment", embedding_endpoint=OTHER_ENDPOINT
    )
    transport = FakeClient(embeddings=[fake_embedding_response([[0.1]])])
    model = connect(cfg, client=transport)
    refuses(
        ConfigError,
        lambda: model.embed("hello", deployment="my-embedding-deployment"),
        contains="not on this client's account",
    )
    refuses(ConfigError, lambda: model.embed_raw(input="hello"))
    refuses(ConfigError, lambda: model.embed_raw(input="hello", model="anything"))
    assert transport.requests == []
    # The escape hatch is explicit, documented, and never sent to the provider.
    model.embed_raw(input="hello", allow_foreign_account=True)
    assert "allow_foreign_account" not in transport.requests[0]
    model.close()

    local = connect(
        config(embedding_deployment="e", embedding_endpoint=ENDPOINT),
        client=FakeClient(embeddings=[fake_embedding_response([[0.1]])]),
    )
    assert local.embed("hello", deployment="other-embedding").vector == (0.1,)
    local.close()


@check
def a_contradictory_stream_option_is_refused_not_dropped() -> None:
    model = connect(config(), client=FakeClient(streams=[[], []]))
    refuses(ConfigError, lambda: model.stream_events(input="q", stream=False), contains="stream")
    assert list(model.stream_events(input="q", stream=True)) == []
    model.close()


@check
def an_endpoint_allowlist_is_available_for_untrusted_configuration() -> None:
    allowed = ("example-account.openai.azure.com",)
    refuses(
        ConfigError,
        lambda: ModelConfig(
            endpoint="https://attacker.example.com/",
            deployment="my-chat-deployment",
            allowed_hosts=allowed,
        ),
        contains="allowed_hosts",
    )
    pinned = config(allowed_hosts=allowed)
    assert pinned.account_host == allowed[0]
    refuses(
        ConfigError,
        lambda: pinned.with_overrides(
            embedding_deployment="e", embedding_endpoint=OTHER_ENDPOINT
        ),
        contains="allowed_hosts",
    )
    # None keeps the default: any https host, which is the operator-input case.
    assert config().allowed_hosts is None


def main() -> int:
    failures = 0
    for fn in CHECKS:
        try:
            fn()
        except BaseException:
            failures += 1
            print(f"FAIL  {fn.__name__}")
            traceback.print_exc()
        else:
            print(f"ok    {fn.__name__}")
    for note in SKIPPED:
        print(f"skip  {note}")
    print(f"\n{len(CHECKS) - failures}/{len(CHECKS)} checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
