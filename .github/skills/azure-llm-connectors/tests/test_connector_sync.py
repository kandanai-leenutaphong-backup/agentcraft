"""The sync call surface: ask, respond, parse, and the options that reach the API."""

from __future__ import annotations

import pytest

from azllm import ConfigError, FoundryConfig, connect
from fakes import FakeClient, FakeResponse


def test_ask_returns_text_and_metadata(connector, fake_client: FakeClient) -> None:
    result = connector.ask("hello")
    assert result.text == "hello"
    assert result.response_id == "resp_fake_1"
    assert result.deployment == "chat"
    assert result.model == "chat"
    assert result.status == "completed"
    assert result.usage == {"input_tokens": 7, "output_tokens": 3, "total_tokens": 10}
    assert result.raw is fake_client.responses.response
    assert result.complete is True
    assert result.input_tokens == 7 and result.output_tokens == 3


def test_ask_sends_the_prompt_as_input_with_the_default_deployment(
    connector, fake_client: FakeClient
) -> None:
    connector.ask("hello")
    call = fake_client.responses.calls[0]
    assert call["model"] == "chat"
    assert call["input"] == "hello"


def test_ask_defaults_store_to_false(connector, fake_client: FakeClient) -> None:
    connector.ask("hello")
    assert fake_client.responses.calls[0]["store"] is False


def test_store_can_be_turned_on_explicitly(connector, fake_client: FakeClient) -> None:
    connector.ask("hello", store=True)
    assert fake_client.responses.calls[0]["store"] is True


def test_per_call_deployment_override(connector, fake_client: FakeClient) -> None:
    result = connector.ask("hello", deployment="chat-batch")
    assert fake_client.responses.calls[0]["model"] == "chat-batch"
    assert result.deployment == "chat-batch"
    assert connector.config.deployment == "chat"


def test_blank_deployment_override_is_rejected(connector) -> None:
    with pytest.raises(ConfigError):
        connector.ask("hello", deployment="   ")


def test_instructions_are_forwarded_only_when_given(connector, fake_client: FakeClient) -> None:
    connector.ask("hello")
    assert "instructions" not in fake_client.responses.calls[0]
    connector.ask("hello", instructions="be terse")
    assert fake_client.responses.calls[1]["instructions"] == "be terse"


def test_arbitrary_responses_options_pass_through(connector, fake_client: FakeClient) -> None:
    tools = [{"type": "web_search"}]
    connector.ask(
        "hello",
        tools=tools,
        previous_response_id="resp_prev",
        reasoning={"effort": "low"},
        include=["reasoning.encrypted_content"],
        metadata={"trace": "abc"},
        temperature=0.2,
    )
    call = fake_client.responses.calls[0]
    assert call["tools"] == tools
    assert call["previous_response_id"] == "resp_prev"
    assert call["reasoning"] == {"effort": "low"}
    assert call["include"] == ["reasoning.encrypted_content"]
    assert call["metadata"] == {"trace": "abc"}
    assert call["temperature"] == 0.2


@pytest.mark.parametrize("option", ["model", "stream", "input"])
def test_options_owned_by_the_method_are_refused(connector, option: str) -> None:
    with pytest.raises(ConfigError) as caught:
        connector.ask("hello", **{option: "x"})
    assert option in str(caught.value)


def test_default_max_output_tokens_is_applied_and_overridable(fake_client: FakeClient) -> None:
    cfg = FoundryConfig(endpoint="https://acct.openai.azure.com/", default_max_output_tokens=64)
    with connect(cfg, client=fake_client) as conn:
        conn.ask("hello")
        assert fake_client.responses.calls[0]["max_output_tokens"] == 64
        conn.ask("hello", max_output_tokens=8)
        assert fake_client.responses.calls[1]["max_output_tokens"] == 8


def test_respond_passes_everything_through_untouched(connector, fake_client: FakeClient) -> None:
    response = connector.respond(
        model="chat-alternate",
        input=[{"role": "user", "content": "hi"}],
        background=True,
        store=True,
    )
    call = fake_client.responses.calls[0]
    assert call == {
        "model": "chat-alternate",
        "input": [{"role": "user", "content": "hi"}],
        "background": True,
        "store": True,
    }
    assert response is fake_client.responses.response


def test_respond_defaults_the_deployment_but_nothing_else(
    connector, fake_client: FakeClient
) -> None:
    connector.respond(input="hi")
    call = fake_client.responses.calls[0]
    assert call["model"] == "chat"
    assert "store" not in call
    assert "max_output_tokens" not in call


def test_respond_rejects_a_blank_model(connector) -> None:
    with pytest.raises(ConfigError):
        connector.respond(model="  ", input="hi")


def test_parse_returns_the_validated_object(connector, fake_client: FakeClient) -> None:
    from pydantic import BaseModel

    class Answer(BaseModel):
        ok: bool

    result = connector.parse("hello", text_format=Answer)
    assert result.parsed == {"ok": True}
    assert result.status == "completed"
    assert fake_client.responses.parse_calls[0]["text_format"] is Answer
    assert fake_client.responses.parse_calls[0]["store"] is False


def test_parse_reports_a_refusal_as_no_parsed_object(connector, fake_client: FakeClient) -> None:
    from pydantic import BaseModel

    class Answer(BaseModel):
        ok: bool

    fake_client.responses.parsed_response = FakeResponse(
        output_parsed=None, output_text="", status="incomplete"
    )
    result = connector.parse("hello", text_format=Answer)
    assert result.parsed is None
    assert result.complete is False


def test_result_repr_and_metadata_never_contain_the_text(connector) -> None:
    result = connector.ask("hello")
    assert result.text == "hello"
    assert "hello" not in repr(result)
    assert "hello" not in str(result.metadata())
    assert result.metadata()["text_chars"] == 5
