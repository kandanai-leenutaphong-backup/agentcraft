"""What the agent makes of one scanned situation: summary, classification, diagnosis."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from ..agents import sse
from ..knowledge import KnowledgeUnavailable
from ..models import Situation
from ..knowledge.situation_types import get_situation_type
from .dependencies import Caller, investigator

router = APIRouter()


@router.post("/api/cyber/situations/summary")
async def situation_summary(body: Situation, request: Request, caller: Caller) -> dict[str, Any]:
    agent, _ = await investigator(request, caller)
    try:
        return await asyncio.to_thread(agent.summarize_situation, body)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"situation summary failed: {exc}") from exc


@router.post("/api/cyber/situations/summary/stream")
async def situation_summary_stream(body: Situation, request: Request, caller: Caller) -> StreamingResponse:
    """The same summary, streamed. The non-streaming POST above stays for JSON callers."""
    agent, _ = await investigator(request, caller)

    async def stream():
        try:
            async for event, data in agent.stream_summary(body):
                yield sse(event, data)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            yield sse("error", {"error": type(exc).__name__, "detail": str(exc)})

    return StreamingResponse(
        stream(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/api/cyber/situations/classify")
async def situation_classify(body: Situation, request: Request, caller: Caller) -> dict[str, Any]:
    """Name the kind of situation from retrieved MITRE ATT&CK candidates, never from memory.

    An unusable model response is returned as a structured envelope carrying `error`; only a
    transport-level failure becomes a 502.
    """
    agent, _ = await investigator(request, caller)
    try:
        return await asyncio.to_thread(agent.classify_situation, body)
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=f"situation classification failed: {exc}",
        ) from exc


@router.get("/api/cyber/knowledge/type/{type_id}")
async def knowledge_type(type_id: str) -> dict[str, Any]:
    try:
        document = await asyncio.to_thread(get_situation_type, type_id)
    except KnowledgeUnavailable as exc:
        raise HTTPException(status_code=503, detail=f"knowledge index unavailable: {exc}") from exc
    if document is None:
        raise HTTPException(status_code=404,
                            detail="unknown situation type in the MITRE ATT&CK index")
    return document


@router.post("/api/cyber/situations/diagnose")
async def diagnose_situation(situation: Situation, request: Request, caller: Caller) -> StreamingResponse:
    agent, _ = await investigator(request, caller)

    async def stream():
        try:
            async for event, data in agent.diagnose_situation(situation):
                yield sse(event, data)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            yield sse("error", {"error": type(exc).__name__, "detail": str(exc)})

    return StreamingResponse(
        stream(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
