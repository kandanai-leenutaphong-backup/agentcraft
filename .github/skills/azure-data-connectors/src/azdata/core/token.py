"""Fabric REST token cache — one token, refreshed early, degraded not dropped.

WHY THIS EXISTS
---------------
Entra access tokens live 60-90 minutes. A long-running process that
acquires one per call pays a network round trip every time; one that
acquires a token once fails an hour later with a 401 that looks like a
permissions problem.

Refresh well before expiry (45 minutes by default), guard the refresh with
double-checked locking so a burst of concurrent callers triggers one
acquisition rather than twenty, and — the part that is easy to get wrong —
if refresh fails while a still-valid cached token exists, return the
cached token and log. A transient Entra failure should not take down a
service whose current credential still works (GOTCHAS.md G9).

DEPENDENCIES
------------
Standard library. The credential arrives injected.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable

logger = logging.getLogger(__name__)


class TokenCache:
    """Caches one bearer token for one scope.

    Args:
        credential_provider: Returns a ``TokenCredential``.
        scope: The resource scope, e.g. ``https://api.fabric.microsoft.com/.default``.
        stale_after_secs: Refresh once the token is older than this. Keep
            it comfortably under the shortest expiry you expect.
    """

    def __init__(
        self,
        *,
        credential_provider: Callable[[], Any],
        scope: str,
        stale_after_secs: float = 2700.0,
    ) -> None:
        self._credential_provider = credential_provider
        self._scope = scope
        self._stale_after = stale_after_secs
        self._credential: Any = None
        self._token: str | None = None
        self._acquired_at = 0.0
        self._lock = asyncio.Lock()

    async def get(self) -> str:
        """Return a bearer token, refreshing when stale.

        Raises:
            RuntimeError: Refresh failed and no cached token exists.
        """
        if self._token and (time.monotonic() - self._acquired_at) < self._stale_after:
            return self._token

        async with self._lock:
            # Re-check: another caller may have refreshed while we queued.
            if self._token and (
                time.monotonic() - self._acquired_at
            ) < self._stale_after:
                return self._token

            if self._credential is None:
                self._credential = self._credential_provider()

            try:
                # get_token is synchronous and does network I/O.
                token_obj = await asyncio.to_thread(
                    self._credential.get_token, self._scope
                )
            except Exception as exc:
                if self._token:
                    logger.warning(
                        "token_cache.refresh_failed, serving cached token: %s",
                        str(exc)[:200],
                    )
                    return self._token
                raise RuntimeError(
                    "Unable to acquire an access token. Check the credential "
                    "configuration and the role assignment for this scope."
                ) from exc

            self._token = token_obj.token
            self._acquired_at = time.monotonic()
            logger.debug("token_cache.refreshed scope=%s", self._scope)
            return self._token

    def invalidate(self) -> None:
        """Drop the cached token so the next ``get`` re-acquires."""
        self._token = None
        self._acquired_at = 0.0


__all__ = ["TokenCache"]
