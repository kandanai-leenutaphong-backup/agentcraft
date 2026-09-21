"""Production composition with explicit offline adapters for the real public package."""

from contextlib import contextmanager
from dataclasses import replace
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import unquote, urlsplit


@contextmanager
def public_runtime(monkeypatch, state_dir: Path, public_key: str, frontend_dist: Path | None = None):
    from azdata import HttpResponse, connect
    from fastapi.staticfiles import StaticFiles
    from signed_dev_access import InProcessReplayLedger, install_signed_request_auth, public_key_fingerprint
    from app.cybereye.backend import main
    from app.cybereye.backend.agents import config
    from app.cybereye.backend.agents import service as agent_service
    from app.cybereye.backend.data import telemetry as telemetry_module
    from app.cybereye.backend.inventory import probes, sources
    from app.cybereye.backend.knowledge import search
    from app.cybereye.backend.security import signed_developer_principal
    from app.cybereye.backend.security.gate import SCOPE_KEY
    from app.cybereye.backend.security.config import SecuritySettings
    from app.cybereye.backend.security.signin_routes import build_signin_router
    import _auth_support
    from test_cosmos_telemetry import PACKAGE, PackageGraph, PackageStore, public_package

    package = public_package()
    store = PackageStore(package["cosmos.json"])
    graph = PackageGraph()
    requests = []
    model_requests = []

    async def scripted_model(request):
        from test_native_agent import completion
        assert request.url.host == "fixture.openai.azure.com"
        body = json.loads(request.content)
        assert body["store"] is False
        model_requests.append(body)
        tool_names = {item["function"]["name"] for item in body.get("tools", [])}
        assert "query_events_kql" not in tool_names
        assert "get_dns_activity" not in tool_names
        messages = body["messages"]
        last_user = max(index for index, item in enumerate(messages) if item["role"] == "user")
        results = [item for item in messages[last_user + 1:] if item["role"] == "tool"]
        case = next(item for item in package["cosmos.json"] if item["kind"] == "incident")
        alarm = next(item for item in package["cosmos.json"] if item["kind"] == "alarm")
        event = next(item for item in package["cosmos.json"] if item["kind"] == "event")
        partition = case["partition"]
        stages = {
            0: [("list_public_cases", {})],
            1: [("list_public_alarms", {"partition": partition, "case_id": case["id"]})],
            2: [("get_public_evidence", {"partition": partition, "resource_ids": alarm["event_refs"]})],
            3: [
                ("get_public_entity_activity", {"partition": partition, "entity_id": event["entity_refs"]["host"],
                    "start": "2025-07-29T09:41:00Z", "end": "2025-07-29T09:43:00Z"}),
                ("get_public_graph_entity", {"partition": partition, "entity_id": event["entity_refs"]["process"]}),
                ("scan_public_situations", {"start": "2025-07-29T09:41:00Z", "end": "2025-07-29T09:43:00Z"}),
            ],
        }
        diagnosis = "Diagnose this situation" in str(messages[last_user].get("content", ""))
        if diagnosis:
            stages[6] = [("search_mitre_attack", {"question": "rundll32", "technique_ids": ["T1218.011"],
                "behaviour_classes": [], "platforms": ["Windows"], "max_results": 1})]
            if len(results) == 7:
                advisory = json.loads(results[-1]["content"])["rows"][0]
                stages[7] = [
                    ("record_situation_diagnosis", {
                        "headline": f"Scripted offline review of rundll32 evidence on {event['host']}.",
                        "narrative": "Scripted offline review of observed public emulation records. This is not external model judgment or incident ground truth.",
                        "assessment": "insufficient_evidence", "confidence": "low",
                        "supporting_observations": ["The public evidence tool returned source-linked process creation records."],
                        "would_change_the_call": ["Independent analyst review and wider scenario coverage remain required."],
                        "evidence_ids": alarm["event_refs"], "situation_type": advisory["title"],
                        "citation_ids": [advisory["doc_id"]],
                    }),
                    ("record_sequence_step", {"position": 1, "description": "Public emulation recorded rundll32 process creation.",
                        "timestamp": event["timestamp"], "evidence_ids": [event["resource_id"]]}),
                    ("complete_sequence_of_events", {"ordering_note": "Scripted offline transport; two-event smoke only."}),
                ]
        if not tool_names:
            return completion([({"role": "assistant", "content": "Scripted offline summary; no external model."}, None), ({}, "stop")], stream=body.get("stream", False))
        if len(results) in stages:
            calls = [{"index": index, "id": f"public-{len(results)}-{index}", "type": "function",
                      "function": {"name": name, "arguments": json.dumps(arguments)}}
                     for index, (name, arguments) in enumerate(stages[len(results)])]
            assert {item["function"]["name"] for item in calls}.issubset(tool_names)
            return completion([({"role": "assistant", "tool_calls": calls}, None), ({}, "tool_calls")])
        assert len(results) == (10 if diagnosis else 6)
        assert all("error" not in json.loads(item["content"]) for item in results)
        return completion([({"role": "assistant", "content":
            "Scripted offline transport completed six native public tools; no external model. "
            f"Observed emulation evidence: `{event['resource_id']}`. Not incident ground truth."}, None), ({}, "stop")])

    native_connect = agent_service.connect

    def model_connection(endpoint, model, **kwargs):
        import httpx
        kwargs.pop("capabilities", None)
        return native_connect(endpoint, model, **{**kwargs, "credential": "offline-fixture",
            "provider": "openai_completions", "allow_model_calls": True,
            "transport": httpx.MockTransport(scripted_model)})

    class Credential:
        async def get_token(self, *_args, **_kwargs):
            return SimpleNamespace(token="offline-test-token", expires_on=2**31)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            pass

    class SearchTransport:
        async def request(self, request):
            assert urlsplit(request.url).hostname == "fixture.search.windows.net"
            requests.append({"service": "search", "method": request.method, "url": request.url, "body": request.body})
            if request.method == "GET":
                decoded = unquote(request.url)
                matches = [item for item in package["search.json"] if f"('{item['id']}')" in decoded or decoded.split("?")[0].endswith("/" + item["id"])]
                return HttpResponse(200, matches[0]) if len(matches) == 1 else HttpResponse(404)
            assert request.method == "POST" and "/docs/search" in request.url
            body = request.body
            documents = package["search.json"]
            expression = body.get("filter", "") or ""
            for kind in ("analytic", "situation_type"):
                if f"doc_kind eq '{kind}'" in expression:
                    documents = [item for item in documents if item["doc_kind"] == kind]
            if "T1218.011" in expression:
                documents = [item for item in documents if "T1218.011" in item["technique_ids"]]
            text = body.get("search", "*")
            if text != "*":
                documents = [item for item in documents if text.casefold() in item["content"].casefold()]
            return HttpResponse(200, {"value": documents[:body.get("top", 1)], "@odata.count": len(documents)})

    configured = replace(main.settings, telemetry_profile="public-cosmos", adx_cluster_uri="",
        cosmos_endpoint="https://fixture.documents.azure.com", cosmos_database="public", cosmos_container="telemetry",
        public_manifest_path=str(PACKAGE / "manifest.json"),
        public_manifest_sha256=hashlib.sha256((PACKAGE / "manifest.json").read_bytes()).hexdigest(),
        agent_store_dir=str(state_dir / "agents"), search_endpoint="https://fixture.search.windows.net",
        knowledge_index="public-mitre", openai_endpoint="https://fixture.openai.azure.com/openai/v1/",
        allow_model_calls=False, graph_account="public-fixture", graph_database="public", graph_name="ontology",
        graph_resource_group="offline", graph_subscription_id="00000000-0000-0000-0000-000000000000")
    for module in (main, config, probes, sources, agent_service):
        monkeypatch.setattr(module, "settings", configured)
    monkeypatch.setattr(main, "DefaultAzureCredential", lambda **kwargs: Credential())
    monkeypatch.setattr(agent_service, "connect", model_connection)
    monkeypatch.setattr(main, "ReadOnlyAdx", lambda **kwargs: (_ for _ in ()).throw(AssertionError("ADX forbidden in public fixture")))
    monkeypatch.setattr(telemetry_module, "connect", lambda *args, **kwargs: store)
    monkeypatch.setattr(main, "bind_graph", lambda **kwargs: graph)
    monkeypatch.setattr(search, "connect", lambda service, config, **kwargs: connect(service, config, **{**kwargs, "transport": SearchTransport()}))
    monkeypatch.setattr(main.app, "middleware_stack", None)
    monkeypatch.setattr(main.app, "user_middleware", list(main.app.user_middleware))
    monkeypatch.setattr(main.app.router, "routes", [route for route in main.app.router.routes if route.name != "frontend"])
    identity_router = build_signin_router(settings=SecuritySettings(), validator=None, sessions=None)
    assert not any(getattr(route, "path", "") == "/api/whoami" for route in main.app.router.routes)
    main.app.router.routes.extend(route for route in identity_router.routes if route.path == "/api/whoami")
    fingerprint = public_key_fingerprint(public_key)
    assert install_signed_request_auth(main.app, public_key_b64=public_key,
        identity_factory=lambda slug: signed_developer_principal(fingerprint=fingerprint, slug=slug),
        replay_ledger=InProcessReplayLedger(), scope_key=SCOPE_KEY)
    main.app.state.public_transport = "SYNTHETIC store transport / real licensed public payload / scripted native SDK / no external model"
    if frontend_dist is not None:
        main.app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
    with _auth_support.anonymous():
        yield SimpleNamespace(app=main.app, telemetry=store, graph=graph, search_requests=requests,
                      model_requests=model_requests, package=package)