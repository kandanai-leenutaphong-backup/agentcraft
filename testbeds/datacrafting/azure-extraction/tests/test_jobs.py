from copy import deepcopy
from pathlib import Path
from uuid import uuid4
import json
import sys
import unittest

import azure.functions as func

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import function_app
from azure_extraction.auth import AuthenticationError
from azure_extraction.contracts import Refusal, documents_from_manifest
from azure_extraction.jobs import ExtractionJobs, JobConflict, MissingJob
from azure_extraction.provider import ProviderError


class MemoryStore:
    def __init__(self):
        self.states = {}
        self.natives = {}

    def create(self, state):
        if state["id"] in self.states:
            return False
        self.states[state["id"]] = deepcopy(state)
        return True

    def read(self, job_id):
        if job_id not in self.states:
            raise MissingJob("Job not found")
        return deepcopy(self.states[job_id]), "etag"

    def replace(self, state, etag):
        self.states[state["id"]] = deepcopy(state)

    def save_native(self, job_id, native):
        self.natives[job_id] = deepcopy(native)

    def native(self, job_id):
        return deepcopy(self.natives[job_id])


class FakeProvider:
    def __init__(self):
        self.starts = 0
        self.failure = None
        self.result = {"status": "succeeded", "result": {"contents": [{"markdown": "complete provider text", "pages": [{}]}]}}

    def descriptor(self, method):
        return {"api_version": "fixture", "model_id": method}

    def begin(self, method, payload):
        self.starts += 1
        if self.failure:
            raise self.failure
        return str(uuid4())

    def poll(self, method, operation_id):
        return deepcopy(self.result)


class JobTests(unittest.TestCase):
    def setUp(self):
        self.source = Path(__file__).resolve().parents[2] / "source_data"
        self.documents = documents_from_manifest(json.loads((self.source / "manifest.json").read_text()))
        self.payload = (self.source / self.documents["murray"].file).read_bytes()
        self.provider = FakeProvider()
        self.store = MemoryStore()
        self.jobs = ExtractionJobs(self.documents, self.provider, self.store)
        self.job_id = str(uuid4())

    def begin(self, payload=None):
        return self.jobs.begin("content-understanding", "murray", self.job_id, self.payload if payload is None else payload, "operator")

    def test_begin_poll_and_immutable_native_readback(self):
        self.assertEqual(self.begin()["status"], "Running")
        self.assertEqual(self.begin()["status"], "Running")
        self.assertEqual(self.provider.starts, 1)
        result = self.jobs.poll(self.job_id, "operator")
        self.assertEqual(result["status"], "Succeeded")
        self.assertEqual(result["native"], self.provider.result)
        self.assertEqual(result["text"], "complete provider text")
        self.assertEqual(self.begin()["status"], "Succeeded")

    def test_wrong_input_and_other_owner_refused(self):
        with self.assertRaises(Refusal):
            self.begin(b"%PDF-unapproved")
        self.assertEqual(self.provider.starts, 0)
        self.begin()
        with self.assertRaises(MissingJob):
            self.jobs.poll(self.job_id, "other-operator")
        with self.assertRaises(JobConflict):
            self.jobs.begin("content-understanding", "yallourn", self.job_id, (self.source / self.documents["yallourn"].file).read_bytes(), "operator")

    def test_retired_methods_refused_before_provider_or_store(self):
        for method in ("document-intelligence-read", "document-intelligence-layout", "pymupdf", "markitdown"):
            with self.subTest(method=method), self.assertRaises(Refusal):
                self.jobs.begin(method, "murray", self.job_id, self.payload, "operator")
        self.assertEqual(self.provider.starts, 0)
        self.assertEqual(self.store.states, {})

    def test_unconfirmed_submission_never_resubmits(self):
        self.provider.failure = TimeoutError("may have applied")
        result = self.begin()
        self.assertEqual(result["status"], "Failed")
        self.assertIn("no automatic resubmission", result["error"]["message"])
        self.begin()
        self.assertEqual(self.provider.starts, 1)

    def test_provider_denial_and_empty_success_preserve_failure(self):
        self.provider.failure = ProviderError(403, "Forbidden")
        self.assertEqual(self.begin()["status"], "Failed")
        self.job_id = str(uuid4())
        self.provider.failure = None
        self.provider.result = {"status": "succeeded", "result": {"contents": [{"markdown": "", "pages": [{}]}]}}
        self.begin()
        result = self.jobs.poll(self.job_id, "operator")
        self.assertEqual(result["status"], "Failed")
        self.assertEqual(result["native"], self.provider.result)
        self.assertEqual(result["error"]["type"], "EmptyExtraction")

    def test_real_function_route_ignores_forged_principal_headers(self):
        class RefusingGate:
            def authenticate(self, authorization):
                raise AuthenticationError("missing bearer")
        previous = function_app._runtime
        function_app._runtime = ({}, RefusingGate(), self.jobs, "workload")
        try:
            for route in ("health", "jobs/" + self.job_id, "unknown", "static/secret"):
                request = func.HttpRequest("GET", "https://owned/api/" + route,
                    headers={"X-MS-CLIENT-PRINCIPAL-ID": "operator", "X-MS-CLIENT-PRINCIPAL": "forged"},
                    body=b"", route_params={"route": route})
                response = function_app.extract(request)
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.headers["Cache-Control"], "no-store, private")
        finally:
            function_app._runtime = previous

    def test_retired_function_routes_refuse_before_job_creation(self):
        class AuthorizedGate:
            def authenticate(self, authorization):
                return {"oid": "operator"}
        previous = function_app._runtime
        function_app._runtime = ({}, AuthorizedGate(), self.jobs, "workload")
        try:
            for method in ("document-intelligence-read", "document-intelligence-layout", "pymupdf", "markitdown"):
                request = func.HttpRequest("POST", f"https://owned/api/extract/{method}/murray/{self.job_id}",
                    headers={"Content-Type": "application/pdf"}, body=self.payload)
                response = function_app.extract(request)
                self.assertEqual(response.status_code, 403)
                self.assertEqual(response.headers["Cache-Control"], "no-store, private")
            self.assertEqual(self.provider.starts, 0)
            self.assertEqual(self.store.states, {})
        finally:
            function_app._runtime = previous

    def test_explicit_bindings_have_only_cu_status_and_health(self):
        bindings = json.loads((Path(function_app.__file__).parent / "function-bindings.json").read_text())
        self.assertEqual(bindings, {
            "ContentUnderstanding": {"route": "extract/content-understanding/{document_id}/{job_id}", "methods": ["post"]},
            "ExtractionStatus": {"route": "jobs/{job_id}", "methods": ["get"]},
            "ExtractionHealth": {"route": "health", "methods": ["get"]},
        })


if __name__ == "__main__":
    unittest.main()