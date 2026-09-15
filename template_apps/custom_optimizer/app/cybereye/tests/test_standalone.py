from dataclasses import replace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.cybereye.backend.config import Settings
from app.cybereye.backend.main import create_app
from app.cybereye.backend.knowledge import Knowledge, describe_capabilities
from test_optimization_service import FixtureDataset


def test_standalone_lifespan_composes_without_investigation_or_inference(tmp_path):
    configuration = replace(Settings(), openai_endpoint="https://fixture.openai.azure.com/openai/v1/",
                            search_endpoint="https://fixture.search.windows.net", knowledge_index="mitre-fixture",
                            optimization_dir=str(tmp_path / "optimization"),
                            copilot_workspace_dir=str(tmp_path / "workspaces"))
    with patch("app.cybereye.backend.main.GuideDataset", return_value=FixtureDataset()), \
            patch("azure.identity.DefaultAzureCredential.get_token", side_effect=AssertionError("startup must not request tokens")):
        with TestClient(create_app(configuration), base_url="http://127.0.0.1:9012", client=("127.0.0.1", 1234)) as client:
            response = client.get("/api/cyber/optimization")
            assert response.status_code == 200
            assert response.json()["available"] is True
            assert response.json()["experiments"] == []
            assert client.get("/api/cyber/scenarios").status_code == 404
            assert client.get("/api/cyber/agent-editor").status_code == 404
            assert client.get("/api/cyber/optimization", headers={"Origin": "https://foreign.example"}).status_code == 401


@pytest.mark.parametrize("peer,host,origin", [
    ("192.0.2.4", "127.0.0.1:9012", "http://127.0.0.1:5180"),
    ("127.0.0.1", "foreign.example", "http://127.0.0.1:5180"),
    ("127.0.0.1", "127.0.0.1:9012", "https://foreign.example"),
])
def test_remote_or_cross_origin_callers_are_refused(peer, host, origin):
    client = TestClient(create_app(), base_url="http://127.0.0.1:9012", client=(peer, 1234))
    response = client.get("/api/cyber/optimization", headers={"Host": host, "Origin": origin})
    assert response.status_code == 401
    assert response.content == b""


def test_capabilities_exclude_investigation_and_never_expose_labels():
    catalogue = describe_capabilities({"dataset_id": "fixture"}, {"workflow": True}, Knowledge("", "", None))
    assert {source["id"] for source in catalogue["sources"]} == {
        "guide.sqlite.evidence", "guide.sqlite.training_profile", "guide.sqlite.labels", "cyberkb.search.mitre_attack"}
    labels = next(source for source in catalogue["sources"] if source["id"] == "guide.sqlite.labels")
    assert labels["access"] == "evaluator_only"
    assert labels["operations"] == []