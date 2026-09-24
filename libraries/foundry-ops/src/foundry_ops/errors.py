"""Refusal and verification errors; `code` is a stable machine reason, never provider payload."""

from __future__ import annotations


class FoundryOpsError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class RefusedError(FoundryOpsError, ValueError):
    """Local refusal before any side effect: foreign path, overwrite, pin drift, invalid input."""


class UnresolvedIntentError(RefusedError):
    """An intent exists without its terminal record; reconcile by read-back, never replay the write."""


class BoundExceededError(FoundryOpsError, ValueError):
    """A byte, event, item, page or deadline bound was reached."""


class VerificationError(FoundryOpsError, ValueError):
    """Read-back contradicted the expected identity, state or shape."""


class ReadbackError(FoundryOpsError, RuntimeError):
    """Read-back could not establish state; the remote outcome is unknown."""
