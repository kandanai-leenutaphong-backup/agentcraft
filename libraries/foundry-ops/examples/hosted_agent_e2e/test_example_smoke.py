"""Offline smoke: the example run spec drives the full `pipeline.run` sequence end to end against fakes.

Run: python3 -B -m unittest discover -s libraries/foundry-ops/examples/hosted_agent_e2e
"""

import json
import tempfile
import unittest

from offline_fakes import MODEL, OPTIMIZER, JUDGE, Rig
from foundry_ops import pipeline
from foundry_ops.core import RefusedError, sha256_hex


class ExampleSmokeTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.rig = Rig(self.directory.name)

    def test_example_spec_is_placeholder_only(self):
        from offline_fakes import HERE
        path = HERE / "run-spec.example.json"
        with self.assertRaises(RefusedError) as refused:
            pipeline.load_run_spec(path, expected_sha256=sha256_hex(path.read_bytes()), repo=HERE.parents[3],
                                   available=False)
        self.assertEqual(refused.exception.code, "spec_placeholder")

    def test_full_sequence_then_resume_reuses_every_stage(self):
        spec, ledger = self.rig.spec()
        result = pipeline.run(spec, self.rig.clients, ledger)
        self.assertEqual(result["status"], "complete", result)
        self.assertEqual([entry["stage"] for entry in result["stages"]], list(pipeline.STAGES))
        self.assertEqual({entry["outcome"] for entry in result["stages"]}, {"complete"})
        record = lambda stage: ledger.read(pipeline.stage_record(stage))["result"]
        self.assertIn("package/tools.py", self.rig.az.staged)
        self.assertEqual(record("deploy")["version"], "1")
        self.assertEqual([entry["id"] for entry in record("invoke")], ["J1", "J2", "J3"])
        self.assertEqual(record("verify")["anonymous_status"], 401)
        failed = [entry for entry in record("verify")["invocations"] if entry["id"] == "J3"][0]["tool_calls"][0]
        self.assertEqual((failed["status"], failed["error_code"]), ("error", "E_ZONE"))
        self.assertTrue(record("register_evaluator")["canary"]["passed"])
        self.assertEqual(record("evaluate")["summary"]["exact"]["passed"], 1)
        job = self.rig.project.beta.agents.jobs[0]
        self.assertEqual((job["inputs"]["options"]["optimization_model"], job["inputs"]["options"]["eval_model"]),
                         (OPTIMIZER, JUDGE))
        self.assertEqual((record("select")["decision"], record("select")["candidate_id"]), ("selected", "c1"))
        promoted = record("promote")
        self.assertEqual(promoted["version"], "2")
        self.assertEqual(json.loads(promoted["definition"]["environment_variables"]["OPTIMIZATION_CONFIG"]),
                         {"instructions": "prompt for c1", "model": MODEL})
        reverified = record("reverify")["verify"]
        self.assertEqual(reverified["identity"]["agent_version"], "2")
        self.assertEqual(reverified["identity"]["optimization_config_sha256"],
                         promoted["metadata"]["optimization_config_sha256"])
        self.assertEqual(self.rig.evals.definitions[max(self.rig.evals.definitions)]["name"], "demo-eval")
        calls = (self.rig.az.count("acr", "build"), self.rig.log.count("create_version"),
                 self.rig.log.count("responses.create"), len(self.rig.project.beta.agents.jobs))
        self.assertEqual(calls, (1, 2, 6, 1))

        again = pipeline.run(spec, self.rig.clients, ledger)
        self.assertEqual(again["status"], "complete")
        self.assertEqual({entry["outcome"] for entry in again["stages"]}, {"reused"})
        self.assertEqual((self.rig.az.count("acr", "build"), self.rig.log.count("create_version"),
                          self.rig.log.count("responses.create"), len(self.rig.project.beta.agents.jobs)), calls)

    def test_stepwise_until_and_from(self):
        spec, ledger = self.rig.spec()
        self.assertEqual(pipeline.run(spec, self.rig.clients, ledger, until="verify")["status"], "complete")
        self.assertEqual(self.rig.project.beta.agents.jobs, [])
        with self.assertRaises(RefusedError) as refused:
            pipeline.run(spec, self.rig.clients, ledger, from_="optimize")
        self.assertEqual(refused.exception.code, "resume_gap")
        done = pipeline.run(spec, self.rig.clients, ledger, from_="register_evaluator")
        self.assertEqual(done["status"], "complete")
        self.assertEqual(done["stages"][0]["stage"], "register_evaluator")

    def test_baseline_decision_stops_after_promote(self):
        self.rig = Rig(self.directory.name + "/b", scores={"base": 0.9, "c1": 0.1, "c2": 0.2})
        spec, ledger = self.rig.spec()
        result = pipeline.run(spec, self.rig.clients, ledger)
        self.assertEqual((result["status"], result["stopped_at"]), ("baseline_retained", "promote"))
        self.assertEqual(self.rig.log.count("create_version"), 1)
        self.assertEqual(pipeline.run(spec, self.rig.clients, ledger)["status"], "baseline_retained")


if __name__ == "__main__":
    unittest.main()
