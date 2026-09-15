"""The CyberEye security edge: one principal model, one gate, three ways in.

Read this file to know the whole surface; read the modules for why each piece is shaped the
way it is.

- ``principal`` — :class:`Principal` and the two namespaced constructors. The only identity
  type in the application.
- ``gate`` — :class:`AuthorizationGate`, deny-by-default at the ASGI edge, with no switch that
  turns it off, plus the exact public-route allowlist sign-in needs.
- ``entra`` — Microsoft Entra ID mapped onto this application's principal: a bearer resolver, a
  browser-session resolver, and the cross-site guard cookies require.
- ``signin_routes`` — the four public routes a person signs in through, and ``/api/whoami``.
- ``composition`` — what gets mounted, and :func:`register_principal_resolver`.
- ``config`` — the environment variables, validated loudly at startup.
- ``sessions`` — chat sessions and scan results, owned by the principal that created them.

Signed developer access is provided by ``app.components.signed_dev_access`` and token
validation by ``app.components.entra_auth``. Both own their cryptography and neither knows
anything about this application.
"""

from .composition import (
    STATE_KEY,
    SecurityComposition,
    build_browser_sessions,
    build_replay_ledger,
    current_principal,
    install_security,
    register_principal_resolver,
)
from .config import (
    ENTRA_CLIENT_VAR,
    ENTRA_TENANT_VAR,
    LEDGER_AZURE_TABLE,
    LEDGER_IN_PROCESS,
    PUBLIC_KEY_VAR,
    PUBLIC_ORIGIN_VAR,
    SESSION_TABLE_ENDPOINT_VAR,
    SecurityConfigurationError,
    SecuritySettings,
)
from .entra import (
    FLOW_COOKIE,
    SESSION_COOKIE,
    BrowserSessions,
    CookieCrossSiteGuard,
    bearer_resolver,
    build_entra_config,
    cookie_resolver,
    principal_from_token,
)
from .gate import (
    PUBLIC_PROBE_PATH,
    SCOPE_KEY,
    AuthorizationGate,
    PrincipalResolver,
    PublicRoute,
    ResolverRegistry,
    safe_return_path,
)
from .principal import (
    ISSUER_ENTRA,
    ISSUER_SIGNED_DEV,
    KIND_SERVICE,
    KIND_USER,
    Principal,
    entra_principal,
    signed_developer_principal,
)
from .sessions import ChatSession, OwnedCache, SessionStore
from .signin_routes import PUBLIC_ROUTES, SIGN_IN_PATH, build_signin_router

__all__ = [
    "AuthorizationGate",
    "BrowserSessions",
    "ChatSession",
    "CookieCrossSiteGuard",
    "ENTRA_CLIENT_VAR",
    "ENTRA_TENANT_VAR",
    "FLOW_COOKIE",
    "ISSUER_ENTRA",
    "ISSUER_SIGNED_DEV",
    "KIND_SERVICE",
    "KIND_USER",
    "LEDGER_AZURE_TABLE",
    "LEDGER_IN_PROCESS",
    "OwnedCache",
    "PUBLIC_KEY_VAR",
    "PUBLIC_ORIGIN_VAR",
    "PUBLIC_PROBE_PATH",
    "PUBLIC_ROUTES",
    "Principal",
    "PrincipalResolver",
    "PublicRoute",
    "ResolverRegistry",
    "SCOPE_KEY",
    "SESSION_COOKIE",
    "SESSION_TABLE_ENDPOINT_VAR",
    "SIGN_IN_PATH",
    "STATE_KEY",
    "SecurityComposition",
    "SecurityConfigurationError",
    "SecuritySettings",
    "SessionStore",
    "bearer_resolver",
    "build_browser_sessions",
    "build_entra_config",
    "build_replay_ledger",
    "build_signin_router",
    "cookie_resolver",
    "current_principal",
    "entra_principal",
    "install_security",
    "principal_from_token",
    "register_principal_resolver",
    "safe_return_path",
    "signed_developer_principal",
]
