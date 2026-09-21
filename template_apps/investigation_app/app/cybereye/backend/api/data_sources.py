"""Direct reads of the telemetry store: what is connected, and one bounded KQL query."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from ..inventory.sources import verify as verify_sources
from ..models import QueryRequest, QueryResponse
from ..data.telemetry import CosmosTelemetry
from .dependencies import Caller

router = APIRouter()


def public_telemetry(request: Request) -> CosmosTelemetry:
    service = request.app.state.adx
    if not isinstance(service, CosmosTelemetry):
        raise HTTPException(404, "public source profile not selected")
    return service


@router.get("/api/cyber/public/profile")
async def public_profile(request: Request, caller: Caller) -> dict[str, Any]:
    service = request.app.state.adx
    if not isinstance(service, CosmosTelemetry):
        return {"profile": "adx"}
    return {"profile": service.profile, "partition": service.partition, "source": service.source,
            "coverage": "two-event development smoke; not malicious ground truth",
            "transport": getattr(request.app.state, "public_transport", "native Azure; availability unverified")}


async def public_read(work):
    try:
        return await work
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except RuntimeError as error:
        raise HTTPException(503, str(error)) from error


@router.get("/api/cyber/public/cases")
async def public_cases(request: Request, caller: Caller, partition: str):
    return await public_read(public_telemetry(request).cases(partition))


@router.get("/api/cyber/public/alarms")
async def public_alarms(request: Request, caller: Caller, partition: str, case_id: str):
    return await public_read(public_telemetry(request).alarms(partition, case_id))


@router.get("/api/cyber/public/document")
async def public_document(request: Request, caller: Caller, partition: str, id: str):
    return await public_read(public_telemetry(request).document(partition, id))


@router.get("/api/cyber/public/evidence")
async def public_evidence(request: Request, caller: Caller, partition: str, resource_id: str):
    return await public_read(public_telemetry(request).evidence(partition, [resource_id]))


@router.get("/api/cyber/public/events")
async def public_events(request: Request, caller: Caller, partition: str, start: datetime, end: datetime,
                        entity_id: str = ""):
    return await public_read(public_telemetry(request).events(partition, start, end, entity_id))


@router.get("/api/cyber/sources")
async def sources(request: Request) -> dict[str, Any]:
    """Every connected data source: what it holds, what it answers, and whether it responds."""
    declared = await verify_sources(request.app.state.adx, request.app.state.graph)
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
        return await request.app.state.adx.query(body.query, body.max_rows)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"ADX query failed: {exc}") from exc
