# `data_connector_library` — the datastore capability

One entry point for Azure Data Explorer, Cosmos DB for Gremlin, and Azure AI Search. Two
planes that do not blur into each other:

| Plane | Contract | Use it for |
| --- | --- | --- |
| **Read** | One bounded read of one named thing. Failure is a **value**: six statuses, never an exception. | Previews, inventories, anything an analyst browses |
| **CRUD** | The full connector surface — query, command, ingest, provision, upsert, index and document CRUD. Raises typed errors. | Pipelines and operational tools that write |

`KustoReader` and `AdxConnector` both reach ADX and neither replaces the other. A reader
never widens into a writer; a writer never inherits "failure is a value".

The read plane was adopted from `azdata` 3.4.0 as a subset. The CRUD plane was written in
this repository. [`PROVENANCE.md`](PROVENANCE.md) records which is which, file by file.
**Azure AI Search is re-exported from `app.components.azure_search`, not reimplemented** —
the exported objects are that component's own classes, so there is one write path.

## Import cost

Importing this package touches the standard library and nothing else. Everything below
resolves from `app.components.data_connector_library`; what it costs depends on the name.

| Import | Costs |
| --- | --- |
| `ContentBounds`, `GraphReader`, `SearchReader`, `KustoReader` | nothing; the reader's SDK loads on first call through `load()` |
| `SearchIndexClient` and the Search values | nothing; Search CRUD is REST over the standard library |
| `AdxConnector`, `AdxClient`, `Ingestor` and the rest of the ADX surface | `azure-kusto-data` and `azure-kusto-ingest`, at the moment of import |
| `AdxProvisioner` | as above, plus `azure-mgmt-kusto` when it builds its client |
| `GremlinGraph` | nothing; `gremlinpython` loads when a graph is constructed |

The CRUD names resolve through a module `__getattr__`, which is what keeps the first two
rows true. Adding an eager `from .kusto.client import ...` to `__init__.py` would make
`import ContentBounds` fail on a machine with no Kusto SDK.

## Read plane

Reaching into a submodule from outside `app/components/` crosses the boundary and fails
`arch.py`.

| Reader | Call | Reads | Needs |
| --- | --- | --- | --- |
| `KustoReader` | `rows(query_uri=, database=, table=, bounds=)` | `["T"] \| take n` | `azure-kusto-data`, `Viewer` on that one database |
| `KustoTableInspector` | `facts(query_uri=, database=, table=, bounds=)` | `\| count`, `\| getschema` | as above |
| `SearchReader` | `documents(endpoint=, index=, text=, bounds=)` | `search("*", top=n+1)` | `azure-search-documents`, `Search Index Data Reader` |
| `GraphReader` | `elements(target=, element=, bounds=)` | whatever the injected source samples | nothing — the transport is injected |

Both Kusto readers issue data-plane queries against the database they are handed and nothing
else: no management command, no `database("Other")` hop. The minimum grant is therefore a
`Viewer` database principal assignment on **each database a caller names**, not a
cluster-wide `AllDatabasesViewer`. This deployment holds exactly that — one `Viewer`
assignment on `PerthCyber` and one on `AitLogs` — and reads both.

Values: `ContentBounds`, `ContentPayload`, `ContentResult`, `RowSample`, `GraphTarget`,
`TableFacts`. Helpers: `bounded_content`, `content_failure`, `normalize_sample`,
`normalize_rows`, `classify_discovery_failure`, `collected_now`, `sanitize_detail`,
`shape_kusto_response`. SDK seam: `load`, `override`, `override_missing`,
`clear_overrides`, `MissingDependency`.

```python
reader = KustoReader(credential_provider=azure_credential)
result = await reader.rows(query_uri=..., database=..., table=...,
                           bounds=ContentBounds(max_rows=25))
result.status          # ok | empty | forbidden | unreachable | unconfigured | unavailable
result.payload.rows    # tuple of dicts, bounded
result.payload.notes   # what a bound cut, in a reader's words
result.truncated       # true when anything was left out
```

## Statuses

Six, and they survive to whatever renders them. Collapsing them to "no rows" throws the
operator's diagnosis away.

| Status | Means | Fixed by |
| --- | --- | --- |
| `ok` | Read succeeded and returned something | — |
| `empty` | Read succeeded and the thing is empty | Nothing; it is a true answer |
| `forbidden` | The service refused the identity | A role grant |
| `unreachable` | Network, DNS or private-endpoint path | Not a role grant |
| `unconfigured` | A coordinate nobody set | Setting it; no client was built |
| `unavailable` | The service said no, or an SDK is missing | Depends; the detail says |

## Bounds and truncation

`ContentBounds` clamps rather than raises: a caller that computed `0` gets one row.

| Bound | Default | Enforced on |
| --- | --- | --- |
| `max_rows` | 100 | Rows kept from the sample |
| `max_bytes` | 1 MiB | Serialized UTF-8 size of the kept rows |
| `max_columns` | 512 | Distinct columns kept, in first-appearance order |
| `max_cell_chars` | 4000 | Characters of one rendered cell |
| `timeout_secs` | 20 | The whole read |

Rules a caller may rely on:

- **A bounded sample is lossy only where it says so.** `RowSample.truncated` is true if
  anything was left out; `RowSample.notes` names which bound did it, and those notes reach
  the wire as `ContentResponse.sampleNotes`.
- **A shortened cell says so inside the cell**, with `… [N more characters not shown]`, so
  a copied value cannot be mistaken for the whole one.
- **Data is never rewritten.** `sanitize_detail` strips URL-shaped tokens and is for
  exception text only. A URL, a JSON blob or a control character in a row is what the
  source holds and comes back as text. Running the error formatter over data was a real
  defect here — see PROVENANCE, "The sample bounds are this repository's".
- **A row bound is not a size bound.** 100 rows of 1,000 wide columns is bounded by
  `max_bytes`, not by `max_rows`. At least one row is always returned, so a single fat row
  previews rather than disappearing.
- **`KustoReader.rows` cannot report its own truncation.** It issues `take n`, so a full
  page looks identical to a table with exactly `n` rows. Compare the sample against
  `KustoTableInspector.facts(...).row_count`. `SearchReader` and `GraphReader` ask for
  `n + 1` and report truncation directly.
- **Rendering is the caller's.** These readers return text. Nothing here produces HTML, a
  link, or anything a renderer should execute.

## Target resolution

`GraphTarget(account, database, graph)` — all three are identity. Two accounts holding a
database and graph of the same name are two different graphs, and a resolver that keys a
client on fewer than three coordinates will serve one target's contents under another's
name. `GraphReader` never builds a client: it calls the injected
`resolve(target) -> GraphElementSource | None`, and `None` is `unconfigured`.

The graph reader imports nothing. Upstream's Gremlin plane authenticates with an Entra
token, which is unverified in this tenant; the only proven path here is an ARM
`readonlykeys` read with the ambient identity, so the transport stays with the caller that
has proved it.

## SDKs

`azure-kusto-data` and `azure-search-documents` are loaded on first call through `load()`.
A missing one is `unavailable` naming the distribution, not an `ImportError`. The same
seam is how every path is tested with no account and no network:
`override("azure.kusto.data", fake)`.

**`azure-search-documents` is not installed in this deployment.** Every Search slot is
`unconfigured` before a client is attempted, so nothing depends on it today. Configuring a
Search index means pinning the distribution first. Search *CRUD* is unaffected: it is REST
over the standard library and needs no distribution.

---

# CRUD plane

## `AdxConnector` — Azure Data Explorer

```python
from app.components.data_connector_library import AdxConfig, AdxConnector

connector = AdxConnector.from_env()                                # reads ADX_* environment
connector = AdxConnector(AdxConfig(cluster_uri=..., database=...))  # explicit
connector = AdxConnector.from_env(credential=my_credential)         # injected identity
```

`AdxConfig` resolves explicit arguments first, then `ADX_*` environment variables, so the
same code runs from a developer shell and from a managed identity with no branching. The
ingestion endpoint is derived from `cluster_uri` by prefixing the first host label with
`ingest-` unless `ADX_INGEST_URI` is set.

| Operation | Method | Notes |
| --- | --- | --- |
| Create (schema) | `create_table(schema, mapping_name=None) -> TableSchema` | |
| Create (schema from data) | `infer_schema_from_csv(csv_path, table_name, **kwargs) -> TableSchema` | |
| Create (rows) | `repo.insert(rows, mode=IngestMode.QUEUED)` | via `repo = connector.repository(schema)` |
| Create (bulk) | `load_csv(...)` | file-level ingest |
| Read | `query(kql, parameters=None, **kwargs) -> QueryResult` | every value crosses as a declared KQL parameter |
| Read (paged) | `iter_pages(kql, parameters=None, **kwargs)` | |
| Read (row) | `repo.get(key_column, key_value) -> dict \| None` | |
| Read (set) | `repo.read(...)`, `repo.latest_by(...)`, `repo.count(...)`, `repo.exists(...)` | |
| Update | `repo.update(...)` | append-plus-dedupe or soft-update; Kusto has no in-place row update, and `UpsertStrategy` names which one is in force |
| Delete | `repo.delete_where(predicate, parameters=None) -> int` | |
| Delete (keys) | `repo.delete_in(key_column, keys, chunk=500) -> int` | |
| Delete (hard) | `repo.purge_where(predicate, confirm=False)`, `repo.truncate(confirm="")`, `repo.drop(confirm="")` | each refuses without the explicit confirmation argument |
| Delete (extent) | `repo.drop_by_tag(tag)`, `repo.extents()` | |
| Command | `command(kql, parameters=None, **kwargs) -> QueryResult` | control commands |
| Health | `health() -> dict`, `list_tables() -> list[str]`, `table_schema(table_name) -> TableSchema` | |
| Ingest tuning | `set_batching_latency(table, seconds)`, `enable_streaming(table)`, `wait_for_rows(table, expected, ...)`, `ingestion_failures(hours=1)` | queued ingest is not immediately readable; `wait_for_rows` is the gate |
| Provision | `ensure_infrastructure(wait=True) -> ClusterInfo`, `connector.provisioner` | control plane; needs the provisioning triple |
| Close | `close()` | releases pooled clients |

Exported: `AdxClient`, `AdxConfig`, `AdxConnector`, `AdxProvisioner`, `ClusterInfo`,
`CrudRepository`, `UpsertStrategy`, `Ingestor`, `ColumnSpec`, `IngestMode`, `IngestResult`,
`QueryResult`, `TableSchema`, and the error hierarchy `AdxError`, `AdxAuthError`,
`AdxConfigError`, `AdxIdentifierError`, `AdxIngestionError`, `AdxProvisioningError`,
`AdxQueryError`, `AdxTimeoutError`.

**`query()` is the query endpoint, not the command endpoint.** A control command sent through
it — `.show tables` and the like — fails inside the SDK with `'NoneType' object is not
iterable` rather than a Kusto error. Use `command()`, or `list_tables()` for that one case.

Retries apply to throttling and transient service faults only. A client fault, and anything
the policy cannot classify, stops after a single attempt; `AdxQueryError` reports the number
of attempts actually made and carries `retryable` saying which kind it was. Guarded by
`app/components/tests/test_adx_connector_retry.py`.

### Configuration keys

Source file: `app/data/adx.env` (non-secret). Load with
`set -a && source app/data/adx.env && set +a`.

| Key | Required | Meaning |
| --- | --- | --- |
| `ADX_CLUSTER_URI` | yes | Query endpoint, `https://<cluster>.<region>.kusto.windows.net` |
| `ADX_DATABASE` | yes | Target database |
| `ADX_INGEST_URI` | no | Ingestion endpoint; derived from `ADX_CLUSTER_URI` when absent |
| `ADX_SUBSCRIPTION_ID` / `ADX_RESOURCE_GROUP` / `ADX_CLUSTER_NAME` | provisioning only | The control-plane triple |
| `ADX_LOCATION` | no | Default `australiaeast` |
| `ADX_SKU_NAME` / `ADX_SKU_TIER` | no | Default `Dev(No SLA)_Standard_E2a_v4` / `Basic` |
| `ADX_APPLICATION_NAME` | no | Reported to the service for traceability |
| `ADX_QUERY_TIMEOUT_SECONDS` | no | Default `240` |
| `ADX_MAX_RETRIES` | no | Default `4` |
| `ADX_BACKOFF_BASE_SECONDS` / `ADX_BACKOFF_CAP_SECONDS` | no | Default `0.5` / `20.0` |

Auth is `DefaultAzureCredential(exclude_interactive_browser_credential=False)` unless a
credential is injected into `AdxClient`/`AdxConnector`. No key, no connection string.

## `GremlinGraph` — Cosmos DB for Gremlin

```python
from app.components.data_connector_library import GremlinGraph, GremlinSettings

settings = GremlinSettings.from_env()
with GremlinGraph(settings, account_key) as graph:
    ...
```

`GremlinSettings.from_env()` raises `GremlinError` naming every missing required variable.
`GremlinGraph` is a context manager and closes its socket on exit.

| Operation | Method | Notes |
| --- | --- | --- |
| Create/Update (vertices) | `upsert_vertices(vertices) -> int` | idempotent, keyed by deterministic id; batched at `batch_size` |
| Create/Update (edges) | `upsert_edges(edges) -> int` | idempotent; batched |
| Read (arbitrary) | `submit(script, bindings=None) -> list` | every value passes as a Gremlin binding, never interpolated |
| Read (shape) | `counts()`, `label_counts()` | |
| Delete (all) | `drop_all()` | drops every vertex and edge in the graph |
| Close | `close()` | or use the context manager |

Exported: `GremlinGraph`, `GremlinSettings`, `GremlinError`, `DEFAULT_BATCH` (20),
`encode_properties`, `PROPERTY_TEXT_LIMIT` (1000). There is no per-element delete: the loader
is an idempotent full upsert, and the only supported removal is `drop_all()` and a reload.

`DEFAULT_BATCH` at this barrel is the Gremlin traversal-chain batch. Azure AI Search's own
document batch size is `app.components.azure_search.client.DEFAULT_BATCH` (50) and is
deliberately not re-exported under the same name.

### Property encoding — the caller's half of the contract

`encode_properties(properties) -> dict` is what `upsert_vertices` and `upsert_edges` run over
every property before binding it. It is public because **what a producer hands over decides
whether the value survives**, and a caller cannot see the rule from outside:

| Handed over as | Stored as |
| --- | --- |
| `list`, `tuple`, `set` | JSON array of sorted strings, whole |
| `dict` | JSON object, key-sorted, **whole — never truncated** |
| `bool`, `int`, `float` | as-is |
| anything else | `str(value)` truncated at `PROPERTY_TEXT_LIMIT` |
| `None`, `""`, `[]`, `{}` | dropped; no property is written |

The cap has teeth. A bucket map pre-serialised to JSON by the caller is free text, is chopped
mid-token at 1000 characters, and reads back as corrupt — which is how the 34 busiest edges in
the ontology graph were silently truncated once. Hand a mapping over as a mapping. Both halves
are guarded: `app/components/tests/test_gremlin_connector_properties.py` for the encoder,
`app/data/data_pipelines/perth/tests/test_graph_load_contract.py` for the producer.

### Configuration keys

Source file: `app/data/gremlin.env` (non-secret). `GREMLIN_ACCOUNT`, `GREMLIN_DATABASE` and
`GREMLIN_GRAPH` are required; `GREMLIN_PARTITION_KEY` (`pk`), `GREMLIN_PARTITION_VALUE`
(`perth`), `GREMLIN_BATCH_SIZE` (20) and `GREMLIN_MAX_RETRIES` (5) have defaults;
`GREMLIN_RESOURCE_GROUP` and `GREMLIN_SUBSCRIPTION_ID` are needed only to look the account
key up from the control plane.

Cosmos DB for Gremlin does not accept an Entra ID bearer token on the Gremlin wire protocol,
so `GremlinGraph` takes an account key as its second constructor argument. **The key is never
stored in the repository.** The caller resolves it at run time and passes it in — from
`GREMLIN_ACCOUNT_KEY` already in the environment, which is how a hosting platform resolves a
Key Vault reference, and otherwise through `cosmos_primary_key` over ARM. `GREMLIN_ACCOUNT_KEY` is not
a repository configuration key and never appears in `app/data/gremlin.env`. Nothing writes the
value to disk or logs. This is the one surface here whose auth is not a token credential.

`cosmos_primary_key(subscription, resource_group, account)` and
`cosmos_ensure_graph(subscription, resource_group, account, database, graph, partition_key, *,
max_throughput=4000, wait_seconds=300)` are exported from this barrel. Both accept an optional
`client=ArmClient(...)` for explicit identity or offline testing. Default identity acquisition
is lazy. The helpers use the existing ARM transport, request read-write keys only for graph
producers, and wait for creation read-back before reporting `created`. An existing graph is
never rewritten. Both pipelines retain their `arm.py` import paths as compatibility exports
of this one implementation; the pipeline framework remains datasource-neutral.

## `SearchIndexClient` — Azure AI Search

Re-exported from [`app/components/azure_search`](../azure_search), which owns the
implementation, its contract and its tests. Importing it from either place yields the same
class object. Everything that component exports is on this barrel except `DEFAULT_ENV_PREFIX`,
which is ambiguous at a barrel serving three services; import it from `azure_search` directly.

```python
from app.components.data_connector_library import (
    FieldSpec, IndexSpec, SearchIndexClient, VectorSpec, safe_key,
)

client = SearchIndexClient.from_env()                    # SEARCH_* environment
client.create_or_update_index(spec)
client.upload_documents("perth-kb", [{"id": safe_key("docs/a.md"), "title": "A"}])
hits = client.search("perth-kb", "explicit credential logon", top=5)
```

The one behaviour worth repeating here because it silently loses documents when unhandled:
**a 200 and a 207 carry the same per-document result array**, and a document can fail inside
an otherwise successful response. `upload_documents` and `delete_documents` inspect every
entry and raise `SearchError` carrying the first failed key.

---

## Adding a datastore

1. Create `<service>/` inside this package, with the connector and its values.
2. Resolve configuration at **call time** — explicit argument, then environment variable,
   then default. Never freeze configuration in a module-level constant.
3. Prefer a token credential. If the service requires a key, the caller supplies it at run
   time and the repository stores only its *name and location*, never its value.
4. Pass every caller-supplied value as a declared parameter or binding. Validate identifiers
   the query language cannot parameterise against a strict allowlist.
5. Add the names to `__all__`, and to `_LAZY_EXPORTS` if the module imports an SDK at module
   scope. Add a section here documenting the CRUD surface, configuration keys, and auth.

## Status

Proved against real services: ADX rows and facts, and a Cosmos Gremlin graph through
`app/cybereye/backend/inventory/probes.py`; ADX CRUD and Gremlin upsert through both data
pipelines, from the code these modules were ported from byte for byte. Simulated only, and
labelled as such in the tests: Search CRUD mutations and the consolidated Cosmos provisioning
helpers. The configured MITRE Search index's read path is verified by the application runbook;
this maintenance change did not provision or mutate cloud data.

## Tests

Offline, no Azure account, no network:

```bash
/usr/bin/python3 -m unittest discover -s app/components/tests -t .
```

| File | Covers |
| --- | --- |
| `test_data_connector_library.py` | the read plane: bounds, statuses, readers, the SDK seam |
| `test_connector_library_surface.py` | the public surface, the import-cost rule under blocked SDKs, Search re-export identity, Search CRUD including 207 |
| `test_adx_connector_retry.py` | the retry policy's attempt reporting and fault classification |
| `test_gremlin_connector_properties.py` | the property encoder, its cap, and binding discipline |
| `test_connector_library_contract.py` | the migrated public signatures and every name the two superseded barrels exported, plus that the superseded package is gone |
| `test_cosmos_control.py` | shared graph creation, no-write existing path, key refusal, read-back failure, and both pipeline aliases |
