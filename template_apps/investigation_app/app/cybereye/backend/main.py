"""FastAPI composition root for the CyberEye application.

Nothing is defined here that a route could own. This module builds the application,
installs the access edge, composes the services every router reads from `app.state`,
and mounts the built frontend.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from azure.identity import DefaultAzureCredential
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.components.resource_explorer import SELECTION_HEADER, build_inventory_router

from .agents import AgentService, load_agent_spec
from .agents.editor import AgentEditor
from .api import ROUTERS
from .api.dependencies import inventory_service
from .config import settings
from .data import GraphService, ReadOnlyAdx
from .inventory import build_service as build_inventory_service
from .investigation import Scanner, load_configuration
from .models import ScanResponse
from .security import OwnedCache, SessionStore, install_security


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.validate()
    agent_spec = load_agent_spec()
    with DefaultAzureCredential(exclude_interactive_browser_credential=True) as credential:
        adx = ReadOnlyAdx(credential=credential)
        try:
            scanner = Scanner(adx, load_configuration(Path(settings.detector_config_path)))
            app.state.adx = adx
            app.state.scanner = scanner
            app.state.agent = AgentService(adx, scanner, agent_spec)
            app.state.agent_editor = AgentEditor(Path(settings.agent_store_dir), agent_spec, settings.agent_models)
            app.state.graph = GraphService()
            app.state.inventory = build_inventory_service()
            app.state.sessions = SessionStore()
            app.state.last_scan = OwnedCache[ScanResponse]()
            yield
        finally:
            adx.close()


app = FastAPI(
    title="CyberEye Local",
    version="1.0.0",
    description="Historical replay scanner, evidence board, and ADX-equipped investigation agent.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT"],
    allow_headers=["Content-Type", "Accept", SELECTION_HEADER],
)

# Added last, so it runs first: Starlette builds the stack in reverse registration order. The
# gate refuses every unauthenticated request before routing, before body parsing and before
# the static mount, and signed developer access sits outside it because it produces the
# principal the gate reads. Both are unconditional edges; only the signing key is optional,
# and without it no signed authorizing path exists at all.
security = install_security(app)

# The inventory is a component contribution: a bounded, read-only router over a
# registry this application composes. Its own auth, static mounts and settings
# are deliberately not adopted — this application already owns all three.
app.include_router(build_inventory_router(inventory_service))

for _router in ROUTERS:
    app.include_router(_router)

FRONTEND_DIST = settings.app_root / "frontend" / "dist"
if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
