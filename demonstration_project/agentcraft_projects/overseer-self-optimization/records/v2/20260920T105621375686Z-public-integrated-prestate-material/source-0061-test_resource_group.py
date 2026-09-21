import copy
import importlib.util
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

spec = importlib.util.spec_from_file_location("resource_group", Path(__file__).resolve().parents[1] / "resource_group.py")
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)

TARGET = module.Target("11111111-1111-1111-1111-111111111111", "22222222-2222-2222-2222-222222222222",
                       "rg-agentcraft-unit-test", "eastus2", "AzureCloud")


class FakeAzure:
    def __init__(self):
        self.calls = []
        self.account = {"id": TARGET.subscription_id, "tenantId": TARGET.tenant_id, "state": "Enabled", "cloud": "AzureCloud"}
        self.permissions = [{"actions": ["*"], "notActions": []}]
        self.group = None
        self.resources = []
        self.locks = []
        self.created_location = TARGET.location

    def __call__(self, *arguments):
        self.calls.append(arguments)
        operation = arguments[:2]
        if operation == ("account", "show"):
            return self.account
        if operation == ("account", "list-locations"):
            return [TARGET.location]
        if arguments[0] == "rest":
            return self.permissions
        if operation == ("group", "exists"):
            return self.group is not None
        if operation == ("group", "create"):
            self.group = {"id": TARGET.resource_id, "name": TARGET.resource_group, "location": self.created_location,
                          "tags": dict(value.split("=", 1) for value in arguments[arguments.index("--tags") + 1:]),
                          "properties": {"provisioningState": "Succeeded"}}
            return self.group
        if operation == ("group", "show"):
            return copy.deepcopy(self.group)
        if operation == ("resource", "list"):
            return self.resources
        if operation == ("lock", "list"):
            return self.locks
        if operation == ("group", "delete"):
            self.group = None
            return None
        raise AssertionError(f"Unexpected Azure operation: {operation}")

    def mutations(self):
        return [call for call in self.calls if call[:2] in {("group", "create"), ("group", "delete")}]


class ResourceGroupTests(unittest.TestCase):
    def setUp(self):
        self.cli = FakeAzure()
        self.runner = module.ResourceGroupDeployment(TARGET, self.cli)

    def create(self):
        return self.runner.run("create", TARGET.resource_id)

    def test_plan_is_read_only_and_names_exact_target(self):
        result = self.runner.run("plan")
        self.assertEqual(result["confirmation_required"], TARGET.resource_id)
        self.assertTrue(result["would_create"])
        self.assertEqual(self.cli.mutations(), [])

    def test_mutation_requires_exact_confirmation_before_cli(self):
        for action in ("create", "teardown"):
            with self.subTest(action=action), self.assertRaises(module.DeploymentError):
                self.runner.run(action, "another-target")
        self.assertEqual(self.cli.calls, [])

    def test_mismatched_account_cannot_create(self):
        for field in ("id", "tenantId", "cloud", "state"):
            with self.subTest(field=field):
                self.cli.account[field], original = "wrong", self.cli.account[field]
                with self.assertRaises(module.DeploymentError):
                    self.create()
                self.cli.account[field] = original
        self.assertEqual(self.cli.mutations(), [])

    def test_missing_permission_cannot_create(self):
        self.cli.permissions = [{"actions": ["*/read"], "notActions": []}]
        with self.assertRaises(module.DeploymentError):
            self.create()
        self.assertEqual(self.cli.mutations(), [])

    def test_excluded_action_does_not_grant_creation(self):
        self.cli.permissions = [{"actions": ["*"], "notActions": [module.GROUP_ACTION + "write"]}]
        with self.assertRaises(module.DeploymentError):
            self.create()
        self.assertEqual(self.cli.mutations(), [])

    def test_create_reads_back_group_and_contents(self):
        result = self.create()
        self.assertEqual(result["action"], "created")
        self.assertEqual(result["resource_count"], 0)
        self.assertTrue(result["read_back_verified"])
        self.assertTrue(any(call[:2] == ("group", "show") for call in self.cli.calls))
        self.assertTrue(any(call[:2] == ("resource", "list") for call in self.cli.calls))

    def test_repeat_create_is_noop_not_retag(self):
        self.create()
        result = self.create()
        self.assertEqual(result["action"], "unchanged")
        self.assertEqual(len(self.cli.mutations()), 1)

    def test_project_target_has_own_tags_without_changing_connector_defaults(self):
        target = replace(TARGET, capability="agentcraft", purpose="project-testing", data_policy="operator-approved")
        runner = module.ResourceGroupDeployment(target, self.cli)
        result = runner.run("create", target.resource_id)
        self.assertEqual(result["tags"], target.tags)
        self.assertEqual(result["tags"]["capability"], "agentcraft")
        self.assertEqual(result["tags"]["purpose"], "project-testing")
        self.assertEqual(result["tags"]["data-policy"], "operator-approved")
        self.assertEqual(TARGET.tags, module.TAGS)
        self.assertEqual(runner.run("create", target.resource_id)["action"], "unchanged")
        with self.assertRaises(module.DeploymentError):
            self.runner.run("verify")
        self.assertEqual(len(self.cli.mutations()), 1)

    def test_existing_unowned_group_is_preserved(self):
        self.create()
        self.cli.group["tags"]["managed-by"] = "another-owner"
        with self.assertRaises(module.DeploymentError):
            self.create()
        self.assertEqual(len(self.cli.mutations()), 1)

    def test_wrong_readback_does_not_claim_success(self):
        self.cli.created_location = "westus2"
        with self.assertRaises(module.DeploymentError):
            self.create()
        self.assertIsNotNone(self.cli.group)

    def test_verify_does_not_create_an_absent_group(self):
        with self.assertRaises(module.DeploymentError):
            self.runner.run("verify")
        self.assertEqual(self.cli.mutations(), [])

    def test_teardown_refuses_child_resources(self):
        self.create()
        self.cli.resources = [{"id": TARGET.resource_id + "/providers/example/resources/one"}]
        with self.assertRaises(module.DeploymentError):
            self.runner.run("teardown", TARGET.resource_id)
        self.assertEqual(len(self.cli.mutations()), 1)

    def test_teardown_does_not_remove_locks(self):
        self.create()
        self.cli.locks = [{"level": "CanNotDelete"}]
        with self.assertRaises(module.DeploymentError):
            self.runner.run("teardown", TARGET.resource_id)
        self.assertEqual(len(self.cli.mutations()), 1)

    def test_authorized_empty_teardown_verifies_absence_and_repeats(self):
        self.create()
        result = self.runner.run("teardown", TARGET.resource_id)
        self.assertEqual(result["action"], "deleted")
        self.assertTrue(result["read_back_verified"])
        self.assertEqual(self.runner.run("teardown", TARGET.resource_id)["action"], "already_absent")

    def test_environment_is_data_not_shell_or_credentials(self):
        base = (f"SUBSCRIPTION_ID={TARGET.subscription_id}\nTENANT_ID={TARGET.tenant_id}\n"
                f"RESOURCE_GROUP={TARGET.resource_group}\nLOCATION={TARGET.location}\nCLOUD=AzureCloud\n")
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "target.env"
            path.write_text(base, encoding="utf-8")
            self.assertEqual(module.Target.load(path), TARGET)
            path.write_text(base + "CAPABILITY=agentcraft\nPURPOSE=project-testing\nDATA_POLICY=operator-approved\n", encoding="utf-8")
            self.assertEqual(module.Target.load(path), replace(TARGET, capability="agentcraft", purpose="project-testing", data_policy="operator-approved"))
            for text in (base + "CLIENT_SECRET=not-a-real-secret\n", base + "LOCATION=eastus2\n",
                         base.replace("LOCATION=eastus2", "LOCATION=$(uname)"), base.replace("CLOUD=AzureCloud\n", ""),
                         base + "PURPOSE=$(uname)\n", base + "PURPOSE=testing\nPURPOSE=duplicate\n"):
                path.write_text(text, encoding="utf-8")
                with self.subTest(text=text), self.assertRaises(module.DeploymentError):
                    module.Target.load(path)


if __name__ == "__main__":
    unittest.main()