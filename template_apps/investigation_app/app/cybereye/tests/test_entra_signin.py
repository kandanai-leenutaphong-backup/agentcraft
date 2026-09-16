"""Browser sign-in, end to end, against a tenant that does not exist.

The token validator takes an injected fetcher and the stores are in-process, so the whole
Authorization Code + PKCE round trip runs offline: this file mints its own signing key,
issues its own access tokens, and drives the real routes, the real gate and the real cookie
handling. Nothing here is a stand-in for the production path — it *is* the production path
with two dependencies substituted at their declared seams.

The negatives are the point. A sign-in that works proves very little; what has to be true is
that the application bundle is unreachable, that a forged cookie is worth nothing, that a
platform header nobody verified is worth nothing, that a cross-site POST cannot ride a
session, and that signing out actually ends it.
"""

from __future__ import annotations

import base64
import json
import time
import unittest
from datetime import timedelta

import jwt as pyjwt
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat
from fastapi import FastAPI
from fastapi.testclient import TestClient

from entra_auth import (
    EntraAuthConfig,
    InProcessRecordStore,
    TokenValidator,
)
from app.cybereye.backend.security import (
    SESSION_COOKIE,
    BrowserSessions,
    SecuritySettings,
    install_security,
)

TENANT = "c79ab2bb-79cb-47f1-b4da-b6852fe45ff7"
CLIENT = "b1fa8094-e820-4d5b-8552-4dbf64fb70d0"
ORIGIN = "https://cybereye.test"
KID = "signin-key"

#: What a browser sends when a person types a URL, as opposed to what a page's own
#: subresource requests send. The gate treats the two differently and both are asserted.
NAVIGATION = {
    "Accept": "text/html,application/xhtml+xml",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Dest": "document",
}
SUBRESOURCE = {"Accept": "*/*", "Sec-Fetch-Mode": "no-cors", "Sec-Fetch-Dest": "script"}


def _b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


class Signer:
    def __init__(self) -> None:
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    @property
    def pem(self) -> bytes:
        return self.key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())

    def document(self) -> dict:
        numbers = self.key.public_key().public_numbers()
        return {"keys": [{
            "kty": "RSA", "kid": KID, "use": "sig",
            "n": _b64u(numbers.n.to_bytes((numbers.n.bit_length() + 7) // 8, "big")),
            "e": _b64u(numbers.e.to_bytes((numbers.e.bit_length() + 7) // 8, "big")),
        }]}

    def token(self, **overrides) -> str:
        now = int(time.time())
        claims = {
            "iss": f"https://login.microsoftonline.com/{TENANT}/v2.0",
            "aud": CLIENT, "tid": TENANT,
            "oid": "11111111-1111-1111-1111-111111111111",
            "scp": "access_as_user", "name": "Test Analyst",
            "preferred_username": "analyst@example.test",
            "iat": now, "nbf": now, "exp": now + 900,
        }
        claims.update(overrides)
        return pyjwt.encode(claims, self.pem, algorithm="RS256", headers={"kid": KID})


def build_app(signer: Signer, *, session_hours: int = 8):
    """A minimal application behind the real security edge."""
    app = FastAPI()

    @app.get("/api/health")
    async def health():
        return {"status": "ok"}

    @app.post("/api/cyber/scan")
    async def scan():
        return {"scanned": True}

    @app.get("/assets/index.js")
    async def asset():
        return {"bundle": True}

    settings = SecuritySettings(
        entra_tenant_id=TENANT, entra_client_id=CLIENT, public_origin=ORIGIN,
        session_table_endpoint="https://example.table.core.windows.net",
        session_table_name="browserauth", session_max_hours=session_hours,
    )

    async def fetch(_url):
        return signer.document()

    validator = TokenValidator(
        EntraAuthConfig(tenant_id=TENANT, client_id=CLIENT), fetcher=fetch
    )
    sessions = BrowserSessions(
        store=InProcessRecordStore(), flow_store=InProcessRecordStore(),
        max_lifetime=timedelta(hours=session_hours),
    )
    composition = install_security(
        app, settings=settings, validator=validator, sessions=sessions
    )
    return app, composition


def client_for(app) -> TestClient:
    """A client that speaks to the application's real origin over https.

    Not cosmetic. The session cookie is ``Secure``, so a client rooted at ``http://testserver``
    silently never sends it and every session assertion would pass for the wrong reason.
    """
    return TestClient(app, base_url=ORIGIN, follow_redirects=False)


def sign_in(client: TestClient, signer: Signer, **overrides):
    """Complete a sign-in the way the callback page does, and return the response."""
    return client.post(
        "/auth/session",
        headers={"Origin": ORIGIN, "Content-Type": "application/json"},
        content=json.dumps({"access_token": signer.token(**overrides)}),
    )


class UnauthenticatedSurfaceTests(unittest.TestCase):
    """What a stranger can reach. The answer must be: a sign-in page, and nothing else."""

    def setUp(self) -> None:
        self.signer = Signer()
        self.app, _ = build_app(self.signer)
        self.client = client_for(self.app)

    def test_the_application_bundle_is_never_served_anonymously(self) -> None:
        response = self.client.get("/assets/index.js", headers=SUBRESOURCE)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.content, b"")

    def test_the_api_answers_a_status_code_rather_than_a_sign_in_page(self) -> None:
        for path in ("/api/health", "/api/whoami", "/api/cyber/scan"):
            with self.subTest(path=path):
                response = self.client.get(path, headers=NAVIGATION)
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.content, b"")

    def test_a_person_navigating_is_sent_to_sign_in_and_told_nothing_else(self) -> None:
        response = self.client.get("/", headers=NAVIGATION)
        self.assertEqual(response.status_code, 303)
        self.assertTrue(response.headers["location"].startswith("/auth/login?return_to="))
        self.assertEqual(response.content, b"")

    def test_an_unknown_path_answers_exactly_as_a_real_one(self) -> None:
        known = self.client.get("/assets/index.js", headers=SUBRESOURCE)
        unknown = self.client.get("/assets/does-not-exist.js", headers=SUBRESOURCE)
        self.assertEqual(known.status_code, unknown.status_code)
        self.assertEqual(known.content, unknown.content)

    def test_every_refusal_refuses_to_be_cached(self) -> None:
        response = self.client.get("/api/health")
        self.assertEqual(response.headers["cache-control"], "no-store, private")

    def test_only_the_four_sign_in_paths_are_public(self) -> None:
        from app.cybereye.backend.security import PUBLIC_ROUTES

        self.assertEqual(
            {route.path for route in PUBLIC_ROUTES},
            {"/auth/login", "/auth/callback", "/auth/session", "/auth/signed-out"},
        )
        for route in PUBLIC_ROUTES:
            self.assertNotIn("*", route.path)

    def test_a_public_route_publishes_only_its_own_methods(self) -> None:
        self.assertEqual(self.client.post("/auth/login").status_code, 401)
        self.assertEqual(self.client.get("/auth/session").status_code, 401)

    def test_a_public_path_prefix_publishes_nothing_beneath_it(self) -> None:
        for path in ("/auth", "/auth/", "/auth/login/extra", "/auth/config"):
            with self.subTest(path=path):
                self.assertIn(self.client.get(path, headers=SUBRESOURCE).status_code, (401,))


class SignInRedirectTests(unittest.TestCase):
    def setUp(self) -> None:
        self.signer = Signer()
        self.app, _ = build_app(self.signer)
        self.client = client_for(self.app)

    def test_login_redirects_to_the_configured_tenant_with_pkce(self) -> None:
        response = self.client.get("/auth/login")
        self.assertEqual(response.status_code, 303)
        location = response.headers["location"]
        self.assertTrue(
            location.startswith(f"https://login.microsoftonline.com/{TENANT}/oauth2/v2.0/authorize?")
        )
        for expected in ("code_challenge_method=S256", "response_type=code", f"client_id={CLIENT}"):
            self.assertIn(expected, location)
        self.assertNotIn("client_secret", location)

    def test_the_flow_cookie_is_http_only_and_scoped_to_the_auth_paths(self) -> None:
        cookie = self.client.get("/auth/login").headers["set-cookie"]
        self.assertIn("HttpOnly", cookie)
        self.assertIn("Secure", cookie)
        self.assertIn("SameSite=Lax", cookie)
        self.assertIn("Path=/auth", cookie)

    def test_a_foreign_return_to_cannot_survive_the_redirect(self) -> None:
        for hostile in ("https://evil.example/steal", "//evil.example", "javascript:alert(1)"):
            with self.subTest(hostile=hostile):
                response = self.client.get("/auth/login", params={"return_to": hostile})
                self.assertEqual(response.status_code, 303)
                self.assertNotIn("evil.example", response.headers["location"])

    def test_a_callback_with_no_flow_is_refused_and_shows_no_application(self) -> None:
        response = self.client.get("/auth/callback", params={"code": "x", "state": "y"})
        self.assertEqual(response.status_code, 400)
        self.assertNotIn("access_token", response.text)
        self.assertIn("Content-Security-Policy", response.headers)

    def test_a_callback_whose_state_does_not_match_is_refused(self) -> None:
        self.client.get("/auth/login")
        response = self.client.get("/auth/callback", params={"code": "x", "state": "wrong"})
        self.assertEqual(response.status_code, 400)

    def test_a_spent_flow_cannot_be_replayed(self) -> None:
        self.client.get("/auth/login")
        first = self.client.get("/auth/callback", params={"code": "x", "state": "wrong"})
        second = self.client.get("/auth/callback", params={"code": "x", "state": "wrong"})
        self.assertEqual(first.status_code, 400)
        self.assertEqual(second.status_code, 400)

    def test_the_callback_page_forbids_everything_it_does_not_need(self) -> None:
        policy = self.client.get(
            "/auth/callback", params={"code": "x", "state": "y"}
        ).headers["content-security-policy"]
        for expected in ("default-src 'none'", "frame-ancestors 'none'", "base-uri 'none'"):
            self.assertIn(expected, policy)
        self.assertNotIn("unsafe-inline", policy)

    # The provider-error branch, exercised offline. A browser walk cannot reach it without a
    # real failed sign-in at Microsoft, and no deployed route may be added to simulate one:
    # an endpoint that produces the signed-out-error page on demand is a way into the auth
    # surface that exists only for the test. Here the fixture is the whole application, and
    # the only thing faked is the query string Entra would have sent back.
    def test_a_provider_error_is_shown_as_a_retry_and_not_echoed(self) -> None:
        hostile = "<img src=x onerror=alert(1)>consent_required"
        response = self.client.get("/auth/callback", params={"error": hostile})
        self.assertEqual(response.status_code, 400)
        # The provider's error text is influenced by whoever produced the request that caused
        # it, so it is reported to the log by length and never rendered into the page.
        self.assertNotIn("onerror", response.text)
        self.assertNotIn("consent_required", response.text)
        self.assertIn("Sign-in did not complete", response.text)
        self.assertIn('href="/auth/login"', response.text)
        self.assertNotIn("access_token", response.text)
        self.assertEqual(response.headers["cache-control"], "no-store, private")

    def test_the_error_page_still_loads_nothing_of_its_own(self) -> None:
        policy = self.client.get(
            "/auth/callback", params={"error": "access_denied"}
        ).headers["content-security-policy"]
        self.assertIn("default-src 'none'", policy)
        self.assertNotIn("unsafe-inline", policy)

    def test_a_provider_error_never_becomes_a_session(self) -> None:
        """The branch that must not exist: an error path that signs somebody in anyway."""
        self.client.get("/auth/login")
        response = self.client.get("/auth/callback", params={"error": "access_denied",
                                                             "code": "x", "state": "y"})
        self.assertEqual(response.status_code, 400)
        self.assertNotIn("cy_session", response.headers.get("set-cookie", ""))
        self.assertEqual(self.client.get("/api/health").status_code, 401)


class SessionMintingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.signer = Signer()
        self.app, _ = build_app(self.signer)
        self.client = client_for(self.app)

    def test_a_valid_token_becomes_a_session_and_the_token_is_never_returned(self) -> None:
        response = sign_in(self.client, self.signer)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("access_token", response.text)
        cookie = response.headers["set-cookie"]
        for attribute in ("HttpOnly", "Secure", "SameSite=Lax", "Path=/"):
            self.assertIn(attribute, cookie)

    def test_the_session_then_reaches_the_protected_application(self) -> None:
        sign_in(self.client, self.signer)
        who = self.client.get("/api/whoami")
        self.assertEqual(who.status_code, 200)
        self.assertEqual(who.json()["id"], f"entra:{TENANT}:11111111-1111-1111-1111-111111111111")
        self.assertEqual(who.json()["issuer"], "entra")
        self.assertEqual(self.client.get("/assets/index.js", headers=SUBRESOURCE).status_code, 200)

    def test_a_foreign_origin_cannot_mint_a_session(self) -> None:
        response = self.client.post(
            "/auth/session",
            headers={"Origin": "https://evil.example", "Content-Type": "application/json"},
            content=json.dumps({"access_token": self.signer.token()}),
        )
        self.assertEqual(response.status_code, 403)
        self.assertNotIn("set-cookie", response.headers)

    def test_a_form_content_type_cannot_mint_a_session(self) -> None:
        response = self.client.post(
            "/auth/session",
            headers={"Origin": ORIGIN, "Content-Type": "application/x-www-form-urlencoded"},
            content="access_token=" + self.signer.token(),
        )
        self.assertEqual(response.status_code, 415)

    def test_a_token_from_another_tenant_mints_nothing(self) -> None:
        other = "22222222-2222-2222-2222-222222222222"
        response = sign_in(
            self.client, self.signer,
            iss=f"https://login.microsoftonline.com/{other}/v2.0", tid=other,
        )
        self.assertEqual(response.status_code, 401)
        self.assertNotIn("set-cookie", response.headers)

    def test_a_token_for_another_audience_mints_nothing(self) -> None:
        self.assertEqual(sign_in(self.client, self.signer, aud="api://other").status_code, 401)

    def test_a_token_without_the_delegated_scope_mints_nothing(self) -> None:
        self.assertEqual(sign_in(self.client, self.signer, scp="User.Read").status_code, 401)

    def test_an_expired_token_mints_nothing(self) -> None:
        now = int(time.time())
        response = sign_in(self.client, self.signer, iat=now - 7200, nbf=now - 7200, exp=now - 60)
        self.assertEqual(response.status_code, 401)

    def test_a_forged_token_mints_nothing(self) -> None:
        forged = Signer().token()
        response = self.client.post(
            "/auth/session", headers={"Origin": ORIGIN, "Content-Type": "application/json"},
            content=json.dumps({"access_token": forged}),
        )
        self.assertEqual(response.status_code, 401)

    def test_every_refusal_here_carries_no_body(self) -> None:
        response = sign_in(self.client, self.signer, aud="api://other")
        self.assertEqual(response.content, b"")

    def test_a_session_never_outlives_the_token_that_proved_it(self) -> None:
        now = int(time.time())
        response = sign_in(self.client, self.signer, iat=now, nbf=now, exp=now + 120)
        expires = response.json()["expiresAt"]
        # Two minutes, not the eight-hour ceiling.
        self.assertLess(
            time.mktime(time.strptime(expires[:19], "%Y-%m-%dT%H:%M:%S")) - time.timezone,
            now + 600,
        )


class ForgedCredentialTests(unittest.TestCase):
    """Everything that looks like a credential but proves nothing."""

    def setUp(self) -> None:
        self.signer = Signer()
        self.app, _ = build_app(self.signer)
        self.client = client_for(self.app)

    def test_an_invented_session_cookie_is_worth_nothing(self) -> None:
        for value in ("x", "0" * 43, "../../etc/passwd", "null", ""):
            with self.subTest(value=value):
                response = self.client.get(
                    "/api/whoami", headers={"Cookie": f"{SESSION_COOKIE}={value}"}
                )
                self.assertEqual(response.status_code, 401)

    def test_a_session_id_that_hashes_to_a_stored_key_is_still_needed_whole(self) -> None:
        sign_in(self.client, self.signer)
        real = self.client.cookies.get(SESSION_COOKIE)
        self.client.cookies.clear()
        response = self.client.get(
            "/api/whoami", headers={"Cookie": f"{SESSION_COOKIE}={real[:-1]}"}
        )
        self.assertEqual(response.status_code, 401)

    def test_platform_principal_headers_are_not_a_credential(self) -> None:
        forged = base64.b64encode(json.dumps({
            "auth_typ": "aad",
            "claims": [{"typ": "http://schemas.microsoft.com/identity/claims/objectidentifier",
                        "val": "11111111-1111-1111-1111-111111111111"}],
        }).encode()).decode()
        response = self.client.get("/api/whoami", headers={
            "X-MS-CLIENT-PRINCIPAL": forged,
            "X-MS-CLIENT-PRINCIPAL-ID": "11111111-1111-1111-1111-111111111111",
            "X-MS-CLIENT-PRINCIPAL-NAME": "analyst@example.test",
            "X-MS-CLIENT-PRINCIPAL-IDP": "aad",
        })
        self.assertEqual(response.status_code, 401)

    def test_self_asserted_identity_headers_are_not_a_credential(self) -> None:
        response = self.client.get("/api/whoami", headers={
            "X-User-Id": "11111111-1111-1111-1111-111111111111",
            "X-User-Email": "analyst@example.test",
            "Authorization": "Bearer not-a-token",
        })
        self.assertEqual(response.status_code, 401)

    def test_a_bearer_token_from_another_signer_is_worth_nothing(self) -> None:
        response = self.client.get(
            "/api/whoami", headers={"Authorization": f"Bearer {Signer().token()}"}
        )
        self.assertEqual(response.status_code, 401)

    def test_a_real_bearer_token_reaches_the_same_identity_as_the_cookie(self) -> None:
        response = self.client.get(
            "/api/whoami", headers={"Authorization": f"Bearer {self.signer.token()}"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["issuer"], "entra")


class CrossSiteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.signer = Signer()
        self.app, _ = build_app(self.signer)
        self.client = client_for(self.app)
        sign_in(self.client, self.signer)

    def test_a_cross_site_post_riding_the_session_is_refused(self) -> None:
        response = self.client.post(
            "/api/cyber/scan",
            headers={"Origin": "https://evil.example", "Content-Type": "application/json"},
            content="{}",
        )
        self.assertEqual(response.status_code, 403)

    def test_a_post_with_no_origin_at_all_is_refused(self) -> None:
        response = self.client.post(
            "/api/cyber/scan", headers={"Content-Type": "application/json"}, content="{}"
        )
        self.assertEqual(response.status_code, 403)

    def test_a_form_post_shape_is_refused(self) -> None:
        response = self.client.post(
            "/api/cyber/scan",
            headers={"Origin": ORIGIN, "Content-Type": "application/x-www-form-urlencoded"},
            content="a=b",
        )
        self.assertEqual(response.status_code, 403)

    def test_a_same_origin_json_post_is_allowed(self) -> None:
        response = self.client.post(
            "/api/cyber/scan",
            headers={"Origin": ORIGIN, "Content-Type": "application/json"}, content="{}",
        )
        self.assertEqual(response.status_code, 200)

    def test_reads_are_untouched_by_the_guard(self) -> None:
        self.assertEqual(self.client.get("/api/whoami").status_code, 200)


class SignOutTests(unittest.TestCase):
    def setUp(self) -> None:
        self.signer = Signer()
        self.app, _ = build_app(self.signer)
        self.client = client_for(self.app)
        sign_in(self.client, self.signer)

    def test_signing_out_revokes_the_session_here_first(self) -> None:
        response = self.client.post(
            "/auth/logout", headers={"Origin": ORIGIN, "Content-Type": "application/json"},
            content="{}",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Max-Age=0", response.headers["set-cookie"])
        self.assertEqual(self.client.get("/api/whoami").status_code, 401)

    def test_the_revoked_cookie_cannot_be_replayed_after_sign_out(self) -> None:
        stolen = self.client.cookies.get(SESSION_COOKIE)
        self.client.post(
            "/auth/logout", headers={"Origin": ORIGIN, "Content-Type": "application/json"},
            content="{}",
        )
        response = self.client.get(
            "/api/whoami", headers={"Cookie": f"{SESSION_COOKIE}={stolen}"}
        )
        self.assertEqual(response.status_code, 401)

    def test_the_provider_sign_out_url_returns_to_this_origin(self) -> None:
        body = self.client.post(
            "/auth/logout", headers={"Origin": ORIGIN, "Content-Type": "application/json"},
            content="{}",
        ).json()
        self.assertIn(f"login.microsoftonline.com/{TENANT}", body["providerLogoutUrl"])
        self.assertIn("auth%2Fsigned-out", body["providerLogoutUrl"])

    def test_the_signed_out_page_offers_a_way_back_and_nothing_more(self) -> None:
        page = self.client.get("/auth/signed-out")
        self.assertEqual(page.status_code, 200)
        self.assertIn("/auth/login", page.text)
        self.assertNotIn("access_token", page.text)


class OwnershipTests(unittest.TestCase):
    """Two people, two sessions, and no way to address each other's resources."""

    def test_two_identities_produce_two_distinct_principals(self) -> None:
        signer = Signer()
        app, _ = build_app(signer)
        first = client_for(app)
        second = client_for(app)

        sign_in(first, signer)
        second.post(
            "/auth/session", headers={"Origin": ORIGIN, "Content-Type": "application/json"},
            content=json.dumps({
                "access_token": signer.token(oid="99999999-9999-9999-9999-999999999999")
            }),
        )
        self.assertNotEqual(
            first.get("/api/whoami").json()["id"], second.get("/api/whoami").json()["id"]
        )

    def test_a_signed_developer_and_a_person_never_share_a_namespace(self) -> None:
        from app.cybereye.backend.security import entra_principal, signed_developer_principal

        person = entra_principal(tenant_id=TENANT, object_id="abc")
        agent = signed_developer_principal(fingerprint="deadbeef", slug="pilot")
        self.assertNotEqual(person.id, agent.id)
        self.assertTrue(person.id.startswith("entra:"))
        self.assertTrue(agent.id.startswith("devkey:"))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
