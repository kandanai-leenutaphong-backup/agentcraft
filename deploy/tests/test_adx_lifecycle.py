import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import adx_lifecycle as module


TARGET = module.AdxTarget(
    subscription_id="11111111-1111-1111-1111-111111111111",
    tenant_id="22222222-2222-2222-2222-222222222222",
    resource_group="rg-existing-test",
    cluster="existingadx01",
    location="australiaeast",
    database="Events",
    endpoint="https://existingadx01.australiaeast.kusto.windows.net",
    cloud="AzureCloud",
)


class FakeAzure:
    def __init__(self):
        self.calls = []
        self.account = {"id": TARGET.subscription_id, "tenantId": TARGET.tenant_id,
                        "state": "Enabled", "cloud": "AzureCloud"}
        self.permissions = [{"actions": ["Microsoft.Kusto/clusters/*"], "notActions": []}]
        self.cluster = {"id": TARGET.resource_id, "name": TARGET.cluster, "location": TARGET.location,
                        "state": "Running", "provisioningState": "Succeeded", "enableAutoStop": True,
                        "uri": TARGET.endpoint, "protectedSettings": {"enableStreamingIngest": True}}
        self.revert_auto_stop = False
        self.wait_completes = True
        self.drift_protected = False

    def __call__(self, *arguments, **options):
        self.calls.append(arguments)
        if arguments[:2] == ("account", "show"):
            return self.account
        if arguments[:3] == ("rest", "--method", "get"):
            return self.permissions
        if arguments[:3] == ("rest", "--method", "patch"):
            if not self.revert_auto_stop:
                self.cluster["enableAutoStop"] = False
            if self.drift_protected:
                self.cluster["protectedSettings"]["enableStreamingIngest"] = False
            return None
        operation = arguments[:3]
        if operation == ("kusto", "cluster", "show"):
            return copy.deepcopy(self.cluster)
        if operation == ("kusto", "cluster", "start"):
            self.cluster.update(state="Starting", provisioningState="Running")
            return None
        if operation == ("kusto", "cluster", "wait"):
            if self.wait_completes:
                self.cluster.update(state="Running", provisioningState="Succeeded")
            return None
        raise AssertionError(f"Unexpected Azure operation: {arguments}")

    def mutations(self):
        return [call for call in self.calls if call[:3] in {
            ("kusto", "cluster", "start"), ("rest", "--method", "patch")
        }]


class AdxLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.cli = FakeAzure()
        self.runner = module.AdxLifecycle(TARGET, self.cli)

    def apply(self):
        return self.runner.run("keep-running", TARGET.resource_id)

    def test_plan_is_read_only_and_names_billing_and_schedule_limits(self):
        self.cli.cluster["protectedSettings"] = {"publicNetworkAccess": "Disabled", "enableStreamingIngest": True}
        result = self.runner.run("plan")
        self.assertEqual(result["confirmation_required"], TARGET.resource_id)
        self.assertEqual(result["before"]["protectedSettings"], self.cli.cluster["protectedSettings"])
        self.assertTrue(result["continuous_billing"])
        self.assertEqual(result["external_stop_schedules"], "unknown")
        self.assertEqual(self.cli.mutations(), [])

    def test_confirmation_required_before_any_cli_call(self):
        for confirmation in (None, "", TARGET.resource_id + "/databases/Events"):
            with self.subTest(confirmation=confirmation), self.assertRaises(module.DeploymentError):
                self.runner.run("keep-running", confirmation)
        self.assertEqual(self.cli.calls, [])

    def test_unknown_and_destructive_actions_refuse_before_cli(self):
        for action in ("stop", "teardown", "create", "delete", "restart"):
            with self.subTest(action=action), self.assertRaises(module.DeploymentError):
                self.runner.run(action, TARGET.resource_id)
        self.assertEqual(self.cli.calls, [])

    def test_mismatched_account_cannot_mutate(self):
        for field in ("id", "tenantId", "state", "cloud"):
            original = self.cli.account[field]
            self.cli.account[field] = "wrong"
            with self.subTest(field=field), self.assertRaises(module.DeploymentError):
                self.apply()
            self.cli.account[field] = original
        self.assertEqual(self.cli.mutations(), [])

    def test_missing_or_excluded_write_permission_refuses(self):
        for permissions in ([{"actions": ["*/read"], "notActions": []}],
                            [{"actions": ["*"], "notActions": ["*/write"]}]):
            self.cli.permissions = permissions
            with self.subTest(permissions=permissions), self.assertRaises(module.DeploymentError):
                self.apply()
        self.assertEqual(self.cli.mutations(), [])

    def test_wrong_resource_location_or_endpoint_refuses(self):
        for field in ("id", "name", "location", "uri"):
            original = self.cli.cluster[field]
            self.cli.cluster[field] = "wrong"
            with self.subTest(field=field), self.assertRaises(module.DeploymentError):
                self.apply()
            self.assertEqual(self.runner.last_observed[field], "wrong")
            self.cli.cluster[field] = original
        self.assertEqual(self.cli.mutations(), [])

    def test_unsupported_transition_refuses(self):
        for state in ("Stopping", "Deleting", "Creating", "Unavailable", "Updating"):
            self.cli.cluster["state"] = state
            with self.subTest(state=state), self.assertRaises(module.DeploymentError):
                self.apply()
        self.assertEqual(self.cli.mutations(), [])

    def test_azure_display_location_matches_canonical_region(self):
        self.cli.cluster["location"] = "Australia East"
        self.assertTrue(self.apply()["read_back_verified"])

    def test_failed_provisioning_refuses(self):
        self.cli.cluster["provisioningState"] = "Failed"
        with self.assertRaises(module.DeploymentError):
            self.apply()
        self.assertEqual(self.cli.mutations(), [])

    def test_starting_waits_before_disabling_auto_stop(self):
        self.cli.cluster.update(state="Starting", provisioningState="Running")
        result = self.apply()
        operations = [call[:3] for call in self.cli.calls]
        self.assertLess(operations.index(("kusto", "cluster", "wait")),
                        operations.index(("rest", "--method", "patch")))
        self.assertNotIn(("kusto", "cluster", "start"), operations)
        self.assertTrue(result["read_back_verified"])
        self.assertFalse(result["after"]["enableAutoStop"])

    def test_stopped_starts_then_waits_then_updates(self):
        self.cli.cluster["state"] = "Stopped"
        result = self.apply()
        self.assertEqual([call[:3] for call in self.cli.mutations()],
                         [("kusto", "cluster", "start"), ("rest", "--method", "patch")])
        self.assertEqual(result["after"]["state"], "Running")

    def test_stopped_requires_start_permission(self):
        self.cli.cluster["state"] = "Stopped"
        self.cli.permissions[0]["notActions"] = ["*/start/action"]
        with self.assertRaises(module.DeploymentError):
            self.apply()
        self.assertEqual(self.cli.mutations(), [])

    def test_wait_without_ready_readback_cannot_update(self):
        self.cli.cluster.update(state="Starting", provisioningState="Running")
        self.cli.wait_completes = False
        with self.assertRaises(module.DeploymentError):
            self.apply()
        self.assertEqual(self.cli.mutations(), [])

    def test_update_is_exactly_one_field_with_explicit_subscription(self):
        self.apply()
        update, = self.cli.mutations()
        self.assertEqual(update[:3], ("rest", "--method", "patch"))
        self.assertEqual(update[update.index("--url") + 1],
                         f"https://management.azure.com{TARGET.resource_id}?api-version=2022-02-01")
        self.assertEqual(update[update.index("--subscription") + 1], TARGET.subscription_id)
        self.assertEqual(json.loads(update[update.index("--body") + 1]), {"properties": {"enableAutoStop": False}})

    def test_protected_setting_drift_never_reports_success(self):
        self.cli.drift_protected = True
        with self.assertRaises(module.DeploymentError):
            self.apply()

    def test_policy_reversion_cannot_claim_success(self):
        self.cli.revert_auto_stop = True
        with self.assertRaises(module.DeploymentError):
            self.apply()

    def test_repeat_run_is_noop_and_verify_is_read_only(self):
        self.apply()
        result = self.apply()
        self.assertEqual(result["action"], "unchanged")
        verified = self.runner.run("verify")
        self.assertTrue(verified["read_back_verified"])
        self.assertEqual(len(self.cli.mutations()), 1)

    def test_verify_requires_running_and_auto_stop_false(self):
        with self.assertRaises(module.DeploymentError):
            self.runner.run("verify")
        self.cli.cluster.update(enableAutoStop=False, state="Stopped")
        with self.assertRaises(module.DeploymentError):
            self.runner.run("verify")
        self.assertEqual(self.cli.mutations(), [])

    def test_configuration_refuses_unknown_duplicate_or_secret_fields(self):
        data = dict(TARGET.__dict__)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "target.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            self.assertEqual(module.AdxTarget.load(path), TARGET)
            for text in (json.dumps({**data, "credential": "not-a-credential"}),
                         json.dumps(data)[:-1] + ', "cluster": "another"}',
                         json.dumps({**data, "endpoint": "http://localhost"})):
                path.write_text(text, encoding="utf-8")
                with self.subTest(text=text), self.assertRaises(module.DeploymentError):
                    module.AdxTarget.load(path)


if __name__ == "__main__":
    unittest.main()