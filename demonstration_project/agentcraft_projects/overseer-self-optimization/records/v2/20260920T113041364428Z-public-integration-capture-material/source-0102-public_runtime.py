"""Production composition with explicit offline adapters for the real public package."""

from contextlib import contextmanager
from dataclasses import replace
import hashlib
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
    import _auth_support
    from test_cosmos_telemetry import PACKAGE, PackageGraph, PackageStore, public_package

    package = public_package()
    store = PackageStore(package["cosmos.json"])
    graph = PackageGraph()
    requests = []

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
    monkeypatch.setattr(main, "ReadOnlyAdx", lambda **kwargs: (_ for _ in ()).throw(AssertionError("ADX forbidden in public fixture")))
    monkeypatch.setattr(telemetry_module, "connect", lambda *args, **kwargs: store)
    monkeypatch.setattr(main, "bind_graph", lambda **kwargs: graph)
    monkeypatch.setattr(search, "connect", lambda service, config, **kwargs: connect(service, config, **{**kwargs, "transport": SearchTransport()}))
    monkeypatch.setattr(main.app, "middleware_stack", None)
    monkeypatch.setattr(main.app, "user_middleware", list(main.app.user_middleware))
    monkeypatch.setattr(main.app.router, "routes", [route for route in main.app.router.routes if route.name != "frontend"])
    fingerprint = public_key_fingerprint(public_key)
    assert install_signed_request_auth(main.app, public_key_b64=public_key,
        identity_factory=lambda slug: signed_developer_principal(fingerprint=fingerprint, slug=slug),
        replay_ledger=InProcessReplayLedger(), scope_key=SCOPE_KEY)
    main.app.state.public_transport = "SYNTHETIC store transport / real licensed public payload / models disabled"
    if frontend_dist is not None:
        main.app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
    with _auth_support.anonymous():
        yield SimpleNamespace(app=main.app, telemetry=store, graph=graph, search_requests=requests, package=package)