from dataclasses import replace
import hashlib
import json
import asyncio
from contextlib import ExitStack
from threading import get_ident
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


@pytest.mark.parametrize("startup_failure", [None, "service", "terminal", "configuration"])
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
    service = SimpleNamespace(close=Mock(side_effect=lambda: events.append("service-close")))
    terminal = SimpleNamespace(close=Mock(side_effect=lambda: events.append("terminal-close")))
    model = SimpleNamespace(aclose=AsyncMock(side_effect=lambda: events.append("model-close")))
    with ExitStack() as stack:
        stack.enter_context(patch.object(main, "DefaultAzureCredential", return_value=CredentialContext()))
        stack.enter_context(patch.object(main, "GuideDataset", return_value=FixtureDataset()))
        stack.enter_context(patch.object(main, "connect", return_value=model))
        stack.enter_context(patch.object(main, "Knowledge", return_value=SimpleNamespace(search=AsyncMock(), aclose=close)))
        stack.enter_context(patch.object(main, "model_predictor", return_value=Mock()))
        stack.enter_context(patch.object(main, "OptimizationService", return_value=service,
                                       side_effect=RuntimeError("startup") if startup_failure == "service" else None))
        terminal_error = (RuntimeError("startup") if startup_failure == "terminal" else
                          ValueError("configuration") if startup_failure == "configuration" else None)
        stack.enter_context(patch.object(main, "OptimizationTerminal", return_value=terminal, side_effect=terminal_error))
        application = create_app(configuration)
        user_state = object()
        application.state.user_state = user_state

        async def drive():
            async with application.router.lifespan_context(application):
                if startup_failure == "configuration":
                    assert application.state.optimization is None
                    assert application.state.optimization_error == "Optimizer configuration unavailable: ValueError"

        if startup_failure in {"service", "terminal"}:
            with pytest.raises(RuntimeError, match="startup"):
                asyncio.run(drive())
        else:
            asyncio.run(drive())
    expected = ([] if startup_failure else ["terminal-close"])
    if startup_failure != "service":
        expected.append("service-close")
    assert events == [*expected, "knowledge-close", "model-close", "credential-exit"]
    assert application.state.optimization_cleanup_complete is True
    assert application.state.user_state is user_state


@pytest.mark.asyncio
@pytest.mark.parametrize("times_out", [False, True])
async def test_lifespan_settlement_gates_borrowed_clients_and_retains_retry_owner(tmp_path, times_out):
    from app.cybereye.backend import main

    events = []
    entered, release = asyncio.Event(), asyncio.Event()
    loop = asyncio.get_running_loop()
    host_thread = get_ident()
    credential = SimpleNamespace(get_token=Mock(side_effect=AssertionError("token touched")))
    context = Mock(__enter__=Mock(return_value=credential),
                   __exit__=Mock(side_effect=lambda *args: events.append("credential-exit")))
    model = SimpleNamespace(aclose=AsyncMock(side_effect=lambda: events.append("model-close")))
    knowledge = SimpleNamespace(search=AsyncMock(),
                                aclose=AsyncMock(side_effect=lambda: events.append("knowledge-close")))
    terminal = SimpleNamespace(close=Mock(side_effect=lambda: events.append("terminal-close")))

    async def predict(*args):
        entered.set()
        await release.wait()
        assert not any(event in events for event in ("knowledge-close", "model-close", "credential-exit"))
        events.append("prediction-settled")
        return {"grade": "TruePositive", "rationale": "fixture"}

    configuration = replace(Settings(), openai_endpoint="https://fixture.openai.azure.com/openai/v1/",
                            search_endpoint="https://fixture.search.windows.net", knowledge_index="fixture",
                            optimization_dir=str(tmp_path / "optimization"),
                            copilot_workspace_dir=str(tmp_path / "workspaces"))
    with ExitStack() as stack:
        stack.enter_context(patch.object(main, "DefaultAzureCredential", return_value=context))
        stack.enter_context(patch.object(main, "GuideDataset", return_value=FixtureDataset()))
        stack.enter_context(patch.object(main, "connect", return_value=model))
        stack.enter_context(patch.object(main, "Knowledge", return_value=knowledge))
        stack.enter_context(patch.object(main, "model_predictor", return_value=predict))
        stack.enter_context(patch.object(main, "OptimizationTerminal", return_value=terminal))
        application = create_app(configuration)
        lifecycle = application.router.lifespan_context(application)
        await lifecycle.__aenter__()
        service = application.state.optimization
        cleanup = application.state.optimization_cleanup
        resources = application.state.optimization_resources
        user_state = object()
        application.state.user_state = user_state
        application.state.optimization_error = "host-owned-status"
        future = None
        original_close = service.close

        def close():
            assert get_ident() != host_thread
            events.append("service-close")
            original_close(timeout=0.05 if times_out else 2)
            events.append("service-settled")

        close_mock = stack.enter_context(patch.object(service, "close", side_effect=close))
        try:
            experiment = service.create(main.LOCAL_PRINCIPAL, "Lifespan settlement")
            identifier = experiment["id"]
            future = service.futures[identifier]
            await asyncio.wait_for(entered.wait(), timeout=2)
            stop = service.stops[identifier]
            original_set = stop.set

            def signal():
                original_set()
                if not times_out:
                    loop.call_soon_threadsafe(release.set)

            stack.enter_context(patch.object(stop, "set", side_effect=signal))
            if times_out:
                with pytest.raises(TimeoutError, match="^optimization_close_timeout$"):
                    await lifecycle.__aexit__(None, None, None)
                with pytest.raises(TimeoutError, match="^optimization_close_timeout$"):
                    await cleanup()
                assert application.state.optimization_cleanup_complete is False
                assert not future.done()
                assert events == ["terminal-close", "service-close", "service-close"]
                knowledge.aclose.assert_not_awaited()
                model.aclose.assert_not_awaited()
                context.__exit__.assert_not_called()
                before = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
                for submit in (lambda: service.create(main.LOCAL_PRINCIPAL, "Refused"),
                               lambda: service.evaluate(main.LOCAL_PRINCIPAL, identifier, 1),
                               lambda: service.measure(main.LOCAL_PRINCIPAL, identifier, 1, "training"),
                               lambda: service.verify_final(main.LOCAL_PRINCIPAL, identifier)):
                    with pytest.raises(RuntimeError, match="^optimization_service_closing$"):
                        submit()
                assert before == {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
                release.set()
                await asyncio.wait_for(asyncio.wrap_future(future), timeout=2)
                await asyncio.gather(cleanup(), cleanup())
            else:
                await lifecycle.__aexit__(None, None, None)
            await cleanup()
            assert application.state.optimization_cleanup_complete is True
            assert application.state.optimization is service
            assert application.state.optimization_terminal is terminal
            assert application.state.knowledge is knowledge
            assert application.state.optimization_resources is resources
            assert application.state.optimization_cleanup is cleanup
            assert application.state.user_state is user_state
            assert application.state.optimization_error == "host-owned-status"
            assert future.done()
            assert service.get(main.LOCAL_PRINCIPAL, identifier)["versions"][0]["evaluations"][-1]["status"] == "cancelled"
            assert events[-5:] == ["prediction-settled", "service-settled", "knowledge-close", "model-close", "credential-exit"] if not times_out else events[-4:] == ["service-settled", "knowledge-close", "model-close", "credential-exit"]
            assert events.count("prediction-settled") == 1
            assert close_mock.call_count == (3 if times_out else 1)
            terminal.close.assert_called_once()
            knowledge.aclose.assert_awaited_once()
            model.aclose.assert_awaited_once()
            context.__exit__.assert_called_once()
            credential.get_token.assert_not_called()
        finally:
            release.set()
            if future is not None:
                await asyncio.wait_for(asyncio.wrap_future(future), timeout=2)
            await lifecycle.__aexit__(None, None, None)
            await cleanup()


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