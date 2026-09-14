"""The one failure type callers catch — sanitised, classified, and caused.

WHY THIS EXISTS
---------------
An ``openai.APIStatusError`` carries the provider's HTTP response object and
its decoded body. Both routinely contain the prompt, a content-filter
excerpt of the prompt, or a fragment of the completion. Letting that
exception escape into an application means every log line, every error
tracker and every 500-page renderer becomes a place model input can leak.

:class:`ModelError` is what leaves this package instead. It carries the facts
an operator needs to act — category, HTTP status, whether a retry can help,
the provider request id — and nothing that came out of the model. The
original exception is preserved as ``__cause__``, so a debugger still has
everything; a formatter that prints ``str(exc)`` does not.

DEPENDENCIES
------------
Standard library. ``openai`` is imported lazily, inside :func:`classify`, so
this module classifies correctly in a process where the SDK is absent.
"""

from __future__ import annotations

from typing import Any, Literal

ErrorCategory = Literal[
    "config",  # caller built an impossible configuration; never retryable
    "auth",  # 401/403, or the credential itself refused to issue a token
    "not_found",  # 404 — on Azure OpenAI this is almost always a bad deployment
    "bad_request",  # 400/422 — malformed request or rejected content
    "rate_limit",  # 429 — capacity, retry after backoff
    "timeout",  # client-side deadline elapsed
    "connection",  # DNS, TLS, reset; no HTTP status was ever seen
    "server",  # 5xx
    "stream",  # the SSE stream itself reported a failure mid-flight
    "unknown",  # classified nowhere else; treated as non-retryable
]

# Retrying these can succeed with no change to the request. Everything else
# needs the caller or the configuration to change first.
_RETRYABLE: frozenset[str] = frozenset({"rate_limit", "timeout", "connection", "server"})


class ModelError(Exception):
    """A provider failure, stripped of provider content.

    Attributes:
        category: Stable machine-readable class of failure, see
            :data:`ErrorCategory`. Safe to branch on; the message is not.
        status_code: HTTP status when one was received, else None.
        retryable: True when retrying the identical request may succeed.
        request_id: Provider correlation id (``x-request-id``) when present.
            This is the value to quote in a support case.
        deployment: Deployment name the call targeted, when known.
        code: Short provider error code (for example ``"content_filter"``)
            when the provider supplied one. Codes are enumerated identifiers,
            not free text, so they do not carry prompt content.
    """

    def __init__(
        self,
        message: str,
        *,
        category: ErrorCategory = "unknown",
        status_code: int | None = None,
        retryable: bool | None = None,
        request_id: str | None = None,
        deployment: str | None = None,
        code: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.category: ErrorCategory = category
        self.status_code = status_code
        self.retryable = category in _RETRYABLE if retryable is None else retryable
        self.request_id = request_id
        self.deployment = deployment
        self.code = code

    def __str__(self) -> str:
        parts = [self.message, f"category={self.category}"]
        if self.status_code is not None:
            parts.append(f"status={self.status_code}")
        parts.append(f"retryable={self.retryable}")
        if self.deployment:
            parts.append(f"deployment={self.deployment}")
        if self.code:
            parts.append(f"code={self.code}")
        if self.request_id:
            parts.append(f"request_id={self.request_id}")
        return " ".join(parts)

    def __repr__(self) -> str:
        return f"ModelError({self!s})"


class ConfigError(ModelError):
    """The configuration cannot produce a working client. Never retryable."""

    def __init__(self, message: str) -> None:
        super().__init__(message, category="config", retryable=False)


def _status_category(status: int | None) -> ErrorCategory:
    if status is None:
        return "unknown"
    if status in (401, 403):
        return "auth"
    if status == 404:
        return "not_found"
    if status == 429:
        return "rate_limit"
    if status in (400, 422):
        return "bad_request"
    if 500 <= status <= 599:
        return "server"
    if 400 <= status <= 499:
        return "bad_request"
    return "unknown"


def _short_code(exc: Any) -> str | None:
    """Read the provider's error *code* only — never its message or body."""
    code = getattr(exc, "code", None)
    if isinstance(code, str) and code and len(code) <= 64 and "\n" not in code:
        return code
    return None


def classify(exc: BaseException, *, deployment: str | None = None) -> ModelError:
    """Translate a provider or transport exception into a :class:`ModelError`.

    The returned error never embeds ``str(exc)``: provider messages quote the
    offending input. Only the exception *type*, the HTTP status, the error
    code and the request id cross the boundary.

    Args:
        exc: The exception raised by the OpenAI SDK or the credential.
        deployment: Deployment the call targeted, recorded for triage.

    Returns:
        A :class:`ModelError`. The caller is expected to ``raise ... from exc``,
        which keeps the original available as ``__cause__`` for a debugger.
    """
    if isinstance(exc, ModelError):
        return exc

    # Imported lazily so this module can be used (and unit tested) in a
    # process where the SDK is not installed at all.
    try:
        import openai
    except Exception:
        openai = None  # type: ignore[assignment]

    status: int | None = getattr(exc, "status_code", None)
    request_id: str | None = getattr(exc, "request_id", None)
    code = _short_code(exc)

    if openai is not None:
        if isinstance(exc, openai.APITimeoutError):
            return ModelError(
                "Request to the model deployment timed out.",
                category="timeout",
                deployment=deployment,
                request_id=request_id,
            )
        if isinstance(exc, openai.APIConnectionError):
            return ModelError(
                "Could not reach the model endpoint.",
                category="connection",
                deployment=deployment,
                request_id=request_id,
            )
        if isinstance(exc, openai.APIStatusError):
            category = _status_category(status)
            return ModelError(
                _status_message(category),
                category=category,
                status_code=status,
                request_id=request_id,
                deployment=deployment,
                code=code,
            )
        if isinstance(exc, openai.APIError):
            return ModelError(
                "The model provider returned an unusable response.",
                category="unknown",
                status_code=status,
                request_id=request_id,
                deployment=deployment,
                code=code,
            )

    # Credential failures arrive as azure-core ``ClientAuthenticationError``
    # or as whatever a caller-supplied token provider raised. Matched by name
    # so the identity library does not have to be imported to classify.
    if type(exc).__name__ in {"ClientAuthenticationError", "CredentialUnavailableError"}:
        return ModelError(
            "Could not acquire an Entra token for the model endpoint.",
            category="auth",
            retryable=False,
            deployment=deployment,
        )

    if isinstance(exc, TimeoutError):
        return ModelError("Operation timed out.", category="timeout", deployment=deployment)

    return ModelError(
        f"Unexpected {type(exc).__name__} while calling the model deployment.",
        category="unknown",
        status_code=status,
        request_id=request_id,
        deployment=deployment,
    )


def _status_message(category: ErrorCategory) -> str:
    return {
        "auth": (
            "Authentication or authorization failed. The identity needs a "
            "data-plane role on the model account."
        ),
        "not_found": (
            "The deployment was not found. On Azure OpenAI the model field is "
            "the deployment name, not the model family name."
        ),
        "rate_limit": "The deployment is at capacity (429).",
        "bad_request": "The provider rejected the request.",
        "server": "The provider reported a server-side failure.",
    }.get(category, "The provider returned an error status.")


def stream_error(
    *,
    code: str | None,
    deployment: str | None = None,
    failed: bool = False,
) -> ModelError:
    """Build the error for a provider failure signalled inside a live stream.

    A streamed response opens with HTTP 200 and can still fail three tokens
    later. The SSE ``error`` and ``response.failed`` events are the only
    signal, and the accompanying message quotes the input, so only the code
    is carried across. See GOTCHAS.md, G3.
    """
    what = "The streamed response failed" if failed else "The response stream reported an error"
    return ModelError(
        f"{what} after the connection was established.",
        category="stream",
        retryable=False,
        deployment=deployment,
        code=code,
    )


__all__ = ["ConfigError", "ErrorCategory", "ModelError", "classify", "stream_error"]
