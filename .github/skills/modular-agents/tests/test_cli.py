"""The command path refuses cloud work before credentials when policy denies it."""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_definition import ROOT
sys.path.insert(0, str(ROOT / "scripts"))
import agent


class CliTests(unittest.TestCase):
    def test_plan_is_offline_and_grants_are_disabled(self):
        arguments = agent.parser().parse_args(["--env", str(ROOT / "deploy/env/example.env"), "plan"])
        with patch.object(agent, "preflight", side_effect=AssertionError("cloud preflight is forbidden")):
            result = asyncio.run(agent.execute(arguments))
        self.assertFalse(result["cloud_calls"])
        self.assertFalse(result["operator_policy"]["allow_deploy"])

    def test_denied_deployment_never_reads_credentials(self):
        arguments = agent.parser().parse_args(["--env", str(ROOT / "deploy/env/example.env"), "deploy", "--confirm"])
        with patch.object(agent, "preflight", side_effect=AssertionError("credential lookup reached")):
            with self.assertRaises(agent.DeployRefused):
                asyncio.run(agent.execute(arguments))

    def test_unknown_or_secret_environment_fields_are_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "target.env"
            source = (ROOT / "deploy/env/example.env").read_text()
            path.write_text(source + "\nCLIENT_SECRET=not-a-secret\n")
            with self.assertRaises(agent.DeployRefused):
                agent.environment(path)

    def test_shell_help_needs_neither_azure_nor_uv(self):
        result = subprocess.run(["bash", str(ROOT / "deploy/deploy.sh"), "--help"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertIn("--artifact", result.stdout)


if __name__ == "__main__":
    unittest.main()