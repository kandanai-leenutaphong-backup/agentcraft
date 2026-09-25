import importlib.util
import json
import copy
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location("evaluation_runner", Path(__file__).resolve().parents[1] / "deploy/experiment.py")
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)
from foundry_ops.core import UnresolvedIntentError  # noqa: E402  (path set by runner)


class SafetyTests(unittest.TestCase):
    def test_definition_service_fields_preserve_exact_requested_criterion(self):
        criterion = {"name": "Coherence", "type": "azure_ai_evaluator", "evaluator_version": "12", "data_mapping": {"response": "{{sample.output_text}}"}}
        actual = dict(criterion, id="service-id", input=None, labels=None, model=None, passing_labels=None)
        runner.definition_check({"id": "eval", "testing_criteria": [actual]}, "eval", criterion)
        for key, value in (("evaluator_version", "13"), ("data_mapping", {}), ("model", "foreign"), ("extra", None)):
            with self.assertRaises(ValueError):
                runner.definition_check({"id": "eval", "testing_criteria": [dict(actual, **{key: value})]}, "eval", criterion)

    def test_catalogue_timestamp_normalization_preserves_contract(self):
        expected = {"name": "builtin.coherence", "version": "12", "definition": {"metrics": {"coherence": {"type": "ordinal"}}}, "created_at": "listed", "modified_at": "listed"}
        actual = dict(expected, created_at="retrieved", modified_at="retrieved")
        self.assertEqual(runner.evaluator_contract(actual), runner.evaluator_contract(expected))
        for key, value in (("version", "13"), ("definition", {}), ("name", "foreign")):
            self.assertNotEqual(runner.evaluator_contract(dict(actual, **{key: value})), runner.evaluator_contract(expected))

    def test_fresh_manifest_binding_and_changed_host_refusal(self):
        manifest = json.loads((runner.DEPLOY / "env/migration-e-v1.json").read_text())
        original_decision = (runner.DEPLOY / "records/approved-decision.json").read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            deploy = root / "evaluation/deploy"
            host = root / "host"
            (deploy / "env").mkdir(parents=True)
            (deploy / "records").mkdir()
            (deploy / "records/approved-decision.json").write_bytes(original_decision)
            constitution = root / "constitution.yaml"
            constitution.write_text("fixture constitution\n")
            manifest["constitution_sha256"] = runner.digest(constitution)
            path = deploy / "env/migration-e-v1.json"
            path.write_text(json.dumps(manifest))
            hosted = host / "deploy/records/migration-h-v1/deploy.json"
            hosted.parent.mkdir(parents=True)
            hosted.write_text(json.dumps({"action": "deploy", "status": "complete", "target": {"project_endpoint": runner.DECISION["endpoint"]},
                "result": {"agent": manifest["agent"], "version": "1", "image": "registry/image@sha256:synthetic",
                    "source": {"sha256": "source", "files": {"app/configuration.yaml": "config"}}}}))
            with patch.object(runner, "DEPLOY", deploy), patch.object(runner, "HOST", host), \
                 patch.object(runner, "CONSTITUTION", constitution), \
                 patch.object(runner, "RECORDS", runner.RECORDS), patch.object(runner, "DECISION", dict(runner.DECISION)), \
                 patch.object(runner, "PINS", dict(runner.PINS)), patch.object(runner, "RUN_MANIFEST", None), \
                 patch.object(runner, "DATASET_PATH", runner.DATASET_PATH), patch.object(runner, "DATASET_NAME", runner.DATASET_NAME), \
                 patch.object(runner, "DATASET_VERSION", runner.DATASET_VERSION), patch.object(runner, "NAME", runner.NAME), \
                 patch.object(runner.ORACLE, "ROOT", runner.ORACLE.ROOT):
                result = runner.configure_run(path, runner.digest(path), "manifest-check", hosted, runner.digest(hosted))
                self.assertEqual(result["pins"]["agent_name"], manifest["agent"])
                self.assertEqual(runner.local_validate()["rows"], 3)
                self.assertEqual(runner.configure_run(path, runner.digest(path), "manifest-check"), result)
                with self.assertRaises(ValueError):
                    runner.configure_run(path, runner.digest(path), "upload", hosted, "0" * 64)
                constitution.write_text("edited constitution\n")
                with self.assertRaisesRegex(ValueError, "constitution_sha256"):
                    runner.configure_run(path, runner.digest(path), "manifest-check")

    def test_public_request_models_preserve_version_mapping(self):
        from azure.ai.projects.models import TestingCriterionAzureAIEvaluator, TargetCompletionEvalRunDataSource, AzureAIAgentTargetParam
        criterion = {"type": "azure_ai_evaluator", "name": "Coherence", "evaluator_name": "builtin.coherence",
            "evaluator_version": "2", "initialization_parameters": {"deployment_name": "judge"},
            "data_mapping": {"query": "{{item.query}}", "response": "{{sample.output_text}}"}}
        self.assertEqual(TestingCriterionAzureAIEvaluator(criterion), criterion)
        target = {"type": "azure_ai_agent", "name": "canary", "version": "1"}
        self.assertEqual(AzureAIAgentTargetParam(target), target)
        source = {"type": "azure_ai_target_completions", "target": target, "source": {"type": "file_id", "id": "dataset"}}
        self.assertEqual(TargetCompletionEvalRunDataSource(source), source)

    def test_unknown_reservation_never_repeated(self):
        from unittest.mock import MagicMock
        from azure.core.exceptions import ResourceNotFoundError
        project = MagicMock()
        project.datasets.get.side_effect = ResourceNotFoundError()
        project.datasets.pending_upload.side_effect = TimeoutError("unknown reservation")
        with tempfile.TemporaryDirectory() as directory, patch.object(runner, "RECORDS", Path(directory)), \
             patch.object(runner, "RUN_MANIFEST", {"series": "migration-test"}), patch.object(runner, "selection_check"):
            for name in ("approved-decision.json", "run-manifest.json"):
                (Path(directory) / name).write_text("{}")
            with self.assertRaises(TimeoutError):
                runner.upload(project)
            with self.assertRaises(UnresolvedIntentError):
                runner.upload(project)
        self.assertEqual(project.datasets.pending_upload.call_count, 1)

    def test_manifest_refuses_drift_and_consumed_action(self):
        path = runner.DEPLOY / "env/migration-e-v1.json"
        with self.assertRaises(ValueError):
            runner.configure_run(path, "0" * 64, "upload")
        with self.assertRaises(ValueError):
            runner.configure_run(path, runner.digest(path), "register-existing")

    def test_strict_result_acceptance(self):
        retained = runner.read_record("20260922T075532691203Z-reconcile.json")["result"]
        criterion = runner.read_record("definition-intent.json")["request"]["testing_criteria"]
        def model(value):
            return SimpleNamespace(**value, model_dump=lambda **kwargs: value)
        def collect(value, extra=False):
            pages = [SimpleNamespace(data=[model(row) for row in value["items"]], last_id="last")]
            if extra:
                pages.append(SimpleNamespace(data=[model(dict(value["items"][0], id="surplus"))], last_id="surplus"))
            pager = SimpleNamespace(iter_pages=lambda: iter(pages))
            client = SimpleNamespace(evals=SimpleNamespace(retrieve=lambda identifier: model({"id": identifier, "testing_criteria": criterion}),
                runs=SimpleNamespace(output_items=SimpleNamespace(list=lambda **kwargs: pager))))
            return runner.collect(client, value["identity"], model(value["aggregate"]))
        result = collect(copy.deepcopy(retained))
        self.assertTrue(result["accepted"])
        self.assertFalse(result["criterion_passed"])
        for field, value in (("status", "failed"), ("error", {"code": "failed"}), ("eval_id", "foreign")):
            changed = copy.deepcopy(retained)
            changed["items"][0][field] = value
            self.assertFalse(collect(changed)["accepted"])
        for field, value in (("score", True), ("score", float("nan")), ("score", float("inf")),
                             ("name", "foreign"), ("metric", "foreign"), ("status", "skipped"),
                             ("evaluator_version", "foreign")):
            changed = copy.deepcopy(retained)
            changed["items"][0]["results"][0][field] = value
            self.assertFalse(collect(changed)["accepted"])
        changed = copy.deepcopy(retained)
        changed["aggregate"]["status"] = "cancelled"
        self.assertFalse(collect(changed)["accepted"])
        self.assertFalse(collect(retained, extra=True)["accepted"])

    def test_target_output_conflicts_and_bounds(self):
        for fields in ({"sample": {"output_text": "one", "output": [{"role": "assistant", "content": "two"}]}},
                       {"sample": {"output_text": "one"}, "datasource_item": {"sample.output_text": "two"}},
                       {"sample": {"output": [{"role": "assistant", "content": [{"type": "output_text", "text": 1}]}]}},
                       {"sample": None}, {"sample": {"output_text": "x" * 1000001}}):
            with self.assertRaises(ValueError):
                runner.sample_text(fields)
        self.assertEqual(runner.sample_text({"sample": {"output_text": "one"},
            "results": [{"sample": {"output_text": "judge"}}]}), "one")

    def pending(self, path="/container/folder/data%20set", credential_path="/container"):
        from azure.ai.projects.models import PendingUploadResponse
        return PendingUploadResponse({"pendingUploadId": "reservation", "pendingUploadType": "BlobReference",
            "version": runner.DATASET_VERSION, "blobReference": {
                "blobUri": "https://synthetic.blob.core.windows.net:443" + path,
                "storageAccountArmId": "/subscriptions/provider/resourceGroups/managed/providers/Microsoft.Storage/storageAccounts/synthetic",
                "credential": {"type": "SAS", "sasUri": "https://synthetic.blob.core.windows.net" + credential_path + "?sig=secret"}}})

    def test_documented_pending_model_and_container_relationship(self):
        pending = self.pending()
        self.assertEqual(pending.pending_upload_id, "reservation")
        location = runner.storage_location(pending.blob_reference, False)
        self.assertEqual(location["prefix"], "folder/data set")
        self.assertEqual(location["container"], "https://synthetic.blob.core.windows.net/container")
        self.assertEqual(runner.storage_location(self.pending("/container/").blob_reference, False)["prefix"], "")
        self.assertEqual(runner.storage_location(self.pending("/container/folder%2Fdata%2520set", "/%63ontainer/").blob_reference, False)["prefix"], "folder/data%20set")

    def test_storage_path_boundary_and_encoding_refusals(self):
        for path, credential in (("/container-other/path", "/container"), ("/container/%2e%2e/escape", "/container"),
                                 ("/container/folder", "/container/folder"), ("/container/path", "/container%2Fother"),
                                 ("/container/%00", "/container"), ("/container/%xx", "/container")):
            with self.subTest(path=path, credential=credential), self.assertRaises(ValueError):
                runner.storage_location(self.pending(path, credential).blob_reference, False)

    def test_metadata_retains_fields_without_credentials(self):
        pending = self.pending()
        pending.blob_reference.credential.sas_uri = "https://user:password@synthetic.blob.core.windows.net/container?sig=secret#fragment"
        result = runner.storage_metadata(pending)
        self.assertEqual(result["pending_upload_id"], "reservation")
        self.assertEqual(result["credential_type"], "SAS")
        self.assertEqual(result["credential_container"], "https://synthetic.blob.core.windows.net/container")
        self.assertNotIn("secret", json.dumps(result))
        self.assertNotIn("password", json.dumps(result))

    def test_service_error_sanitization(self):
        error = ValueError("Rejected https://user:pass@synthetic.blob.core.windows.net/container?sig=secret token=private")
        result = runner.error_summary(error)
        self.assertIn("Rejected", result["reason"])
        for secret in ("user:pass", "sig=secret", "private"):
            self.assertNotIn(secret, result["reason"])

    def test_sample_text_uses_output_not_input(self):
        self.assertEqual(runner.sample_text({"sample": {"output": [{"role": "assistant", "content": "proof"}]}}), "proof")
        self.assertEqual(runner.sample_text({"sample": {"output_text": "proof"}}), "proof")
        with self.assertRaises(ValueError):
            runner.sample_text({"datasource_item": {"sample.output_text": "fake"}})

    def test_retained_foundry_output_blocks(self):
        result = runner.read_record("20260922T075532691203Z-reconcile.json")["result"]
        runner.rows_check(result["items"])
        for item in result["items"]:
            text = runner.sample_text(item)
            self.assertEqual(text, item["datasource_item"]["sample.output_text"])
            self.assertTrue(runner.ORACLE.oracle(item["datasource_item"]["query"], text, runner.PINS))
        self.assertEqual([item["results"][0]["score"] for item in result["items"]], [4.0, 4.0, 2.0])

    def test_packet_oracle_controls(self):
        runner.ORACLE.validate()

    def test_unknown_write_cannot_repeat(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runner.reserve("run", {"name": "one"}, root)
            with self.assertRaises(UnresolvedIntentError):
                runner.reserve("run", {"name": "replacement"}, root)

    def test_evidence_path_refusal(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                runner.retain("../escape.json", {}, Path(directory))

    def test_dataset_identity(self):
        rows, digest = runner.ORACLE.rows()
        self.assertEqual(len(rows), 3)
        self.assertEqual(digest, runner.DECISION["dataset_sha256"])
        self.assertLessEqual(len(runner.DATASET_VERSION), 50)
        self.assertRegex(runner.DATASET_VERSION, r"^[A-Za-z0-9_.-]+$")

    def test_wrong_and_missing_pins(self):
        self.assertFalse(runner.ORACLE.oracle("0" * 32, json.dumps({"answer": "success"}), runner.PINS))
        self.assertFalse(runner.ORACLE.oracle("0" * 32, "{}", {}))

    def test_row_completeness(self):
        rows = [{"id": str(index), "datasource_item": row} for index, row in enumerate(runner.ORACLE.rows()[0])]
        runner.rows_check(rows)
        for invalid in (rows[:2], rows + rows[:1], [rows[0], rows[0], rows[2]],
                        rows[:2] + [{"id": "other", "datasource_item": {"query": "foreign"}}]):
            with self.assertRaises(ValueError):
                runner.rows_check(invalid)

    def test_storage_url_refuses_foreign_and_unsafe(self):
        arm = "/subscriptions/" + runner.DECISION["subscription"] + "/resourceGroups/synthetic/providers/Microsoft.Storage/storageAccounts/synthetic"
        self.assertEqual(runner.storage_url("https://synthetic.blob.core.windows.net/container?sig=secret", arm, False),
                         "https://synthetic.blob.core.windows.net/container")
        for url in ("http://synthetic.blob.core.windows.net/container", "https://evil.example/container",
                    "https://user@synthetic.blob.core.windows.net/container", "https://127.0.0.1/container"):
            with self.assertRaises(ValueError):
                runner.storage_url(url, arm, False)

    def test_sanitize_urls_and_credentials(self):
        result = runner.sanitize({"report_url": "https://example.test/report?sig=private#fragment", "credential": "secret"})
        self.assertEqual(result, {"report_url": "https://example.test/report"})

    def test_managed_storage_requires_project_provenance(self):
        arm = "/subscriptions/provider/resourceGroups/managed/providers/Microsoft.Storage/storageAccounts/synthetic"
        url = "https://synthetic.blob.core.windows.net/container?sig=secret"
        for origin in (None, "https://evil.example"):
            with self.assertRaises(ValueError):
                runner.storage_url(url, arm, False, origin)
        self.assertEqual(runner.storage_url(url, arm, False, runner.DECISION["endpoint"]), url.split("?")[0])
        self.assertEqual(runner.storage_url(url.replace(".net/", ".net:443/"), arm, False,
                           runner.DECISION["endpoint"]), url.split("?")[0])
        with self.assertRaises(ValueError):
            runner.storage_url("https://other.blob.core.windows.net/container", arm, False, runner.DECISION["endpoint"])

    def test_managed_storage_private_dns_refused(self):
        arm = "/subscriptions/provider/resourceGroups/managed/providers/Microsoft.Storage/storageAccounts/synthetic"
        with patch.object(runner.socket, "getaddrinfo", return_value=[(2, 1, 6, "", ("10.0.0.1", 443))]):
            with self.assertRaises(ValueError):
                runner.storage_url("https://synthetic.blob.core.windows.net/container", arm,
                                   service_origin=runner.DECISION["endpoint"])

    def test_project_response_provenance(self):
        for url in ("https://evil.example/datasets/name", runner.DECISION["endpoint"] + ".evil/datasets/name"):
            response = SimpleNamespace(http_response=SimpleNamespace(request=SimpleNamespace(url=url), status_code=200,
                headers={}, json=lambda: self.pending().as_dict()))
            with patch.object(runner, "retain") as retained, self.assertRaises(ValueError):
                runner.storage_response(response)
            self.assertEqual(retained.call_count, 1)

    def test_live_pin_guard(self):
        self.assertTrue(callable(runner.closeout))
        self.assertTrue(callable(runner.settled_closeout))
        value = {"version": "3", "status": "active", "metadata": dict(runner.PINS),
                 "definition": {"container_configuration": {"image": runner.DECISION["image"]}}}
        project = SimpleNamespace(agents=SimpleNamespace(get_version=lambda **kwargs: SimpleNamespace(as_dict=lambda: value)))
        self.assertEqual(runner.version_check(project)["version"], "3")
        for key, wrong in (("version", "2"), ("status", "creating"), ("metadata", {})):
            old = value[key]
            value[key] = wrong
            with self.assertRaises(ValueError):
                runner.version_check(project)
            value[key] = old
        value["definition"]["container_configuration"]["image"] = "foreign"
        with self.assertRaises(ValueError):
            runner.version_check(project)