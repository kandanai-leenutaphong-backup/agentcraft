# Kusto behaviours that cost real debugging time

Historical source observations, not live verification of this portable package.
Measurements came from a Dev/No-SLA E2a_v4 cluster in australiaeast loading a
27,181,871-byte, 15,520-row, 181-column corpus.

## Accepted is not arrived

Queued ingestion returns success when the service takes the payload, not when rows are
queryable. The corpus was accepted in **4.89s** and fully queryable **73s** later.

Never assert on the return value of an ingest call. Poll a count with a deadline.

## Small writes vanish without `flush_immediately`

A 3-row, 222-byte queued write was accepted in 3.47s and had not appeared after **300s**.
`.show ingestion failures` was empty, because nothing failed — the table's default
ingestion batching policy waits up to five minutes, 1,000 items, or 1 GB, and a handful of
rows trips none of them early.

Set `flush_immediately` on interactive row writes. The same write then landed in **2.5s**.
Leave batching enabled for bulk file loads, where throughput matters more than latency.

## Streaming policy resets when a table is recreated

Enabling a table's streaming ingestion policy is not instantaneous. A test that drops and
recreates its table each run resets the policy before it propagates, so the managed client
silently falls back to queued and inherits the batching delay.

Symptom: identical code timed at **3.36s**, then **60.20s**, then failed at **428.43s**
reading zero rows. Fix: retain the table and clear its data instead of dropping it.

## `dcount` is approximate

`dcount(resource_id, 4)` reported **15,515** distinct values over a column that is exactly
unique across **15,520** rows. The accuracy parameter tunes the estimator; it does not make
it exact.

For a uniqueness claim use `summarize by key | count`, or prove the negative with
`summarize n = count() by key | where n > 1 | count`.

## Control commands can take query parameters

`.delete table T records <| ...` embeds a query. Declaring parameters in the command text
without binding them in the request properties fails with:

> Query parameter 'k0' is not specified in the query's client request properties

Bind them. This keeps deletion predicates parameterised rather than string-formatted.

## `in` rejects a dynamic array

Binding a key set as one `dynamic` parameter fails with `SEM0001: invalid query parameter
type (expected 'dynamic')` on the `in` operator. Bind each key as its own named scalar and
generate the names in code, never from caller input. Chunk large sets.

## SDK specifics

Versions: `azure-kusto-data` 6.0.2, `azure-kusto-ingest` 6.0.4, `azure-mgmt-kusto` 4.0.0.

| Trap | Detail |
| --- | --- |
| `Cluster.state` | An enum. `str()` yields `State.RUNNING`, not `Running`, so a readiness loop comparing the stringified enum never exits. Read `.value`. |
| `ReadWriteDatabase` | Needs `kind="ReadWrite"` explicitly from API version 2021-01-01; the SDK does not default it. |
| `ManagedStreamingIngestClient` | No `from_dm_kcsb` factory. Construct with `engine_kcsb` and `dm_kcsb` — engine is the query endpoint, dm is the ingestion endpoint. |
| SDK logging | `azure.*` logs every HTTP exchange at INFO. Raise those loggers to WARNING or your own output is unreadable. |
| `az kusto` CLI | An experimental extension. `az kusto cluster create` without `--no-wait` can appear to hang before the resource exists. |

## Limits

- One ingestion payload: **1 GB** uncompressed. Split, or ingest from blob storage.
- One record or string value: **64 MB**. Ingestion fails above it.
- Queued ingestion buffers reliably for **7 days**; beyond that, unprocessed data is dropped.

## Permissions

| Operation | Minimum role |
| --- | --- |
| Create a table | Database User |
| Ingest into an existing table | Table Ingestor |
| Change an existing table's schema | Table Admin or Database Admin |
| Inline ingest or ingest from query | Table Ingestor **and** Database Viewer |
