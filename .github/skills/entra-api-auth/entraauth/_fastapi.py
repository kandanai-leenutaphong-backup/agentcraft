"""The web-framework seam — one call wires authentication into an app.

Module role:
    Adapts the framework-free :class:`TokenValidator` to a FastAPI/Starlette
    application: a dependency that yields a :class:`Principal`, exception
    handlers that turn this box's errors into correct HTTP responses, and the
    unauthenticated configuration endpoint a sign-in client needs.

Why the framework import is inside the functions:
    So the box installs, imports and selftests with no web framework present.
    The validator is the capability; this file is a convenience, and a
    convenience must not become a dependency of the thing it is convenient for.

Why there is a scope hand-off:
    Another mechanism may have already authenticated the request — a signed
    developer request, a service-to-service mutual TLS layer, a gateway that
    validated the token in front of the app. Such a mechanism puts a
    :class:`Principal` on the ASGI scope and this dependency returns it
    unchanged. That is what lets a separate access path coexist with Entra
    without either one weakening the other.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from ._config import AuthConfig
from ._errors import AuthError, ForbiddenError, NotFoundError
from ._jwks import Fetcher
from ._principal import Principal
from ._validator import TokenValidator

logger = logging.getLogger(__name__)

# ASGI scope key where a prior mechanism may leave an authenticated principal.
DEFAULT_SCOPE_KEY = "auth_principal"

# Where the sign-in client fetches its configuration. Unauthenticated by
# necessity: a browser cannot present a token before it knows what to ask for.
DEFAULT_SETUP_PATH = "/api/auth_setup"


def install_auth(
    app: Any,
    config: AuthConfig,
    *,
    fetcher: Fetcher | None = None,
    scope_key: str = DEFAULT_SCOPE_KEY,
    setup_path: str | None = DEFAULT_SETUP_PATH,
    validator: TokenValidator | None = None,
) -> TokenValidator:
    """Wire authentication into an application. The whole integration surface.

    Args:
        app: A FastAPI application.
        config: Tenant, audience and policy.
        fetcher: Async key-set fetcher, injected for tests or for a consumer
            with its own HTTP policy.
        scope_key: ASGI scope key consulted before any token inspection.
        setup_path: Where to mount the client-configuration endpoint. ``None``
            skips mounting it.
        validator: A pre-built validator, when one is shared across apps.

    Returns:
        The validator, so the caller can build dependencies from it.

    Side effects:
        Registers three exception handlers and, unless suppressed, one route.
        Logs every configuration warning at startup — including, loudly, that
        authentication is disabled.
    """
    from fastapi import Request
    from fastapi.responses import JSONResponse

    built = validator or TokenValidator(config, fetcher=fetcher)

    for problem in config.warnings():
        logger.warning("auth.config.warning", extra={"problem": problem})

    app.state.auth_config = config
    app.state.auth_validator = built

    async def _auth_error(_request: Request, exc: AuthError) -> JSONResponse:
        headers = {}
        if exc.status_code == 401:
            # RFC 6750: a 401 must say what scheme it wants, or a compliant
            # client has no way to know it should acquire a token.
            headers["WWW-Authenticate"] = "Bearer"
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.reason, "message": exc.public_message},
            headers=headers,
        )

    async def _forbidden(_request: Request, exc: ForbiddenError) -> JSONResponse:
        return JSONResponse(
            status_code=403,
            content={"error": exc.reason, "message": exc.public_message},
        )

    async def _not_found(_request: Request, exc: NotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={"error": "not_found", "message": exc.public_message},
        )

    app.add_exception_handler(AuthError, _auth_error)
    app.add_exception_handler(ForbiddenError, _forbidden)
    app.add_exception_handler(NotFoundError, _not_found)

    if setup_path:
        @app.get(setup_path, tags=["auth"])
        async def auth_setup() -> dict:
            """Public sign-in configuration. Never returns a secret."""
            return config.client_setup()

    logger.info(
        "auth.installed",
        extra={"enabled": config.enabled, "multi_tenant": config.multi_tenant,
               "setup_path": setup_path or ""},
    )
    return built


def principal_dependency(
    validator: TokenValidator,
    *,
    scope_key: str = DEFAULT_SCOPE_KEY,
) -> Callable[..., Any]:
    """Build the FastAPI dependency that yields the authenticated principal.

    Use as ``principal: Principal = Depends(current_principal)``. Routes receive
    an identity and never see a header, a token or a claim.
    """

    from fastapi import Request

    async def current_principal(request: Request) -> Principal:
        existing = request.scope.get(scope_key)
        if isinstance(existing, Principal):
            # Already authenticated upstream. Returning it unchanged is what
            # keeps a second access path from needing a second identity model.
            return existing
        return await validator.authenticate(
            request.headers, dev_identity=request.headers
        )

    # This module uses postponed annotations, so the signature above is the
    # *string* "Request", which FastAPI cannot resolve — the import is local, so
    # it is not in module globals. The symptom is a 422 naming `request` as a
    # missing query parameter, never a 401 (G13). Rebinding the real classes
    # fixes resolution without making the framework a module-level import.
    current_principal.__annotations__ = {"request": Request, "return": Principal}

    return current_principal


def require_scope(scope: str) -> Callable[[Principal], Principal]:
    """Build a guard that rejects a principal lacking a delegated permission.

    A plain callable, applied to an already-resolved principal inside the route:
    ``require_scope("access_as_user")(principal)``. Not a FastAPI dependency —
    it needs the principal, and expressing that as a dependency would mean
    resolving the identity twice per request.
    """

    def _check(principal: Principal) -> Principal:
        if not principal.has_scope(scope):
            raise ForbiddenError(
                "missing_scope", f"scope {scope!r} not granted", scope=scope,
                principal_id=principal.id,
            )
        return principal

    return _check


def require_role(role: str) -> Callable[[Principal], Principal]:
    """Build a guard that rejects a principal lacking an application role.

    Applied to a resolved principal, like :func:`require_scope`.
    """

    def _check(principal: Principal) -> Principal:
        if not principal.has_role(role):
            raise ForbiddenError(
                "missing_role", f"role {role!r} not assigned", role=role,
                principal_id=principal.id,
            )
        return principal

    return _check


__all__ = [
    "install_auth",
    "principal_dependency",
    "require_scope",
    "require_role",
    "DEFAULT_SCOPE_KEY",
    "DEFAULT_SETUP_PATH",
]
