from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import importlib.util
import json
import sys
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("datacrafting_lifecycle", ROOT / "deploy" / "lifecycle.py")
lifecycle = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = lifecycle
spec.loader.exec_module(lifecycle)


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((ROOT / "deploy" / "env" / "experiment.json").read_text())
        self.group = {"id": lifecycle.group_id(self.config), "tags": {"owner": self.config["owner"]}}
        dependencies = [
            ("Microsoft.ManagedIdentity/userAssignedIdentities", self.config["identity_name"]),
            ("Microsoft.Network/virtualNetworks", self.config["network_name"]),
            ("Microsoft.Network/privateEndpoints", self.config["private_endpoint_name"]),
            ("Microsoft.Network/privateDnsZones", "privatelink.blob.core.windows.net"),
            ("Microsoft.Storage/storageAccounts", self.config["storage_name"]),
            ("Microsoft.Web/serverfarms", self.config["plan_name"]),
            ("Microsoft.Web/sites", self.config["function_name"]),
            ("Microsoft.OperationalInsights/workspaces", self.config["logs_name"]),
            ("Microsoft.CognitiveServices/accounts", self.config["content_understanding_name"]),
        ]
        self.resources = [{"id": self.group["id"] + "/providers/" + resource_type + "/" + name,
                           "type": resource_type, "name": name, "tags": self.group["tags"]}
                          for resource_type, name in dependencies]
        self.resources.append({"id": self.group["id"] + "/providers/Microsoft.Network/privateDnsZones/privatelink.blob.core.windows.net/virtualNetworkLinks/datacrafting-network",
            "type": "Microsoft.Network/privateDnsZones/virtualNetworkLinks", "name": "privatelink.blob.core.windows.net/datacrafting-network",
            "tags": self.group["tags"]})
        self.unrelated = {"id": self.group["id"] + "/providers/Microsoft.EventGrid/systemTopics/untagged-topic",
                          "type": "Microsoft.EventGrid/systemTopics", "name": "untagged-topic", "tags": None}

    def test_frozen_target_and_unknown_credentials_refuse(self):
        self.assertEqual(lifecycle.validate_target(self.config), self.config)
        for changes in ({"subscription_id": "11111111-1111-4111-8111-111111111111"}, {"location": "unknown"},
                        {"storage_name": "name; command"}, {"connection_string": "refused"}, {"auth_enabled": "false"},
                        {"function_name": "../../other"}):
            with self.subTest(changes=changes), self.assertRaises(RuntimeError):
                lifecycle.validate_target(self.config | changes)

    def test_account_mismatch_never_switches_context(self):
        account = {"subscriptionId": "wrong", "tenantId": self.config["tenant_id"], "state": "Enabled", "cloud": "AzureCloud"}
        with patch.object(lifecycle, "command", return_value=account) as command:
            with self.assertRaises(RuntimeError):
                lifecycle.current_account(self.config)
            self.assertEqual(command.call_count, 1)
            self.assertEqual(command.call_args.args[0][:3], ["az", "account", "show"])

    def test_group_and_resource_collisions_refuse(self):
        group = {"id": lifecycle.group_id(self.config), "tags": {"owner": self.config["owner"]}}
        lifecycle.assert_group_owned(self.config, group)
        with self.assertRaises(RuntimeError):
            lifecycle.assert_group_owned(self.config, group | {"tags": {"owner": "someone-else"}})
        resource = {"id": group["id"] + "/providers/Microsoft.Storage/storageAccounts/" + self.config["storage_name"],
                    "name": self.config["storage_name"], "type": "Microsoft.Storage/storageAccounts", "tags": group["tags"]}
        lifecycle.assert_resources_owned(self.config, [resource])
        for changes in ({"name": "unrelated"}, {"type": "Unknown/resources"}, {"tags": {"owner": "someone-else"}}):
            with self.assertRaises(RuntimeError):
                lifecycle.assert_resources_owned(self.config, [resource | changes])

    def test_reference_host_allows_untouched_additions_without_ownership_or_deletion_authority(self):
        tagged = {"id": self.group["id"] + "/providers/Microsoft.Network/networkSecurityGroups/concurrent-nsg",
                  "type": "Microsoft.Network/networkSecurityGroups", "name": "concurrent-nsg", "tags": self.group["tags"]}
        resources = deepcopy(self.resources + [self.unrelated, tagged])
        original = deepcopy(resources)
        result = lifecycle.assert_reference_host_dependencies(self.config, self.group, resources)
        self.assertEqual(resources, original)
        self.assertEqual(set(result["required_resource_ids"]), {resource["id"] for resource in self.resources})
        self.assertEqual([resource["owner_tag"] for resource in result["observed_not_owned"]], [None, self.config["owner"]])
        for resource in result["observed_not_owned"]:
            self.assertEqual(resource["status"], "observed-not-owned/unmodified")
            self.assertFalse(resource["deletion_authorized"])
        self.assertFalse(result["whole_group_lifecycle_ownership_validated"])
        self.assertFalse(result["deletion_authorized"])
        self.assertEqual(result["release_mutation_set"], [{"resource_id": self.group["id"] + "/providers/Microsoft.Web/sites/" + self.config["function_name"],
                                                         "operation": "publish-function-package-only"}])

    def test_reference_host_refuses_missing_duplicate_unowned_or_mismatched_dependencies(self):
        for index, resource in enumerate(self.resources):
            with self.subTest(resource=resource["id"], case="missing"), self.assertRaisesRegex(RuntimeError, "Missing exact"):
                lifecycle.assert_reference_host_dependencies(self.config, self.group, self.resources[:index] + self.resources[index + 1:])
            with self.subTest(resource=resource["id"], case="duplicate"), self.assertRaisesRegex(RuntimeError, "Duplicate"):
                lifecycle.assert_reference_host_dependencies(self.config, self.group, self.resources + [deepcopy(resource)])
            for changes in ({"tags": None}, {"tags": {}}, {"tags": {"owner": "someone-else"}}, {"name": "other"},
                            {"type": "Unknown/resources"}, {"id": resource["id"] + "-other"},
                            {"id": resource["id"].replace(self.config["resource_group"], "wrong-group")}):
                with self.subTest(resource=resource["id"], changes=changes), self.assertRaises(RuntimeError):
                    lifecycle.assert_reference_host_dependencies(self.config, self.group,
                        self.resources[:index] + [resource | changes] + self.resources[index + 1:])
        for extra in (self.resources[0] | {"id": self.resources[0]["id"] + "-impostor"},
                      self.unrelated | {"id": self.unrelated["id"].replace(self.config["resource_group"], "wrong-group")}):
            with self.subTest(extra=extra), self.assertRaises(RuntimeError):
                lifecycle.assert_reference_host_dependencies(self.config, self.group, self.resources + [extra])

    def test_reference_host_refuses_wrong_group_identity_or_owner(self):
        for changes in ({"id": self.group["id"] + "-other"}, {"tags": None}, {"tags": {"owner": "someone-else"}}):
            with self.subTest(changes=changes), self.assertRaises(RuntimeError):
                lifecycle.assert_reference_host_dependencies(self.config, self.group | changes, self.resources)

    def test_reference_host_validation_never_weakens_whole_group_preflight_or_teardown(self):
        resources = self.resources + [self.unrelated]
        lifecycle.assert_reference_host_dependencies(self.config, self.group, resources)

        def azure(config, *arguments):
            if arguments[:2] == ("group", "exists"):
                return True
            if arguments[:2] == ("group", "show"):
                return self.group
            if arguments[:2] == ("resource", "list"):
                return resources
            self.fail(f"Unexpected Azure call after unknown-resource refusal: {arguments}")

        with patch.object(lifecycle, "azure", side_effect=azure), patch.object(lifecycle, "current_account"), \
             patch.object(lifecycle, "record"), patch.object(lifecycle, "rest") as rest:
            for action in (lambda: lifecycle.preflight(self.config),
                           lambda: lifecycle.teardown(self.config, lifecycle.group_id(self.config))):
                with self.assertRaisesRegex(RuntimeError, "Unknown or unowned resource"):
                    action()
            rest.assert_not_called()

    def test_scoped_azure_argv_and_no_shell(self):
        with patch.object(lifecycle, "command", return_value={}) as command:
            lifecycle.azure(self.config, "group", "show", "--name", self.config["resource_group"])
            argv = command.call_args.args[0]
            self.assertEqual(argv[argv.index("--subscription") + 1], self.config["subscription_id"])
            self.assertNotIn("--debug", argv)

    def test_bicep_gates_and_no_secret_configuration(self):
        template = (ROOT / "deploy" / "infra" / "resources.bicep").read_text()
        for required in ("requireAuthentication: true", "unauthenticatedClientAction: 'Return401'", "disableLocalAuth: true",
                         "allowSharedKeyAccess: false", "enabled: activate", "allowedPrincipals:", "instanceMemoryMB: 512"):
            self.assertIn(required, template)
        for forbidden in ("listKeys(", "AccountKey=", "WEBSITE_CONTENTAZUREFILECONNECTIONSTRING", "clientSecretSettingName"):
            self.assertNotIn(forbidden, template)
        for retired in ("resource di ", "resource diUser ", "target.document_intelligence_name", "FormRecognizer"):
            self.assertNotIn(retired, template)

    def test_runner_refuses_retired_methods_before_cloud_or_process_calls(self):
        from azure_extraction.contracts import Refusal

        with patch.object(lifecycle, "current_account") as account, patch.object(lifecycle.subprocess, "run") as run:
            for method in ("document-intelligence-read", "document-intelligence-layout", "pymupdf", "markitdown"):
                with self.subTest(method=method), self.assertRaises(Refusal):
                    lifecycle.run_extractions(self.config, method, "murray")
            account.assert_not_called()
            run.assert_not_called()

    def test_readback_needs_only_cu_and_storage_grants(self):
        prefix = lifecycle.group_id(self.config) + "/providers/"
        identity_id = prefix + "Microsoft.ManagedIdentity/userAssignedIdentities/" + self.config["identity_name"]
        storage_id = prefix + "Microsoft.Storage/storageAccounts/" + self.config["storage_name"]
        cu_id = prefix + "Microsoft.CognitiveServices/accounts/" + self.config["content_understanding_name"]
        site = {"identity": {"userAssignedIdentities": {identity_id: {}}}, "properties": {
            "functionAppConfig": {"deployment": {"storage": {"authentication": {"type": "UserAssignedIdentity"}}}, "scaleAndConcurrency": {}},
            "defaultHostName": self.config["function_name"] + ".azurewebsites.net",
            "enabledHostNames": [self.config["function_name"] + ".scm.azurewebsites.net"]}}
        urls = []
        scopes = []

        def rest(config, method, url):
            self.assertEqual(method, "GET")
            urls.append(url)
            if "/config/authsettingsV2?" in url:
                return {}
            if "/userAssignedIdentities/" in url:
                return {"id": identity_id, "properties": {"principalId": "workload", "clientId": "client"}}
            if "/storageAccounts/" in url:
                return {"id": storage_id, "properties": {"allowSharedKeyAccess": False, "publicNetworkAccess": "Disabled", "allowBlobPublicAccess": False}}
            if "/accounts/" in url:
                self.assertIn(self.config["content_understanding_name"], url)
                return {"id": cu_id, "properties": {"disableLocalAuth": True}, "sku": {"name": "S0"}}
            if "/basicPublishingCredentialsPolicies/" in url:
                return {"properties": {"allow": False}}
            return site

        def azure(config, *arguments):
            if arguments[:2] == ("group", "show"):
                return self.group
            if arguments[:2] == ("resource", "list"):
                return self.resources + [self.unrelated]
            self.assertEqual(arguments[:3], ("role", "assignment", "list"))
            scope = arguments[4]
            scopes.append(scope)
            role = "b7e6dc6d-f1e8-4753-8033-0f276bb0955b" if scope == storage_id else "a97b65f3-24c7-4388-baec-2e87135dc908"
            return [{"scope": scope, "principalId": "workload", "roleDefinitionId": "/roles/" + role}]

        with TemporaryDirectory() as temporary:
            identity_path = Path(temporary) / "identity.json"
            identity_path.write_text(json.dumps({"api_client_id": "owned-api"}))
            with patch.object(lifecycle, "IDENTITY_PATH", identity_path), patch.object(lifecycle, "current_account"), \
                 patch.object(lifecycle, "existing_resources", side_effect=AssertionError("whole-group release guard")), patch.object(lifecycle, "validate_auth"), \
                 patch.object(lifecycle, "rest", side_effect=rest), patch.object(lifecycle, "azure", side_effect=azure), \
                 patch.object(lifecycle, "save_state"), patch.object(lifecycle, "record") as record:
                runtime = lifecycle.readback(self.config)
                inventory = next(call.args[1] for call in record.call_args_list if call.args[0] == "reference-host-inventory")
                self.assertEqual(inventory["resources"], self.resources + [self.unrelated])
                self.assertFalse(inventory["validation"]["deletion_authorized"])
        self.assertNotIn("di_host", runtime)
        self.assertNotIn("document_intelligence_name", runtime)
        self.assertEqual(scopes, [storage_id, cu_id])
        self.assertFalse(any(self.config["document_intelligence_name"] in url for url in urls))

    def test_auth_readback_refuses_exclusions_or_other_principal(self):
        identity = {"api_client_id": "owned-api"}
        auth = {"properties": {
            "platform": {"enabled": True},
            "globalValidation": {"requireAuthentication": True, "unauthenticatedClientAction": "Return401"},
            "login": {"tokenStore": {"enabled": False}},
            "identityProviders": {"azureActiveDirectory": {"enabled": True,
                "registration": {"clientId": "owned-api", "openIdIssuer": f"https://login.microsoftonline.com/{self.config['tenant_id']}/v2.0"},
                "validation": {"defaultAuthorizationPolicy": {"allowedApplications": [lifecycle.CLI_CLIENT_ID],
                    "allowedPrincipals": {"identities": [self.config["operator_principal_id"]]}}}}}}}
        lifecycle.validate_auth(self.config, identity, auth)
        changed = deepcopy(auth)
        changed["properties"]["globalValidation"]["excludedPaths"] = ["/api/*"]
        with self.assertRaises(RuntimeError):
            lifecycle.validate_auth(self.config, identity, changed)
        changed = deepcopy(auth)
        changed["properties"]["identityProviders"]["azureActiveDirectory"]["validation"]["defaultAuthorizationPolicy"]["allowedPrincipals"]["identities"] = ["another-principal"]
        with self.assertRaises(RuntimeError):
            lifecycle.validate_auth(self.config, identity, changed)

    def test_native_scm_states_and_bounded_target(self):
        from types import SimpleNamespace

        operation = lifecycle.ScmOperation("https://owned.scm.azurewebsites.net/api/deployments/fixture")
        for status, expected in ((0, "InProgress"), (1, "InProgress"), (2, "InProgress"), (3, "Failed"), (4, "Succeeded")):
            response = SimpleNamespace(http_response=SimpleNamespace(json=lambda: {"status": status}))
            self.assertEqual(operation.get_status(response), expected)
        polling = lifecycle.ScmPolling(operation.status_url)
        with self.assertRaises(RuntimeError):
            polling.request_status("https://elsewhere")
        polling.deadline = -1
        with self.assertRaises(RuntimeError):
            polling.request_status(operation.status_url)

    def test_cu_release_refuses_intrusive_activation_changes(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "build").mkdir()
            (root / "build/release.json").write_text(json.dumps({"archive": str(root / "build/function.zip")}))
            site = {"properties": {"enabled": False, "publicNetworkAccess": "Disabled"}}
            with patch.object(lifecycle, "ROOT", root), patch.object(lifecycle, "check_package"), \
                 patch.object(lifecycle, "readback", return_value={"function_id": "owned"}), \
                 patch.object(lifecycle, "rest", return_value=site) as rest, \
                 patch.object(lifecycle, "management_client") as client:
                with self.assertRaisesRegex(RuntimeError, "ingress/activation"):
                    lifecycle.release(self.config)
                self.assertEqual(rest.call_count, 1)
                self.assertEqual(rest.call_args.args[1], "GET")
                client.assert_not_called()

    def test_cached_local_build_targets_refuse_drift_and_retired_hosts(self):
        runtime = lifecycle.cached_runtime(self.config)
        self.assertNotIn("di_host", runtime)
        identity = json.loads((ROOT / "deploy/env/identity.json").read_text())
        for changes in ({"subscription_id": "other"}, {"di_host": "retired.example"}, {"api_client_id": "other"},
                        {"cu_host": "other.example"}, {"function_host": "other.azurewebsites.net"},
                        {"function_endpoint": "http://" + runtime["function_host"]}):
            with self.subTest(changes=changes), TemporaryDirectory() as temporary:
                root = Path(temporary)
                (root / "env").mkdir()
                (root / "env/runtime.json").write_text(json.dumps(runtime | changes))
                (root / "env/identity.json").write_text(json.dumps(identity))
                with patch.object(lifecycle, "ROOT", root), patch.object(lifecycle, "IDENTITY_PATH", root / "env/identity.json"), \
                     patch.object(lifecycle, "command") as command:
                    with self.assertRaises((RuntimeError, ValueError)):
                        lifecycle.cached_runtime(self.config)
                    command.assert_not_called()

    def test_local_only_flag_cannot_bypass_release_readback(self):
        with patch.object(sys, "argv", ["lifecycle.py", "release", "--local-only"]), \
             patch.object(lifecycle, "release") as release:
            with self.assertRaises(SystemExit) as context:
                lifecycle.main()
            self.assertEqual(context.exception.code, 2)
            release.assert_not_called()

    def test_teardown_refuses_before_any_command_without_exact_confirmation(self):
        with patch.object(lifecycle, "command") as command:
            for confirmation in (None, "", "some-other-group", lifecycle.group_id(self.config) + "/extra"):
                with self.assertRaises(RuntimeError):
                    lifecycle.teardown(self.config, confirmation)
            command.assert_not_called()

    def test_teardown_owned_group_is_read_back_and_second_run_is_noop(self):
        state = {"exists": True, "deletes": 0, "reads_after_delete": 0}

        def azure(config, *arguments):
            operation = arguments[:2]
            if operation == ("group", "exists"):
                if not state["exists"]:
                    state["reads_after_delete"] += 1
                return state["exists"]
            if operation == ("group", "show"):
                return {"id": lifecycle.group_id(config), "tags": {"owner": config["owner"]}}
            if operation in {("resource", "list"), ("lock", "list")}:
                return []
            if operation == ("group", "delete"):
                self.assertEqual(arguments, ("group", "delete", "--name", self.config["resource_group"], "--yes"))
                state["exists"] = False
                state["deletes"] += 1
                return None
            self.fail(f"Unexpected fake Azure operation: {operation}")

        with TemporaryDirectory() as temporary, patch.object(lifecycle, "IDENTITY_PATH", Path(temporary) / "identity.json"), \
             patch.object(lifecycle, "azure", side_effect=azure), patch.object(lifecycle, "current_account"), \
             patch.object(lifecycle, "record"), patch.object(lifecycle, "rest") as rest:
            lifecycle.teardown(self.config, lifecycle.group_id(self.config))
            lifecycle.teardown(self.config, lifecycle.group_id(self.config))
            rest.assert_not_called()
        self.assertEqual(state["deletes"], 1)
        self.assertGreaterEqual(state["reads_after_delete"], 2)

    def test_teardown_lock_refuses_without_mutation(self):
        calls = []

        def azure(config, *arguments):
            calls.append(arguments)
            return [{"level": "CanNotDelete"}] if arguments[:2] == ("lock", "list") else True

        with patch.object(lifecycle, "azure", side_effect=azure), patch.object(lifecycle, "current_account"), \
             patch.object(lifecycle, "existing_resources", return_value=[]):
            with self.assertRaises(RuntimeError):
                lifecycle.teardown(self.config, lifecycle.group_id(self.config))
        self.assertFalse(any(arguments[:2] == ("group", "delete") for arguments in calls))


if __name__ == "__main__":
    unittest.main()