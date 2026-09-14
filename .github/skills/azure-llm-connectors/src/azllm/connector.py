"""The synchronous connector — one client, reused, identity-authenticated.

WHY THIS EXISTS
---------------
Constructing an ``OpenAI`` client per request throws away the connection
pool, so every call pays a fresh TLS handshake, and it re-creates the
credential chain, so every call risks a fresh token acquisition. Both are
invisible in a demo and dominate latency under load. :class:`FoundryConnector`
builds the client and the token provider exactly once and is safe to share
across threads: the underlying ``httpx`` client is.

WHAT IS NOT WRAPPED
-------------------
:meth:`FoundryConnector.respond` forwards arbitrary keyword arguments to
``responses.create``. Tools, ``previous_response_id``, ``reasoning``,
``include``, ``background``, ``store``, and whatever the API ships next are
reachable without this library being updated. The convenience methods are
sugar on top, never the only door.

DEPENDENCIES
------------
``openai>=2``, ``azure-identity``.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Iterable, Iterator, TypeVar

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


class FoundryConnector:
    """A reusable, identity-authenticated client for one Foundry account.

    Build it with :func:`azllm.connect`. Construct it directly only to inject
    a fake ``client`` in tests.

    Args:
        config: Validated coordinates. Required.
        client: An ``OpenAI``-shaped object. When supplied, no credential and
            no token provider are created, which is what makes the tests
            cloud-free.
        token_provider: A zero-argument callable returning a bearer token
            string. Invoked by the SDK on every request.
        credential: A ``TokenCredential`` to derive the provider from.
        owns_credential: Whether :meth:`close` should close ``credential``.
            False for an injected credential — closing something the caller
            still holds breaks the caller.
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
                    credential = auth.default_credential(config)
                    self._credential = credential
                    self._owns_credential = True
                token_provider = auth.bearer_token_provider(config, credential)
            # Cached for the life of the connector. The callable is handed to
            # the SDK, never called here: the SDK invokes it per request, so
            # token refresh is the credential's business and no token string
            # is ever frozen into the client.
            self._token_provider = token_provider
            self._client = self._build_client(config, token_provider)

        logger.debug(
            "azllm connector ready host=%s deployment=%s timeout=%.1fs retries=%d",
            config.account_host,
            config.deployment,
            config.timeout_secs,
            config.max_retries,
        )

    @staticmethod
    def _build_client(config: FoundryConfig, token_provider: Any) -> Any:
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - hard dependency
            raise LlmError(
                "openai is not installed; pip install 'openai>=2'", category="config"
            ) from exc
        return OpenAI(
            base_url=config.base_url,
            api_key=token_provider,
            timeout=config.timeout_secs,
            max_retries=config.max_retries,
        )

    @property
    def client(self) -> Any:
        """The underlying OpenAI client, for anything this library does not model."""
        self._check_open()
        return self._client

    @property
    def token_provider(self) -> Any:
        """The per-request token callable handed to the SDK."""
        return self._token_provider

    def _check_open(self) -> None:
        if self._closed:
            raise LlmError(
                "connector is closed; build a new one with connect()",
                category="config",
                retryable=False,
            )

    @contextmanager
    def _translate(self, deployment: str) -> Iterator[None]:
        try:
            yield
        except BaseException as exc:  # noqa: BLE001 - re-raised, sanitised
            raise classify(exc, deployment=deployment) from exc

    # ---------------------------------------------------------------- raw

    def respond(self, **options: Any) -> Any:
        """Call ``responses.create`` with full control and no interpretation.

        Every Responses API parameter is accepted. ``model`` defaults to the
        configured deployment when omitted. The provider object is returned
        untouched — including a ``Stream`` when ``stream=True``.
        """
        self._check_open()
        request = raw_request(self.config, options)
        deployment = str(request.get("model"))
        with self._translate(deployment):
            response = self._client.responses.create(**request)
        logger.debug(
            "azllm respond deployment=%s response_id=%s",
            deployment,
            getattr(response, "id", None),
        )
        return response

    # -------------------------------------------------------- convenience

    def ask(
        self,
        prompt: str,
        *,
        deployment: str | None = None,
        instructions: str | None = None,
        **options: Any,
    ) -> LlmResult:
        """Send one prompt, get text plus metadata back.

        ``store`` defaults to False. Prompts and completions are never
        logged.
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
        with self._translate(target):
            response = self._client.responses.create(**request)
        result = LlmResult.from_response(response, deployment=target)
        logger.debug("azllm ask %s", result.metadata())
        return result

    def parse(
        self,
        prompt: str,
        *,
        text_format: type[T],
        deployment: str | None = None,
        instructions: str | None = None,
        **options: Any,
    ) -> ParsedResult[T]:
        """Send one prompt and validate the answer into ``text_format``.

        ``text_format`` is a pydantic model class; the SDK derives the JSON
        schema, enforces it server-side and validates the result into
        ``ParsedResult.parsed``. A refusal leaves ``parsed`` None rather
        than raising.
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
        with self._translate(target):
            response = self._client.responses.parse(text_format=text_format, **request)
        result: ParsedResult[T] = ParsedResult.from_response(response, deployment=target)
        logger.debug("azllm parse %s", result.metadata())
        return result

    # -------------------------------------------------------- embeddings

    def embed(
        self,
        input: str | Iterable[str],
        /,
        *,
        deployment: str | None = None,
        dimensions: int | None = None,
        **options: Any,
    ) -> EmbeddingResult:
        """Embed one string or a batch of strings.

        The deployment is the embedding default, never the chat deployment
        this connector may be configured with; pass ``deployment=`` or build
        the connector from :func:`azllm.embedding_config` to choose. A
        deployment is only reachable through the endpoint of the account that
        owns it.

        Args:
            input: One string, or any iterable of strings. An iterable is
                copied before anything else happens, so a generator or a list
                mutated afterwards cannot desynchronise the result.
            deployment: Per-call override.
            dimensions: Truncated vector width, supported by the
                ``text-embedding-3`` family. Must be a positive int.
            **options: Any other embeddings parameter — ``encoding_format``,
                ``user``, ``extra_headers`` — passed through untouched.

        Returns:
            An :class:`~azllm.result.EmbeddingResult` whose vectors are in
            input order, verified against the provider's indexes.

        Raises:
            ConfigError: for a bad input type, an empty string, an empty
                batch, more than 2048 inputs, or a non-positive
                ``dimensions`` — all before any request is sent.
            LlmError: for any provider failure, and for a response that
                cannot be aligned to the inputs.
        """
        self._check_open()
        prepared = embedding_request(
            self.config,
            input=input,
            deployment=deployment,
            dimensions=dimensions,
            options=options,
        )
        with self._translate(prepared.deployment):
            response = self._client.embeddings.create(**prepared.kwargs)
        result = EmbeddingResult.from_response(
            response, deployment=prepared.deployment, expected_count=prepared.count
        )
        logger.debug("azllm embed %s", result.metadata())
        return result

    def embed_raw(self, **options: Any) -> Any:
        """Call ``embeddings.create`` with full control and no interpretation.

        Only ``model`` is defaulted, to the embedding deployment. The
        provider object is returned untouched — the door to ``base64``
        vectors, token-id inputs and anything the API ships next.
        """
        self._check_open()
        request = embedding_raw_request(self.config, options)
        deployment = str(request.get("model"))
        with self._translate(deployment):
            return self._client.embeddings.create(**request)

    # ------------------------------------------------------------ stream

    def stream_text(
        self,
        prompt: str,
        *,
        deployment: str | None = None,
        instructions: str | None = None,
        **options: Any,
    ) -> Iterator[str]:
        """Yield output text deltas as they arrive.

        Provider ``error`` and ``response.failed`` events raise
        :class:`~azllm.errors.LlmError`; a stream that ends early is never
        reported as a successful empty answer.
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

    def _iter_text(self, request: dict[str, Any], deployment: str) -> Iterator[str]:
        with self._translate(deployment):
            stream = self._client.responses.create(stream=True, **request)
        events = iter(stream)
        try:
            while True:
                with self._translate(deployment):
                    try:
                        event = next(events)
                    except StopIteration:
                        break
                delta = stream_delta(event, deployment=deployment)
                if delta:
                    yield delta
        finally:
            close = getattr(stream, "close", None)
            if callable(close):
                close()

    def stream_events(self, **options: Any) -> Iterator[Any]:
        """Yield raw Responses stream events, unfiltered.

        For callers that need tool-call deltas, reasoning summaries or
        usage-bearing terminal events. Error events are *not* raised here:
        holding the raw feed means owning its semantics.
        """
        self._check_open()
        request = raw_request(self.config, options)
        request.pop("stream", None)
        deployment = str(request.get("model"))
        return self._iter_events(request, deployment)

    def _iter_events(self, request: dict[str, Any], deployment: str) -> Iterator[Any]:
        with self._translate(deployment):
            stream = self._client.responses.create(stream=True, **request)
        events = iter(stream)
        try:
            while True:
                with self._translate(deployment):
                    try:
                        event = next(events)
                    except StopIteration:
                        break
                yield event
        finally:
            close = getattr(stream, "close", None)
            if callable(close):
                close()

    # --------------------------------------------------------- lifecycle

    def close(self) -> None:
        """Release the HTTP pool, and the credential when this object made it."""
        if self._closed:
            return
        self._closed = True
        for target, owned in ((self._client, True), (self._credential, self._owns_credential)):
            if not owned or target is None:
                continue
            close = getattr(target, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:  # pragma: no cover - shutdown must not raise
                    logger.debug("azllm close: %s.close() failed", type(target).__name__)

    def __enter__(self) -> "FoundryConnector":
        self._check_open()
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.close()
