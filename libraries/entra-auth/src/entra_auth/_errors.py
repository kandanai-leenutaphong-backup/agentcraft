"""Rejection reasons that never carry a byte of the token into a response or a log.

Module role:
    One exception type for every way a token is refused. The caller-visible message is
    **selected** from a fixed table by reason code, never built from input, so nothing an
    attacker controls can reach a response body, a log line, a dashboard or a terminal.

Why this is a separate module:
    The temptation to interpolate is strongest at the point of failure — ``f"unknown key
    {kid!r}"`` reads like helpful diagnostics. Keeping the message table away from the
    validator makes the constant-message rule structural rather than a habit. Operators get
    measurements of hostile values (a length), never the values.
"""

from __future__ import annotations

from typing import Any

#: Every reason a token can be refused, mapped to the one message a caller may see.
#: The application does not use these bodies — refusals leave as a bare 401 — but a
#: mis-wired consumer that does echo one still leaks nothing.
_PUBLIC_MESSAGES: dict[str, str] = {
    "missing_header": "authentication required",
    "empty_token": "authentication required",
    "malformed": "the token could not be read",
    "oversized": "the token could not be read",
    "bad_algorithm": "the token could not be read",
    "unknown_kid": "the token could not be verified",
    "jwks_unavailable": "the token could not be verified",
    "jwks_stale": "the token could not be verified",
    "bad_signature": "the token could not be verified",
    "bad_audience": "the token is not accepted here",
    "bad_issuer": "the token is not accepted here",
    "bad_tenant": "the token is not accepted here",
    "key_issuer_mismatch": "the token is not accepted here",
    "expired": "the token is not valid",
    "not_yet_valid": "the token is not valid",
    "missing_claim": "the token is not valid",
    "missing_scope": "the token does not carry the required permission",
    "service_principal_refused": "the token does not carry the required permission",
}

_FALLBACK = "the token was refused"


class AuthError(Exception):
    """A token was refused. The reason is a code; the message is a constant.

    Args:
        reason: A key of :data:`_PUBLIC_MESSAGES`. An unknown key degrades to a generic
            message rather than raising, because a bug in error handling must not become a
            second failure on the rejection path.
        detail: Operator-facing text. Kept off the wire. Callers must still ensure it holds
            no token-derived value; the safe fields below exist so it does not have to.
        **fields: Structured operator fields — lengths, counts, claim *names*. Never a claim
            *value*, never a key id, never a token fragment.
    """

    def __init__(self, reason: str, detail: str = "", **fields: Any) -> None:
        super().__init__(detail or reason)
        self.reason = reason
        self.detail = detail
        self.fields = fields

    @property
    def public_message(self) -> str:
        """The only text that may cross the wire."""
        return _PUBLIC_MESSAGES.get(self.reason, _FALLBACK)

    def log_fields(self) -> dict[str, Any]:
        """Structured fields for a log line. Measurements only, never values."""
        return {"auth_reason": self.reason, **self.fields}


__all__ = ["AuthError"]
