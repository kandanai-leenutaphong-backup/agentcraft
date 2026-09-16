from hashlib import sha256
from pathlib import Path
import json
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from azure_extraction.contracts import (
    Document,
    Refusal,
    artifact_path,
    authorize_verified_claims,
    documents_from_manifest,
    require_content,
    require_method,
    validate_endpoint,
    validate_input,
)


TENANT = "c79ab2bb-79cb-47f1-b4da-b6852fe45ff7"
PRINCIPAL = "11111111-1111-4111-8111-111111111111"


class ContractTests(unittest.TestCase):
    def test_only_immutable_authorized_pdfs(self):
        root = Path(__file__).resolve().parents[2] / "source_data"
        documents = documents_from_manifest(json.loads((root / "manifest.json").read_text()))
        for document in documents.values():
            payload = (root / document.file).read_bytes()
            validate_input(payload, document)
            with self.assertRaises(Refusal):
                validate_input(payload + b"changed", document)
        self.assertEqual(set(documents), {"yallourn", "murray"})

    def test_pdf_signature_and_digest_refuse(self):
        payload = b"not a PDF"
        document = Document("murray", "murray.pdf", sha256(payload).hexdigest(), len(payload))
        with self.assertRaises(Refusal):
            validate_input(payload, document)

    def test_explicit_principal_and_tenant(self):
        authorize_verified_claims({"tid": TENANT, "oid": PRINCIPAL}, TENANT, PRINCIPAL)
        for claims in ({}, {"tid": TENANT}, {"tid": PRINCIPAL, "oid": PRINCIPAL}, {"tid": TENANT, "oid": TENANT}):
            with self.assertRaises(Refusal):
                authorize_verified_claims(claims, TENANT, PRINCIPAL)

    def test_fixed_method_and_endpoint(self):
        self.assertEqual(require_method("content-understanding"), "prebuilt-layout")
        for method in ("document-intelligence-read", "document-intelligence-layout", "pymupdf", "markitdown", "../prebuilt-read", "https://elsewhere", "", "custom"):
            with self.assertRaises(Refusal):
                require_method(method)
        host = "owned.azurewebsites.net"
        self.assertEqual(validate_endpoint(f"https://{host}/", host), f"https://{host}")
        for endpoint in ("http://owned.azurewebsites.net", "https://owned.azurewebsites.net.evil", "https://evil@owned.azurewebsites.net", "https://owned.azurewebsites.net/?target=other", "https://127.0.0.1", "https://owned.azurewebsites.net/api/other"):
            with self.assertRaises(Refusal):
                validate_endpoint(endpoint, host)

    def test_artifact_traversal_refuses(self):
        self.assertEqual(artifact_path("content.txt"), "content.txt")
        for path in ("../outside", "/tmp/outside", "folder/../../outside", "folder\\outside", "https://elsewhere", "./native.json", "folder//native.json"):
            with self.assertRaises(Refusal):
                artifact_path(path)

    def test_no_empty_success(self):
        for native in ({}, {"status": "failed"}, {"result": {"contents": [{"markdown": "", "pages": [{}]}]}}, {"result": {"contents": [{"markdown": "observed", "pages": []}]}}):
            with self.assertRaises(Refusal):
                require_content(native, "content-understanding")
        native = {"result": {"contents": [{"markdown": "observed", "pages": [{}]}]}}
        self.assertEqual(require_content(native, "content-understanding"), ("observed", "observed", 1))


if __name__ == "__main__":
    unittest.main()