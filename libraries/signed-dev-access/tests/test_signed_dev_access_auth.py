"""Adversarial tests for `signed_dev_access`.

Offline: no Azure account, no network, no browser. Every key is generated in memory and
discarded when the process exits; nothing here reads or writes a key file.

The battery is hostile on purpose. A signed-access mechanism that has only been tested with a
correct signature has been tested for availability, not for security, and the interesting
inputs are all the wrong ones: a tampered field, a stale clock, a re-encoded signature, a
second copy of a header, a body that never ends.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import unittest
from datetime import datetime, timedelta, timezone
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from signed_dev_access import (
    CONTEXT_HEADER,
    MAX_SIGNED_BODY_BYTES,
    MAX_SIGNED_BODY_CHUNKS,
    MAX_SKEW_SECONDS,
    SIGNATURE_HEADER,
    TIMESTAMP_HEADER,
    AzureTableReplayLedger,
    InProcessReplayLedger,
    ReplayLedgerUnavailable,
    SignedRequestASGIMiddleware,
    canonical_string,
    install_signed_request_auth,
    public_key_fingerprint,
    verify,
)

_B64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"


def now_text(offset_seconds: float = 0.0) -> str:
    moment = datetime.now(timezone.utc) + timedelta(seconds=offset_seconds)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def sign(
    key: Ed25519PrivateKey,
    method: str,
    path: str,
    ts: str,
    *,
    slug: str = "",
    body: bytes = b"",
) -> str:
    message = canonical_string(
        method=method,
        path_and_query=path,
        timestamp=ts,
        context_slug=slug.strip().lower(),
        body_sha256_hex=hashlib.sha256(body).hexdigest(),
    )
    return base64.b64encode(key.sign(message)).decode("ascii")


def public_b64(key: Ed25519PrivateKey) -> str:
    return base64.b64encode(key.public_key().public_bytes_raw()).decode("ascii")


def reencode(sig_b64: str) -> str:
    """Return a different base64 text that decodes to the same signature bytes.

    Sixty-four bytes encode as 88 base64 characters whose 86th carries two significant bits and
    four ignored ones, so sixteen distinct texts decode identically. Any ledger keyed on the
    header string therefore admits fifteen replays of a signature it has already accepted.
    """
    body, padding = sig_b64[:-2], sig_b64[-2:]
    value = _B64.index(body[-1])
    for candidate in range(64):
        if candidate != value and candidate & 0b110000 == value & 0b110000:
            return body[:-1] + _B64[candidate] + padding
    raise AssertionError("no alternative encoding found")


class VerifierTests(unittest.TestCase):
    def setUp(self) -> None:
        self.key = Ed25519PrivateKey.generate()
        self.pub = public_b64(self.key)
        self.ts = now_text()
        self.sig = sign(self.key, "GET", "/api/cyber/sources", self.ts)

    def call(self, **overrides: Any):
        arguments = {
            "public_key_b64": self.pub,
            "method": "GET",
            "path_and_query": "/api/cyber/sources",
            "ts": self.ts,
            "sig_b64": self.sig,
            "body": b"",
        }
        arguments.update(overrides)
        return verify(**arguments)

    def test_a_correct_signature_is_accepted(self) -> None:
        result = self.call()
        self.assertTrue(result.ok)
        self.assertEqual(result.user_slug, "")
        self.assertEqual(len(result.replay_key), 64)

    def test_every_tampered_field_is_rejected(self) -> None:
        cases = {
            "method": {"method": "POST"},
            "path": {"path_and_query": "/api/cyber/query"},
            "query": {"path_and_query": "/api/cyber/sources?limit=1"},
            "body": {"body": b"x"},
            "signature": {"sig_b64": base64.b64encode(b"\x00" * 64).decode("ascii")},
            "truncated signature": {"sig_b64": self.sig[:-4]},
            "signature not base64": {"sig_b64": "not base64!!"},
            "empty signature": {"sig_b64": ""},
            "empty timestamp": {"ts": ""},
            "timestamp without a zone": {"ts": "2026-09-06T00:00:00"},
            "timestamp not a date": {"ts": "yesterday"},
            "public key not base64": {"public_key_b64": "!!!"},
            "public key wrong length": {"public_key_b64": base64.b64encode(b"\x01" * 16).decode()},
            "public key empty": {"public_key_b64": ""},
            "non-ascii path": {"path_and_query": "/api/caf\u00e9"},
        }
        for label, override in cases.items():
            with self.subTest(label):
                self.assertFalse(self.call(**override).ok)

    def test_a_signature_from_another_key_is_rejected(self) -> None:
        other = Ed25519PrivateKey.generate()
        self.assertFalse(
            self.call(sig_b64=sign(other, "GET", "/api/cyber/sources", self.ts)).ok
        )

    def test_a_stale_or_future_timestamp_outside_the_window_is_rejected(self) -> None:
        for offset in (-MAX_SKEW_SECONDS - 30, MAX_SKEW_SECONDS + 30):
            with self.subTest(offset=offset):
                ts = now_text(offset)
                self.assertFalse(
                    self.call(ts=ts, sig_b64=sign(self.key, "GET", "/api/cyber/sources", ts)).ok
                )

    def test_the_skew_window_cannot_be_widened_by_configuration(self) -> None:
        import os

        from signed_dev_access import _verifier

        self.assertEqual(MAX_SKEW_SECONDS, 300)
        source = (_verifier.__file__ or "")
        with open(source, encoding="utf-8") as handle:
            text = handle.read()
        self.assertNotIn("os.environ", text)
        self.assertNotIn("getenv", text)
        os.environ["MAX_SKEW_SECONDS"] = "99999"
        try:
            ts = now_text(MAX_SKEW_SECONDS + 30)
            self.assertFalse(
                self.call(ts=ts, sig_b64=sign(self.key, "GET", "/api/cyber/sources", ts)).ok
            )
        finally:
            del os.environ["MAX_SKEW_SECONDS"]

    def test_retention_outlives_a_future_dated_signature(self) -> None:
        """A signature dated ahead stays usable after a naive 300 s TTL would have expired."""
        ts = now_text(MAX_SKEW_SECONDS - 30)
        result = self.call(ts=ts, sig_b64=sign(self.key, "GET", "/api/cyber/sources", ts))
        self.assertTrue(result.ok)
        naive_ttl = datetime.now(timezone.utc) + timedelta(seconds=MAX_SKEW_SECONDS)
        self.assertGreater(result.expires_at, naive_ttl)
        signed_at = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        self.assertEqual(result.expires_at, signed_at + timedelta(seconds=MAX_SKEW_SECONDS))

    def test_the_slug_is_normalised_and_bounded(self) -> None:
        for raw in ("Analyst", "  Analyst  "):
            with self.subTest(raw):
                ts = now_text()
                result = self.call(
                    ts=ts, user_slug=raw,
                    sig_b64=sign(self.key, "GET", "/api/cyber/sources", ts, slug=raw),
                )
                self.assertTrue(result.ok)
                self.assertEqual(result.user_slug, "analyst")

    def test_slug_length_boundary(self) -> None:
        for length, expected in ((64, True), (65, False)):
            with self.subTest(length=length):
                slug = "a" * length
                ts = now_text()
                result = self.call(
                    ts=ts, user_slug=slug,
                    sig_b64=sign(self.key, "GET", "/api/cyber/sources", ts, slug=slug),
                )
                self.assertEqual(result.ok, expected)

    def test_hostile_slugs_are_refused_at_the_boundary(self) -> None:
        """A slug that reaches a partition key or a path is a crash class, so it stops here."""
        for slug in ("probe/../admin", "a b", "caf\u00e9", "UPPER!", "a\nb", "a\x00b"):
            with self.subTest(slug):
                ts = now_text()
                try:
                    signature = sign(self.key, "GET", "/api/cyber/sources", ts, slug=slug)
                except UnicodeEncodeError:
                    # A non-ASCII slug cannot even be signed: the canonical string is ASCII.
                    signature = sign(self.key, "GET", "/api/cyber/sources", ts)
                self.assertFalse(self.call(ts=ts, user_slug=slug, sig_b64=signature).ok)

    def test_oversized_inputs_are_refused_before_any_parsing(self) -> None:
        for label, override in {
            "timestamp": {"ts": "2" * 4096},
            "signature": {"sig_b64": "A" * 4096},
            "context": {"user_slug": "a" * 4096},
            "path": {"path_and_query": "/" + "a" * 20_000},
        }.items():
            with self.subTest(label):
                self.assertFalse(self.call(**override).ok)

    def test_failure_carries_no_reason(self) -> None:
        result = self.call(method="POST")
        self.assertFalse(result.ok)
        self.assertEqual(result.user_slug, "")
        self.assertEqual(result.replay_key, "")
        self.assertIsNone(result.expires_at)
        self.assertFalse(hasattr(result, "reason"))

    def test_a_re_encoded_signature_verifies_and_keys_identically(self) -> None:
        """The base64 text is malleable; the bytes are not, and the bytes are the ledger key."""
        variant = reencode(self.sig)
        self.assertNotEqual(variant, self.sig)
        self.assertEqual(base64.b64decode(variant), base64.b64decode(self.sig))
        first, second = self.call(), self.call(sig_b64=variant)
        self.assertTrue(first.ok and second.ok)
        self.assertEqual(first.replay_key, second.replay_key)

    def test_the_fingerprint_is_stable_derived_and_not_the_key(self) -> None:
        fingerprint = public_key_fingerprint(self.pub)
        self.assertEqual(len(fingerprint), 16)
        self.assertEqual(fingerprint, public_key_fingerprint(f"  {self.pub}  "))
        self.assertNotIn(fingerprint, self.pub)
        self.assertNotEqual(fingerprint, public_key_fingerprint(public_b64(Ed25519PrivateKey.generate())))
        self.assertEqual(public_key_fingerprint(""), "")
        self.assertEqual(public_key_fingerprint("nonsense"), "")


class InProcessLedgerTests(unittest.IsolatedAsyncioTestCase):
    def deadline(self, seconds: float = 300.0) -> datetime:
        return datetime.now(timezone.utc) + timedelta(seconds=seconds)

    async def test_a_key_is_claimable_once(self) -> None:
        ledger = InProcessReplayLedger()
        self.assertTrue(await ledger.claim("a", self.deadline()))
        self.assertFalse(await ledger.claim("a", self.deadline()))
        self.assertTrue(await ledger.claim("b", self.deadline()))

    async def test_exactly_one_of_many_concurrent_claims_wins(self) -> None:
        ledger = InProcessReplayLedger()
        results = await asyncio.gather(
            *(ledger.claim("same", self.deadline()) for _ in range(50))
        )
        self.assertEqual(sum(results), 1)

    async def test_an_expired_key_is_reclaimable_only_after_it_can_no_longer_verify(self) -> None:
        ledger = InProcessReplayLedger()
        self.assertTrue(await ledger.claim("a", self.deadline(-1)))
        self.assertTrue(await ledger.claim("a", self.deadline()))
        self.assertFalse(await ledger.claim("a", self.deadline()))

    async def test_a_full_ledger_denies_rather_than_evicting_a_live_key(self) -> None:
        ledger = InProcessReplayLedger(max_entries=2)
        await ledger.claim("a", self.deadline())
        await ledger.claim("b", self.deadline())
        with self.assertRaises(ReplayLedgerUnavailable):
            await ledger.claim("c", self.deadline())
        self.assertFalse(await ledger.claim("a", self.deadline()))

    async def test_it_declares_itself_not_durable(self) -> None:
        self.assertFalse(InProcessReplayLedger.durable)
        self.assertTrue(AzureTableReplayLedger.durable)


class ResourceExistsError(Exception):
    """Named exactly as the Azure SDK exception the adapter branches on."""


class ServiceRequestError(Exception):
    """Named exactly as an Azure SDK transport failure."""


class FakeTableClient:
    """Table client with the conflict semantics the real service has."""

    def __init__(self, *, fail_writes: bool = False, fail_create_table: bool = False) -> None:
        self.entities: dict[tuple[str, str], dict[str, Any]] = {}
        self.fail_writes = fail_writes
        self.fail_create_table = fail_create_table
        self.created_table = 0
        self.closed = False

    async def create_table(self) -> None:
        self.created_table += 1
        if self.fail_create_table:
            raise ServiceRequestError("table service unreachable")
        if self.created_table > 1:
            raise ResourceExistsError("table exists")

    async def create_entity(self, entity: dict[str, Any]) -> None:
        if self.fail_writes:
            raise ServiceRequestError("table service unreachable")
        key = (entity["PartitionKey"], entity["RowKey"])
        if key in self.entities:
            raise ResourceExistsError("entity exists")
        self.entities[key] = dict(entity)

    def query_entities(self, _filter: str, parameters: dict[str, Any]):
        stored = [
            entity for entity in self.entities.values()
            if entity["ExpiresAt"] <= parameters["cutoff"]
        ]

        async def iterator():
            for entity in stored:
                yield entity

        return iterator()

    async def delete_entity(self, partition_key: str, row_key: str) -> None:
        self.entities.pop((partition_key, row_key), None)

    async def close(self) -> None:
        self.closed = True


class AzureTableLedgerTests(unittest.IsolatedAsyncioTestCase):
    def build(self, client: FakeTableClient) -> AzureTableReplayLedger:
        return AzureTableReplayLedger(
            endpoint="https://example.table.core.windows.net",
            table_name="devauthreplay",
            client_factory=lambda: client,
        )

    def deadline(self, seconds: float = 300.0) -> datetime:
        return datetime.now(timezone.utc) + timedelta(seconds=seconds)

    async def test_a_conflicting_insert_is_a_replay_not_an_error(self) -> None:
        ledger = self.build(FakeTableClient())
        self.assertTrue(await ledger.claim("k", self.deadline()))
        self.assertFalse(await ledger.claim("k", self.deadline()))

    async def test_exactly_one_of_many_concurrent_claims_wins(self) -> None:
        ledger = self.build(FakeTableClient())
        results = await asyncio.gather(*(ledger.claim("k", self.deadline()) for _ in range(25)))
        self.assertEqual(sum(results), 1)

    async def test_an_outage_fails_closed_rather_than_admitting_the_request(self) -> None:
        ledger = self.build(FakeTableClient(fail_writes=True))
        with self.assertRaises(ReplayLedgerUnavailable):
            await ledger.claim("k", self.deadline())

    async def test_an_unreachable_table_service_fails_closed_at_setup(self) -> None:
        ledger = self.build(FakeTableClient(fail_create_table=True))
        with self.assertRaises(ReplayLedgerUnavailable):
            await ledger.claim("k", self.deadline())

    async def test_the_table_is_created_once_and_an_existing_one_is_fine(self) -> None:
        client = FakeTableClient()
        ledger = self.build(client)
        await ledger.claim("a", self.deadline())
        await ledger.claim("b", self.deadline())
        self.assertEqual(client.created_table, 1)

    async def test_stored_rows_carry_no_caller_or_request_detail(self) -> None:
        client = FakeTableClient()
        await self.build(client).claim("k", self.deadline())
        stored = next(iter(client.entities.values()))
        self.assertEqual(set(stored), {"PartitionKey", "RowKey", "ExpiresAt"})

    async def test_purge_removes_only_signatures_that_can_no_longer_verify(self) -> None:
        client = FakeTableClient()
        ledger = self.build(client)
        await ledger.claim("live", self.deadline(300))
        await ledger.claim("dead", self.deadline(-300))
        self.assertEqual(await ledger.purge_expired(), 1)
        self.assertEqual([key[1] for key in client.entities], ["live"])

    async def test_the_row_key_is_hex_and_therefore_a_legal_table_key(self) -> None:
        client = FakeTableClient()
        key = hashlib.sha256(b"signature").hexdigest()
        await self.build(client).claim(key, self.deadline())
        row = next(iter(client.entities))[1]
        self.assertEqual(row, key)
        for illegal in "/\\#?":
            self.assertNotIn(illegal, row)

    async def test_endpoint_and_table_are_required(self) -> None:
        for endpoint, table in (("", "t"), ("https://x", "")):
            with self.subTest(endpoint=endpoint, table=table), self.assertRaises(ValueError):
                AzureTableReplayLedger(endpoint=endpoint, table_name=table)

    async def test_close_releases_the_client(self) -> None:
        client = FakeTableClient()
        ledger = self.build(client)
        await ledger.claim("k", self.deadline())
        await ledger.close()
        self.assertTrue(client.closed)


class _Recorder:
    """Inner ASGI app that records what reached it."""

    def __init__(self, *, stream: bool = False) -> None:
        self.reached = 0
        self.body: bytes | None = None
        self.scope: dict | None = None
        self.stream = stream

    async def __call__(self, scope: dict, receive, send) -> None:
        self.reached += 1
        self.scope = scope
        message = await receive()
        self.body = message.get("body")
        await send({"type": "http.response.start", "status": 200, "headers": []})
        if self.stream:
            await send({"type": "http.response.body", "body": b"one", "more_body": True})
            await send({"type": "http.response.body", "body": b"two", "more_body": False})
        else:
            await send({"type": "http.response.body", "body": b"ok", "more_body": False})


async def drive(middleware, scope: dict, chunks: list[dict] | None = None):
    """Run one request through the middleware; return (status, response headers, body)."""
    queue = list(chunks or [{"type": "http.request", "body": b"", "more_body": False}])
    sent: list[dict] = []

    async def receive() -> dict:
        return queue.pop(0) if queue else {"type": "http.disconnect"}

    async def send(message: dict) -> None:
        sent.append(message)

    await middleware(scope, receive, send)
    start = next((m for m in sent if m["type"] == "http.response.start"), None)
    body = b"".join(m.get("body") or b"" for m in sent if m["type"] == "http.response.body")
    return (start or {}).get("status", 0), (start or {}).get("headers", []), body


class MiddlewareTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.key = Ed25519PrivateKey.generate()
        self.pub = public_b64(self.key)
        self.identities: list[str] = []

    def build(self, inner, *, ledger=None, public_key: str | None = None):
        def factory(slug: str) -> str:
            self.identities.append(slug)
            return f"principal:{slug or 'default'}"

        return SignedRequestASGIMiddleware(
            inner,
            public_key_b64=self.pub if public_key is None else public_key,
            identity_factory=factory,
            replay_ledger=InProcessReplayLedger() if ledger is None else ledger,
        )

    def scope(self, method: str, raw_path: bytes, headers: list, query: bytes = b"") -> dict:
        return {
            "type": "http", "method": method, "raw_path": raw_path,
            "path": raw_path.decode("latin-1"), "query_string": query, "headers": headers,
        }

    def headers(self, ts: str, sig: str, slug: str | None = None) -> list[tuple[bytes, bytes]]:
        items = [
            (TIMESTAMP_HEADER.lower().encode(), ts.encode()),
            (SIGNATURE_HEADER.lower().encode(), sig.encode()),
        ]
        if slug is not None:
            items.append((CONTEXT_HEADER.lower().encode(), slug.encode()))
        return items

    async def test_a_signed_request_reaches_the_app_with_a_principal(self) -> None:
        inner = _Recorder()
        ts = now_text()
        scope = self.scope("GET", b"/api/health", self.headers(ts, sign(self.key, "GET", "/api/health", ts)))
        status, _, body = await drive(self.build(inner), scope)
        self.assertEqual((status, body), (200, b"ok"))
        self.assertEqual(inner.scope["auth_principal"], "principal:default")
        self.assertEqual(self.identities, [""])

    async def test_the_context_slug_reaches_the_identity_factory(self) -> None:
        inner = _Recorder()
        ts = now_text()
        sig = sign(self.key, "GET", "/api/health", ts, slug="Pilot")
        scope = self.scope("GET", b"/api/health", self.headers(ts, sig, "Pilot"))
        status, _, _ = await drive(self.build(inner), scope)
        self.assertEqual(status, 200)
        self.assertEqual(self.identities, ["pilot"])
        self.assertEqual(inner.scope["auth_principal"], "principal:pilot")

    async def test_an_unsigned_request_passes_through_untouched(self) -> None:
        inner = _Recorder()
        status, _, _ = await drive(self.build(inner), self.scope("GET", b"/api/health", []))
        self.assertEqual(status, 200)
        self.assertIsNone(inner.scope.get("auth_principal"))

    async def test_every_bad_signed_request_is_the_same_bare_401(self) -> None:
        ts = now_text()
        good = sign(self.key, "GET", "/api/health", ts)
        other = Ed25519PrivateKey.generate()
        stale = now_text(-MAX_SKEW_SECONDS - 60)
        cases = {
            "forged": self.headers(ts, base64.b64encode(b"\x01" * 64).decode()),
            "wrong key": self.headers(ts, sign(other, "GET", "/api/health", ts)),
            "wrong path": self.headers(ts, sign(self.key, "GET", "/api/other", ts)),
            "stale": self.headers(stale, sign(self.key, "GET", "/api/health", stale)),
            "garbage signature": self.headers(ts, "%%%%"),
            "hostile slug": self.headers(ts, good, "probe/../admin"),
        }
        for label, headers in cases.items():
            with self.subTest(label):
                inner = _Recorder()
                status, response_headers, body = await drive(
                    self.build(inner), self.scope("GET", b"/api/health", headers),
                )
                self.assertEqual(status, 401)
                self.assertEqual(body, b"")
                self.assertEqual(inner.reached, 0)
                names = {name.lower() for name, _ in response_headers}
                self.assertNotIn(b"www-authenticate", names)
                self.assertIn((b"cache-control", b"no-store, private"), response_headers)

    async def test_a_duplicated_signing_header_is_refused_not_resolved(self) -> None:
        ts = now_text()
        good = sign(self.key, "GET", "/api/health", ts)
        forged = base64.b64encode(b"\x02" * 64).decode()
        for label, headers in {
            "two signatures": self.headers(ts, good) + [
                (SIGNATURE_HEADER.lower().encode(), forged.encode()),
            ],
            "two timestamps": self.headers(ts, good) + [
                (TIMESTAMP_HEADER.lower().encode(), now_text(-5).encode()),
            ],
            "two contexts": self.headers(ts, good, "a") + [
                (CONTEXT_HEADER.lower().encode(), b"b"),
            ],
        }.items():
            with self.subTest(label):
                inner = _Recorder()
                status, _, _ = await drive(
                    self.build(inner), self.scope("GET", b"/api/health", headers),
                )
                self.assertEqual(status, 401)
                self.assertEqual(inner.reached, 0)

    async def test_a_replayed_signature_is_refused(self) -> None:
        ledger = InProcessReplayLedger()
        ts = now_text()
        sig = sign(self.key, "GET", "/api/health", ts)
        scope = lambda: self.scope("GET", b"/api/health", self.headers(ts, sig))  # noqa: E731
        first, _, _ = await drive(self.build(_Recorder(), ledger=ledger), scope())
        inner = _Recorder()
        second, _, _ = await drive(self.build(inner, ledger=ledger), scope())
        self.assertEqual((first, second), (200, 401))
        self.assertEqual(inner.reached, 0)

    async def test_a_re_encoded_replay_is_refused(self) -> None:
        """The same signature wearing different base64 is the same signature."""
        ledger = InProcessReplayLedger()
        ts = now_text()
        sig = sign(self.key, "GET", "/api/health", ts)
        first, _, _ = await drive(
            self.build(_Recorder(), ledger=ledger),
            self.scope("GET", b"/api/health", self.headers(ts, sig)),
        )
        inner = _Recorder()
        second, _, _ = await drive(
            self.build(inner, ledger=ledger),
            self.scope("GET", b"/api/health", self.headers(ts, reencode(sig))),
        )
        self.assertEqual((first, second), (200, 401))
        self.assertEqual(inner.reached, 0)

    async def test_concurrent_replays_admit_exactly_one(self) -> None:
        ledger = InProcessReplayLedger()
        ts = now_text()
        sig = sign(self.key, "GET", "/api/health", ts)
        statuses = await asyncio.gather(*(
            drive(
                self.build(_Recorder(), ledger=ledger),
                self.scope("GET", b"/api/health", self.headers(ts, sig)),
            )
            for _ in range(20)
        ))
        self.assertEqual(sum(1 for status, _, _ in statuses if status == 200), 1)

    async def test_a_ledger_outage_denies_the_request(self) -> None:
        class Broken:
            async def claim(self, key: str, expires_at: datetime) -> bool:
                raise ReplayLedgerUnavailable("down")

        inner = _Recorder()
        ts = now_text()
        status, _, _ = await drive(
            self.build(inner, ledger=Broken()),
            self.scope("GET", b"/api/health", self.headers(ts, sign(self.key, "GET", "/api/health", ts))),
        )
        self.assertEqual(status, 401)
        self.assertEqual(inner.reached, 0)

    async def test_the_query_string_and_encoded_path_are_signed_as_sent(self) -> None:
        ts = now_text()
        sig = sign(self.key, "GET", "/api/topology/A%0AB?limit=10", ts)
        scope = self.scope("GET", b"/api/topology/A%0AB", self.headers(ts, sig), query=b"limit=10")
        scope["path"] = "/api/topology/A\nB"
        status, _, _ = await drive(self.build(_Recorder()), scope)
        self.assertEqual(status, 200)

    async def test_a_signed_body_verifies_and_is_replayed_once(self) -> None:
        payload = b'{"message":"hello"}'
        ts = now_text()
        sig = sign(self.key, "POST", "/api/chat/abc", ts, body=payload)
        inner = _Recorder()
        status, _, _ = await drive(
            self.build(inner), self.scope("POST", b"/api/chat/abc", self.headers(ts, sig)),
            chunks=[
                {"type": "http.request", "body": payload[:5], "more_body": True},
                {"type": "http.request", "body": payload[5:], "more_body": False},
            ],
        )
        self.assertEqual(status, 200)
        self.assertEqual(inner.body, payload)

    async def test_an_oversized_body_is_refused_without_buffering_it_all(self) -> None:
        ts = now_text()
        sig = sign(self.key, "POST", "/api/chat/abc", ts, body=b"")
        chunk = b"x" * 65536
        count = MAX_SIGNED_BODY_BYTES // len(chunk) + 4
        inner = _Recorder()
        status, _, _ = await drive(
            self.build(inner), self.scope("POST", b"/api/chat/abc", self.headers(ts, sig)),
            chunks=[{"type": "http.request", "body": chunk, "more_body": True} for _ in range(count)],
        )
        self.assertEqual(status, 401)
        self.assertEqual(inner.reached, 0)

    async def test_an_endless_stream_of_empty_chunks_terminates(self) -> None:
        ts = now_text()
        sig = sign(self.key, "POST", "/api/chat/abc", ts, body=b"")
        inner = _Recorder()
        status, _, _ = await asyncio.wait_for(
            drive(
                self.build(inner), self.scope("POST", b"/api/chat/abc", self.headers(ts, sig)),
                chunks=[
                    {"type": "http.request", "body": b"", "more_body": True}
                    for _ in range(MAX_SIGNED_BODY_CHUNKS + 10)
                ],
            ),
            timeout=10,
        )
        self.assertEqual(status, 401)
        self.assertEqual(inner.reached, 0)

    async def test_a_disconnect_during_the_body_denies(self) -> None:
        ts = now_text()
        sig = sign(self.key, "POST", "/api/chat/abc", ts, body=b"abc")
        inner = _Recorder()
        status, _, _ = await drive(
            self.build(inner), self.scope("POST", b"/api/chat/abc", self.headers(ts, sig)),
            chunks=[
                {"type": "http.request", "body": b"ab", "more_body": True},
                {"type": "http.disconnect"},
            ],
        )
        self.assertEqual(status, 401)
        self.assertEqual(inner.reached, 0)

    async def test_a_streamed_response_is_not_buffered(self) -> None:
        ts = now_text()
        sig = sign(self.key, "GET", "/api/cyber/scan/stream", ts)
        inner = _Recorder(stream=True)
        sent: list[dict] = []

        async def receive() -> dict:
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message: dict) -> None:
            sent.append(message)

        await self.build(inner)(
            self.scope("GET", b"/api/cyber/scan/stream", self.headers(ts, sig)), receive, send,
        )
        bodies = [m for m in sent if m["type"] == "http.response.body"]
        self.assertEqual([m["body"] for m in bodies], [b"one", b"two"])
        self.assertTrue(bodies[0]["more_body"])

    async def test_non_http_scopes_pass_through(self) -> None:
        seen: list[str] = []

        async def inner(scope: dict, receive, send) -> None:
            seen.append(scope["type"])

        await self.build(inner)({"type": "lifespan"}, None, None)
        self.assertEqual(seen, ["lifespan"])


class InstallationTests(unittest.TestCase):
    class FakeApp:
        def __init__(self) -> None:
            self.mounted: list[tuple] = []

        def add_middleware(self, cls, **kwargs) -> None:
            self.mounted.append((cls, kwargs))

    def setUp(self) -> None:
        self.key = Ed25519PrivateKey.generate()
        self.pub = public_b64(self.key)

    def test_no_key_means_nothing_is_mounted(self) -> None:
        for value in ("", "   ", None):
            with self.subTest(repr(value)):
                app = self.FakeApp()
                mounted = install_signed_request_auth(
                    app, public_key_b64=value, identity_factory=lambda slug: slug,
                    replay_ledger=InProcessReplayLedger(),
                )
                self.assertFalse(mounted)
                self.assertEqual(app.mounted, [])

    def test_a_key_mounts_exactly_one_middleware_with_the_key_stripped(self) -> None:
        app = self.FakeApp()
        mounted = install_signed_request_auth(
            app, public_key_b64=f"  {self.pub}  ", identity_factory=lambda slug: slug,
            replay_ledger=InProcessReplayLedger(),
        )
        self.assertTrue(mounted)
        self.assertEqual(len(app.mounted), 1)
        self.assertEqual(app.mounted[0][1]["public_key_b64"], self.pub)

    def test_a_ledger_is_not_optional(self) -> None:
        """No per-process default: the absence of a shared ledger has to be a decision."""
        with self.assertRaises(ValueError):
            install_signed_request_auth(
                self.FakeApp(), public_key_b64=self.pub,
                identity_factory=lambda slug: slug, replay_ledger=None,
            )
        with self.assertRaises(ValueError):
            SignedRequestASGIMiddleware(
                None, public_key_b64=self.pub, identity_factory=lambda slug: slug,
                replay_ledger=None,
            )

    def test_the_class_refuses_an_empty_key_rather_than_passing_everything(self) -> None:
        """Constructing with no key must fail loudly, not silently verify against nothing."""
        with self.assertRaises(ValueError):
            SignedRequestASGIMiddleware(
                None, public_key_b64="", identity_factory=lambda slug: slug,
                replay_ledger=InProcessReplayLedger(),
            )

    def test_the_component_holds_no_bypass_and_no_logging(self) -> None:
        from signed_dev_access import _middleware, _replay, _verifier

        for module in (_middleware, _replay, _verifier):
            with self.subTest(module.__name__):
                with open(module.__file__ or "", encoding="utf-8") as handle:
                    text = handle.read()
                for banned in ("import logging", "getLogger", "AUTH_ENABLED", "DEV_PRINCIPAL"):
                    self.assertNotIn(banned, text)

    def test_the_component_imports_standalone(self) -> None:
        """It must carry no dependency on this application, so it moves to another one."""
        import importlib

        module = importlib.import_module("signed_dev_access")
        for name in module.__all__:
            self.assertTrue(hasattr(module, name), name)
        for submodule in ("_middleware", "_replay", "_verifier"):
            source = importlib.import_module(f"signed_dev_access.{submodule}")
            with open(source.__file__ or "", encoding="utf-8") as handle:
                text = handle.read()
            self.assertNotIn("app.cybereye", text)
            self.assertNotIn("fastapi", text.lower())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
