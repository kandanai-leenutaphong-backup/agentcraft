import json
import os
from pathlib import Path
import tempfile
import unittest

from foundry_ops.core import EvidenceLedger, RefusedError, load_run_manifest, series_directory, sha256_hex


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.env = self.root / "env"
        self.env.mkdir()
        self.target = self.env / "target.json"
        self.target.write_text('{"project": "p"}')
        self.constitution = self.root / "constitution.yaml"
        self.constitution.write_text("rules: []\n")
        self.value = {"schema_version": 1, "purpose": "migration-development", "actions": ["deploy", "invoke"],
                      "series": "migration-h-v2", "agent": "agentcraft-migration-h-v2",
                      "target_sha256": sha256_hex(self.target.read_bytes()),
                      "constitution": {"path": "constitution.yaml", "sha256": sha256_hex(self.constitution.read_bytes())}}

    def tearDown(self):
        self.temp.cleanup()

    def write(self, value=None, name="run.json"):
        path = self.env / name
        path.write_text(json.dumps(value or self.value))
        return path, sha256_hex(path.read_bytes())

    def load(self, path, digest, **kwargs):
        kwargs.setdefault("action", "deploy")
        kwargs.setdefault("pins", {"target_sha256": self.target, "constitution.sha256": self.constitution})
        return load_run_manifest(path, expected_sha256=digest, allowed_root=self.env, **kwargs)

    def test_valid_manifest_binds_once(self):
        path, digest = self.write()
        manifest = self.load(path, digest)
        self.assertEqual((manifest.series, manifest.agent, manifest.sha256), ("migration-h-v2", "agentcraft-migration-h-v2", digest))
        (self.root / "records").mkdir()
        ledger = EvidenceLedger(series_directory(self.root / "records", manifest.series))
        manifest.bind(ledger)
        manifest.bind(ledger)
        other_path, other_digest = self.write(dict(self.value, actions=["deploy"]), "other.json")
        with self.assertRaises(RefusedError):
            self.load(other_path, other_digest).bind(ledger)

    def assertCode(self, code, path, digest, **kwargs):
        with self.assertRaises(RefusedError) as caught:
            self.load(path, digest, **kwargs)
        self.assertEqual(caught.exception.code, code)

    def test_digest_mismatch_refused(self):
        path, _ = self.write()
        self.assertCode("manifest_digest", path, "0" * 64)

    def test_disallowed_action_refused(self):
        path, digest = self.write()
        self.assertCode("manifest_action", path, digest, action="teardown")

    def test_outside_root_refused(self):
        outside = self.root / "run.json"
        outside.write_text(json.dumps(self.value))
        self.assertCode("manifest_path", outside, sha256_hex(outside.read_bytes()))
        link = self.env / "link.json"
        os.symlink(outside, link)
        self.assertCode("manifest_path", link, sha256_hex(outside.read_bytes()))

    def test_schema_purpose_series_agent_pin_refused(self):
        for code, change in (("manifest_schema", {"schema_version": 2}), ("manifest_purpose", {"purpose": "production"}),
                             ("manifest_series", {"series": "../escape"}), ("manifest_agent", {"agent": "agentcraft-hosted-tool-proof"}),
                             ("manifest_pin", {"target_sha256": "0" * 64})):
            path, digest = self.write(dict(self.value, **change), code + ".json")
            self.assertCode(code, path, digest)
        path, digest = self.write()
        self.assertCode("manifest_agent", path, digest, forbidden_agents=frozenset({"agentcraft-migration-h-v2"}))
        self.constitution.write_text("rules: [changed]\n")
        self.assertCode("manifest_pin", path, digest)

    def test_agent_check_optional(self):
        path, digest = self.write({k: v for k, v in self.value.items() if k != "agent"})
        self.assertIsNone(self.load(path, digest, agent_pattern=None).agent)

    def test_series_directory_refuses_symlink(self):
        base = self.root / "records"
        base.mkdir()
        os.symlink(self.root, base / "migration-x")
        with self.assertRaises(RefusedError):
            series_directory(base, "migration-x")
        with self.assertRaises(RefusedError):
            series_directory(base, "../x")


if __name__ == "__main__":
    unittest.main()
