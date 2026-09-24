import importlib.util
from pathlib import Path
import sys
import os
import unittest
from unittest.mock import patch
import tempfile
import copy
import asyncio
from types import SimpleNamespace

DEPLOY = Path(__file__).resolve().parents[1] / "deploy"
sys.path.insert(0, str(DEPLOY))
spec = importlib.util.spec_from_file_location("iris_live", DEPLOY / "live.py")
live = importlib.util.module_from_spec(spec)
spec.loader.exec_module(live)


class NativeEvaluatorTests(unittest.TestCase):
    def test_log_stream_utf8_multiline_malformed_and_bounds(self):
        import campaign
        payload = b'data: {"message":\ndata: "Error \xc3\xa9"}\n\ndata: invalid\n\n'
        self.assertEqual(list(campaign.log_messages([payload[index:index + 1] for index in range(len(payload))])), ["Error \u00e9"])
        with self.assertRaises(ValueError):
            list(campaign.log_messages([payload], max_bytes=2))
        with self.assertRaises(ValueError):
            list(campaign.log_messages([payload], max_events=0))

    def test_bounded_resolver_preserves_bytes_and_refuses_fields(self):
        import campaign
        import json
        from unittest.mock import MagicMock
        project = MagicMock()
        response = project.send_request.return_value
        response.status_code = 200
        config = {"instructions": "  exact bytes\n", "model": "gpt-5.6-luna"}
        response.read.return_value = json.dumps(config).encode()
        self.assertEqual(campaign.resolve_candidate_config(project, live.TARGET["endpoint"], "job", "candidate"), config)
        for changed in (dict(config, skills_dir="/tmp"), dict(config, model="foreign"), dict(config, tools=[{}])):
            response.read.return_value = json.dumps(changed).encode()
            with self.assertRaises(ValueError):
                campaign.resolve_candidate_config(project, live.TARGET["endpoint"], "job", "candidate")
        with self.assertRaises(ValueError):
            campaign.resolve_candidate_config(project, live.TARGET["endpoint"], "job", "../escape")
        response.read.return_value = b"x" * 1000001
        with self.assertRaises(ValueError):
            campaign.resolve_candidate_config(project, live.TARGET["endpoint"], "job", "candidate")

    def test_loader_path_and_silent_field_refusal(self):
        sys.path.insert(0, str(DEPLOY.parent))
        from main import loaded_spec
        for fields in ({"OPTIMIZATION_CANDIDATE_ID": "../escape"},
                       {"OPTIMIZATION_CONFIG": '{"instructions":"test","skills_dir":"/tmp/skills"}'},
                       {"OPTIMIZATION_CONFIG": '[]'}):
            with patch.dict(os.environ, fields, clear=True), self.assertRaises(ValueError):
                loaded_spec(None)

    def test_public_loader_whitespace_gate(self):
        from azure.ai.agentserver.optimization import load_config
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            baseline = Path(directory) / "baseline"
            baseline.mkdir()
            (baseline / "metadata.yaml").write_text("model: gpt-5.6-luna\ninstruction_file: instructions.md\n")
            original = "  exact instruction bytes\n"
            (baseline / "instructions.md").write_text(original)
            loaded = load_config(config_dir=directory, credential=None)
            self.assertNotEqual(loaded.instructions, original)
            self.assertEqual(loaded.instructions, original.strip())

    def test_native_classifier_cancellation(self):
        sys.path.insert(0, str(DEPLOY.parent))
        import main
        from unittest.mock import AsyncMock
        from azure.ai.agentserver.responses import ResponsesAgentServerHost
        captured = []
        credential = AsyncMock()
        original = ResponsesAgentServerHost.response_handler
        def register(server, function):
            captured.append(function)
            return original(server, function)
        with patch.object(ResponsesAgentServerHost, "response_handler", register), \
               patch("azure.identity.aio.DefaultAzureCredential", return_value=credential), \
             patch.dict(os.environ, {"FOUNDRY_AGENT_NAME": "canary", "FOUNDRY_AGENT_VERSION": "1"}), \
             patch.object(Path, "exists", return_value=False):
            main.create_server("https://smoke.invalid/api/projects/smoke", {"sha256": "source", "files": {"app/configuration.yaml": "config"}},
                SimpleNamespace(instructions="canary", model="gpt-5.6-luna"), SimpleNamespace(source="test", candidate_id=None), configure_observability=None)
        async def exercise():
            signal, entered = asyncio.Event(), asyncio.Event()
            closed = []
            async def classify(*args):
                try:
                    entered.set()
                    await asyncio.Event().wait()
                    self.fail("dispatch after cancellation")
                finally:
                    closed.append(True)
            with patch("azure.identity.aio.DefaultAzureCredential", return_value=credential), patch.object(main, "classify", classify):
                task = asyncio.create_task(captured[0](None, SimpleNamespace(get_input_text=AsyncMock(return_value="canary")), signal))
                await asyncio.wait_for(entered.wait(), 2)
                signal.set()
                with self.assertRaises(asyncio.CancelledError):
                    await asyncio.wait_for(task, 2)
            self.assertEqual(closed, [True])
            credential.__aexit__.assert_awaited_once()
            self.assertEqual(len([task for task in asyncio.all_tasks() if task is not asyncio.current_task()]), 0)
        asyncio.run(exercise())

    def test_manifest_digest_and_historical_refusal(self):
        path = DEPLOY / "env/migration-o-v1.json"
        with self.assertRaises(ValueError):
            live.configure_run(path, "0" * 64, "optimize")
        with self.assertRaises(ValueError):
            live.configure_run(path, live.prepare.sha(path.read_bytes()), "final-holdout")

    def test_retired_entrypoint_refuses_before_python(self):
        import subprocess
        for action in ("install-loader", "restore-sdk", "optimizer-operation", "optimize-retry-rejected", "final-holdout", "observe-holdout"):
            result = subprocess.run(["bash", str(DEPLOY / "deploy.sh"), action], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 2)
            self.assertIn("Retired historical action", result.stderr)

    def test_native_candidate_identity_and_partial_refusal(self):
        import campaign
        candidates = [{"id": "candidate-" + str(index), "name": "name-" + str(index), "avg_score": 0.5,
                       "avg_tokens": 0, "eval_id": "eval-" + str(index), "eval_run_id": "run-" + str(index)} for index in range(3)]
        job = {"status": "completed", "result": {"candidates": candidates}}
        self.assertEqual(campaign.native_candidates(job, 3), candidates)
        for values in ([], candidates[:2], [candidates[0]] * 3):
            with self.assertRaises(ValueError):
                campaign.native_candidates({"status": "completed", "result": {"candidates": values}}, 3)
        for state in ("failed", "cancelled", "canceled", "in_progress"):
            with self.assertRaises(ValueError):
                campaign.native_candidates(dict(job, status=state), 3)
        changed = copy.deepcopy(job)
        changed["result"]["candidates"][0].pop("eval_run_id")
        with self.assertRaises(ValueError):
            campaign.native_candidates(changed, 3)

    def test_optimizer_reconciliation_never_creates(self):
        import campaign
        from unittest.mock import MagicMock
        project = MagicMock()
        project.beta.agents.get_optimization_job.return_value.as_dict.return_value = {"status": "failed"}
        with patch.object(campaign, "SERIES", "migration-test"), patch.object(live, "connect", return_value=(project, None)), patch.object(Path, "read_text", return_value='{"job_id":"existing"}'):
            self.assertTrue(campaign.optimizer_operation(live)["read_only_reconciliation"])
        project.beta.agents.begin_create_optimization_job.assert_not_called()
    def test_native_result_contract(self):
        import campaign
        evaluator = {"name": "exact-v3", "version": "1"}
        criterion = {"type": "azure_ai_evaluator", "name": "exact-v3", "evaluator_name": "exact-v3", "evaluator_version": "1"}
        row = {"id": "row", "eval_id": "eval", "run_id": "run", "status": "completed",
               "datasource_item": {"query": "query", "ground_truth": "Iris-setosa", "sample.output_text": "Iris-versicolor"},
               "results": [{"name": "exact-v3", "metric": "exact-v3", "type": "azure_ai_evaluator", "status": "completed", "score": 0, "passed": False}]}
        value = {"id": "eval", "run_id": "run", "status": "completed", "rows": [row],
                 "run": {"id": "run", "eval_id": "eval", "status": "completed"},
                 "result_counts": {"total": 1, "errored": 0, "skipped": 0},
                 "definition": {"id": "eval", "testing_criteria": [criterion]}}
        self.assertEqual(campaign.eval_metrics(value, {"query": "Iris-setosa"}, evaluator)["accuracy"], 0)
        for key, wrong in (("status", "failed"), ("run_id", "foreign"), ("id", None), ("error", {"code": "bad"})):
            changed = copy.deepcopy(value)
            changed["rows"][0][key] = wrong
            with self.assertRaises(ValueError):
                campaign.eval_metrics(changed, {"query": "Iris-setosa"}, evaluator)
        for key, wrong in (("score", True), ("score", float("nan")), ("score", float("inf")),
                           ("metric", "foreign"), ("name", "foreign"), ("status", "skipped")):
            changed = copy.deepcopy(value)
            changed["rows"][0]["results"][0][key] = wrong
            with self.assertRaises(ValueError):
                campaign.eval_metrics(changed, {"query": "Iris-setosa"}, evaluator)
        changed = copy.deepcopy(value)
        changed["definition"]["testing_criteria"][0]["evaluator_version"] = "2"
        with self.assertRaises(ValueError):
            campaign.eval_metrics(changed, {"query": "Iris-setosa"}, evaluator)
        for rows in ([], [row, row]):
            with self.assertRaises(ValueError):
                campaign.eval_metrics(dict(value, rows=rows), {"query": "Iris-setosa"}, evaluator)
        with self.assertRaises(ValueError):
            campaign.target_text(dict(row, sample={"output_text": "conflict"}))

    def test_native_pagination_and_duplicates(self):
        import campaign
        def model(identifier):
            return SimpleNamespace(model_dump=lambda **kwargs: {"id": identifier})
        pages = [SimpleNamespace(data=[model("first")], last_id="first"), SimpleNamespace(data=[model("second")], last_id="second")]
        client = SimpleNamespace(evals=SimpleNamespace(runs=SimpleNamespace(output_items=SimpleNamespace(
            list=lambda **kwargs: SimpleNamespace(iter_pages=lambda: iter(pages))))))
        events = []
        self.assertEqual(len(campaign.evaluation_rows(client, "eval", "run", 2, events)), 2)
        self.assertEqual(events[-1]["last_id"], "second")
        pages[1].data = [model("first")]
        with self.assertRaises(ValueError):
            campaign.evaluation_rows(client, "eval", "run", 2, [])

    def test_consumed_package_repairs_refuse_without_dispatch(self):
        with patch.object(live.subprocess, "run") as command:
            self.assertFalse(hasattr(live, "install_loader"))
            self.assertFalse(hasattr(live, "restore_sdk"))
            command.assert_not_called()

    def test_locked_image_dependencies(self):
        import json
        docker = (DEPLOY / "Dockerfile").read_text()
        self.assertEqual(docker.count("@sha256:"), 2)
        self.assertNotIn("RUN pip", docker)
        for text in ("--no-python-downloads", "--no-build-isolation", "--require-hashes", "--no-index", "uv pip freeze"):
            self.assertIn(text, docker)
        manifest = json.loads((DEPLOY / "dependency-manifest.json").read_text())
        self.assertEqual(manifest["runtime_lock_sha256"], live.prepare.sha((DEPLOY / "runtime-requirements.lock").read_bytes()))
        self.assertTrue(any(name.startswith("azure_ai_agentserver_optimization-") for name in manifest["wheels"]))

    def test_exact_canaries(self):
        namespace = {}
        exec(live.EXACT_CODE, namespace)
        for response, expected in ((" Iris-setosa ", 1), ("Iris-versicolor", 0), ("not-a-label", 0), (None, 0)):
            self.assertEqual(namespace["grade"]({"output_text": response}, {"ground_truth": "Iris-setosa"}), expected)
            self.assertEqual(namespace["grade"]({}, {"sample.output_text": response, "ground_truth": "Iris-setosa"}), expected)

    def test_sdk_roundtrip(self):
        from azure.ai.projects.models import EvaluatorVersion
        definition = live.evaluator_definition()
        self.assertEqual(EvaluatorVersion(definition).as_dict(), definition)

    def test_exact_shapes_and_mapping_errors(self):
        namespace = {}
        exec(live.EXACT_CODE, namespace)
        grade = namespace["grade"]
        for response, expected in ((" Iris-setosa ", 1), ("Iris-virginica", 0), ("invalid", 0), (None, 0), (12, 0)):
            for fields in ({"response": response}, {"sample.output_text": response},
                           {"sample": {"output_text": response}}):
                self.assertEqual(grade(None, dict(fields, ground_truth="Iris-setosa")), expected)
        self.assertEqual(grade(None, {"response": "Iris-setosa", "sample": {"output_text": "Iris-setosa"},
                                      "ground_truth": "Iris-setosa"}), 1)
        for item in ({}, {"response": "Iris-setosa"}, {"ground_truth": "Iris-setosa"},
                     {"response": "Iris-setosa", "ground_truth": None},
                     {"response": "Iris-setosa", "ground_truth": "foreign"},
                     {"response": "Iris-setosa", "ground_truth": "Iris-setosa", "sample": None},
                     {"response": "Iris-setosa", "ground_truth": "Iris-setosa", "sample": []},
                     {"response": "Iris-setosa", "ground_truth": "Iris-setosa", "sample.output_text": "Iris-virginica"}):
            with self.subTest(item=item), self.assertRaises(ValueError):
                grade(None, item)
        with self.assertRaises(ValueError):
            grade([], {"response": "Iris-setosa", "ground_truth": "Iris-setosa"})

    def test_directory_and_inline_skills_refused(self):
        sys.path.insert(0, str(DEPLOY.parent))
        from composition import apply_optimization, load_spec
        from azure.ai.agentserver.optimization import CandidateConfig, OptimizationConfig
        for kwargs in ({"skills_dir": "/tmp/skills"}, {"skills": [{"name": "foreign"}]},
                       {"instructions": None}, {"instructions": 42}):
            fields = dict(instructions="test")
            fields.update(kwargs)
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                constructor = OptimizationConfig if "skills_dir" in fields else CandidateConfig
                apply_optimization(load_spec(), constructor(**fields))
        for fields in ({"skills": {}}, {"tool_definitions": ""}, {"model": []}):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                apply_optimization(load_spec(), CandidateConfig(instructions="test", **fields))

    def test_native_loader_and_canonical_composition(self):
        sys.path.insert(0, str(DEPLOY.parent))
        from main import loaded_spec
        with patch.dict(os.environ, {"OPTIMIZATION_CONFIG": '{"instructions":"loader canary","model":"gpt-5.6-luna"}'}, clear=True):
            agent, config = loaded_spec(None)
        self.assertEqual(agent.instructions, "loader canary")
        self.assertEqual(config.source, "env:OPTIMIZATION_CONFIG")
        from composition import compose
        class Model:
            def agent(self, **kwargs):
                return kwargs
        self.assertEqual(compose(Model(), agent)["instructions"], "loader canary")

    def test_native_model_and_tools_refused(self):
        sys.path.insert(0, str(DEPLOY.parent))
        from composition import apply_optimization, load_spec
        from azure.ai.agentserver.optimization import OptimizationConfig
        for config in (OptimizationConfig(instructions="test", model="foreign"),
                       OptimizationConfig(instructions="test", tool_definitions=[{"name": "foreign"}]),
                       OptimizationConfig(instructions="test", temperature=1), None):
            with self.assertRaises(ValueError):
                apply_optimization(load_spec(), config)

    def test_selection_requires_complete_metrics(self):
        import campaign
        with self.assertRaises(ValueError):
            campaign.select_candidate([])
        with self.assertRaises(ValueError):
            campaign.select_candidate([{"candidate_id": "partial", "metrics": {"n": 29}}])

    def test_selection_frozen_order(self):
        import campaign
        metrics = {"n": 30, "macro_f1": 0.9, "accuracy": 0.9, "invalid_rate": 0}
        candidates = [{"candidate_id": name, "metrics": dict(metrics)} for name in ("candidate-b", "candidate-a")]
        self.assertEqual(campaign.select_candidate(candidates)["candidate_id"], "candidate-a")
        candidates[0]["metrics"]["macro_f1"] = 0.95
        self.assertEqual(campaign.select_candidate(candidates)["candidate_id"], "candidate-b")

    def test_demonstration_selection_excludes_better_baseline(self):
        import campaign
        metrics = {"n": 30, "macro_f1": 0.93, "accuracy": 28 / 30, "invalid_rate": 0}
        comparison = {"complete_independent_validation": True, "candidates": [
            {"candidate_id": name, "metrics": dict(metrics)} for name in ("baseline", "candidate-b", "candidate-a")]}
        comparison["candidates"][0]["metrics"]["macro_f1"] = 0.97
        self.assertEqual(campaign.demonstration_candidate(comparison, "baseline")["candidate_id"], "candidate-a")
        comparison["complete_independent_validation"] = False
        with self.assertRaises(ValueError):
            campaign.demonstration_candidate(comparison, "baseline")

    def test_build_context_excludes_evaluation_data(self):
        import hosting
        files, manifest = hosting.source_bytes()
        self.assertFalse(any("dataset/" in name or "private/" in name or "evaluator.py" in name for name in files))
        if "app/.agent_configs/selection.json" in files:
            import json
            selection = json.loads(files["app/.agent_configs/selection.json"])
            self.assertEqual(live.prepare.sha(files["app/.agent_configs/baseline/instructions.md"]), selection["instructions_sha256"])
        else:
            self.assertEqual(files["app/.agent_configs/baseline/instructions.md"], files["app/prompts/classifier.md"])
        self.assertTrue(manifest["libraries_archive_sha256"])

    def test_demonstration_overlay_exact_bytes_without_baseline_mutation(self):
        import hosting
        import campaign
        import json
        original = (DEPLOY.parent / ".agent_configs/selection.json").read_bytes()
        instructions = "native generated instructions\n"
        candidate = {"candidate_id": "native-generated", "instructions_sha256": live.prepare.sha(instructions.encode()),
                     "config": {"instructions": instructions}}
        with patch.object(campaign, "demonstration_context", return_value=({"native_config": {"sha256": "native-config"}}, candidate)):
            files, manifest = hosting.source_bytes(demonstration=True)
        self.assertEqual(files["app/.agent_configs/baseline/instructions.md"], instructions.encode())
        self.assertEqual(json.loads(files["app/.agent_configs/selection.json"])["candidate_id"], "native-generated")
        self.assertFalse(any("dataset/" in name or "private/" in name or "evaluator.py" in name for name in files))
        self.assertEqual(manifest["files"]["app/.agent_configs/baseline/instructions.md"], candidate["instructions_sha256"])
        self.assertEqual((DEPLOY.parent / ".agent_configs/selection.json").read_bytes(), original)

    def test_holdout_refuses_before_selection_without_reading_labels(self):
        import campaign
        with patch.object(Path, "read_text", side_effect=FileNotFoundError("selection unavailable")) as reader:
            with self.assertRaises(FileNotFoundError):
                campaign.final_holdout(live)
        self.assertEqual(reader.call_count, 1)

    def test_mutation_intent_cannot_be_reused(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(live.prepare, "EVIDENCE", Path(directory)):
                live.evaluator_retain("test-intent", {"request": "first"}, intent=True)
                with self.assertRaises(ValueError):
                    live.evaluator_retain("test-intent", {"request": "first"}, intent=True)

    def test_runtime_identity_refuses_wrong_version_or_prompt(self):
        import campaign
        deployed = {"agent": "iris", "version": "1", "build": {"source": {"sha256": "source",
                    "files": {"app/configuration.yaml": "config"}}}}
        response = {"status": "completed", "metadata": {"agent_name": "iris", "agent_version": "1",
                    "source_sha256": "source", "config_sha256": "config", "instructions_sha256": "prompt"}}
        campaign.verify_identity(response, deployed, "prompt")
        response["metadata"]["agent_version"] = "2"
        with self.assertRaises(ValueError):
            campaign.verify_identity(response, deployed, "prompt")
        response["metadata"]["agent_version"] = "1"
        with self.assertRaises(ValueError):
            campaign.verify_identity(response, deployed, "other-prompt")