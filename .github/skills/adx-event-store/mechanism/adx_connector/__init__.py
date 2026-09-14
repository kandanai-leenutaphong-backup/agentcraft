"""Production-grade Azure Data Explorer connector.

A reusable CRUD and provisioning layer over the official Kusto SDKs
(`azure-kusto-data`, `azure-kusto-ingest`, `azure-mgmt-kusto`).

Design commitments:

* **Injection-safe.** Every user value crosses the wire as a declared KQL query
  parameter, never as interpolated text. Identifiers, which KQL cannot
  parameterise, are validated against a strict allowlist before use.
* **Client reuse.** `KustoClient` holds pooled HTTP connections and a token
  cache; the connector creates one per endpoint and reuses it.
* **Retry with backoff.** Throttling and transient service faults retry with
  exponential backoff and full jitter. Client faults never retry.
* **Traceable.** Every request carries a client request id, so a failure in the
  terminal can be found in `.show queries` and cluster diagnostics.
* **Honest CRUD.** Kusto is an append-optimised store with no row update. This
  connector implements update and delete in the two ways the engine actually
  supports and names them plainly rather than pretending otherwise.

Entry point: :class:`AdxConnector`.
"""

from __future__ import annotations

from .client import AdxClient
from .config import AdxConfig
from .connector import AdxConnector
from .errors import (
    AdxAuthError,
    AdxConfigError,
    AdxError,
    AdxIdentifierError,
    AdxIngestionError,
    AdxProvisioningError,
    AdxQueryError,
    AdxTimeoutError,
)
from .ingest import IngestMode, IngestResult
from .models import ColumnSpec, QueryResult, TableSchema
from .provision import AdxProvisioner

__all__ = [
    "AdxClient",
    "AdxConfig",
    "AdxConnector",
    "AdxAuthError",
    "AdxConfigError",
    "AdxError",
    "AdxIdentifierError",
    "AdxIngestionError",
    "AdxProvisioningError",
    "AdxQueryError",
    "AdxTimeoutError",
    "AdxProvisioner",
    "ColumnSpec",
    "IngestMode",
    "IngestResult",
    "QueryResult",
    "TableSchema",
]

__version__ = "1.0.0"
