"""The optimization component, exercised with a neutral domain and no application import.

The point of these checks is independence: a second host, with its own labels, scorer name,
tool families and authorization rule, gets a working optimization ledger out of the same code
CyberEye runs — without `app.cybereye` ever being imported.
"""

import json
import sys
import subprocess
import tempfile
import unittest
from pathlib import Path

from app.components.agent_optimization import (
    OptimizationProfile,
    OptimizationService,
    PythonToolRunner,
    score,
)

LABELS = ("accept", "review", "reject")

TOOL_CODE = "def run(ctx):\n    return {'rows': 1}\n"


def neutral_request(prompt, evidence, model):
    return {"model": model, "instructions": prompt, "input": json.dumps(evidence), "store": False}


NEUTRAL_PROFILE = OptimizationProfile(
    grades=LABELS,
    scorer_version="neutral-macro-f1-v1",
    tool_runtime="neutral-python-tool-v1",
    tool_families=("sampling", "calibration"),
    objective="Neutral triage decision quality",
    baseline_proposal={"name": "Neutral baseline", "system_prompt": "Decide the outcome.",
                       "rationale": "Control.", "parent_version": None,
                       "tools": [{"name": "basic", "code": TOOL_CODE, "description": "Sample rows.",
                                  "queries": "Rows.", "returns": "A count.", "logic": "Counts."}]},
    model_request=neutral_request,
    runtime={"tool_runtime": "neutral-python-tool-v1", "max_output_tokens": 128},
)


class FakeDataset:
    """The structural protocol the component depends on. No domain meaning lives here."""

    profile_digest = "neutral-profile-digest"

    def describe(self):
        return {"dataset_id": "neutral"}

    def cases(self):
        return [{"case_id": character * 16, "expected": label, "split": split,
                 "start_time": "2024-01-01", "end_time": "2024-01-02"}
                for character, label, split in (("a", "accept", "development"),
                                                ("b", "review", "validation"),
                                                ("c", "reject", "validation"))]

    def query(self, case_id, sql):
        return {"columns": ["rows"], "rows": [[1]], "truncated": False}

    def profiles(self):
        return {"columns": [], "rows": []}

    def run_tool(self, case_id, tool, scope=None):
        return {"rows": 1}


def owner_of(caller):
    if caller != "operator":
        raise PermissionError("Only the operator may optimize")
    return "operator-directory"


class AgentOptimizationComponentTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.service = OptimizationService(FakeDataset(), self.root / "experiments", "neutral-model",
                                           lambda prompt, evidence, model: {"grade": "accept", "rationale": "fixture"},
                                           authorize=owner_of, profile=NEUTRAL_PROFILE)
        self.addCleanup(self.service.close)

    def test_component_imports_without_the_application(self):
        result = subprocess.run([sys.executable, "-c", "import sys; import app.components.agent_optimization; assert not any(name.startswith('app.cybereye') for name in sys.modules)"],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_a_neutral_host_gets_a_measured_baseline_ledger(self):
        experiment = self.service.create("operator", "Neutral experiment")
        self.service.futures[experiment["id"]].result(timeout=10)
        saved = self.service.get("operator", experiment["id"])
        self.assertEqual(saved["scorer_version"], "neutral-macro-f1-v1")
        self.assertEqual(saved["tool_runtime"], "neutral-python-tool-v1")
        self.assertEqual(saved["objective"], "Neutral triage decision quality")
        evaluation = saved["versions"][0]["evaluations"][-1]
        self.assertEqual(evaluation["status"], "completed")
        self.assertEqual(sorted(evaluation["metrics"]["per_class"]), sorted(LABELS))
        self.assertEqual(evaluation["metrics"]["case_count"], 3)
        self.assertTrue((self.root / "experiments" / "operator-directory" / experiment["id"] / "experiment.json").exists())

    def test_the_injected_authorization_decides_who_may_read(self):
        experiment = self.service.create("operator", "Owned")
        self.service.futures[experiment["id"]].result(timeout=10)
        with self.assertRaises(PermissionError):
            self.service.get("intruder", experiment["id"])

    def test_the_host_scorer_labels_are_the_only_classes_counted(self):
        cases = [{"expected": "accept", "predicted": "accept", "correct": True, "elapsed_ms": 1},
                 {"expected": "reject", "predicted": "accept", "correct": False, "elapsed_ms": 3}]
        metrics = score(cases, 4, LABELS)
        self.assertEqual(sorted(metrics["per_class"]), sorted(LABELS))
        self.assertEqual(metrics["accuracy"], 0.5)
        self.assertEqual(sorted(metrics["confusion_matrix"]["accept"]), sorted((*LABELS, "Error")))

    def test_a_tool_without_a_run_entry_point_is_refused(self):
        with self.assertRaises(ValueError):
            PythonToolRunner.validate("x = 1\n")


if __name__ == "__main__":
    unittest.main()
