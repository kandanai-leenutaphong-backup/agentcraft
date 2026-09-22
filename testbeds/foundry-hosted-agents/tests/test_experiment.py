import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from deploy import experiment

from composition import ROOT, load_spec
from proof_tools import nonce_digest
from main import validate_events


class ConfigurationTests(unittest.TestCase):
    def test_real_hosting_sdk_compatibility(self):
        from deploy.compatibility import check

        self.assertEqual(check()["readiness"], 200)

    def test_positive_custom_script(self):
        spec = load_spec()
        nonce = "a1" * 16
        result = spec.tools[0](nonce)
        self.assertEqual(result, {
            "marker": "foundry-custom-script-v1", "nonce": nonce,
            "sha256": hashlib.sha256(("foundry-custom-script-v1:" + nonce).encode()).hexdigest(),
        })

    def test_invalid_nonce(self):
        for nonce in ("", "../secret", "f" * 33, None):
            with self.subTest(nonce=nonce), self.assertRaises(ValueError):
                nonce_digest(nonce)

    def test_native_maf_schema(self):
        from agent_framework import tool

        schema = tool(nonce_digest).to_json_schema_spec()
        self.assertEqual(schema["function"]["name"], "nonce_digest")
        self.assertEqual(schema["function"]["parameters"]["required"], ["nonce"])

    def test_build_source_allowlist(self):
        sources = experiment.source_inputs()
        self.assertIn("app/configuration.yaml", sources)
        self.assertTrue(all("records/" not in name and "__pycache__" not in name for name in sources))
        self.assertEqual(experiment.manifest(), experiment.manifest())

    def test_foreign_receipt_refused(self):
        with self.assertRaises(ValueError):
            experiment.read_receipt("/tmp/foreign-receipt.json", "build")

    def test_target_mismatch_refused(self):
        with patch.object(experiment, "prerequisites", return_value={"gaps": []}), patch.object(
            experiment, "cli", return_value={"subscriptionId": "foreign"}
        ) as command:
            with self.assertRaisesRegex(ValueError, "account mismatch"):
                experiment.preflight()
            self.assertEqual(command.call_count, 1)

    def test_build_stops_before_mutation(self):
        with patch.object(experiment, "preflight", side_effect=RuntimeError("blocked")), patch.object(experiment, "cli") as command:
            with self.assertRaises(RuntimeError):
                experiment.build()
            command.assert_not_called()

    def test_pull_role_semantics_refuse_broad_role(self):
        with patch.object(experiment, "preflight", return_value={"project_registry_roles": []}), patch.object(
            experiment, "cli", return_value=[{"id": experiment.PULL_ROLE, "name": "AcrPull", "permissions": []}]
        ) as command:
            with self.assertRaisesRegex(ValueError, "semantics"):
                experiment.grant_pull()
            self.assertEqual(command.call_count, 1)

    def test_existing_exact_pull_grant_is_read_only(self):
        scope = experiment.TARGET["registry_id"]
        definition = [{"id": experiment.PULL_ROLE, "name": "AcrPull", "permissions": [{
            "actions": ["Microsoft.ContainerRegistry/registries/pull/read"],
            "notActions": [], "dataActions": [], "notDataActions": [],
            "condition": None, "conditionVersion": None}]}]
        assignment = {"scope": scope, "principalId": experiment.PROJECT_PRINCIPAL,
                      "roleDefinitionId": "/roles/" + experiment.PULL_ROLE, "condition": None}
        with patch.object(experiment, "preflight", return_value={"project_registry_roles": [
            {"scope": scope, "role": "AcrPull", "condition": None}]}), patch.object(
            experiment, "cli", side_effect=[definition, [assignment]]
        ) as command:
            self.assertFalse(experiment.grant_pull()["created"])
            self.assertEqual(command.call_count, 2)

    def test_inactive_version_refused(self):
        deployed = {"version": "1", "definition": {"kind": "hosted", "cpu": "1", "memory": "2Gi",
                    "protocol_versions": [], "container_configuration": {"image": "registry/image@sha256:test"}}}
        with patch.object(experiment, "api", return_value=(200, {"status": "creating", "definition": deployed["definition"]})):
            with self.assertRaises(RuntimeError):
                experiment.check_version(deployed)

    def test_existing_name_without_owned_receipt_refused(self):
        with patch.object(experiment, "preflight"), patch.object(experiment, "read_receipt", return_value={}), patch.object(
            experiment, "api", return_value=(200, {"name": experiment.TARGET["agent_name"]})
        ) as request:
            with self.assertRaisesRegex(ValueError, "explicit owned"):
                experiment.deploy("build")
            self.assertEqual(request.call_count, 1)

    def test_active_image_drift_refused(self):
        definition = {"kind": "hosted", "cpu": "1", "memory": "2Gi", "protocol_versions": [],
                      "container_configuration": {"image": "registry/image@sha256:expected"}}
        actual = {**definition, "container_configuration": {"image": "registry/image@sha256:foreign"}}
        with patch.object(experiment, "api", return_value=(200, {"status": "active", "definition": actual})):
            with self.assertRaises(RuntimeError):
                experiment.check_version({"version": "1", "definition": definition})

    def test_unknown_tool(self):
        self.assert_bad_config((ROOT / "configuration.yaml").read_text().replace(
            "proof_tools:nonce_digest", "os:system"))

    def test_duplicate_yaml_key(self):
        self.assert_bad_config("agents: {}\nagents: {}\n")

    def test_unknown_field(self):
        self.assert_bad_config((ROOT / "configuration.yaml").read_text() + "credential: forbidden\n")

    def test_tool_evidence(self):
        expected = nonce_digest("a1" * 16)
        events = [
            {"kind": "tool.call.ready", "data": {"name": "nonce_digest", "call_id": "call_1", "arguments": {"nonce": expected["nonce"]}}},
            {"kind": "tool.started", "data": {"name": "nonce_digest", "call_id": "call_1"}},
            {"kind": "tool.result", "data": {"call_id": "call_1", "result": expected}},
        ]
        validate_events(events, expected)
        with self.assertRaises(ValueError):
            validate_events([], expected)
        events[2]["data"]["call_id"] = "different"
        with self.assertRaises(ValueError):
            validate_events(events, expected)

    def assert_bad_config(self, content):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "configuration.yaml"
            path.write_text(content)
            with self.assertRaises(ValueError):
                load_spec(path)


if __name__ == "__main__":
    unittest.main()