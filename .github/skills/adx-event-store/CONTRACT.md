# ADX Contract

`AdxConnector` owns one configured lifetime for query, ingestion and provisioning clients.
`AdxConfig` carries target, retry, timeout and optional control-plane settings. Construction imports
SDKs but does not provision. `close()` and context-manager exit close query/ingestion transports.

Public exports remain: `AdxClient`, `AdxConfig`, `AdxConnector`, `AdxProvisioner`, `ColumnSpec`,
`TableSchema`, `QueryResult`, `IngestMode`, `IngestResult`, and the `AdxError` hierarchy:
`AdxAuthError`, `AdxConfigError`, `AdxIdentifierError`, `AdxIngestionError`,
`AdxProvisioningError`, `AdxQueryError`, `AdxTimeoutError`.

Use `query()` for declared-parameter queries, `command()` for trusted operator-authored management
KQL, `create_table()` for schema/mapping, `repository()` for table-bound CRUD, `load_csv()` and
`ingestor` for writes, `ensure_infrastructure()` for explicitly authorized provisioning.
Identifiers pass an allowlist. Values use query parameters. Raw predicates and raw KQL are code,
not untrusted end-user input. Confirmation of destructive repository operations names the target.

The bootstrap validates table/database identifiers and matching database confirmation before client
construction; recreation also requires matching table confirmation. It accepts headered CSV,
counts logical CSV records, rejects a mismatched expected count, and tags ingestion with SHA-256
over content plus interpretation settings. It queries only that batch's extents for exact count
read-back. Whole-table size is never replay evidence. A timeout or over-count is failure.

Kusto is append-oriented. Replacement/soft deletion is not a transaction or immediate hard delete.
Extent tag retention bounds service-side ingestion idempotency; this is not a permanent exactly-once
ledger. Managed streaming may fall back to queued ingestion. Read back the batch rather than
treating SDK acceptance or `IngestResult.is_terminal` as sufficient arrival proof.

For headerless or non-CSV data, supply an explicit schema and format through the connector API;
the bootstrap refuses its inherited, nonfunctional headerless option. No live-cloud behavior is
certified by the offline tests. Application authorization and deployment authority remain external.