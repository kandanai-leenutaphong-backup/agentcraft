import hashlib
import importlib.util
import json
from pathlib import Path
import stat
import sys
import tempfile
import unittest
import zipfile


SPEC = importlib.util.spec_from_file_location("optimization_skillpack", Path(__file__).resolve().parents[1] / "scripts/skillpack.py")
skillpack = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(skillpack)
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build_snapshot


class SkillpackTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="optimization-pack-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.pack = self.root / "pack"
        (self.pack / "assets").mkdir(parents=True)

    def bundle(self, files=None, *, kind=stat.S_IFREG, bad_hash=False, duplicate=False):
        files = files or {"runtime/app/example.py": b"value = 1\n"}
        payload = self.pack / skillpack.PAYLOAD
        with zipfile.ZipFile(payload, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, content in files.items():
                member = zipfile.ZipInfo(name)
                member.external_attr = (kind | 0o600) << 16
                archive.writestr(member, content)
        entries = [{"path": name, "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()} for name, content in files.items()]
        if bad_hash:
            entries[0]["sha256"] = "0" * 64
        if duplicate:
            entries.append(entries[0])
        manifest = {"format": skillpack.FORMAT,
                    "payload": {"path": skillpack.PAYLOAD, "sha256": skillpack.file_digest(payload)}, "files": entries}
        (self.pack / "manifest.json").write_text(json.dumps(manifest))
        return payload

    def test_verify_extract_and_refuse_existing_destination(self):
        self.bundle()
        self.assertEqual(len(skillpack.verify(self.pack)["files"]), 1)
        destination = self.root / "extracted"
        self.assertEqual(skillpack.extract(destination, self.pack)["status"], "extracted")
        self.assertEqual((destination / "runtime/app/example.py").read_bytes(), b"value = 1\n")
        with self.assertRaisesRegex(ValueError, "already exists"):
            skillpack.extract(destination, self.pack)

    def test_tampered_payload_refused_before_extraction(self):
        payload = self.bundle()
        with payload.open("ab") as stream:
            stream.write(b"changed")
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            skillpack.extract(self.root / "absent", self.pack)
        self.assertFalse((self.root / "absent").exists())

    def test_file_hash_and_duplicate_inventory_refused(self):
        self.bundle(bad_hash=True)
        with self.assertRaisesRegex(ValueError, "file hash"):
            skillpack.verify(self.pack)
        self.bundle(duplicate=True)
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            skillpack.verify(self.pack)

    def test_traversal_and_unsupported_roots_refused(self):
        for name in ("/absolute", "runtime/../outside", "runtime//empty", "C:/outside", "runtime\\file",
                     "other/file", "case-study/versions/1.json", "reference-host/app/backend.py"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                skillpack.safe_path(name)

    def test_links_and_symlinked_destination_refused(self):
        self.bundle(kind=stat.S_IFLNK)
        with self.assertRaisesRegex(ValueError, "regular files"):
            skillpack.verify(self.pack)
        self.bundle()
        (self.root / "link").symlink_to(self.pack, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symbolic"):
            skillpack.extract(self.root / "link/extracted", self.pack)

    def source_fixture(self):
        source = self.root / "source"
        for path, content in {
            "python/agent_optimization/__init__.py": "VALUE = 1\n",
            "python/agent_optimization/__pycache__/ignored.pyc": "cache",
            "python/agent_optimization/node_modules/ignored.js": "dependency",
            "assets/example/campaign-summary.json": "{}",
            "pyproject.toml": "[project]\n",
        }.items():
            target = source / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
        selection = {"format": build_snapshot.SELECTION_FORMAT, "version": "2.0.0",
                     "basis": "fixture sources",
                     "trees": [{"path": "python/agent_optimization", "destination": "runtime/agent_optimization", "role": "runtime"},
                               {"path": "assets/example", "destination": "example", "role": "synthetic example"}],
                     "mapped_files": [{"source": "pyproject.toml", "destination": "runtime/pyproject.toml", "role": "manifest"}],
                     "excluded": []}
        (self.pack / "assets/sources.json").write_text(json.dumps(selection))
        return source, selection

    def test_builder_copies_selected_bytes_without_touching_source_and_is_reproducible(self):
        source, _ = self.source_fixture()
        original = (source / "python/agent_optimization/__init__.py").read_bytes()
        first = build_snapshot.build(source, pack=self.pack)
        manifest = skillpack.verify(self.pack)
        self.assertEqual(first["files"], 3)
        self.assertEqual({item["path"] for item in manifest["files"]},
                         {"runtime/agent_optimization/__init__.py", "runtime/pyproject.toml",
                          "example/campaign-summary.json"})
        self.assertEqual((source / "python/agent_optimization/__init__.py").read_bytes(), original)
        with self.assertRaisesRegex(ValueError, "already exists"):
            build_snapshot.build(source, pack=self.pack)
        second = build_snapshot.build(source, replace=True, pack=self.pack)
        self.assertEqual(first["sha256"], second["sha256"])

    def test_builder_refuses_credential_files_and_source_escape(self):
        source, selection = self.source_fixture()
        (source / "python/agent_optimization/.env").write_text("fixture only")
        with self.assertRaisesRegex(ValueError, "credential-shaped"):
            build_snapshot.collect(source, selection)
        with self.assertRaisesRegex(ValueError, "Unsafe"):
            build_snapshot.source_file(source, "../outside.txt")

    def test_shipped_pack_is_first_party_and_free_of_host_roots(self):
        pack = Path(__file__).resolve().parents[1]
        manifest = skillpack.verify(pack)
        roots = {entry["path"].split("/")[0] for entry in manifest["files"]}
        self.assertEqual(roots, {"runtime", "example"})
        self.assertNotIn("git_revision", manifest["source"])
        with zipfile.ZipFile(pack / skillpack.PAYLOAD) as archive:
            self.assertEqual(archive.read("runtime/LICENSE"), (pack / "LICENSE").read_bytes())

    def test_frontend_check_declares_the_real_package_peers(self):
        pack = Path(__file__).resolve().parents[1]
        component = json.loads((pack / "package.json").read_text())
        check = json.loads((pack / "assets/frontend-check.package.json").read_text())
        self.assertEqual(check["peerDependencies"], component["peerDependencies"])


if __name__ == "__main__":
    unittest.main()