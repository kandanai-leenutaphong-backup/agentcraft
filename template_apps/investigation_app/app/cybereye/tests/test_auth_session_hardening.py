"""Hardening battery for the one route a stranger may post to, and for flow consumption.

Three things are pinned here:

* **F8** ``/auth/session`` buffered an unbounded body before anything about the caller had
  been established. It is the only route in the application that must read bytes from someone
  who has proved nothing, so its ceiling is the difference between a public endpoint and a
  memory allocator.
* **F3** ``claim_flow`` must use the store's atomic consume. Read-then-delete handed two
  concurrent callbacks the same PKCE verifier.
* **F1** the browser client must send the same-origin JSON headers the cross-site guard
  requires. There is no JavaScript test runner in this repository, so the client is pinned by
  reading it; the behavioural proof is the real-cookie browser walk in ``deploy/``.
"""

from __future__ import annotations

import asyncio
import json
import re
import unittest
from datetime import timedelta
from pathlib import Path

from app.components.entra_auth import InProcessRecordStore, RecordStoreUnavailable, new_flow
from app.cybereye.backend.security import BrowserSessions
from app.cybereye.backend.security.signin_routes import (
    MAX_SESSION_BODY_BYTES,
    MAX_SESSION_BODY_CHUNKS,
    _OVERSIZED,
    _read_bounded_body,
)

from test_entra_signin import ORIGIN, Signer, build_app, client_for


class BoundedSessionBodyTests(unittest.TestCase):
    """The public token-for-cookie exchange reads a bounded body or refuses."""

    def setUp(self) -> None:
        self.signer = Signer()
        self.app, _ = build_app(self.signer)
        self.client = client_for(self.app)

    def _post(self, content, headers=None):
        return self.client.post(
            "/auth/session",
            headers={"Origin": ORIGIN, "Content-Type": "application/json", **(headers or {})},
            content=content,
        )

    def test_a_declared_oversize_body_is_refused_before_it_is_read(self) -> None:
        response = self._post(b"x" * (MAX_SESSION_BODY_BYTES + 1))
        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.content, b"")

    def test_a_streamed_oversize_body_is_refused_without_a_declared_length(self) -> None:
        """Chunked, so nothing declares the size. The ceiling has to hold on the stream too."""
        def chunks():
            for _ in range(8):
                yield b"x" * 4096

        response = self._post(chunks())
        self.assertEqual(response.status_code, 413)

    def test_a_body_at_the_ceiling_is_read_and_judged_on_its_contents(self) -> None:
        """The ceiling admits a real token. Refusal past it is a size decision, not a shortcut."""
        payload = json.dumps({"access_token": "a" * (MAX_SESSION_BODY_BYTES - 40)})
        self.assertLessEqual(len(payload), MAX_SESSION_BODY_BYTES)
        self.assertEqual(self._post(payload).status_code, 401)

    def test_malformed_json_is_a_bare_400(self) -> None:
        response = self._post(b"{not json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b"")

    def test_a_non_object_body_is_refused(self) -> None:
        for body in (b"[]", b'"token"', b"null", b"12"):
            with self.subTest(body=body):
                self.assertEqual(self._post(body).status_code, 400)

    def test_the_content_type_is_matched_case_insensitively(self) -> None:
        """``Application/JSON; charset=UTF-8`` is JSON. Rejecting it breaks real clients."""
        response = self._post(
            json.dumps({"access_token": "no"}),
            headers={"Content-Type": "Application/JSON; charset=UTF-8"},
        )
        self.assertEqual(response.status_code, 401)

    def test_a_non_json_content_type_is_refused(self) -> None:
        for value in ("text/plain", "application/x-www-form-urlencoded", ""):
            with self.subTest(content_type=value):
                response = self._post(b"{}", headers={"Content-Type": value})
                self.assertEqual(response.status_code, 415)

    def test_a_foreign_origin_is_refused_before_the_body_is_touched(self) -> None:
        response = self.client.post(
            "/auth/session",
            headers={"Origin": "https://evil.example", "Content-Type": "application/json"},
            content=b"x" * (MAX_SESSION_BODY_BYTES + 1),
        )
        self.assertEqual(response.status_code, 403)

    def test_no_refusal_reflects_what_the_caller_sent(self) -> None:
        marker = "ReFlEcTeD-MaRkEr-9137"
        for content, headers in (
            (json.dumps({"access_token": marker}), None),
            (f"{{bad {marker}".encode(), None),
            (b"{}", {"Content-Type": f"text/{marker}"}),
        ):
            with self.subTest(headers=headers):
                response = self._post(content, headers)
                self.assertNotIn(marker.encode(), response.content)
                self.assertNotIn(marker, " ".join(response.headers.values()))


class _StubRequest:
    """Just enough Request for the bounded reader: a stream and a disconnect answer."""

    def __init__(self, chunks, *, disconnected: bool = False) -> None:
        self._chunks = chunks
        self._disconnected = disconnected

    async def stream(self):
        for chunk in self._chunks:
            if isinstance(chunk, Exception):
                raise chunk
            yield chunk

    async def is_disconnected(self) -> bool:
        return self._disconnected


class BoundedReaderTests(unittest.IsolatedAsyncioTestCase):
    """The reader itself, where the transport cannot coalesce chunks out of the way.

    An HTTP client is free to merge a generator's chunks into one frame, so the chunk ceiling
    is unobservable through ``TestClient``. It still has to hold: a malformed chunked stream
    of empty chunks never reaches the byte ceiling and would otherwise hold the connection.
    """

    async def test_a_stream_of_empty_chunks_is_refused_by_the_chunk_ceiling(self) -> None:
        chunks = [b""] * (MAX_SESSION_BODY_CHUNKS + 10)
        self.assertIs(await _read_bounded_body(_StubRequest(chunks)), _OVERSIZED)

    async def test_the_byte_ceiling_stops_before_buffering_everything(self) -> None:
        chunks = [b"x" * 1024] * (MAX_SESSION_BODY_BYTES // 1024 + 4)
        self.assertIs(await _read_bounded_body(_StubRequest(chunks)), _OVERSIZED)

    async def test_a_body_inside_both_ceilings_is_returned_whole(self) -> None:
        self.assertEqual(await _read_bounded_body(_StubRequest([b"ab", b"cd"])), b"abcd")

    async def test_a_broken_stream_is_none_not_a_partial_body(self) -> None:
        self.assertIsNone(await _read_bounded_body(_StubRequest([b"ab", RuntimeError("reset")])))

    async def test_a_caller_that_vanished_is_none(self) -> None:
        self.assertIsNone(await _read_bounded_body(_StubRequest([b"{}"], disconnected=True)))


class _RecordingStore(InProcessRecordStore):
    """Counts which primitive the service reached for, and suspends the way a network does."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[str] = []

    async def get(self, key):
        self.calls.append("get")
        await asyncio.sleep(0)
        return await super().get(key)

    async def delete(self, key):
        self.calls.append("delete")
        await asyncio.sleep(0)
        return await super().delete(key)

    async def consume(self, key):
        self.calls.append("consume")
        await asyncio.sleep(0)
        return await super().consume(key)


class _BrokenStore(InProcessRecordStore):
    async def consume(self, key):
        raise RecordStoreUnavailable("store is down")


def _sessions(flow_store) -> BrowserSessions:
    return BrowserSessions(
        store=InProcessRecordStore(), flow_store=flow_store, max_lifetime=timedelta(hours=8),
    )


class FlowClaimTests(unittest.IsolatedAsyncioTestCase):
    async def test_a_claim_uses_the_atomic_primitive_and_never_read_then_delete(self) -> None:
        store = _RecordingStore()
        sessions = _sessions(store)
        flow = new_flow(return_to="/")
        await sessions.start_flow(flow, ttl=timedelta(seconds=300))
        store.calls.clear()
        self.assertIsNotNone(await sessions.claim_flow(flow.flow_id, flow.state))
        self.assertEqual(store.calls, ["consume"])

    async def test_fifty_concurrent_claims_produce_one_winner(self) -> None:
        store = _RecordingStore()
        sessions = _sessions(store)
        flow = new_flow(return_to="/")
        await sessions.start_flow(flow, ttl=timedelta(seconds=300))
        results = await asyncio.gather(
            *(sessions.claim_flow(flow.flow_id, flow.state) for _ in range(50))
        )
        self.assertEqual(sum(1 for r in results if r is not None), 1)

    async def test_a_wrong_state_still_spends_the_flow(self) -> None:
        """A flow that survives a failed attempt is one an attacker may keep trying."""
        store = _RecordingStore()
        sessions = _sessions(store)
        flow = new_flow(return_to="/")
        await sessions.start_flow(flow, ttl=timedelta(seconds=300))
        self.assertIsNone(await sessions.claim_flow(flow.flow_id, "w" * len(flow.state)))
        self.assertIsNone(await sessions.claim_flow(flow.flow_id, flow.state))

    async def test_a_malformed_identifier_never_reaches_the_store(self) -> None:
        store = _RecordingStore()
        sessions = _sessions(store)
        good = new_flow(return_to="/")
        await sessions.start_flow(good, ttl=timedelta(seconds=300))
        store.calls.clear()
        for flow_id, state in (
            ("", good.state), (good.flow_id, ""),
            ("short", good.state), (good.flow_id, "short"),
            ("x" * 4096, good.state), (good.flow_id, "y" * 4096),
            ("has spaces here!", good.state), (good.flow_id, "has/slashes+here="),
        ):
            with self.subTest(flow_id=flow_id[:12], state=state[:12]):
                self.assertIsNone(await sessions.claim_flow(flow_id, state))
        self.assertEqual(store.calls, [])

    async def test_a_broken_store_refuses_rather_than_admitting(self) -> None:
        sessions = _sessions(_BrokenStore())
        with self.assertRaises(RecordStoreUnavailable):
            await sessions.claim_flow("a" * 32, "b" * 32)


class BrowserClientContractTests(unittest.TestCase):
    """The client half of the cross-site guard, pinned by reading the client.

    The guard requires a same-origin JSON request for any unsafe method carrying a cookie. A
    client that omits the content type is refused 403 for every human while signed developer
    access — which carries a header, not a cookie — keeps working, so no automated check
    noticed. This asserts the shape; the behaviour is proved in a real browser by
    ``deploy/verify_entra_cookie_journey.py``.
    """

    SOURCE = Path(__file__).resolve().parents[1] / "frontend" / "src" / "shared" / "api" / "api.ts"

    def setUp(self) -> None:
        self.text = self.SOURCE.read_text(encoding="utf-8")

    def test_every_unsafe_fetch_declares_json(self) -> None:
        calls = re.findall(r"fetch\((?:[^()]|\([^()]*\))*\)", self.text, flags=re.S)
        unsafe = [c for c in calls if re.search(r'method:\s*"(POST|PUT|PATCH|DELETE)"', c)]
        self.assertTrue(unsafe, "no unsafe requests found; the parser has drifted")
        for call in unsafe:
            with self.subTest(call=call[:70]):
                self.assertTrue(
                    "headers: json" in call or "...json" in call,
                    "an unsafe same-origin request must declare application/json",
                )

    def test_session_creation_sends_a_body_and_same_origin_credentials(self) -> None:
        call = re.search(r'fetch\("/api/sessions".*?\}\)', self.text, flags=re.S)
        self.assertIsNotNone(call)
        self.assertIn("headers: json", call.group(0))
        self.assertIn('credentials: "same-origin"', call.group(0))
        self.assertIn("body:", call.group(0))

    def test_sign_out_checks_the_response_before_navigating(self) -> None:
        body = self.text[self.text.index("export async function signOut"):]
        body = body[: body.index("\n}\n") + 3]
        self.assertIn("response.ok", body)
        navigate = body.index("window.location.assign")
        self.assertLess(body.index("response.ok"), navigate,
                        "sign-out must judge the response before it navigates")
        self.assertIn("throw new Error", body)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
