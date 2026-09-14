"""Error translation: correct category, and nothing the model produced."""

from __future__ import annotations

import openai
import pytest

from azllm import ConfigError, LlmError
from azllm.errors import classify
from fakes import LEAKY_BODY, LEAKY_MESSAGE, connection_error, status_error, timeout_error


@pytest.mark.parametrize(
    "error_cls, status, category, retryable",
    [
        (openai.AuthenticationError, 401, "auth", False),
        (openai.PermissionDeniedError, 403, "auth", False),
        (openai.NotFoundError, 404, "not_found", False),
        (openai.BadRequestError, 400, "bad_request", False),
        (openai.UnprocessableEntityError, 422, "bad_request", False),
        (openai.RateLimitError, 429, "rate_limit", True),
        (openai.InternalServerError, 503, "server", True),
    ],
)
def test_status_errors_are_classified(
    error_cls: type, status: int, category: str, retryable: bool
) -> None:
    err = classify(status_error(error_cls, status), deployment="chat")
    assert err.category == category
    assert err.status_code == status
    assert err.retryable is retryable
    assert err.request_id == "req_abc123"
    assert err.deployment == "chat"


def test_transport_errors_are_classified() -> None:
    assert classify(timeout_error()).category == "timeout"
    assert classify(timeout_error()).retryable is True
    assert classify(connection_error()).category == "connection"
    assert classify(connection_error()).retryable is True


def test_credential_failures_are_auth_failures() -> None:
    class ClientAuthenticationError(Exception):
        pass

    err = classify(ClientAuthenticationError("no token for you"))
    assert err.category == "auth"
    assert err.retryable is False


def test_unknown_exceptions_are_not_retryable() -> None:
    err = classify(ValueError("something odd"))
    assert err.category == "unknown"
    assert err.retryable is False
    assert "ValueError" in err.message


def test_an_llm_error_passes_through_unchanged() -> None:
    original = LlmError("nope", category="config")
    assert classify(original) is original


@pytest.mark.parametrize(
    "error_cls, status",
    [(openai.BadRequestError, 400), (openai.RateLimitError, 429), (openai.NotFoundError, 404)],
)
def test_no_provider_message_or_body_survives_translation(error_cls: type, status: int) -> None:
    err = classify(status_error(error_cls, status))
    rendered = f"{err} {err!r} {err.message}"
    assert LEAKY_MESSAGE not in rendered
    assert "patient" not in rendered
    assert str(LEAKY_BODY) not in rendered


def test_the_short_error_code_is_kept_because_it_is_an_identifier() -> None:
    err = classify(status_error(openai.BadRequestError, 400))
    assert err.code == "content_filter"


def test_the_original_exception_is_preserved_as_the_cause(connector, fake_client) -> None:
    fake_client.responses.raises = status_error(openai.NotFoundError, 404)
    with pytest.raises(LlmError) as caught:
        connector.ask("hi")
    assert isinstance(caught.value.__cause__, openai.NotFoundError)
    assert caught.value.category == "not_found"


def test_not_found_explains_the_deployment_name_trap(connector, fake_client) -> None:
    fake_client.responses.raises = status_error(openai.NotFoundError, 404)
    with pytest.raises(LlmError) as caught:
        connector.ask("hi", deployment="gpt-5.6")
    assert "deployment name" in str(caught.value)
    assert caught.value.deployment == "gpt-5.6"


def test_auth_failure_names_the_role_needed(connector, fake_client) -> None:
    fake_client.responses.raises = status_error(openai.AuthenticationError, 401)
    with pytest.raises(LlmError) as caught:
        connector.ask("hi")
    assert "Cognitive Services OpenAI User" in str(caught.value)


def test_config_error_is_an_llm_error_and_never_retryable() -> None:
    err = ConfigError("bad")
    assert isinstance(err, LlmError)
    assert err.category == "config"
    assert err.retryable is False


def test_str_renders_the_triage_fields() -> None:
    err = classify(status_error(openai.RateLimitError, 429), deployment="chat-batch")
    rendered = str(err)
    for fragment in ("category=rate_limit", "status=429", "retryable=True", "deployment=chat-batch", "request_id=req_abc123"):
        assert fragment in rendered
