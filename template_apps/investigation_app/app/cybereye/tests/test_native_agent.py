import asyncio
import json
import os
import socket
import subprocess
import sys
import threading
import traceback
import uuid
from collections import deque
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import httpx
import pytest
import pytest_asyncio

from llm_interface import Limits, LlmError, connect

with patch("dotenv.load_dotenv"):
    from app.cybereye.backend.agents.config import ResolvedTool, load_agent_spec
    from app.cybereye.backend.agents.service import AgentService
    from app.cybereye.backend.agents.tools.base import ToolMetadata
    from app.cybereye.backend.security.sessions import SessionStore


def completion(chunks, *, stream=True, terminal=True):
    if not stream:
        return httpx.Response(200, json={"id": "fixture", "object": "chat.completion", "created": 1,
            "model": "fixture-model", "choices": [{"index": 0, "finish_reason": chunks[-1][1],
                "message": {"role": "assistant", "content": "".join(
                    delta.get("content", "") for delta, _ in chunks)}}]})
    frames = [{"id": "fixture", "object": "chat.completion.chunk", "created": 1, "model": "fixture-model",
               "choices": [{"index": 0, "delta": delta, "finish_reason": reason}]} for delta, reason in chunks]
    return httpx.Response(200, headers={"content-type": "text/event-stream"},
                         content="".join("data: " + json.dumps(frame) + "\n\n" for frame in frames)
                         + ("data: [DONE]\n\n" if terminal else ""))


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


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["sync", "async", "awaitable"])
@pytest.mark.parametrize("outcome", ["allowed", "denied", "cancelled"])
async def test_native_binding_invocation_kind(kind, outcome):
    loop = asyncio.get_running_loop()
    loop_thread = threading.get_ident()
    entered, finished, async_release = asyncio.Event(), asyncio.Event(), asyncio.Event()
    sync_release = threading.Event()
    invoked, executed, authorized, requests, frames = [], [], [], [], []

    def blocking_lookup(context, *, count):
        invoked.append(threading.get_ident())
        executed.append((context, count, threading.get_ident()))
        loop.call_soon_threadsafe(entered.set)
        try:
            assert sync_release.wait(2), "event loop did not release synchronous tool"
            return {"count": count}
        finally:
            loop.call_soon_threadsafe(finished.set)

    async def async_lookup(context, *, count):
        executed.append((context, count, threading.get_ident()))
        entered.set()
        try:
            await async_release.wait()
            return {"count": count}
        finally:
            finished.set()

    def awaitable_lookup(context, *, count):
        invoked.append(threading.get_ident())
        return async_lookup(context, count=count)

    function = {"sync": blocking_lookup, "async": async_lookup, "awaitable": awaitable_lookup}[kind]
    schema = {"type": "object", "properties": {"count": {"type": "integer", "minimum": 1}},
              "required": ["count"], "additionalProperties": False}
    resolved = ResolvedTool(function, ToolMetadata("lookup", "Read fixture evidence", schema, "evidence"), "Lookup")
    spec = replace(load_agent_spec(), model="fixture-model", tools=(resolved,), max_output_tokens=300)

    def authorize(call):
        authorized.append(call)
        return outcome != "denied"

    async def handle(request):
        body = json.loads(request.content)
        requests.append(body)
        assert request.url.host == "fixture.invalid"
        if len(requests) == 1:
            assert body["tools"][0]["function"]["parameters"] == schema
            return completion([({"role": "assistant", "tool_calls": [{"index": 0, "id": "call-kind",
                "type": "function", "function": {"name": "lookup", "arguments": '{"count":1}'}}]}, None),
                ({}, "tool_calls")])
        assert len(requests) == 2
        return completion([({"role": "assistant", "content": "Evidence verified."}, None), ({}, "stop")])

    async with connect("https://fixture.invalid/v1", "fixture-model", provider="openai_completions",
                       credential="offline-fixture", allow_model_calls=True, allowed_tools=("lookup",),
                       transport=httpx.MockTransport(handle)) as model:
        service = AgentService(SimpleNamespace(), SimpleNamespace(), spec, connection=model, authorize_tool=authorize)
        session = service.create_session(principal="owner")

        async def consume():
            async for frame in service.stream_turn("read", principal="owner", session=session, situation=None):
                frames.append(frame)

        pending = asyncio.create_task(consume())
        try:
            if outcome == "denied":
                with pytest.raises(LlmError, match="tool_authorization_denied"):
                    await asyncio.wait_for(pending, 5)
                assert invoked == executed == []
            else:
                await asyncio.wait_for(entered.wait(), 5)
                assert not finished.is_set()
                assert executed == [(service.tool_context, 1, executed[0][2])]
                assert (executed[0][2] == loop_thread) == (kind != "sync")
                if kind != "async":
                    assert len(invoked) == 1 and invoked[0] != loop_thread
                if outcome == "cancelled":
                    pending.cancel()
                    with pytest.raises(asyncio.CancelledError):
                        await pending
                    if kind == "sync":
                        assert not finished.is_set()
                else:
                    sync_release.set()
                    async_release.set()
                    await asyncio.wait_for(pending, 5)
                    assert session.result(principal="owner").text == "Evidence verified."
                    assert frames[-1][0] == "done" and frames[-1][1]["status"] == "completed"
                    assert any(name == "tool_result" and data["result"] == {"count": 1} for name, data in frames)
            assert len(authorized) == 1
            assert authorized[0].principal == "owner" and authorized[0].call_id == "call-kind"
            assert authorized[0].arguments == {"count": 1} and authorized[0].run_id
            assert len(requests) == (2 if outcome == "allowed" else 1)
            if outcome != "allowed":
                assert session.result(principal="owner") is None
                assert not any(name == "done" for name, _ in frames)
                if outcome == "cancelled":
                    assert not any(name == "tool_result" for name, _ in frames)
                with pytest.raises(LlmError, match="session_interrupted"):
                    await consume()
                assert len(requests) == 1
        finally:
            sync_release.set()
            async_release.set()
            if not pending.done():
                pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)
            if executed:
                await asyncio.wait_for(finished.wait(), 5)


@asynccontextmanager
async def native_asgi_support(monkeypatch, tmp_path, *, authorized_principal=None,
                              model_response=None, data_response=None, search_response=None):
    """Test-only production ASGI composition with synthetic external services.

    A browser driver may serve the yielded app on loopback with lifespan disabled;
    this context already owns service lifecycle. The caller owns MonkeyPatch cleanup.
    """
    import azure.identity
    import azure.identity.aio

    external_attempts = []

    def refuse_external(operation):
        def blocked(*args, **kwargs):
            observation = {"operation": operation, "stack": [
                {"path": frame.filename, "line": frame.lineno, "function": frame.name}
                for frame in traceback.extract_stack(limit=10)[:-1]]}
            if operation.startswith("socket."):
                target = args[1] if operation in {"socket.connect", "socket.connect_ex"} else args[-1] if operation == "socket.sendto" else args[0]
                observation["target"] = str(target)[:256]
            external_attempts.append(observation)
            raise AssertionError(f"forbidden external I/O: {operation}")
        return blocked

    monkeypatch.setattr(socket.socket, "connect", refuse_external("socket.connect"))
    monkeypatch.setattr(socket.socket, "connect_ex", refuse_external("socket.connect_ex"))
    monkeypatch.setattr(socket.socket, "sendto", refuse_external("socket.sendto"))
    monkeypatch.setattr(socket, "create_connection", refuse_external("socket.create_connection"))
    monkeypatch.setattr(socket, "getaddrinfo", refuse_external("socket.getaddrinfo"))
    monkeypatch.setattr(subprocess, "Popen", refuse_external("subprocess.Popen"))
    monkeypatch.setattr(uuid, "getnode", lambda: 0x010000000001)
    for identity in (azure.identity, azure.identity.aio):
        monkeypatch.setattr(identity.DefaultAzureCredential, "__init__",
                            refuse_external(identity.__name__ + ".DefaultAzureCredential"))

    with patch.dict(os.environ, {"PYTHON_DOTENV_DISABLED": "1"}, clear=True):
        import _auth_support
        from azdata import ConnectorConfig, Limits as DataLimits, Policy, ResourceAddress
        from test_azdata_migration import Credential, Transport
        from test_graph_service import ScriptedClient, service as graph_service
        from app.cybereye.backend import config, main as backend
        from app.cybereye.backend.agents.editor import AgentEditor
        from app.cybereye.backend.data.adx import ReadOnlyAdx
        from app.cybereye.backend.investigation import Scanner, load_configuration
        from app.cybereye.backend.knowledge import search as knowledge_search

        original = config.settings
        spec = load_agent_spec()
        settings = replace(original, app_root=tmp_path,
            adx_cluster_uri="https://fixture.invalid", adx_database="fixture",
            table="EventsUnified", extra_tables=(), openai_endpoint="https://fixture.invalid/v1",
            model=spec.model, allow_model_calls=False, agent_store_dir=str(tmp_path / "agents"),
            agent_models=(spec.model,), search_endpoint="https://fixture.invalid",
            knowledge_index="fixture", graph_account="", graph_database="fixture",
            graph_name="fixture", graph_resource_group="", graph_subscription_id="",
            detector_config_path=str(Path(__file__).parents[1] / "control/situation_detector.json"))
        settings.validate()
        for name, module in tuple(sys.modules.items()):
            if name.startswith("app.cybereye.backend") and getattr(module, "settings", None) is original:
                monkeypatch.setattr(module, "settings", settings)

        replies, model_requests, responses, authorized, denied = deque(), [], [], [], set()
        model_loops = []
        search_replies, search_requests, search_loops = deque(), [], []
        data_replies = deque()
        credential, transport = Credential(), Transport()

        async def data_request(request):
            if data_response is not None:
                transport.requests.append(request)
                transport.loops.append(asyncio.get_running_loop())
                return data_response(request)
            if not data_replies:
                return await Transport.request(transport, request)
            transport.requests.append(request)
            transport.loops.append(asyncio.get_running_loop())
            return data_replies.popleft()

        monkeypatch.setattr(transport, "request", data_request)
        adx = ReadOnlyAdx(credential=credential, transport=transport)
        scanner = Scanner(adx, load_configuration(Path(settings.detector_config_path)))
        graph_driver = ScriptedClient([])
        graph = graph_service([graph_driver], credential=credential)
        inventory = backend.build_inventory_service(probes={})

        async def search_request(request):
            assert httpx.URL(request.url).host == "fixture.invalid"
            search_requests.append(request)
            search_loops.append(asyncio.get_running_loop())
            if search_response is not None:
                return search_response(request)
            assert search_replies, "unexpected native Search attempt"
            return search_replies.popleft()

        async def handle(request):
            assert request.url.host == "fixture.invalid"
            body = json.loads(request.content)
            assert body["store"] is False
            assert "previous_response_id" not in body
            model_requests.append(body)
            model_loops.append(asyncio.get_running_loop())
            if model_response is None:
                assert replies, "unexpected native attempt; no automatic replay is authorized"
                response = replies.popleft()
            else:
                response = model_response(body)
            responses.append(response)
            return response

        def authorize(call):
            authorized.append(call)
            expected = _auth_support.DEFAULT.id if authorized_principal is None else authorized_principal
            return call.principal == expected and call.name not in denied

        sessions = SessionStore()
        initial_tasks = asyncio.all_tasks()
        try:
            knowledge = await knowledge_search.configure(
                ConnectorConfig(settings.search_endpoint, ResourceAddress({"index": "fixture"}),
                                ("fixture.invalid",)), credential=credential,
                policy=Policy("synthetic-host-authorized", grants={"query", "read"},
                              limits=DataLimits(max_attempts=1)),
                transport=SimpleNamespace(request=search_request))
            async with httpx.MockTransport(handle) as model_transport:
                async with connect(settings.openai_endpoint, spec.model, provider="openai_completions",
                    credential="synthetic-external-service", allow_model_calls=True,
                    allowed_tools=tuple(tool.metadata.name for tool in spec.tools),
                    limits=Limits(max_output_tokens=4000, max_model_calls=12, max_tool_calls=64),
                    transport=model_transport) as model:
                    service = AgentService(adx, scanner, spec, connection=model, authorize_tool=authorize)
                    editor = AgentEditor(Path(settings.agent_store_dir), spec, settings.agent_models)
                    for name, value in {"agent": service, "agent_editor": editor,
                                        "sessions": sessions, "adx": adx, "scanner": scanner,
                                        "graph": graph, "inventory": inventory}.items():
                        monkeypatch.setattr(backend.app.state, name, value, raising=False)
                    _auth_support.install(backend.app)
                    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=backend.app),
                                                 base_url="http://fixture.invalid") as client:
                        yield SimpleNamespace(client=client, app=backend.app, spec=spec,
                            replies=replies, model_requests=model_requests, authorized=authorized,
                            denied=denied, adx=adx, transport=transport, credential=credential,
                            search_replies=search_replies, search_requests=search_requests,
                            data_replies=data_replies, knowledge=knowledge,
                            graph=graph, graph_driver=graph_driver, external_attempts=external_attempts)
                    await service.aclose()
                with pytest.raises(LlmError):
                    await model.chat.get_response("closed connection must refuse")
        finally:
            await graph.aclose()
            await knowledge_search.reset_client()
            await adx.aclose()
            await adx.aclose()
            assert not credential.closed
            credential.close()
        assert credential.closed
        assert not graph_driver.scripts or graph_driver.closed
        assert all(response.is_closed for response in responses)
        assert all(loop is asyncio.get_running_loop() for loop in model_loops + transport.loops + search_loops)
        assert external_attempts == [], external_attempts
        async with asyncio.timeout(1):
            pending = asyncio.all_tasks() - initial_tasks - {asyncio.current_task()}
            while pending:
                await asyncio.gather(*pending)
                pending = asyncio.all_tasks() - initial_tasks - {asyncio.current_task()}


@pytest_asyncio.fixture
async def native_asgi(monkeypatch, tmp_path):
    async with native_asgi_support(monkeypatch, tmp_path) as fixture:
        yield fixture


@pytest.mark.asyncio
@pytest.mark.parametrize("allowed,max_rows", [(True, 1), (False, 1), (True, 0)])
async def test_native_asgi_chat_data_owner_roundtrip(native_asgi, allowed, max_rows):
    import _auth_support
    from test_chat_sessions import frames

    fixture = native_asgi
    client = fixture.client
    created = await client.post("/api/sessions")
    assert created.status_code == 200, created.text
    session_id = created.json()["session_id"]
    chat_url, result_url = f"/api/chat/{session_id}", f"/api/sessions/{session_id}/result"
    result = await client.get(result_url)
    assert result.status_code == 200 and result.json()["result"] is None

    with _auth_support.anonymous():
        for method, url, body in [("POST", "/api/sessions", None),
                                  ("POST", chat_url, {"message": "refuse"}),
                                  ("GET", result_url, None)]:
            response = await client.request(method, url, json=body)
            assert response.status_code == 401
    with _auth_support.as_principal(_auth_support.OTHER):
        assert (await client.post(chat_url, json={"message": "refuse"})).status_code == 404
        assert (await client.get(result_url)).status_code == 404
    assert (await client.post(chat_url, json={"message": ""})).status_code == 422
    assert fixture.model_requests == fixture.transport.requests == []

    tool_name = "query_events_kql"
    if not allowed:
        fixture.denied.add(tool_name)
    arguments = {"query": "EventsUnified | project n, evidence_ids", "max_rows": max_rows}
    fixture.replies.append(completion([
        ({"role": "assistant", "tool_calls": [{"index": 0, "id": "call-data",
          "type": "function", "function": {"name": tool_name, "arguments": json.dumps(arguments)}}]}, None),
        ({}, "tool_calls")]))
    if allowed and max_rows:
        fixture.replies.append(completion([
            ({"role": "assistant", "content": "Evidence verified."}, None), ({}, "stop")]))
    response = await client.post(chat_url, json={"message": "Read the uncovered evidence projection."})
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store, private"
    events = frames(response.text)
    assert events, response.text

    if not allowed or not max_rows:
        assert events[-1][0] == "error", events
        assert not any(name == "done" for name, _ in events)
        assert len(fixture.model_requests) == 1
        assert fixture.transport.requests == fixture.credential.scopes == []
        interrupted = await client.post(chat_url, json={"message": "must not replay"})
        assert any(name == "error" for name, _ in frames(interrupted.text))
        assert len(fixture.model_requests) == 1
        assert (await client.get(result_url)).json()["result"] is None
    else:
        assert events[-1][0] == "done", events
        assert events[-1][1]["status"] == "completed"
        assert events[-1][1]["native"]["kind"] == "run.completed"
        assert len(fixture.authorized) == 1
        authorization = fixture.authorized[0]
        assert authorization.principal == _auth_support.DEFAULT.id
        assert authorization.name == tool_name and authorization.call_id == "call-data"
        assert {data["native"]["run_id"] for _, data in events} == {authorization.run_id}
        tool_result = next(data["result"] for name, data in events if name == "tool_result")
        assert "row-1" in json.dumps(tool_result)
        assert len(fixture.model_requests) == 2
        handoff = [message for message in fixture.model_requests[1]["messages"]
                   if message.get("role") == "tool"]
        assert len(handoff) == 1 and "row-1" in json.dumps(handoff[0])
        assert len(fixture.transport.requests) == 1
        data_request = fixture.transport.requests[0]
        assert data_request.url == "https://fixture.invalid/v2/rest/query"
        assert data_request.body["db"] == "fixture"
        assert "EventsUnified | project n, evidence_ids" in data_request.body["csl"]
        assert "| take 2" in data_request.body["csl"]
        result = (await client.get(result_url)).json()["result"]
        assert result["text"] == "Evidence verified." and result["status"] == "completed"
        assert result["run_id"] == authorization.run_id
        assert len(fixture.model_requests) == 2

        fixture.replies.append(completion([
            ({"role": "assistant", "content": "Follow-up verified."}, None), ({}, "stop")]))
        followup = await client.post(chat_url, json={"message": "Summarize the evidence already retrieved."})
        assert frames(followup.text)[-1][1]["status"] == "completed", followup.text
        assert (await client.get(result_url)).json()["result"]["text"] == "Follow-up verified."
        assert len(fixture.model_requests) == 3 and len(fixture.transport.requests) == 1
        assert any(message.get("role") == "assistant" and "Evidence verified." in json.dumps(message)
                   for message in fixture.model_requests[2]["messages"])
        assert fixture.adx.library_identity()["query_metrics"] == {
            "submitted": 1, "completed": 1, "known_attempts": 1, "unknown_attempt_queries": 0}

    assert not fixture.replies
    print(json.dumps({"external_services": "synthetic", "case": [allowed, max_rows],
        "model_attempts": len(fixture.model_requests), "adx_attempts": len(fixture.transport.requests),
        "native_terminal": events[-1][1].get("native", {}).get("kind")}))


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["summary", "summary/stream", "classify"])
async def test_native_asgi_situation_summary_and_classification(native_asgi, operation):
    import _auth_support
    from azdata import HttpResponse
    from knowledge_documents import build_document
    from test_chat_sessions import frames
    from test_situation_classification import situation, situation_type

    fixture = native_asgi
    client = fixture.client
    url = f"/api/cyber/situations/{operation}"
    envelope = situation().model_dump(mode="json")
    with _auth_support.anonymous():
        assert (await client.post(url, json=envelope)).status_code == 401
    assert (await client.post(url, json={"situation_id": "invalid"})).status_code == 422
    assert fixture.model_requests == fixture.search_requests == []

    summary = "The supplied replay recorded explicit credential use. Authorization remains unknown."
    candidate = build_document(situation_type())
    output = summary
    if operation == "classify":
        fixture.search_replies.append(HttpResponse(200, {"value": [candidate]}))
        output = json.dumps({"situation_type": candidate["title"], "confidence": "low",
            "basis": ["30 event-4648 records"], "alternatives": [],
            "not_established": ["Authorization is not established."]})
    fixture.replies.append(completion([
        ({"role": "assistant", "content": output}, None), ({}, "stop")], stream=operation == "summary/stream"))
    response = await client.post(url, json=envelope)
    assert response.status_code == 200, response.text
    assert len(fixture.model_requests) == 1
    assert not fixture.model_requests[0].get("tools")
    assert fixture.authorized == fixture.transport.requests == []
    if operation == "summary/stream":
        events = frames(response.text)
        assert [name for name, _ in events][-2:] == ["summary", "done"]
        assert events[-1][1]["status"] == "completed"
        assert events[-1][1]["run_id"]
        assert events[-2][1]["summary"] == summary
        assert "".join(data["token"] for name, data in events if name == "token") == summary
    elif operation == "summary":
        assert response.json()["summary"] == summary
        assert response.json()["status"] == "completed"
        assert response.json()["historical_replay"] is True
    else:
        result = response.json()
        assert "error" not in result, result
        assert result["situation_type"] == candidate["title"]
        assert result["citations"][0]["type_id"] == candidate["doc_id"]
        assert result["citations"][0]["path"] == candidate["path"]
        assert result["candidates_considered"] == 1
        assert candidate["title"] in json.dumps(fixture.model_requests[0]["messages"])
        assert len(fixture.search_requests) == 1
        assert "doc_kind eq 'situation_type'" in fixture.search_requests[0].body["filter"]

        fixture.search_replies.append(HttpResponse(200, {"value": [candidate]}))
        fixture.replies.append(completion([
            ({"role": "assistant", "content": json.dumps({"situation_type": "Invented type",
              "confidence": "high", "basis": [], "alternatives": [], "not_established": []})}, None),
                        ({}, "stop")], stream=False))
        refused = await client.post(url, json=envelope)
        assert refused.status_code == 200
        assert refused.json()["error"] == "unparseable_model_output"
        assert refused.json()["situation_type"] == ""
        assert len(fixture.model_requests) == len(fixture.search_requests) == 2
    assert not fixture.replies and not fixture.search_replies
    print(json.dumps({"external_services": "synthetic", "operation": operation,
        "model_attempts": len(fixture.model_requests), "search_attempts": len(fixture.search_requests)}))


@pytest.mark.asyncio
@pytest.mark.parametrize("supported,driver_failure,batch_records", [(True, False, False), (False, False, False),
                                                                 (True, True, False), (True, False, True)],
                         ids=["retrieved-ids", "unsupported-ids", "driver-failure", "batched-recording"])
async def test_native_asgi_diagnosis_toolchain(native_asgi, supported, driver_failure, batch_records):
    import _auth_support
    from datetime import datetime
    from azdata import HttpResponse
    from test_chat_sessions import frames
    from test_graph_service import edge_row, vertex
    from test_situation_classification import situation
    from app.cybereye.backend.knowledge.search import safe_key

    fixture = native_asgi
    envelope = situation().model_dump(mode="json")
    url = "/api/cyber/situations/diagnose"
    with _auth_support.anonymous():
        assert (await fixture.client.post(url, json=envelope)).status_code == 401
    assert (await fixture.client.post(url, json={"situation_id": "invalid"})).status_code == 422
    assert fixture.model_requests == fixture.search_requests == []

    candidate = {"doc_id": "attack:fixture-analytic", "doc_kind": "analytic", "source": "attack",
        "doc_type": "analytic", "title": "Explicit Credential Use", "technique_ids": ["T1078"],
        "platforms": ["Windows"], "path": "fixture/enterprise-attack.json", "commit": "a" * 40,
        "license": "fixture", "body": "Synthetic advisory about explicit credential use."}
    candidate["id"] = safe_key(f"analytic:{candidate['doc_id']}")
    resource_id = "native-event-1"
    timestamp = datetime.fromisoformat(envelope["first_seen"]).isoformat()
    citation_id = candidate["doc_id"] if supported else "unreturned-document"
    evidence_ids = [resource_id, candidate["doc_id"], "r1"] if supported else ["unreturned-document", "r1"]
    diagnosis = {
        "headline": "admLRhodes used explicit credentials on svpmn082 in the historical replay.",
        "narrative": "The supplied replay recorded explicit credential use on svpmn082. "
                     "Retrieved knowledge described credential access; authorization was not established.",
        "assessment": "insufficient_evidence", "confidence": "low",
        "supporting_observations": ["The supplied envelope reported 30 event-4648 records."],
        "would_change_the_call": ["An approved activity record would help establish authorization."],
        "evidence_ids": evidence_ids,
        "situation_type": candidate["title"] if supported else "Invented situation type",
        "citation_ids": [citation_id],
    }
    calls = [
        ("call-telemetry", "query_events_kql", {
            "query": "EventsUnified | project resource_id, source_time, device_name", "max_rows": 1}),
        ("call-knowledge", "search_mitre_attack", {"question": "explicit credential use",
            "technique_ids": ["T1078"], "behaviour_classes": ["credential_use"],
            "platforms": ["Windows"], "max_results": 1}),
        ("call-diagnosis", "record_situation_diagnosis", diagnosis),
        ("call-step", "record_sequence_step", {"position": 1,
            "description": "admLRhodes used explicit credentials on svpmn082.",
            "timestamp": timestamp, "evidence_ids": evidence_ids}),
        ("call-sequence", "complete_sequence_of_events", {
            "ordering_note": "One event timestamp did not establish authorization."}),
    ]
    fixture.data_replies.append(HttpResponse(200, [
        {"FrameType": "DataTable", "TableId": 0, "TableKind": "PrimaryResult",
         "TableName": "PrimaryResult", "Columns": [
             {"ColumnName": "resource_id", "ColumnType": "string"},
             {"ColumnName": "source_time", "ColumnType": "datetime"},
             {"ColumnName": "device_name", "ColumnType": "string"}],
         "Rows": [[resource_id, envelope["first_seen"], envelope["host"]]]},
        {"FrameType": "DataSetCompletion", "HasErrors": False}]))
    fixture.search_replies.append(HttpResponse(200, {"value": [candidate]}))
    groups = [[call] for call in calls] if not batch_records else [[calls[0]], [calls[1]], calls[2:]]
    for group in groups:
        fixture.replies.append(completion([
            ({"role": "assistant", "tool_calls": [{"index": index, "id": call_id,
              "type": "function", "function": {"name": tool_name,
                  "arguments": json.dumps(arguments)}} for index, (call_id, tool_name, arguments) in enumerate(group)]}, None),
            ({}, "tool_calls")]))
    fixture.replies.append(completion([
        ({"role": "assistant", "content": "Historical diagnosis recorded."}, None), ({}, "stop")]))

    response = await fixture.client.post(url, json=envelope)
    assert response.status_code == 200, response.text
    assert response.is_closed
    assert response.headers["cache-control"] == "no-store, private"
    events = frames(response.text)
    assert not any(name == "error" for name, _ in events), events
    terminal = events[-1]
    assert terminal[0] == "done" and terminal[1]["status"] == "completed", events
    assert terminal[1]["recorded"] is True and terminal[1]["sequenced"] is True
    assert sum(name == "done" for name, _ in events) == 1
    assert len(fixture.model_requests) == len(groups) + 1
    assert len(fixture.search_requests) == len(fixture.transport.requests) == 1
    assert "| take 2" in fixture.transport.requests[0].body["csl"]
    assert fixture.transport.requests[0].body["db"] == "fixture"
    assert "doc_kind eq 'analytic'" in fixture.search_requests[0].body["filter"]
    assert [(call.call_id, call.name) for call in fixture.authorized] == [
        (call_id, tool_name) for call_id, tool_name, _ in calls]
    assert all(call.principal == _auth_support.DEFAULT.id for call in fixture.authorized)
    run_ids = {call.run_id for call in fixture.authorized}
    assert len(run_ids) == 1
    assert {data["native"]["run_id"] for _, data in events if "native" in data} == run_ids

    recorded = next(data for name, data in events if name == "diagnosis")
    assert recorded["situation_id"] == envelope["situation_id"]
    assert recorded["historical_replay"] is True and recorded["fallback"] is False
    assert recorded["situation_type_supported"] is supported
    assert "citation_ids" not in recorded
    assert [citation["type_id"] for citation in recorded["citations"]] == (
        [candidate["doc_id"]] if supported else [])
    assert recorded["unsupported_citations"] == ([] if supported else [citation_id])
    if supported:
        assert recorded["citations"][0]["path"] == candidate["path"]
        assert recorded["citations"][0]["commit"] == candidate["commit"][:12]

    step = next(data for name, data in events if name == "sequence_step")
    assert step["position"] == 1 and step["timestamp"] == timestamp
    telemetry_result = next(data["result"] for name, data in events
                            if name == "tool_result" and data["name"] == "query_events_kql")
    native_time = telemetry_result["rows"][0]["source_time"]
    assert isinstance(native_time, str)
    assert datetime.fromisoformat(native_time) == datetime.fromisoformat(timestamp)
    assert [entry["evidence_id"] for entry in step["evidence"]] == (
        [resource_id, candidate["doc_id"]] if supported else [])
    assert step["unsupported_evidence_ids"] == (["r1"] if supported else evidence_ids)
    if supported:
        telemetry = step["evidence"][0]
        assert telemetry["record"]["resource_id"] == resource_id
        assert telemetry["record"]["source_time"] == str(native_time)
        assert datetime.fromisoformat(native_time) == datetime.fromisoformat(step["timestamp"])
        assert telemetry["retrieval"]["retrieval_id"] == "call-telemetry"
        assert telemetry["retrieval"]["datasource"] == "Azure Data Explorer table fixture.EventsUnified"
        assert telemetry["retrieval"]["query"] == calls[0][2]["query"]
        evidence = step["evidence"][1]
        assert evidence["record"]["doc_id"] == candidate["doc_id"]
        assert evidence["retrieval"]["retrieval_id"] == "call-knowledge"
        assert evidence["retrieval"]["tool"] == "search_mitre_attack"
        assert evidence["retrieval"]["datasource"] == "Azure AI Search index fixture"
        assert evidence["retrieval"]["row_count"] == 1
        assert "explicit credential use" in evidence["retrieval"]["query"]
    sequence = next(data for name, data in events if name == "sequence")
    assert sequence["steps"] == [{key: value for key, value in step.items()
                                  if key not in {"position", "situation_id"}}]
    assert sequence["ordering_note"] == calls[-1][2]["ordering_note"]
    assert [name for name, _ in events].index("diagnosis") < [name for name, _ in events].index("sequence_step")
    for request in fixture.model_requests[1:]:
        assert any(message.get("role") == "tool" for message in request["messages"])
    assert resource_id in json.dumps(fixture.model_requests[1]["messages"])
    assert candidate["doc_id"] in json.dumps(fixture.model_requests[2]["messages"])

    missing = HttpResponse(404, {"error": {"code": "DocumentNotFound", "message": "synthetic missing"}})
    fixture.search_replies.extend([missing, HttpResponse(200, candidate) if supported else missing])
    citation_url = f"/api/cyber/knowledge/type/{citation_id}"
    graph_url = "/api/cyber/graph/node"
    node_id, identity_id = f"host|{envelope['host']}", f"identity|{envelope['principal']}"
    fixture.graph_driver.table.extend([
        (f"g.V({json.dumps(node_id)}).valueMap", [vertex(node_id)]),
        ("bothE()", [edge_row("fixture-authentication", identity_id, node_id)]),
        ("both().dedup()", [vertex(identity_id, "Identity")])])
    graph_params = {"id": node_id if supported else "host|unreturned", "depth": 1,
                    "start": envelope["first_seen"], "end": envelope["last_seen"]}
    with _auth_support.anonymous():
        assert (await fixture.client.get(citation_url)).status_code == 401
        assert (await fixture.client.get(graph_url, params=graph_params)).status_code == 401
    assert len(fixture.search_requests) == 1 and fixture.graph_driver.scripts == []
    citation = await fixture.client.get(citation_url)
    if driver_failure:
        fixture.graph_driver.failure = "Connection was already closed. fixture-private-driver-detail"
    graph_response = await fixture.client.get(graph_url, params=graph_params)
    assert citation.is_closed and graph_response.is_closed
    assert citation.headers["cache-control"] == graph_response.headers["cache-control"] == "no-store, private"
    assert citation.status_code == (200 if supported else 404), citation.text
    assert graph_response.status_code == (503 if driver_failure else 200 if supported else 404), graph_response.text
    assert len(fixture.search_requests) == 3
    for request, kind in zip(fixture.search_requests[1:], ("situation_type", "analytic"), strict=True):
        assert request.method == "GET"
        assert safe_key(f"{kind}:{citation_id}") in request.url
    if supported:
        assert citation.json()["type_id"] == recorded["citations"][0]["type_id"]
        assert citation.json()["path"] == recorded["citations"][0]["path"]
        assert citation.json()["commit"][:12] == recorded["citations"][0]["commit"]
        assert citation.json()["body"] == candidate["body"]
    else:
        assert citation.json()["detail"] == "unknown situation type in the MITRE ATT&CK index"
    if driver_failure:
        assert graph_response.json()["detail"] == "gremlin_connection_closed"
        assert "fixture-private-driver-detail" not in graph_response.text
        assert len(fixture.graph_driver.scripts) == 1
    elif supported:
        graph_result = graph_response.json()
        assert graph_result["focus"] == node_id
        assert {node["id"] for node in graph_result["nodes"]} == {node_id, identity_id}
        assert graph_result["edges"][0]["id"] == "fixture-authentication"
        assert graph_result["edges"][0]["event_count"] == 1
        assert graph_result["edges"][0]["window_scoped"] is True
        assert len(fixture.graph_driver.scripts) == 3
        assert (await fixture.client.get(graph_url, params=graph_params)).json() == graph_result
        assert len(fixture.graph_driver.scripts) == 3
    else:
        assert graph_response.json()["detail"] == "unknown graph node"
        assert len(fixture.graph_driver.scripts) == 1
    assert fixture.graph_driver.closed
    assert len(fixture.model_requests) == len(groups) + 1 and len(fixture.transport.requests) == 1
    assert not fixture.replies and not fixture.search_replies and not fixture.data_replies
    print(json.dumps({"mode": "native-offline", "supported": supported, "driver_failure": driver_failure,
        "model_attempts": len(fixture.model_requests), "search_attempts": len(fixture.search_requests),
        "adx_attempts": len(fixture.transport.requests), "graph_attempts": len(fixture.graph_driver.scripts),
        "authorized_tools": len(fixture.authorized), "paid_requests": 0,
        "citations": len(recorded["citations"]), "evidence": len(step["evidence"]),
        "terminal": terminal[1]["status"]}))


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["version-change", "cancel"])
async def test_native_asgi_chat_session_terminal_controls(native_asgi, operation):
    import _auth_support
    from test_chat_sessions import frames

    fixture = native_asgi
    client = fixture.client
    prefix = "/api/cyber/agent-editor"
    if operation == "version-change":
        payload = {"name": "Native Investigator", "model": fixture.spec.model,
            "system_prompt": "SYNTHETIC-AUTHORED-VERSION-ONE",
            "instruction_files": [{"name": "context.md", "content": "SYNTHETIC-AUTHORED-CONTEXT"}],
            "tool_ids": [tool.metadata.name for tool in fixture.spec.tools],
            "base_version": 0, "expected_latest_version": 0}
        created = await client.post(f"{prefix}/agents", json=payload)
        assert created.status_code == 201, created.text
        authored = created.json()
        definition_url = f"{prefix}/agents/{authored['agent_id']}"
        assigned = await client.put(f"{prefix}/roles/investigator", json={
            "agent_id": authored["agent_id"], "version": 1, "expected_revision": 0})
        assert assigned.status_code == 200, assigned.text
        assert (await client.get(prefix)).json()["investigator"] == assigned.json()
        assert fixture.model_requests == []

    created = await client.post("/api/sessions")
    assert created.status_code == 200, created.text
    session_id = created.json()["session_id"]
    chat_url, result_url = f"/api/chat/{session_id}", f"/api/sessions/{session_id}/result"
    session = fixture.app.state.sessions.get(session_id, _auth_support.DEFAULT.id)
    assert session is not None and session.model_session.id == session_id
    with _auth_support.anonymous():
        assert (await client.post(chat_url, json={"message": "refuse"})).status_code == 401
        assert (await client.get(result_url)).status_code == 401
    with _auth_support.as_principal(_auth_support.OTHER):
        assert (await client.post(chat_url, json={"message": "refuse"})).status_code == 404
        assert (await client.get(result_url)).status_code == 404
    assert fixture.model_requests == []

    if operation == "version-change":
        fixture.replies.append(completion([
            ({"role": "assistant", "content": "Version one result."}, None), ({}, "stop")]))
        first = await client.post(chat_url, json={"message": "Use the authored investigator."})
        events = frames(first.text)
        assert events[-1][0] == "done" and events[-1][1]["status"] == "completed", events
        metadata = next(data for name, data in events if name == "metadata")
        assert metadata["agent_id"] == authored["agent_id"] and metadata["config_version"] == 1
        original_result = (await client.get(result_url)).json()
        assert original_result["result"]["text"] == "Version one result."
        assert original_result["result"]["run_id"] == metadata["run_id"]
        first_messages = json.dumps(fixture.model_requests[0]["messages"])
        assert payload["system_prompt"] in first_messages
        assert payload["instruction_files"][0]["content"] in first_messages
        with _auth_support.as_principal(_auth_support.OTHER):
            assert (await client.get(definition_url)).status_code == 404
            assert (await client.post(definition_url + "/versions", json=payload)).status_code == 404
            assert (await client.put(f"{prefix}/roles/investigator", json={
                "agent_id": authored["agent_id"], "version": 1, "expected_revision": 0})).status_code == 404
        second_payload = {**payload, "system_prompt": "SYNTHETIC-AUTHORED-VERSION-TWO",
                          "base_version": 1, "expected_latest_version": 1}
        saved = await client.post(definition_url + "/versions", json=second_payload)
        assert saved.status_code == 201 and saved.json()["version"] == 2, saved.text
        assert (await client.get(definition_url)).json()["system_prompt"] == second_payload["system_prompt"]
        assert (await client.get(definition_url, params={"version": 1})).json()["system_prompt"] == payload["system_prompt"]
        reassigned = await client.put(f"{prefix}/roles/investigator", json={
            "agent_id": authored["agent_id"], "version": 2,
            "expected_revision": assigned.json()["revision"]})
        assert reassigned.status_code == 200, reassigned.text
        assert (await client.get(prefix)).json()["investigator"] == reassigned.json()
        refused = await client.post(chat_url, json={"message": "Do not replay after editing."})
        assert refused.status_code == 409
        assert refused.json()["detail"] == "agent definition changed; create a new session"
        assert (await client.get(result_url)).json() == original_result
        assert len(fixture.model_requests) == 1
    else:
        started, closed = asyncio.Event(), asyncio.Event()

        class PendingCompletion(httpx.AsyncByteStream):
            async def __aiter__(self):
                yield completion([({"role": "assistant", "content": "Unfinished response."}, None)],
                                 terminal=False).content
                started.set()
                await asyncio.Event().wait()

            async def aclose(self):
                closed.set()

        provider_response = httpx.Response(200, headers={"content-type": "text/event-stream"},
                           stream=PendingCompletion())
        fixture.replies.append(provider_response)
        pending = asyncio.create_task(client.post(chat_url, json={"message": "Pause this native turn."}))
        try:
            async with asyncio.timeout(1):
                await started.wait()
                assert session.lock.locked()
                pending.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await pending
                await closed.wait()
        finally:
            if not pending.done():
                pending.cancel()
                async with asyncio.timeout(1):
                    await asyncio.gather(pending, return_exceptions=True)
            async with asyncio.timeout(1):
                await provider_response.aclose()
        assert not session.lock.locked()
        assert provider_response.is_closed
        assert session.model_session.id == session_id
        assert (await client.get(result_url)).json()["result"] is None
        assert len(fixture.model_requests) == 1
        refused = await client.post(chat_url, json={"message": "Do not resume the interrupted run."})
        refusal_events = frames(refused.text)
        assert refused.status_code == 200
        assert any(name == "error" for name, _ in refusal_events), refusal_events
        assert not any(name == "done" for name, _ in refusal_events)
        assert len(fixture.model_requests) == 1
        assert (await client.get(result_url)).json()["result"] is None

    fresh = await client.post("/api/sessions")
    assert fresh.status_code == 200
    fresh_id = fresh.json()["session_id"]
    assert fresh_id != session_id
    fixture.replies.append(completion([
        ({"role": "assistant", "content": "Fresh session result."}, None), ({}, "stop")]))
    resumed = await client.post(f"/api/chat/{fresh_id}", json={"message": "Start a new conversation explicitly."})
    resumed_events = frames(resumed.text)
    assert resumed.is_closed and resumed.headers["cache-control"] == "no-store, private"
    assert resumed_events[-1][0] == "done" and resumed_events[-1][1]["status"] == "completed"
    latest = (await client.get(f"/api/sessions/{fresh_id}/result")).json()["result"]
    assert latest["text"] == "Fresh session result." and latest["status"] == "completed"
    assert fixture.app.state.sessions.get(session_id, _auth_support.DEFAULT.id) is session
    assert len(fixture.model_requests) == 2
    fresh_messages = json.dumps(fixture.model_requests[1]["messages"])
    assert "Version one result." not in fresh_messages and "Unfinished response." not in fresh_messages
    if operation == "version-change":
        metadata = next(data for name, data in resumed_events if name == "metadata")
        assert metadata["agent_id"] == authored["agent_id"] and metadata["config_version"] == 2
        assert second_payload["system_prompt"] in fresh_messages
        assert payload["system_prompt"] not in fresh_messages
    assert fixture.transport.requests == fixture.search_requests == fixture.authorized == []
    assert fixture.graph_driver.scripts == [] and not fixture.replies
    print(json.dumps({"mode": "native-offline", "operation": operation,
        "model_attempts": len(fixture.model_requests), "automatic_replays": 0,
        "owner_result_readback": latest["status"], "paid_requests": 0}))