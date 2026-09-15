"""Direct reads of the telemetry store: what is connected, and one bounded KQL query."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from ..inventory.sources import verify as verify_sources
from ..models import QueryRequest, QueryResponse

router = APIRouter()


@router.get("/api/cyber/sources")
async def sources(request: Request) -> dict[str, Any]:
    """Every connected data source: what it holds, what it answers, and whether it responds."""
    declared = await asyncio.to_thread(
        verify_sources, request.app.state.adx, request.app.state.graph,
    )
    return {
        "sources": declared,
        "required_unreachable": [
            item["source_id"] for item in declared if item["required"] and not item["reachable"]
        ],
        "historical_replay": True,
    }


@router.post("/api/cyber/query", response_model=QueryResponse)
async def query(body: QueryRequest, request: Request) -> QueryResponse:
    try:
        return await asyncio.to_thread(request.app.state.adx.query, body.query, body.max_rows)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"ADX query failed: {exc}") from exc
