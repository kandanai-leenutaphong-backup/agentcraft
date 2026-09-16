import json
import tempfile
import time
from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.cybereye.backend.api.optimization import router
from app.cybereye.backend.optimization.cli import OptimizationTerminal
from app.cybereye.backend.optimization.evaluation import model_predictor
from app.cybereye.backend.optimization.service import OptimizationService, compare_evaluation, digest
from app.cybereye.backend.security import Principal, current_principal


class FixtureDataset:
    profile_digest = "fixture-profile-digest"

    def describe(self):
        return {"dataset_id": "fixture"}

    def cases(self):
        return [{"case_id": character * 16, "expected": grade, "split": split,
                 "start_time": "2024-01-01", "end_time": "2024-01-02"}
                for character, grade, split in (("a", "TruePositive", "development"),
                    ("b", "BenignPositive", "validation"), ("c", "FalsePositive", "validation"))]

    def query(self, case_id, sql):
        if "labels" in sql or "DELETE" in sql:
            raise ValueError("Forbidden query")
        return {"columns": ["detector_id"], "rows": [["7"]], "truncated": False}

    def profiles(self):
        return {"columns": [], "rows": []}

    def run_tool(self, case_id, tool, scope=None):
        return self.query(case_id, tool.get("code", tool.get("sql", "")))


class OptimizationServiceTests(TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.caller = Principal("local:fixture", issuer="local-preview")
        self.predict = Mock(return_value={"grade": "TruePositive", "rationale": "fixture"})
        self.service = OptimizationService(FixtureDataset(), self.root / "experiments", "fixture-model", self.predict)
        self.addCleanup(self.service.close)
        self.experiment = self.service.create(self.caller, "Fixture experiment")
        self.identifier = self.experiment["id"]
        self.service.futures[self.identifier].result(timeout=5)
        self.directory = self.service.directory(self.caller, self.identifier)

    def proposal(self, **changes):
        return {"name": "Specialized", "parent_version": 1, "system_prompt": "Refined prompt",
                "rationale": "Test a bounded aggregation", "tools": [{"name": "aggregate", "code": "def run(ctx):\n    return ctx.query('SELECT count(*) FROM evidence')",
                    "queries": "Incident evidence", "returns": "Evidence count", "logic": "Count all evidence rows"}], **changes}

    def test_immutable_configs_and_all_evaluations_survive_restart(self):
        before = (self.directory / "versions/1.json").read_bytes()
        version = self.service.publish(self.caller, self.identifier, self.proposal())
        for _ in range(2):
            self.service.evaluate(self.caller, self.identifier, version["version"], wait=True)
        stored = self.service.get(self.caller, self.identifier)
        self.assertEqual(len(stored["versions"][1]["evaluations"]), 2)
        self.assertEqual(len(list((self.directory / "evaluations").glob("*.json"))), 3)
        self.assertEqual((self.directory / "versions/1.json").read_bytes(), before)
        evaluation = stored["versions"][1]["evaluations"][-1]
        self.assertEqual(evaluation["agent_version"], 2)
        self.assertEqual(evaluation["tool_ids"], version["tool_ids"])
        self.assertEqual(evaluation["config_digest"], digest(json.loads((self.directory / "versions/2.json").read_text())))
        self.assertEqual(evaluation["dataset_id"], "fixture")
        self.assertEqual(evaluation["comparison"]["reference_version"], 1)
        self.assertEqual(evaluation["comparison"]["verdict"], "quality-unchanged")
        self.assertEqual(evaluation["comparison"]["validation_macro_f1_delta"], 0)
        self.service.finish(self.caller, self.identifier)
        self.service.close()
        reopened = OptimizationService(FixtureDataset(), self.root / "experiments", "fixture-model", self.predict)
        self.addCleanup(reopened.close)
        self.assertEqual(reopened.get(self.caller, self.identifier)["versions"], stored["versions"])
        self.assertEqual(len(reopened.catalogue_agents(self.caller)), 2)
        self.assertEqual(reopened.catalogue_agents(self.caller)[1]["tools"][0]["source"]["code"], self.proposal()["tools"][0]["code"])
        self.assertTrue((self.directory / "tools" / f"{version['tool_ids'][0]}.py").exists())
        self.assertIn("confusion_matrix", reopened.get(self.caller, self.identifier)["versions"][1]["validation_metrics"])

    def test_other_owners_and_non_local_callers_cannot_read(self):
        other = Principal("local:other", issuer="local-preview")
        self.assertEqual(self.service.snapshot(other)["experiments"], [])
        with self.assertRaises(KeyError):
            self.service.get(other, self.identifier)
        for caller in (Principal("remote", issuer="entra"), Principal("app", kind="service", issuer="local-preview")):
            with self.subTest(caller=caller), self.assertRaises(PermissionError):
                self.service.snapshot(caller)

    def test_reusing_a_pinned_tool_preserves_its_source_and_history(self):
        first = self.service.get(self.caller, self.identifier)["versions"][0]
        tool_id = first["tool_ids"][0]
        tool_file = self.directory / "tools" / f"{tool_id}.json"
        before = tool_file.read_bytes()
        candidate = self.service.publish(self.caller, self.identifier, self.proposal(tools=[{"id": tool_id}]))
        self.assertEqual(candidate["tool_ids"], [tool_id])
        self.assertEqual(tool_file.read_bytes(), before)
        self.assertEqual(len(list((self.directory / "tools").glob("*.json"))), 1)
        with self.assertRaises(ValueError):
            self.service.publish(self.caller, self.identifier, self.proposal(tools=[{"id": "../../labels"}]))

    def test_optimizer_feedback_has_validation_summaries_but_no_validation_cases(self):
        feedback = self.service.feedback(self.caller, self.identifier)
        self.assertIn("validation", feedback["audit"])
        self.assertEqual(feedback["validation_metrics"], feedback["audit"]["validation"]["metrics"])
        self.assertLess(list(feedback).index("operator_guidance"), list(feedback).index("audit"))
        self.assertNotIn("cases", feedback["audit"]["validation"])
        self.assertTrue(all(case["split"] == "development" for case in feedback["development_failures"]))
        self.assertNotIn("b" * 16, json.dumps(feedback))
        self.assertNotIn("c" * 16, json.dumps(feedback))

    def test_guidance_is_owned_retained_and_does_not_rewrite_a_candidate(self):
        before = (self.directory / "versions/1.json").read_bytes()
        note = self.service.intervene(self.caller, self.identifier, "Inspect whether class scores change when the observed detector changes.")
        self.assertEqual(self.service.feedback(self.caller, self.identifier)["operator_guidance"], [note])
        self.assertEqual((self.directory / "versions/1.json").read_bytes(), before)
        self.assertTrue((self.directory / "interventions" / f"{note['id']}.json").exists())
        with self.assertRaises(KeyError):
            self.service.intervene(Principal("other", issuer="local-preview"), self.identifier, note["guidance"])
        self.service.finish(self.caller, self.identifier)
        with self.assertRaises(ValueError):
            self.service.intervene(self.caller, self.identifier, note["guidance"])

    def test_comparison_uses_validation_latency_not_development_latency(self):
        parent = {"version": 1, "evaluations": [{"id": "parent", "completed_at": "2026-09-10T01:00:00Z", "metrics": {"median_ms": 999}, "cases": [
            {"split": "validation", "expected": "TruePositive", "predicted": "TruePositive", "correct": True, "elapsed_ms": 10},
            {"split": "development", "expected": "FalsePositive", "predicted": "FalsePositive", "correct": True, "elapsed_ms": 2000}]}]}
        child = {"parent_version": 1}
        evaluation = {"started_at": "2026-09-10T02:00:00Z", "metrics": {"median_ms": 1}, "cases": [
            {"split": "validation", "expected": "TruePositive", "predicted": "TruePositive", "correct": True, "elapsed_ms": 30}]}
        comparison = compare_evaluation({"versions": [parent]}, child, evaluation)
        self.assertEqual(comparison["median_ms_delta"], 20)
        self.assertIn("validation median +20 ms", comparison["reason"])

    def test_cancel_is_terminal_and_pending_candidate_has_no_fake_score(self):
        self.service.publish(self.caller, self.identifier, self.proposal())
        record = self.service.cancel(self.caller, self.identifier)
        self.assertEqual(record["versions"][1]["status"], "cancelled")
        self.assertIsNone(record["versions"][1]["metrics"])
        for operation in (lambda: self.service.finish(self.caller, self.identifier),
                          lambda: self.service.evaluate(self.caller, self.identifier, 2),
                          lambda: self.service.publish(self.caller, self.identifier, self.proposal())):
            with self.assertRaises(ValueError):
                operation()
        self.assertEqual(self.service.get(self.caller, self.identifier)["status"], "cancelled")

    def test_missing_python_isolation_leaves_no_empty_experiment(self):
        before = list(self.service.root.glob("*/*/experiment.json"))
        with patch.object(self.service.dataset, "run_tool", side_effect=ValueError("Python isolation unavailable")):
            with self.assertRaisesRegex(ValueError, "isolation unavailable"):
                self.service.create(self.caller, "Cannot run here")
        self.assertEqual(list(self.service.root.glob("*/*/experiment.json")), before)
        self.assertEqual(len(self.service.snapshot(self.caller)["experiments"]), 1)

    def test_completed_experiment_and_version_budget_cannot_be_overwritten(self):
        for number in range(2, 6):
            self.service.publish(self.caller, self.identifier, self.proposal(name=f"v{number}"))
            self.service.evaluate(self.caller, self.identifier, number, wait=True)
        with self.assertRaisesRegex(ValueError, "budget"):
            self.service.publish(self.caller, self.identifier, self.proposal())
        self.service.finish(self.caller, self.identifier)
        self.assertEqual(self.service.cancel(self.caller, self.identifier)["status"], "completed")

    def test_bad_proposals_are_retained_without_request_credentials(self):
        for tools in (None, ["bad"], [{"name": "blocked", "sql": "SELECT * FROM labels", "task_key": "nested-test-secret"}]):
            with self.subTest(tools=tools), self.assertRaises(ValueError):
                self.service.publish(self.caller, self.identifier, self.proposal(tools=tools, task_key="test-task-secret", key="test-control-secret"))
        rejections = list((self.directory / "rejections").glob("*.json"))
        self.assertEqual(len(rejections), 3)
        self.assertEqual(len(self.service.get(self.caller, self.identifier)["rejections"]), 3)
        serialized = "".join(path.read_text() for path in rejections)
        for secret in ("test-task-secret", "test-control-secret", "nested-test-secret"):
            self.assertNotIn(secret, serialized)

    def test_json_mode_requirement_is_in_the_actual_input_message(self):
        from app.cybereye.backend.optimization.profile import model_request
        request = model_request("generic", {"tools": []}, "fixture-model")
        self.assertIn("JSON", request["message"])
        self.assertEqual(request["contract"], "llm_interface.agent/v1")
        self.assertEqual(request["options"]["response_format"], {"type": "json_object"})

    def test_contract_drift_preserves_history_but_refuses_new_measurements(self):
        self.service.model = "different-model"
        self.assertEqual(self.service.get(self.caller, self.identifier)["versions"][0]["model"], "fixture-model")
        for operation in (lambda: self.service.publish(self.caller, self.identifier, self.proposal()),
                          lambda: self.service.evaluate(self.caller, self.identifier, 1)):
            with self.assertRaisesRegex(ValueError, "create a new experiment"):
                operation()
        self.service.model = "fixture-model"
        self.service.case_digest = "different-cases"
        with self.assertRaisesRegex(ValueError, "create a new experiment"):
            self.service.evaluate(self.caller, self.identifier, 1)

    def test_api_checks_body_and_caller_before_exposing_records(self):
        app = FastAPI()
        app.include_router(router)
        app.state.optimization = self.service
        app.dependency_overrides[current_principal] = lambda: self.caller
        client = TestClient(app)
        self.assertEqual(client.get("/api/cyber/optimization").status_code, 200)
        path = f"/api/cyber/optimization/experiments/{self.identifier}/capabilities"
        self.assertEqual(client.get(path).status_code, 200)
        for body in ([], None, {"name": 3}, {"name": ""}):
            with self.subTest(body=body):
                self.assertEqual(client.post("/api/cyber/optimization/experiments", json=body).status_code, 422)
        app.dependency_overrides[current_principal] = lambda: Principal("app", kind="service", issuer="local-preview")
        self.assertEqual(client.get("/api/cyber/optimization").status_code, 404)
        self.assertEqual(client.get(path).status_code, 404)
        app.dependency_overrides.clear()
        self.assertEqual(client.get("/api/cyber/optimization").status_code, 401)
        self.assertEqual(client.get(path).status_code, 401)

    def test_terminal_task_key_cannot_control_session_or_query_validation(self):
        catalogue = {"version": 1, "sources": [{"id": "reference-graph", "access": "not_exposed", "reason": "No case identity join."}],
                     "tools": [{"name": "reference_lookup", "access": "not_exposed"}], "limitations": ["Discovery grants no access."]}
        self.service.capability_catalogue = Mock(return_value=catalogue)
        with patch("copilot_terminal.service.PtySession") as process:
            process.side_effect = lambda arguments, workspace, environment, **options: Mock(workspace=workspace)
            terminal = OptimizationTerminal(self.service, cli="fixture-cli", endpoint="https://model.example/openai/v1/", model="fixture-model",
                workspace_root=self.root / "workspaces", token_provider=lambda: ("test-provider-secret", time.time() + 3600),
                path="/usr/bin:/bin", api_origin="http://127.0.0.1:9000")
            self.addCleanup(terminal.close)
            headers = {"host": "127.0.0.1:9000", "origin": "http://127.0.0.1:9000", "content-type": "application/json", "x-copilot-terminal": "1"}
            self.assertEqual(terminal.handle(self.caller, "start", {**headers, "origin": "https://foreign.example"}, {})[0], 403)
            status, started = terminal.handle(self.caller, "start", headers, {})
            self.assertEqual(status, 201)
            session_id = started["session_id"]
            session = terminal.terminal._sessions[session_id]
            creative_skill = session.terminal.workspace / ".github/skills/creative-agent-optimization/SKILL.md"
            self.assertEqual(creative_skill.read_text(), terminal.creative_skill)
            self.assertIn("name: creative-agent-optimization", creative_skill.read_text())
            self.assertIn("## Diversify, Then Refine", creative_skill.read_text())
            control = {"session_id": session_id, "key": started["key"]}
            task = {"session_id": session_id, "task_key": session.task_key}
            self.assertNotIn("test-provider-secret", json.dumps(started))
            arguments = process.call_args.args[0]
            self.assertFalse(any(argument.startswith("--allow-all") for argument in arguments))
            self.assertEqual(sum(argument.startswith("--allow-tool=shell(") for argument in arguments), 3)
            self.assertEqual(terminal.handle(self.caller, "prepare", headers, {**control, "experiment_id": self.identifier})[0], 200)
            status, discovery = terminal.handle(self.caller, "capabilities", headers, task)
            self.assertEqual(status, 200)
            self.assertEqual(discovery["sources"], catalogue["sources"])
            self.assertEqual(discovery["digest"], digest(catalogue))
            self.assertEqual(json.loads((session.terminal.workspace / "CAPABILITIES.json").read_text()), discovery)
            self.assertIn("./opt capabilities", (session.terminal.workspace / "TASK.md").read_text())
            self.assertEqual(terminal.handle(self.caller, "describe", headers, task)[1]["capabilities"], discovery)
            for action in ("input", "resize", "stop", "prepare"):
                with self.subTest(action=action):
                    self.assertEqual(terminal.handle(self.caller, action, headers, task)[0], 404)
            other = Principal("local:other", issuer="local-preview")
            self.assertEqual(terminal.handle(other, "feedback", headers, control)[0], 404)
            self.assertEqual(terminal.handle(other, "capabilities", headers, task)[0], 404)
            self.assertEqual(terminal.handle(self.caller, "query", headers, {**task, "case_id": "a"*16, "sql": "SELECT * FROM evidence"})[0], 200)
            self.assertEqual(terminal.handle(self.caller, "query", headers, {**task, "case_id": "reference-graph", "sql": "SELECT * FROM evidence"})[0], 404)
            self.assertEqual(terminal.handle(self.caller, "query", headers, {**task, "case_id": "b"*16, "sql": "SELECT * FROM evidence"})[0], 404)
            self.assertEqual(terminal.handle(self.caller, "publish", headers, {**task, **self.proposal(tools=None)})[0], 400)
            self.assertTrue(all(session.task_key not in path.read_text() for path in (self.directory / "rejections").glob("*.json")))
            def output_and_cancel(*args, **kwargs):
                terminal.cancel_experiment(self.identifier)
                return {"output": "", "cursor": 0}
            session.terminal.output.side_effect = output_and_cancel
            self.assertEqual(terminal.handle(self.caller, "output", headers, control)[0], 404)
            session.terminal.close.assert_called_once()
            self.assertEqual(terminal.handle(self.caller, "feedback", headers, task)[0], 404)

    def test_capability_discovery_is_owned_bounded_and_has_an_explicit_unconfigured_state(self):
        self.assertIn("not supplied", self.service.capabilities(self.caller, self.identifier)["limitations"][0])
        callback = Mock(return_value={"version": 1, "sources": [], "tools": [], "limitations": []})
        self.service.capability_catalogue = callback
        with self.assertRaises(KeyError):
            self.service.capabilities(Principal("local:other", issuer="local-preview"), self.identifier)
        callback.assert_not_called()
        callback.return_value["limitations"] = ["x" * 131073]
        with self.assertRaisesRegex(ValueError, "128 KiB"):
            self.service.capabilities(self.caller, self.identifier)