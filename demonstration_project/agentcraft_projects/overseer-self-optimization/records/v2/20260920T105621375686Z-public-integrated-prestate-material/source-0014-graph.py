"""Read-only traversals of the ontology graph."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, Request

from ..data import DEFAULT_SCOPE, GraphService
from .dependencies import graph_call

router = APIRouter()


@router.get("/api/cyber/graph/status")
async def graph_status(request: Request) -> dict[str, Any]:
    graph: GraphService = request.app.state.graph
    return await graph.status()


@router.get("/api/cyber/graph/overview")
async def graph_overview(request: Request) -> dict[str, Any]:
    return await graph_call(request, lambda graph: graph.overview())


@router.get("/api/cyber/graph/core")
async def graph_core(request: Request, limit: int = 260, start: str = "", end: str = "") -> dict[str, Any]:
    return await graph_call(request, lambda graph: graph.core(limit, start, end))


@router.get("/api/cyber/graph/entities")
async def graph_entities(request: Request) -> list[dict[str, Any]]:
    return await graph_call(request, lambda graph: graph.entities())


@router.get("/api/cyber/graph/node")
async def graph_node(request: Request, id: str, limit: int = 220,
                     start: str = "", end: str = "", depth: int = 1) -> dict[str, Any]:
    if not id.strip():
        raise HTTPException(status_code=422, detail="id is required")
    return await graph_call(request, lambda graph: graph.neighbourhood(id, limit, start, end, depth))


@router.get("/api/cyber/graph/selection")
async def graph_selection(request: Request, id: Annotated[list[str], Query()],
                          limit: int = 220, start: str = "", end: str = "",
                          depth: int = 2, scope: str = DEFAULT_SCOPE) -> dict[str, Any]:
    if not id:
        raise HTTPException(status_code=422, detail="at least one id is required")
    return await graph_call(request,
                            lambda graph: graph.selection(id, limit, start, end, depth, scope))


@router.get("/api/cyber/graph/search")
async def graph_search(request: Request, q: str, limit: int = 25) -> list[dict[str, Any]]:
    return await graph_call(request, lambda graph: graph.search(q, limit))
