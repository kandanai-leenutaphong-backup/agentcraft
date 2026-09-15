from __future__ import annotations

import asyncio
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .dependencies import Caller

router = APIRouter(prefix="/api/cyber/optimization")
HEADERS = {"Cache-Control": "no-store, private"}


class NewExperiment(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    protocol: Literal["smoke", "stress-10", "full-10", "joint-smoke", "joint-10", "joint-12"] = "smoke"
    workflow: bool = False
    creative: bool = False


class DetectorPreview(BaseModel):
    case_id: str = Field(pattern=r"^[0-9a-f]{16}$")
    detector: dict | int


class CandidateProbe(BaseModel):
    proposal: dict
    case_ids: list[str] = Field(min_length=2, max_length=4)

class OperatorGuidance(BaseModel):
    guidance: str = Field(min_length=20, max_length=4000)


def service(request: Request, caller):
    if caller.issuer != "local-preview":
        raise HTTPException(404, "Local optimization is not available here")
    current = getattr(request.app.state, "optimization", None)
    if current is None:
        raise HTTPException(503, getattr(request.app.state, "optimization_error", "Prepare GUIDE data before starting optimization"))
    try:
        current.authorize(caller)
    except PermissionError as exc:
        raise HTTPException(404, "Local optimization is not available here") from exc
    return current


async def result(work):
    try:
        return JSONResponse(await asyncio.to_thread(work), headers=HEADERS)
    except (PermissionError, KeyError) as exc:
        raise HTTPException(404, "Experiment or operation not found") from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("")
async def snapshot(request: Request, caller: Caller):
    if getattr(request.app.state, "optimization", None) is None:
        return JSONResponse({"available": False, "detail": getattr(request.app.state, "optimization_error", "GUIDE data not prepared"),
                             "experiments": [], "tools": []}, headers=HEADERS)
    current = service(request, caller)
    return await result(lambda: current.snapshot(caller))


@router.post("/experiments")
async def create(body: NewExperiment, request: Request, caller: Caller):
    current = service(request, caller)
    return await result(lambda: current.create(caller, body.name, body.protocol, workflow=body.workflow, creative=body.creative))


@router.get("/experiments/{identifier}")
async def experiment(identifier: str, request: Request, caller: Caller):
    current = service(request, caller)
    return await result(lambda: current.get(caller, identifier))


@router.get("/experiments/{identifier}/capabilities")
async def capabilities(identifier: str, request: Request, caller: Caller):
    current = service(request, caller)
    return await result(lambda: current.capabilities(caller, identifier))


@router.post("/experiments/{identifier}/cancel")
async def cancel(identifier: str, request: Request, caller: Caller):
    current = service(request, caller)
    def stop():
        experiment = current.cancel(caller, identifier)
        request.app.state.optimization_terminal.cancel_experiment(identifier)
        return experiment
    return await result(stop)


@router.get("/experiments/{identifier}/trace")
async def trace(identifier: str, request: Request, caller: Caller):
    current = service(request, caller)
    def read():
        current.get(caller, identifier)
        path = current.directory(caller, identifier) / "terminal.log"
        return {"text": path.read_text()[-1_000_000:] if path.exists() else ""}
    return await result(read)

@router.post("/experiments/{identifier}/verify-final")
async def verify_final(identifier: str, request: Request, caller: Caller):
    current = service(request, caller)
    return await result(lambda: current.verify_final(caller, identifier))

@router.post("/experiments/{identifier}/interventions")
async def intervene(identifier: str, body: OperatorGuidance, request: Request, caller: Caller):
    current = service(request, caller)
    return await result(lambda: current.intervene(caller, identifier, body.guidance))


@router.post("/experiments/{identifier}/versions/{number}/tune")
async def tune(identifier: str, number: int, request: Request, caller: Caller):
    current = service(request, caller)
    return await result(lambda: current.measure(caller, identifier, number, "training"))


@router.get("/experiments/{identifier}/detectors")
async def detectors(identifier: str, request: Request, caller: Caller):
    current = service(request, caller)
    return await result(lambda: current.detectors(caller, identifier))


@router.post("/experiments/{identifier}/detector-preview")
async def detector_preview(identifier: str, body: DetectorPreview, request: Request, caller: Caller):
    current = service(request, caller)
    return await result(lambda: current.test_detector(caller, identifier, body.case_id, body.detector))


@router.post("/experiments/{identifier}/knowledge")
async def knowledge(identifier: str, body: dict, request: Request, caller: Caller):
    current = service(request, caller)
    return await result(lambda: current.knowledge(caller, identifier, body))


@router.post("/experiments/{identifier}/probe")
async def probe(identifier: str, body: CandidateProbe, request: Request, caller: Caller):
    current = service(request, caller)
    return await result(lambda: current.probe(caller, identifier, body.proposal, body.case_ids))


@router.post("/experiments/{identifier}/versions/{number}/evaluate")
async def evaluate(identifier: str, number: int, request: Request, caller: Caller):
    current = service(request, caller)
    return await result(lambda: current.evaluate(caller, identifier, number))


@router.get("/experiments/{identifier}/versions/{number}/runs/{run_id}/examples/{kind}")
async def exemplar(identifier: str, number: int, run_id: str, kind: Literal["best", "worst"], request: Request, caller: Caller):
    current = service(request, caller)
    return await result(lambda: current.exemplar(caller, identifier, number, run_id, kind))


@router.get("/sources/preview")
async def preview(request: Request, caller: Caller):
    current = service(request, caller)
    return await result(current.dataset.preview)


@router.get("/profiles")
async def profiles(request: Request, caller: Caller):
    current = service(request, caller)
    return await result(current.dataset.profiles)


@router.post("/terminal/{action}")
async def terminal(action: str, request: Request, caller: Caller):
    service(request, caller)
    body = await request.body()
    if len(body) > 65_536:
        raise HTTPException(413, "Terminal request exceeds 64 KiB")
    import json
    try:
        payload = json.loads(body)
    except (ValueError, UnicodeError) as exc:
        raise HTTPException(400, "Expected JSON") from exc
    status, reply = await asyncio.to_thread(request.app.state.optimization_terminal.handle,
                                            caller, action, dict(request.headers), payload)
    return JSONResponse(reply, status_code=status, headers=HEADERS)