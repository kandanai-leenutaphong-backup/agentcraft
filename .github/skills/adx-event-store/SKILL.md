---
name: adx-event-store
description: "Use when event or log data must be provisioned into, loaded into, or queried from Azure Data Explorer: cluster and database creation, CSV schema inference, ingestion mode choice, injection-safe CRUD, and a runnable verification battery. Covers the Kusto behaviours that silently lose data if unhandled."
---

# Azure Data Explorer event store

For **event and log data**: append-heavy, timestamped, wide, sparse. Not for metric series — Kusto is a search-and-time-range engine, and a corpus where few rows carry a numeric measure belongs here rather than in a measurement database.

Not for mutable application state. Kusto has no row update and no immediate hard delete; pair it with a transactional store for anything a user edits.

## Mechanism

[mechanism/adx_connector/](mechanism/adx_connector/) is the connector library.
[mechanism/bootstrap_adx.py](mechanism/bootstrap_adx.py) provisions, loads, and verifies a headered CSV.
Resolve `SKILL_ROOT` from this loaded skill's absolute path, not the consuming project's directory.
Install the declared dependencies into an external environment as described in [README.md](README.md).
No source checkout, sibling skill or particular agent client is required.

```bash
python3 "$SKILL_ROOT/mechanism/bootstrap_adx.py" \
  --csv path/to/events.csv --table MyEvents --cluster mycluster01 \
  --resource-group my-rg --subscription "$SUBSCRIPTION_ID" --database MyDb \
  --location "$AZURE_REGION" --confirm-database MyDb
```

Requires `azure-kusto-data`, `azure-kusto-ingest`, `azure-mgmt-kusto`, `azure-identity`, and an authenticated `az login`. No keys or connection strings: authentication is Entra ID via `DefaultAzureCredential`.
An injected workload credential is also supported by the Python API. Installation grants no roles
and authorizes no cloud changes. Call provisioning from an authorized project's deployment entry
point; never run it merely to verify that the skill installed. Existing-cluster ingestion uses
`--skip-provision --cluster-uri URL`, but still requires matching `--confirm-database`.
Recreation additionally requires `--recreate --confirm-table TABLE`.

## Sequence

| Phase | Action | Gate before proceeding |
| --- | --- | --- |
| provision | `ensure_infrastructure()` | cluster state is `Running`, not merely created |
| schema | `infer_schema_from_csv()` | column count matches the source header |
| create | `create_table()` + CSV mapping | `.show tables` lists the table |
| tune | batching latency, streaming policy | applied before first write, not after |
| load | `ingest_file()` queued | the exact content-hash-tagged batch has the expected record count |
| verify | query battery | every case passes, exit code 0 |

Never report success on ingestion acceptance. Acceptance means the service took the payload, not that rows are queryable.

## Non-negotiables

- **Bind values, validate identifiers.** Values cross as declared query parameters. Identifiers cannot be parameterised, so validate against a strict allowlist and reject anything needing bracket quoting rather than escaping it.
- **Flush interactive writes.** Small row writes without `flush_immediately` wait out the table's batching policy — five minutes by default — and read as data loss with zero logged failures.
- **Confirm destructives by name.** `truncate`, `drop`, `purge`, and cluster teardown take the entity name as an explicit argument. Refuse an empty delete predicate.
- **Order by time *and* key.** Event corpora share timestamps. Time alone is a partial order and paging on it is not reproducible.
- **Count exactly when counting keys.** `dcount` is approximate by design and will under-report a unique key.

## Diagnosing missing rows

In order, stopping at the first that explains it:

1. `.show ingestion failures` — an actual rejection.
2. Inline `.ingest inline into table T <|` — synchronous, bypasses the ingestion service. Lands means the problem is batching, not schema or permissions.
3. Table batching policy and `flush_immediately`.
4. Streaming policy propagation. Dropping and recreating a table resets it, so the managed client falls back to queued.

## Verification

[tests/selftest.py](tests/selftest.py) gates identifiers, parameter typing, schema inference and the
bundled connector. [tests/test_bootstrap.py](tests/test_bootstrap.py) verifies write refusals,
content identity and batch read-back with injected clients. Neither makes Azure calls.

```bash
python3 "$SKILL_ROOT/tests/selftest.py"
python3 "$SKILL_ROOT/tests/test_bootstrap.py"
```

Live validation must be separately authorized against named targets. It is not part of these
offline tests. See [GOTCHAS.md](GOTCHAS.md) and [references/gotchas.md](references/gotchas.md).
Use existing `azure-data-connectors` query/MCP access when that already meets the need; this skill
adds the operator ingestion/provisioning workflow, not another MCP server or an implicit write grant.
