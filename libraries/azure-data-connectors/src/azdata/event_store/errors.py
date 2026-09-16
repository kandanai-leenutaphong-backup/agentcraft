"""Typed exception hierarchy.

Callers distinguish a bad request they must fix from a transient fault worth
retrying without parsing message text.
"""

from __future__ import annotations


class AdxError(Exception):
    """Base for every error raised by this connector."""


class AdxConfigError(AdxError):
    """Configuration is absent, malformed, or internally inconsistent."""


class AdxPermissionError(AdxError):
    """The host did not explicitly grant this operator operation; no I/O occurred."""


class AdxAuthError(AdxError):
    """No usable credential, or the credential was rejected."""


class AdxIdentifierError(AdxError):
    """A database, table, column, or mapping name failed validation.

    Raised before any network call. KQL cannot parameterise identifiers, so an
    unvalidated identifier is an injection vector.
    """


class AdxQueryError(AdxError):
    """The service rejected a query or control command."""

    def __init__(self, message: str, *, client_request_id: str | None = None, retryable: bool = False) -> None:
        super().__init__(message)
        self.client_request_id = client_request_id
        self.retryable = retryable


class AdxTimeoutError(AdxError):
    """A request exceeded its deadline, including time spent retrying."""


class AdxIngestionError(AdxError):
    """Ingestion was rejected, or landed with failures reported by the service."""

    def __init__(self, message: str, *, failures: list[str] | None = None) -> None:
        super().__init__(message)
        self.failures = failures or []


class AdxProvisioningError(AdxError):
    """A control-plane operation failed: cluster, database, or role assignment."""
