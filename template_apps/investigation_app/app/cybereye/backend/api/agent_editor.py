"""Authenticated authoring endpoints; every saved object belongs to the current caller."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from ..agents.library import AssignInvestigator, LibraryError, SaveAgent
from .dependencies import Caller, agent_datasources

PRIVATE_HEADERS = {"Cache-Control": "no-store, private", "Vary": "Authorization, Cookie"}


def private_response(response: Response) -> None:
    response.headers.update(PRIVATE_HEADERS)


router = APIRouter(prefix="/api/cyber/agent-editor", dependencies=[Depends(private_response)])


async def call(work: Callable[[], Any]) -> Any:
    try:
        return await asyncio.to_thread(work)
    except LibraryError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc), headers=PRIVATE_HEADERS) from exc
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=503, detail="The local agent library could not be read or saved",
                    headers=PRIVATE_HEADERS) from exc


@router.get("")
async def catalogue(request: Request, caller: Caller) -> dict[str, Any]:
    editor = request.app.state.agent_editor
    datasources = agent_datasources(request)
    return await call(lambda: editor.catalogue(caller, datasources))


@router.get("/agents/{agent_id}")
async def version(agent_id: str, request: Request, caller: Caller,
                  version: int | None = Query(default=None, ge=1)) -> dict[str, Any]:
    editor = request.app.state.agent_editor
    return await call(lambda: editor.describe_version(caller, editor.library.get(caller, agent_id, version)))


@router.post("/agents", status_code=201)
async def create(body: SaveAgent, request: Request, caller: Caller) -> dict[str, Any]:
    editor = request.app.state.agent_editor
    return await call(lambda: editor.describe_version(caller, editor.library.save(caller, body)))


@router.post("/agents/{agent_id}/versions", status_code=201)
async def save(agent_id: str, body: SaveAgent, request: Request, caller: Caller) -> dict[str, Any]:
    editor = request.app.state.agent_editor
    return await call(lambda: editor.describe_version(caller, editor.library.save(caller, body, agent_id)))


@router.put("/roles/investigator")
async def assign(body: AssignInvestigator, request: Request, caller: Caller) -> dict[str, Any]:
    editor = request.app.state.agent_editor
    return await call(lambda: editor.library.assign(caller, body).model_dump())