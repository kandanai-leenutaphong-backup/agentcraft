from copy import deepcopy
import json
from unittest.mock import Mock

import pytest

from app.cybereye.backend.optimization.service import OptimizationService
from app.cybereye.backend.security import Principal
from app.cybereye.tests.test_optimization_service import FixtureDataset
from app.cybereye.backend.optimization.cli import OptimizationTerminal


class JointDataset(FixtureDataset):
    def cases(self):
        return [{**case, "split": "development"} for case in super().cases()] + [
            {**super().cases()[0], "case_id": "d" * 16, "split": "validation"}]

    def detector_query(self, case_id, rule, window):
        return {"rows": [{"signal": case_id[0]}]}

    def detector_process(self, case_id, rule, result, window):
        return {"matched": True, "facts": ["Observed value " + result["rows"][0]["signal"]],
                "technique_ids": [], "summary": result["rows"][0]}


def test_twelve_generations_keep_full_cohorts_and_creative_contract(tmp_path):
    class Dataset(JointDataset):
        def full_cases(self):
            return self.cases()

    caller = Principal("local:twelve-generation", issuer="local-preview")
    answer = {"grade": "TruePositive", "rationale": "Fixture", "diagnosis": "Fixture hypothesis", "proposed_actions": [], "citations": []}
    service = OptimizationService(Dataset(), tmp_path, "fixture", lambda *arguments: answer, knowledge_search=lambda arguments: {"rows": []})
    try:
        experiment = service.create(caller, "Twelve-generation fixture", "joint-12", creative=True)
        service.futures[experiment["id"]].result(timeout=5)
        service.futures[experiment["id"]].result(timeout=5)
        saved = service.get(caller, experiment["id"])
        assert saved["limits"]["min_versions"] == saved["limits"]["max_versions"] == 13
        assert saved["limits"]["workers"] == 8
        assert saved["stage_counts"] == {"training": 3, "evaluation": 1}
        assert saved["versions"][0]["generation"] == 0
        assert saved["versions"][0]["status"] == "completed"
        assert "no untouched test" in saved["evaluation_policy"]
    finally:
        service.close()


def test_joint_publication_requires_successful_exact_probes_and_lever_audit(tmp_path):
    caller = Principal("local:joint-fixture", issuer="local-preview")
    predict = Mock(return_value={"grade": "TruePositive", "rationale": "Observed", "diagnosis": "Hypothesis", "proposed_actions": [], "citations": []})
    service = OptimizationService(JointDataset(), tmp_path, "fixture", predict, knowledge_search=lambda arguments: {"rows": []})
    try:
        identifier = service.create(caller, "Joint fixture", "joint-smoke")["id"]
        service.futures[identifier].result(timeout=5)
        service.futures[identifier].result(timeout=5)
        experiment = service.get(caller, identifier)
        baseline = experiment["versions"][0]
        assert baseline["status"] == "completed"
        assert baseline["process_contract"]["version"] == "joint-query-battery-v1"
        proposal = {"name": "Joint successor", "parent_version": 1, "system_prompt": "Diagnose the observed detector summary, then triage.",
                    "rationale": "Probe a controlled prompt change", "tools": [{"id": baseline["tool_ids"][0]}], "situation_detector": 1,
                    "knowledge_access": True,
                    "improvements": ["Retain measured window summaries before triage.", "Separate diagnosis hypothesis from grade decision.", "Keep existing tool logic fixed for this experiment."],
                    "design_audit": {"parent_training_run_id": baseline["training_runs"][-1]["id"],
                                     "observed_gaps": ["Minority grades are misclassified in development."],
                                     "changes": ["Change investigator prompt without changing evidence."],
                                     "expected_tradeoffs": ["Prompt changes may not overcome weak evidence."],
                                     "hypothesis": "Explicitly distinguishing observations from diagnosis will reduce unsupported grade choices.",
                                     "levers": {"detector_rulesets": "Retain query rulesets to isolate prompt effects.", "tools": "Retain tool logic for a controlled comparison.", "investigator_prompt": "Change prompt to separate diagnosis and triage."}}}
        with pytest.raises(ValueError, match="probe_id"):
            service.publish(caller, identifier, proposal)
        with pytest.raises(PermissionError):
            service.probe(caller, identifier, proposal, ["a" * 16, "d" * 16])
        invalid = deepcopy(proposal)
        invalid["design_audit"].pop("levers")
        with pytest.raises(ValueError, match="lever"):
            service.probe(caller, identifier, invalid, ["a" * 16, "b" * 16])
        process = service.dataset.detector_process
        service.dataset.detector_process = lambda *arguments: {
            "matched": True, "facts": ["Constant observation"], "technique_ids": [], "summary": {"constant": True}}
        failed = service.probe(caller, identifier, proposal, ["a" * 16, "b" * 16])
        assert failed["status"] == "failed" and not failed["detector_summary_varies"]
        with pytest.raises(ValueError, match="Probe failed"):
            service.publish(caller, identifier, {"probe_id": failed["id"]})
        service.dataset.detector_process = process
        receipt = service.probe(caller, identifier, proposal, ["a" * 16, "b" * 16])
        assert receipt["status"] == "passed" and receipt["detector_summary_varies"]
        assert "proposal" not in receipt
        discovery = service.capabilities(caller, identifier)
        service.record_process_task(caller, identifier, "Recorded task procedure", "session-fixture", capabilities=discovery)
        processes = list((service.directory(caller, identifier) / "process").glob("*.json"))
        assert len(processes) == 1
        assert json.loads(processes[0].read_text())["capabilities"] == discovery
        with pytest.raises(ValueError, match="proposal changed"):
            service.publish(caller, identifier, {**proposal, "system_prompt": "Different prompt", "probe_id": receipt["id"]})
        terminal = OptimizationTerminal.__new__(OptimizationTerminal)
        terminal.service = service
        terminal.bindings = {"workspace": (caller, identifier)}
        saved = terminal.operation("publish")("workspace", {"probe_id": receipt["id"]}, {})
        assert saved["probe_receipt"]["id"] == receipt["id"]
        assert saved["lever_changes"] == {"detector_rulesets": False, "tools": False, "investigator_prompt": True}
        service.measure(caller, identifier, 2, "training", wait=True)
        service.evaluate(caller, identifier, 2, wait=True)
        assert service.get(caller, identifier)["versions"][1]["evaluation_metrics"]["case_count"] == 1
        with pytest.raises(ValueError, match="per lever"):
            service.finish(caller, identifier)
        proposal["parent_version"] = 2
        proposal["design_audit"]["parent_training_run_id"] = service.get(caller, identifier)["versions"][1]["training_runs"][-1]["id"]
        proposal["tools"].append({"name": "category_inventory", "family": "category-calibration", "description": "Inventory observed categories.",
                                  "queries": "Distinct categories in this case window.", "returns": "A bounded category table.",
                                  "logic": "Deduplicate categories without predicting a grade.",
                                  "code": "def run(ctx):\n    return ctx.query(\"SELECT DISTINCT category FROM evidence\", max_rows=20)\n",
                                  "change_rationale": ["Answer the category-inventory question independently of the sample tool."]})
        plan = {"version": "question-evidence-tools-v1", "questions": [
            {"id": "sample", "question": "What does the recorded evidence contain?", "decision": "Check the scope before interpreting categories.",
             "data": "evidence", "view": "Bounded evidence sample", "tool": baseline["tool_ids"][0], "status": "tool", "limits": "A sample is not complete coverage."},
            {"id": "categories", "question": "Which distinct categories are observed?", "decision": "Distinguish diversity from duplicate rows.",
             "data": "evidence(category)", "view": "Category inventory", "tool": "category_inventory", "status": "tool", "limits": "Categories do not establish a grade."}],
            "code_changes": ["Add a separate category-inventory tool."], "agent_changes": ["Select both evidence views."],
            "held_fixed": ["Detector configuration, model and investigator prompt."], "acceptance_checks": ["Both selected tools execute on each probe case."]}
        proposal["design_audit"]["investigation_plan"] = plan
        receipt = service.probe(caller, identifier, proposal, ["a" * 16, "b" * 16])
        changed = deepcopy(proposal)
        changed["design_audit"]["investigation_plan"]["agent_changes"] = ["A different interpretation policy."]
        with pytest.raises(ValueError, match="proposal changed"):
            service.publish(caller, identifier, {**changed, "probe_id": receipt["id"]})
        saved = service.publish(caller, identifier, {"probe_id": receipt["id"]})
        assert len(saved["tool_ids"]) == 2
        assert saved["design_audit"]["investigation_plan"] == plan
        directory = service.directory(caller, identifier)
        assert json.loads((directory / "versions/3.json").read_text())["design_audit"]["investigation_plan"] == plan
        retained = json.loads((directory / "probes" / f"{receipt['id']}.json").read_text())
        assert all(len(result["transcript"]["evidence"]["tools"]) == 2 for result in retained["results"])
    finally:
        service.close()


def test_creative_campaign_requires_diverse_records_and_pins_installed_skill(tmp_path):
    import hashlib
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from importlib.resources import files
    import agent_optimization as agent_optimization
    from app.cybereye.backend.api.optimization import router
    from app.cybereye.backend.security import current_principal

    caller = Principal("local:creative-fixture", issuer="local-preview")
    dataset = JointDataset()
    dataset.full_cases = dataset.cases
    predict = Mock(return_value={"grade": "TruePositive", "rationale": "Observed", "diagnosis": "Hypothesis", "proposed_actions": [], "citations": []})
    service = OptimizationService(dataset, tmp_path, "fixture", predict, knowledge_search=lambda arguments: {"rows": []})
    application = FastAPI()
    application.include_router(router)
    application.state.optimization = service
    application.dependency_overrides[current_principal] = lambda: caller
    try:
        with TestClient(application) as client:
            assert client.get("/api/cyber/optimization").json()["creative_supported"] is True
            assert client.post("/api/cyber/optimization/experiments", json={"name": "Invalid", "creative": True}).status_code == 422
            response = client.post("/api/cyber/optimization/experiments", json={"name": "Creative fixture", "protocol": "joint-10", "creative": True})
            assert response.status_code == 200
        identifier = response.json()["id"]
        service.futures[identifier].result(timeout=5)
        service.futures[identifier].result(timeout=5)
        experiment = service.get(caller, identifier)
        baseline = experiment["versions"][0]
        assert experiment["limits"]["workers"] == 8
        assert experiment["exploration_contract"]["minimums"]["approaches"] == 5
        proposal = {"name": "Timeline and evidence", "parent_version": 1, "system_prompt": "Compare the event timeline with the evidence sample.",
                    "rationale": "Test two distinct evidence views", "situation_detector": 1, "knowledge_access": True,
                    "tools": [{"id": baseline["tool_ids"][0]},
                              {"name": "event_timeline", "family": "temporal", "description": "Inspect ordered observation times.",
                               "queries": "Evidence event times in the incident window.", "returns": "An ordered time table with a row cap.",
                               "logic": "Sort observed times without claiming causality.",
                               "code": "def run(ctx):\n    return ctx.query(\"SELECT event_time FROM evidence ORDER BY event_time LIMIT 20\", max_rows=20)\n",
                               "change_rationale": ["Answer the temporal-ordering question separately from the sample."]}],
                    "improvements": ["Expose ordered events separately from the sample.", "Compare evidence views before forming a hypothesis.", "Retain parent detector rules for this comparison."],
                    "design_audit": {"parent_training_run_id": baseline["training_runs"][-1]["id"],
                                     "hypothesis": "Temporal ordering adds distinguishing evidence beyond a small unordered sample.",
                                     "observed_gaps": ["The sample-only baseline misclassifies development cases."],
                                     "changes": ["Add an independently useful temporal view."],
                                     "expected_tradeoffs": ["Extra evidence may increase latency without improving the decision."],
                                     "levers": {"detector_rulesets": "Retain the parent detector configuration.", "tools": "Add a separate ordered observation tool.",
                                                "investigator_prompt": "Interpret temporal order alongside the evidence sample."}}}
        with pytest.raises(ValueError, match="investigation_plan"):
            service.probe(caller, identifier, proposal, ["a" * 16, "b" * 16])
        proposal["design_audit"]["investigation_plan"] = {
            "version": "question-evidence-tools-v1", "questions": [
                {"id": "sample", "question": "Which observations exist?", "decision": "Check evidence before interpretation.",
                 "data": "evidence", "view": "Evidence sample", "tool": baseline["tool_ids"][0], "status": "tool", "limits": "A sample is incomplete."},
                {"id": "timeline", "question": "In which order did observations occur?", "decision": "Distinguish sequences from repeated samples.",
                 "data": "evidence(event_time)", "view": "Ordered timeline", "tool": "event_timeline", "status": "tool", "limits": "Temporal order does not prove causality."}],
            "code_changes": ["Add bounded temporal retrieval."], "agent_changes": ["Compare the two selected views."],
            "held_fixed": ["Detector, model, cohorts and response contract."], "acceptance_checks": ["Inspect both tools on contrasting development cases."]}
        proposal["design_audit"]["experiment"] = {
            "approach_id": "temporal_evidence", "kind": "new-evidence", "mechanism": "Use event order to complement incomplete evidence samples.",
            "alternatives": ["Inspect evidence duplication and concentration first.", "Compare matched historical calibration without temporal evidence."],
            "disconfirmation": "The temporal view supplies no distinguishing evidence across contrasting development cases."}
        receipt = service.probe(caller, identifier, proposal, ["a" * 16, "b" * 16])
        assert receipt["status"] == "passed"
        saved = service.publish(caller, identifier, {"probe_id": receipt["id"]})
        assert saved["design_audit"]["experiment"] == proposal["design_audit"]["experiment"]
        assert service.feedback(caller, identifier)["exploration_coverage"]["measured_versions"] == 0
        service.measure(caller, identifier, 2, "training", wait=True)
        service.evaluate(caller, identifier, 2, wait=True)
        assert service.feedback(caller, identifier)["exploration_coverage"]["counts"]["multi_tool_versions"] == 1
        with pytest.raises(ValueError, match="Creative exploration incomplete"):
            service.finish(caller, identifier)
        skill = files(agent_optimization).joinpath("skills", "creative-agent-optimization", "SKILL.md").read_text()
        with pytest.raises(ValueError, match="skill receipt"):
            service.record_process_task(caller, identifier, "Fixture task", "fixture-session")
        service.record_process_task(caller, identifier, "Fixture task", "fixture-session", skill=skill)
        record = json.loads(next((service.directory(caller, identifier) / "process").glob("*.json")).read_text())
        assert record["skill"]["content"] == skill
        assert record["skill"]["digest"] == hashlib.sha256(skill.encode()).hexdigest() == experiment["exploration_contract"]["skill_digest"]
        service.creative_skill_digest = "changed"
        with pytest.raises(ValueError, match="skill changed"):
            service.probe(caller, identifier, proposal, ["a" * 16, "b" * 16])
    finally:
        service.close()