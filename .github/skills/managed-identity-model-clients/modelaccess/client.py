"""The synchronous client — one HTTP client, reused, identity-authenticated.

WHY THIS EXISTS
---------------
Constructing an ``OpenAI`` client per request throws away the connection
pool, so every call pays a fresh TLS handshake, and it re-creates the
credential chain, so every call risks a fresh token acquisition. Both are
invisible in a demo and dominate latency under load. :class:`ModelClient`
builds the client and the token provider exactly once and is safe to share
across threads: the underlying ``httpx`` client is.

WHAT IS NOT WRAPPED
-------------------
:meth:`ModelClient.respond` forwards arbitrary keyword arguments to
``responses.create``. Tools, ``previous_response_id``, ``reasoning``,
``include``, ``background``, ``store``, and whatever the API ships next are
reachable without this package being updated. The convenience methods are
sugar on top, never the only door.

DEPENDENCIES
------------
``openai>=2`` and ``azure-identity``, both imported lazily: a client injected
by a caller needs neither.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Iterable, Iterator, TypeVar

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


class ModelClient:
    """A reusable, identity-authenticated client for one model account.

    Build it with :func:`modelaccess.connect`. Construct it directly only to
    inject a fake ``client`` in tests.

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
            still holds breaks the caller. See GOTCHAS.md, G9.
        owns_client: Whether :meth:`close` should close ``client``. Defaults
            to True only for a client this object built. An injected client
            may be shared with other code, and closing it out from under that
            code is the same defect ``owns_credential`` exists to prevent.
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
                    credential = auth.default_credential(config)
                    self._credential = credential
                    self._owns_credential = True
                token_provider = auth.bearer_token_provider(config, credential)
            # Cached for the life of the client. The callable is handed to the
            # SDK, never called here: the SDK invokes it per request, so token
            # refresh is the credential's business and no token string is ever
            # frozen into the client.
            self._token_provider = token_provider
            self._client = self._build_client(config, token_provider)

        logger.debug(
            "model client ready host=%s deployment=%s timeout=%.1fs retries=%d",
            config.account_host,
            config.deployment,
            config.timeout_secs,
            config.max_retries,
        )

    @staticmethod
    def _build_client(config: ModelConfig, token_provider: Any) -> Any:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise ModelError(
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
        """The underlying OpenAI client, for anything this package does not model."""
        self._check_open()
        return self._client

    @property
    def token_provider(self) -> Any:
        """The per-request token callable handed to the SDK."""
        return self._token_provider

    def _check_open(self) -> None:
        if self._closed:
            raise ModelError(
                "client is closed; build a new one with connect()",
                category="config",
                retryable=False,
            )

    @contextmanager
    def _translate(self, deployment: str) -> Iterator[None]:
        try:
            yield
        # KeyboardInterrupt, SystemExit, GeneratorExit and asyncio.CancelledError
        # are BaseException, not Exception: catching them would turn Ctrl-C and
        # generator teardown into a retryable-looking ModelError. They are left
        # alone by narrowing to Exception. See GOTCHAS.md, G14.
        except Exception as exc:
            error = classify(exc, deployment=deployment)
            if error is exc:
                # Already a ModelError from below. Re-raising it ``from exc``
                # would make it its own ``__cause__``.
                raise
            raise error from exc

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
            "respond deployment=%s response_id=%s", deployment, getattr(response, "id", None)
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
    ) -> TextResult:
        """Send one prompt, get text plus metadata back.

        ``store`` defaults to False. Prompts and completions are never logged.
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
        result = TextResult.from_response(response, deployment=target)
        logger.debug("ask %s", result.metadata())
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
        ``ParsedResult.parsed``. A refusal leaves ``parsed`` None rather than
        raising.
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
        logger.debug("parse %s", result.metadata())
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

        The deployment is the configured embedding deployment, never the chat
        deployment; there is no fallback, because a chat deployment answers an
        embedding request with a 404 that reads like a typo.

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
            An :class:`~modelaccess.results.EmbeddingResult` whose vectors are
            in input order, verified against the provider's indexes.

        Raises:
            ConfigError: for an unconfigured embedding deployment, a bad input
                type, an empty string, an empty batch, an over-large batch, or
                a non-positive ``dimensions`` — all before any request is sent.
            ModelError: for any provider failure, and for a response that
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
        logger.debug("embed %s", result.metadata())
        return result

    def embed_raw(self, **options: Any) -> Any:
        """Call ``embeddings.create`` with full control and no interpretation.

        Only ``model`` is defaulted, to the configured embedding deployment.
        The provider object is returned untouched — the door to ``base64``
        vectors, token-id inputs and anything the API ships next.

        ``allow_foreign_account=True`` is consumed here and never sent: it is
        the documented escape from the cross-account guard, for a caller who
        has decided this client's base URL really can serve that deployment.
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
        :class:`~modelaccess.errors.ModelError`; a stream that ends early is
        never reported as a successful empty answer.
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
            # Runs on exhaustion, on an error event, and on generator close —
            # which is what abandoning the iterator triggers. The socket is
            # released either way. See GOTCHAS.md, G10.
            close = getattr(stream, "close", None)
            if callable(close):
                close()

    def stream_events(self, **options: Any) -> Iterator[Any]:
        """Yield raw Responses stream events, unfiltered.

        For callers that need tool-call deltas, reasoning summaries or
        usage-bearing terminal events. Error events are *not* raised here:
        holding the raw feed means owning its semantics.

        ``stream=True`` is redundant but accepted; ``stream=False`` is a
        contradiction and raises :class:`~modelaccess.errors.ConfigError`
        rather than being silently overridden.
        """
        self._check_open()
        request = stream_request(self.config, options)
        deployment = str(request.get("model"))
        return self._iter_events(request, deployment)

    def _iter_events(self, request: dict[str, Any], deployment: str) -> Iterator[Any]:
        with self._translate(deployment):
            stream = self._client.responses.create(**request)
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
        """Release what this object owns: its HTTP pool, and its credential.

        An injected ``client`` or ``credential`` is left open unless ownership
        was transferred explicitly with ``owns_client=``/``owns_credential=``.
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
            if callable(close):
                try:
                    close()
                except Exception:
                    logger.debug("close: %s.close() failed", type(target).__name__)

    def __enter__(self) -> "ModelClient":
        self._check_open()
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.close()


__all__ = ["ModelClient"]
