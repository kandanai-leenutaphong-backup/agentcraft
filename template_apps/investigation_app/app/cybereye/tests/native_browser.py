"""Loopback-only native browser fixture. Never imported by the production application."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import socket
import sys
from collections import deque
from contextvars import ContextVar
from pathlib import Path


def emit(kind, **payload):
    print(json.dumps({"kind": kind, **payload}), flush=True)


async def serve(state_dir, frontend_dist, public_key):
    import pytest
    import uvicorn
    from fastapi.staticfiles import StaticFiles
    from signed_dev_access import (
        InProcessReplayLedger,
        install_signed_request_auth,
        public_key_fingerprint,
    )

    sys.path.insert(0, str(Path(__file__).parent))
    from test_native_agent import completion, native_asgi_support
    import _auth_support
    from azdata import HttpResponse
    from app.cybereye.backend.security import OwnedCache, signed_developer_principal
    from app.cybereye.backend.security.gate import SCOPE_KEY
    from app.cybereye.backend.knowledge.search import safe_key

    fingerprint = public_key_fingerprint(public_key)
    assert fingerprint, "an ephemeral public verifier is required"
    owner = signed_developer_principal(fingerprint=fingerprint, slug="browser")
    requests = []
    request_path = ContextVar("native_browser_request_path")
    model_plans, data_plans, search_plans, graph_plans, attempts = {}, [], [], [], []
    model_prompts = {}
    native_rejections = []
    prepared = set()
    first_seen = "2026-08-13T02:30:00+00:00"
    last_seen = "2026-08-13T02:30:05+00:00"
    host, principal = "synthetic-host", "synthetic-analyst"
    resource_id = "synthetic-event-1"
    candidate = {"doc_id": "attack:synthetic-analytic", "doc_kind": "analytic", "source": "attack",
        "doc_type": "analytic", "title": "SYNTHETIC explicit credential use", "technique_ids": ["T1078"],
        "platforms": ["Windows"], "path": "synthetic/enterprise-attack.json", "commit": "a" * 40,
        "license": "Synthetic offline fixture", "body": "SYNTHETIC advisory about explicit credential use. "
        "No live MITRE retrieval or authorization conclusion."}
    candidate["id"] = safe_key(f"analytic:{candidate['doc_id']}")
    candidate["definition"] = candidate["body"]

    def table(columns, rows):
        return HttpResponse(200, [
            {"FrameType": "DataTable", "TableId": 0, "TableKind": "PrimaryResult",
             "TableName": "PrimaryResult", "Columns": [
                 {"ColumnName": name, "ColumnType": kind} for name, kind in columns], "Rows": rows},
            {"FrameType": "DataSetCompletion", "HasErrors": False}])

    def require_declared(condition, service, path, **detail):
        if not condition:
            native_rejections.append({"service": service, "path": path, **detail})
            raise AssertionError(f"undeclared native {service} attempt: {path}: {detail}")

    def model_response(body):
        path = request_path.get()
        plan_path = path if path in model_plans or not path.startswith("/api/chat/") else "/api/chat/"
        plan = model_plans.get(plan_path)
        require_declared(bool(plan), "model", path, plan=plan_path,
                 stream=body.get("stream", False), remaining=len(plan or ()))
        expected_stream, response = plan.popleft()
        assert body.get("stream", False) is expected_stream
        if plan_path in model_prompts:
            assert model_prompts[plan_path] in json.dumps(body["messages"]), "saved synthetic prompt was not used"
        attempts.append({"service": "model", "path": path, "plan": plan_path, "stream": expected_stream})
        return response

    def data_response(request):
        path = request_path.get()
        query = request.body["csl"]
        matches = [plan for plan in data_plans if plan["remaining"]
                   and path.startswith(plan["path"]) and plan["query"] in query]
        require_declared(len(matches) == 1, "adx", path, query=query, matching_plans=len(matches))
        plan = matches[0]
        plan["remaining"] -= 1
        assert request.url == "https://fixture.invalid/v2/rest/query"
        assert request.body["db"] == "fixture"
        properties = json.loads(request.body["properties"])
        assert properties["Options"]["request_readonly"] is True
        attempts.append({"service": "adx", "path": path, "plan": plan["name"], "query": query,
                         "parameters": properties.get("Parameters", {})})
        return plan["response"]

    def search_response(request):
        path = request_path.get()
        matches = [plan for plan in search_plans if plan["remaining"] and path == plan["path"]
                   and request.method == plan.get("method", "POST")
                   and plan.get("key", "") in request.url
                   and all((request.body or {}).get(key) == value for key, value in plan["body"].items())]
        require_declared(len(matches) == 1, "search", path, method=request.method,
                 url=request.url, body=request.body, matching_plans=len(matches))
        plan = matches[0]
        plan["remaining"] -= 1
        attempts.append({"service": "search", "path": path, "plan": plan["name"],
                         "method": request.method, "url": request.url, "body": request.body})
        return plan["response"]

    def prepare_health(fixture, *, graph_cached=False):
        data_plans.append({"name": "startup-health", "path": "/api/health",
            "query": "print principal = current_principal()", "remaining": 1,
            "response": table([("principal", "string")], [["SYNTHETIC offline principal"]])})
        for name, expression in [("documents", None), ("situation-types", "doc_kind eq 'situation_type'"),
                                 ("analytics", "doc_kind eq 'analytic'")]:
            search_plans.append({"name": "startup-health-" + name, "path": "/api/health",
                "body": {"search": "*", "count": True, "select": "id", "filter": expression},
                "remaining": 1, "response": HttpResponse(200, {"value": [], "@odata.count": 2 if name == "documents" else 1})})
        if graph_cached:
            return
        for name, query, rows, path in [
            ("vertices", "g.V().count()", [2], "/api/health"),
            ("edges", "g.E().count()", [1], "/api/health"),
            ("entities", '.project("id","label","name","event_count")', [], "/api/cyber/graph/entities"),
        ]:
            graph_plans.append({"name": "startup-" + name, "path": path,
                "query": query, "rows": rows, "remaining": 1})

    def prepare_scan(fixture):
        assert "scan" not in prepared, "scan phase may only be prepared once"
        prepared.add("scan")
        group_columns = [("host", "string"), ("principal", "string"), ("event_count", "long"),
                         ("first_seen", "datetime"), ("last_seen", "datetime"), ("evidence_ids", "dynamic")]
        for rule in fixture.app.state.scanner.engine.rules:
            count = {"explicit_credential_burst": 30, "tool_url_in_session_title": 1,
                     "directory_enumeration_alert": 1}.get(rule.rule_id)
            rows = [[host, principal, count, first_seen, last_seen, [resource_id]]] if count else []
            data_plans.append({"name": rule.rule_id, "path": "/api/cyber/scan/stream",
                "query": rule.query, "response": table(group_columns, rows), "remaining": 1})
        telemetry = table([("resource_id", "string"), ("source_time", "datetime"),
            ("device_name", "string"), ("target_host_name", "string"), ("win_event_id", "string")],
            [[resource_id, first_seen, host, principal, "4648"]])
        data_plans.append({"name": "cited-evidence", "path": "/api/cyber/evidence/",
            "query": "EventsUnified", "response": telemetry, "remaining": 1})
        query = "EventsUnified | project resource_id, source_time, device_name"
        data_plans.append({"name": "diagnosis-telemetry", "path": "/api/cyber/situations/diagnose",
            "query": query, "response": telemetry, "remaining": 1})
        search_plans.append({"name": "diagnosis-knowledge", "path": "/api/cyber/situations/diagnose",
            "body": {"search": "SYNTHETIC explicit credential use"}, "remaining": 1,
            "response": HttpResponse(200, {"value": [candidate]})})
        evidence_ids = [resource_id, candidate["doc_id"]]
        diagnosis = {"headline": "SYNTHETIC explicit credential activity in historical replay.",
            "narrative": "SYNTHETIC telemetry recorded explicit credential use on synthetic-host. "
            "Synthetic retrieved knowledge did not establish authorization.",
            "assessment": "insufficient_evidence", "confidence": "low",
            "supporting_observations": ["SYNTHETIC envelope contains 30 event-4648 records."],
            "would_change_the_call": ["An approved activity record would help establish authorization."],
            "evidence_ids": evidence_ids, "situation_type": candidate["title"],
            "citation_ids": [candidate["doc_id"]]}
        calls = [
            ("call-telemetry", "query_events_kql", {"query": query, "max_rows": 1}),
            ("call-knowledge", "search_mitre_attack", {"question": "SYNTHETIC explicit credential use",
                "technique_ids": ["T1078"], "behaviour_classes": ["credential_use"],
                "platforms": ["Windows"], "max_results": 1}),
            ("call-diagnosis", "record_situation_diagnosis", diagnosis),
            ("call-step", "record_sequence_step", {"position": 1,
                "description": "SYNTHETIC explicit credential event on synthetic-host.",
                "timestamp": first_seen, "evidence_ids": evidence_ids}),
            ("call-sequence", "complete_sequence_of_events", {
                "ordering_note": "SYNTHETIC single timestamp does not establish authorization."}),
        ]
        model_plans["/api/cyber/situations/diagnose"] = deque([
            (True, completion([({"role": "assistant", "tool_calls": [{"index": 0, "id": call_id,
                "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)}}]}, None),
                ({}, "tool_calls")])) for call_id, name, arguments in calls])
        model_plans["/api/cyber/situations/diagnose"].append((True, completion([
            ({"role": "assistant", "content": "SYNTHETIC historical diagnosis recorded."}, None), ({}, "stop")])))
        model_plans["/api/cyber/situations/summary/stream"] = deque([(True, completion([
            ({"role": "assistant", "content": "SYNTHETIC replay contains explicit credential use. "}, None),
            ({"content": "Authorization remains unknown; no live provider was contacted."}, None), ({}, "stop")]))])

    def prepare_query():
        assert "query" not in prepared
        prepared.add("query")
        data_plans.extend([
            {"name": "query-board-products", "path": "/api/cyber/query", "remaining": 2,
             "query": "summarize events=count() by product",
             "response": table([("product", "string"), ("events", "long")],
                               [["SYNTHETIC_WINDOWS", 30], ["SYNTHETIC_CYBERARK", 1]])},
            {"name": "query-board-empty-auth", "path": "/api/cyber/query", "remaining": 1,
             "query": "summarize events=count() by win_event_id",
             "response": table([("win_event_id", "string"), ("events", "long")], [])},
        ])

    def prepare_chat(fixture, session_id):
        assert "chat" not in prepared
        assert fixture.app.state.sessions.get(session_id, owner.id) is not None
        prepared.add("chat")
        path = "/api/chat/" + session_id
        query = "EventsUnified | project resource_id, source_time, category"
        data_plans.append({"name": "chat-telemetry", "path": path, "query": query, "remaining": 1,
            "response": table([("resource_id", "string"), ("source_time", "datetime"), ("category", "string")],
                              [["synthetic-chat-event-1", first_seen, "SYNTHETIC_CREDENTIAL_USE"]])})
        question = "SYNTHETIC chat credential evidence"
        search_plans.append({"name": "chat-knowledge", "path": path, "body": {"search": question},
            "remaining": 1, "response": HttpResponse(200, {"value": [candidate]})})
        calls = [
            ("chat-telemetry", "query_events_kql", {"query": query, "max_rows": 1}),
            ("chat-knowledge", "search_mitre_attack", {"question": question,
                "technique_ids": ["T1078"], "behaviour_classes": ["credential_use"],
                "platforms": ["Windows"], "max_results": 1}),
        ]
        model_plans[path] = deque([(True, completion([
            ({"role": "assistant", "tool_calls": [{"index": 0, "id": call_id, "type": "function",
                "function": {"name": name, "arguments": json.dumps(arguments)}}]}, None),
            ({}, "tool_calls")])) for call_id, name, arguments in calls])
        for text in ["SYNTHETIC chat returned one telemetry row and one advisory document. Authorization remains unknown.",
                     "SYNTHETIC follow-up reused the retrieved evidence without another data request."]:
            model_plans[path].append((True, completion([
                ({"role": "assistant", "content": text}, None), ({}, "stop")])))

    def prepare_knowledge():
        assert "knowledge" not in prepared
        prepared.add("knowledge")
        missing = HttpResponse(404, {"error": {"code": "DocumentNotFound", "message": "SYNTHETIC missing"}})
        for doc_id in (candidate["doc_id"], "unreturned-document"):
            for kind in ("situation_type", "analytic"):
                search_plans.append({"name": f"citation-{doc_id}-{kind}", "method": "GET",
                    "path": "/api/cyber/knowledge/type/" + doc_id, "body": {},
                    "key": safe_key(f"{kind}:{doc_id}"), "remaining": 1,
                    "response": HttpResponse(200, candidate) if doc_id == candidate["doc_id"]
                                and kind == "analytic" else missing})

    def prepare_profile(fixture, session_id, revision):
        assert revision in (1, 2, 3) and f"profile-{revision}" not in prepared
        assert fixture.app.state.sessions.get(session_id, owner.id) is not None
        prepared.add(f"profile-{revision}")
        path = "/api/chat/" + session_id
        assert not model_plans.get(path)
        query = "EventsUnified | project resource_id, source_time, target_user_name, device_name"
        data_plans.append({"name": f"profile-telemetry-{revision}", "path": path,
            "query": query, "remaining": 1,
            "response": table([("resource_id", "string"), ("source_time", "datetime"),
                ("target_user_name", "string"), ("device_name", "string")],
                [["synthetic-profile-event", first_seen, principal, host]])})
        calls = [
            ("get_suspect_profile", {"profile_id": "synthetic-analyst"}),
            ("query_events_kql", {"query": query, "max_rows": 1}),
            ("update_suspect_profile", {"profile_id": "synthetic-analyst", "expected_revision": revision - 1,
                "identity": {"account": principal, "display_name": "SYNTHETIC analyst"},
                "activity": [{"timestamp": first_seen,
                    "summary": f"SYNTHETIC historical credential activity on synthetic-host; revision {revision}. Authorization remains unknown.",
                    "evidence_ids": ["synthetic-profile-event"]}]}),
        ]
        model_plans[path] = deque([(True, completion([
            ({"role": "assistant", "tool_calls": [{"index": 0, "id": f"profile-{revision}-{name}",
                "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)}}]}, None),
            ({}, "tool_calls")])) for name, arguments in calls])
        model_plans[path].append((True, completion([
            ({"role": "assistant", "content": f"SYNTHETIC profile revision {revision} persisted."}, None),
            ({}, "stop")])))

    def prepare_graph():
        from test_graph_service import edge_row, vertex

        assert "graph" not in prepared
        prepared.add("graph")
        node_id, identity_id = "host|SYNTHETIC_HOST", "identity|SYNTHETIC_ANALYST"
        nodes = [vertex(node_id), vertex(identity_id, "Identity")]
        edges = [edge_row("SYNTHETIC_AUTHENTICATION", identity_id, node_id)]
        declarations = [
            ("overview-vertices", "overview", "g.V().groupCount().by(label)", [{"Host": 1, "Identity": 1}], 1),
            ("overview-edges", "overview", "g.E().groupCount().by(label)", [{"AUTHENTICATED_TO": 1}], 1),
            ("overview-kinds", "overview", 'g.E().groupCount().by("kind")', [{"event": 1}], 1),
            ("overview-first", "overview", '.values("first_seen")', [first_seen], 1),
            ("overview-last", "overview", '.values("last_seen")', ["2026-08-13T04:30:00Z"], 1),
            ("overview-seeds", "overview", ".limit(40).valueMap(true)", nodes, 1),
            ("core-nodes", "core", ".limit(260).valueMap(true)", nodes, 1),
            ("core-edges", "core", ".bothE().dedup().limit(1200)", edges, 1),
            ("search-missing", "search", 'TextP.containing("SYNTHETIC_MISSING")', [], 1),
            ("search-host", "search", 'TextP.containing("SYNTHETIC_HOST")', [nodes[0]], 1),
            ("node-missing", "node", 'g.V("host|SYNTHETIC_MISSING").valueMap(true)', [], 1),
            ("node-focus", "node", f"g.V({json.dumps(node_id)}).valueMap(true)", [nodes[0]], 2),
            ("node-direct", "node", ".bothE().limit(220)", edges, 2),
            ("node-neighbours", "node", ".both().dedup().limit(220)", [nodes[1]], 1),
            ("node-two-hops", "node", ".times(2).emit()", [nodes[1]], 1),
            ("node-core-edges", "node", ".bothE().where(__.otherV().hasLabel(", edges, 1),
        ]
        for name, route, query, rows, remaining in declarations:
            graph_plans.append({"name": name, "path": "/api/cyber/graph/" + route,
                                "query": query, "rows": rows, "remaining": remaining})

    def prepare_editor_turn(version):
        assert version in (1, 2) and f"editor-v{version}" not in prepared
        assert not model_plans.get("/api/chat/")
        prepared.add(f"editor-v{version}")
        model_prompts["/api/chat/"] = f"SYNTHETIC-EDITOR-PROMPT-V{version}"
        model_plans["/api/chat/"] = deque([(True, completion([
            ({"role": "assistant", "content": f"SYNTHETIC editor version {version} used its saved instructions."}, None),
            ({}, "stop")]))])

    with pytest.MonkeyPatch.context() as monkeypatch:
        async with native_asgi_support(monkeypatch, state_dir, authorized_principal=owner.id,
                                      model_response=model_response, data_response=data_response,
                                      search_response=search_response) as fixture:
            prepare_health(fixture)
            original_submit = fixture.graph_driver.submit

            def graph_response(script, bindings=None, **options):
                path = request_path.get()
                matches = [plan for plan in graph_plans if plan["remaining"]
                           and plan["path"] == path and plan["query"] in script]
                require_declared(len(matches) == 1, "graph", path, script=script, matching_plans=len(matches))
                plan = matches[0]
                plan["remaining"] -= 1
                attempts.append({"service": "graph", "path": path, "plan": plan["name"],
                                 "script": script, "bindings": bindings})
                fixture.graph_driver.table[:] = [(plan["query"], plan["rows"])]
                return original_submit(script, bindings=bindings, **options)

            monkeypatch.setattr(fixture.graph_driver, "submit", graph_response)
            with _auth_support.anonymous():
                monkeypatch.setattr(fixture.app.state, "last_scan", OwnedCache(), raising=False)
                assert fixture.app.middleware_stack is None
                assert install_signed_request_auth(
                    fixture.app, public_key_b64=public_key,
                    identity_factory=lambda slug: signed_developer_principal(
                        fingerprint=fingerprint, slug=slug),
                    replay_ledger=InProcessReplayLedger(), scope_key=SCOPE_KEY,
                )
                monkeypatch.setattr(fixture.app.router, "routes", [
                    route for route in fixture.app.router.routes if route.name != "frontend"
                ])
                fixture.app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")

                async def observed_app(scope, receive, send):
                    if scope["type"] != "http":
                        return await fixture.app(scope, receive, send)
                    observation = {"method": scope["method"], "path": scope["path"], "status": None}
                    requests.append(observation)

                    async def observe(message):
                        if message["type"] == "http.response.start":
                            observation["status"] = message["status"]
                        await send(message)

                    token = request_path.set(scope["path"])
                    try:
                        await fixture.app(scope, receive, observe)
                    finally:
                        request_path.reset(token)

                listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                listener.bind(("127.0.0.1", 0))
                listener.listen(128)
                listener.setblocking(False)

                class Server(uvicorn.Server):
                    async def startup(self, sockets=None):
                        await super().startup(sockets)
                        emit("ready", origin=f"http://127.0.0.1:{listener.getsockname()[1]}",
                             pid=os.getpid(), principal=owner.id, synthetic=True,
                                interpreter={"executable": sys.executable, "prefix": sys.prefix,
                                          "version": sys.version.split()[0]},
                             lifecycle="native_asgi_support; uvicorn lifespan=off")

                server = Server(uvicorn.Config(observed_app, lifespan="off", loop="asyncio",
                    ws="none", access_log=False, log_level="warning", timeout_graceful_shutdown=5))
                reader = asyncio.StreamReader()
                pipe, _ = await asyncio.get_running_loop().connect_read_pipe(
                    lambda: asyncio.StreamReaderProtocol(reader), sys.stdin)

                async def commands():
                    while line := await reader.readline():
                        command = json.loads(line)
                        if command["command"] == "stop":
                            server.should_exit = True
                            return
                        if command["command"] == "prepare-scan":
                            prepare_scan(fixture)
                            emit("response", id=command["id"], value={"prepared": "scan", "synthetic": True})
                            continue
                        if command["command"] == "prepare-query":
                            prepare_query()
                            emit("response", id=command["id"], value={"prepared": "query", "synthetic": True})
                            continue
                        if command["command"] == "prepare-chat":
                            prepare_chat(fixture, command["session_id"])
                            emit("response", id=command["id"], value={"prepared": "chat", "synthetic": True})
                            continue
                        if command["command"] == "prepare-profile":
                            prepare_profile(fixture, command["session_id"], command["revision"])
                            emit("response", id=command["id"], value={"prepared": "profile", "synthetic": True})
                            continue
                        if command["command"] == "prepare-profile-reload":
                            prepare_health(fixture, graph_cached=True)
                            emit("response", id=command["id"], value={"prepared": "profile-reload", "synthetic": True})
                            continue
                        if command["command"] == "prepare-knowledge":
                            prepare_knowledge()
                            emit("response", id=command["id"], value={"prepared": "knowledge", "synthetic": True})
                            continue
                        if command["command"] == "prepare-graph":
                            prepare_graph()
                            emit("response", id=command["id"], value={"prepared": "graph", "synthetic": True})
                            continue
                        if command["command"] == "prepare-editor-turn":
                            prepare_editor_turn(command["version"])
                            emit("response", id=command["id"], value={"prepared": "editor-turn", "synthetic": True})
                            continue
                        if command["command"] != "snapshot":
                            raise AssertionError("undeclared native browser phase")
                        emit("response", id=command["id"], value={
                            "synthetic": True, "http": requests,
                            "model_requests": fixture.model_requests,
                            "adx_attempts": len(fixture.transport.requests),
                            "search_attempts": len(fixture.search_requests),
                            "graph_scripts": fixture.graph_driver.scripts,
                            "attempts": attempts,
                            "data_plans_remaining": {plan["name"]: plan["remaining"] for plan in data_plans},
                            "search_plans_remaining": {plan["name"]: plan["remaining"] for plan in search_plans},
                            "graph_plans_remaining": {plan["name"]: plan["remaining"] for plan in graph_plans},
                            "model_plans_remaining": {path: len(plan) for path, plan in model_plans.items()},
                            "external_attempts": fixture.external_attempts,
                            "native_rejections": native_rejections,
                            "state_files": [{"path": str(path.relative_to(state_dir)), "bytes": path.stat().st_size}
                                            for path in sorted(state_dir.rglob("*")) if path.is_file()],
                            "last_scan": (fixture.app.state.last_scan.get(owner.id).model_dump(mode="json")
                                          if fixture.app.state.last_scan.get(owner.id) else None),
                            "authorized_tools": [{"name": call.name, "call_id": call.call_id,
                                "run_id": call.run_id, "principal": call.principal}
                                for call in fixture.authorized],
                            "test_resolver_principal": _auth_support._current.principal,
                        })
                    server.should_exit = True

                control = asyncio.create_task(commands())
                def command_finished(task):
                    if not task.cancelled() and task.exception() is not None:
                        emit("control-error", error=str(task.exception()))
                        server.should_exit = True
                control.add_done_callback(command_finished)
                try:
                    await server.serve(sockets=[listener])
                finally:
                    control.cancel()
                    await asyncio.gather(control, return_exceptions=True)
                    pipe.close()
                    listener.close()
    emit("closed", pid=os.getpid(), fixture_cleanup=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--frontend-dist", type=Path, required=True)
    args = parser.parse_args()
    assert os.environ.get("PYTHON_DOTENV_DISABLED") == "1"
    expected_python = os.environ.get("CYBEREYE_NATIVE_BROWSER_PYTHON", "")
    assert expected_python and Path(sys.executable).absolute() == Path(expected_python).absolute(), "selected interpreter mismatch"
    assert sys.prefix != sys.base_prefix and sys.version_info[:2] == (3, 12), "an isolated Python 3.12 environment is required"
    checkout = Path(__file__).resolve().parents[5]
    for directory in (args.state_dir, args.frontend_dist):
        assert directory.is_absolute() and not directory.resolve().is_relative_to(checkout), "fixture state must stay outside checkout"
        assert directory.is_dir()
    initial = json.loads(sys.stdin.readline())
    assert set(initial) == {"public_key"}, "stdin accepts a public verifier, never private credentials"
    asyncio.run(serve(args.state_dir, args.frontend_dist, initial["public_key"]))


if __name__ == "__main__":
    main()