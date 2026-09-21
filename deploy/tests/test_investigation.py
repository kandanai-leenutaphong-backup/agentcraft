import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from investigation import DeploymentError, InvestigationDeployment, PROVIDERS, load_config
import investigation

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

    def test_manual_release_updates_only_existing_app_and_preserves_auth(self):
        self.deployment.manual_evidence = Path("/manual/evidence")
        self.deployment.group.preflight = Mock(return_value={})
        self.deployment.group.snapshot = Mock(return_value={})
        runtime = self.config["runtime"]
        before = {"id": self.deployment.target.resource_id + "/providers/Microsoft.App/containerApps/" + self.config["names"]["app"],
            "identity": {}, "registries": [], "secrets": [], "scale": {"maxReplicas": 1},
            "ingress": {"external": True, "allowInsecure": False},
            "containers": [{"name": "app", "image": "old", "env": [{"name": key, "value": value} for key, value in {
                "AUTH_TENANT_ID": self.config["tenant_id"], "AUTH_CLIENT_ID": runtime["client_id"],
                "AUTH_PUBLIC_ORIGIN": runtime["origin"], "DEV_PUBLIC_KEY_ED25519": runtime["public_key"],
                "DEV_REPLAY_LEDGER": "azure-table", "CYBEREYE_ALLOWED_PRINCIPAL_IDS":
                f"entra:{self.config['tenant_id']}:{runtime['owner_object_id']},devkey:{runtime['fingerprint']}:default"}.items()]}]}
        image = self.config["names"]["registry"] + ".azurecr.io/investigation@sha256:" + "a" * 64
        protected = copy.deepcopy(before)
        protected["ingress"]["external"] = False
        after = copy.deepcopy(protected)
        after["containers"][0]["image"] = image
        self.deployment.cli = Mock(return_value={})
        self.deployment.app_status = Mock(side_effect=[before, protected, after])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "build.json"
            path.write_text(json.dumps({"status": "image-built", "image": image}))
            self.assertEqual(self.deployment.private_release(path)["status"], "private-app-deployed")
            calls = [call.args for call in self.deployment.cli.call_args_list]
            self.assertEqual(len(calls), 2)
            self.assertEqual(calls[0][:3], ("containerapp", "ingress", "enable"))
            self.assertIn("internal", calls[0])
            self.assertEqual(calls[1][:2], ("containerapp", "update"))
            self.deployment.cli.reset_mock()
            self.deployment.app_status = Mock(side_effect=[after, after, after])
            self.deployment.private_release(path)
            self.assertEqual(self.deployment.cli.call_count, 1)
            before["containers"][0]["env"] = []
            self.deployment.app_status = Mock(return_value=before)
            self.deployment.cli.reset_mock()
            with self.assertRaisesRegex(DeploymentError, "authentication"):
                self.deployment.private_release(path)
            self.deployment.cli.assert_not_called()

    def test_secret_reference_empty_value_normalization_preserves_refusals(self):
        before = [{"name": "GRAPH_KEY", "secretRef": "graph-readonly"}]
        normalized = [{"name": "GRAPH_KEY", "secretRef": "graph-readonly", "value": ""}]
        self.assertEqual(investigation.protected_environment(before), investigation.protected_environment(normalized))
        for changed in ({"name": "GRAPH_KEY", "secretRef": "other", "value": ""},
                        {"name": "GRAPH_KEY", "secretRef": "graph-readonly", "value": "not-empty"}):
            self.assertNotEqual(investigation.protected_environment(before), investigation.protected_environment([changed]))
        with self.assertRaises(DeploymentError):
            investigation.protected_environment(before + before)

    def test_private_probe_diagnostic_is_valid_and_payload_free(self):
        command = investigation.private_probe_command()
        source = bytes.fromhex(command.split("'")[1]).decode()
        compile(source, "private_probe", "exec")
        self.assertIn("traceback.extract_tb", source)
        self.assertNotIn("str(error)", source)
        self.assertNotIn("frame.locals", source)
        self.assertIn("private_probe()", source)

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


class ManualAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.project = self.root / "project"
        self.evidence = self.root / "demonstration_project/agentcraft_projects/manual_notes/20260921T051248Z-manual-deployment/evidence"
        self.evidence.mkdir(parents=True)
        (self.project / "constitution").mkdir(parents=True)
        (self.project / "constitution/constitution.yaml").write_text("revision: 10\n")
        self.constitution = hashlib.sha256((self.project / "constitution/constitution.yaml").read_bytes()).hexdigest()
        (self.project / "records/v2").mkdir(parents=True)
        self.original = self.project / "records/v2/original.json"
        self.original.write_text(json.dumps({"id": "user-directed-conciseness-deploy-20260921-decision",
            "record_type": "decision", "project_id": "project", "constraints": ["Deploy rg-agentcraft-dev"]}))
        self.path = self.project / "records/v2/decision.json"
        self.record = {"id": "manual-deploy-runner-20260921-decision", "record_type": "decision", "project_id": "project",
            "constitution": {"sha256": self.constitution}, "manual_task": {
                "active_constitution_sha256": self.constitution,
                "historical_constitution_sha256": investigation.CONSTITUTION_SHA256,
                "evidence_root": str(self.evidence.relative_to(self.root)),
                "build_receipt_scope": str(self.evidence.relative_to(self.root))},
            "record_refs": [{"relation": "earlier-user-directed-decision", "path": "records/v2/original.json",
                "sha256": hashlib.sha256(self.original.read_bytes()).hexdigest()}]}
        self.addCleanup(patch.stopall)
        patch.object(investigation, "ROOT", self.root).start()
        patch.object(investigation, "PROJECT", self.project).start()

    def verify(self):
        self.path.write_text(json.dumps(self.record))
        return investigation.verify_manual_authority(self.path, hashlib.sha256(self.path.read_bytes()).hexdigest(),
                                                     self.constitution, self.evidence)

    def test_explicit_manual_authority_preserves_historical_refusal(self):
        self.assertEqual(self.verify()["authority"], "explicit-user-manual-task")
        with self.assertRaisesRegex(DeploymentError, "Pinned source changed"):
            investigation.verify_pins()
        self.assertEqual(investigation.CONSTITUTION_SHA256, "070cadee2c44731d1b984dafc906a6bba2f2797de1bd2530474ef5777b8c0e37")

    def test_wrong_record_type_project_scope_and_constitution_refuse(self):
        for key in ("record_type", "project_id", "id"):
            with self.subTest(key=key):
                original = self.record[key]
                self.record[key] = "foreign"
                with self.assertRaises(DeploymentError):
                    self.verify()
                self.record[key] = original
        self.record["manual_task"]["active_constitution_sha256"] = "0" * 64
        with self.assertRaisesRegex(DeploymentError, "provenance"):
            self.verify()

    def test_missing_tampered_hash_and_foreign_receipts_refuse(self):
        self.verify()
        for digest in (None, "", "0" * 64):
            with self.assertRaises(DeploymentError):
                investigation.checked_receipt(self.path, digest, self.project)
        with self.assertRaises(OSError):
            investigation.checked_receipt(self.project / "missing.json", "a" * 64, self.project)
        with self.assertRaises(DeploymentError):
            investigation.checked_receipt(self.path, hashlib.sha256(self.path.read_bytes()).hexdigest(), self.evidence)
        self.original.write_text("{}")
        with self.assertRaisesRegex(DeploymentError, "SHA-256 mismatch"):
            self.verify()

    def test_symlink_traversal_and_other_task_refuse(self):
        linked = self.evidence / "linked"
        linked.symlink_to(self.project, target_is_directory=True)
        for path in (linked / "records/v2/original.json", self.evidence / ".." / "evidence/file"):
            with self.assertRaises(DeploymentError):
                investigation.confined_path(path, self.evidence)
        self.record["manual_task"]["evidence_root"] = "demonstration_project/agentcraft_projects/manual_notes/other/evidence"
        with self.assertRaises(DeploymentError):
            self.verify()


if __name__ == "__main__":
    unittest.main()