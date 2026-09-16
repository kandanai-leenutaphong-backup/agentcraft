# ADX Contract

Public namespace: `azdata.event_store` in `azdata` `4.0.0a4`. This is the synchronous operator
contract, not a provider escape hatch on the bounded async `DataConnector`.

`AdxConnector` owns one configured lifetime for query, ingestion and provisioning clients.
`AdxConfig` carries target, retry, timeout and optional control-plane settings. Construction imports
SDKs but performs no credential acquisition, request or provisioning. Base namespace, configuration,
models, schema inference and policy imports are lazy and need no provider SDK. `close()` and
context-manager exit close query/ingestion/management clients; borrowed credentials remain external.

Public exports remain: `AdxClient`, `AdxConfig`, `AdxConnector`, `AdxProvisioner`, `ColumnSpec`,
`TableSchema`, `QueryResult`, `IngestMode`, `IngestResult`, and the `AdxError` hierarchy:
`AdxAuthError`, `AdxConfigError`, `AdxIdentifierError`, `AdxIngestionError`,
`AdxProvisioningError`, `AdxQueryError`, `AdxTimeoutError`.

Additional exports: `EventStorePolicy`, `AdxPermissionError`, `CrudRepository`, `UpsertStrategy`,
`Ingestor`, `ClusterInfo`, `infer_schema`, `validate_identifier`, `validate_type`.
`AdxClient`, `AdxConnector`, `AdxProvisioner` and `Ingestor` accept keyword-only `policy=`.
No policy means no mutation grants. The [caller guide](README.md#explicit-operator-grants)
names every grant. Invalid policy raises `AdxConfigError`; a missing grant raises
`AdxPermissionError` before I/O. Policy is immutable host configuration, never request-supplied
authority, an Azure grant, a credential or an OS sandbox.

Use `query()` for declared-parameter queries, `command()` for trusted operator-authored management
KQL, `create_table()` for schema/mapping, `repository()` for table-bound CRUD, `load_csv()` and
`ingestor` for writes, `ensure_infrastructure()` for explicitly authorized provisioning.
Identifiers pass an allowlist. Values use query parameters. Raw predicates and raw KQL are code,
not untrusted end-user input. Confirmation of destructive repository operations names the target.

Purge and extent-tag deletion require the exact table name, not a truthy boolean. Raw management
KQL beyond `.show` requires both `command` and `delete` because arbitrary KQL cannot be granted
as a narrow schema or ingestion operation. SDK objects are trusted operator internals; direct
SDK calls do not inherit local policy. The bounded v4 API exposes no such SDK escape hatch.

Query and `.show` requests set `request_readonly=true` and disable remote entities. Read retries
use configured attempts, exponential jitter and a deadline; in-flight sync calls still depend
on SDK/server timeout behavior. Mutating control commands are not retried by this wrapper.
Queued/managed ingestion has native SDK retry semantics and extent-tag-scoped deduplication;
it is not a permanent exactly-once guarantee or transactional replacement.

`QueryResult` preserves the first primary table's column and row tuples and offers `scalar`,
`first`, `to_dicts`, `column_values`, length and empty checks. This operator contract is not
v4 `OperationResult`: byte budgets, async cancellation, multi-table normalization and standard
partial results are not claimed. Re-query paging requires a stable dataset plus caller-chosen
time/key total order; concurrent append/update can change later pages. It is not a snapshot cursor.

The bootstrap validates table/database identifiers and matching database confirmation before client
construction; recreation also requires matching table confirmation. It accepts headered CSV,
counts logical CSV records, rejects a mismatched expected count, and tags ingestion with SHA-256
over content plus interpretation settings. It queries only that batch's extents for exact count
read-back. Whole-table size is never replay evidence. A timeout or over-count is failure.

Kusto is append-oriented. Replacement/soft deletion is not a transaction or immediate hard delete.
Extent tag retention bounds service-side ingestion idempotency; this is not a permanent exactly-once
ledger. Managed streaming may fall back to queued ingestion. Read back the batch rather than
treating SDK acceptance or `IngestResult.is_terminal` as sufficient arrival proof.

Managed row writes now report `status="accepted"`, so `is_terminal` is false before explicit
verification. Cluster/database existence only treats `ResourceNotFoundError` as absence;
403, timeout and other unknown reads refuse provisioning. Infrastructure creation still requires
independent ownership, approved SKU, network and permission checks in the host deployment owner.

For headerless or non-CSV data, supply an explicit schema and format through the connector API;
the bootstrap refuses its inherited, nonfunctional headerless option. No live-cloud behavior is
certified by the offline tests. Application authorization and deployment authority remain external.