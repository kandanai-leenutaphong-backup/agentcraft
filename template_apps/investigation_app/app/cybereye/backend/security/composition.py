"""Composition of the security edge. The only file that decides what is mounted.

Three mechanisms, one principal, one gate:

    request -> SignedRequestASGIMiddleware   authenticates a signature, or refuses it
            -> AuthorizationGate             refuses anything with no principal at all
            -> CookieCrossSiteGuard          refuses an unsafe request carried by a cookie
                                             that did not come from this origin
            -> CORSMiddleware                exact trusted origins
            -> the application

The signing middleware runs outside the gate because it produces the principal the gate reads.
It never denies an unsigned request; the gate does that, once, for every mechanism. Nothing is
authenticated twice.

Microsoft Entra ID plugs in as two gate *resolvers* rather than as another layer: a bearer
token on the request, and a browser session cookie minted only after such a token was
validated. Both produce the same :class:`Principal`, so the application below has no idea
which way somebody came in — which is the property that keeps ownership checks singular.

Order in Starlette is the reverse of registration — the last middleware added is outermost —
so :func:`install_security` must be called *after* the application has added CORS.

The gate is installed unconditionally. Both mechanisms are conditional on their configuration,
and when neither is configured the application authenticates nobody and therefore serves
nobody. That is the intended failure mode: a deployment that forgets to configure
authentication is unusable rather than open.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from fastapi import HTTPException, Request

from app.components.entra_auth import (
    AzureTableRecordStore,
    RecordStore,
    TokenValidator,
)
from app.components.signed_dev_access import (
    AzureTableReplayLedger,
    InProcessReplayLedger,
    ReplayLedger,
    install_signed_request_auth,
    public_key_fingerprint,
)

from .config import (
    LEDGER_AZURE_TABLE,
    LEDGER_IN_PROCESS,
    SecurityConfigurationError,
    SecuritySettings,
)
from .entra import (
    FLOW_PARTITION,
    SESSION_PARTITION,
    BrowserSessions,
    CookieCrossSiteGuard,
    bearer_resolver,
    build_entra_config,
    cookie_resolver,
)
from .gate import SCOPE_KEY, AuthorizationGate, PrincipalResolver, PublicRoute, ResolverRegistry
from .principal import Principal, signed_developer_principal
from .signin_routes import PUBLIC_ROUTES, SIGN_IN_PATH, build_signin_router

#: Where the composition result is published for routes, tests and operational reporting.
STATE_KEY = "security"


@dataclass(frozen=True, slots=True)
class SecurityComposition:
    """What was actually mounted. Reported, never inferred from configuration."""

    settings: SecuritySettings
    resolvers: ResolverRegistry
    signed_access_mounted: bool
    key_fingerprint: str
    replay_ledger: ReplayLedger | None
    entra_mounted: bool = False
    sessions: BrowserSessions | None = None
    validator: TokenValidator | None = None

    def describe(self) -> dict[str, Any]:
        """Non-secret summary for a status surface. Never includes key material."""
        return {
            **self.settings.describe(fingerprint=self.key_fingerprint),
            "signed_access_mounted": self.signed_access_mounted,
            "entra_mounted": self.entra_mounted,
            "primary_auth_mechanisms": len(self.resolvers),
        }


def build_replay_ledger(settings: SecuritySettings) -> ReplayLedger | None:
    """Build the ledger the configuration names, or ``None`` when no signing key is set.

    There is no fallback path. A ledger that cannot be built raises, because the only way to
    continue would be to accept signed requests without replay protection.
    """
    if not settings.signed_access_configured:
        return None
    if settings.ledger_kind == LEDGER_AZURE_TABLE:
        return AzureTableReplayLedger(
            endpoint=settings.table_endpoint,
            table_name=settings.table_name,
        )
    if settings.ledger_kind == LEDGER_IN_PROCESS:
        return InProcessReplayLedger()
    raise SecurityConfigurationError(f"unknown replay ledger {settings.ledger_kind!r}")


def build_browser_sessions(
    settings: SecuritySettings,
    *,
    session_store: RecordStore | None = None,
    flow_store: RecordStore | None = None,
) -> BrowserSessions:
    """Build the browser-session machinery over the dedicated authentication table.

    Sessions and in-progress flows share one table and never one partition: they have
    different lifetimes and very different consequences if one is read.
    """
    sessions = session_store or AzureTableRecordStore(
        endpoint=settings.session_table_endpoint,
        table_name=settings.session_table_name,
        partition_key=SESSION_PARTITION,
    )
    flows = flow_store or AzureTableRecordStore(
        endpoint=settings.session_table_endpoint,
        table_name=settings.session_table_name,
        partition_key=FLOW_PARTITION,
    )
    return BrowserSessions(
        store=sessions,
        flow_store=flows,
        max_lifetime=timedelta(hours=settings.session_max_hours),
    )


def install_security(
    app,
    *,
    settings: SecuritySettings | None = None,
    replay_ledger: ReplayLedger | None = None,
    validator: TokenValidator | None = None,
    sessions: BrowserSessions | None = None,
) -> SecurityComposition:
    """Mount the authorization gate, signed developer access, and Entra sign-in.

    Args:
        app: The FastAPI application, with its own middleware already added.
        settings: Resolved configuration. Read from the environment when omitted.
        replay_ledger: Pre-built ledger, injected by tests. Built from settings otherwise.
        validator: Pre-built token validator, injected by tests so the whole Entra path can be
            exercised against minted keys with no tenant and no network.
        sessions: Pre-built browser sessions, injected by tests.

    Returns:
        What was mounted, also published at ``app.state.security``.
    """
    resolved = settings if settings is not None else SecuritySettings.from_env()
    ledger = replay_ledger if replay_ledger is not None else build_replay_ledger(resolved)
    fingerprint = public_key_fingerprint(resolved.public_key_b64)

    if resolved.signed_access_configured and not fingerprint:
        raise SecurityConfigurationError(
            "DEV_PUBLIC_KEY_ED25519 is not a base64-encoded 32-byte Ed25519 public key"
        )

    entra_mounted = resolved.entra_configured or validator is not None
    live_validator = validator
    live_sessions = sessions
    if entra_mounted:
        live_validator = validator or TokenValidator(build_entra_config(resolved))
        live_sessions = sessions or build_browser_sessions(resolved)
        # Registered first, so it ends up innermost: it must run after the gate has decided
        # who the caller is, because whether a cookie carried them is what it acts on.
        app.add_middleware(CookieCrossSiteGuard, expected_origin=resolved.public_origin)

    registry = ResolverRegistry()
    app.add_middleware(
        AuthorizationGate,
        resolvers=registry,
        public_routes=PUBLIC_ROUTES if entra_mounted else (),
        sign_in_path=SIGN_IN_PATH if entra_mounted else None,
    )

    mounted = False
    if resolved.signed_access_configured:
        if ledger is None:
            raise SecurityConfigurationError("a signing key is configured but no replay ledger")
        mounted = install_signed_request_auth(
            app,
            public_key_b64=resolved.public_key_b64,
            identity_factory=lambda slug: signed_developer_principal(
                fingerprint=fingerprint, slug=slug,
            ),
            replay_ledger=ledger,
            scope_key=SCOPE_KEY,
        )

    if entra_mounted:
        assert live_validator is not None and live_sessions is not None
        # Order matters only for cost: a bearer token is validated cryptographically, a cookie
        # is one store read, and most requests from a browser carry the cookie.
        registry.add(cookie_resolver(live_sessions))
        registry.add(bearer_resolver(live_validator))
        app.include_router(
            build_signin_router(
                settings=resolved, validator=live_validator, sessions=live_sessions,
            )
        )

    composition = SecurityComposition(
        settings=resolved,
        resolvers=registry,
        signed_access_mounted=mounted,
        key_fingerprint=fingerprint,
        replay_ledger=ledger,
        entra_mounted=entra_mounted,
        sessions=live_sessions,
        validator=live_validator,
    )
    setattr(app.state, STATE_KEY, composition)
    return composition


def register_principal_resolver(app, resolver: PrincipalResolver) -> None:
    """Add a primary-authentication mechanism. The seam the Entra work fills.

    A resolver receives the raw ASGI scope and returns a :class:`Principal` or ``None``. It is
    registered in process, by code, never by a configuration value — so no deployed setting can
    introduce one, and none can remove the gate.
    """
    composition: SecurityComposition = getattr(app.state, STATE_KEY)
    composition.resolvers.add(resolver)


def current_principal(request: Request) -> Principal:
    """FastAPI dependency yielding the authenticated caller.

    Unreachable without a principal in a correctly composed application: the gate refuses
    first. It raises rather than inventing a default anyway, so a future composition mistake
    fails closed instead of serving an anonymous caller under a shared identity.
    """
    principal = request.scope.get(SCOPE_KEY)
    if not isinstance(principal, Principal):
        raise HTTPException(status_code=401)
    return principal
