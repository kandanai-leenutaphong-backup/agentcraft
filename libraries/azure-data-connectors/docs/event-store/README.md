# ADX Event Store

Canonical operator API: `azdata.event_store`, shipped in `azdata` `4.0.0a4`, Python 3.11+.
This absorbs the retired `adx-event-store` skill; it is not another distribution or MCP server.
The bounded async `azdata.connect("adx", ...)` contract remains the application default.

## Install And Read

Select the `event-store` extra for synchronous SDK queries, ingestion and management APIs.
Its direct dependencies are `azure-kusto-data>=5.0.2,<6`, `azure-kusto-ingest>=5.0.2,<6`,
`azure-mgmt-kusto>=4.0,<5`, and `azure-identity>=1.19,<2`. The base retains `azure-core`.
`kusto` remains the separate async v4 extra. Installing either grants no access or writes.

Artifacts are local candidates, not published packages. In an operator-owned environment:

```bash
uv pip install --python "$ENV/bin/python" "${WHEEL}[event-store]"
```

The host supplies `ENV`, reviewed `WHEEL`, approved endpoint/database and an authenticated
credential. No key, connection string, role grant or network change is needed by installation.
Borrowed credentials remain caller-owned. `from_env()` is an optional composition-edge
convenience; runtime modules do not resolve application configuration from environment variables.

```python
from azdata.event_store import AdxConfig, AdxConnector

config = AdxConfig(cluster_uri=operator_endpoint, database=operator_database)
with AdxConnector(config, credential=workload_credential) as store:
    result = store.query("Events | where record_id == record_key", {"record_key": requested_key})
    rows = result.to_dicts()
```

Queries bind declared parameters automatically, including datetime, timespan and dynamic values.
Read requests set server-side `request_readonly` and disable remote entities. Query text is
trusted host code, not an end-user query sandbox. This operator API does not inherit v4's
transport byte caps, async cancellation, standard result envelope or scoped continuations.

## Explicit Operator Grants

All mutations refuse by default before SDK I/O with `AdxPermissionError`. A host-established
principal and explicit grants are required; local policy is not Azure RBAC or human approval.

```python
from azdata.event_store import EventStorePolicy

policy = EventStorePolicy(principal=approved_operator, grants={"ingest", "schema"})
with AdxConnector(config, credential=workload_credential, policy=policy) as store:
    schema, accepted = store.load_csv(source_csv, "Events", mapping_name="EventsCsv")
```

That example is an authorized-host integration shape, not permission to run ingestion here.
`accepted` is not persistence proof. Use the [bootstrap workflow](WORKFLOW.md) for exact
content-hash-tagged batch counting; `wait_for_rows()` counts the whole table and is not replay proof.

| Grant | Named Surface |
| --- | --- |
| `ingest` | `ingest_rows`, `ingest_file`, repository insert and version append |
| `schema` | `create_table`, CSV mapping, batching and streaming policy |
| `delete` | generated soft delete, named purge/truncate/drop/extent deletion |
| `provision` | explicitly authorized cluster/database creation |
| `provision` + `delete` | named cluster teardown |
| `command` + `delete` | arbitrary operator-authored management KQL; deliberately broad, no narrow-command parser claim |

Soft replacement requires both `ingest` and `delete` before the first query or write.
It remains non-atomic. Schema, data and infrastructure grants do not imply one another.
Managed streaming may queue: its result is `accepted`, never immediate arrival evidence.
Mutating control commands have no wrapper retry; a timeout can mean an unknown applied result.

## Migration Map

| Old Import / Entry | Canonical Replacement |
| --- | --- |
| `from adx_connector import AdxConfig, AdxConnector` | `from azdata.event_store import AdxConfig, AdxConnector` |
| `adx_connector.client`, `.crud`, `.schema`, `.models`, `.errors`, `.identifiers`, `.ingest`, `.provision`, `.retry` | Same suffix under `azdata.event_store` |
| `app.components.data_connector_library.kusto.<module>` | `azdata.event_store.<module>` for the preserved operator modules |
| app barrel `AdxClient`, `AdxConfig`, `AdxConnector`, `CrudRepository`, `UpsertStrategy`, `Ingestor`, `ClusterInfo` and model/error exports | Same names exported by `azdata.event_store` |
| Retired skill bootstrap script | `azdata.event_store.bootstrap.main(argv)`; host deployment entry point invokes it |

No `adx_connector` compatibility namespace is installed. Current imports and dependency
ownership follow [workspace setup](../../../README.md). App-specific `content`,
`metadata`, `read`, `KustoReader`, `KustoTableInspector` and `shape_kusto_response` are not this
operator API and must not be deleted as part of that mechanical import replacement.

Breaking safety corrections: supply `policy=` for writes; `purge_where(confirm=True)` becomes
`purge_where(confirm="TableName")`; `drop_by_tag(tag)` also requires `confirm="TableName"`.
Identifier validation now rejects trailing newlines and reserved words in both Kusto APIs.
Uncertain existence reads no longer trigger provisioning. Retry and paging limits are in
[the contract](CONTRACT.md); historical service findings remain in [GOTCHAS.md](GOTCHAS.md).

## Verify

From the library root in an explicit environment with the extras installed:

```bash
"$ENV/bin/python" -B -m unittest discover -s tests -t . -q
"$ENV/bin/python" -B tests/event_store/selftest.py
```

Source and artifact evidence: [VERIFICATION.md](../../VERIFICATION.md).
[Provenance](PROVENANCE.md) and [preservation manifest](preservation.json) retain source
identity and all original paths. No live ingestion/provisioning/teardown or Python/platform
matrix is implied by offline passes. The host [deployment runbook](../../../../deploy/README.md)
owns separately authorized Perth keep-running operations and payload-free receipts.