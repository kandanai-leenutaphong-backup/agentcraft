import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from resource_group import DeploymentError
from writeup import DIRECTORY, TAGS, WriteupDeployment, load_config


CONFIG = load_config(DIRECTORY / "env/writeup.json")


class WriteupTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.runner = WriteupDeployment(CONFIG, self.azure)
        self.registration = {
            "id": CONFIG["auth_registration_object_id"], "appId": CONFIG["auth_client_id"],
            "signInAudience": "AzureADMultipleOrgs", "requiredResourceAccess": [],
            "web": {"redirectUris": ["https://old.example/.auth/login/aad/callback"],
                    "implicitGrantSettings": {"enableIdTokenIssuance": True, "enableAccessTokenIssuance": False}},
        }
        self.url = "https://ca-agentcraft-writeup.example-123.eastus2.azurecontainerapps.io"

    def azure(self, *arguments, timeout_seconds=180):
        self.calls.append(arguments)
        if arguments[:3] == ("ad", "app", "show"):
            return copy.deepcopy(self.registration)
        if arguments[:3] == ("rest", "--method", "patch"):
            self.registration.update(json.loads(arguments[arguments.index("--body") + 1]))
            return None
        raise AssertionError(arguments)

    def test_wrong_confirmation_refuses_before_azure(self):
        with self.assertRaises(DeploymentError):
            self.runner.run("deploy", "another-group")
        self.assertEqual(self.calls, [])

    def test_only_single_app_and_hosting_ids_are_declared(self):
        resources = self.runner.expected_resources()
        self.assertEqual(set(resources), {"app", "environment", "registry", "identity"})
        self.assertTrue(all(value.startswith(self.runner.project.resource_id + "/providers/") for value in resources.values()))

    def test_template_never_opens_ingress(self):
        for application in (False, True):
            parameters = self.runner.template_parameters(application, "registry/writeup:tag", "public")
            self.assertIn("ingressExternal=false", parameters)
            self.assertIn(f"deployApplication={str(application).lower()}", parameters)

    def test_url_must_match_app_region_and_https(self):
        self.runner.validate_url(self.url)
        for url in ("http://" + self.url.removeprefix("https://"), "https://example.com", self.url + "?redirect=elsewhere",
                    self.url.replace("eastus2", "westus"), self.url.replace("ca-agentcraft-writeup", "another-app"),
                    self.url + "/path", "https://127.0.0.1"):
            with self.subTest(url=url), self.assertRaises(DeploymentError):
                self.runner.validate_url(url)

    def test_callback_is_append_only_and_repeat_is_noop(self):
        original = copy.deepcopy(self.registration)
        self.runner.configure_callback(self.url)
        self.assertEqual(self.registration["web"]["redirectUris"], original["web"]["redirectUris"] + [self.url + "/.auth/login/aad/callback"])
        self.assertEqual(self.registration["web"]["implicitGrantSettings"], original["web"]["implicitGrantSettings"])
        self.assertEqual(self.registration["requiredResourceAccess"], original["requiredResourceAccess"])
        self.runner.configure_callback(self.url)
        self.assertEqual(len([call for call in self.calls if call[:3] == ("rest", "--method", "patch")]), 1)
        self.assertFalse(self.runner.observations["registration"]["callback_added"])

    def test_callback_rejects_changed_registration(self):
        for field in ("id", "appId", "signInAudience"):
            original = self.registration[field]
            self.registration[field] = "different"
            with self.subTest(field=field), self.assertRaises(DeploymentError):
                self.runner.configure_callback(self.url)
            self.registration[field] = original
        self.assertFalse(any(call[:3] == ("rest", "--method", "patch") for call in self.calls))

    def test_missing_key_never_generates_one(self):
        with patch("writeup.Path.is_file", return_value=False), patch.object(self.runner, "local") as local:
            with self.assertRaises(DeploymentError):
                self.runner.public_key()
        local.assert_not_called()

    def test_unsafe_config_fields_and_targets_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "target.json"
            for change in ({"client_secret": "not-a-real-secret"}, {"resource_group": "rg-singtel-ticket-poc"},
                           {"subscription_id": "00000000-0000-0000-0000-000000000000"}, {"name": "$(id)"}):
                path.write_text(json.dumps({**CONFIG, **change}), encoding="utf-8")
                with self.subTest(change=change), self.assertRaises(DeploymentError):
                    load_config(path)

    def test_azure_security_state_requires_positive_readback(self):
        state = {
            "app": {"id": self.runner.expected_resources()["app"], "state": "Succeeded", "scale": {"maxReplicas": 1},
                    "ingress": {"allowInsecure": False}},
            "auth": {"platform": {"enabled": True}, "globalValidation": {"unauthenticatedClientAction": "AllowAnonymous"},
                     "identityProviders": {"azureActiveDirectory": {"registration": {
                         "clientId": CONFIG["auth_client_id"],
                         "openIdIssuer": f"https://login.microsoftonline.com/{CONFIG['auth_tenant_id']}/v2.0"}}}},
            "registry": {"adminUserEnabled": False, "anonymousPullEnabled": False},
        }

        def snapshot_cli(*arguments, **kwargs):
            if arguments[0] == "containerapp":
                return state["app"]
            if arguments[0] == "rest":
                return state["auth"]
            if arguments[0] == "acr":
                return state["registry"]
            raise AssertionError(arguments)

        self.runner.cli = snapshot_cli
        self.runner.snapshot()
        for owner, field in ((state["registry"], "adminUserEnabled"), (state["registry"], "anonymousPullEnabled"),
                             (state["app"]["ingress"], "allowInsecure"), (state["auth"]["platform"], "enabled")):
            original = owner[field]
            owner[field] = not original
            with self.subTest(field=field), self.assertRaises(DeploymentError):
                self.runner.snapshot()
            owner[field] = original

    def test_failed_http_verification_closes_ingress(self):
        with patch.object(self.runner, "public_key", return_value="public"), patch.object(self.runner, "local"), \
                patch.object(self.runner, "apply", return_value={"url": self.url, "registryLoginServer": "example.azurecr.io"}), \
                patch.object(self.runner, "configure_callback"), patch.object(self.runner, "snapshot", return_value={
                    "app": {"ingress": {"fqdn": self.url.removeprefix("https://")}}}), \
                patch.object(self.runner, "verify_http", side_effect=DeploymentError("refusal failed")), \
                patch.object(self.runner, "call") as call:
            with self.assertRaises(DeploymentError):
                self.runner.deploy()
            self.assertEqual(call.call_args.args[:3], ("containerapp", "ingress", "disable"))


if __name__ == "__main__":
    unittest.main()