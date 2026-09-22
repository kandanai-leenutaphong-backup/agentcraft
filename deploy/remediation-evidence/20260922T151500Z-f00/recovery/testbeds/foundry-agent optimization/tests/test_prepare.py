import importlib.util
import json
from pathlib import Path
import re
import tempfile
import unittest
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("preparation", ROOT / "deploy/prepare.py")
PREP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PREP)


class PreparationTests(unittest.TestCase):
    def test_metric_oracles(self):
        labels = list(PREP.LABELS)
        perfect = PREP.EVALUATOR.score(labels, labels)
        self.assertEqual(perfect["accuracy"], 1)
        self.assertEqual(perfect["macro_f1"], 1)
        invalid = PREP.EVALUATOR.score(labels, ["explanation", None, ""])
        self.assertEqual(invalid["accuracy"], 0)
        self.assertEqual(invalid["macro_f1"], 0)
        self.assertEqual(invalid["invalid_rate"], 1)
        majority = PREP.EVALUATOR.score(labels, [labels[0]] * 3)
        self.assertAlmostEqual(majority["macro_f1"], 1 / 6)
        with self.assertRaises(ValueError):
            PREP.EVALUATOR.score(labels, [])

    def test_duplicate_group_and_conflict(self):
        row = "5.1,3.5,1.4,0.2,Iris-setosa\n"
        rows, findings = PREP.rows_from_text(row * 2)
        self.assertEqual(len(rows), 1)
        self.assertEqual(findings["duplicates_removed"], 1)
        with self.assertRaises(ValueError):
            PREP.rows_from_text(row + row.replace("Iris-setosa", "Iris-virginica"))
        for bad in ("nan,3,2,1,Iris-setosa", "1,2,3,4,foreign", "1,2,3,Iris-setosa", ""):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                PREP.rows_from_text(bad)

    def fixture_rows(self):
        return [{"id": f"{label}-{index}", "features": (index + 1, 2, 3, 4), "label": label}
                for label in PREP.LABELS for index in range(10)]

    def test_splits_order_independent_stratified(self):
        rows = self.fixture_rows()
        partitions = PREP.splits(rows)
        self.assertEqual(partitions, PREP.splits(list(reversed(rows))))
        identifiers = [row["id"] for members in partitions.values() for row in members]
        self.assertEqual(len(identifiers), len(set(identifiers)))
        for members in partitions.values():
            self.assertEqual({row["label"] for row in members}, set(PREP.LABELS))

    def test_native_dataset_and_query_separation(self):
        row = self.fixture_rows()[0]
        document = PREP.native_dataset([row])
        self.assertEqual(document["type"], "inline")
        self.assertEqual(document["items"][0]["ground_truth"], row["label"])
        self.assertEqual(document["items"][0]["desired_num_turns"], 1)
        self.assertNotIn(row["id"], document["items"][0]["query"])
        changed = {**row, "label": PREP.LABELS[1]}
        self.assertEqual(PREP.query(row), PREP.query(changed))

    def test_immutable_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "frozen.json"
            PREP.persist(path, b"first")
            PREP.persist(path, b"first")
            with self.assertRaises(ValueError):
                PREP.persist(path, b"changed")
            link = Path(directory) / "link"
            link.symlink_to(path)
            with self.assertRaises(ValueError):
                PREP.persist(link, b"first")

    def test_configuration_and_model_owner(self):
        from unittest.mock import Mock
        config_spec = importlib.util.spec_from_file_location("classifier_composition", ROOT / "composition.py")
        composition = importlib.util.module_from_spec(config_spec)
        config_spec.loader.exec_module(composition)
        agent = composition.load_spec()
        self.assertEqual(agent.name, "agentcraft-iris-optimization")
        self.assertEqual(agent.tools, ())
        model = Mock()
        self.assertIs(composition.compose(model, agent), model.agent.return_value)
        model.agent.assert_called_once_with(name=agent.name, instructions=agent.instructions, tools=())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "configuration.yaml"
            path.write_text((ROOT / "configuration.yaml").read_text().replace("tools: []", "tools: [os:system]"))
            with self.assertRaises(ValueError):
                composition.load_spec(path)

    def test_frozen_constitution_and_manifest(self):
        validator_spec = importlib.util.spec_from_file_location("constitution_validator", PREP.REPO / ".github/skills/agentcraft-process/validate.py")
        validator = importlib.util.module_from_spec(validator_spec)
        validator_spec.loader.exec_module(validator)
        constitution = PREP.PROJECT / "constitution/constitution.yaml"
        self.assertEqual(validator.validate(constitution), [])
        document = validator.yaml.safe_load(constitution.read_text())
        manifest = PREP.DATA / "manifest.json"
        self.assertIn(PREP.sha(manifest.read_bytes()), document["dataset"]["revision"])
        self.assertIn(PREP.sha((ROOT / "evaluator.py").read_bytes()), document["metrics"][0]["evaluator"])
        prepared = json.loads(manifest.read_text())
        self.assertEqual({name: len(rows) for name, rows in prepared["membership"].items()}, {"train": 87, "validation": 30, "holdout": 30})
        self.assertFalse(prepared["findings"]["holdout_scored"])
        self.assertEqual((PREP.DATA / "private/holdout.json").stat().st_mode & 0o777, 0o600)

    def test_specification_links_and_pins(self):
        documents = [PREP.REPO / "specs/20260922_FOUNDRY_AGENT_OPTIMIZATION.md", ROOT / "README.md", ROOT / "deploy/README.md"]
        for document in documents:
            for link in re.findall(r"\]\(([^)]+)\)", document.read_text()):
                if not link.startswith(("https://", "http://", "#")):
                    self.assertTrue((document.parent / unquote(link.split("#")[0])).exists(), (document, link))
        specification = documents[0].read_text()
        for path in (ROOT / "evaluator.py", ROOT / "configuration.yaml", ROOT / "prompts/classifier.md", PREP.DATA / "manifest.json"):
            self.assertIn(PREP.sha(path.read_bytes()), specification)