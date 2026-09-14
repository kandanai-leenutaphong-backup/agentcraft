"""Request shaping and stream-event handling, shared by both clients.

WHY THIS EXISTS
---------------
The sync and async clients differ only in ``await``. Everything that can be
got wrong — which key holds the deployment name, which convenience defaults
apply, which SSE events mean the call has already failed — is decided once,
here, so the two code paths cannot drift.

THE STREAM TRAP
---------------
A streaming Responses call returns HTTP 200 as soon as the first byte is
written. A content filter trip, a mid-flight capacity failure or a model
error arrives *inside* the stream as an ``error`` or ``response.failed``
event. Code that iterates deltas and ignores event types treats those as an
empty answer and reports success. :func:`stream_delta` refuses to. See
GOTCHAS.md, G3.

DEPENDENCIES
------------
Standard library only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from modelaccess.config import ENV_PREFIX, ModelConfig
from modelaccess.errors import ConfigError, stream_error

# Options the convenience helpers own. A caller who needs to set these is
# using the wrong method and should call ``respond``/``stream_events``.
_RESERVED_CONVENIENCE_OPTIONS = frozenset({"model", "stream", "input"})

# Same idea for ``embed``: these three are arguments of the method, so
# passing them again as options is an ambiguity, not a preference.
_RESERVED_EMBEDDING_OPTIONS = frozenset({"model", "input", "dimensions"})

_TEXT_DELTA_EVENT = "response.output_text.delta"
_ERROR_EVENT = "error"
_FAILED_EVENT = "response.failed"

# Published Azure OpenAI batch limit for one embeddings request, and the only
# one decidable locally: the token limits need a tokenizer, a character count
# does not prove one, and the service enforces them as a 400.
MAX_EMBEDDING_INPUTS = 2048


def _field(obj: Any, name: str) -> Any:
    """Read ``name`` from a pydantic event model or a plain dict alike."""
    if isinstance(obj, Mapping):
        return obj.get(name)
    return getattr(obj, name, None)


def resolve_deployment(config: ModelConfig, deployment: str | None) -> str:
    """Per-call override, falling back to the configured default."""
    if deployment is None:
        return config.deployment
    value = deployment.strip()
    if not value:
        raise ConfigError("deployment override is blank; pass None to use the configured default")
    return value


def convenience_request(
    config: ModelConfig,
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
    anything the API adds next are never blocked by this package.
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


def raw_request(config: ModelConfig, options: dict[str, Any]) -> dict[str, Any]:
    """Build kwargs for a raw Responses call, defaulting only the deployment."""
    request = dict(options)
    model = request.get("model")
    if model is None:
        request["model"] = config.deployment
    elif not str(model).strip():
        raise ConfigError("model is blank; omit it to use the configured deployment")
    return request


# ------------------------------------------------------------- embeddings


def resolve_embedding_deployment(
    config: ModelConfig,
    deployment: str | None,
    *,
    allow_foreign_account: bool = False,
) -> str:
    """Decide which deployment an embedding call targets, or refuse.

    Precedence: the per-call override, then ``config.embedding_deployment``.
    There is no third rule. Falling back to the chat deployment sends
    ``embeddings.create`` somewhere that cannot serve it, and the 404 reads
    like a misspelled name. See GOTCHAS.md, G6.

    The account check is on the **endpoint**, not on how the name was chosen:
    a per-call ``deployment=`` does not move this client's base URL, so an
    explicit override used to walk straight into the 404 the check exists to
    prevent. ``allow_foreign_account`` is the one documented way past it, and
    it is reachable only through ``embed_raw``.

    Raises:
        ConfigError: when nothing is configured and nothing was passed, or
            when the embedding deployment lives on a different account than
            this client is bound to — one client, one base URL.
    """
    if deployment is None:
        target = config.embedding_deployment
        if not target:
            raise ConfigError(
                "no embedding deployment is configured; set "
                f"{ENV_PREFIX}EMBEDDING_DEPLOYMENT, pass embedding_deployment= to "
                "ModelConfig, or pass deployment= to this call. A chat deployment "
                "cannot serve embeddings."
            )
    else:
        target = deployment.strip()
        if not target:
            raise ConfigError("deployment override is blank; pass None to use the default")

    if not allow_foreign_account and not config.embeddings_are_local:
        raise ConfigError(
            f"embedding deployment {target!r} is hosted on {config.embedding_endpoint!r}, "
            f"not on this client's account {config.endpoint!r}. A deployment is only "
            "reachable through its own account's endpoint — build a second client with "
            "connect(embedding_config(config)). Passing deployment= does not change "
            "this client's base URL; embed_raw(..., allow_foreign_account=True) is the "
            "deliberate escape."
        )
    return target


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
            f"input must be a string or a sequence of strings, got {type(value).__name__}"
        )
    if not isinstance(value, Iterable):
        raise ConfigError(
            f"input must be a string or a sequence of strings, got {type(value).__name__}"
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
    config: ModelConfig,
    *,
    input: Any,
    deployment: str | None,
    dimensions: int | None,
    options: dict[str, Any],
) -> EmbeddingRequest:
    """Shape and validate an embedding call before any socket is opened.

    Everything decidable from the values in hand is decided here: the target
    deployment, the input type, empty strings, an empty batch, a batch over
    :data:`MAX_EMBEDDING_INPUTS`, and a non-positive ``dimensions``. Token
    counts are *not* checked — that needs a tokenizer, character count does
    not prove it, and the service reports it as a 400.
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


def embedding_raw_request(config: ModelConfig, options: dict[str, Any]) -> dict[str, Any]:
    """Build kwargs for a raw embeddings call, defaulting only the deployment.

    ``allow_foreign_account`` is this package's option, not the provider's: it
    is removed from the request and only relaxes the cross-account check.
    """
    request = dict(options)
    escape = request.pop("allow_foreign_account", False)
    if not isinstance(escape, bool):
        raise ConfigError("allow_foreign_account must be a bool")
    model = request.get("model")
    if model is None:
        request["model"] = resolve_embedding_deployment(
            config, None, allow_foreign_account=escape
        )
    elif not str(model).strip():
        raise ConfigError("model is blank; omit it to use the configured embedding deployment")
    else:
        resolve_embedding_deployment(config, str(model), allow_foreign_account=escape)
    return request


def stream_request(config: ModelConfig, options: dict[str, Any]) -> dict[str, Any]:
    """Build kwargs for a raw *streaming* Responses call.

    ``stream`` is the method's own decision. ``stream=True`` is redundant and
    accepted; anything else is a contradiction between what was asked for and
    what the method does, and every other conflicting option in this package
    raises rather than being silently dropped.
    """
    request = raw_request(config, options)
    if "stream" in request and request["stream"] is not True:
        raise ConfigError(
            f"stream={request['stream']!r} contradicts this method, which always "
            "streams; use respond() for a non-streaming call"
        )
    request["stream"] = True
    return request


def stream_delta(event: Any, *, deployment: str) -> str | None:
    """Return the text delta for ``event``, or None if it carries no text.

    Raises:
        ModelError: when the event is the provider signalling failure inside
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


__all__ = [
    "MAX_EMBEDDING_INPUTS",
    "EmbeddingRequest",
    "convenience_request",
    "embedding_raw_request",
    "embedding_request",
    "raw_request",
    "resolve_deployment",
    "resolve_embedding_deployment",
    "stream_delta",
]
