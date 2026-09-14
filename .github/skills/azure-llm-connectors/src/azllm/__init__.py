"""azllm — Azure AI Foundry / Azure OpenAI access with identity already in place.

Entra-only, no API keys: the target account has local auth disabled.

    from azllm import connect

    with connect() as llm:
        print(llm.ask("Name three uses for a paperclip.").text)

Public surface
--------------
- :func:`connect`, :func:`connect_async` — build a reusable connector.
- :class:`FoundryConfig` — frozen, validated coordinates; ``from_env()``.
- :func:`embedding_config` — a config already pointed at the account that
  owns a given embedding deployment.
- :class:`FoundryConnector`, :class:`AsyncFoundryConnector` — ``respond``,
  ``ask``, ``parse``, ``embed``, ``embed_raw``, ``stream_text``,
  ``stream_events``, ``close``/``aclose``.
- :class:`LlmResult`, :class:`ParsedResult`, :class:`EmbeddingResult` —
  results plus safe metadata.
- :class:`LlmError`, :class:`ConfigError` — the only failures that escape.
- :data:`KNOWN_DEPLOYMENTS`, :data:`DEFAULT_DEPLOYMENT`,
  :data:`EMBEDDING_DEPLOYMENTS` — the verified inventory, as documentation
  and never as a restriction.
"""

from azllm.aio import AsyncFoundryConnector
from azllm.config import (
    DEFAULT_MAX_RETRIES,
    DEFAULT_TIMEOUT_SECS,
    ENV_PREFIX,
    FoundryConfig,
    normalize_endpoint,
)
from azllm.connect import (
    async_token_provider_for,
    connect,
    connect_async,
    token_provider_for,
)
from azllm.connector import FoundryConnector
from azllm.deployments import (
    ACCOUNT_NAME,
    DEFAULT_DEPLOYMENT,
    DEFAULT_EMBEDDING_DEPLOYMENT,
    DEFAULT_ENDPOINT,
    DEFAULT_SCOPE,
    EMBEDDING_DEPLOYMENT,
    EMBEDDING_DEPLOYMENTS,
    HIGHEST_CAPACITY_DEPLOYMENT,
    KNOWN_DEPLOYMENTS,
    MAX_EMBEDDING_INPUTS,
    MAX_TOKENS_PER_INPUT,
    MAX_TOKENS_PER_REQUEST,
    SECONDARY_ACCOUNT_NAME,
    SECONDARY_ENDPOINT,
    DeploymentProfile,
    embedding_deployment,
    known_deployment,
)
from azllm.embeddings import embedding_config
from azllm.errors import ConfigError, ErrorCategory, LlmError
from azllm.result import EmbeddingResult, LlmResult, ParsedResult

__version__ = "1.1.0"

__all__ = [
    "ACCOUNT_NAME",
    "AsyncFoundryConnector",
    "ConfigError",
    "DEFAULT_DEPLOYMENT",
    "DEFAULT_EMBEDDING_DEPLOYMENT",
    "DEFAULT_ENDPOINT",
    "DEFAULT_MAX_RETRIES",
    "DEFAULT_SCOPE",
    "DEFAULT_TIMEOUT_SECS",
    "DeploymentProfile",
    "EMBEDDING_DEPLOYMENT",
    "EMBEDDING_DEPLOYMENTS",
    "ENV_PREFIX",
    "EmbeddingResult",
    "ErrorCategory",
    "FoundryConfig",
    "FoundryConnector",
    "HIGHEST_CAPACITY_DEPLOYMENT",
    "KNOWN_DEPLOYMENTS",
    "LlmError",
    "LlmResult",
    "MAX_EMBEDDING_INPUTS",
    "MAX_TOKENS_PER_INPUT",
    "MAX_TOKENS_PER_REQUEST",
    "ParsedResult",
    "SECONDARY_ACCOUNT_NAME",
    "SECONDARY_ENDPOINT",
    "__version__",
    "async_token_provider_for",
    "connect",
    "connect_async",
    "embedding_config",
    "embedding_deployment",
    "known_deployment",
    "normalize_endpoint",
    "token_provider_for",
]
