"""One client for an Azure model endpoint: responses, streaming, and embeddings.

The underlying ``OpenAI`` client is built on first use, not at construction, so a
pipeline can import this module and inspect configuration without holding an
Azure identity.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from typing import Any

from .config import DEFAULT_ENV_PREFIX, LlmConfig, LlmConfigError
from .credentials import bearer_token_provider


class AzureLlmClient:
    """Azure OpenAI access over Entra ID, with no API key anywhere in the path."""

    def __init__(self, config: LlmConfig, *, credential: Any | None = None, client: Any | None = None) -> None:
        self._config = config
        self._credential = credential
        self._client = client
        self._embeddings_client: Any | None = None

    @classmethod
    def from_env(
        cls,
        prefix: str = DEFAULT_ENV_PREFIX,
        *,
        credential: Any | None = None,
        client: Any | None = None,
        **overrides: object,
    ) -> "AzureLlmClient":
        """Build from ``<prefix>*`` environment variables read at call time."""
        return cls(LlmConfig.from_env(prefix, **overrides), credential=credential, client=client)

    @property
    def config(self) -> LlmConfig:
        return self._config

    @property
    def client(self) -> Any:
        """The OpenAI-compatible client, built on first use."""
        if self._client is None:
            self._client = self._build(self._config.endpoint)
        return self._client

    @property
    def embeddings_client(self) -> Any:
        """Client for the embeddings base URL, which may differ from the chat endpoint."""
        if self._config.embeddings_base_url == self._config.endpoint:
            return self.client
        if self._embeddings_client is None:
            self._embeddings_client = self._build(self._config.embeddings_base_url)
        return self._embeddings_client

    def _build(self, base_url: str) -> Any:
        from openai import OpenAI

        # The token provider is called per request, so a long-lived client keeps
        # working across token expiry. It is a callable, not a stored secret.
        provider = bearer_token_provider(self._config.scope, self._credential)
        return OpenAI(
            base_url=base_url,
            api_key=provider,
            timeout=self._config.timeout_seconds,
            max_retries=self._config.max_retries,
        )

    def _model(self, model: str | None) -> str:
        resolved = model or self._config.model
        if not resolved:
            raise LlmConfigError("no model given and no default model configured")
        return resolved

    def respond(
        self,
        *,
        input: Any,
        instructions: str | None = None,
        model: str | None = None,
        max_output_tokens: int | None = None,
        reasoning_effort: str | None = None,
        tools: Sequence[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> Any:
        """One Responses API call. Returns the SDK response object unchanged."""
        return self.client.responses.create(**self._request(
            input=input, instructions=instructions, model=model,
            max_output_tokens=max_output_tokens, reasoning_effort=reasoning_effort,
            tools=tools, **kwargs,
        ))

    def respond_text(self, **kwargs: Any) -> str:
        """One Responses API call, reduced to its output text."""
        return (self.respond(**kwargs).output_text or "").strip()

    def stream(self, **kwargs: Any) -> Iterator[Any]:
        """A streaming Responses call. Close the returned stream when done."""
        request = self._request(**kwargs)
        return self.client.responses.create(**request, stream=True)

    def _request(
        self,
        *,
        input: Any,
        instructions: str | None = None,
        model: str | None = None,
        max_output_tokens: int | None = None,
        reasoning_effort: str | None = None,
        tools: Sequence[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Build a Responses request, omitting every unset optional field."""
        request: dict[str, Any] = {"model": self._model(model), "input": input}
        if instructions is not None:
            request["instructions"] = instructions
        if max_output_tokens is not None:
            request["max_output_tokens"] = max_output_tokens
        if reasoning_effort is not None:
            request["reasoning"] = {"effort": reasoning_effort}
        if tools is not None:
            request["tools"] = list(tools)
        request.update(kwargs)
        return request

    def embed(
        self,
        texts: Sequence[str],
        *,
        deployment: str | None = None,
        dimensions: int | None = None,
    ) -> list[list[float]]:
        """Embed texts, returned in the order given."""
        resolved = deployment or self._config.embedding_deployment
        if not resolved:
            raise LlmConfigError("no deployment given and no default embedding_deployment configured")
        items = list(texts)
        if not items:
            return []
        request: dict[str, Any] = {"model": resolved, "input": items}
        if dimensions is not None:
            request["dimensions"] = dimensions
        response = self.embeddings_client.embeddings.create(**request)
        # The service orders results by an explicit index field, not by position.
        ordered = sorted(response.data, key=lambda item: item.index)
        vectors = [list(item.embedding) for item in ordered]
        if len(vectors) != len(items):
            raise RuntimeError(f"embedding count mismatch: sent {len(items)}, received {len(vectors)}")
        return vectors

    def describe(self) -> dict[str, Any]:
        """Non-secret description of what this client would call. Makes no request."""
        return {
            "endpoint": self._config.endpoint,
            "embeddings_endpoint": self._config.embeddings_base_url,
            "model": self._config.model,
            "embedding_deployment": self._config.embedding_deployment,
            "scope": self._config.scope,
            "auth": "entra-id-bearer-token",
            "timeout_seconds": self._config.timeout_seconds,
            "max_retries": self._config.max_retries,
        }
