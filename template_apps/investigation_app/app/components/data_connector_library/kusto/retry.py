"""Retry policy.

Throttling and transient service faults retry with exponential backoff and full
jitter. Client faults — bad syntax, missing table, unauthorised — never retry,
because retrying them burns the deadline and hides the real error.
"""

from __future__ import annotations

import logging
import random
import time
from typing import Callable, TypeVar

from azure.kusto.data.exceptions import (
    KustoApiError,
    KustoAuthenticationError,
    KustoClientError,
    KustoNetworkError,
    KustoServiceError,
    KustoThrottlingError,
)

from .errors import AdxAuthError, AdxQueryError, AdxTimeoutError

LOGGER = logging.getLogger("adx_connector.retry")

T = TypeVar("T")

# Service-side conditions worth another attempt.
_RETRYABLE = (KustoThrottlingError, KustoNetworkError)

# Substrings that mark a transient server fault inside a generic service error.
_RETRYABLE_TEXT = (
    "request is denied due to throttling",
    "service is unavailable",
    "internal service error",
    "gateway timeout",
    "connection reset",
    "temporarily unavailable",
    "e_too_many_requests",
)


def is_retryable(exc: BaseException) -> bool:
    """True when another attempt could plausibly succeed."""
    if isinstance(exc, _RETRYABLE):
        return True
    if isinstance(exc, (KustoAuthenticationError, KustoClientError)):
        return False
    if isinstance(exc, (KustoApiError, KustoServiceError)):
        text = str(exc).lower()
        return any(marker in text for marker in _RETRYABLE_TEXT)
    return False


def backoff_delay(attempt: int, base: float, cap: float) -> float:
    """Exponential backoff with full jitter, per the AWS-documented algorithm.

    Full jitter rather than equal jitter because concurrent ingestion workers
    otherwise resynchronise and re-collide on the next attempt.
    """
    ceiling = min(cap, base * (2**attempt))
    return random.uniform(0.0, ceiling)


def call_with_retry(
    operation: Callable[[], T],
    *,
    max_retries: int,
    base: float,
    cap: float,
    deadline: float | None = None,
    description: str = "kusto operation",
) -> T:
    """Run ``operation``, retrying retryable faults until attempts or deadline run out."""
    last: BaseException | None = None
    attempts = 0
    for attempt in range(max_retries + 1):
        if deadline is not None and time.monotonic() >= deadline:
            raise AdxTimeoutError(f"{description} exceeded its deadline before attempt {attempt + 1}")
        try:
            return operation()
        except KustoAuthenticationError as exc:
            raise AdxAuthError(f"{description} could not authenticate: {exc}") from exc
        except Exception as exc:  # noqa: BLE001 - re-raised below after classification
            last = exc
            attempts = attempt + 1
            if attempt >= max_retries or not is_retryable(exc):
                break
            delay = backoff_delay(attempt, base, cap)
            if deadline is not None and time.monotonic() + delay >= deadline:
                raise AdxTimeoutError(f"{description} would exceed its deadline while backing off") from exc
            LOGGER.warning(
                "%s failed on attempt %d/%d (%s); retrying in %.2fs",
                description,
                attempt + 1,
                max_retries + 1,
                type(exc).__name__,
                delay,
            )
            time.sleep(delay)

    assert last is not None
    # The count is what actually happened, not the budget. A permanent fault stops after one
    # attempt, and reporting the budget instead sends the reader hunting a throttling problem.
    raise AdxQueryError(
        f"{description} failed after {attempts} attempt(s): {last}",
        retryable=is_retryable(last),
    ) from last
