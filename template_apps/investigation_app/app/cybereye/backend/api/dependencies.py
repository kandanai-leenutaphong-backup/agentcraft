"""What every route in this package is given: the caller, and the composed services."""

from __future__ import annotations

import asyncio
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request

from resource_explorer import InventoryService

from ..agents.config import AgentSpec
from ..agents.library import LibraryError
from ..agents.service import AgentService
from ..config import settings
from ..data import GraphNotFound, GraphService, GraphUnavailable
from ..security import Principal, current_principal

#: Injected identity. Every route that creates or reads something a caller owns takes this.
Caller = Annotated[Principal, Depends(current_principal)]

async def investigator(request: Request, caller: Principal) -> tuple[AgentService, AgentSpec]:
    try:
        return await asyncio.to_thread(request.app.state.agent_editor.investigator, caller,
                                       request.app.state.agent)
    except LibraryError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=503, detail="The saved Investigator configuration could not be read") from exc


def agent_datasources(request: Request) -> dict[str, dict[str, Any]]:
    datasources = {
        "adx": {"kind": "adx", "label": "Azure Data Explorer",
                "target": f"{settings.adx_database}.{settings.table}", "endpoint": settings.adx_cluster_uri,
                "configured": bool(settings.adx_cluster_uri and settings.adx_database and settings.table)},
        "search": {"kind": "search", "label": "Azure AI Search", "target": settings.knowledge_index,
                   "endpoint": settings.search_endpoint,
                   "configured": bool(settings.search_endpoint and settings.knowledge_index)},
        "none": {"kind": "none", "label": "No external datasource", "target": "Investigation output",
                 "endpoint": "", "configured": True},
    }
    bindings = {
        "adx": {"endpoint": settings.adx_cluster_uri, "database": settings.adx_database, "table": settings.table},
        "search": {"endpoint": settings.search_endpoint, "index": settings.knowledge_index},
    }
    declared = request.app.state.inventory.registry.sources()
    for kind, coordinates in bindings.items():
        datasources[kind]["source_ids"] = [
            source.source_id for source in declared
            if source.binding.connector == kind and all(
                value and source.binding.coordinates.get(key) == value for key, value in coordinates.items()
            )
        ]
    return datasources


def inventory_service(request: Request) -> InventoryService:
    service = getattr(request.app.state, "inventory", None)
    if service is None:  # pragma: no cover - lifespan always sets it
        raise HTTPException(status_code=503, detail="inventory is not composed")
    return service


def graph_status(request: Request) -> dict[str, Any]:
    """The graph is an optional source, so an absent one is a report, not a failure."""
    graph = getattr(request.app.state, "graph", None)
    if graph is None:
        return {"available": False, "detail": "graph source not configured"}
    return graph.status()


async def graph_call(request: Request, work: Any) -> Any:
    graph: GraphService = request.app.state.graph
    try:
        return await asyncio.to_thread(work, graph)
    except GraphNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except GraphUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
