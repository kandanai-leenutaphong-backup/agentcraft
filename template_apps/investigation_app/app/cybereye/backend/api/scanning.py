"""The deterministic replay scan: its registry, its windows, its results, and their evidence."""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from situation_detector import configuration_digest

from ..agents import sse
from ..data.telemetry import CosmosTelemetry
from ..models import ScanRequest, ScanResponse, Situation
from ..agents.tools.base import evidence_query
from .dependencies import Caller

router = APIRouter()


@router.get("/api/cyber/rules")
async def rules(request: Request) -> list[dict[str, Any]]:
    """The detection registry, so the scanner UI never keeps a second copy of it."""
    return [
        {
            "rule_id": rule.rule_id, "label": rule.name, "version": rule.version,
            "role": rule.role, "score": rule.score, "confidence": rule.confidence,
            "behaviour_class": rule.behaviour_class, "threshold": rule.threshold,
            "technique_ids": list(rule.technique_ids), "description": rule.description,
        }
        for rule in request.app.state.scanner.engine.rules
    ]


@router.get("/api/cyber/detector/configuration")
async def detector_configuration(request: Request, caller: Caller) -> dict[str, Any]:
    configuration = request.app.state.scanner.engine.configuration
    if isinstance(request.app.state.adx, CosmosTelemetry):
        return {"configuration": configuration, "configuration_digest": hashlib.sha256(
            json.dumps(configuration, sort_keys=True).encode()).hexdigest(),
            "component": "public-windows", "historical_replay": True}
    return {"configuration": configuration, "configuration_digest": configuration_digest(configuration),
            "component": "situation_detector", "historical_replay": True}


@router.get("/api/cyber/scenarios")
async def scenarios(request: Request) -> list[dict[str, Any]]:
    telemetry = request.app.state.adx
    if isinstance(telemetry, CosmosTelemetry):
        from datetime import timedelta
        cases = await telemetry.cases(telemetry.partition)
        output = []
        for case in cases:
            events = await telemetry.evidence(telemetry.partition, case["event_refs"])
            times = [datetime.fromisoformat(item["timestamp"]) for item in events]
            output.append({"id": case["id"], "name": case["title"],
                "start": min(times).replace(second=0, microsecond=0).isoformat(),
                "end": (max(times).replace(second=0, microsecond=0) + timedelta(minutes=1)).isoformat(),
                "description": "Public emulation smoke export; derived alarms, no per-event malicious labels."})
        return output
    return [
        {
            "id": "focal-privileged-session",
            "name": "Privileged session and tool retrieval",
            "start": "2026-08-13T02:30:00Z",
            "end": "2026-08-13T03:40:59Z",
            "description": "CyberArk access, explicit credentials, directory discovery, and WinPEAS URL evidence.",
        },
        {
            "id": "service-account-credentials",
            "name": "Service account explicit credentials",
            "start": "2026-08-12T15:45:00Z",
            "end": "2026-08-12T16:20:00Z",
            "description": "The same credential rule that scores critical for admLRhodes scores medium for svcSNOWDiscovery ten hours earlier on the same host.",
        },
        {
            "id": "beacon-only",
            "name": "Fixed-interval DNS without the session",
            "start": "2026-08-12T06:00:00Z",
            "end": "2026-08-12T10:00:00Z",
            "description": "The 120-second DNS cadence alone, hours away from any privileged-session activity.",
        },
        {
            "id": "full-export",
            "name": "Full 33-hour replay",
            "start": "2026-08-11T23:57:53Z",
            "end": "2026-08-13T08:48:52Z",
            "description": "Full source-time-corrected export, including the periodic DNS lead.",
        },
    ]


@router.post("/api/cyber/scan", response_model=ScanResponse)
async def scan(body: ScanRequest, request: Request, caller: Caller) -> ScanResponse:
    try:
        result = await request.app.state.scanner.scan_async(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"ADX scan failed: {exc}") from exc
    request.app.state.last_scan.put(caller.id, result)
    return result


@router.post("/api/cyber/scan/stream")
async def scan_stream(body: ScanRequest, request: Request, caller: Caller) -> StreamingResponse:
    async def stream():
        async for item in request.app.state.scanner.stream_scan(body):
            if item["event"] == "done":
                request.app.state.last_scan.put(
                    caller.id, ScanResponse.model_validate(item["data"]),
                )
            yield sse(item["event"], item["data"])

    return StreamingResponse(
        stream(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/api/cyber/evidence/{situation_id}")
async def evidence(situation_id: str, request: Request, caller: Caller,
                   start: datetime | None = None, end: datetime | None = None) -> dict[str, Any]:
    """Resolve a situation without depending on which replica served the scan.

    The cached scan is per-caller, and per-process besides, so ingress having no session
    affinity is only half the reason a lookup misses. When the caller supplies the scanned
    window the situation is re-derived from it instead: the scan is deterministic, so the ids
    match. A caller therefore never resolves a situation from another caller's cached result.
    """
    situation = _find_situation(request.app.state.last_scan.get(caller.id), situation_id)
    if situation is None and start is not None and end is not None:
        try:
            rescan = await request.app.state.scanner.scan_async(ScanRequest(start=start, end=end))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"ADX scan failed: {exc}") from exc
        situation = _find_situation(rescan, situation_id)
    if situation is None:
        raise HTTPException(
            status_code=404,
            detail="unknown situation; pass the scanned window as ?start=&end= so it can be re-derived"
            if start is None or end is None else "unknown situation in the supplied window",
        )
    ids = [rid for pattern in situation.patterns for rid in pattern.evidence_ids]
    if not ids:
        return {"situation_id": situation_id, "columns": [], "rows": [], "row_count": 0}
    try:
        telemetry = request.app.state.adx
        if isinstance(telemetry, CosmosTelemetry):
            result = telemetry.as_query(await telemetry.evidence(telemetry.partition, list(dict.fromkeys(ids))))
        else:
            kql, params = evidence_query(ids)
            result = await telemetry.parameterized(kql, params, 100)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"evidence query failed: {exc}") from exc
    return {"situation_id": situation_id, **result.model_dump(mode="json")}


def _find_situation(scan_result: ScanResponse | None, situation_id: str) -> Situation | None:
    if not scan_result:
        return None
    return next((item for item in scan_result.situations if item.situation_id == situation_id), None)
