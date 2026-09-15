from copy import deepcopy
import json
import os
import sqlite3
from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.cybereye.backend.api.optimization import router
from app.cybereye.backend.optimization.cli import OptimizationTerminal
from app.cybereye.backend.optimization.evaluation import GradeEvaluator, model_request
from app.cybereye.backend.optimization.python_tools import PythonToolRunner
from app.cybereye.backend.optimization.service import OptimizationService
from app.cybereye.backend.optimization.workflow import BASELINE_DETECTOR, detect, detector_version, knowledge_arguments, verify_detector
from app.cybereye.backend.security import Principal, current_principal
from app.cybereye.tests.test_optimization_service import FixtureDataset


def test_detector_versions_preserve_unchanged_rules_and_revise_changed_rules():
    first = detector_version(deepcopy(BASELINE_DETECTOR), [], "first")
    proposal = {**deepcopy(BASELINE_DETECTOR), "parent_version": 1}
    second = detector_version(proposal, [first], "second")
    assert second["version"] == 2
    assert second["rules"][0]["revision"] == 1
    proposal["rules"][0]["code"] = 'def run(ctx):\n    return {"matched": False, "facts": ["No rule match"], "technique_ids": []}'
    proposal["parent_version"] = 2
    third = detector_version(proposal, [first, second], "third")
    assert third["rules"][0]["revision"] == 2
    assert first["rules"][0]["code"] == BASELINE_DETECTOR["rules"][0]["code"]
    verify_detector(first)
    changed = deepcopy(first)
    changed["rules"][0]["code"] += "\n"
    with pytest.raises(ValueError, match="rule content changed"):
        verify_detector(changed)
    with pytest.raises(ValueError, match="parent"):
        detector_version({**proposal, "parent_version": 99}, [first], "bad")
    proposal["rules"].append(proposal["rules"][0])
    with pytest.raises(ValueError, match="unique"):
        detector_version({**proposal, "parent_version": 1}, [first], "bad")


def test_detector_contract_preserves_misses_and_rejects_grade_output():
    class Dataset:
        result = {"matched": False, "facts": ["No matching evidence"], "technique_ids": []}

        def run_tool(self, case_id, tool, scope):
            assert case_id == "incident"
            return self.result

    dataset = Dataset()
    detector = detector_version(deepcopy(BASELINE_DETECTOR), [], "first")
    result = detect(dataset, "incident", detector)
    assert result["situations"] == []
    assert len(result["rule_results"]) == 1
    dataset.result = {"matched": True, "facts": ["Evidence present"], "technique_ids": ["T1078"]}
    assert detect(dataset, "incident", detector)["situations"][0]["technique_ids"] == ["T1078"]
    dataset.result["grade"] = "TruePositive"
    with pytest.raises(ValueError, match="only"):
        detect(dataset, "incident", detector)


def test_knowledge_search_arguments_are_bounded_and_not_executable():
    assert knowledge_arguments({"question": "credential evidence", "technique_ids": ["T1078"]})["max_results"] == 3
    for arguments in ({"max_results": 11}, {"sql": "SELECT labels"}, {"technique_ids": ["not-a-technique"]},
                      {"behaviour_classes": ["unknown"]}, {"question": "x" * 2001}):
        with pytest.raises(ValueError):
            knowledge_arguments(arguments)


class WorkflowDataset(FixtureDataset):
    def run_tool(self, case_id, tool, scope=None):
        if '"matched"' in tool.get("code", ""):
            return {"kind": "cybereye_tool_result", "historical_replay": True, "query_count": 1,
                    "data": {"matched": "False" not in tool["code"], "facts": ["Observed incident evidence"], "technique_ids": ["T1078"]}}
        return super().run_tool(case_id, tool, scope)


def test_baseline_detector_accepts_the_real_sandbox_result_envelope(tmp_path):
    executable = Path(os.getenv("CYBEREYE_PYTHON_SANDBOX", str(Path(__file__).resolve().parents[1] / ".local/tools/bubblewrap/usr/bin/bwrap")))
    if not executable.exists():
        pytest.skip("Local Python isolation is not installed")
    database = tmp_path / "case.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE evidence(event_time TEXT)")
        connection.execute("INSERT INTO evidence VALUES('2024-01-01')")
    runner = PythonToolRunner(str(executable))

    class Dataset:
        def run_tool(self, case_id, tool, scope=None):
            return runner.run(tool["code"], database, scope)

    detector = detector_version(deepcopy(BASELINE_DETECTOR), [], "first")
    result = detect(Dataset(), "case", detector)
    assert result["situations"][0]["matched"] is True
    assert result["situations"][0]["facts"] == ["1 evidence rows in the supplied incident"]


def test_joint_query_and_processing_use_only_window_evidence(tmp_path):
    import threading
    from app.cybereye.backend.optimization.dataset import GuideDataset
    from template_foundations.situation_detector import normalize_window

    executable = Path(os.getenv("CYBEREYE_PYTHON_SANDBOX", str(Path(__file__).resolve().parents[1] / ".local/tools/bubblewrap/usr/bin/bwrap")))
    if not executable.exists():
        pytest.skip("Local Python isolation is not installed")
    with sqlite3.connect(tmp_path / "source.sqlite") as connection:
        connection.execute("CREATE TABLE evidence(row_id,case_id,event_time,detector_id,category,mitre_techniques,entity_type,evidence_role)")
        connection.executemany("INSERT INTO evidence VALUES(?,?,?,?,?,?,?,?)", [
            (1, "a" * 16, "2024-01-01T00:00:00Z", "early", "category", "", "host", "source"),
            (2, "a" * 16, "2024-01-01T02:00:00Z", "late", "category", "", "host", "source")])
    dataset = GuideDataset.__new__(GuideDataset)
    dataset.root, dataset.contexts = tmp_path, tmp_path / "contexts"
    dataset.manifest, dataset.profile, dataset.lock = {"dataset_id": "fixture"}, [], threading.RLock()
    dataset.python_runner = PythonToolRunner(str(executable))
    window = normalize_window({"start": "2024-01-01T00:00:00Z", "end": "2024-01-01T00:30:00Z"}, 3600)
    rule = {"query": "SELECT detector_id FROM evidence", "parameters": {},
            "processing": {"max_rows": 10, "code": 'def process(rows, parameters):\n    return {"values": [row["detector_id"] for row in rows]}'}}
    result = dataset.detector_query("a" * 16, rule, window)
    assert result["rows"] == [{"detector_id": "early"}]
    assert dataset.detector_process("a" * 16, rule, result, window) == {"values": ["early"]}
    from app.cybereye.backend.optimization.joint_config import BASELINE_RULESETS
    detector = detector_version(BASELINE_RULESETS, [], "real-window")
    observed = detect(dataset, "a" * 16, detector, {"start": "2024-01-01T00:00:00Z", "end": "2024-01-01T00:30:00Z"})
    assert observed["summary"]["tests_run"] == 2
    assert observed["summary"]["observations"][0]["summary"]["evidence_rows"] == 1
    rule["query"] = "SELECT * FROM labels"
    with pytest.raises(ValueError):
        dataset.detector_query("a" * 16, rule, window)


def test_workflow_pins_detector_history_and_keeps_legacy_requests_unchanged(tmp_path):
    knowledge = Mock(return_value={"rows": [{"doc_id": "attack/T1078", "path": "techniques/T1078", "snippet": "Advisory"}]})
    predict = Mock(side_effect=lambda prompt, evidence, model: {
        "grade": "TruePositive", "rationale": "Observed evidence", "diagnosis": "Credential-use hypothesis",
        "proposed_actions": ["Review authorization before any response."], "citations": ["attack/T1078"] if "knowledge" in evidence else []})
    caller = Principal("local:workflow", issuer="local-preview")
    service = OptimizationService(WorkflowDataset(), tmp_path, "fixture", predict, knowledge_search=knowledge)
    try:
        experiment = service.create(caller, "Workflow fixture", workflow=True)
        identifier = experiment["id"]
        service.futures[identifier].result(timeout=5)
        service.futures[identifier].result(timeout=5)
        baseline = service.get(caller, identifier)["versions"][0]
        assert baseline["status"] == "completed"
        assert baseline["training_metrics"]["case_count"] == 1
        assert baseline["evaluation_metrics"]["case_count"] == 2
        assert baseline["situation_detector_version"] == 1
        knowledge.assert_called()
        assert knowledge.call_args.args[0]["technique_ids"] == ["T1078"]
        directory = service.directory(caller, identifier)
        original = (directory / "detectors/1.json").read_bytes()
        proposal = {"name": "Workflow successor", "parent_version": 1, "system_prompt": "Classify observed evidence.", "rationale": "Test changed rule",
                    "tools": [{"id": baseline["tool_ids"][0]}], "knowledge_access": False,
                    "improvements": ["Retain case-scoped evidence before triage.", "Revise the detector explanation explicitly.", "Ablate advisory knowledge for comparison."],
                    "design_audit": {"parent_training_run_id": baseline["training_runs"][-1]["id"],
                                     "observed_gaps": ["Minority classes remain incorrect in this fixture."],
                                     "changes": ["Revise the rule with an independent detector version."],
                                     "expected_tradeoffs": ["Knowledge ablation loses external context."]},
                    "situation_detector": {**deepcopy(BASELINE_DETECTOR), "parent_version": 1}}
        proposal["situation_detector"]["rules"][0]["description"] = "Changed evidence description"
        successor = service.publish(caller, identifier, proposal)
        assert successor["situation_detector_version"] == 2
        with pytest.raises(ValueError, match="development tuning"):
            service.evaluate(caller, identifier, 2)
        service.measure(caller, identifier, 2, "training", wait=True)
        service.evaluate(caller, identifier, 2, wait=True)
        assert service.get(caller, identifier)["versions"][1]["evaluation_metrics"]["error_rate"] == 0
        assert (directory / "detectors/1.json").read_bytes() == original
        assert service.detector(caller, identifier, 2)["rules"][0]["revision"] == 2
        snapshot = service.snapshot(caller)
        assert snapshot["detectors"][0]["agent_versions"] == [1]
        assert snapshot["detectors"][1]["agent_versions"] == [2]
        assert not service.get(caller, identifier)["versions"][1]["knowledge_access"]
        with pytest.raises(PermissionError):
            service.test_detector(caller, identifier, "b" * 16, 1)
        with pytest.raises(KeyError):
            service.detectors(Principal("local:other", issuer="local-preview"), identifier)
        run = baseline["training_runs"][-1]
        replay = service.exemplar(caller, identifier, 1, run["id"], "best")
        assert replay["case"]["actions_executed"] is False
        assert replay["case"]["transcript"]["response"]["citations"] == ["attack/T1078"]
        assert replay["case"]["transcript"]["request"]["max_output_tokens"] == 1200
        assert "expected" not in json.dumps(predict.call_args.args[1])
        legacy_request = model_request("Legacy prompt", {"time_window": {}, "tools": []}, "fixture")
        assert legacy_request["max_output_tokens"] == 350
        assert "proposed_actions" not in legacy_request["instructions"]
        service.knowledge_reference = {"index": "different-index"}
        with pytest.raises(ValueError, match="create a new experiment"):
            service.evaluate(caller, identifier, 2)
    finally:
        service.close()


def test_detection_misses_are_scored_and_never_execute_the_agent():
    detector = detector_version(deepcopy(BASELINE_DETECTOR), [], "first")
    detector["rules"][0]["code"] = 'def run(ctx):\n    return {"matched": False, "facts": ["No match"], "technique_ids": []}'
    predict = Mock()
    dataset = WorkflowDataset()
    evaluator = GradeEvaluator(dataset, predict)
    candidate = {"version": 1, "model": "fixture", "system_prompt": "Triage", "situation_detector_version": 1, "_detector": detector}
    rows, metrics = evaluator.run(candidate, [], dataset.cases(), lambda: False, lambda result: None, capture=True)
    assert metrics["case_count"] == 3 and metrics["macro_f1"] == 0
    assert all(row["situation_count"] == 0 and row["actions_executed"] is False for row in rows)
    predict.assert_not_called()
    assert all(row["transcript"]["model_call_attempted"] is False for row in rows)


def test_joint_response_schema_enforces_types_and_returned_citations_without_changing_legacy():
    evidence = {"situation_detector": {"schema_version": 2},
                "knowledge": {"result": {"rows": [{"doc_id": "actual-document", "path": "actual-path"}]}}}
    request = model_request("Triage", evidence, "fixture")
    response_format = request["text"]["format"]
    assert response_format["type"] == "json_schema" and response_format["strict"] is True
    schema = response_format["schema"]
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {"grade", "rationale", "diagnosis", "proposed_actions", "citations"}
    assert schema["properties"]["diagnosis"]["type"] == "string"
    assert schema["properties"]["proposed_actions"]["items"]["type"] == "string"
    assert schema["properties"]["citations"]["items"]["enum"] == ["actual-document", "actual-path"]
    assert request["max_output_tokens"] == 1200 and request["store"] is False
    evidence.pop("knowledge")
    assert model_request("Triage", evidence, "fixture")["text"]["format"]["schema"]["properties"]["citations"]["maxItems"] == 0
    evidence["situation_detector"].pop("schema_version")
    assert model_request("Legacy workflow", evidence, "fixture")["text"]["format"] == {"type": "json_object"}
    evidence.pop("situation_detector")
    assert model_request("Legacy grade", evidence, "fixture")["max_output_tokens"] == 350


def test_unknown_citations_are_refused_and_raw_response_remains_in_replay():
    detector = detector_version(deepcopy(BASELINE_DETECTOR), [], "first")
    answer = {"grade": "TruePositive", "rationale": "Evidence", "diagnosis": "Hypothesis",
              "proposed_actions": ["Review the evidence"], "citations": ["invented-document"]}
    knowledge = Mock(return_value={"rows": [{"doc_id": "actual-document"}]})
    evaluator = GradeEvaluator(WorkflowDataset(), lambda *args: answer, knowledge_search=knowledge)
    candidate = {"version": 1, "model": "fixture", "system_prompt": "Triage", "situation_detector_version": 1,
                 "knowledge_access": True, "_detector": detector}
    rows, metrics = evaluator.run(candidate, [], WorkflowDataset().cases(), lambda: False, lambda result: None, capture=True)
    assert metrics["error_rate"] == 1
    assert all(row["predicted"] is None and "citations" in row["error"] for row in rows)
    assert all(row["transcript"]["response"] == answer and row["actions_executed"] is False for row in rows)


def test_workflow_http_and_cli_enforce_owner_and_development_scope(tmp_path):
    caller = Principal("local:workflow-api", issuer="local-preview")
    knowledge = Mock(return_value={"rows": [], "category": "mitre_attack"})
    predict = Mock(return_value={"grade": "TruePositive", "rationale": "Evidence", "diagnosis": "Hypothesis", "proposed_actions": [], "citations": []})
    service = OptimizationService(WorkflowDataset(), tmp_path, "fixture", predict, knowledge_search=knowledge)
    application = FastAPI()
    application.include_router(router)
    application.state.optimization = service
    application.dependency_overrides[current_principal] = lambda: caller
    client = TestClient(application)
    try:
        response = client.post("/api/cyber/optimization/experiments", json={"name": "Workflow API", "workflow": True})
        assert response.status_code == 200
        identifier = response.json()["id"]
        service.futures[identifier].result(timeout=5)
        service.futures[identifier].result(timeout=5)
        base = f"/api/cyber/optimization/experiments/{identifier}"
        assert client.get(base + "/detectors").json()[0]["version"] == 1
        assert client.post(base + "/detector-preview", json={"case_id": "a" * 16, "detector": 1}).status_code == 200
        assert client.post(base + "/detector-preview", json={"case_id": "b" * 16, "detector": 1}).status_code == 404
        assert client.post(base + "/knowledge", json={"question": "credential use"}).status_code == 200
        assert client.post(base + "/knowledge", json={"max_results": 100}).status_code == 422
        terminal = OptimizationTerminal.__new__(OptimizationTerminal)
        terminal.service = service
        terminal.bindings = {"workspace": (caller, identifier)}
        result = terminal.operation("knowledge")("workspace", {"question": "credential use", "session_id": "session", "task_key": "test-key"}, {})
        assert result == knowledge.return_value
        assert "task_key" not in knowledge.call_args.args[0]
        assert terminal.operation("detector")("workspace", {}, {})["versions"][0]["version"] == 1
        application.dependency_overrides[current_principal] = lambda: Principal("local:foreign", issuer="local-preview")
        assert client.get(base + "/detectors").status_code == 404
        assert client.post(base + "/knowledge", json={"question": "credential use"}).status_code == 404
        application.dependency_overrides.clear()
        assert client.get(base + "/detectors").status_code == 401
    finally:
        service.close()