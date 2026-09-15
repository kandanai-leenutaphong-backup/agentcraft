"""The configured agent as the UI reads it: tools, their datasources, and their real source."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Request

from ..agents import describe_agent
from .dependencies import Caller, agent_datasources, investigator

router = APIRouter()


@router.get("/api/cyber/agents")
async def agents(request: Request, caller: Caller) -> dict[str, Any]:
    _, spec = await investigator(request, caller)
    agent = await asyncio.to_thread(describe_agent, spec, agent_datasources(request))
    return {"agents": [agent]}
