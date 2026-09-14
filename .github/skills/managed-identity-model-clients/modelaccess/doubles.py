"""Offline doubles — the seam that makes every test and example cloud-free.

WHY THESE SHIP WITH THE MECHANISM
---------------------------------
Every client method takes an injected ``client``. Without a stand-in shaped
like the SDK, that seam is only usable by whoever writes a fake first, and
every adopter writes a slightly different one. These are the fakes this
package's own tests and examples run on, so a consumer's first test is the
same shape as the ones that already pass.

They imitate the *three* call sites this package actually uses —
``responses.create``, ``responses.parse`` and ``embeddings.create`` — plus
streaming and ``close()``. They are not a simulator of the service: a fake
that mirrors the implementation proves nothing about the wire. For protocol
shape, drive the real SDK over a fake HTTP transport instead; the tests in
this box do both.

DEPENDENCIES
------------
Standard library only.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Iterable, Sequence

_DEFAULT_MODEL = "deployment-under-test"


def fake_text_response(
    text: str = "",
    *,
    response_id: str = "resp_offline_1",
    model: str = _DEFAULT_MODEL,
    status: str | None = "completed",
    usage: dict[str, Any] | None = None,
) -> Any:
    """A stand-in for a Responses API object with output text."""
    return SimpleNamespace(
        output_text=text,
        id=response_id,
        model=model,
        status=status,
        usage=usage,
        output=[],
    )


def fake_parsed_response(
    parsed: Any = None,
    *,
    text: str = "",
    refusal: str | None = None,
    response_id: str = "resp_offline_1",
    model: str = _DEFAULT_MODEL,
    status: str | None = "completed",
    usage: dict[str, Any] | None = None,
) -> Any:
    """A stand-in for ``responses.parse``, optionally carrying a refusal.

    A refusal is a *successful* call whose answer is "no": ``output_parsed``
    is None and the refusal text sits in ``output[].content[].refusal``.
    """
    output = []
    if refusal is not None:
        output = [SimpleNamespace(content=[SimpleNamespace(refusal=refusal)])]
    return SimpleNamespace(
        output_parsed=parsed,
        output_text=text,
        id=response_id,
        model=model,
        status=status,
        usage=usage,
        output=output,
    )


def fake_embedding_response(
    vectors: Sequence[Sequence[float]],
    *,
    indexes: Sequence[int] | None = None,
    model: str = _DEFAULT_MODEL,
    usage: dict[str, Any] | None = None,
) -> Any:
    """A stand-in for ``embeddings.create``.

    ``indexes`` defaults to ``0..n-1``. Pass it explicitly to build the
    responses alignment must survive: shuffled, duplicated, or out of range.
    """
    order = list(range(len(vectors))) if indexes is None else list(indexes)
    data = [
        SimpleNamespace(index=order[i], embedding=list(vector))
        for i, vector in enumerate(vectors)
    ]
    return SimpleNamespace(data=data, model=model, usage=usage)


def text_delta_event(delta: str) -> Any:
    """One ``response.output_text.delta`` event."""
    return SimpleNamespace(type="response.output_text.delta", delta=delta)


def stream_error_event(code: str | None = None) -> Any:
    """One SSE ``error`` event — HTTP 200 already happened."""
    return SimpleNamespace(type="error", code=code)


def stream_failed_event(code: str | None = None) -> Any:
    """One ``response.failed`` event carrying the provider's error code."""
    return SimpleNamespace(
        type="response.failed",
        response=SimpleNamespace(error=SimpleNamespace(code=code)),
    )


class _FakeStream:
    """A synchronous event stream that records whether it was closed."""

    def __init__(self, events: Iterable[Any]) -> None:
        self._events = list(events)
        self.closed = False

    def __iter__(self) -> Any:
        for event in self._events:
            if isinstance(event, BaseException):
                raise event
            yield event

    def close(self) -> None:
        self.closed = True


class _FakeAsyncStream:
    """The asyncio twin, whose ``close`` is a coroutine on purpose."""

    def __init__(self, events: Iterable[Any]) -> None:
        self._events = list(events)
        self._position = 0
        self.closed = False

    def __aiter__(self) -> "_FakeAsyncStream":
        return self

    async def __anext__(self) -> Any:
        if self._position >= len(self._events):
            raise StopAsyncIteration
        event = self._events[self._position]
        self._position += 1
        if isinstance(event, BaseException):
            raise event
        return event

    async def close(self) -> None:
        self.closed = True


class _Queue:
    """Pops scripted outcomes in order and raises the ones that are errors."""

    def __init__(self, items: Iterable[Any], what: str) -> None:
        self._items = list(items)
        self._what = what

    def take(self) -> Any:
        if not self._items:
            raise AssertionError(f"the fake client has no {self._what} left to return")
        item = self._items.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    def __len__(self) -> int:
        return len(self._items)


class FakeClient:
    """An offline stand-in shaped like the OpenAI client, for the sync path.

    Args:
        responses: Objects returned by ``responses.create``/``parse``, in
            order. An exception in the sequence is raised instead.
        embeddings: Same, for ``embeddings.create``.
        streams: One sequence of events per streaming call. An exception
            inside a sequence is raised mid-iteration, which is how a failure
            *after* HTTP 200 is reproduced.

    Attributes:
        requests: Every call's kwargs, in order, each with a ``kind`` key.
        streams_opened: The stream objects handed out, so a test can assert
            they were closed.
        closed: Whether ``close()`` was called.
    """

    def __init__(
        self,
        *,
        responses: Iterable[Any] = (),
        embeddings: Iterable[Any] = (),
        streams: Iterable[Iterable[Any]] = (),
    ) -> None:
        self.requests: list[dict[str, Any]] = []
        self.streams_opened: list[Any] = []
        self.closed = False
        self._responses = _Queue(responses, "responses")
        self._embeddings = _Queue(embeddings, "embeddings")
        self._streams = _Queue([list(s) for s in streams], "streams")
        self.responses = SimpleNamespace(create=self._create, parse=self._parse)
        self.embeddings = SimpleNamespace(create=self._embed)

    def _record(self, kind: str, kwargs: dict[str, Any]) -> None:
        self.requests.append(dict(kwargs, kind=kind))

    def _create(self, **kwargs: Any) -> Any:
        self._record("responses.create", kwargs)
        if kwargs.get("stream"):
            stream = _FakeStream(self._streams.take())
            self.streams_opened.append(stream)
            return stream
        return self._responses.take()

    def _parse(self, **kwargs: Any) -> Any:
        self._record("responses.parse", kwargs)
        return self._responses.take()

    def _embed(self, **kwargs: Any) -> Any:
        self._record("embeddings.create", kwargs)
        return self._embeddings.take()

    def close(self) -> None:
        self.closed = True


class FakeAsyncClient(FakeClient):
    """The asyncio twin of :class:`FakeClient`; every call site is awaited."""

    def __init__(
        self,
        *,
        responses: Iterable[Any] = (),
        embeddings: Iterable[Any] = (),
        streams: Iterable[Iterable[Any]] = (),
    ) -> None:
        super().__init__(responses=responses, embeddings=embeddings, streams=streams)
        self.responses = SimpleNamespace(create=self._acreate, parse=self._aparse)
        self.embeddings = SimpleNamespace(create=self._aembed)

    async def _acreate(self, **kwargs: Any) -> Any:
        self._record("responses.create", kwargs)
        if kwargs.get("stream"):
            stream = _FakeAsyncStream(self._streams.take())
            self.streams_opened.append(stream)
            return stream
        return self._responses.take()

    async def _aparse(self, **kwargs: Any) -> Any:
        self._record("responses.parse", kwargs)
        return self._responses.take()

    async def _aembed(self, **kwargs: Any) -> Any:
        self._record("embeddings.create", kwargs)
        return self._embeddings.take()

    async def close(self) -> None:
        self.closed = True


__all__ = [
    "FakeAsyncClient",
    "FakeClient",
    "fake_embedding_response",
    "fake_parsed_response",
    "fake_text_response",
    "stream_error_event",
    "stream_failed_event",
    "text_delta_event",
]
