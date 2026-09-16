from collections.abc import Callable
from typing import Any

import jwt

from .contracts import Refusal, authorize_verified_claims


CLI_CLIENT_ID = "04b07795-8ddb-461a-bbee-02f9e1bf7b46"


class AuthenticationError(Refusal):
    pass


class JwtGate:
    def __init__(self, tenant_id: str, principal_id: str, audience: str, key_resolver: Callable | None = None):
        self.tenant_id = tenant_id
        self.principal_id = principal_id
        self.audience = audience
        self.issuer = f"https://login.microsoftonline.com/{tenant_id}/v2.0"
        self.jwks = jwt.PyJWKClient(
            f"https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys",
            cache_keys=True,
            lifespan=300,
            timeout=10,
        )
        self.key_resolver = key_resolver or (lambda token: self.jwks.get_signing_key_from_jwt(token).key)

    def authenticate(self, authorization: str | None) -> dict[str, Any]:
        if not authorization or not authorization.startswith("Bearer ") or len(authorization) > 20000:
            raise AuthenticationError("An Entra bearer token for this API is required")
        token = authorization[7:]
        try:
            header = jwt.get_unverified_header(token)
            if header.get("alg") != "RS256" or not header.get("kid"):
                raise AuthenticationError("Unsupported bearer token")
            claims = jwt.decode(
                token,
                self.key_resolver(token),
                algorithms=["RS256"],
                audience=self.audience,
                issuer=self.issuer,
                leeway=15,
                options={"require": ["exp", "nbf", "iat", "iss", "aud", "tid", "oid"]},
            )
        except (jwt.PyJWTError, ValueError, TypeError) as error:
            raise AuthenticationError("Bearer token validation failed") from error
        authorize_verified_claims(claims, self.tenant_id, self.principal_id)
        if claims.get("azp") != CLI_CLIENT_ID or "access_as_user" not in claims.get("scp", "").split():
            raise Refusal("Caller application or delegated scope is not allowed")
        return claims