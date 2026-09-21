import contextlib
import io
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from deploy import cloud


class CloudFeasibilityTests(unittest.TestCase):
    def test_plan_records_authority_limits_and_no_eligible_mutations(self):
        result = cloud.plan()
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["authority"]["eligible_mutations"], [])
        self.assertEqual(result["limits"]["max_replicas"], 1)
        self.assertEqual(result["limits"]["verification_model_calls"], 10)
        self.assertFalse(result["limits"]["model_calls_enabled"])
        self.assertTrue(all(item["exists"] for item in result["source_inputs"]))

    def test_actions_never_invoke_a_process_and_mutations_refuse(self):
        for action in ("plan", "preflight", "apply", "verify", "teardown"):
            with self.subTest(action=action), patch("subprocess.run") as process:
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    code = cloud.main([action])
                self.assertEqual(code, 0 if action == "plan" else 2)
                self.assertEqual(json.loads(output.getvalue())["cloud_mutations"], [])
                process.assert_not_called()

    def test_unknown_arguments_cannot_bypass_preflight(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            cloud.main(["apply", "--force"])
        self.assertEqual(error.exception.code, 2)

    def test_package_excludes_state_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary)
            root = repository / "template_apps/investigation_app"
            for relative in cloud.SOURCE_FILES:
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("synthetic source", encoding="utf-8")
            for library in cloud.LIBRARIES[:8]:
                path = repository / "libraries" / library / "pyproject.toml"
                path.parent.mkdir(parents=True)
                path.write_text("synthetic metadata", encoding="utf-8")
            shared = repository / "template_apps/shared"
            shared.mkdir(parents=True)
            (shared / "pyproject.toml").write_text("synthetic metadata", encoding="utf-8")
            backend = root / "app/cybereye/backend"
            (backend / "data").mkdir()
            (backend / "data/adx.py").write_text("synthetic adapter", encoding="utf-8")
            (backend / ".env").write_text("must not package", encoding="utf-8")
            (backend / "profiles.sqlite3").write_text("must not package", encoding="utf-8")
            (backend / ".local").mkdir()
            (backend / ".local/state.json").write_text("must not package", encoding="utf-8")
            output = root / "deploy/packages/candidate.tar"
            result = cloud.package(output, repository=repository)
            self.assertFalse(result["deployable"])
            with tarfile.open(output) as archive:
                names = archive.getnames()
                self.assertIn("source-manifest.json", names)
                self.assertIn("template_apps/investigation_app/app/cybereye/backend/data/adx.py", names)
                self.assertFalse(any(".env" in name or ".local" in name or ".sqlite3" in name for name in names))
            with self.assertRaises(FileExistsError):
                cloud.package(output, repository=repository)
            (backend / "escape.py").symlink_to(repository / "libraries")
            with self.assertRaisesRegex(ValueError, "symlink"):
                cloud.package_inputs(repository)

    def test_package_refuses_outside_owned_destination(self):
        with self.assertRaisesRegex(ValueError, "deploy/packages"):
            cloud.package(Path("/tmp/unsafe.tar"))

    def test_target_refuses_unknown_duplicate_or_foreign_fields(self):
        original = cloud.load_target(cloud.ROOT / cloud.TARGET_FILE)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "target.json"
            for change in ({"unexpected": "value"}, {"tenant_id": "foreign"}, {"identity": "shared"}):
                path.write_text(json.dumps({**original, **change}), encoding="utf-8")
                with self.subTest(change=change), self.assertRaises(ValueError):
                    cloud.load_target(path)
            path.write_text('{"cloud":"AzureCloud","cloud":"AzureCloud"}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate"):
                cloud.load_target(path)

    def test_owner_entry_routes_cloud_without_local_launcher(self):
        entry = Path(cloud.__file__).with_name("deploy.sh")
        result = subprocess.run(["bash", str(entry), "cloud", "preflight"],
                                capture_output=True, text=True, timeout=10,
                                env={"PATH": "/usr/bin:/bin", "LIVE_PYTHON": "/usr/bin/python3"})
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "blocked")


if __name__ == "__main__":
    unittest.main()