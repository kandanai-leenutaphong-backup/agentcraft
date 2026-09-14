"""Composition root — settings, access bundle, explorer, routes, static, guard.

WHAT THE ROUTES PROMISE
-----------------------
``GET /api/tree``, ``GET /api/content`` and ``GET /api/search`` answer **200
whenever the process can serve**. A dark branch is data. The only non-200
answers are ``400`` for a node id this server did not mint or a search term
outside its bounds, ``401`` for a missing principal, and ``503`` from
readiness.

A 400 body echoes nothing. Reflecting a submitted token, or any fragment
decoded out of it, would turn the endpoints that accept client input into a
reflection surface for no benefit — the client already has the token.

``GET /health/ready`` **must not depend on Azure reachability**. A fully 403'd
estate is a *healthy* explorer showing forbidden branches; a readiness probe
that failed on it would restart the one process still able to explain the
problem. Readiness asks two local questions — did settings parse, is the SPA
on disk — and its body carries no resource, subscription or tenant identifier.

A missing ``frontend/dist`` serves a placeholder rather than crashing. The
backend is deployable before the frontend exists, and a process that refuses
to start because a static file is absent cannot report anything at all.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from resource_explorer_api.contracts import (
    ContentResponse,
    InvalidNodeError,
    InvalidQueryError,
    LiveHealth,
    ReadyHealth,
    SearchResponse,
    TreeResponse,
)
from resource_explorer_api.discovery import build_access
from resource_explorer_api.nodes import InvalidNode, token_digest
from resource_explorer_api.security import PrincipalGuard
from resource_explorer_api.settings import MAX_SEARCH_HITS, Settings
from resource_explorer_api.tree import ExplorerService, InvalidQuery

logger = logging.getLogger(__name__)

#: Sent with every protected response. The payload names resources in a
#: subscription and can carry their contents; a shared cache holding it for
#: the next viewer is a disclosure, and ``private`` alone would still permit a
#: browser store.
NO_STORE = "no-store, private"

PROTECTED_HEADERS = {"Cache-Control": NO_STORE, "Vary": "Cookie"}

PLACEHOLDER_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Azure resource explorer</title></head>
<body style="font-family:system-ui;margin:3rem;max-width:40rem">
<h1>The SPA is not built</h1>
<p>The API is running. No <code>frontend/dist</code> was found, so there is
nothing to render here yet.</p>
<p>The tree is at <code>/api/tree</code>, one node's contents at
<code>/api/content</code>, and estate search at <code>/api/search</code>.</p>
</body></html>
"""


def create_app(
    settings: Settings | None = None,
    access: Any | None = None,
) -> FastAPI:
    """Build the application. Never raises on a bad environment."""
    settings_error: str | None = None
    try:
        resolved = settings if settings is not None else Settings.from_env()
    except Exception:  # noqa: BLE001 - an unreadable environment is a 503, not a crash
        logger.exception("settings could not be parsed")
        resolved = Settings()
        settings_error = "settings"

    app = FastAPI(
        title="Azure resource explorer",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )

    bundle = access if access is not None else build_access(resolved)
    explorer = ExplorerService(settings=resolved, access=bundle)

    app.state.settings = resolved
    app.state.settings_error = settings_error
    app.state.access = bundle
    app.state.explorer = explorer

    _register_routes(app, resolved, explorer, settings_error)
    _register_static(app, resolved)

    # Added last so it wraps routing: the guard must decide before the router
    # does, or an unknown path answers 404 and confirms what exists.
    app.add_middleware(PrincipalGuard, dev_principal=resolved.dev_principal)
    return app


def _register_routes(
    app: FastAPI,
    settings: Settings,
    explorer: ExplorerService,
    settings_error: str | None,
) -> None:
    @app.get("/api/tree", response_model=TreeResponse)
    async def read_tree(
        response: Response,
        node: str | None = Query(default=None),
    ) -> Any:
        _protect(response)
        try:
            return await explorer.expand(node)
        except InvalidNode:
            return _rejected_node(node)

    @app.get("/api/content", response_model=ContentResponse)
    async def read_content(
        response: Response,
        node: str = Query(default=""),
    ) -> Any:
        _protect(response)
        try:
            return await explorer.read_content(node)
        except InvalidNode:
            return _rejected_node(node)

    @app.get("/api/search", response_model=SearchResponse)
    async def search(
        response: Response,
        q: str = Query(default=""),
        limit: int = Query(default=MAX_SEARCH_HITS, ge=1, le=MAX_SEARCH_HITS),
    ) -> Any:
        _protect(response)
        try:
            return await explorer.search(q, limit)
        except InvalidQuery:
            logger.debug("rejected a search term")
            return JSONResponse(
                status_code=400,
                content=InvalidQueryError().model_dump(by_alias=True),
                headers=PROTECTED_HEADERS,
            )

    @app.get("/health/live", response_model=LiveHealth)
    async def live() -> LiveHealth:
        # No settings read, no registry touched, no Azure call. Liveness that
        # depends on a dependency restarts a healthy process.
        return LiveHealth()

    @app.get("/health/ready", response_model=ReadyHealth)
    async def ready() -> Any:
        if settings_error is not None:
            return JSONResponse(
                status_code=503, content={"status": "not-ready", "reason": "settings"}
            )
        if not settings.static_ready:
            return JSONResponse(
                status_code=503, content={"status": "not-ready", "reason": "static"}
            )
        return ReadyHealth()

    @app.get("/", response_class=HTMLResponse)
    async def index() -> Any:
        if settings.static_ready:
            return FileResponse(settings.index_path, headers=PROTECTED_HEADERS)
        return HTMLResponse(PLACEHOLDER_HTML, headers=PROTECTED_HEADERS)


def _protect(response: Response) -> None:
    response.headers["Cache-Control"] = NO_STORE
    response.headers["Vary"] = "Cookie"


def _rejected_node(node: str | None) -> JSONResponse:
    logger.debug("rejected node id sha256:%s", token_digest(node or ""))
    return JSONResponse(
        status_code=400,
        content=InvalidNodeError().model_dump(by_alias=True),
        headers=PROTECTED_HEADERS,
    )


def _register_static(app: FastAPI, settings: Settings) -> None:
    # Resolved per request, not at startup: the SPA is built after the image
    # layer that installs this package, and a start-time mount would 404 every
    # asset until the process was restarted.
    @app.get("/assets/{asset_path:path}", include_in_schema=False)
    async def asset(asset_path: str) -> FileResponse:
        assets = settings.assets_dir.resolve()
        candidate = (assets / asset_path).resolve()
        if not candidate.is_relative_to(assets) or not candidate.is_file():
            raise HTTPException(status_code=404)
        return FileResponse(candidate, headers=PROTECTED_HEADERS)


app = create_app()

__all__ = ["NO_STORE", "PLACEHOLDER_HTML", "PROTECTED_HEADERS", "app", "create_app"]
