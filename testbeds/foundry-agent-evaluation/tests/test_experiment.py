import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location("evaluation_runner", Path(__file__).resolve().parents[1] / "deploy/experiment.py")
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


class SafetyTests(unittest.TestCase):
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
        result = runner.error_details(error)
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
            with self.assertRaises(FileExistsError):
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
        result = runner.sanitized({"report_url": "https://example.test/report?sig=private#fragment", "credential": "secret"})
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