from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

from agentcraft import catalogue


class CatalogueTests(unittest.TestCase):
    def test_installed_snapshot_has_one_owner_and_safe_status(self):
        document = catalogue.load_catalogue()
        capabilities = document["capabilities"]
        identifiers = {entry["id"] for entry in capabilities}
        self.assertEqual(len(capabilities), len(identifiers))
        features = [feature for entry in capabilities for feature in entry.get("feature_ids", [])]
        self.assertEqual(38, len(set(features)))
        self.assertEqual(len(features), len(set(features)))
        self.assertTrue(all(set(entry["dependencies"]) <= identifiers for entry in capabilities))
        self.assertEqual([], document["mcp"]["registered_servers"])
        self.assertEqual("implemented", document["mcp"]["status"])
        self.assertEqual("offline-verified", document["mcp"]["verification"])
        self.assertEqual("disabled-by-default", document["mcp"]["activation"])
        self.assertEqual({"command": "agentcraft", "args": ["mcp", "--offline"],
                  "capabilities": ["app-composition"], "status": "operator-opt-in"},
                 document["mcp"]["default_request"])
        self.assertTrue(all(target["status"] == "implemented" and target["availability"] == "conditional"
                    for target in document["mcp"]["targets"]))
        self.assertEqual(15, sum(len(target["tools"]) for target in document["mcp"]["targets"]))
        self.assertEqual(27, len(document["mcp"]["legacy_tools"]))
        self.assertEqual("libraries/capabilities.json", document["generation"]["source"])
        self.assertEqual(64, len(document["generation"]["sha256"]))

    def test_snapshot_reads_are_independent(self):
        document = catalogue.load_catalogue()
        count = len(document["skills"])
        document["skills"].clear()
        self.assertEqual(count, len(catalogue.load_catalogue()["skills"]))

    def test_all_tasks_components_and_aliases_are_readable(self):
        document = catalogue.load_catalogue()
        result = catalogue.report()
        self.assertEqual({"skills": 36, "protocols": 8, "embedded_skills": 5, "source_only_skills": 0}, result["totals"])
        self.assertEqual("azure-llm-connectors",
                 catalogue.report(name="managed-identity-model-clients")["entries"][0]["name"])
        names = []
        for skill in document["skills"]:
            names.extend([skill["name"], *skill.get("aliases", [])])
            names.extend(component["name"] for component in skill.get("components", []))
        for protocol in document["protocols"]:
            names.extend({protocol["name"], protocol["native_name"]})
        root = catalogue.guidance_root().resolve()
        for name in names:
            with self.subTest(name=name):
                entry = catalogue.report(name=name)["entries"][0]
                self.assertTrue(entry["content"])
                self.assertTrue(Path(entry["read_path"]).resolve().is_relative_to(root))
        self.assertTrue(catalogue.report(query="composition")["entries"])

    def test_unknown_names_invalid_search_and_root_injection_refuse(self):
        for arguments in ({"name": "missing-capability"}, {"name": "../../private"},
                          {"query": "the and"}, {"query": "composition", "limit": 0},
                          {"name": "harness-guide", "query": "composition"}):
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                catalogue.report(**arguments)
        with self.assertRaises(TypeError):
            catalogue.report(root=Path("/tmp"))

    def test_guidance_is_data_only_and_integrity_checked(self):
        root = catalogue.guidance_root()
        self.assertFalse(any(path.suffix in {".py", ".pyc", ".js", ".mjs", ".ts", ".tsx", ".whl"}
                             for path in root.rglob("*") if path.is_file()))
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "guidance"
            shutil.copytree(root, copied)
            document = copied / "skills/harness-guide/SKILL.md"
            document.write_text("tampered", encoding="utf-8")
            with patch.object(catalogue, "guidance_root", return_value=copied):
                with self.assertRaisesRegex(ValueError, "Native package projection changed"):
                    catalogue.report(name="harness-guide")

    def test_missing_tooling_dependency_fails_without_fallback(self):
        with patch.dict(sys.modules, {"repository_inspection.catalogue": None}):
            with self.assertRaisesRegex(RuntimeError, "requires repository-inspection"):
                catalogue.report()

    def test_reading_never_opens_network_or_starts_processes(self):
        with patch("socket.socket", side_effect=AssertionError("network forbidden")), \
                patch("subprocess.Popen", side_effect=AssertionError("process forbidden")):
            self.assertTrue(catalogue.load_catalogue()["capabilities"])
            self.assertTrue(catalogue.report(name="foundry-agent-runtime")["entries"])
            evidence = json.loads((catalogue.guidance_root() / "provenance.json").read_text())
            self.assertTrue(evidence["sources"])


if __name__ == "__main__":
    unittest.main()