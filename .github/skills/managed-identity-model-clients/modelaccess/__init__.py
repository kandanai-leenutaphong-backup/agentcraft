"""modelaccess — Entra-authenticated model access with a failure model in place.

No API keys: the token provider is re-invoked by the SDK on every request, so
refresh belongs to the credential and no token is ever frozen into a client.

    from modelaccess import ModelConfig, connect

    config = ModelConfig(endpoint="https://example-account.openai.azure.com/",
                         deployment="my-chat-deployment")
    with connect(config) as model:
        print(model.ask("Name three uses for a paperclip.").text)

Public surface
--------------
- :func:`connect`, :func:`connect_async` — build a reusable client.
- :func:`token_provider_for`, :func:`async_token_provider_for` — the same
  identity handling for a caller who builds their own SDK client.
- :class:`ModelConfig` — frozen, validated coordinates; ``from_env()``.
- :func:`embedding_config` — a config pointed at the account that owns the
  embedding deployment; :func:`normalize_endpoint` for the URL rule alone.
- :class:`ModelClient`, :class:`AsyncModelClient` — ``respond``, ``ask``,
  ``parse``, ``embed``, ``embed_raw``, ``stream_text``, ``stream_events``,
  ``close``/``aclose``.
- :class:`TextResult`, :class:`ParsedResult`, :class:`EmbeddingResult` —
  results plus safe metadata.
- :class:`ModelError`, :class:`ConfigError`, :data:`ErrorCategory` — the only
  failures that escape.
- :class:`FakeClient`, :class:`FakeAsyncClient` and the ``fake_*``/``*_event``
  builders — offline doubles for tests and examples.
"""

from modelaccess.aio import AsyncModelClient
from modelaccess.client import ModelClient
from modelaccess.config import (
    DEFAULT_MAX_RETRIES,
    DEFAULT_SCOPE,
    DEFAULT_TIMEOUT_SECS,
    ENV_PREFIX,
    ModelConfig,
    embedding_config,
    normalize_endpoint,
)
from modelaccess.connect import (
    async_token_provider_for,
    connect,
    connect_async,
    token_provider_for,
)
from modelaccess.doubles import (
    FakeAsyncClient,
    FakeClient,
    fake_embedding_response,
    fake_parsed_response,
    fake_text_response,
    stream_error_event,
    stream_failed_event,
    text_delta_event,
)
from modelaccess.errors import ConfigError, ErrorCategory, ModelError
from modelaccess.invoke import MAX_EMBEDDING_INPUTS
from modelaccess.results import EmbeddingResult, ParsedResult, TextResult

__version__ = "1.0.0"

__all__ = [
    "AsyncModelClient",
    "ConfigError",
    "DEFAULT_MAX_RETRIES",
    "DEFAULT_SCOPE",
    "DEFAULT_TIMEOUT_SECS",
    "ENV_PREFIX",
    "EmbeddingResult",
    "ErrorCategory",
    "FakeAsyncClient",
    "FakeClient",
    "MAX_EMBEDDING_INPUTS",
    "ModelClient",
    "ModelConfig",
    "ModelError",
    "ParsedResult",
    "TextResult",
    "__version__",
    "async_token_provider_for",
    "connect",
    "connect_async",
    "embedding_config",
    "fake_embedding_response",
    "fake_parsed_response",
    "fake_text_response",
    "normalize_endpoint",
    "stream_error_event",
    "stream_failed_event",
    "text_delta_event",
    "token_provider_for",
]
