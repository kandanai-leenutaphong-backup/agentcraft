"""The authorization edge: everything is refused until something proves who is calling.

These tests are written from the outside, as a stranger. They assert on status codes and
headers rather than on internal state, because that is all an attacker gets and it is
therefore the only surface worth pinning down.

The application is the real one. Nothing here constructs a permissive copy of it.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.cybereye.backend import main as backend
from app.cybereye.backend.security import (
    PUBLIC_PROBE_PATH,
    SCOPE_KEY,
    SecurityConfigurationError,
    SecuritySettings,
    config as security_config,
)

import _auth_support

#: Every shape of path the application can be asked for. None of them is public.
PROTECTED_PATHS = [
    "/",
    "/index.html",
    "/assets/index-abc123.js",
    "/favicon.ico",
    "/api/health",
    "/api/cyber/sources",
    "/api/cyber/rules",
    "/api/cyber/scenarios",
    "/api/cyber/graph/status",
    "/api/cyber/inventory/tree",
    "/api/cyber/knowledge/type/anything",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/does/not/exist",
    "/../etc/passwd",
    "/api/../api/health",
]


class DenyByDefaultTests(unittest.TestCase):
    """No lifespan is entered: nothing that answers here needs the application to have started,
    which is itself the point — refusal happens before anything of the application runs."""

    def setUp(self) -> None:
        _auth_support.install(backend.app)
        self.client = TestClient(backend.app)

    def test_every_path_is_refused_to_a_stranger(self) -> None:
        with _auth_support.anonymous():
            for path in PROTECTED_PATHS:
                with self.subTest(path):
                    response = self.client.get(path)
                    self.assertEqual(response.status_code, 401)
                    self.assertEqual(response.content, b"")

    def test_every_method_is_refused(self) -> None:
        with _auth_support.anonymous():
            for method in ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"):
                with self.subTest(method):
                    response = self.client.request(method, "/api/cyber/scan", json={})
                    self.assertEqual(response.status_code, 401)

    def test_refusal_precedes_routing_so_an_unknown_path_is_not_a_404(self) -> None:
        """A 404 to a stranger is a directory listing delivered one probe at a time."""
        with _auth_support.anonymous():
            self.assertEqual(self.client.get("/definitely-not-a-route").status_code, 401)
            self.assertEqual(self.client.get("/api/cyber/evidence/whatever").status_code, 401)

    def test_refusal_precedes_validation_so_a_bad_body_is_not_a_422(self) -> None:
        with _auth_support.anonymous():
            response = self.client.post("/api/cyber/scan", json={"start": "not-a-date"})
            self.assertEqual(response.status_code, 401)

    def test_the_refusal_carries_no_reason_and_no_challenge(self) -> None:
        with _auth_support.anonymous():
            response = self.client.get("/api/health")
        self.assertEqual(response.content, b"")
        self.assertNotIn("www-authenticate", {k.lower() for k in response.headers})
        self.assertEqual(response.headers["cache-control"], "no-store, private")
        for header in response.headers:
            self.assertNotIn("auth", header.lower().replace("www-authenticate", ""))

    def test_a_refusal_reflects_nothing_the_caller_sent(self) -> None:
        marker = "reflect-me-9f3a1c"
        with _auth_support.anonymous():
            response = self.client.get(
                f"/api/cyber/knowledge/type/{marker}",
                headers={"X-Probe": marker, "User-Agent": marker},
            )
        self.assertEqual(response.status_code, 401)
        self.assertNotIn(marker, response.text)
        self.assertNotIn(marker, str(response.headers))

    def test_self_asserted_identity_headers_are_ignored(self) -> None:
        """The platform strips these inbound, and the application trusts them anyway: not at all."""
        forged = {
            "X-User-Id": "admin",
            "X-MS-CLIENT-PRINCIPAL": "eyJhdXRoX3R5cCI6ImFhZCJ9",
            "X-MS-CLIENT-PRINCIPAL-ID": "00000000-0000-0000-0000-000000000000",
            "X-MS-CLIENT-PRINCIPAL-NAME": "someone@example.com",
            "X-MS-CLIENT-PRINCIPAL-IDP": "aad",
            "Authorization": "Bearer not-a-real-token",
            "X-Forwarded-User": "admin",
            "Cookie": "AppServiceAuthSession=anything",
        }
        with _auth_support.anonymous():
            for name, value in forged.items():
                with self.subTest(name):
                    self.assertEqual(
                        self.client.get("/api/health", headers={name: value}).status_code, 401,
                    )
            self.assertEqual(self.client.get("/api/health", headers=forged).status_code, 401)


class PublicProbeTests(unittest.TestCase):
    def setUp(self) -> None:
        _auth_support.install(backend.app)
        self.client = TestClient(backend.app)

    def test_the_probe_answers_a_stranger_and_says_nothing_else(self) -> None:
        with _auth_support.anonymous():
            response = self.client.get(PUBLIC_PROBE_PATH)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        self.assertEqual(response.headers["cache-control"], "no-store, private")

    def test_the_probe_leaks_no_configuration_or_data(self) -> None:
        with _auth_support.anonymous():
            body = self.client.get(PUBLIC_PROBE_PATH).text.lower()
        for leak in ("adx", "kusto", "gremlin", "openai", "cluster", "endpoint",
                     "version", "table", "subscription", "tenant", "key"):
            self.assertNotIn(leak, body)

    def test_head_is_allowed_and_returns_no_body(self) -> None:
        with _auth_support.anonymous():
            response = self.client.head(PUBLIC_PROBE_PATH)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"")

    def test_every_other_method_on_the_probe_is_refused(self) -> None:
        with _auth_support.anonymous():
            for method in ("POST", "PUT", "PATCH", "DELETE", "OPTIONS"):
                with self.subTest(method):
                    self.assertEqual(
                        self.client.request(method, PUBLIC_PROBE_PATH).status_code, 401,
                    )

    def test_the_real_health_endpoint_stays_protected(self) -> None:
        """`/api/health` reports store reachability and agent configuration. That is not a probe."""
        with _auth_support.anonymous():
            self.assertEqual(self.client.get("/api/health").status_code, 401)


class ResolverSeamTests(unittest.TestCase):
    """The seam the Entra work fills. In-process only: no configured value can add one."""

    def setUp(self) -> None:
        _auth_support.install(backend.app)
        self.client = TestClient(backend.app)

    def test_a_registered_resolver_admits_the_caller_it_names(self) -> None:
        with _auth_support.as_principal(_auth_support.DEFAULT):
            response = self.client.get("/definitely-not-a-route")
        # Past the gate, so the application answers: an unknown route is now honestly a 404.
        self.assertEqual(response.status_code, 404)

    def test_an_authenticated_response_still_refuses_to_be_cached(self) -> None:
        with _auth_support.as_principal(_auth_support.DEFAULT):
            response = self.client.get("/definitely-not-a-route")
        self.assertEqual(response.headers["cache-control"], "no-store, private")

    def test_a_resolver_that_raises_denies_rather_than_admits(self) -> None:
        from app.cybereye.backend.security.gate import AuthorizationGate, ResolverRegistry

        async def explodes(_scope):
            raise RuntimeError("identity provider unreachable")

        registry = ResolverRegistry([explodes])
        gate = AuthorizationGate(_unreachable_app, resolvers=registry)
        self.assertEqual(_drive(gate, "/api/health"), 401)

    def test_a_resolver_returning_none_denies(self) -> None:
        from app.cybereye.backend.security.gate import AuthorizationGate, ResolverRegistry

        async def abstains(_scope):
            return None

        gate = AuthorizationGate(_unreachable_app, resolvers=ResolverRegistry([abstains]))
        self.assertEqual(_drive(gate, "/api/health"), 401)

    def test_the_registry_stays_live_after_the_middleware_is_built(self) -> None:
        from app.cybereye.backend.security.gate import AuthorizationGate, ResolverRegistry

        registry = ResolverRegistry()
        gate = AuthorizationGate(_reachable_app, resolvers=registry)
        self.assertEqual(_drive(gate, "/api/health"), 401)

        async def admits(_scope):
            return _auth_support.DEFAULT

        registry.add(admits)
        self.assertEqual(_drive(gate, "/api/health"), 200)


class NoOffSwitchTests(unittest.TestCase):
    """The gate has no configuration, so no misspelled variable can remove it."""

    SECURITY_DIR = Path(backend.__file__).resolve().parent / "security"

    def test_no_module_in_the_security_package_reads_a_disable_flag(self) -> None:
        banned = (
            "AUTH_ENABLED", "AUTH_DISABLED", "DISABLE_AUTH", "SKIP_AUTH", "ALLOW_ANONYMOUS",
            "DEV_PRINCIPAL", "BYPASS",
        )
        for path in sorted(self.SECURITY_DIR.glob("*.py")):
            text = path.read_text(encoding="utf-8")
            for token in banned:
                with self.subTest(module=path.name, token=token):
                    self.assertNotIn(token, text)

    def test_the_gate_module_reads_no_environment_variable_at_all(self) -> None:
        text = (self.SECURITY_DIR / "gate.py").read_text(encoding="utf-8")
        self.assertNotIn("os.environ", text)
        self.assertNotIn("getenv", text)

    def test_the_gate_is_mounted_outside_the_router_and_the_static_mount(self) -> None:
        classes = [str(item.cls) for item in backend.app.user_middleware]
        self.assertTrue(any("AuthorizationGate" in name for name in classes), classes)


class SecurityConfigurationTests(unittest.TestCase):
    def test_no_signing_key_means_no_signed_path(self) -> None:
        resolved = SecuritySettings.from_env({})
        self.assertFalse(resolved.signed_access_configured)
        self.assertEqual(resolved.ledger_kind, "")

    def test_a_signing_key_without_a_named_ledger_refuses_to_start(self) -> None:
        with self.assertRaises(SecurityConfigurationError) as caught:
            SecuritySettings.from_env({security_config.PUBLIC_KEY_VAR: "abc"})
        self.assertIn(security_config.LEDGER_VAR, str(caught.exception))

    def test_an_unrecognised_ledger_refuses_to_start(self) -> None:
        for value in ("redis", "memory", "", "  ", "azure_table", "AZURE-TABLES"):
            with self.subTest(value), self.assertRaises(SecurityConfigurationError):
                SecuritySettings.from_env({
                    security_config.PUBLIC_KEY_VAR: "abc",
                    security_config.LEDGER_VAR: value,
                })

    def test_the_durable_ledger_needs_an_endpoint(self) -> None:
        with self.assertRaises(SecurityConfigurationError):
            SecuritySettings.from_env({
                security_config.PUBLIC_KEY_VAR: "abc",
                security_config.LEDGER_VAR: "azure-table",
            })

    def test_a_ledger_without_a_key_is_reported_not_ignored(self) -> None:
        with self.assertRaises(SecurityConfigurationError):
            SecuritySettings.from_env({security_config.LEDGER_VAR: "in-process"})

    def test_the_in_process_ledger_is_never_reported_as_durable(self) -> None:
        resolved = SecuritySettings(
            public_key_b64="abc", ledger_kind=security_config.LEDGER_IN_PROCESS,
        )
        self.assertTrue(resolved.signed_access_configured)
        self.assertFalse(resolved.ledger_is_durable)

    def test_the_environment_cannot_select_the_in_process_ledger(self) -> None:
        """Constructible in a test, unreachable from a deployment. That asymmetry is the point."""
        with self.assertRaises(security_config.SecurityConfigurationError) as raised:
            SecuritySettings.from_env({
                security_config.PUBLIC_KEY_VAR: "abc",
                security_config.LEDGER_VAR: security_config.LEDGER_IN_PROCESS,
            })
        message = str(raised.exception)
        self.assertIn(security_config.LEDGER_AZURE_TABLE, message)
        # Capping replicas is not an alternative to a shared ledger, and must not read as one.
        self.assertNotIn("MAX_REPLICAS", message)

    def test_the_environment_refuses_an_unknown_ledger_and_a_missing_one(self) -> None:
        for value in ("", "sqlite", "AZURE-TABLE-ish"):
            with self.subTest(ledger=value):
                with self.assertRaises(security_config.SecurityConfigurationError):
                    SecuritySettings.from_env({
                        security_config.PUBLIC_KEY_VAR: "abc",
                        security_config.LEDGER_VAR: value,
                    })

    def test_the_description_names_the_key_by_fingerprint_never_by_value(self) -> None:
        resolved = SecuritySettings(
            public_key_b64="abcdef", ledger_kind=security_config.LEDGER_IN_PROCESS,
        )
        described = resolved.describe(fingerprint="0123456789abcdef")
        self.assertEqual(described["key_fingerprint"], "0123456789abcdef")
        self.assertNotIn("abcdef", str({k: v for k, v in described.items() if k != "key_fingerprint"}))


async def _unreachable_app(scope, receive, send) -> None:  # pragma: no cover - must not run
    raise AssertionError("the gate let a request through")


async def _reachable_app(scope, receive, send) -> None:
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})


def _drive(gate, path: str) -> int:
    """Run one bare ASGI request through a gate instance and return the status."""
    import asyncio

    sent: list[dict] = []

    async def receive() -> dict:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict) -> None:
        sent.append(message)

    asyncio.run(gate(
        {"type": "http", "method": "GET", "path": path, "raw_path": path.encode(),
         "query_string": b"", "headers": []},
        receive, send,
    ))
    return next(m["status"] for m in sent if m["type"] == "http.response.start")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
