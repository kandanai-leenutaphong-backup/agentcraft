"""AuthError — one failure type, with a reason code and a safe public message.

Module role:
    Separates what operators see from what callers see. Every rejection carries
    a machine-readable ``reason`` for logs and metrics, and a fixed public
    message chosen from a table.

Why the public message is chosen from a table:
    Because the alternative is formatting the caller's own input into the
    response. Token fields are attacker-controlled: a key id can carry newlines
    that forge log lines, ANSI escapes that rewrite a terminal, HTML that lands
    in a diagnostic page, or kilobytes of padding. Reflecting them was a real
    finding, and the fix is that a public message can never be built from input
    (G2).

Why the reasons are coarse:
    An expired token, an unknown signing key and an algorithm-confusion attempt
    all surface as ``invalid_token`` to the caller. Distinguishing them tells an
    attacker which part of the forgery to change next; the distinction is kept
    in the log, where it belongs.
"""

from __future__ import annotations

from typing import Any

# Reason code -> public message. The public side is deliberately uninformative
# and deliberately constant: it never contains a value taken from the request.
_PUBLIC_MESSAGES: dict[str, str] = {
    "missing_header": "Missing or malformed Authorization header",
    "empty_token": "Missing or malformed Authorization header",
    "malformed": "Invalid token",
    "unknown_kid": "Invalid token",
    "bad_signature": "Invalid token",
    "bad_algorithm": "Invalid token",
    "expired": "Token expired",
    "not_yet_valid": "Invalid token",
    "bad_audience": "Invalid audience",
    "bad_issuer": "Invalid issuer",
    "key_issuer_mismatch": "Invalid issuer",
    "missing_claim": "Token missing a required claim",
    "jwks_unavailable": "Authentication temporarily unavailable",
    "unknown": "Authentication failed",
}

# Reasons that mean "the service could not check", not "the caller is wrong".
# These are a 503: a key-service outage is not the caller's fault, and returning
# 401 makes a dependency failure look like a credential problem to everyone
# looking at the dashboard.
_UNAVAILABLE_REASONS = frozenset({"jwks_unavailable"})


class AuthError(Exception):
    """A rejected request, with an operator view and a caller view.

    Attributes:
        reason: Stable machine-readable code. Safe to log, chart and alert on.
        detail: Operator-facing text. May name specifics. **Never returned.**
        context: Structured fields for the log record. Values are the box's own
            measurements — lengths, flags — never raw caller input.
    """

    def __init__(
        self,
        reason: str,
        detail: str = "",
        **context: Any,
    ) -> None:
        super().__init__(detail or reason)
        self.reason = reason
        self.detail = detail or reason
        self.context = context

    @property
    def public_message(self) -> str:
        """What the caller is told. Constant per reason, never derived."""
        return _PUBLIC_MESSAGES.get(self.reason, _PUBLIC_MESSAGES["unknown"])

    @property
    def status_code(self) -> int:
        """HTTP status: 401 for a bad credential, 503 for an unavailable check."""
        return 503 if self.reason in _UNAVAILABLE_REASONS else 401

    def log_fields(self) -> dict[str, Any]:
        """Structured fields for one rejection log line."""
        return {"reason": self.reason, **self.context}

    def __repr__(self) -> str:
        return f"AuthError(reason={self.reason!r}, detail={self.detail!r})"


class ForbiddenError(Exception):
    """An authenticated caller acting outside their permissions.

    Distinct from :class:`AuthError` because the caller *is* authenticated:
    retrying with a fresh token cannot help, so a client that refreshes on 401
    must not be given one here.
    """

    def __init__(self, reason: str, detail: str = "", **context: Any) -> None:
        super().__init__(detail or reason)
        self.reason = reason
        self.detail = detail or reason
        self.context = context
        self.status_code = 403

    @property
    def public_message(self) -> str:
        return "Forbidden"

    def log_fields(self) -> dict[str, Any]:
        return {"reason": self.reason, **self.context}


class NotFoundError(Exception):
    """A resource the caller may not have, reported as absent.

    Deliberately indistinguishable from a resource that does not exist. Telling
    an unauthorised caller "that exists but is not yours" turns an id space into
    an enumerable directory (G4).
    """

    def __init__(self, reason: str = "not_found", **context: Any) -> None:
        super().__init__(reason)
        self.reason = reason
        self.context = context
        self.status_code = 404

    @property
    def public_message(self) -> str:
        return "Not found"

    def log_fields(self) -> dict[str, Any]:
        return {"reason": self.reason, **self.context}


__all__ = ["AuthError", "ForbiddenError", "NotFoundError"]
