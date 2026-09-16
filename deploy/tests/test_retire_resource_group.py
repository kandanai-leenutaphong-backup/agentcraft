import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from resource_group import DeploymentError, Target
from retire_resource_group import ResourceGroupRetirement, load_target


TARGET = Target("11111111-1111-1111-1111-111111111111", "22222222-2222-2222-2222-222222222222",
                "rg-singtel-ticket-poc", "eastus2", "AzureCloud")
TAGS = {"data": "synthetic-only", "owner": "pathfinderiq-demo", "project": "singtel-ticket-poc"}


class FakeAzure:
    def __init__(self):
        self.calls = []
        self.account = {"id": TARGET.subscription_id, "tenantId": TARGET.tenant_id, "state": "Enabled", "cloud": "AzureCloud"}
        self.permissions = [{"actions": ["*"], "notActions": []}]
        self.group = {"id": TARGET.resource_id, "name": TARGET.resource_group, "location": TARGET.location,
                      "tags": dict(TAGS), "managedBy": None, "provisioningState": "Succeeded"}
        self.resources = [{"id": TARGET.resource_id + "/providers/Microsoft.App/containerApps/example",
                           "name": "example", "type": "Microsoft.App/containerApps", "location": "eastus2", "kind": None}]
        self.locks = []
        self.subscription_locks = []
        self.wait_fails = False
        self.keep_present = False

    def __call__(self, *arguments, timeout_seconds=180):
        self.calls.append(arguments)
        operation = arguments[:2]
        if operation == ("account", "show"):
            return copy.deepcopy(self.account)
        if arguments[0] == "rest":
            return copy.deepcopy(self.subscription_locks if "locks?" in arguments[arguments.index("--url") + 1] else self.permissions)
        if operation == ("group", "exists"):
            return self.group is not None
        if operation == ("group", "show"):
            return copy.deepcopy(self.group)
        if operation == ("resource", "list"):
            return copy.deepcopy(self.resources)
        if operation == ("lock", "list"):
            return self.locks
        if operation == ("group", "delete"):
            return None
        if operation == ("group", "wait"):
            if self.wait_fails:
                raise DeploymentError("wait timeout; outcome unknown")
            if not self.keep_present:
                self.group = None
            return None
        raise AssertionError(arguments)

    def mutations(self):
        return [call for call in self.calls if call[:2] == ("group", "delete")]


class RetirementTests(unittest.TestCase):
    def setUp(self):
        self.cli = FakeAzure()
        self.runner = ResourceGroupRetirement(TARGET, TAGS, self.cli)

    def plan(self):
        return self.runner.run("plan")

    def delete(self, plan):
        return self.runner.run("delete", TARGET.resource_id, plan, plan["inventory_sha256"])

    def test_plan_freezes_nonempty_inventory_without_mutation(self):
        plan = self.plan()
        self.assertEqual(plan["resource_count"], 1)
        self.assertEqual(plan["snapshot"]["resources"], self.cli.resources)
        self.assertEqual(plan["confirmation_required"], TARGET.resource_id)
        self.assertEqual(self.cli.mutations(), [])

    def test_exact_group_confirmation_required_before_cli(self):
        with self.assertRaises(DeploymentError):
            self.runner.run("delete", "another-group")
        self.assertEqual(self.cli.calls, [])

    def test_missing_or_modified_inventory_refused(self):
        plan = self.plan()
        self.cli.calls.clear()
        altered = copy.deepcopy(plan)
        altered["snapshot"]["resources"] = []
        for inventory, digest in [(None, None), (plan, "0" * 64), (altered, plan["inventory_sha256"])]:
            with self.subTest(inventory=inventory), self.assertRaises(DeploymentError):
                self.runner.run("delete", TARGET.resource_id, inventory, digest)
        self.assertEqual(self.cli.calls, [])

    def test_wrong_account_refused(self):
        plan = self.plan()
        for field in ("id", "tenantId", "state", "cloud"):
            original = self.cli.account[field]
            self.cli.account[field] = "wrong"
            with self.subTest(field=field), self.assertRaises(DeploymentError):
                self.delete(plan)
            self.cli.account[field] = original
        self.assertEqual(self.cli.mutations(), [])

    def test_delete_permission_required(self):
        plan = self.plan()
        self.cli.permissions = [{"actions": ["*/read"], "notActions": []}]
        with self.assertRaises(DeploymentError):
            self.delete(plan)
        self.assertEqual(self.cli.mutations(), [])

    def test_group_and_subscription_locks_refused(self):
        plan = self.plan()
        for attribute in ("locks", "subscription_locks"):
            setattr(self.cli, attribute, [{"level": "CanNotDelete"}])
            with self.subTest(attribute=attribute), self.assertRaises(DeploymentError):
                self.delete(plan)
            setattr(self.cli, attribute, [])
        self.assertEqual(self.cli.mutations(), [])

    def test_unknown_locks_refused(self):
        plan = self.plan()
        self.cli.locks = None
        with self.assertRaises(DeploymentError):
            self.delete(plan)
        self.assertEqual(self.cli.mutations(), [])

    def test_changed_group_identity_or_ownership_refused(self):
        plan = self.plan()
        for field in ("id", "name", "location", "tags", "managedBy", "provisioningState"):
            original = self.cli.group[field]
            self.cli.group[field] = "changed"
            with self.subTest(field=field), self.assertRaises(DeploymentError):
                self.delete(plan)
            self.cli.group[field] = original
        self.assertEqual(self.cli.mutations(), [])

    def test_changed_inventory_refused(self):
        plan = self.plan()
        self.cli.resources = []
        with self.assertRaises(DeploymentError):
            self.delete(plan)
        self.assertEqual(self.cli.mutations(), [])

    def test_out_of_group_inventory_refused(self):
        self.cli.resources[0]["id"] = TARGET.resource_id + "-other/providers/Microsoft.App/containerApps/example"
        with self.assertRaises(DeploymentError):
            self.plan()
        self.assertEqual(self.cli.mutations(), [])

    def test_delete_waits_and_verifies_absence_then_repeats_without_mutation(self):
        plan = self.plan()
        result = self.delete(plan)
        self.assertEqual(result["action"], "deleted")
        self.assertTrue(result["read_back_verified"])
        self.assertEqual(self.cli.mutations(), [("group", "delete", "--name", TARGET.resource_group,
                                               "--subscription", TARGET.subscription_id, "--yes", "--no-wait")])
        self.assertTrue(any(call[:2] == ("group", "wait") for call in self.cli.calls))
        self.assertEqual(self.delete(plan)["action"], "already_absent")
        self.assertEqual(len(self.cli.mutations()), 1)

    def test_wait_timeout_is_not_success_or_another_delete(self):
        plan = self.plan()
        self.cli.wait_fails = True
        with self.assertRaises(DeploymentError):
            self.delete(plan)
        self.cli.wait_fails = False
        self.assertEqual(self.runner.run("wait")["action"], "verified_absent")
        self.assertEqual(len(self.cli.mutations()), 1)

    def test_remaining_group_is_not_verified(self):
        plan = self.plan()
        self.cli.keep_present = True
        with self.assertRaises(DeploymentError):
            self.delete(plan)
        with self.assertRaises(DeploymentError):
            self.runner.run("verify")
        self.assertEqual(len(self.cli.mutations()), 1)

    def test_current_config_pins_legacy_group(self):
        target, tags = load_target(Path(__file__).resolve().parents[1] / "env" / "singtel-retirement.json")
        self.assertEqual(target.resource_group, "rg-singtel-ticket-poc")
        self.assertEqual(tags, TAGS)


if __name__ == "__main__":
    unittest.main()