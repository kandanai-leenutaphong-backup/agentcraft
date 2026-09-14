"""entraauth — validate Entra ID access tokens, and decide what is whose.

Two capabilities, deliberately separate:

    validator = TokenValidator(AuthConfig.from_env())
    principal = await validator.authenticate(request.headers)   # who
    DEFAULT_POLICY.assert_writable(record.owner_id, principal, "delete")  # what

Authentication proves the caller's identity. Ownership decides whether this
record is theirs. Collapsing them into one check is how an API ends up serving
another tenant's data to a perfectly valid token.

The core is framework-free and imports no web framework. ``install_auth(app,
config)`` adapts it to FastAPI in one call, importing the framework lazily so
the box installs and selftests without it.
"""

from __future__ import annotations

from ._config import (
    ALLOWED_ALGORITHMS,
    DEFAULT_ENV_PREFIX,
    MULTI_TENANT,
    AuthConfig,
)
from ._errors import AuthError, ForbiddenError, NotFoundError
from ._fastapi import (
    DEFAULT_SCOPE_KEY,
    DEFAULT_SETUP_PATH,
    install_auth,
    principal_dependency,
    require_role,
    require_scope,
)
from ._jwks import JWKSCache, build_rsa_pem, default_fetcher
from ._ownership import DEFAULT_POLICY, DEFAULT_SHARED_OWNER, OwnershipPolicy
from ._principal import (
    KIND_DEVELOPER,
    KIND_SERVICE,
    KIND_USER,
    Principal,
    developer_principal,
    principal_from_claims,
)
from ._validator import TokenValidator

__version__ = "1.0.0"

__all__ = [
    # configuration
    "AuthConfig",
    "ALLOWED_ALGORITHMS",
    "DEFAULT_ENV_PREFIX",
    "MULTI_TENANT",
    # identity
    "Principal",
    "principal_from_claims",
    "developer_principal",
    "KIND_USER",
    "KIND_SERVICE",
    "KIND_DEVELOPER",
    # validation
    "TokenValidator",
    "JWKSCache",
    "build_rsa_pem",
    "default_fetcher",
    # authorisation
    "OwnershipPolicy",
    "DEFAULT_POLICY",
    "DEFAULT_SHARED_OWNER",
    # errors
    "AuthError",
    "ForbiddenError",
    "NotFoundError",
    # framework seam
    "install_auth",
    "principal_dependency",
    "require_scope",
    "require_role",
    "DEFAULT_SCOPE_KEY",
    "DEFAULT_SETUP_PATH",
    "__version__",
]
