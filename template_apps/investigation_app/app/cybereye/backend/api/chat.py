"""Owner-bound chat sessions and one streamed turn each."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from llm_interface import LlmError

from ..agents import AgentService, sse
from ..models import ChatRequest, SessionResponse
from ..security import ChatSession
from ..security.principal import Principal
from .dependencies import Caller, investigator

router = APIRouter()

async def run_chat_turn(
    agent: AgentService, session: ChatSession, body: ChatRequest, session_id: str,
    caller: Principal | None = None,
) -> AsyncIterator[str]:
    """One native run. Interrupted sessions never replay implicitly."""
    failed = False
    try:
        async for event, data in agent.stream_turn(body.message, session=session.model_session,
            principal=session.owner_id, situation=body.situation, caller=caller):
            failed = failed or event == "error"
            yield sse(event, data)
    except asyncio.CancelledError:
        raise
    except LlmError as error:
        if not failed:
            yield sse("error", {"error": error.code, "detail": error.action or "Create a new session after an interrupted run."})
    except Exception:
        yield sse("error", {"error": "agent_run_failed", "detail": "The run failed; no automatic replay was attempted."})


@router.post("/api/sessions", response_model=SessionResponse)
async def create_session(request: Request, caller: Caller) -> SessionResponse:
    agent, spec = await investigator(request, caller)
    native = agent.create_session(principal=caller.id)
    return SessionResponse(session_id=request.app.state.sessions.create(caller.id, native,
        agent_version_key=f"{spec.agent_id}:{spec.config_version}:{spec.config_digest}"))


@router.get("/api/sessions/{session_id}/result")
async def session_result(session_id: str, request: Request, caller: Caller):
    session = request.app.state.sessions.get(session_id, caller.id)
    if session is None:
        raise HTTPException(status_code=404, detail="unknown session")
    result = session.model_session.result(principal=caller.id)
    return {"session_id": session_id, "result": None if result is None else {
        "text": result.text, **result.additional_properties["llm_interface"]}}


@router.post("/api/chat/{session_id}")
async def chat(session_id: str, body: ChatRequest, request: Request,
               caller: Caller) -> StreamingResponse:
    # Someone else's session answers exactly as a session that never existed, so the
    # identifier space cannot be probed for which sessions are real.
    session: ChatSession | None = request.app.state.sessions.get(session_id, caller.id)
    if not session:
        raise HTTPException(status_code=404, detail="unknown session")
    agent, spec = await investigator(request, caller)
    version_key = f"{spec.agent_id}:{spec.config_version}:{spec.config_digest}"
    if session.agent_version_key != version_key:
        raise HTTPException(status_code=409, detail="agent definition changed; create a new session")

    async def stream():
        async with session.lock:
            async for frame in run_chat_turn(agent, session, body, session_id, caller):
                yield frame

    return StreamingResponse(
        stream(), media_type="text/event-stream",
        headers={"Cache-Control": "no-store, private", "X-Accel-Buffering": "no"},
    )
