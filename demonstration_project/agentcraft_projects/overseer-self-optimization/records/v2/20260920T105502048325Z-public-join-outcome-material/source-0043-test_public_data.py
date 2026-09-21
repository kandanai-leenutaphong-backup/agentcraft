"""Synthetic structural fixtures; no upstream payload or network."""

import importlib.util
import io
import json
from pathlib import Path
import stat
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import zipfile


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("public_data", ROOT / "template_apps/investigation_app/deploy/public_data.py")
public_data = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(public_data)


class AcquisitionTests(unittest.TestCase):
    def test_paths(self):
        for name in ("../escape", "/absolute", "dir/../../escape", "a\\b", "C:drive", "bad\x00"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                public_data.safe_path(Path("/tmp/bounded"), name)

    def test_immutable(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "item"
            public_data.retain(target, b"data")
            public_data.retain(target, b"data")
            with self.assertRaises(ValueError):
                public_data.retain(target, b"different")
            link = Path(directory) / "link"
            link.symlink_to(target)
            with self.assertRaises(ValueError):
                public_data.safe_path(Path(directory), "link")

    def test_archive(self):
        for name in ("../bad.json", "run.exe", "C:/bad.txt"):
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w") as archive:
                archive.writestr(name, b"data")
            with self.assertRaises(ValueError):
                public_data.archive_members(buffer.getvalue())
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("data.json", b"{}")
        self.assertEqual(public_data.archive_members(buffer.getvalue()), {"data.json": b"{}"})
        with self.assertRaises(ValueError):
            public_data.archive_members(buffer.getvalue(), max_bytes=1)
        with self.assertRaises(ValueError):
            public_data.archive_members(buffer.getvalue(), max_members=0)

    def test_rights_and_urls(self):
        public_data.source_url("https://media.githubusercontent.com/media/splunk/attack_data/commit/data.log")
        for source in ({}, {"license": "MIT"}, {"license": "Apache-2.0", "rights_review": "unknown"}):
            with self.assertRaises(ValueError):
                public_data.rights(source)
        for url in ("http://127.0.0.1/a", "https://other.example/a", "https://api.github.com/repos/private/data/contents", "https://user:secret@raw.githubusercontent.com/splunk/attack_data/master/LICENSE", "https://raw.githubusercontent.com/splunk/attack_data/%2e%2e/other"):
            with self.assertRaises(ValueError):
                public_data.source_url(url)

    def test_archive_special_duplicate_and_expansion(self):
        for case in ("symlink", "duplicate", "expansion"):
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                if case == "symlink":
                    item = zipfile.ZipInfo("link.txt")
                    item.external_attr = (stat.S_IFLNK | 0o777) << 16
                    archive.writestr(item, "target")
                elif case == "duplicate":
                    archive.writestr("data.txt", "one")
                    with self.assertWarns(UserWarning):
                        archive.writestr("data.txt", "two")
                else:
                    archive.writestr("data.txt", "x" * 100000)
            with self.subTest(case=case), self.assertRaises(ValueError):
                public_data.archive_members(buffer.getvalue())

    def test_cached_skip_and_tamper(self):
        url = "https://raw.githubusercontent.com/splunk/attack_data/commit/LICENSE"
        payload = b"synthetic"
        expected = public_data.sha256(payload)
        with tempfile.TemporaryDirectory() as directory, patch.object(public_data, "DATA", Path(directory)):
            public_data.retain(Path(directory) / "item", payload)
            public_data.retain(Path(directory) / "item.provenance.json", public_data.encoded({"source_url": url, "sha256": expected}))
            with patch.dict(sys.modules, {"webres": None}):
                result = public_data.acquire(url, "item", maximum=len(payload), expected=expected)
                self.assertEqual(result["cache"], "verified-skip")
            with self.assertRaises(ValueError):
                public_data.acquire(url, "item", maximum=len(payload) - 1, expected=expected)
            with self.assertRaises(ValueError):
                public_data.acquire(url, "item", maximum=len(payload), expected="0" * 64)

    def test_download_size_and_digest_refusal(self):
        url = "https://raw.githubusercontent.com/splunk/attack_data/commit/LICENSE"
        for maximum, expected in ((1, None), (10, "0" * 64)):
            response = Mock()
            response.__enter__ = Mock(return_value=response)
            response.__exit__ = Mock(return_value=False)
            response.status = 200
            response.read.return_value = b"data"
            fake = SimpleNamespace(Provenance=Mock(), open_public=Mock(return_value=response))
            with tempfile.TemporaryDirectory() as directory, patch.object(public_data, "DATA", Path(directory)), patch.dict(sys.modules, {"webres": fake}):
                with self.assertRaises(ValueError):
                    public_data.acquire(url, "item", maximum=maximum, expected=expected)
                self.assertFalse((Path(directory) / "item").exists())

    def test_lock_rights_refusal(self):
        original = json.loads(public_data.LOCK.read_text())
        for change in ("rights", "license", "revision"):
            broken = json.loads(json.dumps(original))
            if change == "rights":
                broken["sources"][0]["rights_review"] = "unresolved"
            elif change == "license":
                broken["sources"][0]["license_sha256"] = "0" * 64
            else:
                broken["sources"][0]["commit"] = "b" * 40
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "lock.json"
                public_data.retain(path, public_data.encoded(broken))
                with patch.object(public_data, "LOCK", path), self.assertRaises(ValueError):
                    public_data.load_lock()


if __name__ == "__main__":
    unittest.main()