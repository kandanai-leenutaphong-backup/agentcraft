"""Signed developer access, end to end, and what one caller can see of another's work.

Two things are proved here. First, that a correctly signed request becomes a named principal
and anything else becomes an identical bare 401. Second, that two authenticated callers are
isolated from each other: a session and a cached scan belong to whoever created them, and
someone else gets the answer they would get for something that never existed.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import unittest
from datetime import datetime, timedelta, timezone

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.components.signed_dev_access import (
    CONTEXT_HEADER,
    MAX_SKEW_SECONDS,
    SIGNATURE_HEADER,
    TIMESTAMP_HEADER,
    InProcessReplayLedger,
    canonical_string,
    public_key_fingerprint,
)
from app.cybereye.backend import main as backend
from app.cybereye.backend.security import (
    ISSUER_SIGNED_DEV,
    KIND_SERVICE,
    LEDGER_IN_PROCESS,
    AuthorizationGate,
    Principal,
    ResolverRegistry,
    SecuritySettings,
    current_principal,
    entra_principal,
    install_security,
    register_principal_resolver,
    signed_developer_principal,
)

import _auth_support
from test_chat_sessions import FakeAgent, client_with, frames, happy


def sign_headers(
    key: Ed25519PrivateKey,
    method: str,
    path: str,
    *,
    body: bytes = b"",
    slug: str = "",
    offset_seconds: float = 0.0,
) -> dict[str, str]:
    moment = datetime.now(timezone.utc) + timedelta(seconds=offset_seconds)
    ts = moment.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    normalised = slug.strip().lower()
    signature = key.sign(canonical_string(
        method=method,
        path_and_query=path,
        timestamp=ts,
        context_slug=normalised,
        body_sha256_hex=hashlib.sha256(body).hexdigest(),
    ))
    headers = {
        TIMESTAMP_HEADER: ts,
        SIGNATURE_HEADER: base64.b64encode(signature).decode("ascii"),
    }
    if normalised:
        headers[CONTEXT_HEADER] = normalised
    return headers


def build_app(key: Ed25519PrivateKey | None, *, ledger=None) -> tuple[FastAPI, object]:
    """An application composed exactly as `main` composes it, with test routes."""
    app = FastAPI()

    @app.get("/api/whoami")
    async def whoami(caller: Principal = Depends(current_principal)):
        return {"id": caller.id, "kind": caller.kind, "issuer": caller.issuer}

    @app.post("/api/echo")
    async def echo(payload: dict, caller: Principal = Depends(current_principal)):
        return {"id": caller.id, "received": payload}

    public = (
        base64.b64encode(key.public_key().public_bytes_raw()).decode("ascii") if key else ""
    )
    composition = install_security(
        app,
        settings=SecuritySettings(
            public_key_b64=public,
            ledger_kind=LEDGER_IN_PROCESS if public else "",
        ),
        replay_ledger=InProcessReplayLedger() if public else None,
    )
    return app, composition


class SignedAccessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.key = Ed25519PrivateKey.generate()
        self.app, self.composition = build_app(self.key)
        self.client = TestClient(self.app)
        self.fingerprint = public_key_fingerprint(
            base64.b64encode(self.key.public_key().public_bytes_raw()).decode("ascii")
        )

    def test_a_signed_request_becomes_a_named_service_principal(self) -> None:
        response = self.client.get(
            "/api/whoami", headers=sign_headers(self.key, "GET", "/api/whoami"),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {
            "id": f"devkey:{self.fingerprint}:default",
            "kind": KIND_SERVICE,
            "issuer": ISSUER_SIGNED_DEV,
        })

    def test_the_context_slug_names_the_identity(self) -> None:
        response = self.client.get(
            "/api/whoami", headers=sign_headers(self.key, "GET", "/api/whoami", slug="Pilot"),
        )
        self.assertEqual(response.json()["id"], f"devkey:{self.fingerprint}:pilot")

    def test_a_signed_body_reaches_the_route_intact(self) -> None:
        payload = {"question": "what happened at 03:07?"}
        body = json.dumps(payload).encode()
        headers = sign_headers(self.key, "POST", "/api/echo", body=body)
        headers["Content-Type"] = "application/json"
        response = self.client.post("/api/echo", content=body, headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["received"], payload)

    def test_an_unsigned_request_is_the_same_bare_401(self) -> None:
        response = self.client.get("/api/whoami")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.content, b"")

    def test_every_malformed_attempt_is_indistinguishable(self) -> None:
        good = sign_headers(self.key, "GET", "/api/whoami")
        other = Ed25519PrivateKey.generate()
        cases = {
            "signature only": {SIGNATURE_HEADER: good[SIGNATURE_HEADER]},
            "timestamp only": {TIMESTAMP_HEADER: good[TIMESTAMP_HEADER]},
            "garbage signature": {**good, SIGNATURE_HEADER: "%%%%%%"},
            "empty signature": {**good, SIGNATURE_HEADER: ""},
            "wrong key": sign_headers(other, "GET", "/api/whoami"),
            "wrong path": sign_headers(self.key, "GET", "/api/echo"),
            "wrong method": sign_headers(self.key, "POST", "/api/whoami"),
            "stale": sign_headers(
                self.key, "GET", "/api/whoami", offset_seconds=-MAX_SKEW_SECONDS - 60,
            ),
            "far future": sign_headers(
                self.key, "GET", "/api/whoami", offset_seconds=MAX_SKEW_SECONDS + 60,
            ),
        }
        seen = set()
        for label, headers in cases.items():
            with self.subTest(label):
                response = self.client.get("/api/whoami", headers=headers)
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.content, b"")
                seen.add((response.status_code, response.content))
        self.assertEqual(len(seen), 1, "failures must be indistinguishable")

    def test_a_replayed_request_is_refused(self) -> None:
        headers = sign_headers(self.key, "GET", "/api/whoami")
        self.assertEqual(self.client.get("/api/whoami", headers=headers).status_code, 200)
        self.assertEqual(self.client.get("/api/whoami", headers=headers).status_code, 401)

    def test_a_query_string_is_part_of_what_was_signed(self) -> None:
        headers = sign_headers(self.key, "GET", "/api/whoami?verbose=1")
        self.assertEqual(
            self.client.get("/api/whoami?verbose=1", headers=headers).status_code, 200,
        )
        self.assertEqual(
            self.client.get(
                "/api/whoami?verbose=2", headers=sign_headers(self.key, "GET", "/api/whoami?verbose=1"),
            ).status_code,
            401,
        )

    def test_a_signed_request_response_refuses_to_be_cached(self) -> None:
        response = self.client.get(
            "/api/whoami", headers=sign_headers(self.key, "GET", "/api/whoami"),
        )
        self.assertEqual(response.headers["cache-control"], "no-store, private")


class KeyLifecycleTests(unittest.TestCase):
    def test_no_key_means_no_signed_authorizing_path_at_all(self) -> None:
        """Revocation is clearing one variable. Nothing is mounted, so nothing can be signed."""
        key = Ed25519PrivateKey.generate()
        app, composition = build_app(None)
        self.assertFalse(composition.signed_access_mounted)
        self.assertEqual(composition.key_fingerprint, "")
        classes = [str(item.cls) for item in app.user_middleware]
        self.assertFalse(any("SignedRequest" in name for name in classes), classes)

        client = TestClient(app)
        self.assertEqual(
            client.get("/api/whoami", headers=sign_headers(key, "GET", "/api/whoami")).status_code,
            401,
        )

    def test_removing_the_key_leaves_the_primary_path_working(self) -> None:
        """Revoking signed access must not revoke everybody else."""
        app, _ = build_app(None)

        async def primary(_scope):
            return entra_principal(tenant_id="t", object_id="o", display="analyst")

        register_principal_resolver(app, primary)
        response = TestClient(app).get("/api/whoami")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["issuer"], "entra")

    def test_signed_and_entra_identities_can_never_collide(self) -> None:
        signed = signed_developer_principal(fingerprint="0123456789abcdef", slug="pilot")
        entra = entra_principal(
            tenant_id="c79ab2bb-79cb-47f1-b4da-b6852fe45ff7",
            object_id="0123456789abcdef",
        )
        self.assertNotEqual(signed.id, entra.id)
        self.assertTrue(signed.id.startswith("devkey:"))
        self.assertTrue(entra.id.startswith("entra:"))
        self.assertTrue(signed.is_signed_developer)
        self.assertFalse(entra.is_signed_developer)
        # A slug can never be spelled so that it produces an Entra-shaped identifier.
        self.assertNotIn(":entra:", signed.id)

    def test_rotating_the_key_rotates_the_identities_with_it(self) -> None:
        first = signed_developer_principal(fingerprint="aaaaaaaaaaaaaaaa", slug="pilot")
        second = signed_developer_principal(fingerprint="bbbbbbbbbbbbbbbb", slug="pilot")
        self.assertNotEqual(first.id, second.id)

    def test_an_identity_needs_the_key_that_signed_it(self) -> None:
        with self.assertRaises(ValueError):
            signed_developer_principal(fingerprint="", slug="pilot")

    def test_a_malformed_public_key_refuses_to_start(self) -> None:
        from app.cybereye.backend.security import SecurityConfigurationError

        app = FastAPI()
        with self.assertRaises(SecurityConfigurationError):
            install_security(
                app,
                settings=SecuritySettings(
                    public_key_b64="not-a-key", ledger_kind=LEDGER_IN_PROCESS,
                ),
                replay_ledger=InProcessReplayLedger(),
            )


class CallerIsolationTests(unittest.TestCase):
    """Two authenticated callers, one application. Neither sees the other's work."""

    def setUp(self) -> None:
        from unittest import mock

        for target in ("ReadOnlyAdx", "Scanner", "AgentService"):
            patcher = mock.patch.object(backend, target)
            self.addCleanup(patcher.stop)
            patcher.start()
        self.client = client_with(FakeAgent(happy))
        self.addCleanup(self.client.__exit__, None, None, None)

    def test_a_session_belongs_to_the_caller_that_opened_it(self) -> None:
        with _auth_support.as_principal(_auth_support.DEFAULT):
            session_id = self.client.post("/api/sessions").json()["session_id"]
            self.assertEqual(
                self.client.post(f"/api/chat/{session_id}", json={"message": "mine"}).status_code,
                200,
            )
        with _auth_support.as_principal(_auth_support.OTHER):
            stolen = self.client.post(f"/api/chat/{session_id}", json={"message": "yours"})
            missing = self.client.post("/api/chat/never-existed", json={"message": "x"})
        self.assertEqual(stolen.status_code, 404)
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(stolen.json(), missing.json())

    def test_a_refused_session_is_still_usable_by_its_owner(self) -> None:
        with _auth_support.as_principal(_auth_support.DEFAULT):
            session_id = self.client.post("/api/sessions").json()["session_id"]
        with _auth_support.as_principal(_auth_support.OTHER):
            self.client.post(f"/api/chat/{session_id}", json={"message": "probe"})
        with _auth_support.as_principal(_auth_support.DEFAULT):
            self.assertEqual(
                self.client.post(f"/api/chat/{session_id}", json={"message": "still mine"}).status_code,
                200,
            )

    def test_a_cached_scan_is_never_read_by_another_caller(self) -> None:
        from app.cybereye.backend.security import OwnedCache

        cache: OwnedCache[str] = OwnedCache()
        cache.put(_auth_support.DEFAULT.id, "mine")
        self.assertEqual(cache.get(_auth_support.DEFAULT.id), "mine")
        self.assertIsNone(cache.get(_auth_support.OTHER.id))
        self.assertIsNone(cache.get(""))

    def test_a_client_cannot_supply_the_thread_identifier(self) -> None:
        """`previous_response_id` is server state. A posted one is ignored, never honoured."""
        agent = FakeAgent(happy)
        client = client_with(agent)
        self.addCleanup(client.__exit__, None, None, None)
        with _auth_support.as_principal(_auth_support.DEFAULT):
            session_id = client.post("/api/sessions").json()["session_id"]
            client.post(
                f"/api/chat/{session_id}",
                json={"message": "one", "previous_response_id": "resp_injected"},
            )
        self.assertEqual(agent.calls, [None])


class StreamingTests(unittest.TestCase):
    def setUp(self) -> None:
        from unittest import mock

        for target in ("ReadOnlyAdx", "Scanner", "AgentService"):
            patcher = mock.patch.object(backend, target)
            self.addCleanup(patcher.stop)
            patcher.start()

    def test_events_arrive_as_a_stream_not_as_one_buffered_blob(self) -> None:
        """The gate wraps `send`. Wrapping must forward each body message as it is produced."""
        forwarded: list[tuple[bytes, bool]] = []

        async def inner(scope, receive, send) -> None:
            await send({"type": "http.response.start", "status": 200,
                        "headers": [(b"content-type", b"text/event-stream")]})
            await send({"type": "http.response.body", "body": b"event: one\n\n", "more_body": True})
            await send({"type": "http.response.body", "body": b"event: two\n\n", "more_body": True})
            await send({"type": "http.response.body", "body": b"", "more_body": False})

        async def send(message: dict) -> None:
            if message["type"] == "http.response.body":
                forwarded.append((message["body"], message.get("more_body", False)))
            elif message["type"] == "http.response.start":
                self.assertIn(
                    (b"cache-control", b"no-store, private"), message["headers"],
                )

        async def receive() -> dict:
            return {"type": "http.request", "body": b"", "more_body": False}

        async def resolver(_scope):
            return _auth_support.DEFAULT

        gate = AuthorizationGate(inner, resolvers=ResolverRegistry([resolver]))
        asyncio.run(gate(
            {"type": "http", "method": "POST", "path": "/api/chat/x",
             "raw_path": b"/api/chat/x", "query_string": b"", "headers": []},
            receive, send,
        ))
        self.assertEqual(
            forwarded,
            [(b"event: one\n\n", True), (b"event: two\n\n", True), (b"", False)],
        )

    def test_a_full_turn_streams_every_event_in_order(self) -> None:
        client = client_with(FakeAgent(happy))
        self.addCleanup(client.__exit__, None, None, None)
        with _auth_support.as_principal(_auth_support.DEFAULT):
            session_id = client.post("/api/sessions").json()["session_id"]
            with client.stream(
                "POST", f"/api/chat/{session_id}", json={"message": "go"},
            ) as response:
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.headers["cache-control"], "no-store, private")
                events = [
                    line.split(":", 1)[1].strip()
                    for line in response.iter_lines()
                    if line.startswith("event:")
                ]
        self.assertEqual(events, ["status", "metadata", "token", "done"])

    def test_a_streamed_error_is_still_delivered_as_events(self) -> None:
        async def explodes(agent: FakeAgent, message: str, previous: str | None):
            yield "status", {"phase": "model", "label": "first"}
            raise RuntimeError("upstream gone")

        client = client_with(FakeAgent(explodes))
        self.addCleanup(client.__exit__, None, None, None)
        with _auth_support.as_principal(_auth_support.DEFAULT):
            session_id = client.post("/api/sessions").json()["session_id"]
            body = client.post(f"/api/chat/{session_id}", json={"message": "go"}).text
        self.assertEqual([event for event, _ in frames(body)], ["status", "error"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
