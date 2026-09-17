"""Reachability of everything this application depends on, in one unauthenticated report."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Request

from ..config import settings
from ..knowledge.search import status as knowledge_status
from ..knowledge.search import describe as knowledge_description
from .dependencies import Caller, graph_status, investigator

router = APIRouter()


@router.get("/api/cyber/library-identity")
def library_identity(request: Request, caller: Caller) -> dict[str, Any]:
    identity = request.app.state.adx.library_identity()
    knowledge = getattr(request.app.state, "knowledge", None)
    probes = getattr(request.app.state, "inventory_probes", {})
    surfaces = {}
    if callable(getattr(knowledge, "describe", None)):
        surfaces["knowledge"] = knowledge_description()
    catalogue = {name: probe.describe() for name, probe in probes.items()
                 if name in {"adx", "search"} and callable(getattr(probe, "describe", None))}
    if catalogue:
        surfaces["catalogue"] = catalogue
    if surfaces:
        identity["read_surfaces"] = surfaces
    return identity


@router.get("/api/health")
async def health(request: Request, caller: Caller) -> dict[str, Any]:
    report = await request.app.state.adx.health()
    knowledge_base = await knowledge_status()
    _, spec = await investigator(request, caller)
    return {
        "status": "ok" if report.get("reachable") else "degraded",
        "historical_replay": True,
        "adx": report,
        "graph": await graph_status(request),
        "agent": {
            "agent_id": spec.agent_id,
            "name": spec.name,
            "config_id": spec.config_id,
            "config_version": spec.config_version,
            "config_digest": spec.config_digest,
            "model": spec.model,
            "tool_count": len(spec.tools),
            "purpose_built_tool_count": sum(not tool.metadata.fallback for tool in spec.tools),
            "fallback_tool_count": sum(tool.metadata.fallback for tool in spec.tools),
            "reasoning_effort": spec.reasoning_effort,
            "parallel_tool_calls": spec.parallel_tool_calls,
            "endpoint": settings.openai_endpoint,
            "deployment_configured": bool(spec.model and settings.openai_endpoint),
            "knowledge_base": knowledge_base,
            "classification_kb": knowledge_base,
        },
    }
