"""Ed25519 request-signature verification — a pure function that never logs.

The security-critical primitive, kept alone so a review of it fits on one screen and so every
tampered input can be unit-tested without an ASGI stack.

No logging anywhere in this module, at any level. A failed verification must look identical to
"no authentication attempted" from every vantage point including the server's own logs, so
every failure collapses to one falsy result carrying no reason.

Domain-blind: this is transport cryptography. The verified context slug leaves as an opaque
string and the consumer's injected factory decides what identity it means.
"""

from __future__ import annotations

import base64
import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

#: Allowed shape of the normalised context slug. Empty matches: the consumer maps it to a
#: default identity. Validated at the trust boundary so a hostile slug cannot become a crash
#: class downstream (a partition key, a path segment, a cache key).
_SLUG = re.compile(r"^[a-z0-9_-]{0,64}$")

#: Maximum tolerated difference between the signed timestamp and server wall-clock, in
#: seconds, in either direction. Module-private with no environment override on purpose: an
#: attacker who can influence configuration must not be able to widen the replay window.
MAX_SKEW_SECONDS = 300

#: Input bounds applied before any parsing or hashing, so an unauthenticated caller cannot buy
#: server work with an oversized header.
MAX_TIMESTAMP_CHARS = 64
MAX_SIGNATURE_CHARS = 128
MAX_CONTEXT_CHARS = 128
MAX_PATH_CHARS = 8192


@dataclass(frozen=True, slots=True)
class VerifyResult:
    """Outcome of a verification attempt.

    On failure every field is empty: no reason code, no diagnostic string, nothing that
    distinguishes a wrong key from a stale timestamp from a forged signature.

    Attributes:
        ok: Whether every check passed.
        user_slug: The verified, normalised context slug. Empty means the caller sent no
            context header.
        replay_key: Hex SHA-256 of the *decoded* signature bytes, and the only correct replay
            ledger key. The base64 header text is not: base64 leaves the unused bits of the
            final quantum free, so sixteen distinct header texts decode to the same 64-byte
            signature and keying on the text would admit fifteen replays.
        expires_at: The instant after which this signature can never verify again
            (``signed timestamp + MAX_SKEW_SECONDS``). A ledger must retain the key until
            then. Retaining for a fixed TTL measured from first sight is not the same thing:
            a timestamp up to 300 s in the future stays verifiable for up to 600 s from now,
            so a 300 s TTL evicts the entry while the signature still works.
    """

    ok: bool
    user_slug: str = ""
    replay_key: str = ""
    expires_at: datetime | None = None


_DENIED = VerifyResult(False)


def public_key_fingerprint(public_key_b64: str) -> str:
    """Short, stable, non-secret identifier for a public key. Empty when it does not decode.

    Used to namespace the identities a key authorises, so revoking the key retires exactly the
    identities it minted and nothing else.
    """
    raw = _decode_public_bytes(public_key_b64)
    return hashlib.sha256(raw).hexdigest()[:16] if raw else ""


def canonical_string(
    *,
    method: str,
    path_and_query: str,
    timestamp: str,
    context_slug: str,
    body_sha256_hex: str,
) -> bytes:
    """The exact bytes that get signed. Field order is frozen; adding a field rotates keys.

    ``\\n`` is unambiguous because no encoded field can contain one: the method is a verb, the
    path is percent-encoded ASCII, the timestamp has fixed shape, the slug is allowlisted, and
    the digest is hex. Raises ``UnicodeEncodeError`` on a non-ASCII field, which the caller
    treats as a failed verification.
    """
    return (
        f"{method.upper()}\n"
        f"{path_and_query}\n"
        f"{timestamp}\n"
        f"{context_slug}\n"
        f"{body_sha256_hex}"
    ).encode("ascii")


def _decode_public_bytes(public_key_b64: str) -> bytes | None:
    try:
        raw = base64.b64decode(public_key_b64.strip(), validate=True)
    except Exception:
        return None
    return raw if len(raw) == 32 else None


def _load_public_key(public_key_b64: str) -> Ed25519PublicKey | None:
    raw = _decode_public_bytes(public_key_b64)
    if raw is None:
        return None
    try:
        return Ed25519PublicKey.from_public_bytes(raw)
    except Exception:
        return None


def _parse_timestamp(text: str) -> datetime | None:
    """Parse an RFC 3339 UTC timestamp inside the fixed skew window, or ``None``."""
    try:
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None
    if moment.tzinfo is None:
        return None
    if abs((datetime.now(timezone.utc) - moment).total_seconds()) > MAX_SKEW_SECONDS:
        return None
    return moment


def verify(
    *,
    public_key_b64: str,
    method: str,
    path_and_query: str,
    ts: str,
    sig_b64: str,
    body: bytes,
    user_slug: str = "",
) -> VerifyResult:
    """Verify one signed request. Every failure returns the same empty result.

    Args:
        public_key_b64: Server-configured Ed25519 public key, base64 of 32 raw bytes.
        method: HTTP method, uppercased internally.
        path_and_query: Path exactly as it travelled on the wire, still percent-encoded, with
            ``?query`` appended verbatim when present.
        ts: The ``X-Request-Timestamp`` header value, byte-identical to what was signed.
        sig_b64: The ``X-Request-Signature`` header value.
        body: Raw request body bytes.
        user_slug: The ``X-Request-Context`` header value, normalised here before use.
    """
    if not public_key_b64 or not ts or not sig_b64:
        return _DENIED
    if (
        len(ts) > MAX_TIMESTAMP_CHARS
        or len(sig_b64) > MAX_SIGNATURE_CHARS
        or len(user_slug) > MAX_CONTEXT_CHARS
        or len(path_and_query) > MAX_PATH_CHARS
    ):
        return _DENIED

    key = _load_public_key(public_key_b64)
    if key is None:
        return _DENIED

    moment = _parse_timestamp(ts)
    if moment is None:
        return _DENIED

    try:
        signature = base64.b64decode(sig_b64.strip(), validate=True)
    except Exception:
        return _DENIED
    if len(signature) != 64:
        return _DENIED

    slug = (user_slug or "").strip().lower()
    if not _SLUG.match(slug):
        return _DENIED

    try:
        message = canonical_string(
            method=method,
            path_and_query=path_and_query,
            timestamp=ts,
            context_slug=slug,
            body_sha256_hex=hashlib.sha256(body).hexdigest(),
        )
    except Exception:
        return _DENIED

    try:
        key.verify(signature, message)
    except InvalidSignature:
        return _DENIED
    except Exception:
        return _DENIED

    return VerifyResult(
        ok=True,
        user_slug=slug,
        replay_key=hashlib.sha256(signature).hexdigest(),
        expires_at=moment.astimezone(timezone.utc) + timedelta(seconds=MAX_SKEW_SECONDS),
    )
