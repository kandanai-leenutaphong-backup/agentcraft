"""FastAPI composition root for the CyberEye application.

Nothing is defined here that a route could own. This module builds the application,
installs the access edge, composes the services every router reads from `app.state`,
and mounts the built frontend.
"""

from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from azdata import ConnectorConfig, Limits, Policy, ResourceAddress
from azure.identity.aio import DefaultAzureCredential
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from resource_explorer import SELECTION_HEADER, build_inventory_router

from .agents import AgentService, load_agent_spec
from .agents.editor import AgentEditor
from .api import ROUTERS
from .api.dependencies import inventory_service
from .config import settings
from .data import GraphService, ReadOnlyAdx
from .data.graph_binding import bind_graph
from .inventory import build_service as build_inventory_service
from .inventory import default_probes
from .investigation import Scanner, load_configuration
from .knowledge import search as knowledge_search
from .models import ScanResponse
from .security import OwnedCache, SessionStore, install_security


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.validate()
    agent_spec = load_agent_spec()
    async with DefaultAzureCredential(exclude_interactive_browser_credential=True) as credential:
        adx = ReadOnlyAdx(credential=credential)
        knowledge = None
        graph = None
        agent = None
        probes = {}
        try:
            search_config = (ConnectorConfig(settings.search_endpoint,
                             ResourceAddress({"index": settings.knowledge_index}),
                             (urlsplit(settings.search_endpoint).hostname or "",))
                             if settings.search_endpoint and settings.knowledge_index else None)
            knowledge = await knowledge_search.configure(search_config, credential=credential,
                policy=Policy("investigation-knowledge", grants={"query", "read"}, max_concurrency=1,
                              limits=Limits(timeout_seconds=30, max_items=100,
                                            max_output_bytes=1_048_576, max_attempts=1)))
            app.state.knowledge = knowledge
            probes = default_probes(credential_provider=lambda: credential)
            app.state.inventory_probes = probes
            scanner = Scanner(adx, load_configuration(Path(settings.detector_config_path)))
            app.state.adx = adx
            app.state.scanner = scanner
            agent = AgentService(adx, scanner, agent_spec, identity=credential,
                                 allow_model_calls=settings.allow_model_calls)
            app.state.agent = agent
            app.state.agent_editor = AgentEditor(Path(settings.agent_store_dir), agent_spec, settings.agent_models)
            graph = GraphService(connector=bind_graph(account=settings.graph_account,
                database=settings.graph_database, graph=settings.graph_name,
                subscription=settings.graph_subscription_id, resource_group=settings.graph_resource_group,
                credential=credential))
            app.state.graph = graph
            app.state.inventory = build_inventory_service(probes=probes)
            app.state.sessions = SessionStore()
            app.state.last_scan = OwnedCache[ScanResponse]()
            yield
        finally:
            async with AsyncExitStack() as cleanup:
                cleanup.push_async_callback(adx.aclose)
                if agent is not None:
                    cleanup.push_async_callback(agent.aclose)
                if graph is not None:
                    cleanup.push_async_callback(graph.aclose)
                if knowledge is not None:
                    cleanup.push_async_callback(knowledge_search.reset_client)
                for name in ("adx", "search", "gremlin"):
                    if name in probes:
                        cleanup.push_async_callback(probes[name].aclose)


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
