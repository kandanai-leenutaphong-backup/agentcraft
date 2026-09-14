"""AuthConfig — tenant, audience and policy, read once and frozen.

Module role:
    The only place this box reads the environment. Validation, the dependency
    and the ownership guards all take a config instance; none of them reaches
    for a global.

Why the dev switch lives here:
    ``enabled=False`` is a real operating mode — it makes every request an
    anonymous or header-declared identity with no token at all. That is the
    single most dangerous value in the box, so it sits next to the checks that
    catch it being wrong (:meth:`warnings`, :meth:`require_enabled`) rather than
    in an ambient settings object nobody audits.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any

# Entra ID v1 and v2 issuer forms. Used for multi-tenant, where the tenant GUID
# cannot be known ahead of time and only the shape can be asserted.
ISSUER_PATTERN = re.compile(
    r"^https://(?:login\.microsoftonline\.com|sts\.windows\.net)/"
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}(?:/v2\.0)?/?$"
)

# Any 8-4-4-4-12 hex GUID, used to compare tenants across issuer formats.
GUID_PATTERN = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
)

# The tenant value meaning "any Entra tenant".
MULTI_TENANT = "common"

DEFAULT_ENV_PREFIX = "AUTH_"

# Signature algorithms accepted, as an allowlist. Never widen this, and never
# read it from a token: an empty or attacker-influenced algorithm list is the
# `alg: none` and HS256-confusion family of attacks.
ALLOWED_ALGORITHMS = ("RS256",)

# Clock skew tolerance for exp / nbf / iat, in seconds. Small enough that an
# expired token is still expired, large enough that a host drifting by a few
# seconds does not reject every request (G9).
DEFAULT_LEEWAY_SECONDS = 10

# How long a fetched key set is trusted before a scheduled refresh.
DEFAULT_JWKS_TTL_SECONDS = 86400

# Minimum gap between *forced* refreshes triggered by an unrecognised key id.
# Without it, an unauthenticated caller sending random key ids drives one
# outbound fetch per request (G10).
DEFAULT_JWKS_REFRESH_COOLDOWN_SECONDS = 60


@dataclass(frozen=True)
class AuthConfig:
    """Who is trusted to issue tokens, and who they must be addressed to.

    Attributes:
        enabled: When ``False``, no token is inspected and every caller becomes
            a development identity. Never ship this true-to-life.
        tenant_id: Entra tenant GUID, or ``"common"`` for multi-tenant.
        client_id: This API's application id. Tokens must be addressed to it.
        extra_audiences: Additional acceptable ``aud`` values, beyond
            ``client_id`` and ``api://<client_id>``.
        required_claims: Claims that must be present and non-empty. ``oid`` is
            required by default because a token without it produces users who
            all share the same empty identity (G3).
        jwks_ttl_seconds: Scheduled key-set refresh interval.
        jwks_refresh_cooldown_seconds: Floor between rotation-triggered fetches.
        leeway_seconds: Clock skew tolerance.
        dev_identity_headers: In disabled mode, the headers that name the
            caller. Ignored entirely when enabled.
    """

    enabled: bool
    tenant_id: str = ""
    client_id: str = ""
    extra_audiences: tuple[str, ...] = field(default_factory=tuple)
    required_claims: tuple[str, ...] = ("oid",)
    jwks_ttl_seconds: int = DEFAULT_JWKS_TTL_SECONDS
    jwks_refresh_cooldown_seconds: int = DEFAULT_JWKS_REFRESH_COOLDOWN_SECONDS
    leeway_seconds: int = DEFAULT_LEEWAY_SECONDS
    dev_identity_headers: bool = True

    def __post_init__(self) -> None:
        """Reject configurations that cannot validate a token.

        Only checked when enabled: a disabled config legitimately has no tenant
        and no client id, and raising on that would make local development
        require Entra registration to boot.
        """
        if not self.enabled:
            return
        if not self.tenant_id:
            raise ValueError(
                "AuthConfig requires 'tenant_id' when enabled — an Entra tenant "
                "GUID, or 'common' for multi-tenant."
            )
        if not self.client_id:
            raise ValueError(
                "AuthConfig requires 'client_id' when enabled — this API's "
                "application id, which tokens must be addressed to."
            )
        if self.tenant_id != MULTI_TENANT and not GUID_PATTERN.fullmatch(self.tenant_id):
            raise ValueError(
                f"AuthConfig 'tenant_id' must be a GUID or {MULTI_TENANT!r}, got "
                f"{self.tenant_id!r}."
            )
        if self.leeway_seconds < 0:
            raise ValueError("AuthConfig 'leeway_seconds' cannot be negative.")
        if not self.required_claims:
            raise ValueError(
                "AuthConfig 'required_claims' cannot be empty — a token with no "
                "identity claim yields users who all share one identity (G3)."
            )

    @property
    def multi_tenant(self) -> bool:
        """True when tokens from any Entra tenant are accepted."""
        return self.tenant_id == MULTI_TENANT

    def audiences(self) -> list[str]:
        """Every acceptable ``aud`` value, in match order.

        Both the bare application id and the ``api://`` form are accepted
        because which one Entra issues depends on how the scope was requested,
        and accepting only one produces an audience rejection that reads like a
        signature failure (G5).
        """
        values = [self.client_id, f"api://{self.client_id}"]
        values.extend(a for a in self.extra_audiences if a and a not in values)
        return values

    def jwks_url(self) -> str:
        """The discovery endpoint for this tenant's signing keys."""
        return (
            f"https://login.microsoftonline.com/{self.tenant_id}"
            f"/discovery/v2.0/keys"
        )

    def expected_issuers(self) -> tuple[str, ...]:
        """Acceptable issuers for a single-tenant config, v2 and v1 forms.

        Empty for multi-tenant, where the issuer is checked by shape instead.
        """
        if self.multi_tenant:
            return ()
        return (
            f"https://login.microsoftonline.com/{self.tenant_id}/v2.0",
            f"https://sts.windows.net/{self.tenant_id}/",
        )

    def warnings(self) -> list[str]:
        """Non-fatal risks, most dangerous first. Log these at startup."""
        problems: list[str] = []
        if not self.enabled:
            problems.append(
                "auth is DISABLED — every request is granted a development "
                "identity with no token. This must never be the state of a "
                "deployed environment (G11)."
            )
        if self.enabled and self.dev_identity_headers:
            # Harmless — the headers are unreachable when enabled — but the
            # combination reads as if it were meaningful, so say that it is not.
            problems.append(
                "dev_identity_headers is set while auth is enabled; it has no "
                "effect and is ignored."
            )
        if self.multi_tenant:
            problems.append(
                "tenant is 'common' — tokens from ANY Entra tenant are accepted "
                "once the audience matches. Authorisation must be enforced "
                "elsewhere, per user or per tenant."
            )
        return problems

    def require_enabled(self) -> None:
        """Raise unless auth is on. Call from a production startup path.

        The one line that turns G11 from an outage into a failed boot. A service
        that starts with authentication disabled will serve every request
        successfully, which is why nothing else catches it.
        """
        if not self.enabled:
            raise RuntimeError(
                "Authentication is disabled but this environment requires it. "
                "Set AUTH_ENABLED=true, or remove the require_enabled() call if "
                "this really is a development host."
            )

    @classmethod
    def from_env(
        cls,
        env: dict[str, str] | None = None,
        *,
        prefix: str = DEFAULT_ENV_PREFIX,
    ) -> AuthConfig:
        """Build from environment variables. The only env read in this box.

        Reads ``<prefix>ENABLED``, ``<prefix>TENANT_ID``, ``<prefix>CLIENT_ID``
        and ``<prefix>EXTRA_AUDIENCES`` (comma-separated).

        ``ENABLED`` is true only for an explicit affirmative value. Anything
        unrecognised is false, so a typo fails closed into a service that
        rejects requests rather than one that accepts all of them.
        """
        source: Any = os.environ if env is None else env
        raw_enabled = (source.get(f"{prefix}ENABLED") or "").strip().lower()
        enabled = raw_enabled in {"1", "true", "yes", "on"}

        raw_audiences = (source.get(f"{prefix}EXTRA_AUDIENCES") or "").strip()
        extra = tuple(a.strip() for a in raw_audiences.split(",") if a.strip())

        return cls(
            enabled=enabled,
            tenant_id=(source.get(f"{prefix}TENANT_ID") or "").strip(),
            client_id=(source.get(f"{prefix}CLIENT_ID") or "").strip(),
            extra_audiences=extra,
        )

    def client_setup(self) -> dict[str, Any]:
        """Public configuration a sign-in client needs before it has a token.

        Served unauthenticated by definition: a browser cannot acquire a token
        until it knows the authority and scope to ask for. Contains only values
        that are public by design — no secret, and nothing about the tenant that
        the sign-in redirect would not already reveal.
        """
        if not self.enabled:
            return {"useLogin": False}
        return {
            "useLogin": True,
            "clientId": self.client_id,
            "authority": f"https://login.microsoftonline.com/{self.tenant_id}",
            "scopes": [f"api://{self.client_id}/access_as_user"],
        }


__all__ = [
    "AuthConfig",
    "ALLOWED_ALGORITHMS",
    "DEFAULT_ENV_PREFIX",
    "GUID_PATTERN",
    "ISSUER_PATTERN",
    "MULTI_TENANT",
]
