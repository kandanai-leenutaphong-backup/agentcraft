import contextlib
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

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

    def test_delegation_contracts_remove_direct_candidate_exception(self):
        repository = ROOT.parents[2]
        process = (ROOT / "SKILL.md").read_text()
        roster = (repository / ".github/agents/README.md").read_text()
        domain = (repository / ".github/agents/agentcraft-orchestrator.agent.md").read_text()
        self.assertIn("# AgentCraft Process v1.6", process)
        self.assertIn("Overseer direct children are exactly `agentcraft-orchestrator`, `archivist`, `note_scribe`.", process)
        self.assertIn("Overseer direct children are exactly `agentcraft-orchestrator`, `archivist`, `note_scribe`, `agentcraft-oracle`.", roster)
        self.assertIn("advisory-only exception supersedes the process's three-child rule", roster)
        for contract in (process, roster):
            self.assertNotIn("A constitution-named test subject may be dispatched directly", contract)
        self.assertIn("agentcraft-overseer -> agentcraft-orchestrator -> candidates/specialists", roster)
        self.assertIn("Only the overseer dispatches the archivist", process)
        self.assertIn("Only the overseer dispatches it", process)
        for requirement in ("current stage", "next transition", "status: exploring", "status: ready",
                            "fresh", "supplied tools", "Candidates cannot grade themselves",
                            "held-out labels", "Join all assigned workers", "checkpoint request",
                            "Only the overseer dispatches archivist and note_scribe", "failed attempts",
                            "unverified", "Frontmatter is not an OS sandbox"):
            self.assertIn(requirement, domain)

    def test_overseer_mission_alignment_checkpoint(self):
        repository = ROOT.parents[2]
        role = (repository / ".github/agents/agentcraft-overseer.agent.md").read_text()
        checkpoint = role.split("## Mission Alignment Checkpoint\n", 1)[1].split("\n## ", 1)[0]
        for requirement in (
            "every two completed delivery-team assignments", "before any scope expansion",
            "user correction or context resume", "do not count as delivery assignments",
            "not a\n  host-enforced counter", "if the count is unknown, check now",
            "original objective; new acceptance evidence; remaining acceptance gap",
            "re-plan before dispatching another", "blocker and its exit condition",
            "authorization, safety and quality checks", "not evidence of a better overseer",
        ):
            with self.subTest(requirement=requirement):
                self.assertIn(requirement, checkpoint)

    def test_v162_delivery_discipline_and_manual_notes_ignore(self):
        repository = ROOT.parents[2]
        agents = repository / ".github/agents"
        contracts = {
            "agentcraft-overseer.agent.md": (
                "# AgentCraft Overseer v1.62\n", "## Delivery Discipline",
                "one end-to-end orchestrator", "cheapest prerequisites", "Reserve closure time",
                "never reset the clock", "skip safety/acceptance", "prevent causal claims",
            ),
            "agentcraft-orchestrator.agent.md": (
                "## Bounded Delivery", "in-scope repairs", "supplied verified prerequisites",
                "original monotonic start", "no late pass", "Required evidence is never optional",
            ),
            "archivist.agent.md": (
                "Reuse supplied primary receipts", "Keep all required facts",
                "archival time counts toward whole-task time",
            ),
            "note_scribe.agent.md": (
                "Reuse supplied verified evidence", "notes count toward whole-task time",
                "instead of inventing closure",
            ),
            "README.md": ("## AgentCraft v1.62 Delivery", "not a proven causal speedup"),
        }
        for filename, requirements in contracts.items():
            text = " ".join((agents / filename).read_text().split())
            for requirement in requirements:
                with self.subTest(file=filename, requirement=requirement):
                    self.assertIn(" ".join(requirement.split()), text)
        self.assertIn("/demonstration_project/agentcraft_projects/manual_notes/",
                      (repository / ".gitignore").read_text().splitlines())

    def test_all_agent_conciseness_text_and_preserved_frontmatter(self):
        repository = ROOT.parents[2]
        expected_headers = {
            "agentcraft-oracle": "23ae95ccc03bbd486654eca810f50f6596ac3a9c49b73f10f0c9ba748926fddf",
            "agentcraft-orchestrator": "4b07178c06b5a2f181a4294b1a5bee1d787ccc4646227557726f308b314e909a",
            "agentcraft-overseer": "51cda4a8f4a0360879dacb3e61f7b605ac26387b0b3f691f2937f1734f98a5b6",
            "architecture-cartographer": "6069a571ebcec5c0c4f1e65a92996271d934ab361afd8ef5921fd467d59369fb",
            "archivist": "52be7797f85afc79e9ad58534b475c1759a4354476609518c1984c3a93a94e2d",
            "data-explorer": "8a969ed93ccd7277a9a26f4aba795f74d7d21346694f821f4eb9f6438b964bfd",
            "developer": "7d81c45e4aac5d505a1995b12878cc16e1dead7f449638b479d369f4cc8a5ab2",
            "documentation_curator": "6a94b9ff9db0bdf80ac7c30ed43ee6ff8778fa0c931351b460dc888fe2628884",
            "experience-evaluator": "1ee1e7f2e31e79d565601eebb4a44359d05b752840c11e47b78fdae49a127020",
            "frontend-developer": "76e58b26d4b5c24702d8f4f5249c48a16594c36516fa5d7c1caf5748e35936cf",
            "hyperframes-motion-smith": "a7f9ac083e6c73d65ef0f4fb29c4515d644679f575153b89eae1d4d03a756aae",
            "local-dev-test-subject": "2b4f3cb8f34adc7ad68018839d23cb3d69211028f9731c031649e4ff6c350011",
            "note_scribe": "d28a360445fce4fed8cd6401d0c39c23ae0d5f9037216a0b315a1ee5989440fc",
            "orchestrator": "1de107380f9cc9903761e17423625fdad0d590d6f784eff32740084521a10cc4",
            "overseer": "45a29977d6b49486b5408bb08c363f5c66fbd5a102e02025291f82fce595d28f",
            "solution-architect": "ff8c9c0a618951aa86c5c54c82074edd9c9bc64b429253165b7a204bc01173be",
            "ui-experience-auditor": "a05f421754df65c22d1a0b326922f63cd81a132175636a276b2e12a8c0093249",
        }
        paths = sorted((repository / ".github/agents").glob("*.agent.md"))
        self.assertEqual({path.name.removesuffix(".agent.md") for path in paths}, set(expected_headers))
        rule = (
            "Use the fewest words that preserve decisions, instructions, evidence and constraints. "
            "Lead with result/decision/blocker; short sentences/bullets. No filler/repeated plans/transcripts. "
            "Put detailed logs in artifacts; return paths and relevant measurements. "
            "Never omit uncertainty, failed attempts, safety/authorization limits or required acceptance "
            "evidence to shorten output."
        )
        for path in paths:
            with self.subTest(agent=path.name):
                content = path.read_bytes()
                header = content.split(b"---", 2)[1]
                self.assertEqual(hashlib.sha256(header).hexdigest(),
                                 expected_headers[path.name.removesuffix(".agent.md")])
                self.assertEqual(yaml.safe_load(header)["name"], path.name.removesuffix(".agent.md"))
                expected_rule = ("Return exactly two selected lines. No updates, preamble, headings, "
                                 "explanations, interpretation or reasoning."
                                 if path.name == "agentcraft-oracle.agent.md" else rule)
                self.assertEqual(content.decode().count("## Conciseness (Required)\n\n" + expected_rule), 1)

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
        self.assertEqual(specific["agents"], ["agentcraft-orchestrator", "archivist", "note_scribe", "agentcraft-oracle"])
        self.assertNotIn("local-dev-test-subject", specific["agents"])
        self.assertIn("Brevity Is Mandatory", overseer.read_text())
        domain = agents / "agentcraft-orchestrator.agent.md"
        domain_header = header(domain)
        self.assertEqual(domain_header["name"], "agentcraft-orchestrator")
        self.assertEqual(domain_header["model"], "GPT-6 Astra")
        self.assertEqual(domain_header["reasoning-effort"], "medium")
        self.assertFalse(domain_header["user-invocable"])
        self.assertTrue({"agent", "execute", "read", "edit", "search"} <= set(domain_header["tools"]))
        self.assertEqual(domain_header["tools"], header(agents / "orchestrator.agent.md")["tools"])
        self.assertIn("local-dev-test-subject", domain_header["agents"])
        self.assertEqual(len(domain_header["agents"]), len(set(domain_header["agents"])))
        for forbidden in ("agentcraft-overseer", "overseer", "orchestrator", "agentcraft-orchestrator",
                          "archivist", "note_scribe"):
            self.assertNotIn(forbidden, domain_header["agents"])
        for child in specific["agents"] + domain_header["agents"]:
            self.assertEqual(header(agents / f"{child}.agent.md")["name"], child)
        for role in (overseer, domain):
            self.assertIn("[AgentCraft process](../skills/agentcraft-process/SKILL.md)", role.read_text())
        self.assertIn("# AgentCraft Overseer v1.62\n", overseer.read_text())
        self.assertIn("# AgentCraft Orchestrator v1.1\n", domain.read_text())
        self.assertNotIn("invoke that exact agent directly", overseer.read_text())
        scribe = agents / "note_scribe.agent.md"
        self.assertEqual(header(scribe)["tools"], ["read", "search", "edit"])
        self.assertFalse(header(scribe)["user-invocable"])
        self.assertEqual(header(ROOT / "SKILL.md")["name"], "agentcraft-process")
        subject = agents / "local-dev-test-subject.agent.md"
        self.assertEqual(header(subject)["name"], "local-dev-test-subject")
        self.assertEqual(header(subject)["tools"], ["read", "search", "execute"])
        self.assertFalse(header(subject)["user-invocable"])
        self.assertIn("piloted by agentcraft-orchestrator", header(subject)["description"])
        self.assertNotIn("dispatched by AgentCraft Overseer", header(subject)["description"])
        archivist = agents / "archivist.agent.md"
        self.assertEqual(header(archivist)["name"], "archivist")
        self.assertEqual(header(archivist)["tools"], ["read", "search", "execute"])
        self.assertFalse(header(archivist)["user-invocable"])
        catalogue = json.loads((repository / "libraries/capabilities.json").read_text())
        self.assertEqual(sum(item["name"] == "agentcraft-process" for item in catalogue["skills"]), 1)
        for path in (overseer, domain, scribe, subject, archivist, ROOT / "SKILL.md"):
            for target in re.findall(r"\]\(([^)]+)\)", path.read_text()):
                destination, _, anchor = target.partition("#")
                referenced = path.parent / destination
                self.assertTrue(referenced.exists(), target)
                if anchor:
                    headings = [re.sub(r"[^a-z0-9 -]", "", title.lower()).replace(" ", "-")
                                for title in re.findall(r"^#+ (.+)$", referenced.read_text(), re.M)]
                    self.assertIn(anchor, headings)


class OracleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script = ROOT.parents[2] / ".github/tools/oracle.py"
        spec = importlib.util.spec_from_file_location("oracle_selector", cls.script)
        cls.oracle = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.oracle)

    def test_oracle_native_role_and_routing(self):
        agents = ROOT.parents[2] / ".github/agents"
        role = (agents / "agentcraft-oracle.agent.md").read_text()
        header = yaml.safe_load(role.split("---", 2)[1])
        self.assertEqual(header["name"], "agentcraft-oracle")
        self.assertTrue(header["description"])
        self.assertEqual(header["model"], "GPT-6 Astra")
        self.assertEqual(header["reasoning-effort"], "low")
        self.assertEqual(header["tools"], ["execute"])
        self.assertEqual(header["agents"], [])
        self.assertFalse(header["user-invocable"])
        self.assertFalse(header.get("disable-model-invocation", False))
        self.assertLessEqual(len(role.splitlines()), 35)
        for requirement in ("## Conciseness (Required)", "exactly two selected lines",
                            "exactly three distinct", "16 words and 200 characters",
                            "No rerolls", "stdout verbatim", "Oracle unavailable.",
                            "not a sandbox", "never facts, evidence or permission",
                            "python3 .github/tools/oracle.py <<'ORACLE_JSON'"):
            self.assertIn(requirement, role)
        for name in ("agentcraft-overseer", "agentcraft-orchestrator"):
            caller = (agents / f"{name}.agent.md").read_text()
            caller_header = yaml.safe_load(caller.split("---", 2)[1])
            self.assertIn("agentcraft-oracle", caller_header["agents"])
            consultation = caller.split("## Oracle Consultation\n", 1)[1].split("\n## ", 1)[0]
            for requirement in ("Optionally consult", "one call per consultation", "no recursive consultation",
                                "obligation per task", "`low` effort", "Interpret, test or reject",
                                "authority expansion", "never substitute a model or fabricate a draw"):
                self.assertIn(requirement, consultation)
        domain = (agents / "agentcraft-orchestrator.agent.md").read_text()
        self.assertIn("Request max effort except\nfor `agentcraft-oracle`, which retains `low`", domain)
        overseer = (agents / "agentcraft-overseer.agent.md").read_text()
        self.assertIn("Direct dispatch of\n  specialists or candidates", overseer)
        self.assertIn("including `local-dev-test-subject`, is prohibited", overseer)

    def test_oracle_samples_once_without_replacement(self):
        candidates = ["The boundary hides the assumption.", "The exception defines the rule.",
                      "Reverse the question; inspect the answer."]
        with patch.object(self.oracle.random, "SystemRandom") as generator:
            generator.return_value.sample.return_value = [candidates[2], candidates[0]]
            self.assertEqual(self.oracle.select(candidates), [candidates[2], candidates[0]])
            generator.assert_called_once_with()
            generator.return_value.sample.assert_called_once_with(candidates, 2)
        selected = self.oracle.select(candidates)
        self.assertEqual(len(set(selected)), 2)
        self.assertTrue(set(selected) <= set(candidates))

    def test_oracle_rejects_invalid_candidates_before_sampling(self):
        invalid = [None, {}, "three", [], ["one", "two"], ["one", "two", "three", "four"],
                   ["one", "two", 3], ["one", "two", None], ["one", "two", True],
                   ["one", "two", []], ["one", "two", ""], ["one", "two", "   "],
                   ["one", "two", "one"], ["one", "two", " one "],
                   ["one", "two", "word " * 17], ["one", "two", "a" * 201]]
        invalid.extend(["one", "two", "bad" + separator + "line"]
                       for separator in ("\n", "\r", "\t", "\x00", "\x1b", "\u2028", "\u2029", "\ud800"))
        for candidates in invalid:
            with self.subTest(candidates=candidates), patch.object(self.oracle.random, "SystemRandom") as generator:
                with self.assertRaises(ValueError):
                    self.oracle.select(candidates)
                generator.assert_not_called()

    def test_oracle_accepts_exact_bounds_and_literal_content(self):
        candidates = [" ".join(["word"] * 16), "a" * 200, "$(exit 99); 'quoted' `exit 88`"]
        result = subprocess.run([sys.executable, str(self.script)], input=json.dumps(candidates),
                                text=True, capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        selected = result.stdout.splitlines()
        self.assertEqual(len(selected), 2)
        self.assertEqual(len(set(selected)), 2)
        self.assertTrue(set(selected) <= set(candidates))
        self.assertEqual(result.stdout, "\n".join(selected) + "\n")

    def test_oracle_cli_failure_has_no_candidate_output(self):
        for payload in ("", "[", '["one", "two", "three"] trailing',
                        '["private candidate", "two", "two"]', '["one", "two", 3]'):
            with self.subTest(payload=payload):
                result = subprocess.run([sys.executable, str(self.script)], input=payload,
                                        text=True, capture_output=True, timeout=5)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertEqual(result.stderr, "Oracle unavailable.\n")


if __name__ == "__main__":
    unittest.main()