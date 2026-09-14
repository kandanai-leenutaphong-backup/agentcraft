"""Verifier invariants. Pure function, so every case is a one-liner.

The point of these tests is not coverage but the security contract: every
failure mode must return the same shape, and no failure may leak why.
"""

from __future__ import annotations

import base64
import hashlib
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from devauth import verify


def _ts(offset: float = 0.0) -> str:
    return (datetime.now(timezone.utc)
            + timedelta(seconds=offset)).isoformat().replace("+00:00", "Z")


def _sign(key, method, path, ts, slug="", body=b"") -> str:
    canonical = (
        f"{method.upper()}\n{path}\n{ts}\n{slug.strip().lower()}\n"
        f"{hashlib.sha256(body).hexdigest()}"
    ).encode("ascii")
    return base64.b64encode(key.sign(canonical)).decode("ascii")


@pytest.fixture
def keypair():
    key = Ed25519PrivateKey.generate()
    pub = base64.b64encode(key.public_key().public_bytes_raw()).decode("ascii")
    return key, pub


def test_valid_signature_accepted(keypair):
    key, pub = keypair
    ts = _ts()
    r = verify(public_key_b64=pub, method="GET", path_and_query="/a", ts=ts,
               sig_b64=_sign(key, "GET", "/a", ts), body=b"")
    assert r.ok is True


@pytest.mark.parametrize(
    "method,path,body",
    [("POST", "/a", b""), ("GET", "/b", b""), ("GET", "/a", b"x")],
    ids=["method", "path", "body"],
)
def test_any_tampered_field_rejected(keypair, method, path, body):
    key, pub = keypair
    ts = _ts()
    sig = _sign(key, "GET", "/a", ts)
    assert verify(public_key_b64=pub, method=method, path_and_query=path,
                  ts=ts, sig_b64=sig, body=body).ok is False


@pytest.mark.parametrize("offset", [-600, 600], ids=["stale", "future"])
def test_timestamp_outside_skew_rejected(keypair, offset):
    key, pub = keypair
    ts = _ts(offset)
    assert verify(public_key_b64=pub, method="GET", path_and_query="/a", ts=ts,
                  sig_b64=_sign(key, "GET", "/a", ts), body=b"").ok is False


def test_signature_from_other_key_rejected(keypair):
    _, pub = keypair
    other = Ed25519PrivateKey.generate()
    ts = _ts()
    assert verify(public_key_b64=pub, method="GET", path_and_query="/a", ts=ts,
                  sig_b64=_sign(other, "GET", "/a", ts), body=b"").ok is False


@pytest.mark.parametrize(
    "pub", ["", "not-base64!!", base64.b64encode(b"tooshort").decode()],
    ids=["empty", "malformed", "wrong-length"],
)
def test_unusable_public_key_rejected(pub):
    ts = _ts()
    assert verify(public_key_b64=pub, method="GET", path_and_query="/a", ts=ts,
                  sig_b64="AAAA", body=b"").ok is False


@pytest.mark.parametrize(
    "slug",
    ["probe/../admin", "UPPER!", "x" * 65, "café", "has space"],
    ids=["traversal", "punctuation", "too-long", "non-ascii", "space"],
)
def test_illegal_slug_rejected_at_boundary(keypair, slug):
    """G4: an unvalidated slug becomes a downstream crash, not a 401.

    The slug is rejected before the canonical string is built, so no valid
    signature can exist for these values -- a well-behaved client cannot
    even encode some of them. The attacker case is a hostile slug sent with
    an arbitrary signature, which is what this asserts.
    """
    _, pub = keypair
    r = verify(public_key_b64=pub, method="GET", path_and_query="/a",
               ts=_ts(), sig_b64=base64.b64encode(b"\x00" * 64).decode(),
               body=b"", user_slug=slug)
    assert r.ok is False
    assert r.user_slug == ""


def test_slug_normalised_before_signing(keypair):
    key, pub = keypair
    ts = _ts()
    r = verify(public_key_b64=pub, method="GET", path_and_query="/a", ts=ts,
               sig_b64=_sign(key, "GET", "/a", ts, "Alice"), body=b"",
               user_slug="  Alice  ")
    assert r.ok is True and r.user_slug == "alice"


def test_failure_carries_no_diagnostic_information(keypair):
    """Every 'no' must be the same 'no'."""
    _, pub = keypair
    r = verify(public_key_b64=pub, method="GET", path_and_query="/a",
               ts=_ts(), sig_b64="AAAA", body=b"")
    assert r.ok is False
    assert r.user_slug == ""
    assert set(vars(type(r)).get("__dataclass_fields__", {})) <= {"ok",
                                                                  "user_slug"}
