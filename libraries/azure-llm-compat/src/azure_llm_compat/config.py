"""Which model endpoint to call, and how hard to try.

Every value resolves when :meth:`LlmConfig.from_env` is called, never at import
time. A configuration frozen at import cannot be switched by a caller and cannot
be tested without reloading the module.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlparse

#: Entra ID audience for Azure OpenAI and other Cognitive Services model endpoints.
COGNITIVE_SCOPE = "https://cognitiveservices.azure.com/.default"

DEFAULT_ENV_PREFIX = "AZURE_LLM_"


class LlmConfigError(RuntimeError):
    """Configuration is missing or malformed."""


@dataclass(frozen=True, slots=True)
class LlmConfig:
    """Everything needed to reach one Azure model endpoint.

    Attributes:
        endpoint: OpenAI-compatible base URL, e.g.
            ``https://<account>.cognitiveservices.azure.com/openai/v1/``.
        model: Default deployment name for chat and responses calls.
        embedding_deployment: Default deployment name for embeddings calls.
        embedding_endpoint: Base URL for embeddings when it differs from ``endpoint``.
        scope: Token audience. Only change this for a non-public cloud.
        timeout_seconds: Per-request deadline.
        max_retries: Attempts the SDK makes for a retryable fault.
    """

    endpoint: str
    model: str = ""
    embedding_deployment: str = ""
    embedding_endpoint: str = ""
    scope: str = COGNITIVE_SCOPE
    timeout_seconds: float = 120.0
    max_retries: int = 2

    def __post_init__(self) -> None:
        _require_https(self.endpoint, "endpoint")
        if self.embedding_endpoint:
            _require_https(self.embedding_endpoint, "embedding_endpoint")
        if self.timeout_seconds <= 0:
            raise LlmConfigError("timeout_seconds must be positive")
        if self.max_retries < 0:
            raise LlmConfigError("max_retries must not be negative")

    @property
    def embeddings_base_url(self) -> str:
        """Base URL embeddings are sent to, falling back to the main endpoint."""
        return self.embedding_endpoint or self.endpoint

    @classmethod
    def from_env(cls, prefix: str = DEFAULT_ENV_PREFIX, **overrides: object) -> "LlmConfig":
        """Build from ``<prefix>*`` environment variables, read now, with overrides.

        Recognised keys: ``ENDPOINT`` (required), ``MODEL``,
        ``EMBEDDING_DEPLOYMENT``, ``EMBEDDING_ENDPOINT``, ``SCOPE``,
        ``TIMEOUT_SECONDS``, ``MAX_RETRIES``.
        """
        def env(name: str) -> str | None:
            return os.environ.get(prefix + name)

        endpoint = overrides.pop("endpoint", None) or env("ENDPOINT")
        if not endpoint:
            raise LlmConfigError(f"{prefix}ENDPOINT is required when endpoint is not passed explicitly")

        values: dict[str, object] = {"endpoint": str(endpoint)}
        for key, caster in (
            ("MODEL", str),
            ("EMBEDDING_DEPLOYMENT", str),
            ("EMBEDDING_ENDPOINT", str),
            ("SCOPE", str),
            ("TIMEOUT_SECONDS", float),
            ("MAX_RETRIES", int),
        ):
            raw = env(key)
            if raw is not None and raw != "":
                values[key.lower()] = caster(raw)
        values.update(overrides)
        try:
            return cls(**values)  # type: ignore[arg-type]
        except TypeError as exc:
            raise LlmConfigError(str(exc)) from exc


def _require_https(value: str, field: str) -> None:
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc:
        raise LlmConfigError(f"{field} must be an https URL, got {value!r}")
