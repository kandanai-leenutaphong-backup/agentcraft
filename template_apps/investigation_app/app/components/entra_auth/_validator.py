"""The one place a bearer token becomes a believed identity.

Module role:
    Owns the whole decision — size, algorithm, signing key, signature, audience, issuer,
    tenant, time claims, required claims, caller kind and permission. Nothing downstream
    re-checks any of it, and nothing upstream partially checks it first.

Order, and why it is this order:
    Cheap local checks run before anything that touches the network or does public-key
    mathematics, so a malformed or hostile token is refused without spending either. An
    implementation that verifies the signature first performs RSA work on behalf of anonymous
    callers.

What this module refuses to do:
    Trust any value from the token before the signature is verified. The single exception is
    the key id, which must be read unverified to find a key at all — and it is used only as a
    dictionary lookup, never logged raw, never returned.

Two upstream behaviours are deliberately not carried:
    * a disabled mode that granted a self-asserted header identity — there is no such branch
      here, so no configuration mistake can reach it;
    * ``required_claims=("oid",)`` treated as the service-principal filter. It is not one. A
      v2 client-credentials token carries the service principal's own ``oid``, so requiring
      ``oid`` rejects nothing. Caller kind is decided by ``idtyp``/``scp``/``roles`` and
      enforced by :attr:`EntraAuthConfig.allow_service_principals`.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Mapping

import jwt as pyjwt

from ._config import ALLOWED_ALGORITHMS, EntraAuthConfig
from ._errors import AuthError
from ._jwks import Fetcher, JWKSCache, build_rsa_pem

logger = logging.getLogger(__name__)

_BEARER_PREFIX = "bearer "

#: Longest token parsed. Real Entra access tokens are a few kilobytes; the ceiling stops an
#: unauthenticated caller spending server memory and parser time by sending megabytes.
MAX_TOKEN_BYTES = 16 * 1024

#: Time claims that must be present. ``exp`` alone leaves a token with no issuance instant,
#: which is the shape a forged long-life token takes when a verifier only looks at expiry.
REQUIRED_TIME_CLAIMS = ("exp", "iat")

KIND_USER = "user"
KIND_SERVICE = "service"


@dataclass(frozen=True, slots=True)
class VerifiedToken:
    """A token that passed every check, reduced to the fields a consumer may act on.

    Deliberately **not** an identity type. This component knows nothing about the consuming
    application's principal model, and returning one would duplicate it. The consumer maps
    these fields onto its own identity in one place it owns.

    Attributes:
        tenant_id: ``tid``. Equal to the configured tenant; re-stated so a consumer building
            a namespaced identifier does not reach back into configuration.
        object_id: ``oid``. The stable identity. The owner key for anything the caller
            creates — never the email, which changes hands.
        kind: ``user`` or ``service``.
        display: Best available label. Never used for an authorization decision.
        username: ``preferred_username``/``upn``, when present. Personal data; log
            deliberately, not by default.
        scopes: Delegated permissions from ``scp``.
        roles: Application roles from ``roles``.
        expires_at: ``exp`` as a POSIX instant. A consumer minting a session must not outlive
            it.
        claims: The remaining verified claims, for a consumer that genuinely needs one this
            record does not model.
    """

    tenant_id: str
    object_id: str
    kind: str
    display: str = ""
    username: str = ""
    scopes: tuple[str, ...] = ()
    roles: tuple[str, ...] = ()
    expires_at: int = 0
    claims: dict[str, Any] = field(default_factory=dict)

    @property
    def is_service(self) -> bool:
        return self.kind == KIND_SERVICE


class TokenValidator:
    """Validates Entra access tokens against one tenant and one audience.

    One instance per API. It holds the key cache, so constructing a validator per request
    discards the cache and reintroduces an outbound fetch per request.
    """

    def __init__(
        self,
        config: EntraAuthConfig,
        *,
        fetcher: Fetcher | None = None,
        clock: Any = time.monotonic,
        jwks_cache: JWKSCache | None = None,
    ) -> None:
        self.config = config
        self.jwks = jwks_cache or JWKSCache(config, fetcher=fetcher, clock=clock)

    async def authenticate(self, headers: Mapping[str, str]) -> VerifiedToken:
        """Authenticate one request from its headers.

        Header lookup is case-insensitive: header case survives no guarantee across proxies,
        ingress controllers and ASGI servers, and a case-sensitive lookup produces an auth
        failure that appears only once the application is behind a load balancer.
        """
        return await self.validate_token(extract_bearer(headers))

    async def validate_token(self, token: str) -> VerifiedToken:
        """Verify a raw token and return what it proves.

        Separate from :meth:`authenticate` so a non-HTTP caller validates by exactly the same
        rules rather than by a second implementation that drifts.
        """
        started = time.monotonic()
        try:
            verified = await self._validate(token)
        except AuthError as exc:
            logger.warning(
                "auth.token.rejected",
                extra={**exc.log_fields(),
                       "duration_ms": round((time.monotonic() - started) * 1000, 1)},
            )
            raise
        logger.info(
            "auth.token.validated",
            extra={"principal_oid": verified.object_id, "tenant_id": verified.tenant_id,
                   "kind": verified.kind,
                   "duration_ms": round((time.monotonic() - started) * 1000, 1)},
        )
        return verified

    async def _validate(self, token: str) -> VerifiedToken:
        if not token or not token.strip():
            raise AuthError("empty_token", "authorization header carried no token")
        if len(token) > MAX_TOKEN_BYTES:
            raise AuthError("oversized", "token exceeds the accepted size", token_len=len(token))

        header = self._unverified_header(token)
        self._check_algorithm(header)

        key = await self.jwks.get_key(str(header.get("kid", "")))
        pem = build_rsa_pem(key)

        claims = self._decode(token, pem)
        self._check_issuer(claims)
        self._check_key_issuer(key, claims)
        self._check_tenant(claims)
        self._check_time_claims(claims)
        self._check_required_claims(claims)
        verified = self._build(claims)
        self._check_permission(verified)
        return verified

    def _unverified_header(self, token: str) -> dict[str, Any]:
        """Read the JOSE header without trusting it. Needed to find the key at all."""
        try:
            return pyjwt.get_unverified_header(token)
        except pyjwt.PyJWTError as exc:
            raise AuthError("malformed", "token header could not be decoded") from exc

    def _check_algorithm(self, header: Mapping[str, Any]) -> None:
        """Refuse any algorithm outside the allowlist, before touching a key.

        Closes ``alg: none``, which asks the verifier to accept an unsigned token, and
        RS256/HS256 confusion, which asks it to treat a *published* public key as an HMAC
        secret. Both are defeated by never letting the token choose.
        """
        algorithm = header.get("alg", "")
        if algorithm not in ALLOWED_ALGORITHMS:
            raise AuthError(
                "bad_algorithm", "token algorithm is not accepted",
                alg_len=len(str(algorithm)),
            )

    def _decode(self, token: str, pem: bytes) -> dict[str, Any]:
        """Verify signature, audience and expiry.

        Issuer verification is performed separately because the library can only exact-match
        one value, and this API accepts the v1 and v2 forms of one tenant.
        """
        try:
            return pyjwt.decode(
                token,
                pem,
                algorithms=list(ALLOWED_ALGORITHMS),
                audience=list(self.config.audiences()),
                options={"verify_iss": False, "require": list(REQUIRED_TIME_CLAIMS)},
                leeway=self.config.leeway_seconds,
            )
        except pyjwt.ExpiredSignatureError as exc:
            raise AuthError("expired", "token has expired") from exc
        except pyjwt.ImmatureSignatureError as exc:
            raise AuthError("not_yet_valid", "token is not valid yet") from exc
        except pyjwt.InvalidAudienceError as exc:
            raise AuthError("bad_audience", "token audience is not this API") from exc
        except pyjwt.InvalidSignatureError as exc:
            raise AuthError("bad_signature", "signature verification failed") from exc
        except pyjwt.MissingRequiredClaimError as exc:
            raise AuthError("missing_claim", "token is missing a required time claim") from exc
        except pyjwt.PyJWTError as exc:
            raise AuthError("malformed", "token was rejected by the decoder") from exc

    def _check_issuer(self, claims: Mapping[str, Any]) -> None:
        """Exact-match the issuer against the configured tenant's two forms."""
        issuer = str(claims.get("iss", ""))
        if issuer not in self.config.expected_issuers():
            raise AuthError("bad_issuer", "issuer is not the configured tenant")

    def _check_key_issuer(self, key: Mapping[str, Any], claims: Mapping[str, Any]) -> None:
        """Confirm the key that signed this token belongs to the tenant that issued it.

        Redundant for a single-tenant API whose issuer is already exact-matched, and kept
        anyway: it costs one string comparison, and it is the check whose absence lets a
        token claiming one tenant be signed by another tenant's key.
        """
        template = str(key.get("issuer", ""))
        if not template:
            return  # legacy key entries publish no issuer
        expected = template.replace("{tenantid}", str(claims.get("tid", "")))
        if expected in self.config.expected_issuers():
            return
        if str(claims.get("iss", "")) == expected:
            return
        raise AuthError("key_issuer_mismatch", "signing key does not belong to this tenant")

    def _check_tenant(self, claims: Mapping[str, Any]) -> None:
        """The ``tid`` claim must be the configured tenant, compared case-insensitively."""
        if str(claims.get("tid", "")).lower() != self.config.tenant_id.lower():
            raise AuthError("bad_tenant", "token tenant is not the configured tenant")

    def _check_time_claims(self, claims: Mapping[str, Any]) -> None:
        """``exp`` and ``iat`` must be present; ``nbf`` must be honoured when it is.

        ``pyjwt`` already enforces the ``require`` list and validates ``nbf`` when present.
        This adds the plausibility rule the library has no opinion about: an issuance instant
        far in the future is not a clock-skew artefact.
        """
        now = time.time()
        issued = claims.get("iat")
        if not isinstance(issued, (int, float)):
            raise AuthError("missing_claim", "token has no usable issuance time", claim="iat")
        if issued > now + self.config.leeway_seconds:
            raise AuthError("not_yet_valid", "token was issued in the future")

    def _check_required_claims(self, claims: Mapping[str, Any]) -> None:
        """Every configured claim must be present and non-empty.

        A claim used as a primary key must be a claim that is required. ``oid`` absent means
        every such caller shares the empty identity and therefore each other's resources.
        """
        for name in self.config.required_claims:
            if not claims.get(name):
                raise AuthError(
                    "missing_claim", "token is missing a required claim", claim=name
                )

    def _build(self, claims: Mapping[str, Any]) -> VerifiedToken:
        """Reduce verified claims to the record consumers act on.

        Caller kind: an application acting as itself is marked ``idtyp=app`` on v2 tokens and
        carries ``roles`` without ``scp``. Both signals are consulted, because the absence of
        ``oid`` — which upstream documentation treats as the portable test — is **not** one:
        a v2 client-credentials token carries the service principal's own object id.
        """
        scopes = tuple(str(claims.get("scp", "")).split()) if claims.get("scp") else ()
        roles = tuple(str(r) for r in (claims.get("roles") or ()))
        is_service = (
            str(claims.get("idtyp", "")).lower() == "app"
            or not claims.get("oid")
            or (bool(roles) and not scopes and not claims.get("preferred_username"))
        )
        return VerifiedToken(
            tenant_id=str(claims.get("tid", "")),
            object_id=str(claims.get("oid") or claims.get("sub") or ""),
            kind=KIND_SERVICE if is_service else KIND_USER,
            display=str(claims.get("name", "")),
            username=str(claims.get("preferred_username") or claims.get("upn") or ""),
            scopes=scopes,
            roles=roles,
            expires_at=int(claims.get("exp", 0)),
            claims=dict(claims),
        )

    def _check_permission(self, verified: VerifiedToken) -> None:
        """Apply the caller-kind policy and the permission requirement.

        A valid token is not an authorization. A human must hold one of the required delegated
        scopes; a service principal is refused outright unless the configuration opted in and
        the token carries one of the required application roles.
        """
        if verified.is_service:
            if not self.config.allow_service_principals:
                raise AuthError(
                    "service_principal_refused",
                    "application tokens are not accepted by this API",
                )
            if not any(role in verified.roles for role in self.config.required_roles):
                raise AuthError(
                    "missing_scope", "application token carries no accepted role"
                )
            return
        if self.config.required_scopes and not any(
            scope in verified.scopes for scope in self.config.required_scopes
        ):
            raise AuthError("missing_scope", "token carries no accepted delegated scope")


def extract_bearer(headers: Mapping[str, str]) -> str:
    """Pull the bearer token out of ``Authorization``.

    The scheme comparison is case-insensitive per RFC 7235; the token is not. A missing header
    and a wrong scheme produce the same reason, because distinguishing them tells a caller
    nothing they need.
    """
    raw = first_header(headers, "Authorization")
    if not raw:
        raise AuthError("missing_header", "no Authorization header present")
    if raw[: len(_BEARER_PREFIX)].lower() != _BEARER_PREFIX:
        raise AuthError("missing_header", "Authorization header is not Bearer")
    return raw[len(_BEARER_PREFIX):].strip()


def first_header(headers: Mapping[str, str], name: str) -> str:
    """Case-insensitive header lookup."""
    value = headers.get(name)
    if value is not None:
        return str(value)
    lowered = name.lower()
    for key, candidate in headers.items():
        if key.lower() == lowered:
            return str(candidate)
    return ""


__all__ = [
    "TokenValidator",
    "VerifiedToken",
    "extract_bearer",
    "first_header",
    "KIND_USER",
    "KIND_SERVICE",
    "MAX_TOKEN_BYTES",
]
