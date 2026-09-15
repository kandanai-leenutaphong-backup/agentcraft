"""Reachability of everything this application depends on, in one unauthenticated report."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Request

from ..config import settings
from ..knowledge.search import status as knowledge_status
from ..knowledge.situation_types import classification_status
from .dependencies import Caller, graph_status, investigator

router = APIRouter()


@router.get("/api/health")
async def health(request: Request, caller: Caller) -> dict[str, Any]:
    report = await asyncio.to_thread(request.app.state.adx.health)
    knowledge_base = await asyncio.to_thread(knowledge_status)
    classification_kb = await asyncio.to_thread(classification_status)
    _, spec = await investigator(request, caller)
    return {
        "status": "ok" if report.get("reachable") else "degraded",
        "historical_replay": True,
        "adx": report,
        "graph": await asyncio.to_thread(graph_status, request),
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
            "classification_kb": classification_kb,
        },
    }
