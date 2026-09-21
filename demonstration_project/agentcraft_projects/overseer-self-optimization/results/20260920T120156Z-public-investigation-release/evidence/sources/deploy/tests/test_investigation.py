import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock

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
        self.name_available = True

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
            if "/locks?" in arguments[4] or "/denyAssignments?" in arguments[4]:
                return []
            return self.permissions
        if arguments[:2] == ("provider", "list"):
            return [{"namespace": name, "state": "Registered"} for name in PROVIDERS]
        if arguments[:2] == ("provider", "show"):
            return ["Australia East"]
        if arguments[:2] == ("cosmosdb", "check-name-exists"):
            return not self.name_available
        if "check-name" in arguments:
            return {"available": self.name_available, "reason": None}
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
        self.assertEqual(first["status"], "preflight-read")
        self.assertGreater(len(first["limits"]), 0)
        for call in self.cli.calls:
            self.assertFalse({"create", "update", "delete", "put", "patch", "enable", "set"}.intersection(call))

    def test_constraint_reads_are_targeted_and_refuse_collisions(self):
        self.assertEqual(len(self.deployment.constraints()["name_availability"]), 5)
        for call in self.cli.calls:
            self.assertIn("--subscription", call)
            self.assertIn(self.config["subscription_id"], call)
        self.cli.name_available = False
        with self.assertRaisesRegex(DeploymentError, "name unavailable"):
            self.deployment.constraints()

    def test_infrastructure_validation_refusal_never_provisions(self):
        self.deployment.preflight = Mock(return_value={})
        self.deployment.policy_details = Mock(return_value={})
        self.deployment.group.run = Mock(return_value={"action": "created"})
        self.deployment.cli = Mock(side_effect=DeploymentError("provider_refused"))
        with self.assertRaisesRegex(DeploymentError, "provider_refused"):
            self.deployment.infrastructure(apply=True)
        self.assertEqual(self.deployment.cli.call_count, 1)
        self.assertEqual(self.deployment.cli.call_args.args[:3], ("deployment", "group", "validate"))

    def test_validation_only_does_not_create_paid_services(self):
        self.deployment.preflight = Mock(return_value={})
        self.deployment.policy_details = Mock(return_value={})
        self.deployment.group.run = Mock(return_value={"action": "unchanged"})
        self.deployment.cli = Mock(return_value={"state": "Succeeded", "error": None})
        result = self.deployment.infrastructure()
        self.assertFalse(result["paid_services_submitted"])
        self.assertEqual(self.deployment.cli.call_count, 1)

    def test_deny_assignment_refuses_before_mutation(self):
        self.assertEqual(self.deployment.policy_details()["deny_assignments"], [])
        self.deployment.cli = Mock(side_effect=[[], [{"id": "deny"}]])
        with self.assertRaisesRegex(DeploymentError, "Deny assignments"):
            self.deployment.policy_details()

    def test_unrelated_managed_group_denial_does_not_block_target(self):
        unrelated = {"scope": f"/subscriptions/{self.config['subscription_id']}/resourceGroups/other"}
        self.deployment.cli = Mock(side_effect=[[], [unrelated]])
        self.assertEqual(self.deployment.policy_details()["unrelated_denials"], 1)
        self.deployment.cli = Mock(side_effect=[[], [{"scope": self.deployment.target.resource_id}]])
        with self.assertRaisesRegex(DeploymentError, "Deny assignments"):
            self.deployment.policy_details()

    def test_registration_refuses_foreign_owner_before_patch(self):
        self.deployment.group.preflight = Mock(return_value={})
        self.deployment.group.snapshot = Mock(return_value={})
        self.deployment.cli = Mock(side_effect=["example.australiaeast.azurecontainerapps.io",
            "11111111-1111-1111-1111-111111111111",
            [{"id": "app", "appId": "client", "tags": ["agentcraft-rg-agentcraft-dev"], "signInAudience": "AzureADMyOrg"}],
            ["foreign"]])
        with self.assertRaisesRegex(DeploymentError, "ownership"):
            self.deployment.registration()
        self.assertFalse(any("patch" in call.args or "post" in call.args for call in self.deployment.cli.call_args_list))

    def test_private_release_refuses_unowned_image_and_missing_auth(self):
        self.config.pop("runtime", None)
        self.deployment.group.preflight = Mock(return_value={})
        self.deployment.group.snapshot = Mock(return_value={})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "build.json"
            for image, message in (("other.azurecr.io/app:latest", "immutable"),
                ("agentcraftdev67255.azurecr.io/investigation@sha256:" + "a" * 64, "registration")):
                path.write_text(json.dumps({"status": "image-built", "image": image}))
                with self.assertRaisesRegex(DeploymentError, message):
                    self.deployment.private_release(path)
        self.assertEqual(self.cli.calls, [])

    def test_public_release_refuses_partial_private_success(self):
        self.deployment.group.preflight = Mock(return_value={})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "receipt.json"
            path.write_text(json.dumps({"status": "private-verified", "probe": {
                "output": '{"status": "verified", "stage": "anonymous"}\n'}}))
            with self.assertRaisesRegex(DeploymentError, "Complete private"):
                self.deployment.open_ingress(path, path)
        self.assertEqual(self.cli.calls, [])

    def test_registration_reads_back_single_tenant_scope_and_callback(self):
        self.deployment.group.preflight = Mock(return_value={})
        self.deployment.group.snapshot = Mock(return_value={})
        stored = {"id": "11111111-1111-1111-1111-111111111111", "appId": "22222222-2222-2222-2222-222222222222"}

        def cli(*arguments):
            if arguments[0] == "containerapp":
                return "example.australiaeast.azurecontainerapps.io"
            url = arguments[arguments.index("--url") + 1]
            method = arguments[arguments.index("--method") + 1]
            if "/me?" in url:
                return "33333333-3333-3333-3333-333333333333"
            if "$filter=" in url:
                return []
            if method in {"post", "patch"}:
                stored.update(json.loads(arguments[arguments.index("--body") + 1]))
                return {"id": stored["id"], "appId": stored["appId"]} if method == "post" else None
            return stored

        self.deployment.cli = cli
        result = self.deployment.registration()
        self.assertEqual(result["status"], "registration-configured")
        self.assertEqual(stored["requiredResourceAccess"], [])
        self.assertEqual(stored["api"]["oauth2PermissionScopes"][0]["value"], "access_as_user")
        self.assertTrue(stored["spa"]["redirectUris"][0].endswith("/auth/callback"))


if __name__ == "__main__":
    unittest.main()