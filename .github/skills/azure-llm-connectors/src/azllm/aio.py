"""The asynchronous connector — same contract, different await points.

WHY THIS IS A SEPARATE CLASS
----------------------------
``AsyncOpenAI`` *awaits* its ``api_key`` provider
(``openai/_client.py``: ``self.api_key = await self._api_key_provider()``),
while ``OpenAI`` calls it. A provider from ``azure.identity`` returns a
string and a provider from ``azure.identity.aio`` returns a coroutine, so
mixing the two produces either ``await`` on a ``str`` or a coroutine put in
an HTTP header. Two classes, two credential modules, no ambiguity.

The async credential also owns an async transport, so :meth:`aclose` is not
optional housekeeping: skipping it leaks a connection pool and prints
"Unclosed client session" at interpreter exit.

DEPENDENCIES
------------
``openai>=2``, ``azure-identity``.
"""

from __future__ import annotations

import inspect
import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Iterable, TypeVar

from azllm import auth
from azllm._invoke import (
    convenience_request,
    embedding_raw_request,
    embedding_request,
    raw_request,
    resolve_deployment,
    stream_delta,
)
from azllm.config import FoundryConfig
from azllm.errors import LlmError, classify
from azllm.result import EmbeddingResult, LlmResult, ParsedResult

logger = logging.getLogger(__name__)

T = TypeVar("T")


class AsyncFoundryConnector:
    """The asyncio twin of :class:`azllm.connector.FoundryConnector`.

    Build it with :func:`azllm.connect_async`. Construct it directly only to
    inject a fake ``client`` in tests.
    """

    def __init__(
        self,
        config: FoundryConfig,
        *,
        client: Any | None = None,
        token_provider: Any | None = None,
        credential: Any | None = None,
        owns_credential: bool = False,
    ) -> None:
        self.config = config
        self._credential = credential
        self._owns_credential = owns_credential and credential is not None
        self._closed = False

        if client is not None:
            self._token_provider = token_provider
            self._client = client
        else:
            if token_provider is None:
                if credential is None:
                    credential = auth.default_async_credential(config)
                    self._credential = credential
                    self._owns_credential = True
                token_provider = auth.async_bearer_token_provider(config, credential)
            self._token_provider = token_provider
            self._client = self._build_client(config, token_provider)

        logger.debug(
            "azllm async connector ready host=%s deployment=%s timeout=%.1fs retries=%d",
            config.account_host,
            config.deployment,
            config.timeout_secs,
            config.max_retries,
        )

    @staticmethod
    def _build_client(config: FoundryConfig, token_provider: Any) -> Any:
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:  # pragma: no cover - hard dependency
            raise LlmError(
                "openai is not installed; pip install 'openai>=2'", category="config"
            ) from exc
        return AsyncOpenAI(
            base_url=config.base_url,
            api_key=token_provider,
            timeout=config.timeout_secs,
            max_retries=config.max_retries,
        )

    @property
    def client(self) -> Any:
        """The underlying AsyncOpenAI client, for anything not modelled here."""
        self._check_open()
        return self._client

    @property
    def token_provider(self) -> Any:
        """The per-request token coroutine factory handed to the SDK."""
        return self._token_provider

    def _check_open(self) -> None:
        if self._closed:
            raise LlmError(
                "connector is closed; build a new one with connect_async()",
                category="config",
                retryable=False,
            )

    @asynccontextmanager
    async def _translate(self, deployment: str) -> AsyncIterator[None]:
        try:
            yield
        except BaseException as exc:  # noqa: BLE001 - re-raised, sanitised
            raise classify(exc, deployment=deployment) from exc

    # ---------------------------------------------------------------- raw

    async def respond(self, **options: Any) -> Any:
        """``responses.create`` with full control and no interpretation."""
        self._check_open()
        request = raw_request(self.config, options)
        deployment = str(request.get("model"))
        async with self._translate(deployment):
            response = await self._client.responses.create(**request)
        logger.debug(
            "azllm respond deployment=%s response_id=%s",
            deployment,
            getattr(response, "id", None),
        )
        return response

    # -------------------------------------------------------- convenience

    async def ask(
        self,
        prompt: str,
        *,
        deployment: str | None = None,
        instructions: str | None = None,
        **options: Any,
    ) -> LlmResult:
        """Send one prompt, get text plus metadata back. ``store`` defaults False."""
        self._check_open()
        target = resolve_deployment(self.config, deployment)
        request = convenience_request(
            self.config,
            prompt=prompt,
            deployment=deployment,
            instructions=instructions,
            options=options,
        )
        async with self._translate(target):
            response = await self._client.responses.create(**request)
        result = LlmResult.from_response(response, deployment=target)
        logger.debug("azllm ask %s", result.metadata())
        return result

    async def parse(
        self,
        prompt: str,
        *,
        text_format: type[T],
        deployment: str | None = None,
        instructions: str | None = None,
        **options: Any,
    ) -> ParsedResult[T]:
        """Send one prompt and validate the answer into ``text_format``."""
        self._check_open()
        target = resolve_deployment(self.config, deployment)
        request = convenience_request(
            self.config,
            prompt=prompt,
            deployment=deployment,
            instructions=instructions,
            options=options,
        )
        async with self._translate(target):
            response = await self._client.responses.parse(text_format=text_format, **request)
        result: ParsedResult[T] = ParsedResult.from_response(response, deployment=target)
        logger.debug("azllm parse %s", result.metadata())
        return result

    # -------------------------------------------------------- embeddings

    async def embed(
        self,
        input: str | Iterable[str],
        /,
        *,
        deployment: str | None = None,
        dimensions: int | None = None,
        **options: Any,
    ) -> EmbeddingResult:
        """Embed one string or a batch of strings.

        Same contract as :meth:`azllm.connector.FoundryConnector.embed`: the
        embedding deployment default rather than the chat one, an iterable
        copied before validation, and vectors verified against the
        provider's indexes before they are returned.
        """
        self._check_open()
        prepared = embedding_request(
            self.config,
            input=input,
            deployment=deployment,
            dimensions=dimensions,
            options=options,
        )
        async with self._translate(prepared.deployment):
            response = await self._client.embeddings.create(**prepared.kwargs)
        result = EmbeddingResult.from_response(
            response, deployment=prepared.deployment, expected_count=prepared.count
        )
        logger.debug("azllm embed %s", result.metadata())
        return result

    async def embed_raw(self, **options: Any) -> Any:
        """``embeddings.create`` with full control; only ``model`` is defaulted."""
        self._check_open()
        request = embedding_raw_request(self.config, options)
        deployment = str(request.get("model"))
        async with self._translate(deployment):
            return await self._client.embeddings.create(**request)

    # ------------------------------------------------------------ stream

    async def stream_text(
        self,
        prompt: str,
        *,
        deployment: str | None = None,
        instructions: str | None = None,
        **options: Any,
    ) -> AsyncIterator[str]:
        """Yield output text deltas as they arrive.

        Provider ``error`` and ``response.failed`` events raise
        :class:`~azllm.errors.LlmError`.
        """
        self._check_open()
        target = resolve_deployment(self.config, deployment)
        request = convenience_request(
            self.config,
            prompt=prompt,
            deployment=deployment,
            instructions=instructions,
            options=options,
        )
        async for event in self._iter_events(request, target):
            delta = stream_delta(event, deployment=target)
            if delta:
                yield delta

    async def stream_events(self, **options: Any) -> AsyncIterator[Any]:
        """Yield raw Responses stream events, unfiltered."""
        self._check_open()
        request = raw_request(self.config, options)
        request.pop("stream", None)
        deployment = str(request.get("model"))
        async for event in self._iter_events(request, deployment):
            yield event

    async def _iter_events(self, request: dict[str, Any], deployment: str) -> AsyncIterator[Any]:
        async with self._translate(deployment):
            stream = await self._client.responses.create(stream=True, **request)
        events = stream.__aiter__()
        try:
            while True:
                async with self._translate(deployment):
                    try:
                        event = await events.__anext__()
                    except StopAsyncIteration:
                        break
                yield event
        finally:
            close = getattr(stream, "close", None)
            if callable(close):
                result = close()
                if inspect.isawaitable(result):
                    await result

    # --------------------------------------------------------- lifecycle

    async def aclose(self) -> None:
        """Release the HTTP pool, and the credential when this object made it."""
        if self._closed:
            return
        self._closed = True
        for target, owned in ((self._client, True), (self._credential, self._owns_credential)):
            if not owned or target is None:
                continue
            close = getattr(target, "close", None)
            if not callable(close):
                continue
            try:
                result = close()
                if inspect.isawaitable(result):
                    await result
            except Exception:  # pragma: no cover - shutdown must not raise
                logger.debug("azllm aclose: %s.close() failed", type(target).__name__)

    async def __aenter__(self) -> "AsyncFoundryConnector":
        self._check_open()
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        await self.aclose()
