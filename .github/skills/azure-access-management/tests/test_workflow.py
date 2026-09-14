"""Offline native-workflow routing and refusal checks."""

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("workflow", ROOT / "scripts/workflow.py")
workflow = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(workflow)
TENANT = "11111111-1111-1111-1111-111111111111"
SUBSCRIPTION = "22222222-2222-2222-2222-222222222222"


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.data = workflow.catalogue()
        self.config = {"tenant_id": TENANT, "subscription_id": SUBSCRIPTION,
                       "resource_group": "fixture-rg", "app_name": "fixture-app"}

    def test_all_source_families_are_catalogued(self):
        self.assertEqual({entry["workflow"] for entry in self.data["capabilities"]},
                         set(self.data["source_families"]))
        self.assertEqual(len({entry["id"] for entry in self.data["capabilities"]}),
                         len(self.data["capabilities"]))
        self.assertTrue(all(entry["features"] and entry["limit"] for entry in self.data["capabilities"]))

    def test_native_frontend_plan_never_executes(self):
        with patch("socket.socket.connect", side_effect=AssertionError("Network forbidden")), \
             patch("subprocess.run", side_effect=AssertionError("Execution forbidden")):
            result = workflow.plan("container-apps", self.config, self.data)
        self.assertEqual(result["status"], "PLAN_ONLY")
        self.assertFalse(result["executed"])
        self.assertFalse(result["authority_granted"])
        self.assertIn("auth", result["readback_argv"][1])

    def test_headless_provider_token_does_not_require_anonymous_gate(self):
        result = workflow.plan("container-apps", {**self.config, "caller": "provider-token"}, self.data)
        self.assertNotIn("AllowAnonymous", json.dumps(result))

    def test_custom_signature_requires_explicit_application_gate(self):
        with self.assertRaises(ValueError):
            workflow.plan("container-apps", {**self.config, "caller": "custom-signed"}, self.data)
        result = workflow.plan("container-apps", {**self.config, "caller": "custom-signed",
                                                  "enforcement": "application"}, self.data)
        self.assertFalse(result["authority_granted"])

    def test_secret_and_approval_fields_refuse_without_reflection(self):
        for field in ("client_secret", "password", "token", "approved", "authorized", "command"):
            with self.subTest(field=field), self.assertRaises(ValueError):
                workflow.plan("container-apps", {**self.config, field: "synthetic-private-value"}, self.data)

    def test_scope_binding_and_injection_refuse(self):
        for scope in ("/subscriptions/33333333-3333-3333-3333-333333333333/resourceGroups/other",
                      f"/subscriptions/{SUBSCRIPTION}/resourceGroups/../other",
                      f"/subscriptions/{SUBSCRIPTION}/resourceGroups/fixture?api-version=evil"):
            with self.subTest(scope=scope), self.assertRaises(ValueError):
                workflow.plan("access", {**self.config, "scope": scope}, self.data)

    def test_access_plan_reports_native_reads_only(self):
        result = workflow.plan("access", {**self.config, "scope": f"/subscriptions/{SUBSCRIPTION}/resourceGroups/fixture"}, self.data)
        self.assertTrue(all("create" not in argv and "delete" not in argv for argv in result["readback_argv"]))
        self.assertIn("--include-inherited", result["readback_argv"][-1])

    def test_cli_rejects_invalid_config_without_exposing_values(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.json"
            config.write_text(json.dumps({**self.config, "token": "synthetic-private-value"}))
            result = subprocess.run([sys.executable, "-B", str(ROOT / "scripts/workflow.py"),
                                     "plan", "container-apps", "--config", str(config)],
                                    capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 2)
            self.assertNotIn("synthetic-private-value", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
