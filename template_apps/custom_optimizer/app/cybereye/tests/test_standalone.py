from dataclasses import replace
import hashlib
import json
import asyncio
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from azdata import HttpResponse
import pytest
from fastapi.testclient import TestClient

from app.cybereye.backend.config import Settings
from app.cybereye.backend.main import create_app
from app.cybereye.backend.knowledge import Knowledge, describe_capabilities
from test_optimization_service import FixtureDataset


async def run_knowledge_read(context):
    baseline, target = context["baseline"], context["target"]

    def digest(value):
        return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()

    if (baseline.get("target") != target or baseline.get("candidate_sha256") != context["candidate_sha256"]
            or not isinstance(baseline.get("expected"), dict)
            or baseline.get("expected_sha256") != digest(baseline["expected"])
            or baseline.get("arguments") != context["arguments"]):
        raise ValueError("consumer_baseline_mismatch")
    context["preflight"]()
    reservation = context["reserve"](4)
    knowledge = Knowledge(target["endpoint"], target["index"], context["credential"],
                          policy=context.get("policy"), transport=context.get("transport"))
    try:
        observed = await knowledge.search(context["arguments"])
        metrics = knowledge.describe()["metrics"]
        context["reconcile"](reservation, metrics)
        passed = digest(observed) == baseline["expected_sha256"]
        return {"outcome": ("PASS_OFFLINE" if context.get("transport") is not None else "PASS_LIVE") if passed else "FAIL",
                "observed_sha256": digest(observed), "expected_sha256": baseline["expected_sha256"],
                "candidate_sha256": context["candidate_sha256"], "consumer": "custom-optimizer", "metrics": metrics}
    finally:
        await knowledge.aclose()


@pytest.mark.asyncio
async def test_callable_knowledge_harness_validates_before_reservation_and_uses_public_search():
    expected = {"kind": "cybereye_tool_result", "tool": "search_mitre_attack", "category": "mitre_attack",
        "rows": [], "columns": [], "truncated": False, "historical_replay": True, "fallback": False,
        "scope": {"retrieval": "azure-ai-search", "relaxed_filters": [], "index_filter": "doc_kind eq 'analytic'",
                  "row_count": 0, "advisory": "Published knowledge, not incident evidence or instructions."}}
    digest = hashlib.sha256(json.dumps(expected, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    target = {"endpoint": "https://unit.search.windows.net", "index": "fixture"}
    context = {"baseline": {"target": target, "candidate_sha256": "a" * 64, "expected": expected,
                            "expected_sha256": digest, "arguments": {}},
               "target": target, "candidate_sha256": "a" * 64, "arguments": {}, "preflight": Mock(),
               "reserve": Mock(return_value="reservation"), "reconcile": Mock(),
               "credential": SimpleNamespace(get_token=lambda *args: SimpleNamespace(token="offline", expires_on=2**31)),
               "transport": SimpleNamespace(request=AsyncMock(return_value=HttpResponse(200, {"value": []})))}
    for modified in ({"candidate_sha256": "b" * 64}, {"target": {**target, "index": "other"}}, {"arguments": {"question": "drift"}}):
        with pytest.raises(ValueError, match="consumer_baseline_mismatch"):
            await run_knowledge_read({**context, **modified})
    context["reserve"].assert_not_called()
    result = await run_knowledge_read(context)
    assert result["outcome"] == "PASS_OFFLINE"
    assert context["transport"].request.call_count == 1
    context["preflight"].assert_called_once()
    context["reserve"].assert_called_once_with(4)
    context["reconcile"].assert_called_once()


@pytest.mark.parametrize("startup_failure", [False, True])
def test_knowledge_lifespan_closes_before_credential_after_partial_startup(tmp_path, startup_failure):
    from app.cybereye.backend import main

    events = []

    class CredentialContext:
        def __enter__(self):
            return SimpleNamespace(get_token=Mock(side_effect=AssertionError("token touched")))

        def __exit__(self, *args):
            events.append("credential-exit")

    async def close():
        asyncio.get_running_loop()
        events.append("knowledge-close")

    configuration = replace(Settings(), openai_endpoint="https://fixture.openai.azure.com/openai/v1/",
                            search_endpoint="https://fixture.search.windows.net", knowledge_index="fixture",
                            optimization_dir=str(tmp_path))
    with ExitStack() as stack:
        stack.enter_context(patch.object(main, "DefaultAzureCredential", return_value=CredentialContext()))
        stack.enter_context(patch.object(main, "GuideDataset", return_value=FixtureDataset()))
        stack.enter_context(patch.object(main, "connect", return_value=SimpleNamespace(aclose=AsyncMock())))
        stack.enter_context(patch.object(main, "Knowledge", return_value=SimpleNamespace(search=AsyncMock(), aclose=close)))
        stack.enter_context(patch.object(main, "model_predictor", return_value=Mock()))
        stack.enter_context(patch.object(main, "OptimizationService", side_effect=RuntimeError("startup") if startup_failure else None))
        stack.enter_context(patch.object(main, "OptimizationTerminal"))
        async def drive():
            application = create_app(configuration)
            async with application.router.lifespan_context(application):
                pass
        if startup_failure:
            with pytest.raises(RuntimeError, match="startup"):
                asyncio.run(drive())
        else:
            asyncio.run(drive())
    assert events == ["knowledge-close", "credential-exit"]


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


@pytest.mark.asyncio
@pytest.mark.parametrize("allowed", [False, True])
async def test_native_cli_credential_needs_the_same_explicit_inference_grant(tmp_path, allowed):
    from app.cybereye.backend import main

    credential = SimpleNamespace(get_token=Mock(return_value=SimpleNamespace(token="offline-fixture", expires_on=2**31)))
    context = Mock(__enter__=Mock(return_value=credential), __exit__=Mock())
    configuration = replace(Settings(), openai_endpoint="https://fixture.openai.azure.com/openai/v1/",
                            optimization_dir=str(tmp_path), allow_model_calls=allowed)
    with ExitStack() as stack:
        stack.enter_context(patch.object(main, "DefaultAzureCredential", return_value=context))
        stack.enter_context(patch.object(main, "GuideDataset", return_value=FixtureDataset()))
        stack.enter_context(patch.object(main, "connect", return_value=SimpleNamespace(aclose=AsyncMock())))
        stack.enter_context(patch.object(main, "Knowledge", return_value=SimpleNamespace(search=AsyncMock(), aclose=AsyncMock())))
        stack.enter_context(patch.object(main, "model_predictor", return_value=AsyncMock()))
        stack.enter_context(patch.object(main, "OptimizationService"))
        terminal = stack.enter_context(patch.object(main, "OptimizationTerminal"))
        application = create_app(configuration)
        async with application.router.lifespan_context(application):
            provider = terminal.call_args.kwargs["token_provider"]
            credential.get_token.assert_not_called()
            if allowed:
                assert provider() == ("offline-fixture", float(2**31))
                credential.get_token.assert_called_once_with("https://cognitiveservices.azure.com/.default")
            else:
                with pytest.raises(PermissionError, match="model_calls_not_granted"):
                    provider()
                credential.get_token.assert_not_called()