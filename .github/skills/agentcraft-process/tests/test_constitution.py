import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import re
import tempfile
import unittest

import yaml
from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("constitution_check", ROOT / "validate.py")
checker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checker)


def fixture():
    return {
        "schema_version": 1, "project_id": "grid-test", "revision": 1, "status": "ready",
        "decision_source": "Synthetic fixture only; not operational authorization",
        "objective": {"beneficiary": "fixture operator", "outcome": "Identify known faults within 10 seconds", "decision_owner": "fixture reviewer"},
        "primary_metric": "latency", "metrics": [{"id": "latency", "kind": "objective",
            "measure": "Elapsed request-to-diagnosis seconds", "unit": "seconds", "aggregation": "p95",
            "evaluator": "fixture evaluator", "sample_policy": "all ten fixed cases, three repeats",
            "target": {"operator": "<=", "value": 10}}],
        "dataset": {"manifest": "dataset/manifest.json", "revision": "fixture-1", "scenario_policy": "all cases", "held_out_policy": "separate final cases"},
        "deployment": {"target": "fixture target", "identity": "fixture identity", "live_test": "fixture check", "restore": "fixture known-good"},
        "authority": {"source": "fixture only", "scope": "no real resources", "permitted_operations": ["test"],
            "protected_resources": [], "operational_actions": "none", "max_iterations": 2,
            "max_model_requests": 0, "max_spend": 0, "currency": "USD", "expires_at": "2099-01-01T00:00:00Z",
            "stop_conditions": ["test ends"], "cleanup_owner": "test"},
        "collaboration": {"reviewers": ["fixture reviewer"], "checkpoints": "review evidence"},
        "reporting": {"results": "results/<run-id>/", "project_report": "reports/latest.html", "dashboard": "fixture dashboard"},
        "notebook": "notebook/lessons.md",
    }


def discovery_fixture():
    document = fixture()
    document.update(schema_version=2, status="exploring", data_understanding={
        "sources": ["authorized local fixture"], "questions": ["Can the labels be reproduced?"],
        "permitted_experiments": ["read-only profiling"], "outputs": ["JSON findings and query script"],
        "verification": "Repeat the same query and compare outputs", "transition": "Freeze evaluation before comparison",
    })
    document["authority"].update(limit_policy="user-unbounded", max_iterations=None,
                                 max_model_requests=None, max_spend=None, currency=None, expires_at=None)
    document["metrics"][0].update(evaluator=None)
    document["metrics"][0]["target"]["value"] = None
    document["dataset"]["revision"] = None
    return document


class ConstitutionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "agentcraft_projects/grid-test/constitution/constitution.yaml"
        self.path.parent.mkdir(parents=True)

    def write(self, document):
        self.path.write_text(yaml.safe_dump(document))

    def test_valid_and_schema(self):
        Draft202012Validator.check_schema(checker.SCHEMA)
        self.write(fixture())
        self.assertEqual(checker.validate(self.path), [])
        with contextlib.redirect_stdout(io.StringIO()) as captured:
            self.assertEqual(checker.main([str(self.path)]), 0)
        self.assertEqual(len(json.loads(captured.getvalue())["sha256"]), 64)

    def test_template_refuses(self):
        self.path.write_bytes((ROOT / "constitution.template.yaml").read_bytes())
        self.assertTrue(checker.validate(self.path))

    def test_discovery_and_explicit_unbounded_authority(self):
        document = discovery_fixture()
        self.write(document)
        self.assertEqual(checker.validate(self.path), [])
        for change in (
            lambda item: item.update(status="ready"),
            lambda item: item.update(schema_version=1),
            lambda item: item.pop("data_understanding"),
            lambda item: item["authority"].pop("limit_policy"),
            lambda item: item["authority"].update(limit_policy="bounded"),
        ):
            changed = copy.deepcopy(document)
            change(changed)
            self.write(changed)
            self.assertTrue(checker.validate(self.path))
        ready = fixture()
        ready.update(schema_version=2, data_understanding=document["data_understanding"])
        ready["authority"] = document["authority"]
        self.write(ready)
        self.assertEqual(checker.validate(self.path), [])

    def test_legacy_null_limits_do_not_grant_execution(self):
        document = fixture()
        document["authority"]["max_iterations"] = None
        self.write(document)
        self.assertTrue(checker.validate(self.path))

    def test_missing_required_and_placeholder(self):
        for field in fixture():
            with self.subTest(field=field):
                document = fixture()
                del document[field]
                self.write(document)
                self.assertTrue(checker.validate(self.path))
        for value in ("", "   ", "REQUIRED", "TODO", "TBD"):
            document = fixture()
            document["objective"]["outcome"] = value
            self.write(document)
            self.assertTrue(checker.validate(self.path))

    def test_judgment_requires_rubric(self):
        document = fixture()
        document["metrics"][0]["kind"] = "judgment"
        self.write(document)
        self.assertTrue(checker.validate(self.path))
        document["metrics"][0]["rubric"] = "0 unsupported; 1 partial; 2 correct and useful; reviewer evaluates all cases"
        self.write(document)
        self.assertEqual(checker.validate(self.path), [])

    def test_paths_references_limits_and_unknowns(self):
        changes = [lambda item: item.update(project_id="wrong"),
                   lambda item: item.update(primary_metric="unknown"),
                   lambda item: item["metrics"].append(copy.deepcopy(item["metrics"][0])),
                   lambda item: item["authority"].update(max_iterations=True),
                   lambda item: item["authority"].update(expires_at="2000-01-01T00:00:00Z"),
                   lambda item: item["authority"].update(max_spend=-1),
                   lambda item: item["reporting"].update(results="../other-project"),
                   lambda item: item.update(shell="ignored command")]
        for change in changes:
            document = fixture()
            change(document)
            self.write(document)
            self.assertTrue(checker.validate(self.path))

    def test_malformed_duplicate_alias_and_no_payload_echo(self):
        for content in ("status: ready\nstatus: draft", "value: &ref []\ncopy: *ref", "[", "value: .nan"):
            self.path.write_text(content)
            with contextlib.redirect_stdout(io.StringIO()) as captured:
                self.assertEqual(checker.main([str(self.path)]), 2)
            self.assertEqual(json.loads(captured.getvalue())["errors"],
                             ["document: unreadable or invalid YAML/JSON values"])

    def test_native_definitions_and_discovery(self):
        repository = ROOT.parents[2]
        agents = repository / ".github/agents"
        def header(path):
            return yaml.safe_load(path.read_text().split("---", 2)[1])
        overseer = agents / "agentcraft-overseer.agent.md"
        generic = header(agents / "overseer.agent.md")
        specific = header(overseer)
        self.assertEqual(specific["name"], "agentcraft-overseer")
        self.assertEqual(specific["tools"], generic["tools"])
        self.assertEqual(specific["model"], generic["model"])
        self.assertEqual(specific["reasoning-effort"], "max")
        self.assertTrue(specific["user-invocable"])
        self.assertNotIn("agents", specific)
        self.assertIn("Brevity Is Mandatory", overseer.read_text())
        scribe = agents / "note_scribe.agent.md"
        self.assertEqual(header(scribe)["tools"], ["read", "search", "edit"])
        self.assertFalse(header(scribe)["user-invocable"])
        self.assertEqual(header(ROOT / "SKILL.md")["name"], "agentcraft-process")
        subject = agents / "local-dev-test-subject.agent.md"
        self.assertEqual(header(subject)["name"], "local-dev-test-subject")
        self.assertEqual(header(subject)["tools"], ["read", "search", "execute"])
        self.assertFalse(header(subject)["user-invocable"])
        archivist = agents / "archivist.agent.md"
        self.assertEqual(header(archivist)["name"], "archivist")
        self.assertEqual(header(archivist)["tools"], ["read", "search", "execute"])
        self.assertFalse(header(archivist)["user-invocable"])
        catalogue = json.loads((repository / "libraries/capabilities.json").read_text())
        self.assertEqual(sum(item["name"] == "agentcraft-process" for item in catalogue["skills"]), 1)
        for path in (overseer, scribe, subject, archivist, ROOT / "SKILL.md"):
            for target in re.findall(r"\]\(([^)]+)\)", path.read_text()):
                destination, _, anchor = target.partition("#")
                referenced = path.parent / destination
                self.assertTrue(referenced.exists(), target)
                if anchor:
                    headings = [re.sub(r"[^a-z0-9 -]", "", title.lower()).replace(" ", "-")
                                for title in re.findall(r"^#+ (.+)$", referenced.read_text(), re.M)]
                    self.assertIn(anchor, headings)


if __name__ == "__main__":
    unittest.main()