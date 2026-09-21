"""Real licensed payload, synthetic store adapter; no Azure or model calls."""

from copy import deepcopy
from datetime import datetime
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from azdata import ContentValue, DeleteRequest, QueryRequest, RecordKey, ResourceAddress

from app.cybereye.backend.data.telemetry import CosmosTelemetry
from app.cybereye.backend.config import Settings


PACKAGE = Path(__file__).resolve().parents[3] / "deploy/data/public-investigation/packages/c9a96ffcdc3775b89685bac82f9941140b8dc2e724ce5f94442a838ab52e8e12"


def public_package():
    manifest = json.loads((PACKAGE / "manifest.json").read_text())
    output = {}
    for filename in ("cosmos.json", "gremlin.json", "search.json"):
        payload = (PACKAGE / filename).read_bytes()
        assert hashlib.sha256(payload).hexdigest() == manifest["artifacts"][filename]["sha256"]
        output[filename] = json.loads(payload)
    return output


class PackageStore:
    def __init__(self, documents):
        self.documents = deepcopy(documents)
        self.requests = []

    async def query(self, request):
        self.requests.append(request)
        params = request.parameters
        assert request.dialect == "cosmos-sql"
        assert request.service_options["cosmos"]["partition"] == params["@partition"]
        rows = [item for item in self.documents if item["partition"] == params["@partition"]]
        for param, field in (("@kind", "kind"), ("@id", "id"), ("@case", "incident_id")):
            if param in params:
                rows = [item for item in rows if item.get(field) == params[param]]
        if "@ids" in params:
            rows = [item for item in rows if item["resource_id"] in params["@ids"]]
        if "@start" in params:
            rows = [item for item in rows if params["@start"] <= item["timestamp"] <= params["@end"]]
        if "@entity" in params:
            rows = [item for item in rows if params["@entity"] in item["entity_refs"].values()]
        return SimpleNamespace(status="success", truncated=False, continuation=None,
            items=[SimpleNamespace(status="success", content=ContentValue(item)) for item in rows], metrics={"attempts": 1})

    async def aclose(self):
        pass


def service():
    documents = public_package()["cosmos.json"]
    source = documents[0]["source"]
    telemetry = CosmosTelemetry(endpoint="https://fixture.documents.azure.com", database="public", container="telemetry",
        partition=documents[0]["partition"], source=source, credential=SimpleNamespace(get_token=AsyncMock()))
    telemetry.connector = PackageStore(documents)
    return telemetry


@pytest.mark.asyncio
async def test_real_case_alarm_event_entity_source_chain():
    telemetry = service()
    cases = await telemetry.cases(telemetry.partition)
    assert len(cases) == 1 and cases[0]["ground_truth_kind"] == "emulation_scenario"
    alarms = await telemetry.alarms(telemetry.partition, cases[0]["id"])
    assert len(alarms) == 1 and alarms[0]["derived"]
    events = await telemetry.evidence(telemetry.partition, alarms[0]["event_refs"])
    assert len(events) == 2
    for event in events:
        assert event["id"] != event["resource_id"] and event["label_status"] == "unlabelled"
        assert event["source"]["sha256"] == telemetry.source["sha256"]
        for entity in event["entity_refs"].values():
            matched = await telemetry.events(telemetry.partition, datetime.fromisoformat("2025-07-29T09:41:00+00:00"),
                datetime.fromisoformat("2025-07-29T09:43:00+00:00"), entity)
            assert event["id"] in {item["id"] for item in matched}


@pytest.mark.asyncio
async def test_unknown_foreign_source_and_query_refusals():
    telemetry = service()
    with pytest.raises(ValueError, match="foreign scenario"):
        await telemetry.cases("scenario-" + "0" * 64)
    with pytest.raises(ValueError, match="unknown document"):
        await telemetry.document(telemetry.partition, "event-" + "0" * 64)
    with pytest.raises(ValueError, match="unknown evidence"):
        await telemetry.evidence(telemetry.partition, [f"event://{telemetry.partition}/999"])
    with pytest.raises(ValueError, match="foreign or invalid"):
        await telemetry.evidence(telemetry.partition, ["event://foreign/1"])
    with pytest.raises(ValueError, match="raw queries"):
        await telemetry.query("DELETE FROM c")
    with pytest.raises(ValueError, match="KQL unavailable"):
        await telemetry.parameterized("EventsUnified | take 1", {})
    telemetry.connector.documents[0]["source"]["commit"] = "foreign"
    with pytest.raises(ValueError, match="foreign source"):
        await telemetry.cases(telemetry.partition)


@pytest.mark.asyncio
async def test_native_connector_refuses_mutation_and_target_override():
    documents = public_package()["cosmos.json"]
    credential = SimpleNamespace(get_token=AsyncMock())
    telemetry = CosmosTelemetry(endpoint="https://fixture.documents.azure.com", database="public", container="telemetry",
        partition=documents[0]["partition"], source=documents[0]["source"], credential=credential)
    result = await telemetry.connector.delete(DeleteRequest(keys=(RecordKey({"id": documents[0]["id"]}, telemetry.partition),)))
    assert result.status == "denied"
    result = await telemetry.connector.query(QueryRequest(dialect="cosmos-sql", expression="SELECT * FROM c",
        target=ResourceAddress({"database": "foreign", "container": "telemetry"})))
    assert result.status in {"denied", "invalid"}
    credential.get_token.assert_not_called()
    await telemetry.aclose()


def test_explicit_public_profile_and_legacy_default():
    from dataclasses import replace
    legacy = Settings()
    assert legacy.telemetry_profile == "adx"
    legacy.validate()
    public = replace(legacy, telemetry_profile="public-cosmos", adx_cluster_uri="",
        cosmos_endpoint="https://fixture.documents.azure.com", cosmos_database="public", cosmos_container="telemetry",
        public_manifest_path=str(PACKAGE / "manifest.json"),
        public_manifest_sha256=hashlib.sha256((PACKAGE / "manifest.json").read_bytes()).hexdigest())
    public.validate()
    assert public.public_manifest()["counts"]["events"] == 2
    with pytest.raises(RuntimeError, match="CYBEREYE_COSMOS_ENDPOINT"):
        replace(public, cosmos_endpoint="").validate()
    with pytest.raises(ValueError, match="digest mismatch"):
        replace(public, public_manifest_sha256="0" * 64).validate()
    with pytest.raises(RuntimeError, match="unknown CYBEREYE"):
        replace(public, telemetry_profile="fallback").validate()


@pytest.mark.asyncio
async def test_public_scan_uses_same_real_evidence_and_refuses_stale_alarm():
    from app.cybereye.backend.investigation.scanner import Scanner
    from app.cybereye.backend.models import ScanRequest
    telemetry = service()
    scanner = Scanner(telemetry)
    window = ScanRequest(start="2025-07-29T09:41:00Z", end="2025-07-29T09:43:00Z")
    result = await scanner.scan_async(window)
    assert result.summary.evidence_rows == 2 and len(result.situations) == 1
    assert result.situations[0].situation_id == next(item["id"] for item in telemetry.connector.documents if item["kind"] == "alarm")
    assert len(scanner.engine.rules) == 1
    events = [item async for item in scanner.stream_scan(window)]
    assert events[-1]["event"] == "done"
    next(item for item in telemetry.connector.documents if item["kind"] == "event")["fields"]["Image"] = "not-rundll32.exe"
    with pytest.raises(ValueError, match="stale derived alarm"):
        await scanner.scan_async(window)


class PackageGraph:
    def __init__(self):
        self.graph = public_package()["gremlin.json"]
        self.requests = []

    async def query(self, request):
        self.requests.append(request)
        assert request.dialect == "gremlin" and "has('partition',partition)" in request.expression
        if request.expression.startswith("g.V()"):
            rows = [{"id": item["id"], "label": item["label"], "name": item["name"],
                     **{key: [json.dumps(value) if isinstance(value, (dict, list)) else value]
                        for key, value in item["properties"].items()}} for item in self.graph["vertices"]]
        else:
            rows = [{"e": {"id": item["id"], "label": item["label"],
                           **{key: [json.dumps(value) if isinstance(value, (dict, list)) else value]
                              for key, value in item["properties"].items()}},
                     "from": item["from_id"], "to": item["to_id"]} for item in self.graph["edges"]]
        return SimpleNamespace(status="success", truncated=False, errors=[],
            items=[SimpleNamespace(status="success", error=None, content=ContentValue(item)) for item in rows])

    async def aclose(self):
        pass


@pytest.mark.asyncio
async def test_graph_process_drilldown_and_foreign_unknown_stale_refusals():
    from app.cybereye.backend.data.public_graph import PublicGraphService
    from app.cybereye.backend.data.graph import GraphNotFound, GraphUnavailable
    telemetry = service()
    connector = PackageGraph()
    graph = PublicGraphService(telemetry=telemetry, connector=connector)
    payload = await graph.core()
    assert len(payload["nodes"]) == 10 and len(payload["edges"]) == 19
    event = next(item for item in telemetry.connector.documents if item["kind"] == "event")
    for role in ("host", "user", "process"):
        node_id = event["entity_refs"][role]
        detail = await graph.neighbourhood(node_id)
        selected = next(item for item in detail["nodes"] if item["id"] == node_id)
        assert event["resource_id"] in selected["properties"]["evidence_refs"]
        assert selected["properties"]["source"] == telemetry.source
        assert selected["first_seen"].startswith("2025-07-29T09:4")
    with pytest.raises(GraphNotFound):
        await graph.neighbourhood("process-" + "0" * 64)
    with pytest.raises(GraphNotFound):
        await graph.neighbourhood(event["host"])
    connector.graph["vertices"][0]["properties"]["evidence_refs"] = [f"event://{telemetry.partition}/999"]
    with pytest.raises(GraphUnavailable, match="stale or unknown graph evidence"):
        await graph.core()
    connector.graph = public_package()["gremlin.json"]
    connector.graph["vertices"][0]["properties"]["source"]["commit"] = "foreign"
    with pytest.raises(GraphUnavailable, match="foreign graph source"):
        await graph.core()


@pytest.mark.asyncio
async def test_public_roster_native_tools_share_service_and_refuse_legacy(tmp_path):
    from dataclasses import replace
    from unittest.mock import patch
    from app.cybereye.backend.agents import config
    from app.cybereye.backend.agents.tools.base import ToolContext
    from app.cybereye.backend.agents.editor import AgentEditor
    from app.cybereye.backend.investigation.scanner import Scanner
    from _auth_support import DEFAULT, OTHER
    from app.cybereye.backend.agents.library import SaveAgent, LibraryError
    with patch.object(config, "settings", replace(config.settings, telemetry_profile="public-cosmos")):
        spec = config.load_agent_spec()
        with pytest.raises(config.ConfigError, match="legacy query tools"):
            config.load_agent_spec(config.CONFIG_PATH)
    tools = {item.metadata.name: item for item in spec.tools}
    assert "query_events_kql" not in tools and "get_dns_activity" not in tools
    telemetry = service()
    context = ToolContext(telemetry, Scanner(telemetry))
    cases = await tools["list_public_cases"].function(context)
    alarms = await tools["list_public_alarms"].function(context, partition=telemetry.partition, case_id=cases["rows"][0]["id"])
    evidence = await tools["get_public_evidence"].function(context, partition=telemetry.partition,
        resource_ids=alarms["rows"][0]["event_refs"])
    assert len(evidence["rows"]) == 2
    editor = AgentEditor(tmp_path, spec)
    assert editor.investigator_spec(DEFAULT).tools == spec.tools
    with pytest.raises(LibraryError, match="Unknown tools"):
        editor.library.save(DEFAULT, SaveAgent(name="Bad", model=spec.model, system_prompt="Bad", tool_ids=["query_events_kql"]))


@pytest.mark.asyncio
async def test_public_inventory_cosmos_contract_and_bound_query():
    from resource_explorer.probes import CosmosProbe
    from app.cybereye.backend.inventory.manifest import load_registry
    from app.cybereye.backend.agents.config import CONTROL_DIR
    from azdata import ItemResult, OperationResult
    telemetry = service()
    registry = load_registry(CONTROL_DIR / "public_data_inventory.yaml", env={
        "CYBEREYE_COSMOS_ENDPOINT": "https://fixture.documents.azure.com", "CYBEREYE_COSMOS_DATABASE": "public",
        "CYBEREYE_COSMOS_CONTAINER": "telemetry", "CYBEREYE_PUBLIC_PARTITION": telemetry.partition})
    assert registry.source_ids() == ("public-telemetry", "public-graph", "public-mitre")
    source = registry.sources()[0]
    assert source.source_type == "cosmos_container"
    probe = CosmosProbe()
    responses = []
    async def query(request):
        responses.append(request)
        assert request.service_options["cosmos"]["partition"] == telemetry.partition
        assert request.parameters["@partition"] == telemetry.partition
        rows = [{"document_count": 4}] if "COUNT(1)" in request.expression else telemetry.connector.documents[:1]
        return SimpleNamespace(status="success", errors=[], service="cosmos", truncated=False,
            items=[SimpleNamespace(status="success", error=None, content=ContentValue(item)) for item in rows], metrics={"attempts": 1})
    probe._client = lambda config: SimpleNamespace(query=query)
    assert (await probe.metadata(source)).metrics["document_count"] == 4
    assert (await probe.preview(source, limit=1)).status == "ok"
    assert (await probe.preview(source, limit=101)).status == "unavailable"
    assert len(responses) == 2


@pytest.mark.asyncio
async def test_production_lifespan_selects_public_services_without_adx(tmp_path, monkeypatch):
    from dataclasses import replace
    from app.cybereye.backend import main
    from app.cybereye.backend.agents import config
    from app.cybereye.backend.data import telemetry as telemetry_module
    from app.cybereye.backend.inventory import probes as probe_module
    from app.cybereye.backend.data.public_graph import PublicGraphService
    from fastapi import FastAPI
    configured = replace(main.settings, telemetry_profile="public-cosmos", adx_cluster_uri="",
        cosmos_endpoint="https://fixture.documents.azure.com", cosmos_database="public", cosmos_container="telemetry",
        public_manifest_path=str(PACKAGE / "manifest.json"),
        public_manifest_sha256=hashlib.sha256((PACKAGE / "manifest.json").read_bytes()).hexdigest(),
        agent_store_dir=str(tmp_path / "agents"), search_endpoint="", knowledge_index="",
        graph_account="public-fixture", graph_database="public", graph_name="ontology")
    monkeypatch.setattr(main, "settings", configured)
    monkeypatch.setattr(config, "settings", configured)
    monkeypatch.setattr(probe_module, "settings", configured)
    monkeypatch.setattr(telemetry_module, "connect", lambda *args, **kwargs: PackageStore(public_package()["cosmos.json"]))
    monkeypatch.setattr(main, "bind_graph", lambda **kwargs: PackageGraph())
    monkeypatch.setattr(main, "ReadOnlyAdx", lambda **kwargs: pytest.fail("public profile constructed ADX"))
    app = FastAPI()
    async with main.lifespan(app):
        assert isinstance(app.state.adx, CosmosTelemetry)
        assert isinstance(app.state.graph, PublicGraphService)
        assert app.state.agent.adx is app.state.adx and app.state.agent.graph is app.state.graph
        assert app.state.scanner.engine.telemetry is app.state.adx
        assert app.state.inventory.registry.source_ids() == ("public-telemetry", "public-graph", "public-mitre")
        assert "query_events_kql" not in app.state.agent.tools
        assert (await app.state.adx.health())["provider"] == "cosmos"


def test_signed_production_routes_real_package_and_owner_refusals(tmp_path, monkeypatch):
    import base64
    from datetime import timezone
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    from fastapi.testclient import TestClient
    from public_runtime import public_runtime
    private = Ed25519PrivateKey.generate()
    public = base64.b64encode(private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)).decode()
    def headers(method, path, body=b"", owner="public-test"):
        stamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        canonical = "\n".join((method, path, stamp, owner, hashlib.sha256(body).hexdigest())).encode()
        return {"X-Request-Timestamp": stamp, "X-Request-Context": owner,
                "X-Request-Signature": base64.b64encode(private.sign(canonical)).decode(), "Content-Type": "application/json"}
    with public_runtime(monkeypatch, tmp_path, public) as fixture, TestClient(fixture.app) as client:
        def get(path, owner="public-test"):
            return client.get(path, headers=headers("GET", path, owner=owner))
        assert client.get("/api/cyber/public/profile").status_code == 401
        profile = get("/api/cyber/public/profile").json()
        partition = profile["partition"]
        scenario = get("/api/cyber/scenarios").json()[0]
        assert scenario["start"] == "2025-07-29T09:41:00+00:00"
        assert scenario["end"] == "2025-07-29T09:43:00+00:00"
        cases = get(f"/api/cyber/public/cases?partition={partition}").json()
        alarms = get(f"/api/cyber/public/alarms?partition={partition}&case_id={cases[0]['id']}").json()
        events = fixture.package["cosmos.json"]
        event = next(item for item in events if item["kind"] == "event")
        assert get(f"/api/cyber/public/document?partition={partition}&id={event['id']}").json()["source"] == event["source"]
        assert get("/api/cyber/public/cases?partition=foreign").status_code == 422
        assert get(f"/api/cyber/public/document?partition={partition}&id=event-{'0' * 64}").status_code == 422
        assert get(f"/api/cyber/graph/node?id={event['entity_refs']['process']}").status_code == 200
        assert get("/api/cyber/graph/node?id=unknown").status_code == 404
        body = json.dumps({"query": "DELETE FROM c"}).encode()
        assert client.post("/api/cyber/query", content=body, headers=headers("POST", "/api/cyber/query", body)).status_code == 400
        body = json.dumps({"start": "2025-07-29T09:41:00Z", "end": "2025-07-29T09:43:00Z"}).encode()
        response = client.post("/api/cyber/scan", content=body, headers=headers("POST", "/api/cyber/scan", body))
        assert response.status_code == 200, response.text
        assert response.json()["summary"]["evidence_rows"] == 2
        evidence_path = f"/api/cyber/evidence/{alarms[0]['id']}"
        assert get(evidence_path).json()["row_count"] == 2
        assert get(evidence_path, owner="foreign-owner").status_code == 404
        signed = headers("GET", "/api/cyber/public/profile")
        assert client.get("/api/cyber/public/profile", headers=signed).status_code == 200
        assert client.get("/api/cyber/public/profile", headers=signed).status_code in {401, 403, 409}
        technique = get("/api/cyber/knowledge/type/T1218.011")
        assert technique.status_code == 200, technique.text
        assert "b4c5d044bf5a5f117ec241b2536c8cb709f53cdc" in technique.text


@pytest.mark.asyncio
async def test_public_time_boundary_excludes_fractional_event_after_end():
    telemetry = service()
    rows = await telemetry.events(telemetry.partition, datetime.fromisoformat("2025-07-29T09:41:00+00:00"),
        datetime.fromisoformat("2025-07-29T09:42:00+00:00"))
    assert len(rows) == 1 and rows[0]["ordinal"] == 2