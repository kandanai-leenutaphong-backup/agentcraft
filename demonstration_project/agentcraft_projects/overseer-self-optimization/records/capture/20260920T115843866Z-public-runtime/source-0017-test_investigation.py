import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from investigation import DeploymentError, InvestigationDeployment, PROVIDERS, load_config

CONFIG = Path(__file__).resolve().parents[1] / "env/agentcraft-dev.json"


class FakeCli:
    def __init__(self):
        self.calls = []
        self.account = {"id": "67255afe-8670-4401-a1b8-df6ca63a3516",
                        "tenantId": "c79ab2bb-79cb-47f1-b4da-b6852fe45ff7", "state": "Enabled", "cloud": "AzureCloud"}
        self.present = False
        self.permissions = [{"actions": ["*"], "notActions": []}]

    def __call__(self, *arguments):
        self.calls.append(arguments)
        if arguments[:2] == ("account", "show"):
            return self.account
        if arguments[:2] == ("group", "exists"):
            return self.present
        if arguments[:2] == ("group", "show"):
            return {"id": "foreign", "location": "australiaeast", "tags": {}}
        if arguments[0] == "rest":
            if "graph.microsoft.com" in arguments[4]:
                return {"allowedToCreateApps": True}
            if "/locks?" in arguments[4]:
                return []
            return self.permissions
        if arguments[:2] == ("provider", "list"):
            return [{"namespace": name, "state": "Registered"} for name in PROVIDERS]
        if arguments[0] in {"policy", "lock"}:
            return []
        if arguments[:3] == ("cognitiveservices", "account", "list"):
            return [{"resourceGroup": "model-owner"}]
        if arguments[:4] == ("cognitiveservices", "account", "deployment", "show"):
            return {"name": "gpt-5.6-luna", "state": "Succeeded"}
        raise AssertionError(arguments)


class InvestigationTests(unittest.TestCase):
    def setUp(self):
        self.config = load_config(CONFIG)
        self.cli = FakeCli()
        self.deployment = InvestigationDeployment(self.config, self.cli)

    def test_unknown_and_changed_target_fields_refuse(self):
        for key, value in (("secret", "refused"), ("resource_group", "unrelated"), ("model_deployment", "other")):
            changed = copy.deepcopy(self.config)
            changed[key] = value
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "config.json"
                path.write_text(json.dumps(changed))
                with self.assertRaises(DeploymentError):
                    load_config(path)

    def test_duplicate_fields_refuse(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text('{"schema_version":1,"schema_version":1}')
            with self.assertRaises(DeploymentError):
                load_config(path)

    def test_account_drift_stops_before_other_reads(self):
        self.cli.account["tenantId"] = "wrong"
        with self.assertRaisesRegex(DeploymentError, "Wrong tenant"):
            self.deployment.preflight()
        self.assertEqual(len(self.cli.calls), 1)

    def test_ownership_drift_refuses(self):
        self.cli.present = True
        with self.assertRaisesRegex(DeploymentError, "ownership"):
            self.deployment.preflight()

    def test_missing_grant_stops_before_providers(self):
        self.cli.permissions = [{"actions": ["Microsoft.Resources/subscriptions/resourceGroups/*"], "notActions": []}]
        with self.assertRaisesRegex(DeploymentError, "Missing reported"):
            self.deployment.preflight()
        self.assertFalse(any(call[0] == "provider" for call in self.cli.calls))

    def test_idempotent_preflight_has_no_writes_or_exposure(self):
        first = self.deployment.preflight()
        second = self.deployment.preflight()
        self.assertEqual(first, second)
        self.assertEqual(first["cloud_mutations"], 0)
        self.assertEqual(first["status"], "blocked")
        self.assertGreater(len(first["blockers"]), 0)
        for call in self.cli.calls:
            self.assertFalse({"create", "update", "delete", "put", "patch", "enable", "set"}.intersection(call))


if __name__ == "__main__":
    unittest.main()