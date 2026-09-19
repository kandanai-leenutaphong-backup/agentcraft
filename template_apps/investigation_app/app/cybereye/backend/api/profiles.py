"""Authenticated adapters over the same profile service used by native tools."""

import asyncio
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import Field

from ..agents.profiles import ProfileError, SuspectProfile, UpdateSuspectProfile
from .dependencies import Caller


PRIVATE_HEADERS = {"Cache-Control": "no-store, private", "Vary": "Authorization, Cookie"}


def private_response(response: Response) -> None:
    response.headers.update(PRIVATE_HEADERS)


router = APIRouter(prefix="/api/cyber/suspect-profiles", dependencies=[Depends(private_response)])


class ProfileUpdateRequest(UpdateSuspectProfile):
    evidence_run_id: str = Field(min_length=1, max_length=200)


async def call(work):
    try:
        return await asyncio.to_thread(work)
    except ProfileError as exc:
        raise HTTPException(exc.status, detail=exc.code, headers=PRIVATE_HEADERS) from exc
    except (OSError, sqlite3.Error) as exc:
        raise HTTPException(503, detail="profile_store_unavailable", headers=PRIVATE_HEADERS) from exc


@router.get("", response_model=list[SuspectProfile])
async def profiles(request: Request, caller: Caller):
    return await call(lambda: request.app.state.profiles.list(caller))


@router.get("/{profile_id}", response_model=SuspectProfile)
async def profile(profile_id: str, request: Request, caller: Caller):
    return await call(lambda: request.app.state.profiles.get(caller, profile_id))


@router.put("/{profile_id}", response_model=SuspectProfile)
async def update_profile(profile_id: str, body: ProfileUpdateRequest, request: Request, caller: Caller):
    if profile_id != body.profile_id:
        raise HTTPException(422, detail="profile_id_mismatch", headers=PRIVATE_HEADERS)
    service = request.app.state.profiles
    update = UpdateSuspectProfile.model_validate(body.model_dump(exclude={"evidence_run_id"}))
    return await call(lambda: service.update(caller, update, service.evidence(caller, body.evidence_run_id)))