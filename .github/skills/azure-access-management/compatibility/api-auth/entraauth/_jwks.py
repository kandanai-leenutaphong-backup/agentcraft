"""JWKS retrieval and caching — the key set that decides which tokens are real.

Module role:
    Fetches Entra's signing keys, caches them, refreshes them on a schedule, and
    refreshes them again when a token arrives signed by a key that is not in the
    cache — because that is what a key rotation looks like from here.

The three failure modes this exists to avoid:

    1. **Fetching per request.** The obvious implementation calls the discovery
       endpoint on every validation. That is an outbound HTTPS round trip on the
       hot path of every authenticated request, and it makes an outage in the
       key service an outage in your API (G1).
    2. **Never refreshing.** A cache with no rotation path rejects every request
       the day the signing key rotates, and rotation is not announced.
    3. **Refreshing on demand, unbounded.** Refreshing whenever a key id is
       unrecognised turns an unauthenticated caller into a traffic generator
       against the key service: random key ids, one fetch each (G10).

    The resolution is a scheduled TTL, plus rotation-triggered refresh behind a
    cooldown, plus single-flight so a burst produces one fetch and not N.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
import urllib.request
from typing import Any, Awaitable, Callable

from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicNumbers
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from ._config import AuthConfig
from ._errors import AuthError

logger = logging.getLogger(__name__)

# Ceiling on a key-set response. Entra returns a few kilobytes; anything vastly
# larger is a misconfigured endpoint or a hostile one, and decoding it into
# memory before noticing is the wrong order of operations.
_MAX_JWKS_BYTES = 512 * 1024

_FETCH_TIMEOUT_SECONDS = 10.0

# Async fetcher signature: (url) -> parsed JWKS document.
Fetcher = Callable[[str], Awaitable[dict]]


def _http_get_json(url: str) -> dict:
    """Fetch and parse a JSON document over HTTPS. Blocking; run in a thread.

    Uses the standard library rather than an HTTP client dependency: this box
    makes exactly one kind of outbound call, to one well-known endpoint, and a
    client library would be the largest thing it depends on.
    """
    if not url.startswith("https://"):
        raise AuthError(
            "jwks_unavailable",
            f"refusing to fetch signing keys over a non-HTTPS URL: {url!r}",
        )
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=_FETCH_TIMEOUT_SECONDS) as response:
        payload = response.read(_MAX_JWKS_BYTES + 1)
    if len(payload) > _MAX_JWKS_BYTES:
        raise AuthError(
            "jwks_unavailable",
            f"signing key document exceeded {_MAX_JWKS_BYTES} bytes",
        )
    return json.loads(payload.decode("utf-8"))


async def default_fetcher(url: str) -> dict:
    """Fetch a key set without blocking the event loop."""
    return await asyncio.to_thread(_http_get_json, url)


class JWKSCache:
    """A key set, with a scheduled refresh and a rate-limited rotation refresh.

    Not a general cache: it holds exactly one document, for one tenant, for the
    lifetime of the process. That narrowness is what lets the refresh policy be
    stated in twenty lines instead of configured.
    """

    def __init__(
        self,
        config: AuthConfig,
        *,
        fetcher: Fetcher | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Args:
            config: Supplies the tenant URL and both refresh intervals.
            fetcher: Async ``(url) -> dict``. Injected by tests, and by
                consumers who already own an HTTP client with their own
                proxy, retry or telemetry policy.
            clock: Monotonic time source. Injected so TTL expiry is testable
                without waiting a day.
        """
        self._config = config
        self._fetch = fetcher or default_fetcher
        self._clock = clock
        self._keys: dict[str, dict] = {}
        self._fetched_at = 0.0
        self._last_forced = 0.0
        self._lock = asyncio.Lock()
        self.fetch_count = 0

    def clear(self) -> None:
        """Drop the cached key set. For tests and deliberate re-fetch."""
        self._keys = {}
        self._fetched_at = 0.0
        self._last_forced = 0.0

    @property
    def loaded(self) -> bool:
        """True when a key set is held, regardless of age."""
        return bool(self._keys)

    def age_seconds(self) -> float:
        """Seconds since the last successful fetch. ``inf`` when never loaded."""
        if not self._fetched_at:
            return float("inf")
        return self._clock() - self._fetched_at

    def _expired(self) -> bool:
        return self.age_seconds() > self._config.jwks_ttl_seconds

    async def get_key(self, kid: str) -> dict:
        """Return the signing key with this id, refreshing if it is unknown.

        Args:
            kid: Key id from the token header. Attacker-controlled: it is used
                only as a dictionary lookup, is never interpolated into an error
                message, and is never logged raw.

        Raises:
            AuthError: ``unknown_kid`` when no such key exists after a permitted
                refresh; ``jwks_unavailable`` when keys could not be fetched at
                all and none are cached.
        """
        if not self._keys or self._expired():
            await self._refresh(reason="scheduled")

        key = self._keys.get(kid)
        if key is not None:
            return key

        # Unknown id. Either a rotation, or a caller probing. One refresh, at
        # most once per cooldown window, shared across concurrent callers.
        if self._may_force():
            await self._refresh(reason="rotation")
            key = self._keys.get(kid)
            if key is not None:
                return key

        # The id is never echoed — only its length, which is enough to tell a
        # plausible key id from a padding attack.
        logger.warning(
            "auth.jwks.unknown_kid", extra={"kid_len": len(kid), "keys": len(self._keys)}
        )
        raise AuthError("unknown_kid", "no signing key matches the token", kid_len=len(kid))

    def _may_force(self) -> bool:
        """True when a rotation-triggered refresh is allowed right now."""
        if not self._last_forced:
            return True
        elapsed = self._clock() - self._last_forced
        allowed = elapsed >= self._config.jwks_refresh_cooldown_seconds
        if not allowed:
            logger.info(
                "auth.jwks.refresh_suppressed",
                extra={"since_last_s": round(elapsed, 1)},
            )
        return allowed

    async def _refresh(self, *, reason: str) -> None:
        """Fetch the key set once, even under a burst of concurrent misses.

        Raises:
            AuthError: ``jwks_unavailable``, but only when there is nothing
                cached. A fetch failure with a usable cached set is survivable
                and is logged rather than raised — an outage in the key service
                should not take the API down while the current keys still work.
        """
        async with self._lock:
            # Another caller may have refreshed while this one waited.
            if reason == "scheduled" and self._keys and not self._expired():
                return
            if reason == "rotation" and not self._may_force():
                return

            url = self._config.jwks_url()
            started = self._clock()
            try:
                document = await self._fetch(url)
            except AuthError:
                raise
            except Exception as exc:
                logger.warning(
                    "auth.jwks.fetch_failed",
                    extra={"reason": reason, "error": str(exc)[:200],
                           "have_cached": bool(self._keys)},
                )
                if self._keys:
                    return  # serve the stale set; it is still signed by Entra
                raise AuthError(
                    "jwks_unavailable", f"could not fetch signing keys: {exc}"
                ) from exc

            keys = {
                key["kid"]: key
                for key in document.get("keys", [])
                if isinstance(key, dict) and key.get("kid")
            }
            if not keys:
                if self._keys:
                    logger.warning("auth.jwks.empty_document_ignored")
                    return
                raise AuthError(
                    "jwks_unavailable", "signing key document contained no keys"
                )

            self._keys = keys
            self._fetched_at = self._clock()
            self.fetch_count += 1
            if reason == "rotation":
                self._last_forced = self._fetched_at
            logger.info(
                "auth.jwks.fetched",
                extra={"reason": reason, "key_count": len(keys),
                       "duration_ms": round((self._clock() - started) * 1000, 1)},
            )


def build_rsa_pem(jwk: dict) -> bytes:
    """Convert one JWKS entry into a PEM public key.

    Args:
        jwk: A key object with base64url ``n`` and ``e`` values (RFC 7517).

    Returns:
        PEM bytes suitable for signature verification.

    Raises:
        AuthError: ``unknown_kid`` when the entry is not a usable RSA key. Entra
            publishes RSA keys; anything else is a document this box does not
            understand, and guessing at it is how an unexpected key type becomes
            an accepted signature.
    """
    if jwk.get("kty") not in (None, "RSA"):
        raise AuthError(
            "unknown_kid", f"unsupported key type {jwk.get('kty')!r}"
        )
    try:
        # base64url values are unpadded; two '=' is always enough padding and
        # excess padding is ignored by the decoder.
        modulus = int.from_bytes(base64.urlsafe_b64decode(jwk["n"] + "=="), "big")
        exponent = int.from_bytes(base64.urlsafe_b64decode(jwk["e"] + "=="), "big")
    except (KeyError, ValueError, TypeError) as exc:
        raise AuthError("unknown_kid", f"malformed signing key entry: {exc}") from exc

    public_key = RSAPublicNumbers(e=exponent, n=modulus).public_key()
    return public_key.public_bytes(
        encoding=Encoding.PEM, format=PublicFormat.SubjectPublicKeyInfo
    )


__all__ = ["JWKSCache", "build_rsa_pem", "default_fetcher", "Fetcher"]
