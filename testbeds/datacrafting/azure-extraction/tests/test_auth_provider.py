from pathlib import Path
from time import time
from uuid import uuid4
import sys
import unittest

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from azure_extraction.auth import AuthenticationError, CLI_CLIENT_ID, JwtGate
from azure_extraction.contracts import Refusal
from azure_extraction.provider import NativeProvider, ProviderError


TENANT = "c79ab2bb-79cb-47f1-b4da-b6852fe45ff7"
PRINCIPAL = "11111111-1111-4111-8111-111111111111"
AUDIENCE = "22222222-2222-4222-8222-222222222222"


class AuthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    def setUp(self):
        self.gate = JwtGate(TENANT, PRINCIPAL, AUDIENCE, lambda token: self.key.public_key())
        self.claims = {"aud": AUDIENCE, "iss": self.gate.issuer, "tid": TENANT, "oid": PRINCIPAL,
                       "azp": CLI_CLIENT_ID, "scp": "access_as_user", "exp": int(time()) + 300,
                       "iat": int(time()), "nbf": int(time()) - 1}

    def token(self, claims=None, key=None):
        return "Bearer " + jwt.encode(claims or self.claims, key or self.key, algorithm="RS256", headers={"kid": "fixture"})

    def test_authorized_jwt(self):
        self.assertEqual(self.gate.authenticate(self.token())["oid"], PRINCIPAL)

    def test_unauthorized_tokens_and_claims(self):
        for authorization in (None, "", "Bearer malformed", self.token(key=self.other_key)):
            with self.assertRaises(AuthenticationError):
                self.gate.authenticate(authorization)
        for field, value in (("tid", AUDIENCE), ("oid", AUDIENCE), ("aud", PRINCIPAL), ("iss", "https://untrusted"),
                             ("exp", int(time()) - 60), ("nbf", int(time()) + 60), ("scp", ""), ("azp", AUDIENCE)):
            with self.subTest(field=field), self.assertRaises(Refusal):
                self.gate.authenticate(self.token({**self.claims, field: value}))
        unsigned = jwt.encode(self.claims, "", algorithm="none", headers={"kid": "fixture"})
        with self.assertRaises(AuthenticationError):
            self.gate.authenticate("Bearer " + unsigned)


class FakeResponse:
    def __init__(self, status, body=None, headers=None):
        self.status_code = status
        self.body = body or {}
        self.headers = headers or {}

    def json(self):
        return self.body


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.response = FakeResponse(200)
        self.provider = NativeProvider(None, "cu-owned.services.ai.azure.com", self.send)

    def send(self, request, **kwargs):
        self.assertNotIn("logging_enable", kwargs)
        self.calls.append(request)
        return self.response

    def test_native_method_and_binary_body(self):
        method = "content-understanding"
        operation_id = str(uuid4())
        url = f"{self.provider.endpoint(method)}{self.provider.operation_path(method, operation_id)}?api-version={self.provider.descriptor(method)['api_version']}"
        self.response = FakeResponse(202, headers={"Operation-Location": url})
        self.assertEqual(self.provider.begin(method, b"%PDF-authorized"), operation_id)
        self.assertEqual(self.calls[-1].content, b"%PDF-authorized")
        self.assertNotIn("urlSource", self.calls[-1].url)
        self.assertIn("prebuilt-layout:analyzeBinary?api-version=2025-11-01", self.calls[-1].url)

    def test_retired_methods_refused_before_calls(self):
        for method in ("document-intelligence-read", "document-intelligence-layout", "pymupdf", "markitdown"):
            with self.subTest(method=method):
                with self.assertRaises(Refusal):
                    self.provider.begin(method, b"%PDF-authorized")
                with self.assertRaises(Refusal):
                    self.provider.poll(method, str(uuid4()))
        self.assertEqual(self.calls, [])

    def test_operation_target_injection_refused(self):
        operation_id = str(uuid4())
        base = f"https://cu-owned.services.ai.azure.com/contentunderstanding/analyzerResults/{operation_id}?api-version=2025-11-01"
        for location in (base.replace("cu-owned.services.ai.azure.com", "evil.example"), base.replace("/analyzerResults/", "/analyzers/prebuilt-layout/"), base.replace("2025-11-01", "2024-11-30"), base + "&target=elsewhere", base.replace(operation_id, "../other"), base.replace("https:", "http:")):
            with self.assertRaises(Refusal):
                self.provider.operation_id("content-understanding", location)
        self.assertEqual(self.calls, [])

    def test_failure_is_not_success_and_unknown_state_refuses(self):
        self.response = FakeResponse(403, {"error": {"code": "Forbidden", "message": "private payload must not enter errors"}})
        with self.assertRaises(ProviderError) as context:
            self.provider.begin("content-understanding", b"%PDF-")
        self.assertEqual(str(context.exception), "Native service HTTP 403: Forbidden")
        self.response = FakeResponse(200, {"status": "unexpected"})
        with self.assertRaises(Refusal):
            self.provider.poll("content-understanding", str(uuid4()))


if __name__ == "__main__":
    unittest.main()