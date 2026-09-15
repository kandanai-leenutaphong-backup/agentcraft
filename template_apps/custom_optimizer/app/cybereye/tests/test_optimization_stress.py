import threading
import sqlite3
from collections import Counter

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.cybereye.backend.api.optimization import router
from app.cybereye.backend.optimization.dataset import GuideDataset
from app.cybereye.backend.optimization.evaluation import GradeEvaluator, audit_results
from app.cybereye.backend.optimization.service import OptimizationService, TOOL_FAMILIES, compare_evaluation
from app.cybereye.backend.optimization.runs import measure_run
from app.cybereye.backend.security import Principal, current_principal
from app.cybereye.tests.test_optimization_service import FixtureDataset
import pytest
import json


def test_full_run_retains_actual_best_worst_transcripts_and_small_metadata(tmp_path):
    class Dataset:
        def run_tool(self, case_id, tool, scope):
            return {"signal": case_id}

    cases = [{"case_id": str(index), "expected": "TruePositive", "split": "development",
              "start_time": "2024", "end_time": "2024"} for index in range(3)]
    evaluator = GradeEvaluator(Dataset(), lambda prompt, evidence, model: {
        "grade": "TruePositive" if evidence["tools"][0]["result"]["signal"] == "0" else "FalsePositive",
        "rationale": "Actual recorded response"})
    candidate = {"version": 1, "system_prompt": "Actual prompt", "model": "fixture"}
    record = measure_run(evaluator, candidate, [{"id": "tool_a", "name": "signal"}], cases,
                         {"id": "fixture", "stage": "training", "workers": 2}, tmp_path / "run", lambda: False, lambda count: None)
    assert record["status"] == "completed"
    assert record["metrics"]["mean_ms"] >= 0
    assert record["exemplars"]["best"]["correct"] is True
    assert record["exemplars"]["worst"]["correct"] is False
    assert "cases" not in record
    saved = json.loads((tmp_path / "run" / "best.json").read_text())
    assert saved["case"]["transcript"]["response"]["rationale"] == "Actual recorded response"
    assert saved["case"]["transcript"]["request"]["instructions"].startswith("Actual prompt")
    assert "expected" not in saved["case"]["transcript"]["request"]["input"]
    assert len((tmp_path / "run" / "cases.jsonl").read_text().splitlines()) == 3


def test_full_case_selection_preserves_all_rows_and_original_splits(tmp_path):
    with sqlite3.connect(tmp_path / "source.sqlite") as connection:
        connection.execute("CREATE TABLE cases(case_id,start_time,end_time,evidence_count)")
        connection.executemany("INSERT INTO cases VALUES(?,?,?,?)", [
            ("a" * 16, "2024", "2024", 2), ("b" * 16, "2024", "2024", 20),
            ("c" * 16, "2024", "2024", 201)])
    with sqlite3.connect(tmp_path / "labels.sqlite") as connection:
        connection.execute("CREATE TABLE labels(case_id,split,incident_grade)")
        connection.executemany("INSERT INTO labels VALUES(?,?,?)", [
            ("a" * 16, "development", "TruePositive"), ("b" * 16, "validation", "BenignPositive"),
            ("c" * 16, "final", "FalsePositive")])
    dataset = GuideDataset.__new__(GuideDataset)
    dataset.root = tmp_path
    cases = dataset.full_cases()
    assert cases == dataset.full_cases()
    assert Counter(case["stage"] for case in cases) == {"training": 1, "evaluation": 2}
    assert {case["split"] for case in cases} == {"development", "validation", "final"}
    assert {case["evidence_band"] for case in cases} == {"sparse", "ordinary", "large"}
    assert len({case["case_id"] for case in cases}) == 3


def test_full_campaign_stage_order_tool_lineage_and_owned_replays(tmp_path):
    dataset = FixtureDataset()
    dataset.full_cases = lambda: [{**case, "stage": "training" if case["split"] == "development" else "evaluation"}
                                  for case in dataset.cases()]
    service = OptimizationService(dataset, tmp_path, "fixture", lambda *args: {"grade": "TruePositive", "rationale": "Recorded answer"})
    caller = Principal("local:full", issuer="local-preview")
    try:
        identifier = service.create(caller, "Full campaign", "full-10")["id"]
        service.futures[identifier].result(timeout=5)
        service.futures[identifier].result(timeout=5)
        baseline = service.get(caller, identifier)["versions"][0]
        assert baseline["status"] == "completed"
        assert baseline["training_metrics"]["case_count"] == 1
        assert baseline["evaluation_metrics"]["case_count"] == 2
        directory = service.directory(caller, identifier)
        original = (directory / "versions/1.json").read_bytes()
        last_tool = None
        for number in range(2, 12):
            parent = service.feedback(caller, identifier, number - 1)
            definition = {"name": "matched_detector" if number <= 3 else f"signal_{number}",
                          "family": "detector-calibration" if number <= 3 else TOOL_FAMILIES[(number - 1) % 10],
                          "queries": "Incident-scoped development feature profiles", "returns": "A support-normalized signal",
                          "logic": "Normalize matched evidence before emitting a score",
                          "code": f"def run(ctx):\n    return {{'signal': {number}}}",
                          "change_rationale": ["Correct the measured class confusion using matched evidence."]}
            if number == 3:
                definition["supersedes"] = last_tool
            proposal = {"name": f"Audited generation {number - 1}", "parent_version": number - 1,
                        "rationale": "Development-led tuning", "system_prompt": "Use the recorded evidence only.",
                        "improvements": ["Gap: parent misses the false-positive class.", "Change: normalize detector evidence before grading.", "Risk: sparse cases may remain ambiguous."],
                        "design_audit": {"parent_training_run_id": parent["training_run_id"],
                                         "observed_gaps": ["FalsePositive recall is zero on this fixture."],
                                         "changes": ["Add a distinct support-normalized evidence signal."],
                                         "expected_tradeoffs": ["One additional tool invocation increases latency."]},
                        "tools": [{"id": baseline["tool_ids"][0]}, definition]}
            candidate = service.publish(caller, identifier, proposal)
            if number == 2:
                last_tool = candidate["tool_ids"][1]
                with pytest.raises(ValueError, match="development tuning"):
                    service.evaluate(caller, identifier, number)
            service.measure(caller, identifier, number, "training", wait=True)
            tuned = service.get(caller, identifier)["versions"][number - 1]
            assert tuned["status"] == "tuned"
            with pytest.raises(ValueError, match="Evaluate every"):
                service.finish(caller, identifier)
            service.evaluate(caller, identifier, number, wait=True)
        saved = service.get(caller, identifier)
        assert (directory / "versions/1.json").read_bytes() == original
        tools = service.snapshot(caller)["tools"]
        revisions = sorted([tool for tool in tools if tool["name"] == "matched_detector"], key=lambda tool: tool["revision"])
        assert [tool["revision"] for tool in revisions] == [1, 2]
        assert revisions[1]["supersedes"] == revisions[0]["id"]
        assert revisions[0]["first_agent_version"] == revisions[0]["last_agent_version"] == 2
        assert revisions[1]["first_agent_version"] == revisions[1]["last_agent_version"] == 3
        baseline_tool = next(tool for tool in tools if tool["id"] == baseline["tool_ids"][0])
        assert (baseline_tool["first_agent_version"], baseline_tool["last_agent_version"]) == (1, 11)
        assert service.finish(caller, identifier)["status"] == "completed"
        run_id = saved["versions"][1]["training_runs"][0]["id"]
        replay = service.exemplar(caller, identifier, 2, run_id, "best")
        assert replay["stage"] == "training"
        assert replay["case"]["transcript"]["response"]["rationale"] == "Recorded answer"
        with pytest.raises(KeyError):
            service.exemplar(Principal("other", issuer="local-preview"), identifier, 2, run_id, "best")
        with pytest.raises(KeyError):
            service.exemplar(caller, identifier, 2, run_id, "../../labels")
        application = FastAPI()
        application.include_router(router)
        application.state.optimization = service
        application.dependency_overrides[current_principal] = lambda: caller
        client = TestClient(application)
        endpoint = f"/api/cyber/optimization/experiments/{identifier}/versions/2/runs/{run_id}/examples/best"
        response = client.get(endpoint)
        assert response.status_code == 200
        assert response.json() == replay
        assert response.headers["cache-control"] == "no-store, private"
        application.dependency_overrides[current_principal] = lambda: Principal("other", issuer="local-preview")
        assert client.get(endpoint).status_code == 404
        application.dependency_overrides.clear()
        assert client.get(endpoint).status_code == 401
        feedback = json.dumps(service.feedback(caller, identifier))
        assert "b" * 16 not in feedback and "c" * 16 not in feedback
        with pytest.raises(ValueError, match="ended"):
            service.measure(caller, identifier, 2, "training")
    finally:
        service.close()


def test_ten_generation_contract_requires_audits_and_distinct_sources(tmp_path):
    dataset = FixtureDataset()
    dataset.stress_cases = lambda **kwargs: dataset.cases()
    service = OptimizationService(dataset, tmp_path, "test", lambda *args: {"grade": "TruePositive"})
    caller = Principal("local:stress", issuer="local-preview")
    try:
        experiment = service.create(caller, "Stress", "stress-10")
        identifier = experiment["id"]
        service.futures[identifier].result(timeout=5)
        with pytest.raises(ValueError, match="after the ten-generation"):
            service.verify_final(caller, identifier)
        with pytest.raises(ValueError, match="ten generations"):
            service.finish(caller, identifier)
        for number in range(2, 12):
            parent = service.feedback(caller, identifier, number - 1)
            proposal = {"name": f"Generation {number - 1}", "parent_version": number - 1,
                        "rationale": "Measured FalsePositive misses motivate a new evidence treatment. " * 9,
                        "system_prompt": "Use the new evidence and report one grade.",
                        "design_audit": {"parent_evaluation_id": parent["evaluation_id"], **{field: "Specific measured validation mistakes and intended response for this generation. " for field in ("approach", "observed_gaps", "changes", "expected_tradeoffs", "lesson_from_parent")}},
                        "tools": [{"name": f"Focused_{number}", "family": TOOL_FAMILIES[(number - 1) % len(TOOL_FAMILIES)],
                                   "queries": "Current incident evidence", "returns": "A focused signal", "logic": "Distinct test computation",
                                   "code": f"def run(ctx):\n    return {{'signal': {number}}}"}]}
            if number == 2:
                with pytest.raises(ValueError, match="audit"):
                    service.publish(caller, identifier, {**proposal, "design_audit": None})
                missing_family = {key: value for key, value in proposal["tools"][0].items() if key != "family"}
                with pytest.raises(ValueError, match="explicit family"):
                    service.publish(caller, identifier, {**proposal, "tools": [missing_family]})
            service.publish(caller, identifier, proposal)
            service.evaluate(caller, identifier, number, wait=True)
        with pytest.raises(ValueError, match="Repeat unchanged"):
            service.finish(caller, identifier)
        service.evaluate(caller, identifier, 1, wait=True)
        service.evaluate(caller, identifier, 2, wait=True)
        assert service.finish(caller, identifier)["status"] == "completed"
        saved = service.get(caller, identifier)
        assert len(saved["versions"]) == 11
        assert saved["limits"]["workers"] == 4
        assert all(version["design_audit"] for version in saved["versions"][1:])
        assert all(version["evaluations"][0]["audit"] for version in saved["versions"])
        service.verify_final(caller, identifier)
        service.futures[identifier].result(timeout=5)
        assert service.get(caller, identifier)["final_verification"]["status"] == "completed"
    finally:
        service.close()


def test_cancelling_full_training_never_launches_evaluation(tmp_path):
    started = threading.Event()
    released = threading.Event()
    dataset = FixtureDataset()
    dataset.full_cases = lambda: [{**case, "stage": "training" if case["split"] == "development" else "evaluation"}
                                  for case in dataset.cases()]

    def predict(*args):
        started.set()
        assert released.wait(timeout=5)
        return {"grade": "TruePositive", "rationale": "In-flight response retained"}

    service = OptimizationService(dataset, tmp_path, "fixture", predict)
    caller = Principal("local:cancel-full", issuer="local-preview")
    try:
        identifier = service.create(caller, "Cancel full training", "full-10")["id"]
        assert started.wait(timeout=5)
        assert service.cancel(caller, identifier)["status"] == "cancelled"
        released.set()
        service.futures[identifier].result(timeout=5)
        saved = service.get(caller, identifier)
        assert saved["status"] == "cancelled"
        assert saved["versions"][0]["status"] == "cancelled"
        assert saved["versions"][0]["evaluations"] == []
        assert saved["versions"][0]["training_runs"][0]["status"] == "cancelled"
        with pytest.raises(ValueError, match="ended"):
            service.evaluate(caller, identifier, 1)
        with pytest.raises(ValueError, match="ended"):
            service.measure(caller, identifier, 1, "training")
    finally:
        released.set()
        service.close()


def test_full_evaluation_refuses_an_interrupted_latest_training_retry(tmp_path):
    dataset = FixtureDataset()
    dataset.full_cases = lambda: [{**case, "stage": "training" if case["split"] == "development" else "evaluation"}
                                  for case in dataset.cases()]
    service = OptimizationService(dataset, tmp_path, "fixture", lambda *args: {"grade": "TruePositive"})
    caller = Principal("local:retry", issuer="local-preview")
    try:
        identifier = service.create(caller, "Retry guard", "full-10")["id"]
        service.futures[identifier].result(timeout=5)
        service.futures[identifier].result(timeout=5)
        experiment = service.get(caller, identifier)
        version = experiment["versions"][0]
        version["evaluations"] = []
        version["status"] = "failed"
        version["error"] = "Host restarted before the iteration reached a terminal state"
        version["training_runs"].append({"id": "interrupted", "status": "failed", "metrics": None,
                                          "error": version["error"]})
        experiment["status"] = "failed"
        experiment["error"] = version["error"]
        service._store(caller, experiment)
        assert service.get(caller, identifier)["versions"][0]["error"] == version["error"]
        assert service.get(caller, identifier)["error"] == version["error"]
        with pytest.raises(ValueError, match="development tuning"):
            service.evaluate(caller, identifier, 1)
        assert service.get(caller, identifier)["versions"][0]["evaluations"] == []
        service.measure(caller, identifier, 1, "training", wait=True)
        service.futures[identifier].result(timeout=5)
        recovered = service.get(caller, identifier)["versions"][0]
        assert [run["status"] for run in recovered["training_runs"]] == ["completed", "failed", "completed"]
        assert recovered["evaluations"][-1]["status"] == "completed"
        assert "error" not in recovered
        assert recovered["training_runs"][1]["error"] == version["error"]
        assert "error" not in service.get(caller, identifier)
    finally:
        service.close()


def test_cancel_during_full_run_persistence_remains_terminal(tmp_path, monkeypatch):
    dataset = FixtureDataset()
    dataset.full_cases = lambda: [{**case, "stage": "training" if case["split"] == "development" else "evaluation"}
                                  for case in dataset.cases()]
    service = OptimizationService(dataset, tmp_path, "fixture", lambda *args: {"grade": "TruePositive"})
    caller = Principal("local:late-cancel", issuer="local-preview")

    def finish_and_cancel(*args):
        result = measure_run(*args)
        service.cancel(caller, args[5].parent.parent.name)
        return result

    monkeypatch.setattr("app.components.agent_optimization.service.measure_run", finish_and_cancel)
    try:
        identifier = service.create(caller, "Late cancel guard", "full-10")["id"]
        service.futures[identifier].result(timeout=5)
        experiment = service.get(caller, identifier)
        assert experiment["status"] == "cancelled"
        training = experiment["versions"][0]["training_runs"][-1]
        assert training["status"] == "completed"
        assert training["cases_finished"] == training["case_count"] == 1
        assert experiment["versions"][0]["evaluations"] == []
        with pytest.raises(ValueError, match="ended"):
            service.measure(caller, identifier, 1, "training")
    finally:
        service.close()


def test_cancel_during_legacy_run_commit_remains_terminal(tmp_path, monkeypatch):
    service = OptimizationService(FixtureDataset(), tmp_path, "fixture", lambda *args: {"grade": "TruePositive"})
    caller = Principal("local:legacy-late-cancel", issuer="local-preview")
    cancelled = False

    def compare_and_cancel(experiment, candidate, evaluation, grades):
        nonlocal cancelled
        comparison = compare_evaluation(experiment, candidate, evaluation, grades)
        if evaluation["status"] == "completed" and not cancelled:
            cancelled = True
            service.cancel(caller, experiment["id"])
        return comparison

    monkeypatch.setattr("app.components.agent_optimization.service.compare_evaluation", compare_and_cancel)
    try:
        identifier = service.create(caller, "Legacy late cancel guard", "smoke")["id"]
        service.futures[identifier].result(timeout=5)
        experiment = service.get(caller, identifier)
        assert experiment["status"] == "cancelled"
        evaluation = experiment["versions"][0]["evaluations"][-1]
        assert evaluation["status"] == "completed"
        assert len(evaluation["cases"]) == 3
        with pytest.raises(ValueError, match="ended"):
            service.evaluate(caller, identifier, 1)
    finally:
        service.close()


def test_stress_audit_preserves_split_and_difficulty_failures():
    cases = [{"case_id": "a", "split": "development", "expected": "TruePositive", "predicted": "TruePositive", "correct": True, "elapsed_ms": 5, "evidence_band": "sparse"},
             {"case_id": "b", "split": "validation", "expected": "FalsePositive", "predicted": "TruePositive", "correct": False, "elapsed_ms": 20, "evidence_band": "large"},
             {"case_id": "c", "split": "validation", "expected": "BenignPositive", "predicted": None, "correct": False, "elapsed_ms": 30, "evidence_band": "ordinary", "error": "timeout"}]
    audit = audit_results(cases)
    assert audit["development"]["metrics"]["accuracy"] == 1
    assert audit["validation"]["metrics"]["accuracy"] == 0
    assert audit["validation"]["evidence_bands"]["large"]["case_count"] == 1
    assert audit["validation"]["errors"] == 1
    assert len(audit["validation"]["confusions"]) == 2


def test_parallel_evaluation_preserves_case_order_and_every_result():
    barrier = threading.Barrier(4)
    seen = []

    class Dataset:
        def run_tool(self, case_id, tool, scope):
            return {"row": case_id}

    def predict(prompt, evidence, model):
        assert "expected" not in str(evidence)
        barrier.wait(timeout=5)
        return {"grade": "TruePositive", "rationale": "test"}

    cases = [{"case_id": str(index), "expected": "TruePositive", "split": "validation", "start_time": "2024", "end_time": "2024"} for index in range(4)]
    results, metrics = GradeEvaluator(Dataset(), predict).run(
        {"system_prompt": "test", "model": "test"}, [{"name": "test"}], cases, lambda: False, seen.append, workers=4)
    assert [case["case_id"] for case in results] == ["0", "1", "2", "3"]
    assert Counter(case["case_id"] for case in seen) == Counter(case["case_id"] for case in cases)
    assert metrics["accuracy"] == 1