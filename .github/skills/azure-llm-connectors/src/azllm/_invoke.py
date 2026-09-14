"""Request shaping and stream-event handling, shared by both connectors.

WHY THIS EXISTS
---------------
The sync and async connectors differ only in ``await``. Everything that can
be got wrong — which key holds the deployment name, which convenience
defaults apply, which SSE events mean the call has already failed — is
decided once, here, so the two code paths cannot drift.

THE STREAM TRAP
---------------
A streaming Responses call returns HTTP 200 as soon as the first byte is
written. A content filter trip, a mid-flight capacity failure or a model
error arrives *inside* the stream as an ``error`` or ``response.failed``
event. Code that iterates deltas and ignores event types treats those as an
empty answer and reports success. :func:`stream_delta` refuses to.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from azllm.config import FoundryConfig
from azllm.deployments import (
    DEFAULT_EMBEDDING_DEPLOYMENT,
    MAX_EMBEDDING_INPUTS,
    embedding_deployment,
)
from azllm.errors import ConfigError, stream_error

# Options the convenience helpers own. A caller who needs to set these is
# using the wrong method and should call ``respond``/``stream_events``.
_RESERVED_CONVENIENCE_OPTIONS = frozenset({"model", "stream", "input"})

# Same idea for ``embed``: these three are arguments of the method, so
# passing them again as options is an ambiguity, not a preference.
_RESERVED_EMBEDDING_OPTIONS = frozenset({"model", "input", "dimensions"})

_TEXT_DELTA_EVENT = "response.output_text.delta"
_ERROR_EVENT = "error"
_FAILED_EVENT = "response.failed"


def _field(obj: Any, name: str) -> Any:
    """Read ``name`` from a pydantic event model or a plain dict alike."""
    if isinstance(obj, Mapping):
        return obj.get(name)
    return getattr(obj, name, None)


def resolve_deployment(config: FoundryConfig, deployment: str | None) -> str:
    """Per-call override, falling back to the configured default."""
    if deployment is None:
        return config.deployment
    value = deployment.strip()
    if not value:
        raise ConfigError("deployment override is blank; pass None to use the configured default")
    return value


def convenience_request(
    config: FoundryConfig,
    *,
    prompt: str,
    deployment: str | None,
    instructions: str | None,
    options: dict[str, Any],
    store_default: bool = False,
) -> dict[str, Any]:
    """Build the kwargs for ``responses.create``/``parse`` from a prompt.

    ``store`` defaults to False: server-side retention of prompt and
    completion is a data-residency decision, not a default a convenience
    method should make on the caller's behalf. Pass ``store=True``
    explicitly when chaining with ``previous_response_id``.

    Arbitrary Responses API options pass straight through, so ``tools``,
    ``reasoning``, ``previous_response_id``, ``include``, ``metadata`` and
    anything the API adds next are never blocked by this library.
    """
    clashes = _RESERVED_CONVENIENCE_OPTIONS & set(options)
    if clashes:
        raise ConfigError(
            "these options are set by the method itself: "
            f"{', '.join(sorted(clashes))}; use respond()/stream_events() for full control"
        )

    request: dict[str, Any] = {
        "model": resolve_deployment(config, deployment),
        "input": prompt,
        "store": store_default,
    }
    if instructions is not None:
        request["instructions"] = instructions
    if config.default_max_output_tokens is not None:
        request["max_output_tokens"] = config.default_max_output_tokens
    request.update(options)
    return request


def raw_request(config: FoundryConfig, options: dict[str, Any]) -> dict[str, Any]:
    """Build kwargs for a raw Responses call, defaulting only the deployment."""
    request = dict(options)
    model = request.get("model")
    if model is None:
        request["model"] = config.deployment
    elif not str(model).strip():
        raise ConfigError("model is blank; omit it to use the configured deployment")
    return request


# ------------------------------------------------------------- embeddings


def resolve_embedding_deployment(config: FoundryConfig, deployment: str | None) -> str:
    """Decide which deployment an embedding call targets.

    Precedence: the per-call override, then the configured deployment *when
    it is itself a known embedding deployment*, then
    :data:`~azllm.deployments.DEFAULT_EMBEDDING_DEPLOYMENT`.

    The middle rule is what makes ``connect(embedding_config(...)).embed(...)``
    honour the config, and the fall-through is why a connector configured for
    chat never sends an embedding request to a chat deployment — that 404
    reads like a typo and costs an afternoon.
    """
    if deployment is None:
        if embedding_deployment(config.deployment) is not None:
            return config.deployment
        return DEFAULT_EMBEDDING_DEPLOYMENT
    value = deployment.strip()
    if not value:
        raise ConfigError("deployment override is blank; pass None to use the default")
    return value


def _validate_text(value: Any, *, where: str) -> str:
    if not isinstance(value, str):
        raise ConfigError(f"{where} must be a string, got {type(value).__name__}")
    if not value.strip():
        raise ConfigError(f"{where} is empty; an embedding of nothing is not defined")
    return value


def _snapshot_inputs(value: Any) -> list[str]:
    """Copy an iterable of strings into a list this call owns.

    A generator can only be consumed once and a caller's list can be mutated
    between validation and transport; either turns into vectors that do not
    correspond to the text the caller believes they embedded. The copy is
    taken before anything is checked.
    """
    if isinstance(value, (bytes, bytearray, Mapping)):
        raise ConfigError(
            "input must be a string or a sequence of strings, "
            f"got {type(value).__name__}"
        )
    if not isinstance(value, Iterable):
        raise ConfigError(
            "input must be a string or a sequence of strings, "
            f"got {type(value).__name__}"
        )
    items = list(value)
    if not items:
        raise ConfigError("input sequence is empty; there is nothing to embed")
    if len(items) > MAX_EMBEDDING_INPUTS:
        raise ConfigError(
            f"input sequence has {len(items)} entries; the service accepts at most "
            f"{MAX_EMBEDDING_INPUTS} per request"
        )
    return [_validate_text(item, where=f"input[{i}]") for i, item in enumerate(items)]


@dataclass(frozen=True)
class EmbeddingRequest:
    """The validated kwargs for one ``embeddings.create`` call."""

    kwargs: dict[str, Any]
    deployment: str
    count: int


def embedding_request(
    config: FoundryConfig,
    *,
    input: Any,
    deployment: str | None,
    dimensions: int | None,
    options: dict[str, Any],
) -> EmbeddingRequest:
    """Shape and validate an embedding call before any socket is opened.

    Everything decidable from the values in hand is decided here: the input
    type, empty strings, an empty batch, a batch over
    :data:`MAX_EMBEDDING_INPUTS`, and a non-positive ``dimensions``. Token
    counts are *not* checked — that needs a tokenizer, character count does
    not prove it, and the service reports it as a 400.

    Arbitrary embedding options (``encoding_format``, ``user``,
    ``extra_headers``, ...) pass through untouched.
    """
    clashes = _RESERVED_EMBEDDING_OPTIONS & set(options)
    if clashes:
        raise ConfigError(
            "these options are set by the method itself: "
            f"{', '.join(sorted(clashes))}; use embed_raw() for full control"
        )

    target = resolve_embedding_deployment(config, deployment)

    if isinstance(input, str):
        payload: Any = _validate_text(input, where="input")
        count = 1
    else:
        items = _snapshot_inputs(input)
        payload = items
        count = len(items)

    request: dict[str, Any] = {"model": target, "input": payload}

    if dimensions is not None:
        if not isinstance(dimensions, int) or isinstance(dimensions, bool):
            raise ConfigError("dimensions must be an int or None")
        if dimensions <= 0:
            raise ConfigError(f"dimensions must be a positive int, got {dimensions}")
        request["dimensions"] = dimensions

    request.update(options)
    return EmbeddingRequest(kwargs=request, deployment=target, count=count)


def embedding_raw_request(config: FoundryConfig, options: dict[str, Any]) -> dict[str, Any]:
    """Build kwargs for a raw embeddings call, defaulting only the deployment."""
    request = dict(options)
    model = request.get("model")
    if model is None:
        request["model"] = resolve_embedding_deployment(config, None)
    elif not str(model).strip():
        raise ConfigError("model is blank; omit it to use the default embedding deployment")
    return request


def stream_delta(event: Any, *, deployment: str) -> str | None:
    """Return the text delta for ``event``, or None if it carries no text.

    Raises:
        LlmError: when the event is the provider signalling failure inside
            an already-successful HTTP response.
    """
    event_type = _field(event, "type")

    if event_type == _TEXT_DELTA_EVENT:
        delta = _field(event, "delta")
        return delta if isinstance(delta, str) else ""

    if event_type == _ERROR_EVENT:
        raise stream_error(code=_str_or_none(_field(event, "code")), deployment=deployment)

    if event_type == _FAILED_EVENT:
        response = _field(event, "response")
        error = _field(response, "error") if response is not None else None
        code = _str_or_none(_field(error, "code")) if error is not None else None
        raise stream_error(code=code, deployment=deployment, failed=True)

    return None


def _str_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None
