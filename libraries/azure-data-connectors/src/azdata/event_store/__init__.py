"""Opt-in synchronous ADX operator APIs; mutations require explicit host grants.

This contract is separate from the bounded async v4 connector. Imports are lazy;
configuration and policy values need no provider SDK, credential or network call.
"""

from __future__ import annotations

from importlib import import_module

_EXPORTS = {
  "AdxClient": "client", "AdxConfig": "config", "AdxConnector": "connector",
  "AdxProvisioner": "provision", "ClusterInfo": "provision",
  "CrudRepository": "crud", "UpsertStrategy": "crud", "Ingestor": "ingest",
  "IngestMode": "ingest", "IngestResult": "ingest",
  "ColumnSpec": "models", "QueryResult": "models", "TableSchema": "models",
  "EventStorePolicy": "policy", "infer_schema": "schema",
  "validate_identifier": "identifiers", "validate_type": "identifiers",
  **{name: "errors" for name in (
    "AdxError", "AdxAuthError", "AdxConfigError", "AdxIdentifierError",
    "AdxIngestionError", "AdxPermissionError", "AdxProvisioningError",
    "AdxQueryError", "AdxTimeoutError",
  )},
}
__all__ = list(_EXPORTS)


def __getattr__(name: str):
  module = _EXPORTS.get(name)
  if module is None:
    raise AttributeError(name)
  value = getattr(import_module(f"{__name__}.{module}"), name)
  globals()[name] = value
  return value
