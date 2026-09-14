"""What a convenience call returns — text plus the metadata triage needs.

WHY THIS EXISTS
---------------
``ask()`` returning a bare ``str`` throws away the response id needed to
chain a follow-up turn, the token usage needed to attribute cost, and the
status that distinguishes a complete answer from one truncated at the token
ceiling. :class:`TextResult` keeps all of it, and keeps the untouched
provider object in ``raw`` so nothing is a dead end.

LOGGING
-------
``metadata()`` is the safe projection: identifiers, status and counts, never
the text. Log that. ``__repr__`` shows the text *length*, not the text, so a
stray ``repr()`` in a log line cannot leak a completion.

DEPENDENCIES
------------
Standard library only.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Generic, Sequence, TypeVar

from modelaccess.errors import ConfigError, ModelError

T = TypeVar("T")


def usage_dict(response: Any) -> dict[str, Any]:
    """Extract token usage as a plain dict, tolerating a missing usage block.

    Streamed and cancelled responses may carry no usage at all; a KeyError in
    an accounting path is not worth the precision.
    """
    usage = getattr(response, "usage", None)
    if usage is None:
        return {}
    if isinstance(usage, dict):
        return dict(usage)
    dump = getattr(usage, "model_dump", None)
    if callable(dump):
        try:
            return dict(dump())
        except Exception:
            return {}
    return {
        key: getattr(usage, key)
        for key in ("input_tokens", "output_tokens", "total_tokens", "prompt_tokens")
        if getattr(usage, key, None) is not None
    }


@dataclass(frozen=True)
class TextResult:
    """One completed response, with its identifiers and accounting.

    Attributes:
        text: Concatenated output text. Empty when the model produced only
            tool calls or was cut short before emitting text.
        response_id: Provider id. Pass it as ``previous_response_id`` to
            continue the conversation server-side instead of resending
            history.
        deployment: Deployment name the call targeted.
        model: Model identifier the provider reported, which on Azure echoes
            the deployment or its underlying model depending on the API.
        status: ``completed``, ``incomplete``, ``failed`` — or None when the
            provider omitted it.
        usage: Token counts, empty when the provider reported none.
        raw: The provider response object, untouched.
    """

    text: str
    response_id: str | None
    deployment: str
    model: str | None
    status: str | None
    usage: dict[str, Any] = field(default_factory=dict)
    raw: Any = None

    @property
    def complete(self) -> bool:
        """True when the provider reported the response as finished."""
        return self.status == "completed"

    @property
    def output_tokens(self) -> int | None:
        value = self.usage.get("output_tokens")
        return value if isinstance(value, int) else None

    @property
    def input_tokens(self) -> int | None:
        value = self.usage.get("input_tokens")
        return value if isinstance(value, int) else None

    def metadata(self) -> dict[str, Any]:
        """The projection that is safe to log: no prompt, no completion."""
        return {
            "response_id": self.response_id,
            "deployment": self.deployment,
            "model": self.model,
            "status": self.status,
            "text_chars": len(self.text),
            "usage": dict(self.usage),
        }

    def __repr__(self) -> str:
        return (
            f"TextResult(response_id={self.response_id!r}, deployment={self.deployment!r}, "
            f"status={self.status!r}, text_chars={len(self.text)}, usage={self.usage!r})"
        )

    @classmethod
    def from_response(cls, response: Any, *, deployment: str) -> "TextResult":
        """Build a result from a Responses API object."""
        return cls(
            text=getattr(response, "output_text", "") or "",
            response_id=getattr(response, "id", None),
            deployment=deployment,
            model=getattr(response, "model", None),
            status=getattr(response, "status", None),
            usage=usage_dict(response),
            raw=response,
        )


@dataclass(frozen=True)
class ParsedResult(Generic[T]):
    """A structured response: the validated object, plus the same metadata.

    ``parsed`` is None when the model returned a refusal or stopped before
    emitting a complete object; check it rather than assuming. A refusal is
    not an exception — the call succeeded and the answer is "no". See
    GOTCHAS.md, G7.
    """

    parsed: T | None
    text: str
    response_id: str | None
    deployment: str
    model: str | None
    status: str | None
    refusal: str | None = None
    usage: dict[str, Any] = field(default_factory=dict)
    raw: Any = None

    @property
    def complete(self) -> bool:
        return self.status == "completed"

    @property
    def refused(self) -> bool:
        """True when the model declined rather than producing the object."""
        return self.parsed is None and self.refusal is not None

    def metadata(self) -> dict[str, Any]:
        """The projection that is safe to log: no prompt, no parsed content.

        ``refusal`` is reported as a boolean, not as its text: a refusal
        message can quote the input it refused.
        """
        return {
            "response_id": self.response_id,
            "deployment": self.deployment,
            "model": self.model,
            "status": self.status,
            "parsed": self.parsed is not None,
            "refused": self.refused,
            "text_chars": len(self.text),
            "usage": dict(self.usage),
        }

    def __repr__(self) -> str:
        return (
            f"ParsedResult(response_id={self.response_id!r}, deployment={self.deployment!r}, "
            f"status={self.status!r}, parsed={self.parsed is not None}, "
            f"refused={self.refused}, usage={self.usage!r})"
        )

    @classmethod
    def from_response(cls, response: Any, *, deployment: str) -> "ParsedResult[Any]":
        return cls(
            parsed=getattr(response, "output_parsed", None),
            text=getattr(response, "output_text", "") or "",
            response_id=getattr(response, "id", None),
            deployment=deployment,
            model=getattr(response, "model", None),
            status=getattr(response, "status", None),
            refusal=_first_refusal(response),
            usage=usage_dict(response),
            raw=response,
        )


def _first_refusal(response: Any) -> str | None:
    """The refusal string the SDK surfaces, or None.

    Walked defensively: the shape is ``output[].content[].refusal`` and any
    level of it may be missing on a response that did not refuse.
    """
    output = getattr(response, "output", None) or []
    if isinstance(output, (str, bytes)) or not isinstance(output, Sequence):
        return None
    for item in output:
        content = getattr(item, "content", None) or []
        if isinstance(content, (str, bytes)) or not isinstance(content, Sequence):
            continue
        for part in content:
            refusal = getattr(part, "refusal", None)
            if isinstance(refusal, str) and refusal:
                return refusal
    return None


def _item_field(item: Any, name: str) -> Any:
    """Read a field from a pydantic ``Embedding`` or the equivalent dict."""
    if isinstance(item, dict):
        return item.get(name)
    return getattr(item, name, None)


def _malformed(reason: str, *, deployment: str) -> ModelError:
    """A structural complaint about the response — no vector, no input, no text."""
    return ModelError(
        f"The embedding response was malformed: {reason}.",
        category="unknown",
        retryable=False,
        deployment=deployment,
    )


def _as_float(value: Any) -> float | None:
    """Coerce a JSON number to float; reject bool, non-numbers and NaN/inf.

    A vector component of exactly 0 or 1 arrives as an integer from some JSON
    decoders, so integers are accepted. ``bool`` is an ``int`` in Python and
    is not a number the provider can have sent.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


@dataclass(frozen=True)
class EmbeddingResult:
    """The vectors for one embedding call, in the order of the inputs.

    ``vectors[i]`` is the embedding of input ``i``: the provider's ``index``
    field is what establishes that correspondence, and it is verified rather
    than assumed. A response that cannot be aligned raises instead of
    returning vectors silently attached to the wrong text. See GOTCHAS.md, G8.

    Attributes:
        vectors: One tuple of floats per input, in input order. Immutable, so
            a shared result cannot be edited underneath another caller.
        deployment: Deployment name the call targeted.
        model: Model identifier the provider reported.
        usage: Token counts, empty when the provider reported none.
        raw: The provider response object, untouched.
    """

    vectors: tuple[tuple[float, ...], ...]
    deployment: str
    model: str | None
    usage: dict[str, Any] = field(default_factory=dict)
    raw: Any = None

    @property
    def vector(self) -> tuple[float, ...]:
        """The single vector — only when exactly one input was embedded.

        Raises:
            ConfigError: for a batch. ``vectors[0]`` on a batch is a silent
                way to embed twelve documents and index the first.
        """
        if len(self.vectors) != 1:
            raise ConfigError(
                f"this result holds {len(self.vectors)} vectors; "
                ".vector is only defined for a single input — use .vectors"
            )
        return self.vectors[0]

    @property
    def count(self) -> int:
        """How many vectors came back — equal to the number of inputs sent."""
        return len(self.vectors)

    @property
    def dimensions(self) -> int | None:
        """Length of each vector, or None when there are no vectors."""
        return len(self.vectors[0]) if self.vectors else None

    def metadata(self) -> dict[str, Any]:
        """The projection that is safe to log: no input, no vectors."""
        return {
            "deployment": self.deployment,
            "model": self.model,
            "count": self.count,
            "dimensions": self.dimensions,
            "usage": dict(self.usage),
        }

    def __repr__(self) -> str:
        return (
            f"EmbeddingResult(deployment={self.deployment!r}, model={self.model!r}, "
            f"count={self.count}, dimensions={self.dimensions}, usage={self.usage!r})"
        )

    @classmethod
    def from_response(
        cls,
        response: Any,
        *,
        deployment: str,
        expected_count: int,
    ) -> "EmbeddingResult":
        """Validate and align a ``CreateEmbeddingResponse``.

        Raises:
            ModelError: ``category="unknown"`` when the response cannot be
                aligned to the inputs — a missing, duplicated or out-of-range
                index, a wrong number of vectors, a non-numeric or non-finite
                component, or vectors of differing length.
            ConfigError: when the vectors are base64 strings, which means
                ``encoding_format="base64"`` was requested.
        """
        data = _item_field(response, "data")
        if isinstance(data, (str, bytes)) or not isinstance(data, Sequence):
            raise _malformed("the response carried no list of vectors", deployment=deployment)
        if len(data) != expected_count:
            raise _malformed(
                f"the response returned {len(data)} vectors for {expected_count} inputs",
                deployment=deployment,
            )

        slots: list[tuple[float, ...] | None] = [None] * expected_count
        width: int | None = None

        for position, item in enumerate(data):
            index = _item_field(item, "index")
            if isinstance(index, bool) or not isinstance(index, int):
                raise _malformed(f"item {position} has no integer index", deployment=deployment)
            if not 0 <= index < expected_count:
                raise _malformed(
                    f"item {position} reports index {index}, outside 0..{expected_count - 1}",
                    deployment=deployment,
                )
            if slots[index] is not None:
                raise _malformed(f"index {index} appears twice", deployment=deployment)

            raw_vector = _item_field(item, "embedding")
            if isinstance(raw_vector, str):
                raise ConfigError(
                    "the provider returned base64 vectors; embed() decodes float vectors "
                    "only — omit encoding_format, or use embed_raw() to handle base64"
                )
            if isinstance(raw_vector, bytes) or not isinstance(raw_vector, Sequence):
                raise _malformed(f"item at index {index} carries no vector", deployment=deployment)
            if not raw_vector:
                raise _malformed(f"the vector at index {index} is empty", deployment=deployment)

            components: list[float] = []
            for component in raw_vector:
                number = _as_float(component)
                if number is None:
                    raise _malformed(
                        f"the vector at index {index} contains a non-finite or non-numeric value",
                        deployment=deployment,
                    )
                components.append(number)

            if width is None:
                width = len(components)
            elif len(components) != width:
                raise _malformed(
                    f"vector lengths differ ({width} then {len(components)})",
                    deployment=deployment,
                )
            slots[index] = tuple(components)

        missing = [i for i, slot in enumerate(slots) if slot is None]
        if missing:
            raise _malformed(
                f"no vector was returned for index {missing[0]}", deployment=deployment
            )

        return cls(
            vectors=tuple(slot for slot in slots if slot is not None),
            deployment=deployment,
            model=_item_field(response, "model"),
            usage=usage_dict(response),
            raw=response,
        )


__all__ = ["EmbeddingResult", "ParsedResult", "TextResult", "usage_dict"]
