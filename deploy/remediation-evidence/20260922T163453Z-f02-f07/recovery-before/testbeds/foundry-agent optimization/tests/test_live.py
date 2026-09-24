import importlib.util
from pathlib import Path
import sys
import os
import unittest
from unittest.mock import patch
import tempfile

DEPLOY = Path(__file__).resolve().parents[1] / "deploy"
sys.path.insert(0, str(DEPLOY))
spec = importlib.util.spec_from_file_location("iris_live", DEPLOY / "live.py")
live = importlib.util.module_from_spec(spec)
spec.loader.exec_module(live)


class NativeEvaluatorTests(unittest.TestCase):
    def test_consumed_package_repairs_refuse_without_dispatch(self):
        with patch.object(live.subprocess, "run") as command:
            for action in (live.install_loader, live.restore_sdk):
                with self.assertRaisesRegex(RuntimeError, "retirement pending F06"):
                    action()
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