"""Retry and model fallback — what to do when the model refuses.

Module role:
    Classifies a model-side failure and decides whether to wait, how long, and
    when to give up on a deployment and move to the next one.

Why classify at all:
    The three failures look identical to a naive retry loop and want opposite
    treatment. A rate limit wants a long wait and the *same* request. A
    transient 5xx wants a short backoff. A content-filter or auth rejection
    wants no retry at all — retrying it burns quota to receive the same refusal,
    and on a filter it can look like an attempt to evade the filter.

Why text matching:
    The SDK surfaces service errors as exceptions whose types vary by transport
    and version, but whose text carries the status code and reason. Matching on
    type is more elegant and less durable. This is a deliberate trade and it is
    documented in CONTRACT.md so a reimplementation does not "fix" it.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Awaitable, Callable
from typing import Any

from ._config import FoundryConfig

logger = logging.getLogger(__name__)

# Lowercase substrings. Ordered by how often each was the actual cause.
_RATE_LIMIT_PATTERNS = (
    "429", "rate limit", "retry after", "throttl", "token rate limit",
    "peak load", "maximum usage",
)
_FATAL_PATTERNS = (
    "content_filter", "content management policy", "unauthorized", "forbidden",
    "401", "403",
)
_TRANSIENT_PATTERNS = (
    "sorry, something went wrong", "internal server error",
    "502", "503", "504", "service unavailable", "gateway timeout",
)

# Retry-after clamp. Below the floor a "retry after 1s" storms the endpoint that
# is already shedding load; above the ceiling a turn hangs long enough that the
# caller has given up and the wait is spent for nothing.
_RETRY_AFTER_FLOOR = 5
_RETRY_AFTER_CEILING = 60
_BACKOFF_CEILING = 30.0

_RETRY_AFTER_RE = re.compile(r"retry\s*(?:after|in)\s*(\d+)")
_SECONDS_RE = re.compile(r"(\d+)\s*second")


def is_rate_limit(exc: BaseException) -> bool:
    """True when the service is shedding load rather than refusing the request."""
    text = str(exc).lower()
    return any(p in text for p in _RATE_LIMIT_PATTERNS)


def is_fatal(exc: BaseException) -> bool:
    """True when retrying cannot help: content filter, auth, authorization."""
    text = str(exc).lower()
    return any(p in text for p in _FATAL_PATTERNS)


def is_transient(exc: BaseException) -> bool:
    """True for server-side errors that commonly succeed on a second attempt."""
    text = str(exc).lower()
    return any(p in text for p in _TRANSIENT_PATTERNS)


def classify(exc: BaseException) -> str:
    """Return ``"fatal"``, ``"rate_limit"``, ``"transient"`` or ``"unknown"``.

    Fatal is checked first: a 403 whose body happens to mention throttling is
    still a 403, and treating it as a rate limit produces a retry loop that
    never terminates for the right reason.
    """
    if is_fatal(exc):
        return "fatal"
    if is_rate_limit(exc):
        return "rate_limit"
    if is_transient(exc):
        return "transient"
    return "unknown"


def parse_retry_seconds(error_text: str, default: int = 15) -> int:
    """Extract a retry-after hint from error text, clamped to a sane range."""
    text = error_text.lower()
    match = _RETRY_AFTER_RE.search(text) or _SECONDS_RE.search(text)
    if match:
        return max(_RETRY_AFTER_FLOOR, min(_RETRY_AFTER_CEILING, int(match.group(1))))
    return default


def should_retry(
    exc: BaseException, attempt: int, max_retries: int
) -> tuple[bool, float]:
    """Decide whether to retry ``exc``, and how long to wait first.

    Args:
        exc: The failure.
        attempt: Zero-based attempt index that just failed.
        max_retries: Total attempts allowed for this deployment.

    Returns:
        ``(retry, delay_seconds)``. Unknown errors are retried with backoff:
        the failure modes seen in practice are overwhelmingly transient, and a
        genuinely permanent unknown error costs at most ``max_retries`` attempts
        before the caller moves on.
    """
    if is_fatal(exc):
        return False, 0.0
    if attempt >= max_retries - 1:
        return False, 0.0
    if is_rate_limit(exc):
        return True, float(parse_retry_seconds(str(exc)))
    return True, min(2.0 ** attempt * 2.0, _BACKOFF_CEILING)


async def run_with_fallback(
    run: Callable[[str], Awaitable[Any]],
    config: FoundryConfig,
    *,
    context: str = "agent_turn",
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> Any:
    """Run ``run(model_deployment)``, retrying and falling back across models.

    Walks ``config.model_queue()``. Within a deployment it retries per
    :func:`should_retry`; when the attempts are exhausted it moves to the next
    deployment and starts its attempt count fresh — a deployment that is at
    capacity does not consume the budget of one that is not.

    A fatal error aborts everything immediately, including the fallbacks: a
    content-filter rejection or an authorization failure will be identical on
    every deployment in the project, so trying them is pure latency.

    Args:
        run: Async callable taking the deployment name and doing the work.
        config: Supplies the queue and the per-model attempt budget.
        context: Label for the retry logs.
        sleep: Injected for tests, which must not actually wait.

    Returns:
        Whatever ``run`` returned.

    Raises:
        The last exception, when every deployment is exhausted.
    """
    queue = config.model_queue()
    last: BaseException | None = None

    for model in queue:
        for attempt in range(config.max_retries):
            try:
                return await run(model)
            except Exception as exc:
                last = exc
                kind = classify(exc)
                retry, delay = should_retry(exc, attempt, config.max_retries)
                logger.warning(
                    "foundry.retry: context=%s model=%s attempt=%d/%d kind=%s "
                    "delay=%.1fs error=%s",
                    context, model, attempt + 1, config.max_retries, kind,
                    delay, str(exc)[:200],
                )
                if kind == "fatal":
                    raise
                if not retry:
                    break
                await sleep(delay)

    if last is not None:
        logger.error(
            "foundry.retry.exhausted: context=%s models=%s", context, queue
        )
        raise last
    raise RuntimeError(
        "run_with_fallback: model queue was empty — FoundryConfig guarantees a "
        "primary deployment, so this means the config was bypassed."
    )


__all__ = [
    "is_rate_limit", "is_fatal", "is_transient", "classify",
    "parse_retry_seconds", "should_retry", "run_with_fallback",
]
