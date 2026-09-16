"""The signing keys, cached with a scheduled refresh, a rotation refresh, and a stale ceiling.

Module role:
    Holds one tenant's key set for the life of the process, refreshes it on a schedule,
    refreshes it again when a token arrives signed by a key it does not hold — because that
    is what a rotation looks like from here — and refuses to serve keys that have gone stale
    beyond a bounded window.

Four failure modes, and the shape of each fix:

    1. **Fetching per request** makes an outbound HTTPS round trip part of every authenticated
       request, and makes the identity provider's bad minute your bad minute. Fixed by a TTL.
    2. **Never refreshing** rejects every request the hour the key rotates, unannounced. Fixed
       by refreshing when a key id is unknown.
    3. **Refreshing on every unknown key id** hands an unauthenticated caller an outbound
       fetch per request. Fixed by a cooldown plus a single-flight lock, so a burst of
       invented key ids buys one fetch per window, not one per request.
    4. **Serving a stale set forever.** Upstream returned the cached keys on any fetch failure
       with no age limit, so a key revoked during a provider outage stays accepted for as long
       as the process runs. Fixed by :attr:`EntraAuthConfig.jwks_max_stale_seconds`: past that
       age the cache fails closed, and the API rejects tokens rather than honouring keys it
       can no longer confirm.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
import urllib.request
from typing import Awaitable, Callable

from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicNumbers
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from ._config import EntraAuthConfig
from ._errors import AuthError

logger = logging.getLogger(__name__)

#: Ceiling on a key-set response. Entra returns a few kilobytes; decoding something vastly
#: larger into memory before noticing is the wrong order of operations.
MAX_JWKS_BYTES = 512 * 1024

FETCH_TIMEOUT_SECONDS = 10.0

#: Async fetcher signature: ``(url) -> parsed JWKS document``. Injected so the component can
#: be exercised offline against minted keys, and so a consumer with its own HTTP policy —
#: proxy, retry, telemetry — supplies it rather than being overridden by this module.
Fetcher = Callable[[str], Awaitable[dict]]


def _http_get_json(url: str) -> dict:
    """Fetch and parse one JSON document over HTTPS. Blocking; call in a thread."""
    if not url.startswith("https://"):
        raise AuthError("jwks_unavailable", "refusing a non-HTTPS signing-key URL")
    request = urllib.request.Request(  # noqa: S310 - scheme is checked immediately above
        url, headers={"Accept": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=FETCH_TIMEOUT_SECONDS) as response:  # noqa: S310
        payload = response.read(MAX_JWKS_BYTES + 1)
    if len(payload) > MAX_JWKS_BYTES:
        raise AuthError("jwks_unavailable", "signing-key document exceeded the size ceiling")
    return json.loads(payload.decode("utf-8"))


async def default_fetcher(url: str) -> dict:
    """Fetch a key set without blocking the event loop."""
    return await asyncio.to_thread(_http_get_json, url)


class JWKSCache:
    """One tenant's signing keys, with a bounded refusal to go stale.

    Not a general cache. It holds exactly one document, for one tenant, for one process, and
    that narrowness is what lets the whole refresh policy be four rules instead of a
    configuration surface.
    """

    def __init__(
        self,
        config: EntraAuthConfig,
        *,
        fetcher: Fetcher | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._config = config
        self._fetch = fetcher or default_fetcher
        self._clock = clock
        self._keys: dict[str, dict] = {}
        self._fetched_at = 0.0
        self._last_forced = 0.0
        self._lock = asyncio.Lock()
        self.fetch_count = 0

    def clear(self) -> None:
        self._keys = {}
        self._fetched_at = 0.0
        self._last_forced = 0.0

    @property
    def loaded(self) -> bool:
        return bool(self._keys)

    def age_seconds(self) -> float:
        """Seconds since the last successful fetch; ``inf`` when never loaded."""
        if not self._fetched_at:
            return float("inf")
        return self._clock() - self._fetched_at

    def _expired(self) -> bool:
        return self.age_seconds() > self._config.jwks_ttl_seconds

    def _too_stale(self) -> bool:
        return self.age_seconds() > self._config.jwks_max_stale_seconds

    async def get_key(self, kid: str) -> dict:
        """Return the signing key with this id, refreshing when it is unknown.

        Args:
            kid: Key id from the unverified token header. Attacker-controlled: used only as a
                dictionary lookup, never interpolated into a message, never logged raw.

        Raises:
            AuthError: ``jwks_stale`` when the held set has aged past the ceiling and cannot
                be refreshed; ``unknown_kid`` when no such key exists after a permitted
                refresh; ``jwks_unavailable`` when nothing could be fetched and nothing is
                cached.
        """
        if not self._keys or self._expired():
            await self._refresh(reason="scheduled")

        # Checked after the refresh attempt, so a successful refresh clears it, and a failed
        # one that left an over-age set behind fails closed rather than serving it.
        if self._keys and self._too_stale():
            logger.error(
                "auth.jwks.too_stale",
                extra={"age_s": round(self.age_seconds(), 1),
                       "max_stale_s": self._config.jwks_max_stale_seconds},
            )
            raise AuthError(
                "jwks_stale",
                "signing keys are older than the maximum permitted staleness",
                age_s=round(self.age_seconds(), 1),
            )

        key = self._keys.get(kid)
        if key is not None:
            return key

        if self._may_force():
            await self._refresh(reason="rotation")
            key = self._keys.get(kid)
            if key is not None:
                return key

        # The id is never echoed. Its length distinguishes a plausible rotation miss from a
        # padding attack, which is the only thing an operator needs from it.
        logger.warning(
            "auth.jwks.unknown_kid", extra={"kid_len": len(kid), "keys": len(self._keys)}
        )
        raise AuthError("unknown_kid", "no signing key matches the token", kid_len=len(kid))

    def _may_force(self) -> bool:
        if not self._last_forced:
            return True
        elapsed = self._clock() - self._last_forced
        allowed = elapsed >= self._config.jwks_refresh_cooldown_seconds
        if not allowed:
            logger.info(
                "auth.jwks.refresh_suppressed", extra={"since_last_s": round(elapsed, 1)}
            )
        return allowed

    async def _refresh(self, *, reason: str) -> None:
        """Fetch the key set once, even under a burst of concurrent misses."""
        async with self._lock:
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
                    extra={"reason": reason, "error": type(exc).__name__,
                           "have_cached": bool(self._keys)},
                )
                if self._keys and not self._too_stale():
                    return  # still inside the permitted staleness window
                if self._keys:
                    return  # over-age; get_key fails closed on the next check
                raise AuthError(
                    "jwks_unavailable", "could not fetch signing keys"
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
                raise AuthError("jwks_unavailable", "signing-key document contained no keys")

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

    Raises:
        AuthError: ``unknown_kid`` when the entry is not a usable RSA key. Entra publishes RSA
            keys; guessing at anything else is how an unexpected key type becomes an accepted
            signature.
    """
    if jwk.get("kty") not in (None, "RSA"):
        raise AuthError("unknown_kid", "unsupported signing-key type")
    try:
        # base64url values are unpadded; two '=' is always enough and excess padding is ignored.
        modulus = int.from_bytes(base64.urlsafe_b64decode(jwk["n"] + "=="), "big")
        exponent = int.from_bytes(base64.urlsafe_b64decode(jwk["e"] + "=="), "big")
    except (KeyError, ValueError, TypeError) as exc:
        raise AuthError("unknown_kid", "malformed signing-key entry") from exc
    return (
        RSAPublicNumbers(e=exponent, n=modulus)
        .public_key()
        .public_bytes(encoding=Encoding.PEM, format=PublicFormat.SubjectPublicKeyInfo)
    )


__all__ = ["JWKSCache", "build_rsa_pem", "default_fetcher", "Fetcher", "MAX_JWKS_BYTES"]
