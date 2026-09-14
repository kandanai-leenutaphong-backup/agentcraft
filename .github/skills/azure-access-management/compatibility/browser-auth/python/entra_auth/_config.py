"""Which tokens this API believes, frozen at construction.

Module role:
    The trust boundary as data. Tenant, audience, algorithm allowlist, claim requirements and
    the two cache intervals. Every other module in this component takes an instance; none
    reaches for a global and none reads the environment.

**There is no ``enabled`` flag, and that is the point.** Upstream carried one, and with it a
disabled mode that granted every caller a self-asserted identity from an ``X-User-Id`` header.
Its ``from_env`` mapped any unrecognised value — a typo, a trailing space in a variant the
strip did not catch, an empty string — to ``enabled=False``, which is the *open* state. That
is a lever whose accidental position is the dangerous one. Here the lever does not exist: a
config object either describes a real tenant and a real audience, or it cannot be constructed.
A deployment that fails to configure Entra gets no Entra resolver, and the application's
authorization gate then refuses everyone, because the gate has no configuration either.

**Single tenant only.** ``common`` and ``organizations`` are refused at construction. A shared
historical replay dataset has exactly one tenant that may read it, and "any Entra tenant with
a matching audience" is not an authorization decision anybody made deliberately.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

#: Any 8-4-4-4-12 hex GUID. Tenants and object ids are compared with this, never by substring.
GUID_PATTERN = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)

#: Tenant values that mean "more than one tenant". Refused, by name, so the refusal message
#: can say which convenience was attempted.
MULTI_TENANT_VALUES = frozenset({"common", "organizations", "consumers"})

#: Signature algorithms accepted. An allowlist, never read from a token. Widening this to
#: include an HMAC family is the RS256/HS256 confusion attack: the "secret" would be the
#: published public key. ``none`` needs no explanation.
ALLOWED_ALGORITHMS = ("RS256",)

#: Clock skew tolerance for ``exp``/``nbf``/``iat``, in seconds.
DEFAULT_LEEWAY_SECONDS = 10

#: How long a fetched key set is trusted before a scheduled refresh.
DEFAULT_JWKS_TTL_SECONDS = 3600

#: Minimum gap between *forced* refreshes triggered by an unrecognised key id. Without it an
#: unauthenticated caller sending random key ids buys one outbound fetch per request.
DEFAULT_JWKS_REFRESH_COOLDOWN_SECONDS = 60

#: How long a key set may keep being served after refreshes start failing. Upstream served a
#: stale set for as long as the process lived, which means a revoked signing key stays
#: accepted indefinitely whenever the discovery endpoint is unreachable — an availability
#: nicety that quietly becomes a revocation failure. Six hours is long enough to ride out a
#: provider incident and short enough that a revocation lands the same working day.
DEFAULT_JWKS_MAX_STALE_SECONDS = 6 * 3600

#: The delegated permission a human caller must hold.
DEFAULT_REQUIRED_SCOPE = "access_as_user"


class EntraConfigurationError(ValueError):
    """The configuration cannot describe a safe trust boundary. Never caught to continue."""


@dataclass(frozen=True, slots=True)
class EntraAuthConfig:
    """The tenant, the audience, and the claim rules tokens must satisfy.

    Attributes:
        tenant_id: The one Entra tenant whose tokens are accepted. A GUID; never ``common``.
        client_id: This API's application id. Tokens must be addressed to it.
        extra_audiences: Additional acceptable ``aud`` values beyond the two derived ones.
        required_claims: Claims that must be present and non-empty on every token.
        required_scopes: Delegated permissions a *human* token must carry. Any one satisfies
            the requirement.
        required_roles: Application roles a *service* token must carry, when service tokens
            are allowed at all.
        allow_service_principals: Whether an application authenticating as itself may call
            this API. ``False`` by default: a human-facing analyst surface has no reason to
            accept one, and the failure mode of accidentally accepting it is a caller with
            no user behind it holding a human's access.
        leeway_seconds: Clock skew tolerance.
        jwks_ttl_seconds: Scheduled key-set refresh interval.
        jwks_refresh_cooldown_seconds: Floor between rotation-triggered fetches.
        jwks_max_stale_seconds: Hard ceiling on serving a key set whose refresh is failing.
    """

    tenant_id: str
    client_id: str
    extra_audiences: tuple[str, ...] = field(default_factory=tuple)
    required_claims: tuple[str, ...] = ("oid", "tid")
    required_scopes: tuple[str, ...] = (DEFAULT_REQUIRED_SCOPE,)
    required_roles: tuple[str, ...] = ()
    allow_service_principals: bool = False
    leeway_seconds: int = DEFAULT_LEEWAY_SECONDS
    jwks_ttl_seconds: int = DEFAULT_JWKS_TTL_SECONDS
    jwks_refresh_cooldown_seconds: int = DEFAULT_JWKS_REFRESH_COOLDOWN_SECONDS
    jwks_max_stale_seconds: int = DEFAULT_JWKS_MAX_STALE_SECONDS

    def __post_init__(self) -> None:
        tenant = (self.tenant_id or "").strip().lower()
        if tenant in MULTI_TENANT_VALUES:
            raise EntraConfigurationError(
                f"tenant_id={tenant!r} accepts tokens from more than one Entra tenant. This "
                "component is single-tenant by construction; name the tenant GUID that owns "
                "the data."
            )
        if not GUID_PATTERN.match(tenant):
            raise EntraConfigurationError(
                "tenant_id must be an Entra tenant GUID"
            )
        if not GUID_PATTERN.match((self.client_id or "").strip().lower()):
            raise EntraConfigurationError(
                "client_id must be this API's application id, as a GUID"
            )
        if not self.required_claims:
            raise EntraConfigurationError(
                "required_claims cannot be empty: a token carrying no identity claim yields "
                "callers who all share one identity"
            )
        if self.leeway_seconds < 0 or self.leeway_seconds > 300:
            raise EntraConfigurationError(
                "leeway_seconds must be between 0 and 300; a larger window means an expired "
                "token is still accepted"
            )
        for name in ("jwks_ttl_seconds", "jwks_refresh_cooldown_seconds", "jwks_max_stale_seconds"):
            if getattr(self, name) <= 0:
                raise EntraConfigurationError(f"{name} must be positive")
        if self.jwks_max_stale_seconds < self.jwks_ttl_seconds:
            raise EntraConfigurationError(
                "jwks_max_stale_seconds must not be shorter than jwks_ttl_seconds, or a "
                "healthy cache expires into an immediate hard failure"
            )
        if self.allow_service_principals and not self.required_roles:
            raise EntraConfigurationError(
                "allow_service_principals needs required_roles: an application token with no "
                "role assignment is an unauthorized caller that happens to have a token"
            )

    def audiences(self) -> tuple[str, ...]:
        """Every acceptable ``aud``, in match order.

        Entra issues the bare application id or the ``api://`` form depending on how the
        scope was requested. Accepting one and not the other produces an intermittent
        rejection that reads like a signature failure.
        """
        values = [self.client_id, f"api://{self.client_id}"]
        values.extend(a for a in self.extra_audiences if a and a not in values)
        return tuple(values)

    def authority(self) -> str:
        """The tenant-scoped authority. Built from configuration; never from a token."""
        return f"https://login.microsoftonline.com/{self.tenant_id}"

    def jwks_url(self) -> str:
        """The discovery endpoint for this tenant's signing keys.

        Derived from the configured tenant alone. Nothing in a token — not ``kid``, not
        ``jku``, not ``iss`` — influences which URL is fetched, so no token can point this
        component at a key set an attacker controls.
        """
        return f"{self.authority()}/discovery/v2.0/keys"

    def expected_issuers(self) -> tuple[str, ...]:
        """The two acceptable issuer strings, v2 and v1 forms, exact-matched."""
        return (
            f"https://login.microsoftonline.com/{self.tenant_id}/v2.0",
            f"https://sts.windows.net/{self.tenant_id}/",
        )

    def authorize_endpoint(self) -> str:
        return f"{self.authority()}/oauth2/v2.0/authorize"

    def token_endpoint(self) -> str:
        return f"{self.authority()}/oauth2/v2.0/token"

    def logout_endpoint(self) -> str:
        return f"{self.authority()}/oauth2/v2.0/logout"

    def client_scopes(self) -> tuple[str, ...]:
        """Scopes a sign-in client must request to obtain a token this API accepts."""
        return tuple(f"api://{self.client_id}/{s}" for s in self.required_scopes)

    def public_client_setup(self) -> dict[str, object]:
        """The values a browser needs before it can hold a token.

        Public by construction: an application id, a tenant authority and a scope name are
        all disclosed by the sign-in redirect itself. There is no secret here, and nothing
        about the application's data, configuration or deployment.
        """
        return {
            "clientId": self.client_id,
            "tenantId": self.tenant_id,
            "authority": self.authority(),
            "authorizeEndpoint": self.authorize_endpoint(),
            "tokenEndpoint": self.token_endpoint(),
            "scopes": list(self.client_scopes()),
        }


__all__ = [
    "EntraAuthConfig",
    "EntraConfigurationError",
    "ALLOWED_ALGORITHMS",
    "GUID_PATTERN",
    "MULTI_TENANT_VALUES",
    "DEFAULT_REQUIRED_SCOPE",
    "DEFAULT_JWKS_TTL_SECONDS",
    "DEFAULT_JWKS_REFRESH_COOLDOWN_SECONDS",
    "DEFAULT_JWKS_MAX_STALE_SECONDS",
    "DEFAULT_LEEWAY_SECONDS",
]
