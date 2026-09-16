from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest


TOOL = Path(__file__).resolve().parents[1] / "tools/package_native.py"
SPEC = importlib.util.spec_from_file_location("package_native", TOOL)
assert SPEC is not None and SPEC.loader is not None
package_native = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(package_native)


class NativeDistributionTests(unittest.TestCase):
    def test_native_files_use_workspace_sources_without_legacy_core(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            agent = root / ".github/agents/example.agent.md"
            rule = root / ".github/instructions/example.instructions.md"
            agent.parent.mkdir(parents=True)
            rule.parent.mkdir(parents=True)
            agent.write_text("---\nname: example\n---\nExample agent.\n")
            rule.write_text("---\napplyTo: '**'\n---\nExample rule.\n")
            outputs = package_native.native_files(root)
            self.assertEqual(
                set(outputs),
                {
                    "com.github.copilot/agents/example.agent.md",
                    "com.github.copilot/rules/example.instructions.md",
                },
            )
            self.assertFalse((root / "core").exists())


if __name__ == "__main__":
    unittest.main()