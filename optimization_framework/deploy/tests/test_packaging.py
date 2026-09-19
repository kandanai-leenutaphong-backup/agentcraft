import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
import unittest


ENTRY = Path(__file__).resolve().parents[1] / "deploy.sh"


class PackagingTests(unittest.TestCase):
    def invoke(self, *arguments, cwd=None):
        return subprocess.run(["bash", str(ENTRY), *map(str, arguments)], cwd=cwd,
                              capture_output=True, timeout=60)

    def test_portable_install_readback_repeat_and_conflict(self):
        with tempfile.TemporaryDirectory(prefix="optimization-skill-") as temporary:
            target = Path(temporary) / "project with spaces"
            result = self.invoke("install-skill", "--client", "vscode", "--target", target, cwd=temporary)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            installed = target / ".github/skills/optimization-experiment"
            manifest = json.loads((installed / "bundle.json").read_text())
            for relative, expected in manifest["files"].items():
                self.assertEqual(hashlib.sha256((installed / relative).read_bytes()).hexdigest(), expected)
            primary = installed / "framework/skills/optimization-experiment/SKILL.md"
            for reference in re.findall(r"\]\(([^)]+)\)", primary.read_text()):
                self.assertTrue((primary.parent / reference.split("#")[0]).exists(), reference)
            self.assertEqual(self.invoke("install-skill", "--client", "vscode", "--target", target).returncode, 0)
            exported_entry = installed / "framework/deploy/deploy.sh"
            clean_environment = {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": temporary}
            checked = subprocess.run([str(exported_entry), "verify"], cwd=temporary,
                                     env=clean_environment, capture_output=True, timeout=60)
            self.assertEqual(checked.returncode, 0, checked.stderr.decode())
            self.assertEqual(json.loads(checked.stdout)["status"], "complete")
            primary.write_text(primary.read_text() + "\nUser-owned addition.\n")
            self.assertEqual(self.invoke("install-skill", "--client", "vscode", "--target", target).returncode, 2)
            self.assertIn("User-owned addition.", primary.read_text())

    def test_refusals_do_not_grant_authority_or_install(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "absent"
            self.assertEqual(self.invoke("install-skill", "--client", "unsupported", "--target", target).returncode, 2)
            self.assertFalse(target.exists())
            for arguments in (("run", "--allow-model-calls"), ("describe", "--allow-model-calls"),
                              ("run", "--allow-model-call"), ("local", "--allow-model-call"),
                              ("local", "--a"), ("native-run",), ("cloud",), ("teardown",)):
                self.assertEqual(self.invoke(*arguments, cwd=temporary).returncode, 2)


if __name__ == "__main__":
    unittest.main()