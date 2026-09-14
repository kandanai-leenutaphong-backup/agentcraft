"""The asynchronous client — same contract, different await points.

WHY THIS IS A SEPARATE CLASS
----------------------------
``AsyncOpenAI`` *awaits* its ``api_key`` provider while ``OpenAI`` calls it.
A provider from the synchronous identity module returns a string and a
provider from its asyncio module returns a coroutine, so mixing the two
produces either ``await`` on a ``str`` or a coroutine put in an HTTP header.
Two classes, two credential modules, no ambiguity. See GOTCHAS.md, G5.

The async credential also owns an async transport, so :meth:`aclose` is not
optional housekeeping: skipping it leaks a connection pool and prints
"Unclosed client session" at interpreter exit.

DEPENDENCIES
------------
``openai>=2`` and ``azure-identity``, both imported lazily.
"""

from __future__ import annotations

import inspect
import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Iterable, TypeVar

from modelaccess import auth
from modelaccess.config import ModelConfig
from modelaccess.errors import ModelError, classify
from modelaccess.invoke import (
    convenience_request,
    embedding_raw_request,
    embedding_request,
    raw_request,
    resolve_deployment,
    stream_delta,
    stream_request,
)
from modelaccess.results import EmbeddingResult, ParsedResult, TextResult

logger = logging.getLogger(__name__)

T = TypeVar("T")


class AsyncModelClient:
    """The asyncio twin of :class:`modelaccess.client.ModelClient`.

    Build it with :func:`modelaccess.connect_async`. Construct it directly
    only to inject a fake ``client`` in tests. Same arguments and same
    ownership rules as the synchronous class.
    """

    def __init__(
        self,
        config: ModelConfig,
        *,
        client: Any | None = None,
        token_provider: Any | None = None,
        credential: Any | None = None,
        owns_credential: bool = False,
        owns_client: bool | None = None,
    ) -> None:
        self.config = config
        self._credential = credential
        self._owns_credential = owns_credential and credential is not None
        self._owns_client = client is None if owns_client is None else bool(owns_client)
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
            "async model client ready host=%s deployment=%s timeout=%.1fs retries=%d",
            config.account_host,
            config.deployment,
            config.timeout_secs,
            config.max_retries,
        )

    @staticmethod
    def _build_client(config: ModelConfig, token_provider: Any) -> Any:
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise ModelError(
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
            raise ModelError(
                "client is closed; build a new one with connect_async()",
                category="config",
                retryable=False,
            )

    @asynccontextmanager
    async def _translate(self, deployment: str) -> AsyncIterator[None]:
        try:
            yield
        # ``asyncio.CancelledError`` is a BaseException since 3.8. Catching it
        # here would defeat ``wait_for``, ``asyncio.timeout``, task groups and
        # every shutdown path, and would report a cancelled task as a failed
        # one. Narrowing to Exception leaves cancellation, Ctrl-C and generator
        # teardown to propagate untouched. See GOTCHAS.md, G14.
        except Exception as exc:
            error = classify(exc, deployment=deployment)
            if error is exc:
                raise
            raise error from exc

    # ---------------------------------------------------------------- raw

    async def respond(self, **options: Any) -> Any:
        """``responses.create`` with full control and no interpretation."""
        self._check_open()
        request = raw_request(self.config, options)
        deployment = str(request.get("model"))
        async with self._translate(deployment):
            response = await self._client.responses.create(**request)
        logger.debug(
            "respond deployment=%s response_id=%s", deployment, getattr(response, "id", None)
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
    ) -> TextResult:
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
        result = TextResult.from_response(response, deployment=target)
        logger.debug("ask %s", result.metadata())
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
        logger.debug("parse %s", result.metadata())
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

        Same contract as :meth:`modelaccess.client.ModelClient.embed`: the
        configured embedding deployment rather than the chat one, an iterable
        copied before validation, and vectors verified against the provider's
        indexes before they are returned.
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
        logger.debug("embed %s", result.metadata())
        return result

    async def embed_raw(self, **options: Any) -> Any:
        """``embeddings.create`` with full control; only ``model`` is defaulted.

        ``allow_foreign_account=True`` is consumed here and never sent — the
        documented escape from the cross-account guard.
        """
        self._check_open()
        request = embedding_raw_request(self.config, options)
        deployment = str(request.get("model"))
        async with self._translate(deployment):
            return await self._client.embeddings.create(**request)

    # ------------------------------------------------------------ stream

    def stream_text(
        self,
        prompt: str,
        *,
        deployment: str | None = None,
        instructions: str | None = None,
        **options: Any,
    ) -> AsyncIterator[str]:
        """Yield output text deltas as they arrive.

        A plain method, not an async generator: a closed client or a bad
        option has to refuse when the call is made, not when the caller first
        iterates. An async generator body would defer both. See CONTRACT.md,
        invariant 9.

        Provider ``error`` and ``response.failed`` events raise
        :class:`~modelaccess.errors.ModelError`.
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
        return self._iter_text(request, target)

    async def _iter_text(self, request: dict[str, Any], target: str) -> AsyncIterator[str]:
        events = self._iter_events(request, target)
        # Explicit aclose: when stream_delta raises an in-stream failure, the
        # inner async generator is otherwise left suspended until the garbage
        # collector runs, holding the socket open. A sync generator unwinds
        # immediately; an async one does not. See GOTCHAS.md, G10.
        try:
            async for event in events:
                delta = stream_delta(event, deployment=target)
                if delta:
                    yield delta
        finally:
            await events.aclose()

    def stream_events(self, **options: Any) -> AsyncIterator[Any]:
        """Yield raw Responses stream events, unfiltered.

        ``stream=True`` is redundant but accepted; ``stream=False`` raises
        :class:`~modelaccess.errors.ConfigError` rather than being dropped.
        """
        self._check_open()
        request = stream_request(self.config, options)
        deployment = str(request.get("model"))
        return self._iter_raw_events(request, deployment)

    async def _iter_raw_events(
        self, request: dict[str, Any], deployment: str
    ) -> AsyncIterator[Any]:
        events = self._iter_events(request, deployment)
        try:
            async for event in events:
                yield event
        finally:
            await events.aclose()

    async def _iter_events(self, request: dict[str, Any], deployment: str) -> AsyncIterator[Any]:
        async with self._translate(deployment):
            stream = await self._client.responses.create(**dict(request, stream=True))
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
            # Also runs when the consumer stops early: ``aclose()`` on the
            # async generator throws GeneratorExit in here. See GOTCHAS.md, G10.
            close = getattr(stream, "close", None)
            if callable(close):
                result = close()
                if inspect.isawaitable(result):
                    await result

    # --------------------------------------------------------- lifecycle

    async def aclose(self) -> None:
        """Release what this object owns: its HTTP pool, and its credential.

        An injected ``client`` or ``credential`` is left open unless ownership
        was transferred explicitly.
        """
        if self._closed:
            return
        self._closed = True
        for target, owned in (
            (self._client, self._owns_client),
            (self._credential, self._owns_credential),
        ):
            if not owned or target is None:
                continue
            close = getattr(target, "close", None)
            if not callable(close):
                continue
            try:
                result = close()
                if inspect.isawaitable(result):
                    await result
            except Exception:
                logger.debug("aclose: %s.close() failed", type(target).__name__)

    async def __aenter__(self) -> "AsyncModelClient":
        self._check_open()
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        await self.aclose()


__all__ = ["AsyncModelClient"]
