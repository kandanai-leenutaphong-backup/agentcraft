"""Test doubles. Nothing here touches the network or Azure.

The fakes mimic exactly the shapes the connectors depend on: the
``client.responses`` and ``client.embeddings`` resources, the response
objects' public attributes, and the stream's iteration protocol. Everything
else about the real SDK is irrelevant to this library's contract and is
deliberately not simulated.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

try:  # openai>=3 vendors its transport as httpx2
    import httpx2 as httpx  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - openai 2.x
    import httpx  # type: ignore[no-redef]

PROBE_URL = "https://acct.openai.azure.com/openai/v1/responses"

# A message shaped like the ones the provider actually returns: it quotes the
# offending input. If this string ever reaches a caller, sanitisation failed.
LEAKY_MESSAGE = "Invalid prompt: 'my secret patient record' was rejected"
LEAKY_BODY = {"error": {"message": LEAKY_MESSAGE, "code": "content_filter"}, "code": "content_filter"}


class FakeUsage:
    def __init__(self, **counts: int) -> None:
        self._counts = counts

    def model_dump(self) -> dict[str, int]:
        return dict(self._counts)


@dataclass
class FakeResponse:
    id: str = "resp_fake_1"
    model: str = "chat"
    status: str = "completed"
    output_text: str = "hello"
    usage: Any = field(default_factory=lambda: FakeUsage(input_tokens=7, output_tokens=3, total_tokens=10))
    output_parsed: Any = None


class FakeEvent:
    """A stream event with only the fields the connectors read."""

    def __init__(self, type: str, **fields: Any) -> None:
        self.type = type
        for key, value in fields.items():
            setattr(self, key, value)


def text_delta(delta: str) -> FakeEvent:
    return FakeEvent("response.output_text.delta", delta=delta)


def error_event(code: str = "server_error") -> FakeEvent:
    return FakeEvent("error", code=code, message=LEAKY_MESSAGE)


def failed_event(code: str = "content_filter") -> FakeEvent:
    response = FakeEvent("response", error=FakeEvent("error", code=code, message=LEAKY_MESSAGE))
    return FakeEvent("response.failed", response=response)


class FakeStream:
    def __init__(self, events: Iterable[Any]) -> None:
        self._events = list(events)
        self.closed = False

    def __iter__(self) -> Any:
        return iter(self._events)

    def close(self) -> None:
        self.closed = True


class FakeAsyncStream:
    def __init__(self, events: Iterable[Any]) -> None:
        self._events = list(events)
        self.closed = False

    def __aiter__(self) -> "FakeAsyncStream":
        self._iter = iter(self._events)
        return self

    async def __anext__(self) -> Any:
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration from None

    async def close(self) -> None:
        self.closed = True


class FakeResponses:
    """Records every call, replays whatever the test queued."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.parse_calls: list[dict[str, Any]] = []
        self.response = FakeResponse()
        self.parsed_response = FakeResponse(output_parsed={"ok": True}, output_text='{"ok": true}')
        self.raises: BaseException | None = None
        self.stream_events: list[Any] = []
        self.last_stream: FakeStream | None = None

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self.raises is not None:
            raise self.raises
        if kwargs.get("stream"):
            self.last_stream = FakeStream(self.stream_events)
            return self.last_stream
        return self.response

    def parse(self, **kwargs: Any) -> Any:
        self.parse_calls.append(kwargs)
        if self.raises is not None:
            raise self.raises
        return self.parsed_response


class FakeAsyncResponses(FakeResponses):
    async def create(self, **kwargs: Any) -> Any:  # type: ignore[override]
        self.calls.append(kwargs)
        if self.raises is not None:
            raise self.raises
        if kwargs.get("stream"):
            self.last_stream = FakeAsyncStream(self.stream_events)  # type: ignore[assignment]
            return self.last_stream
        return self.response

    async def parse(self, **kwargs: Any) -> Any:  # type: ignore[override]
        self.parse_calls.append(kwargs)
        if self.raises is not None:
            raise self.raises
        return self.parsed_response


class FakeEmbeddingItem:
    """One ``data`` entry, with only the two fields alignment depends on."""

    def __init__(self, index: int, embedding: Any) -> None:
        self.index = index
        self.embedding = embedding


class FakeEmbeddingResponse:
    def __init__(
        self,
        *,
        vectors: Iterable[Any] = ((0.1, -0.2, 3),),
        model: str = "text-embedding-3-large",
        indexes: Iterable[int] | None = None,
        usage: Any = None,
        data: Any = None,
    ) -> None:
        rows = list(vectors)
        order = list(indexes) if indexes is not None else list(range(len(rows)))
        self.data = (
            data
            if data is not None
            else [FakeEmbeddingItem(i, vector) for i, vector in zip(order, rows)]
        )
        self.model = model
        self.usage = usage if usage is not None else FakeUsage(prompt_tokens=4, total_tokens=4)


class FakeEmbeddings:
    """Records every embedding call, replays whatever the test queued."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.response: Any = None
        self.raises: BaseException | None = None

    def _answer(self, kwargs: dict[str, Any]) -> Any:
        self.calls.append(kwargs)
        if self.raises is not None:
            raise self.raises
        if self.response is not None:
            return self.response
        payload = kwargs.get("input")
        count = 1 if isinstance(payload, str) else len(payload)
        width = kwargs.get("dimensions") or 3
        return FakeEmbeddingResponse(
            vectors=[tuple(float(i + j) for j in range(width)) for i in range(count)],
            model=str(kwargs.get("model")),
        )

    def create(self, **kwargs: Any) -> Any:
        return self._answer(kwargs)


class FakeAsyncEmbeddings(FakeEmbeddings):
    async def create(self, **kwargs: Any) -> Any:  # type: ignore[override]
        return self._answer(kwargs)


class FakeClient:
    def __init__(self) -> None:
        self.responses = FakeResponses()
        self.embeddings = FakeEmbeddings()
        self.closed = False

    def close(self) -> None:
        self.closed = True


class FakeAsyncClient:
    def __init__(self) -> None:
        self.responses = FakeAsyncResponses()
        self.embeddings = FakeAsyncEmbeddings()
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class CountingTokenProvider:
    """A sync token provider that returns a different token every call."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self) -> str:
        self.calls += 1
        return f"fake-token-{self.calls}"


class CountingAsyncTokenProvider:
    def __init__(self) -> None:
        self.calls = 0

    async def __call__(self) -> str:
        self.calls += 1
        return f"fake-token-{self.calls}"


class FakeCredential:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class FakeAsyncCredential:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


def status_error(cls: Any, status: int, *, request_id: str = "req_abc123") -> BaseException:
    """Build a real openai status error carrying a prompt-quoting body."""
    request = httpx.Request("POST", PROBE_URL)
    response = httpx.Response(
        status_code=status,
        headers={"x-request-id": request_id},
        request=request,
    )
    return cls(LEAKY_MESSAGE, response=response, body=LEAKY_BODY)


def timeout_error() -> BaseException:
    import openai  # type: ignore[import-not-found]

    return openai.APITimeoutError(httpx.Request("POST", PROBE_URL))


def connection_error() -> BaseException:
    import openai  # type: ignore[import-not-found]

    return openai.APIConnectionError(request=httpx.Request("POST", PROBE_URL))
