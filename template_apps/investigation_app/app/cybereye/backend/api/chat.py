"""Owner-bound chat sessions and one streamed turn each."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from ..agents import AgentService, sse
from ..models import ChatRequest, SessionResponse
from ..security import ChatSession
from .dependencies import Caller, investigator

router = APIRouter()

#: Events after which replaying the turn would duplicate visible output.
IRREVERSIBLE_EVENTS = frozenset({"token", "tool_call_start", "tool_call_end", "tool_result"})


def _stale_thread(exc: Exception) -> bool:
    text = str(exc).lower()
    return "previous response" in text and ("not found" in text or "expired" in text)


async def run_chat_turn(
    agent: AgentService, session: ChatSession, body: ChatRequest, session_id: str,
) -> AsyncIterator[str]:
    """Stream one turn, retrying once from a clean thread if the stored response id is stale."""
    for attempt in (0, 1):
        progressed = False
        final_response_id = session.previous_response_id
        try:
            async for event, data in agent.stream_turn(
                body.message,
                previous_response_id=session.previous_response_id,
                situation=body.situation,
            ):
                if event in IRREVERSIBLE_EVENTS:
                    progressed = True
                if event == "metadata" and data.get("response_id"):
                    final_response_id = str(data["response_id"])
                yield sse(event, data)
            session.previous_response_id = final_response_id
            return
        except asyncio.CancelledError:
            yield sse("aborted", {"session_id": session_id})
            raise
        except Exception as exc:
            if attempt == 0 and not progressed and session.previous_response_id and _stale_thread(exc):
                session.previous_response_id = None
                yield sse("status", {"phase": "model", "label": "Earlier turns expired; restarting the thread…"})
                continue
            yield sse("error", {"error": type(exc).__name__, "detail": str(exc)})
            return


@router.post("/api/sessions", response_model=SessionResponse)
async def create_session(request: Request, caller: Caller) -> SessionResponse:
    return SessionResponse(session_id=request.app.state.sessions.create(caller.id))


@router.post("/api/chat/{session_id}")
async def chat(session_id: str, body: ChatRequest, request: Request,
               caller: Caller) -> StreamingResponse:
    # Someone else's session answers exactly as a session that never existed, so the
    # identifier space cannot be probed for which sessions are real.
    session: ChatSession | None = request.app.state.sessions.get(session_id, caller.id)
    if not session:
        raise HTTPException(status_code=404, detail="unknown session")
    agent, spec = await investigator(request, caller)

    async def stream():
        async with session.lock:
            version_key = f"{spec.agent_id}:{spec.config_version}:{spec.config_digest}"
            if session.agent_version_key and session.agent_version_key != version_key:
                session.previous_response_id = None
            session.agent_version_key = version_key
            async for frame in run_chat_turn(agent, session, body, session_id):
                yield frame

    return StreamingResponse(
        stream(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
