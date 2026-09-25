"""Pipeline: run-spec schema refusals, authorization and resume gating, dataset contract, env-manifest mapping."""

import importlib
import inspect
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples/hosted_agent_e2e"))

from offline_fakes import ACCOUNT, PROJECT, SUBSCRIPTION, TENANT, FakeData, Rig  # noqa: E402
from foundry_ops import pipeline  # noqa: E402
from foundry_ops.core import RefusedError, sha256_hex  # noqa: E402


class SpecTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.rig = Rig(self.directory.name)

    def load(self, value, name="spec.json", text=None):
        path = self.rig.root / name
        path.write_text(text if text is not None else json.dumps(value))
        return pipeline.load_run_spec(path, expected_sha256=sha256_hex(path.read_bytes()), repo=self.rig.root,
                                      available=False)

    def refused(self, code, value=None, **options):
        with self.assertRaises(RefusedError) as refused:
            self.load(value, **options)
        self.assertEqual(refused.exception.code, code)
        return refused.exception

    def test_valid_spec_fields(self):
        spec = self.load(self.rig.spec_value())
        self.assertEqual((spec.series, spec.agent, spec.data, spec.bounds["max_candidates"]), ("demo-v1", "demo-agent",
                                                                                              "inline", 4))
        self.assertEqual(spec.targets["subscription_id"], SUBSCRIPTION)
        self.assertEqual(set(spec.inputs), {"journeys", "criteria", "items", "train", "validation", "evaluator",
                                            "optimization", "selection_rule"})
        self.assertIn("promote", spec.authorization)
        self.assertEqual(spec.package, self.rig.root / "agentcraft_projects/demo/agent")

    def test_schema_refusals(self):
        base = self.rig.spec_value()
        secret = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.signature"
        cases = [({**base, "extra": 1}, "spec_field"),
                 ({**base, "agent": {**base["agent"], "grant_roles": True}}, "spec_field"),
                 ({**base, "models": {**base["models"], "runtime": secret}}, "spec_secret"),
                 ({**base, "targets": {**base["targets"], "acr_login_server": "other.azurecr.io"}}, "spec_registry"),
                 ({**base, "targets": {**base["targets"], "tenant_id": "not-a-guid"}}, "spec_target_format"),
                 ({**base, "authorization": {"cloud_write": ["build", "grant"]}}, "spec_authorization"),
                 ({**base, "bounds": {"max_candidates": 99}}, "spec_bounds"),
                 ({**base, "inputs": {**base["inputs"], "journeys": {"dataset": {"name": "j", "version": "1",
                                                                              "sha256": "0" * 64}}}}, "spec_input"),
                 ({**base, "inputs": {**base["inputs"], "items": {"dataset": {"name": "i", "version": "1",
                                                                           "sha256": "0" * 64}}}}, "spec_data"),
                 ({**base, "inputs": {**base["inputs"], "items": {"path": "../x.jsonl", "sha256": "0" * 64}}},
                  "spec_input"),
                 ({**base, "inputs": {**base["inputs"], "evaluator": base["evaluator"]}}, "spec_input"),
                 ({**base, "records": "/abs"}, "spec_records"),
                 ({**base, "kind": "other"}, "spec_schema"),
                 ({key: value for key, value in base.items() if key != "authorization"}, "spec_missing")]
        for value, code in cases:
            with self.subTest(code=code):
                error = self.refused(code, value)
                self.assertNotIn(secret, str(error))
        self.refused("spec_duplicate", text='{"schema_version": 1, "schema_version": 1}')
        with self.assertRaises(RefusedError) as refused:
            path = self.rig.root / "spec.json"
            pipeline.load_run_spec(path, expected_sha256="0" * 64, repo=self.rig.root)
        self.assertEqual(refused.exception.code, "spec_digest")
        outside = tempfile.NamedTemporaryFile(suffix=".json")
        self.addCleanup(outside.close)
        with self.assertRaises(RefusedError) as refused:
            pipeline.load_run_spec(outside.name, expected_sha256="0" * 64, repo=self.rig.root)
        self.assertEqual(refused.exception.code, "spec_path")

    def test_data_mode_default_follows_availability(self):
        value = {key: item for key, item in self.rig.spec_value().items() if key != "data"}
        self.assertEqual(pipeline.spec_from_value(value, repo=self.rig.root, available=True).data, "dataset")
        self.assertEqual(pipeline.spec_from_value(value, repo=self.rig.root, available=False).data, "inline")

    def test_yaml_form_equals_json_and_refuses_aliases_and_duplicates(self):
        try:
            import yaml
        except ImportError:
            self.skipTest("PyYAML not installed")
        value = self.rig.spec_value()
        spec = self.load(None, name="spec.yaml", text=yaml.safe_dump(value))
        self.assertEqual(spec.inputs, self.load(value).inputs)
        self.refused("spec_alias", name="a.yaml", text="a: &x 1\nb: *x\n")
        self.refused("spec_duplicate", name="d.yaml", text="a: 1\na: 2\n")


class RunGateTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.rig = Rig(self.directory.name)

    def test_unauthorized_stage_refused_before_any_side_effect(self):
        spec, ledger = self.rig.spec(authorization={"cloud_write": ["build", "deploy"]})
        with self.assertRaises(RefusedError) as refused:
            pipeline.run(spec, self.rig.clients, ledger)
        self.assertEqual(refused.exception.code, "stage_unauthorized")
        self.assertIn("invoke", str(refused.exception))
        self.assertEqual((self.rig.az.calls, ledger.list()), ([], ["run-spec.json"]))
        with self.assertRaises(RefusedError) as refused:
            pipeline.optimize(spec, self.rig.clients, ledger)
        self.assertEqual(refused.exception.code, "stage_unauthorized")
        self.assertEqual(pipeline.run(spec, self.rig.clients, ledger, until="deploy")["status"], "complete")

    def test_window_and_input_refusals(self):
        spec, ledger = self.rig.spec(inputs={})
        for options, code in (({"until": "nope"}, "stage_unknown"), ({"until": "build", "from_": "deploy"}, "stage_window"),
                              ({"until": "invoke"}, "inputs_missing")):
            with self.subTest(code=code), self.assertRaises(RefusedError) as refused:
                pipeline.run(spec, self.rig.clients, ledger, **options)
            self.assertEqual(refused.exception.code, code)
        self.assertEqual(self.rig.az.calls, [])

    def test_blocked_stage_is_recorded_and_rerun_resumes(self):
        spec, ledger = self.rig.spec()
        self.rig.az.account = {"subscriptionId": "00000000-0000-0000-0000-000000000000", "tenantId": TENANT}
        blocked = pipeline.run(spec, self.rig.clients, ledger, until="build")
        self.assertEqual((blocked["status"], blocked["stopped_at"], blocked["code"]),
                         ("blocked", "preflight", "account_mismatch"))
        self.assertEqual(len(ledger.list("pipeline-01-preflight-blocked-*.json")), 1)
        self.rig.az.account = {"subscriptionId": SUBSCRIPTION, "tenantId": TENANT}
        self.assertEqual(pipeline.run(spec, self.rig.clients, ledger, until="build")["status"], "complete")

    def test_model_mismatch_refused(self):
        optimization = self.rig.project_dir / "inputs/optimization.json"
        optimization.write_text(json.dumps({"evaluators": [{"name": "demo-exact", "version": "1"}],
                                            "max_candidates": 2, "optimization_model": "other-model"}))
        spec, ledger = self.rig.spec()
        result = pipeline.run(spec, self.rig.clients, ledger, until="optimize")
        self.assertEqual((result["stopped_at"], result["code"]), ("optimize", "model_mismatch"))
        self.assertEqual(self.rig.project.beta.agents.jobs, [])


class DatasetContractTests(unittest.TestCase):
    """`data: dataset` uses exactly the foundry_ops.data contract names; fakes stand in until the module lands."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.rig = Rig(self.directory.name)
        self.real = importlib.import_module("foundry_ops.data")
        self.data = FakeData(self.rig.evals)
        patcher = patch.dict(sys.modules, {"foundry_ops.data": self.data})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_calls_bind_to_the_real_data_module_signatures(self):
        real = self.real
        self.assertIsNot(real, self.data)
        inspect.signature(real.register_jsonl_dataset).bind(object(), object(), name="n", rows=[{"query": "q"}])
        inspect.signature(real.readback_dataset).bind(object(), name="n", version="v", expected_sha256="0" * 64)
        self.assertTrue(pipeline.data_available())

    def test_pinned_rows_registered_and_used_as_dataset_sources(self):
        spec, ledger = self.rig.spec(data="dataset")
        result = pipeline.run(spec, self.rig.clients, ledger)
        self.assertEqual(result["status"], "complete", result)
        self.assertEqual(sorted({name for name, _ in self.data.registered}),
                         ["demo-agent-items", "demo-agent-train", "demo-agent-validation"])
        sources = [request["data_source"]["source"] for request in self.rig.evals.runs.requests
                   if request["data_source"]["type"] == "azure_ai_target_completions"]
        self.assertEqual({source["type"] for source in sources}, {"file_id"})
        self.assertTrue(all(source["id"].startswith("azureai://") and "demo-agent-items" in source["id"]
                            for source in sources))
        job = self.rig.project.beta.agents.jobs[0]["inputs"]
        self.assertEqual((job["train_dataset"]["type"], job["validation_dataset"]["name"]),
                         ("reference", "demo-agent-validation"))
        self.assertTrue(ledger.list("optimize-*-ds-candidates.json"))
        evaluated = ledger.read(pipeline.stage_record("evaluate"))["result"]
        self.assertEqual(evaluated["summary"]["exact"]["passed"], 1)

    def test_spec_dataset_ref_read_back_by_sha256(self):
        identifier = f"azureai://accounts/{ACCOUNT}/projects/{PROJECT}/data/demo-items/versions/3"
        self.rig.evals.datasets[identifier] = [{"query": "q1", "ok": True}, {"query": "q2", "ok": True}]
        criteria = self.rig.project_dir / "inputs/criteria-schema.json"
        criteria.write_text(json.dumps({"testing_criteria": [{"type": "x", "name": "exact"}],
                                        "item_schema": {"type": "object"}}))
        value = self.rig.spec_value(data="dataset")
        value["inputs"]["items"] = {"dataset": {"name": "demo-items", "version": "3", "sha256": "c" * 64, "rows": 2}}
        value["inputs"]["criteria"] = {"path": criteria.relative_to(self.rig.root).as_posix(),
                                       "sha256": sha256_hex(criteria.read_bytes())}
        path = self.rig.root / "ds.json"
        path.write_text(json.dumps(value))
        spec = pipeline.load_run_spec(path, expected_sha256=sha256_hex(path.read_bytes()), repo=self.rig.root)
        ledger = pipeline.open_ledger(spec)
        pipeline.run(spec, self.rig.clients, ledger, until="deploy")
        result = pipeline.evaluate(spec, self.rig.clients, ledger)
        self.assertEqual(self.data.readbacks, [("demo-items", "3", "c" * 64)])
        self.assertEqual(self.data.registered, [])
        self.assertEqual(self.rig.evals.runs.requests[-1]["data_source"]["source"], {"type": "file_id", "id": identifier})
        self.assertEqual(result["summary"]["exact"]["passed"], 2)

    def test_dataset_mode_without_module_refuses(self):
        spec, ledger = self.rig.spec(data="dataset")
        pipeline.run(spec, self.rig.clients, ledger, until="deploy")
        with patch.dict(sys.modules, {"foundry_ops.data": None}), self.assertRaises(RefusedError) as refused:
            pipeline.evaluate(spec, self.rig.clients, ledger)
        self.assertEqual(refused.exception.code, "data_unavailable")


class EnvManifestTests(unittest.TestCase):
    def test_manifest_actions_become_authorization(self):
        from offline_fakes import ENDPOINT, LOGIN, MODEL, REPOSITORY
        env = {"AZURE_TENANT_ID": TENANT, "AZURE_SUBSCRIPTION_ID": SUBSCRIPTION,
               "FOUNDRY_PROJECT_RESOURCE_ID": f"/subscriptions/{SUBSCRIPTION}/resourceGroups/rg/providers/"
                                              "Microsoft.CognitiveServices/accounts/fake-account/projects/p",
               "FOUNDRY_PROJECT_ENDPOINT": ENDPOINT, "ACR_NAME": "fakeregistry", "ACR_LOGIN_SERVER": LOGIN,
               "IMAGE_REPOSITORY": REPOSITORY, "MODEL_ACCOUNT": "fake-account", "MODEL_RESOURCE_GROUP": "rg",
               "MODEL_DEPLOYMENT": MODEL}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "env").mkdir()
            (root / "env/dev.env").write_text("".join(f"{key}={value}\n" for key, value in env.items()))
            manifest = {"schema_version": 1, "purpose": "foundry-hosted-agent", "series": "dev-v1", "agent": "a-agent",
                        "actions": ["preflight", "register-evaluator", "select"],
                        "env_sha256": sha256_hex((root / "env/dev.env").read_bytes()), "previous_version": None,
                        "previous_image": None, "inputs": {"items": ["a" * 64, "b" * 64]}}
            (root / "env/dev.run.json").write_text(json.dumps(manifest))
            spec, run, ledger = pipeline.load_env_manifest(
                "dev", sha256_hex((root / "env/dev.run.json").read_bytes()), "preflight", env_dir=root / "env",
                records=root / "records", repo=root)
        self.assertEqual(spec.authorization, frozenset({"register_evaluator"}))
        self.assertEqual((spec.models["runtime"], spec.data, spec.origin), (MODEL, "inline", "manifest"))
        self.assertEqual([ref.sha256 for ref in spec.inputs["items"]], ["a" * 64, "b" * 64])
        self.assertEqual(run.series, ledger.directory.name)


if __name__ == "__main__":
    unittest.main()
