from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import posixpath
import re
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import unquote, urlsplit

from repository_inspection.catalogue import report


TOOL = Path(__file__).resolve().parents[1] / "tools/package_native.py"
SPEC = importlib.util.spec_from_file_location("package_native", TOOL)
assert SPEC is not None and SPEC.loader is not None
package_native = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(package_native)


class NativeDistributionTests(unittest.TestCase):
    def make_workspace(self, root):
        core = root / ".github"
        files = {
            "agents/example.agent.md": "---\nname: example\n---\n[Skill](../skills/example/SKILL.md)\n",
            "instructions/example.instructions.md": "---\napplyTo: '**'\n---\n[Workflow](../protocols/protocol-example/SKILL.md)\n",
            "skills/example/SKILL.md": "---\nname: example\ndescription: Example task.\n---\n[Guide](../../../libraries/example/README.md)\n",
            "protocols/protocol-example/SKILL.md": "---\nname: protocol-example\ndescription: Example workflow.\n---\nProcedure.\n",
            "skills/catalogue.json": json.dumps({"skills": [{"name": "example", "summary": "Example task."}]}),
            "protocols/catalogue.json": json.dumps({"protocols": [{"name": "protocol-example", "path": "protocol-example/SKILL.md", "summary": "Example workflow."}]}),
        }
        for relative, text in files.items():
            target = core / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        library = root / "libraries/example"
        library.mkdir(parents=True)
        (library / "README.md").write_text("# Example\n\nUse the installed public API.\n", encoding="utf-8")
        catalogue = {
            "schema_version": 1, "revision": "fixture.1", "plugin": {"name": "example", "version": "1.0.0"},
            "capabilities": [{"id": "example", "outcome": "Read example guidance", "owner": "libraries/example",
                              "source_paths": ["libraries/example"], "distributions": [], "public_surfaces": ["example"],
                              "profiles": [], "dependencies": [], "docs": ["libraries/example/README.md"], "examples": [],
                              "checks": {"paths": [], "command": None, "status": "not-run"},
                              "grants": "None", "lifetime": "No clients", "status": "retained"}],
            "skills": [{"name": "example", "summary": "Example task.", "access": "guidance", "aliases": ["old-example"],
                        "capabilities": ["example"], "source": ".github/skills/example/SKILL.md", "guidance": "libraries/example/README.md", "status": "retained",
                        "components": [{"name": "embedded-example", "path": "guides/embedded-example/SKILL.md", "summary": "Embedded task.",
                                        "access": "guidance", "guidance": "libraries/example/README.md", "status": "retained"}]}],
            "protocols": [{"name": "example-workflow", "native_name": "protocol-example", "path": "protocol-example/SKILL.md",
                           "summary": "Example workflow.", "access": "protocol", "guidance": ".github/protocols/protocol-example/SKILL.md", "status": "guidance-only"}],
            "source_skills": [], "mcp": {"status": "unavailable", "verification": "not-run", "activation": "disabled-by-default", "registered_servers": [], "targets": [], "legacy_tools": {}},
            "guidance": {"roots": ["libraries/example", ".github/skills", ".github/protocols", ".github/agents", ".github/instructions"],
                         "notices": [], "redirects": {}, "historical_segments": ["records"]},
        }
        (root / "libraries/capabilities.json").write_text(json.dumps(catalogue), encoding="utf-8")
        return core

    def make_mcp_workspace(self, root):
        core = self.make_workspace(root)
        path = root / "libraries/capabilities.json"
        document = json.loads(path.read_text())
        source = "libraries/app-composition/appcompose/mcp.py"
        tools = ["composition_status", "composition_validate", "composition_demo"]
        for relative in (source, package_native.PACKAGE + "/mcp.py", "libraries/framework/tests/test_mcp.py"):
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("", encoding="utf-8")
        (root / source).write_text("TOOLS = [\n" + "".join(
            f"    types.Tool(name={json.dumps(name)}),\n" for name in tools) + "]\n", encoding="utf-8")
        document["capabilities"].append({
            "id": "app-composition", "outcome": "Offline composition", "owner": "libraries/app-composition",
            "source_paths": ["libraries/app-composition"], "distributions": [], "public_surfaces": ["appcompose"],
            "profiles": [], "dependencies": [], "docs": [], "examples": [],
            "checks": {"paths": [], "command": None, "status": "not-run"},
            "grants": "Explicit host", "lifetime": "Host-owned", "status": "implemented",
        })
        document["mcp"] = {
            "status": "implemented", "verification": "offline-verified", "activation": "disabled-by-default",
            "registered_servers": [], "source": package_native.PACKAGE + "/mcp.py",
            "checks": {"paths": ["libraries/framework/tests/test_mcp.py"], "command": "fixture-check", "status": "offline-verified"},
            "default_request": {"command": "agentcraft", "args": ["mcp", "--offline"],
                                "capabilities": ["app-composition"], "status": "operator-opt-in"},
            "targets": [{"name": "composition", "capability": "app-composition", "source": source,
                         "tools": tools, "status": "implemented", "verification": "offline-verified",
                         "availability": "conditional", "reason": "Explicit offline opt-in"}],
            "legacy_tools": {"appcompose_status": "composition_status"},
        }
        path.write_text(json.dumps(document), encoding="utf-8")
        return core

    def test_native_files_use_workspace_sources_without_legacy_core(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_workspace(root)
            outputs = package_native.native_files(root)
            self.assertIn("com.github.copilot/agents/example.agent.md", outputs)
            self.assertIn("com.github.copilot/rules/example.instructions.md", outputs)
            self.assertFalse(any(Path(relative).suffix in {".py", ".ts", ".tsx", ".js"} for relative in outputs))
            self.assertFalse((root / "core").exists())

    def test_protocol_guidance_is_projected_to_native_skill(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            core = self.make_workspace(root)
            outputs = package_native.native_files(root)
            relative = "skills/protocol-example/SKILL.md"
            self.assertIn(relative, outputs)
            self.assertEqual(
                (core / "protocols/protocol-example/SKILL.md").read_text(),
                outputs["com.github.copilot/guidance/protocols/protocol-example/SKILL.md"],
            )
            self.assertIn("../../protocols/protocol-example/SKILL.md", outputs[relative])

    def test_materialize_round_trip_without_legacy_core_or_source_vendoring(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            core = self.make_workspace(root)
            source = root / "libraries/example/src/example.py"
            source.parent.mkdir(parents=True)
            source.write_text("CAPABILITY_SOURCE = True\n", encoding="utf-8")
            before = {path.relative_to(root) for path in root.rglob("*") if path.is_file()}
            changed = package_native.materialize(root, check=True)
            self.assertEqual(before, {path.relative_to(root) for path in root.rglob("*") if path.is_file()})
            self.assertEqual(changed, package_native.materialize(root))
            self.assertEqual([], package_native.materialize(root, check=True))
            self.assertEqual([], package_native.materialize(root))
            self.assertFalse((root / "core").exists())
            self.assertFalse((core / package_native.PORTABLE).exists())
            after = {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}
            self.assertEqual(after - {path.as_posix() for path in before}, set(changed) - {path.as_posix() for path in before})
            manifest = json.loads((core / "native-manifest.json").read_text())
            for relative, digest in manifest["files"].items():
                self.assertEqual(digest, hashlib.sha256((core / relative).read_bytes()).hexdigest())
            for relative, digest in manifest["package_files"].items():
                self.assertEqual(digest, hashlib.sha256((root / package_native.PACKAGE / relative).read_bytes()).hexdigest())
            catalogue = json.loads((core / "skills/catalogue.json").read_text())
            self.assertEqual([entry["name"] for entry in catalogue["skills"]], ["example", "protocol-example"])
            self.assertEqual("../../" + package_native.PACKAGE + "/guidance", catalogue["reader_root"])
            reader = (core / "skills" / catalogue["reader_root"]).resolve()
            self.assertEqual(report(root / package_native.PACKAGE / "guidance"), report(reader))

    def test_generated_links_resolve_after_guidance_bundle_relocation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "workspace"
            core = self.make_workspace(root)
            package_native.materialize(root)
            bundle = Path(temporary) / "installed"
            self.assertTrue(package_native.materialize(root, plugin_output=bundle, check=True))
            self.assertFalse(bundle.exists())
            self.assertTrue(package_native.materialize(root, plugin_output=bundle))
            self.assertEqual([], package_native.materialize(root, plugin_output=bundle, check=True))
            self.assertEqual([], package_native.materialize(root, plugin_output=bundle))
            self.assertFalse((core / package_native.PORTABLE).exists())
            manifest = json.loads((bundle / "native-manifest.json").read_text())
            self.assertEqual({}, manifest["package_files"])
            for relative, expected in manifest["files"].items():
                self.assertEqual(expected, hashlib.sha256((bundle / relative).read_bytes()).hexdigest())
            for document in bundle.rglob("*.md"):
                for target in re.findall(r"\]\(([^)]+)\)", document.read_text()):
                    parsed = urlsplit(target)
                    if parsed.scheme or not parsed.path:
                        continue
                    resolved = (document.parent / unquote(parsed.path)).resolve()
                    self.assertTrue(resolved.is_relative_to(bundle))
                    self.assertTrue(resolved.is_file())
            self.assertFalse((bundle.parent / "libraries").exists())
            result = report(bundle / "guidance")
            self.assertEqual(result["totals"], {"skills": 2, "protocols": 1, "embedded_skills": 1, "source_only_skills": 0})
            for name in ("example", "old-example", "embedded-example", "protocol-example", "example-workflow"):
                self.assertTrue(report(bundle / "guidance", name=name)["entries"][0]["content"])

    def test_canonical_source_not_generated_catalogue_owns_metadata(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            core = self.make_workspace(root)
            expected = package_native.native_catalogue(root)
            (core / "skills/catalogue.json").write_text("not JSON", encoding="utf-8")
            (core / "protocols/catalogue.json").write_text("not JSON", encoding="utf-8")
            self.assertEqual(expected, package_native.native_catalogue(root))

    def test_malformed_canonical_plugin_metadata_refuses_without_writes(self):
        variants = (None, [], {"name": 42, "version": "1.0.0"},
                    {"name": "", "version": "1.0.0"}, {"name": "../example", "version": "1.0.0"},
                    {"name": "example", "version": 42}, {"name": "example", "version": ""})
        for plugin in variants:
            with self.subTest(plugin=plugin), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                self.make_workspace(root)
                source = root / "libraries/capabilities.json"
                document = json.loads(source.read_text())
                document["plugin"] = plugin
                source.write_text(json.dumps(document), encoding="utf-8")
                before = {path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()}
                for check in (True, False):
                    with self.assertRaisesRegex(ValueError, "plugin"):
                        package_native.materialize(root, check=check)
                    self.assertEqual(before, {path.relative_to(root): path.read_bytes()
                                              for path in root.rglob("*") if path.is_file()})

    def test_malformed_generated_plugin_refuses_without_repairing_bytes(self):
        for external in (False, True):
            for malformed in ('{"name": 42, "version": "1.0.0"}\n', '{"name":\n'):
                with self.subTest(external=external, malformed=malformed), tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary) / "workspace"
                    core = self.make_workspace(root)
                    output = Path(temporary) / "export" if external else None
                    package_native.materialize(root, plugin_output=output)
                    ((output or core) / "plugin.json").write_text(malformed, encoding="utf-8")
                    before = {path: path.read_bytes() for path in Path(temporary).rglob("*") if path.is_file()}
                    for check in (True, False):
                        with self.assertRaisesRegex(ValueError, "Generated file was edited"):
                            package_native.materialize(root, check=check, plugin_output=output)
                        self.assertEqual(before, {path: path.read_bytes()
                                                  for path in Path(temporary).rglob("*") if path.is_file()})

    def test_real_portable_products_have_no_missing_or_escaping_local_targets(self):
        products = package_native.build_products(TOOL.parents[2])
        checked = 0
        for relative, text in products.items():
            if not relative.startswith(".github/com.github.copilot/") or not relative.endswith(".md"):
                continue

            def check(target, line):
                nonlocal checked
                parsed = urlsplit(target)
                if not parsed.scheme and parsed.path and not target.startswith("//"):
                    checked += 1
                    resolved = posixpath.normpath(posixpath.join(posixpath.dirname(relative), unquote(parsed.path)))
                    self.assertTrue(resolved.startswith(".github/com.github.copilot/"), (relative, line, target))
                    self.assertIn(resolved, products, (relative, line, target))
                return target, None

            package_native.rewrite_links(text, check)
        self.assertGreater(checked, 0)
        self.assertFalse(any("/references/.github/" in relative for relative in products))
        self.assertFalse(any("/references/harness/com.github.copilot/" in relative
                             or "/references/libraries/framework/src/agentcraft/guidance/" in relative
                             for relative in products))

    def test_implemented_mcp_stays_disabled_and_exposes_only_explicit_offline_opt_in(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_mcp_workspace(root)
            products = package_native.build_products(root)
            for relative in (".github/mcp.json", ".github/com.github.copilot/mcp.json",
                             ".github/com.github.copilot/guidance/mcp.json"):
                self.assertEqual({}, json.loads(products[relative])["mcpServers"])
            snapshot = json.loads(products[package_native.PACKAGE + "/capabilities.json"])
            self.assertEqual("implemented", snapshot["mcp"]["status"])
            self.assertEqual("conditional", snapshot["mcp"]["targets"][0]["availability"])
            self.assertIn("`agentcraft mcp --offline`", products[".github/skills/README.md"])
            self.assertIn("Registrations: 0; disabled by default", products[".github/skills/README.md"])
            self.assertTrue(package_native.materialize(root))
            self.assertEqual([], package_native.materialize(root, check=True))

    def test_mcp_command_target_grants_and_source_escalation_refuse(self):
        changes = (
            lambda document: document["mcp"].update(status="pending"),
            lambda document: document["mcp"].update(activation="enabled"),
            lambda document: document["mcp"].update(registered_servers=["agentcraft"]),
            lambda document: document["mcp"].update(grants={"model": ["model_chat"]}),
            lambda document: document["mcp"].update(bindings={"model": "live"}),
            lambda document: document["mcp"].update(source="libraries/example/README.md"),
            lambda document: document["mcp"]["default_request"].update(command="/tmp/agentcraft"),
            lambda document: document["mcp"]["default_request"].update(command="python"),
            lambda document: document["mcp"]["default_request"].update(args=["mcp"]),
            lambda document: document["mcp"]["default_request"]["args"].extend(["--config", "live.json"]),
            lambda document: document["mcp"]["default_request"].update(env={"TOKEN": "synthetic"}),
            lambda document: document["mcp"]["default_request"].update(grants={"model": ["model_chat"]}),
            lambda document: document["mcp"]["default_request"]["capabilities"].append("llm-interface"),
            lambda document: document["mcp"]["targets"][0].update(name="administration"),
            lambda document: document["mcp"]["targets"][0].update(capability="example"),
            lambda document: document["mcp"]["targets"][0].update(source="libraries/example/README.md"),
            lambda document: document["mcp"]["targets"][0]["tools"].append("composition_execute"),
            lambda document: document["mcp"]["targets"][0].update(grants=["composition_demo"]),
            lambda document: document["mcp"]["targets"][0].update(availability="available"),
            lambda document: document["mcp"]["targets"][0].update(verification="not-run"),
            lambda document: document["mcp"]["legacy_tools"].update(old="missing_tool"),
            lambda document: document["mcp"]["targets"].append(document["mcp"]["targets"][0].copy()),
            lambda document: document["skills"][0].update(mcp_target="missing"),
        )
        for change in changes:
            with self.subTest(change=change), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                self.make_mcp_workspace(root)
                path = root / "libraries/capabilities.json"
                document = json.loads(path.read_text())
                change(document)
                path.write_text(json.dumps(document), encoding="utf-8")
                with self.assertRaises(ValueError):
                    package_native.materialize(root)
                self.assertFalse((root / ".github/native-manifest.json").exists())

    def test_changed_or_missing_adapter_schema_cannot_claim_implementation(self):
        for content in ("TOOLS = []\n", "TOOLS = factory()\n", "TOOLS = [types.Tool(name='old_tool')]\n", None):
            with self.subTest(content=content), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                self.make_mcp_workspace(root)
                source = root / "libraries/app-composition/appcompose/mcp.py"
                if content is None:
                    source.unlink()
                else:
                    source.write_text(content, encoding="utf-8")
                with self.assertRaises(ValueError):
                    package_native.materialize(root)

    def test_real_catalogue_matches_current_native_schemas_and_examples(self):
        document = package_native.catalogue_source(TOOL.parents[2])
        self.assertEqual("implemented", document["mcp"]["status"])
        self.assertEqual("offline-verified", document["mcp"]["verification"])
        self.assertEqual([], document["mcp"]["registered_servers"])
        self.assertEqual(15, sum(len(target["tools"]) for target in document["mcp"]["targets"]))
        self.assertEqual(27, len(document["mcp"]["legacy_tools"]))
        self.assertTrue(all(target["availability"] == "conditional" for target in document["mcp"]["targets"]))
        framework = next(entry for entry in document["capabilities"] if entry["id"] == "framework")
        self.assertEqual("implemented", framework["status"])
        self.assertIn("libraries/framework/src/agentcraft/examples.py", framework["examples"])
        self.assertIn("libraries/framework/CONFORMANCE.md", framework["docs"])
        recipe = next(entry for entry in document["capabilities"] if entry["id"] == "content-understanding")
        self.assertEqual("native-sdk-recipe", recipe["status"])
        self.assertEqual([], recipe["distributions"])
        model_skill = next(entry for entry in document["skills"] if entry["name"] == "azure-llm-connectors")
        self.assertIn("managed-identity-model-clients", model_skill["aliases"])
        self.assertNotIn("managed-identity-model-clients", {entry["name"] for entry in document["skills"]})

    def test_authoring_skills_are_not_runtime_libraries(self):
        root = TOOL.parents[2]
        document = package_native.catalogue_source(root)
        identifiers = {entry["id"] for entry in document["capabilities"]}
        for name, former_library in (("azure-sky-styling", "azure-sky-styling"),
                                     ("hyperframes-motion", "hyperframes-tools")):
            with self.subTest(skill=name):
                skill = next(entry for entry in document["skills"] if entry["name"] == name)
                self.assertNotIn(former_library, identifiers)
                self.assertEqual("skill-only", skill["status"])
                self.assertEqual([], skill["capabilities"])
                self.assertEqual(f".github/skills/{name}/GUIDE.md", skill["guidance"])
                self.assertTrue((root / f".github/skills/{name}/package.json").is_file())
                self.assertFalse((root / "libraries" / former_library).exists())

    def test_skill_only_membership_refuses_runtime_dependencies(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_workspace(root)
            path = root / "libraries/capabilities.json"
            document = json.loads(path.read_text())
            document["skills"][0]["status"] = "skill-only"
            path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Skill-only"):
                package_native.materialize(root)
            self.assertFalse((root / ".github/native-manifest.json").exists())
            document["skills"][0]["capabilities"] = []
            path.write_text(json.dumps(document), encoding="utf-8")
            self.assertTrue(package_native.build_products(root))

    def test_deep_links_notices_and_omissions_are_honest(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            core = self.make_workspace(root)
            library = root / "libraries/example"
            (library / "README.md").write_text(
                "# Example\n[`Contract`](CONTRACT.md)\n[Multiline\ncontract](CONTRACT.md)\n[Code](runtime.py)\n[Receipt](records/missing.md)\n"
                "[Missing](absent.md)\n[Notice][rights]\n\n[rights]: NOTICE.txt\n"
                "`[literal](not-a-link.md)`\n```md\n[code](also-not-a-link.md)\n```\n", encoding="utf-8")
            (library / "CONTRACT.md").write_text("# Contract\n[Back](README.md)\n", encoding="utf-8")
            (library / "NOTICE.txt").write_text("Actual notice.\n", encoding="utf-8")
            (library / "runtime.py").write_text("raise RuntimeError('must not execute or ship')\n", encoding="utf-8")
            package_native.materialize(root)
            guidance = root / package_native.PACKAGE / "guidance"
            self.assertEqual("Actual notice.\n", (guidance / "references/libraries/example/NOTICE.txt").read_text())
            rendered = (guidance / "references/libraries/example/README.md").read_text()
            self.assertIn("[`Contract`](CONTRACT.md)", rendered)
            self.assertIn("[Multiline\ncontract](CONTRACT.md)", rendered)
            native_agent = (core / "agents/example.agent.md")
            native_agent.write_text("[`Contract`](../../libraries/example/CONTRACT.md)\n", encoding="utf-8")
            products = package_native.native_files(root)
            self.assertIn("[`Contract`](../guidance/references/libraries/example/CONTRACT.md)",
                          products["com.github.copilot/agents/example.agent.md"])
            evidence = json.loads((guidance / "provenance.json").read_text())
            self.assertEqual({entry["classification"] for entry in evidence["omissions"]},
                             {"source-or-asset-not-bundled", "historical-not-advertised", "missing-not-advertised"})
            receipt = next(entry for entry in evidence["omissions"] if entry["target"] == "records/missing.md")
            self.assertFalse(receipt["exists"])
            self.assertFalse(list(guidance.rglob("*.py")))
            self.assertEqual(3, len(evidence["omissions"]))

    def test_outside_guidance_link_is_omitted_without_filesystem_resolution(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_workspace(root)
            (root / "libraries/example/README.md").write_text(
                "[Outside](../../private-outside-guidance/README.md)\n", encoding="utf-8")
            original = Path.resolve

            def guarded_resolve(path, *arguments, **keywords):
                self.assertNotIn("private-outside-guidance", path.parts)
                return original(path, *arguments, **keywords)

            with patch.object(Path, "resolve", guarded_resolve):
                products = package_native.build_products(root)
            evidence = json.loads(products[".github/com.github.copilot/guidance/provenance.json"])
            self.assertEqual(1, len(evidence["omissions"]))
            self.assertEqual("outside-guidance-not-advertised", evidence["omissions"][0]["classification"])
            self.assertEqual("private-outside-guidance/README.md", evidence["omissions"][0]["resolved_source"])
            self.assertIsNone(evidence["omissions"][0]["exists"])

    def test_unknown_alias_dependency_and_active_mcp_refuse(self):
        changes = (
            lambda document: document["skills"][0]["aliases"].append("protocol-example"),
            lambda document: document["capabilities"][0]["dependencies"].append("missing"),
            lambda document: document["mcp"]["registered_servers"].append("legacy"),
            lambda document: document["skills"][0].update(mcp={"server": "missing"}),
        )
        for change in changes:
            with self.subTest(change=change), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                self.make_workspace(root)
                path = root / "libraries/capabilities.json"
                document = json.loads(path.read_text())
                change(document)
                path.write_text(json.dumps(document), encoding="utf-8")
                with self.assertRaises(ValueError):
                    package_native.materialize(root)
                self.assertFalse((root / ".github/native-manifest.json").exists())

    def test_stale_guidance_detected_and_edited_generated_file_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            core = self.make_workspace(root)
            package_native.materialize(root)
            source = root / "libraries/example/README.md"
            source.write_text("# Changed canonical guidance\n", encoding="utf-8")
            self.assertTrue(package_native.materialize(root, check=True))
            package_native.materialize(root)
            generated = root / package_native.PACKAGE / "guidance/references/libraries/example/README.md"
            generated.write_text("user edit", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Generated file was edited"):
                package_native.materialize(root)
            self.assertEqual("user edit", generated.read_text())
            with self.assertRaisesRegex(ValueError, "Native package projection changed"):
                report(root / package_native.PACKAGE / "guidance")

    def test_canonical_source_pointers_must_exist(self):
        missing = "libraries/example/missing.md"
        changes = (
            lambda document: document["skills"][0].update(source=missing),
            lambda document: document["skills"][0].update(guidance=missing),
            lambda document: document["skills"][0]["components"][0].update(guidance=missing),
            lambda document: document["capabilities"][0]["source_paths"].append(missing),
            lambda document: document["capabilities"][0]["docs"].append(missing),
            lambda document: document["capabilities"][0]["examples"].append(missing),
            lambda document: document["capabilities"][0]["checks"]["paths"].append(missing),
            lambda document: document["guidance"]["roots"].append(missing),
            lambda document: document["guidance"]["notices"].append(missing),
            lambda document: document["guidance"]["redirects"].update({"old.md": missing}),
        )
        for change in changes:
            with self.subTest(change=change), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                self.make_workspace(root)
                path = root / "libraries/capabilities.json"
                document = json.loads(path.read_text())
                change(document)
                path.write_text(json.dumps(document), encoding="utf-8")
                with self.assertRaises((ValueError, FileNotFoundError)):
                    package_native.materialize(root)
                self.assertFalse((root / ".github/native-manifest.json").exists())

    def test_retirement_checks_hash_and_preserves_edited_files(self):
        for edited in (False, True):
            with self.subTest(edited=edited), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                core = self.make_workspace(root)
                relative = "com.github.copilot/agents/retired.agent.md"
                retired = core / relative
                retired.parent.mkdir(parents=True)
                retired.write_text("original", encoding="utf-8")
                manifest = {"schema_version": 1, "files": {relative: hashlib.sha256(retired.read_bytes()).hexdigest()}}
                (core / "native-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
                if edited:
                    retired.write_text("user edit", encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, "Retired native file was edited"):
                        package_native.materialize(root)
                    self.assertEqual("user edit", retired.read_text())
                else:
                    self.assertIn(".github/" + relative, package_native.materialize(root, check=True))
                    self.assertTrue(retired.is_file())
                    self.assertIn(".github/" + relative, package_native.materialize(root))
                    self.assertFalse(retired.exists())
                    self.assertFalse((core / package_native.PORTABLE).exists())

    def test_unowned_legacy_portable_file_blocks_all_writes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            core = self.make_workspace(root)
            unknown = core / package_native.PORTABLE / "personal.md"
            unknown.parent.mkdir()
            unknown.write_text("keep", encoding="utf-8")
            before = {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}
            for check in (True, False):
                with self.assertRaisesRegex(ValueError, "Unowned portable path"):
                    package_native.materialize(root, check=check)
                self.assertEqual(before, {path: path.read_bytes() for path in root.rglob("*") if path.is_file()})

    def test_external_output_refuses_workspace_relative_and_symlink_roots(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "workspace"
            self.make_workspace(root)
            outside = Path(temporary) / "outside"
            outside.mkdir()
            link = Path(temporary) / "link"
            link.symlink_to(outside, target_is_directory=True)
            for output in (root, root / "export", root.parent, Path("relative"), link, link / "nested"):
                with self.subTest(output=output), self.assertRaisesRegex(ValueError, "absolute external directory"):
                    package_native.materialize(root, plugin_output=output)
            self.assertEqual([], list(outside.iterdir()))

    def test_external_output_refuses_changed_symlink_and_preserves_unknown_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "workspace"
            self.make_workspace(root)
            output = Path(temporary) / "export"
            output.mkdir()
            unknown = output / "personal.md"
            unknown.write_text("keep", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "complete generated export"):
                package_native.materialize(root, plugin_output=output)
            self.assertEqual("keep", unknown.read_text())
            changed = Path(temporary) / "changed"
            build = package_native.build_products

            def replace_output(source):
                products = build(source)
                changed.symlink_to(output, target_is_directory=True)
                return products

            with patch.object(package_native, "build_products", side_effect=replace_output):
                with self.assertRaises(ValueError):
                    package_native.materialize(root, plugin_output=changed)
            self.assertEqual([unknown], list(output.iterdir()))

    def test_external_output_refuses_edited_manifest_missing_files_and_nested_symlink(self):
        for mutation in ("manifest", "missing", "symlink"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary) / "workspace"
                self.make_workspace(root)
                output = Path(temporary) / "export"
                package_native.materialize(root, plugin_output=output)
                if mutation == "manifest":
                    manifest = output / "native-manifest.json"
                    manifest.write_text(manifest.read_text() + "\n", encoding="utf-8")
                elif mutation == "missing":
                    (output / "README.md").unlink()
                else:
                    (output / "extra").symlink_to(root, target_is_directory=True)
                before = {path: path.read_bytes() for path in output.rglob("*") if path.is_file()}
                for check in (True, False):
                    with self.assertRaises(ValueError):
                        package_native.materialize(root, check=check, plugin_output=output)
                    self.assertEqual(before, {path: path.read_bytes() for path in output.rglob("*") if path.is_file()})

    def test_materialize_refuses_escaping_output_symlink(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "workspace"
            core = self.make_workspace(root)
            outside = Path(temporary) / "outside"
            outside.mkdir()
            (core / "com.github.copilot").symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "Refusing escaped generated target"):
                package_native.materialize(root)
            self.assertEqual([], list(outside.iterdir()))


if __name__ == "__main__":
    unittest.main()