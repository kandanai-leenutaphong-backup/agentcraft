from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4
from time import time
from unittest.mock import patch
import json
import inspect
import sys
import unittest

from azure.core.credentials import AccessToken
import requests
from urllib3.response import HTTPResponse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from azure_extraction.client import FunctionPolling, invoke, save_result
from azure_extraction.contracts import Refusal


class ClientTests(unittest.TestCase):
    def test_real_sdk_pipeline_and_lro_with_fake_http(self):
        job_id = str(uuid4())
        endpoint = "https://owned.azurewebsites.net"
        config = {"function_endpoint": endpoint, "function_host": "owned.azurewebsites.net",
                  "subscription_id": "fixture", "tenant_id": "fixture", "api_client_id": "fixture"}
        observed = []
        request_signature = inspect.signature(requests.Session.request)

        class Credential:
            def get_token(self, *scopes, **kwargs):
                return AccessToken("offline-fixture-no-credential", int(time()) + 300)

        def send(session, method, url, **kwargs):
            request_signature.bind(session, method, url, **kwargs)
            observed.append((method, url, kwargs["headers"]))
            response = requests.Response()
            response.status_code = 202 if method == "POST" else 200
            response.url = url
            response.request = requests.Request(method, url, headers=dict(kwargs["headers"])).prepare()
            body = {"status": "Running"} if method == "POST" else {"status": "Succeeded", "id": job_id, "native": {"complete": True}}
            response._content = json.dumps(body).encode()
            response._content_consumed = True
            response.raw = HTTPResponse(body=response._content, status=response.status_code)
            response.headers["Content-Type"] = "application/json"
            if method == "POST":
                response.headers["Operation-Location"] = endpoint + "/api/jobs/" + job_id
            return response

        with patch("azure_extraction.client.account_matches"), patch("azure_extraction.client.AzureCliCredential", return_value=Credential()), patch.object(requests.Session, "request", send):
            result, polls = invoke(config, "content-understanding", "murray", b"%PDF-fixture", job_id)
        self.assertEqual(result["status"], "Succeeded")
        self.assertEqual(polls, 1)
        self.assertEqual([item[0] for item in observed], ["POST", "GET"])
        self.assertTrue(all("x-ms-client-request-id" in item[2] for item in observed))

    def test_retired_methods_refused_before_client_creation(self):
        with patch("azure_extraction.client.function_client") as create_client:
            for method in ("document-intelligence-read", "document-intelligence-layout", "pymupdf", "markitdown"):
                with self.subTest(method=method), self.assertRaises(Refusal):
                    invoke({}, method, "murray", b"%PDF-fixture", str(uuid4()))
            create_client.assert_not_called()

    def test_polling_cannot_escape_frozen_function(self):
        polling = FunctionPolling("https://owned.azurewebsites.net", str(uuid4()))
        for url in ("https://evil.example/api/jobs/id", polling.expected_url + "?target=other", polling.expected_url.replace("https:", "http:")):
            with self.assertRaises(Refusal):
                polling.request_status(url)

    def test_expired_polling_is_bounded(self):
        polling = FunctionPolling("https://owned.azurewebsites.net", str(uuid4()), limit_seconds=-1)
        with self.assertRaises(TimeoutError):
            polling.request_status(polling.expected_url)

    def receipt(self):
        return {"method": "content-understanding", "status": "failed", "outputs": {"text": None, "markdown": None, "native": None},
                "input": {"pages": None}, "provider": {}, "versions": {}, "warnings": [], "error": None}

    def test_preserves_complete_native_and_unmodified_content(self):
        native = {"status": "succeeded", "result": {"contents": [{"markdown": "# Provider\n<table>native</table>", "pages": [{}], "extraEvidence": [1, 2, 3]}]}}
        content = native["result"]["contents"][0]["markdown"]
        result = {"status": "Succeeded", "native": native, "text": content, "markdown": content, "pages": 1,
                  "provider": {"api_version": "2025-11-01", "model_id": "prebuilt-layout"}, "versions": {"python": "fixture"}}
        receipt = self.receipt()
        with TemporaryDirectory() as temporary:
            directory = Path(temporary)
            save_result(directory, result, receipt)
            self.assertEqual(json.loads((directory / "native.json").read_text()), native)
            self.assertEqual((directory / "content.txt").read_text(), content)
            self.assertEqual((directory / "content.md").read_text(), content)
            self.assertEqual(receipt["status"], "succeeded")
            self.assertEqual(receipt["input"]["pages"], 1)

    def test_failed_result_retains_native_without_empty_success(self):
        receipt = self.receipt()
        with TemporaryDirectory() as temporary:
            save_result(Path(temporary), {"status": "Failed", "native": {"status": "failed"}}, receipt)
            self.assertEqual(receipt["status"], "failed")
            self.assertEqual(receipt["outputs"], {"text": None, "markdown": None, "native": "native.json"})
            self.assertIsNotNone(receipt["error"])


if __name__ == "__main__":
    unittest.main()