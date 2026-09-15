# Azure Data Connector Contract

Implemented surface: **`azdata` 4.0.0a3**, contract version `1`, Python 3.11+.
This is an experimental SDK-backed alpha, not a production-readiness or live-permission claim.
The [README](README.md) retains the broader design and the delivery status.

## Ownership And Dependencies

Runtime source is [src/azdata](src/azdata). It directly uses `azure-core`; optional `search`,
`cosmos`, `blobs`, `tables`, `kusto`, `graph`, `gremlin`, `sql` and `postgresql` extras supply
their actual SDKs, models, drivers, parsers and HTTP/WebSocket dependencies. Provider code
loads lazily. Base import needs no provider extra. Missing extras yield
an explicit `failed` result with `missing_dependency_<service>` before credentials or I/O.
The optional `identity` extra supplies `azure-identity` for a host-owned credential; the
library never constructs one. No skill or template implementation is imported.

The shared facade owns validation, scope/policy checks and result normalization. Adapters own
native SDK mapping and comparison semantics. SDK clients own native operations, token policies,
models and paging. One boundary preserves bounded HTTP and per-connector concurrency, without
a second REST fallback. Verification polling and continuation integrity
have one shared implementation; provider-specific comparison rules remain in their adapters.

No old skill implementations have been retired. Alpha `azdata` 4 and legacy `azdata` 3 cannot
share the same import namespace in one environment. Use an isolated environment; a versioned
consumer migration is a separate operation, not an installation side effect.

## Public Imports

Import from `azdata`, not from its private adapter or execution modules:

- `connect`, `DataConnector`, `ConnectorConfig`, `Policy`, `ConfigurationError`.
- `ResourceAddress`, `RecordKey`, `ContentValue`, `RecordInput`.
- `Limits`, `Requirements`, `Verification`, `confirmation_digest`.
- `CreateRequest`, `ReadRequest`, `UpdateRequest`, `UpsertRequest`, `DeleteRequest`,
  `QueryRequest`, `IngestRequest`, `SchemaRequest`, `ProvisionRequest`, `StatusRequest`.
- `OperationResult`, `ItemResult`, `ErrorInfo`, `Caveat`, `VerificationResult`,
  `OperationCapability`, `ConnectorDescription`.
- `AsyncTransport`, `HttpRequest`, `HttpResponse`, `CONTRACT_VERSION`, `OPERATIONS`.

These public values are defined in [contracts.py](src/azdata/contracts.py).

## Factory And Lifecycle

`connect(service, config, *, credential, policy, transport=None) -> DataConnector`

- Registered identifiers are `search`, `cosmos`, `blobs`, `tables`, `adx`, `eventhouse`,
  `graph`, `gremlin`, `sql` and `postgresql`. Others raise the common
  `ConfigurationError`; there is no dynamic import/plugin loading from configuration.
- Construction validates configuration and adapter scope without performing I/O. Description
  similarly performs no token acquisition, package installation or provider request.
- `credential` must expose `get_token(scope)`. Sync and async implementations are supported;
  the returned object carries `token` and Unix `expires_on`. Credentials are always borrowed.
- `transport`, when supplied, is borrowed and implements
  `async request(request: HttpRequest) -> HttpResponse`. This is a trusted composition-time
  dependency, not a request-level ability to redirect a call. Native SQL/PostgreSQL/Gremlin
  profiles refuse an HTTP transport rather than ignore it or convert database traffic to HTTP.
- `describe()` returns an immutable description of all ten operations, current mode/action
  support, allowed option names, guarantees, limits, key requirements, grants and caveats.
  `availability` remains `unverified`; supported does not mean authorized or reachable.
- `aclose()` is async and idempotent. The default local transport is owned and closed once;
  owned SDK clients close with it. Injected credentials and transports are not closed. Remote
  operations are not rolled back.
- Async context management closes the connector on exit. Calls after close return a standard
  `failed` result with `connector_closed`, without new I/O.

### Configuration

`ConnectorConfig(endpoint, target, allowed_hosts, ...)` requires a service origin without
embedded credentials, path, query or fragment. Adapters enforce their protocol: HTTPS/443,
WSS/443 for Gremlin, MSSQL/1433 for SQL, PostgreSQL/5432 for PostgreSQL.
The exact lower-case host must be in the caller's explicit `allowed_hosts`. Redirects are
not followed by the default transport. These are operator decisions, never values taken
unchecked from a request or tenant record.

Optional fields: `key_field="id"`, `partition_key_field=None`,
`api_version="2024-07-01"`, `scope=None`, `retrievable_fields=None`, `key_fields=None`,
`database_user=None`, `enable_preview=False`, `credential_kind="entra"`.

| Service | Target Coordinates | Key/Partition Configuration | Default Credential Audience |
| --- | --- | --- | --- |
| `search` | Exactly `{"index": "name"}` | Configured key field; no partition field | `https://search.azure.com/.default` |
| `cosmos` | Exactly `{"database": "name", "container": "name"}` | `id` and an explicit top-level partition field | `https://cosmos.azure.com/.default` |
| `blobs` | `{"container": "name"}` | One configured name key, no partition | `https://storage.azure.com/.default` |
| `tables` | `{"table": "Name"}` | Exactly `PartitionKey` and `RowKey`, no separate partition | `https://storage.azure.com/.default` |
| `adx`, `eventhouse` | `{"database": "Name"}`, optional `table` | Table required for ingest/schema; query is database-scoped | `https://kusto.kusto.windows.net/.default` |
| `graph` | `{"workspace": "uuid", "graph_model": "uuid"}` | Canonical UUIDs; query requires `enable_preview=True` | `https://api.fabric.microsoft.com/.default` |
| `gremlin` | `{"database": "Name", "container": "Name"}` | `id`, string partition, `credential_kind="resource_token"` | Credential-provider lookup scope `https://cosmos.azure.com/.default`; token must be a resource token, not an Entra JWT |
| `sql` | `{"database": "Name", "schema": "dbo", "table": "Name"}` | Configured unique `key_fields` or default `id` | `https://database.windows.net/.default` |
| `postgresql` | `{"database": "Name", "schema": "public", "table": "Name"}` | Configured unique key fields plus Entra `database_user` | `https://ossrdbms-aad.database.windows.net/.default` |

The endpoint, token audience and host allowlist are trusted configuration. Supplying an
untrusted allowlist defeats its purpose. Live role requirements and identity support have
not been verified by the synthetic tests. No account-key, password, SAS or automatic identity
fallback is implemented. Gremlin's explicitly selected resource-token profile requires a
caller-owned secure token authority; the library does not provision that authority or issue tokens.

The first Cosmos operation performs SDK account/container metadata reads as needed; it may
need data-plane metadata permission as well as document permission. Region discovery and
hedging remain disabled and every outgoing origin must match the configured endpoint.
The credential bridge pins the caller-selected/default audience instead of allowing ambient
SDK scope overrides to redirect token acquisition. SDK metadata reads do not grant schema or
infrastructure mutation authority. Cosmos wire API versions follow the installed SDK;
`api_version` selects the Search API version.

### Policy

`Policy(principal, grants=..., limits=..., minimum_verification=..., max_concurrency=4,
destructive=False)` snapshots its configuration. `principal` identifies the scope established
by the host; it does not authenticate a caller. The host still owns user authorization and
record-level access decisions.

Default grants are `read` and `query`; mutation is denied. Grants use operation names, except
administrative grants use `schema.<action>` or `provision.<action>`. All are validated.
Data deletion, schema deletion and infrastructure deletion do not imply one another.

Every connector is fixed to one target and one immutable policy. An operation's optional
target must equal that target exactly. A request cannot change credentials, endpoint, principal
or grants; service options do not bypass these checks.

Default limits are 30 seconds, 100 input/results items, 1 MiB input content, 1 MiB output
content and one transport attempt per native call. Integers must be positive and not bool;
timeouts must be finite and positive. Requests can only lower configured ceilings.
Per-connector concurrency is configurable from 1 to 64.

`minimum_verification` maps operation/grant to an evidence kind. A request omitting evidence
inherits the configured minimum; an explicit weaker value refuses. A required verification
read must also be granted before a mutation is submitted. Schema mutations always require
schema read-back and the `schema.read` grant.

## Uniform Operations

Every operation below is async, takes exactly one named request object and returns the same
`OperationResult` class. Passing the wrong request class returns `invalid`.

| Profile | Create / Read / Delete | Update | Upsert | Query | Ingest | Schema | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `search` | Create unsupported; read/delete native | Merge | Merge/replace | Search | Unsupported | Read/list/create/additive update/delete | Unsupported |
| `cosmos` | Native, explicit partition | Replace | Replace | Cosmos SQL | Unsupported | Unsupported | Unsupported |
| `blobs` | Native block blobs | Replace | Replace | Prefix listing | Unsupported | Unsupported | Unsupported |
| `tables` | Native composite-key entities | Merge/replace | Merge/replace | OData | Unsupported | Unsupported | Unsupported |
| `adx`, `eventhouse` | Unsupported keyed CRUD | Unsupported | Unsupported | KQL | Bounded streaming append | Table read | Unsupported |
| `graph` | Unsupported vertex/edge CRUD | Unsupported | Unsupported | Beta GQL | Refresh existing model sources | Definition read | Scoped refresh/definition jobs |
| `gremlin` | Partitioned vertices | Merge | Unsupported | Read traversal subset | Unsupported | Unsupported | Unsupported |
| `sql`, `postgresql` | Native keyed rows | Merge | Transactional merge-upsert | Parsed native SELECT subset | Unsupported | Column read | Unsupported |

All methods retain their matching `CreateRequest`, `ReadRequest`, `UpdateRequest`,
`UpsertRequest`, `DeleteRequest`, `QueryRequest`, `IngestRequest`, `SchemaRequest`,
`ProvisionRequest` or `StatusRequest` class. `provision` is uniformly unsupported in this alpha.

Unsupported operations, modes and guarantees refuse before transport or token calls. No
`NotImplementedError` or missing-method branch is required by a caller.

### Request Values

Requests are frozen dataclasses with keyword-only fields. Nested containers are copied into
immutable mappings/tuples, so changing the caller's original payload does not change a queued
request. Operation validation rejects malformed values before provider execution.

Common fields: `target=None`, generated bounded `request_id`, `limits=None`, empty
`Requirements`, `Verification(kind="none")`, and namespaced `service_options={}`.

- `RecordKey(parts, partition=None)` carries named keys. Table uses two string key parts;
  relational profiles accept configured string/integer key parts backed by a unique constraint.
  Cosmos uses one string ID and a non-null scalar partition; Gremlin requires a string partition.
  Null/hierarchical Cosmos partitions are deferred, not silently encoded into strings.
- `ContentValue(data, kind="json", media_type="application/json")` snapshots the value;
  supports adapter-declared JSON mappings, Blob `kind="bytes"`, Table `kind="entity"` and
  relational `kind="row"`. Native bytes, datetime/date/time, Decimal, UUID and timedelta
  values receive explicit serialization tags in `to_dict()` rather than silent stringification.
  Table SDK wrapper classes are normalized; integer width is selected by the native adapter.
  Table timestamp precision follows Python datetime/the SDK, not an extra nanosecond guarantee.
- `RecordInput(key, content, expected_version=None)` associates an exact identity with its
  payload. Mismatching ID/partition values, invalid JSON, non-finite numbers and ambiguous
  repeated mutation keys refuse before I/O. Repeated read keys retain their input positions.
- Update and upsert require an explicit `mode="merge"` or `mode="replace"`. No `upload`
  alias guesses the meaning. Search document versions and Cosmos merge modes are unsupported.
- Read/delete take `keys`; both expose `missing="error"|"ok"`. Delete takes an optional
  ordered `expected_versions` tuple. Exact versions cannot be wildcard `*` or header-injecting
  text. Cosmos conditional update/delete requirements require a version for every item.
- `Requirements(guarantees=(...))` is checked against the adapter. The base meaning of create
  still prohibits overwrite even if no guarantee is explicitly requested.
- Projections are top-level field names in this pass. Nested field-path projections refuse
  explicitly rather than return incomplete content under a successful result.
- Kusto `IngestRequest` accepts JSON row mappings/sequences or bytes with `json`, `multijson`,
  `csv` or `tsv` formats and optional namespaced `mapping`. Streaming policy/schema must already
  exist. The 4 MiB ceiling and request bounds apply; deduplication requirements/idempotency keys
  and content verification refuse before submission. Acknowledgment alone is available.
- Graph `IngestRequest(format="refresh")` accepts no record payload. It starts a refresh of
  existing sources, returning `pending` and a connector-bound reference. `StatusRequest`
  checks that exact job/definition operation, honors `Retry-After`, and never treats refresh
  completion as input-batch content proof.

### Native Queries

`QueryRequest(dialect, expression, parameters={}, projection=(), continuation=None, ...)`
is the same class for every service. Expressions are bounded to 12,000 characters. Parameters
are separate data values; no generic string interpolation is performed.

Search uses `dialect="search"` and namespaced `service_options={"search": {...}}`.
It maps keyword/full/semantic query type, semantic configuration, filter/order/search fields,
search mode, language and explicit numeric-vector queries to the native API. Arbitrary query
parameters refuse because Search has no corresponding binding API here. `count`, `facets`,
`answers` and `captions` are supported options: counts/facets/answers use common result
`metadata`; caption models are serialized to structured document annotations. Native metadata
and rows come from one fetched page, not a second query. Unknown/reserved option names refuse.

Cosmos uses `dialect="cosmos-sql"`. Queries use the native read-only query endpoint, a SELECT
prefix guard and bounded response pages; that guard is not a general SQL parser or replacement
for read-scoped credentials. Parameter names must be `@name` and are passed in native parameter
objects. `service_options={"cosmos": {"partition": value}}` limits a query to that partition;
otherwise query scope is the configured container. Object-shaped result rows are supported;
scalar `SELECT VALUE` projections are not supported in this alpha.

Blob uses `blob-prefix`; an empty expression lists the configured container root. Results
are name/size metadata; bytes are read by key. Uploads are single bounded block-blob PUTs,
not append/page blobs, leases, historical versions or automatic snapshot deletion. Exact
bytes are preserved even for blobs labeled `application/json`.

Table uses `odata` with SDK parameter binding and native continuation. Entities preserve
binary, Int64, timezone-aware datetime and UUID values; nested/null properties and out-of-range
integers refuse. Exact ETags are supported for update/delete, not conditional upsert.

Kusto uses `kql` and SDK `ClientRequestProperties`. The query endpoint, read-only and
remote-entity restrictions, server timeout and row/byte caps are fixed by the adapter.
Management text cannot enter `query`; parameters remain separate values. Both ADX and
Eventhouse use the same owner. Partial-error frames cannot be reported as complete success.
Queries are database-scoped even when a table coordinate is supplied for ingestion.

Graph uses `gql`, requires preview opt-in and accepts a conservative read-query form.
Native parameter binding is not documented by this API, so parameters refuse instead of
being interpolated. GQL status `00000` and table-shaped data are checked independently of
HTTP 200. Native continuation is wrapped; local truncation does not invent a resume point.

Relational profiles use `tsql` or `postgresql`. SQLGlot parses one SELECT, restricts table
references and functions, and maps named `:parameter` values to driver positional bindings
in rendered order. CTE/other-table references, DML, SELECT INTO, locks, scripts and unknown
functions refuse. PostgreSQL also opens a read-only transaction for queries. Keyed insert,
merge update/delete and native conflict-upsert/locked SQL merge-upsert use transactions;
there is no cross-request or cross-record transaction promise. Row-version preconditions
and full replacement refuse; create-content verification cannot prove unknown server defaults.

Gremlin accepts a parsed `g.V()`/`g.E()` read-chain subset with validated predicates and bound
literal values; it never evaluates Python/Groovy locally. Scripts, mutating steps, bytecode,
lambdas and undeclared names refuse. Vertex writes use generated traversals with scalar
properties; upsert and transactions are not fabricated. Resource tokens refresh on new
connections, account-key/JWT substitution refuses, and SDK 3.7.7 service compatibility is
explicitly unverified against Microsoft's older recommended driver line.

Continuation tokens are opaque, authenticated with a connector-local random key, and bound
to endpoint, target, principal, grants and query settings. They cannot be reused on another
connector instance or after restart. Search, Cosmos, Blob, Table and Graph wrap native continuation rather than
constructing new offsets, without claiming snapshot consistency. Kusto, relational and
Gremlin queries do not supply pagination; truncated results are marked. Search's native token bytes
are converted to an opaque string. A local byte truncation returns
`truncated=True` without an unusable continuation, and retains only the result prefix.

### Search Schema

`SchemaRequest(action, definition=None, expected_version=None, confirmation=None, ...)`
uses native JSON index definitions. Supported actions are `list`, `read`, `create`, `update`
and `delete`. Listing returns only the authorized configured index, not every index on a service.

Create uses `If-None-Match: *`. Update/delete require an exact version and use `If-Match`.
Update first reads the current definition, verifies the version and allows conservative
additive fields only: removing/changing an existing field or replacing other existing schema
settings refuses. There is no drop-and-recreate or automatic data migration.

Delete requires `schema.delete`, `schema.read`, `Policy(destructive=True)` and
`confirmation_digest("search", config, request)` in the request's confirmation field. The
digest binds service, endpoint, target, action, version and definition; it grants nothing by
itself. Mutations read back the state and return named `schema` evidence. A mismatch or a
failed verification read preserves accepted/pending/unknown state instead of claiming no write.

## Results And Evidence

Graph operation references use the same authenticated encoding, bound separately to service,
endpoint, target, principal and grants. Raw provider URLs and references from other connectors
are not accepted by `status`. References are not durable across connector instances/restarts.

`OperationResult` contains request/operation/service/target identity, aggregate `status`,
ordered `items`, `errors`, `verification`, `continuation`, `truncated`, `operation_ref`,
`caveats`, measured `metrics`, `metadata` and `contract_version`. `metadata` is an immutable
mapping, empty when unused; its JSON size is charged against the output content limit before
returning bounded records. Oversized metadata refuses instead of being silently discarded.
Description and results provide
`to_dict()` for deliberate serialization at an application/CLI/MCP boundary. This output
includes returned content; it is not intended as a safe automatic log payload.

Statuses: `success`, `partial`, `pending`, `unknown`, `not_found`, `conflict`, `invalid`,
`denied`, `unsupported`, `failed`. A mixed batch is `partial`; individual unsubmitted items
use `not_attempted`. Empty operations are successful no-ops without invented verification.
An empty query is not a missing record.

Each item retains its input index/key, status, optional content/version/error and verification,
plus `effect="none"|"accepted"|"unknown"`. Known accepted outcomes survive missing or duplicated
batch acknowledgments. Ambiguous writes are not retried. A failure after earlier Cosmos items
retains those items and an explicitly unattempted tail. No batch transaction/rollback is claimed.

Expected provider errors use safe bounded codes without raw provider bodies. Errors from the
injected credential become `credential_unavailable`; raw exception text is not returned.
Programming defects remain exceptions rather than fake service failures. `CancelledError`,
`KeyboardInterrupt` and `SystemExit` propagate. Cancellation may occur after remote acceptance;
the caller must not infer rollback or blindly retry.

| Evidence Kind | Implemented Meaning |
| --- | --- |
| `none` | No verification requested; not a persistence claim |
| `acknowledgment` | Native operation/item acceptance only |
| `presence` | An authorized addressed document read succeeds |
| `content` | Search matches requested fields; Cosmos compares writable replacement; Blob compares bytes; entity/row/vertex merge checks supplied values without conflating bool and integer |
| `absence` | An authorized read confirms absence at the supplied address/partition |
| `schema` | Search mutation fields/absence read back; supported Kusto/relational schema reads return observed structure. Graph definition reads currently carry no extra schema-evidence claim. |

Verification states are `not_requested`, `satisfied`, `pending`, `unknown` or `failed`, with
requested/achieved evidence and observed attempt counts. Polling is bounded by the operation
deadline, at most 20 requested observations and intervals between 0 and 5 seconds.

Search `content` evidence requires operator-declared `retrievable_fields` that cover the
requested fields. Null and complex-object comparison is conservatively unsupported. Values
are compared without conflating JSON bool and integer. Presence of stale content does not
verify an update. Cosmos comparison preserves partition scalar types and excludes only its
known server metadata. Absence in one partition does not establish global ID absence.

## Transport And Resource Safety

Official SDK clients supply authorization formatting and native request construction. The
default HTTP mechanism is Azure Core's `AioHttpTransport`; redirects remain disabled and
success bodies are bounded before SDK deserialization. Error bodies are not read by the
default transport or copied into standard diagnostics. Live behavior remains unverified.

SDK bearer-token policies cache/refresh tokens; the bridge validates borrowed sync/async
credentials and uses the configured audience. Sync credential calls run off the event loop.
The per-connector semaphore bounds concurrency but is not a distributed endpoint-wide gate.

Azure Core's async retry policy is restricted by `Limits.max_attempts` and the overall
deadline. SDK retry hints, including HTTP-date parsing, replace the hand-written delay loop.
Mutations have zero automatic retry allowance; the transport refuses a second native mutation
submission and Cosmos terminal errors are normalized before its extra retry layers. Cosmos
`retry_write` is disabled. A timeout after possible mutation submission is `unknown`, never
evidence nothing was stored. SDK metadata calls are included in measured attempt counts.

The default response byte cap covers native response bodies; returned content and query
metadata also have an aggregate bound. Truncated query pages must not be silently represented
as complete. HTTP is async; cancellation still cannot roll back remote acceptance or stop an
already-running synchronous credential call. No durable operation journal is implemented.

SQL/PostgreSQL use fresh logical connections with TLS verification and injected Entra tokens,
never caller-supplied connection text. Native login/statement timeouts apply; blocking SQL
and Gremlin workers are awaited through cleanup on cancellation rather than abandoned.
Native driver buffering can precede the decoded output-byte check; it is not an HTTP-style
pre-deserialization memory cap. Server-side work may outlive client cancellation. Gremlin's
WebSocket transport refuses redirects/foreign URLs and bounds complete frames.

## Offline Checks

Run from `libraries/` using the [workspace's dependency sequence](../README.md):

```bash
uv run --locked --package azdata --all-extras --no-default-groups \
  python -B -m unittest discover -s azure-data-connectors/tests -t azure-data-connectors -q
```

All tests use synthetic identities/transports or controlled native driver doubles. The
[stateful consumer](tests/integration/test_consumer.py) writes, reads back, queries and deletes
through both public connectors, and proves create never overwrites its pre-existing fixture.
Search/Cosmos/Storage tests run real SDK serialization/paging over fake HTTP. Kusto uses real
SDK models; Gremlin includes real protocol serialization/SASL; relational tests verify native
driver API calls with fake connections, not live database engines. Artifact tests use a fresh environment with selected extras and no repository
`PYTHONPATH` or access to skill implementations. Base import/missing-extra checks run separately
without provider SDKs or aiohttp. SDK fixtures are not live Azure evidence. See [verification](VERIFICATION.md).

`tests/live_tests/` contains [the numbered live-test design](tests/live_tests/LIVE_TEST_DESIGN.md).
No executable live test, fixture or cloud call is included. The design separates positive
CRUD evidence, valid unsupported-operation refusals and blocked service prerequisites.

## Limits And Deferred Work

- All ten profiles are registered, with the matrix above. Infrastructure provisioning,
  most schema mutations, queued ingestion/durable batch evidence, blob chunked uploads,
  cross-record transactions and complete native API parity are not implemented.
- No real cloud identity, permissions, consistency, network or provider-version guarantee
  has been verified. Offline tests validate this implementation against controlled fixtures.
- No legacy skill, MCP or template consumer has been migrated; old implementations and
  existing `azdata` 3.x APIs remain unchanged. This alpha is not an in-place upgrade.
- Nested Search projections, null/object content comparisons,
  automatic schema migration and update-only replacement are not implemented.
- Cosmos merge, hierarchical/null partition keys, scalar query rows, batch atomicity and
  schema/provisioning are not implemented.
- Gremlin requires an external resource-token authority and live verification of the newer
  driver line. Graph query is beta; neither caveat is hidden by uniform method signatures.
- Continuations/references are process/connector-local; there is no durable restart recovery or status
  journal. Cancellation handling makes no remote rollback claim.
- Retry/gate handling is bounded per connector, not yet the legacy endpoint-wide breaker
  and adaptive-throttle system. Native SDK defaults/versions remain part of the tested boundary.
- Full legacy SDK behavior parity, redistribution/release review and consumer migration are
  subsequent passes, not proof implied by a working wheel.