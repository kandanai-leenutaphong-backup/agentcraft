"""TokenValidator — the one place a bearer token becomes a believed identity.

Module role:
    Verifies an Entra ID access token and returns a :class:`Principal`. Owns the
    whole decision: algorithm, signing key, signature, audience, issuer, expiry
    and required claims. Nothing downstream re-checks any of it, and nothing
    upstream partially checks it first.

Order of operations, and why it is this order:
    Cheap and local checks run before anything that touches the network or does
    public-key mathematics, so a malformed or hostile token is rejected without
    spending either. Concretely: header shape, then algorithm, then key lookup,
    then signature, then the claim rules. An implementation that verifies the
    signature first will happily do RSA work on behalf of an anonymous caller.

What this module refuses to do:
    Trust any value from the token before the signature is verified. The one
    exception is the key id, which must be read from the unverified header to
    find the key at all — and it is used only as a dictionary lookup, never
    logged raw, never returned (G2).
"""

from __future__ import annotations

import logging
import time
from typing import Any, Mapping

import jwt as pyjwt

from ._config import ALLOWED_ALGORITHMS, GUID_PATTERN, ISSUER_PATTERN, AuthConfig
from ._errors import AuthError
from ._jwks import Fetcher, JWKSCache, build_rsa_pem
from ._principal import Principal, developer_principal, principal_from_claims

logger = logging.getLogger(__name__)

_BEARER_PREFIX = "Bearer "

# Longest token accepted before parsing. Real Entra access tokens are a few
# kilobytes; the limit stops an unauthenticated caller spending server memory
# and parser time by sending megabytes.
_MAX_TOKEN_BYTES = 16 * 1024


class TokenValidator:
    """Validates Entra access tokens against one tenant and one audience.

    One instance per API. Holds the key cache, so constructing a validator per
    request discards the cache and reintroduces a fetch per request (G1).
    """

    def __init__(
        self,
        config: AuthConfig,
        *,
        fetcher: Fetcher | None = None,
        clock: Any = time.monotonic,
        jwks_cache: JWKSCache | None = None,
    ) -> None:
        """Args:
            config: Tenant, audience and policy.
            fetcher: Async key-set fetcher. Injected by tests and by consumers
                with their own HTTP policy.
            clock: Monotonic time source for cache ages.
            jwks_cache: A pre-built cache, when one is shared deliberately.
        """
        self.config = config
        self.jwks = jwks_cache or JWKSCache(config, fetcher=fetcher, clock=clock)

    # ── entry points ────────────────────────────────────────────────────────

    async def authenticate(
        self, headers: Mapping[str, str], *, dev_identity: Mapping[str, str] | None = None
    ) -> Principal:
        """Authenticate one request from its headers.

        Args:
            headers: Request headers. Looked up case-insensitively, because
                header case is not guaranteed by any hop in front of the app.
            dev_identity: Header values naming the caller in disabled-auth mode.
                Ignored entirely when auth is enabled — this is the property
                that makes the development path impossible to reach in
                production rather than merely discouraged (G12).

        Raises:
            AuthError: On any rejection. The caller-visible message is a
                constant chosen by reason; details stay in the log.
        """
        if not self.config.enabled:
            return self._developer_identity(dev_identity or {})

        token = self._extract_bearer(headers)
        claims = await self.validate_token(token)
        return principal_from_claims(claims)

    async def validate_token(self, token: str) -> dict[str, Any]:
        """Verify a raw token and return its claims.

        Separate from :meth:`authenticate` so a non-HTTP caller — a WebSocket
        handshake, a queue consumer, a test — validates by exactly the same
        rules rather than by a second implementation that drifts.
        """
        started = time.monotonic()
        try:
            claims = await self._validate(token)
        except AuthError as exc:
            logger.warning(
                "auth.token.rejected",
                extra={**exc.log_fields(),
                       "duration_ms": round((time.monotonic() - started) * 1000, 1)},
            )
            raise
        logger.info(
            "auth.token.validated",
            extra={"principal_id": claims.get("oid", claims.get("sub", "")),
                   "tenant_id": claims.get("tid", ""),
                   "duration_ms": round((time.monotonic() - started) * 1000, 1)},
        )
        return claims

    # ── the decision ────────────────────────────────────────────────────────

    async def _validate(self, token: str) -> dict[str, Any]:
        """Run every check, cheapest first. Raises :class:`AuthError`."""
        if not token or not token.strip():
            raise AuthError("empty_token", "authorization header carried no token")
        if len(token) > _MAX_TOKEN_BYTES:
            raise AuthError("malformed", "token exceeds the maximum accepted size",
                            token_len=len(token))

        header = self._unverified_header(token)
        self._check_algorithm(header)

        key = await self.jwks.get_key(header.get("kid", ""))
        pem = build_rsa_pem(key)

        claims = self._decode(token, pem)
        self._check_issuer(claims)
        self._check_key_issuer(key, claims)
        self._check_required_claims(claims)
        return claims

    def _unverified_header(self, token: str) -> dict[str, Any]:
        """Read the JOSE header without trusting it. Needed to find the key."""
        try:
            return pyjwt.get_unverified_header(token)
        except pyjwt.PyJWTError as exc:
            raise AuthError("malformed", f"cannot decode token header: {exc}") from exc

    def _check_algorithm(self, header: Mapping[str, Any]) -> None:
        """Reject any algorithm outside the allowlist, before touching a key.

        The two attacks this closes are ``alg: none``, which asks the verifier
        to accept an unsigned token, and RS256/HS256 confusion, which asks it to
        treat a *public* key as an HMAC secret — a key that is, by definition,
        published. Both are defeated by never letting the token choose.
        """
        algorithm = header.get("alg", "")
        if algorithm not in ALLOWED_ALGORITHMS:
            raise AuthError(
                "bad_algorithm",
                f"token algorithm {algorithm!r} is not in {ALLOWED_ALGORITHMS}",
                alg_len=len(str(algorithm)),
            )

    def _decode(self, token: str, pem: bytes) -> dict[str, Any]:
        """Verify signature, audience and expiry.

        Issuer verification is switched off here and performed separately: the
        library can only exact-match, and a multi-tenant API cannot know the
        issuer in advance.
        """
        try:
            return pyjwt.decode(
                token,
                pem,
                algorithms=list(ALLOWED_ALGORITHMS),
                audience=self.config.audiences(),
                options={"verify_iss": False, "require": ["exp"]},
                leeway=self.config.leeway_seconds,
            )
        except pyjwt.ExpiredSignatureError as exc:
            raise AuthError("expired", "token has expired") from exc
        except pyjwt.ImmatureSignatureError as exc:
            raise AuthError("not_yet_valid", "token is not valid yet") from exc
        except pyjwt.InvalidAudienceError as exc:
            raise AuthError(
                "bad_audience",
                f"token audience is not one of {self.config.audiences()}",
            ) from exc
        except pyjwt.InvalidSignatureError as exc:
            raise AuthError("bad_signature", "signature verification failed") from exc
        except pyjwt.MissingRequiredClaimError as exc:
            raise AuthError("missing_claim", f"token is missing {exc}") from exc
        except pyjwt.PyJWTError as exc:
            raise AuthError("malformed", f"token rejected: {exc}") from exc

    def _check_issuer(self, claims: Mapping[str, Any]) -> None:
        """Confirm the token came from the tenant this API trusts.

        Single-tenant compares against both the v2 and v1 issuer forms, because
        which one appears depends on how the token was requested and rejecting
        the other produces an intermittent failure that looks like a bad
        signature. Multi-tenant can only assert the shape.
        """
        issuer = str(claims.get("iss", ""))
        if self.config.multi_tenant:
            if not ISSUER_PATTERN.match(issuer):
                raise AuthError("bad_issuer", "issuer is not an Entra ID issuer")
            return
        if issuer not in self.config.expected_issuers():
            raise AuthError(
                "bad_issuer",
                f"issuer {issuer!r} is not the configured tenant",
            )

    def _check_key_issuer(
        self, key: Mapping[str, Any], claims: Mapping[str, Any]
    ) -> None:
        """Confirm the signing key belongs to the tenant that issued the token.

        Multi-tenant hardening. Entra publishes an ``issuer`` on each key,
        sometimes templated as ``{tenantid}``. Without this check a multi-tenant
        API accepts a token whose issuer claims tenant A while its signature
        comes from a key scoped to tenant B. Keys with no issuer field are
        legacy and skip the check rather than failing it.
        """
        template = str(key.get("issuer", ""))
        if not template:
            return
        expected = template.replace("{tenantid}", str(claims.get("tid", "")))
        issuer = str(claims.get("iss", ""))
        if issuer == expected:
            return
        # v1 and v2 issuer forms differ by more than the tenant, so compare the
        # tenant GUIDs rather than the URIs.
        key_tenant = GUID_PATTERN.search(expected)
        token_tenant = GUID_PATTERN.search(issuer)
        if not (key_tenant and token_tenant and key_tenant.group() == token_tenant.group()):
            raise AuthError(
                "key_issuer_mismatch",
                f"signing key issuer {expected!r} does not match token issuer {issuer!r}",
            )

    def _check_required_claims(self, claims: Mapping[str, Any]) -> None:
        """Require every configured claim to be present and non-empty.

        ``oid`` by default. A token that verifies but carries no object id —
        a service principal token, or a malformed one — otherwise produces a
        principal whose id is the empty string, and every such caller then
        shares one identity and one set of resources (G3).
        """
        for name in self.config.required_claims:
            if not claims.get(name):
                raise AuthError(
                    "missing_claim",
                    f"token is missing the required {name!r} claim",
                    claim=name,
                )

    # ── disabled mode ───────────────────────────────────────────────────────

    def _developer_identity(self, headers: Mapping[str, str]) -> Principal:
        """Build the identity used when auth is disabled.

        Per-caller identity from headers is genuinely useful — it is what lets
        two browser tabs behave as two users while testing ownership rules — and
        it is also completely unauthenticated. It is confined to this branch,
        which is unreachable when ``enabled`` is true, and the resulting
        principal is marked ``developer`` so nothing downstream mistakes it for
        a proven identity.
        """
        if not self.config.dev_identity_headers:
            return developer_principal()
        return developer_principal(
            principal_id=_first(headers, "X-User-Id") or "anonymous",
            email=_first(headers, "X-User-Email") or "dev@localhost",
            name=_first(headers, "X-User-Name") or "Developer",
        )

    # ── header handling ─────────────────────────────────────────────────────

    def _extract_bearer(self, headers: Mapping[str, str]) -> str:
        """Pull the bearer token out of the Authorization header.

        The scheme comparison is case-insensitive per RFC 7235; the token is
        not. Both a missing header and a wrong scheme produce the same reason,
        because distinguishing them tells a caller nothing they need.
        """
        raw = _first(headers, "Authorization")
        if not raw:
            raise AuthError("missing_header", "no Authorization header present")
        if not raw[: len(_BEARER_PREFIX)].lower() == _BEARER_PREFIX.lower():
            raise AuthError("missing_header", "Authorization header is not Bearer")
        return raw[len(_BEARER_PREFIX):].strip()


def _first(headers: Mapping[str, str], name: str) -> str:
    """Case-insensitive header lookup.

    Header case survives no guarantee across proxies, ingress controllers and
    ASGI servers, and a case-sensitive lookup produces an auth failure that
    appears only once the app is behind a load balancer.
    """
    value = headers.get(name)
    if value is not None:
        return str(value)
    lowered = name.lower()
    for key, candidate in headers.items():
        if key.lower() == lowered:
            return str(candidate)
    return ""


__all__ = ["TokenValidator"]
