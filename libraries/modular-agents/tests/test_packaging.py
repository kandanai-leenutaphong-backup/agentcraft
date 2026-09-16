"""Flat artifact, portability boundary, and integrity refusals."""

from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from test_definition import ROOT
from hostedagents import load_definition
from hostedagents.packaging import BundleError, build_bundle, load_bundle
from hostedagents.policy import RuntimePolicy, RuntimeTarget


class BundleFixture:
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.work = Path(self.temporary.name)
        self.requirements = self.work / "requirements.txt"
        self.requirements.write_text("modular-agents[hosted]==0.2.0\nllm-interface[openai]==0.1.0a1\n", encoding="utf-8")
        self.definition = load_definition(ROOT / "examples/control", allowed_prefixes=("agent_tools.",))

    def build(self, **kwargs):
        return build_bundle(
            self.definition,
            package_sources={"agent_tools": ROOT / "examples/agent_tools"},
            output_dir=self.work / "artifacts", requirements=self.requirements, **kwargs,
        )


class PackagingTests(BundleFixture, unittest.TestCase):
    def test_flat_bundle_preserves_exact_prompt_and_callable_sources(self):
        bundle = self.build()
        with zipfile.ZipFile(bundle.zip_path) as archive:
            names = set(archive.namelist())
            self.assertTrue({"main.py", "agent_config.json", "tool_schemas.json", "requirements.txt"} <= names)
            self.assertIn("agent_tools/notes.py", names)
            self.assertFalse(any(name.startswith(("agentconfig/", "toolshape/", "hostedagents/", "llm_interface/")) for name in names))
            self.assertIn(b"modular-agents[hosted]==0.2.0", archive.read("requirements.txt"))
            self.assertFalse({"metadata.json", "grants.json"} & names)
            self.assertFalse(any("__pycache__" in name or name.startswith("hcagent/") for name in names))
            config = json.loads(archive.read("agent_config.json"))
            self.assertEqual(config["instructions"], self.definition.spec.instructions)
            self.assertEqual(json.loads(archive.read("tool_schemas.json")), self.definition.tools.schemas)
            self.assertFalse(config["policy"]["allow_model"])
            self.assertEqual(config["policy"]["allowed_tools"], [])
            compile(archive.read("main.py"), "main.py", "exec")

    def test_build_is_content_addressed_and_idempotent(self):
        first = self.build()
        second = self.build()
        self.assertEqual(first.artifact_id, second.artifact_id)
        self.assertEqual(first.zip_path, second.zip_path)
        self.assertEqual(load_bundle(first.directory).sha256, first.sha256)

    def test_tampered_artifact_is_refused_without_overwriting_it(self):
        bundle = self.build()
        bundle.zip_path.write_bytes(b"modified")
        with self.assertRaises(BundleError):
            load_bundle(bundle.directory)
        with self.assertRaises(BundleError):
            self.build()
        self.assertEqual(bundle.zip_path.read_bytes(), b"modified")

    def test_dependency_paths_and_implicit_tool_sources_are_refused(self):
        self.requirements.write_text("-e ../another-skill\n", encoding="utf-8")
        with self.assertRaises(BundleError):
            self.build()
        with self.assertRaises(BundleError):
            build_bundle(self.definition, package_sources={}, output_dir=self.work)

    def test_bundle_refuses_missing_canonical_runtime_dependencies(self):
        self.requirements.write_text("PyYAML==6.0.2\n", encoding="utf-8")
        with self.assertRaisesRegex(BundleError, "canonical"):
            self.build()

    def test_runtime_grants_need_a_matching_tool_and_model_target(self):
        with self.assertRaises(BundleError):
            self.build(policy=RuntimePolicy(allowed_tools=("unknown",)))
        with self.assertRaises(BundleError):
            self.build(policy=RuntimePolicy(allow_model=True))
        with self.assertRaises(ValueError):
            RuntimeTarget(model_endpoint="https://untrusted.invalid/openai/v1")

    def test_external_symlink_source_is_refused(self):
        link = self.work / "agent_tools"
        link.symlink_to(ROOT / "examples/agent_tools", target_is_directory=True)
        with self.assertRaises(BundleError):
            build_bundle(self.definition, package_sources={"agent_tools": link}, output_dir=self.work)


if __name__ == "__main__":
    unittest.main()