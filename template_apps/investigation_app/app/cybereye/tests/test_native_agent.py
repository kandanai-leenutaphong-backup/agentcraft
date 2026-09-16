import json
from dataclasses import replace
from types import SimpleNamespace

import httpx
import pytest

from llm_interface import LlmError, connect
from app.cybereye.backend.agents.config import ResolvedTool, load_agent_spec
from app.cybereye.backend.agents.service import AgentService
from app.cybereye.backend.agents.tools.base import ToolMetadata
from app.cybereye.backend.security.sessions import SessionStore


def completion(chunks):
    frames = [{"id": "fixture", "object": "chat.completion.chunk", "created": 1, "model": "fixture-model",
               "choices": [{"index": 0, "delta": delta, "finish_reason": reason}]} for delta, reason in chunks]
    return httpx.Response(200, headers={"content-type": "text/event-stream"},
                         content="".join("data: " + json.dumps(frame) + "\n\n" for frame in frames) + "data: [DONE]\n\n")


@pytest.mark.asyncio
@pytest.mark.parametrize("allowed,argument", [(True, 1), (False, 1), (True, 0)])
async def test_native_tool_run_schema_authorizer_events_and_owner_readback(allowed, argument):
    requests, executed, authorized = [], [], []

    async def lookup(context, *, count):
        executed.append((context, count))
        return {"rows": [{"evidence_id": "fixture"}], "count": count}

    schema = {"type": "object", "properties": {"count": {"type": "integer", "minimum": 1}},
              "required": ["count"], "additionalProperties": False}
    resolved = ResolvedTool(lookup, ToolMetadata("lookup", "Read fixture evidence", schema, "evidence"), "Lookup")
    spec = replace(load_agent_spec(), model="fixture-model", tools=(resolved,), max_output_tokens=300)

    def authorize(call):
        authorized.append(call)
        return allowed

    async def handle(request):
        body = json.loads(request.content)
        requests.append(body)
        assert request.url.host == "fixture.invalid"
        assert body["store"] is False
        assert "previous_response_id" not in body
        if len(requests) == 1:
            assert body["tools"][0]["function"]["parameters"] == schema
            return completion([({"role": "assistant", "tool_calls": [{"index": 0, "id": "call-fixture",
                "type": "function", "function": {"name": "lookup", "arguments": json.dumps({"count": argument})}}]}, None),
                ({}, "tool_calls")])
        assert len(requests) == 2
        assert any(message.get("role") == "tool" for message in body["messages"])
        return completion([({"role": "assistant", "content": "Evidence verified."}, None), ({}, "stop")])

    async with connect("https://fixture.invalid/v1", "fixture-model", provider="openai_completions",
                       credential="offline-fixture", allow_model_calls=True, allowed_tools=("lookup",),
                       transport=httpx.MockTransport(handle)) as model:
        service = AgentService(SimpleNamespace(), SimpleNamespace(), spec, connection=model, authorize_tool=authorize)
        session = service.create_session(principal="owner")
        store = SessionStore()
        assert store.create("owner", session) == session.id
        assert store.get(session.id, "other") is None
        with pytest.raises(LlmError):
            session.result(principal="other")
        with pytest.raises(LlmError):
            async for _ in service.stream_turn("read", principal="other", session=session, situation=None):
                pass
        assert requests == []
        frames = []
        if allowed and argument == 1:
            frames = [frame async for frame in service.stream_turn("read", principal="owner", session=session, situation=None)]
            assert len(requests) == 2
            assert len(executed) == len(authorized) == 1
            assert authorized[0].principal == "owner"
            assert authorized[0].call_id == "call-fixture"
            assert frames[-1][0] == "done"
            assert frames[-1][1]["status"] == "completed"
            assert frames[0][1]["session_id"] == session.id
            assert session.result(principal="owner").text == "Evidence verified."
            assert len(requests) == 2
            assert any(name == "tool_result" and data["result"]["count"] == 1 for name, data in frames)
            assert {data["native"]["run_id"] for _, data in frames} == {authorized[0].run_id}
        else:
            with pytest.raises(LlmError):
                async for frame in service.stream_turn("read", principal="owner", session=session, situation=None):
                    frames.append(frame)
            assert len(requests) == 1
            assert executed == []
            assert frames[-1][0] == "error"