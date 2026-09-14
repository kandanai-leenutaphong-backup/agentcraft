# Azure Data Connector Contract

Implemented surface: **`azdata` 4.0.0a1**, contract version `1`, Python 3.11+.
This is an experimental first pass, not a production-readiness or live-permission claim.
The [README](README.md) retains the broader design and the delivery status.

## Ownership And Dependencies

Runtime source is [src/azdata](src/azdata). It imports only the standard library and its own
package. It does not import skills, template applications, environment configuration or
Azure SDKs. The optional `identity` extra installs `azure-identity` for callers that want to
construct a credential at their composition root; the library never constructs one for them.

The shared facade owns validation, scope/policy checks and result normalization. Adapters own
native request mapping and comparison semantics. One session transport handles bounded HTTP,
token refresh and per-connector concurrency. Verification polling and continuation integrity
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

- Registered service identifiers are exactly `search` and `cosmos`. Others raise the common
  `ConfigurationError`; there is no dynamic import/plugin loading from configuration.
- Construction validates configuration and adapter scope without performing I/O. Description
  similarly performs no token acquisition, package installation or provider request.
- `credential` must expose `get_token(scope)`. Sync and async implementations are supported;
  the returned object carries `token` and Unix `expires_on`. Credentials are always borrowed.
- `transport`, when supplied, is borrowed and implements
  `async request(request: HttpRequest) -> HttpResponse`. This is a trusted composition-time
  dependency, not a request-level ability to redirect a call.
- `describe()` returns an immutable description of all ten operations, current mode/action
  support, allowed option names, guarantees, limits, key requirements, grants and caveats.
  `availability` remains `unverified`; supported does not mean authorized or reachable.
- `aclose()` is async and idempotent. The default local transport is owned and closed once;
  injected credentials and transports are not closed. Remote operations are not rolled back.
- Async context management closes the connector on exit. Calls after close return a standard
  `failed` result with `connector_closed`, without new I/O.

### Configuration

`ConnectorConfig(endpoint, target, allowed_hosts, ...)` requires an HTTPS service origin
without embedded credentials, path, query or fragment. Ports are limited to default HTTPS.
The exact lower-case host must be in the caller's explicit `allowed_hosts`. Redirects are
not followed by the default transport. These are operator decisions, never values taken
unchecked from a request or tenant record.

Optional fields: `key_field="id"`, `partition_key_field=None`,
`api_version="2024-07-01"`, `scope=None`, `retrievable_fields=None`.

| Service | Target Coordinates | Key/Partition Configuration | Default Credential Audience |
| --- | --- | --- | --- |
| `search` | Exactly `{"index": "name"}` | Configured key field; no partition field | `https://search.azure.com/.default` |
| `cosmos` | Exactly `{"database": "name", "container": "name"}` | `id` and an explicit top-level partition field | `https://cosmos.azure.com/.default` |

The endpoint, token audience and host allowlist are trusted configuration. Supplying an
untrusted allowlist defeats its purpose. Live role requirements and identity support have
not been verified by the synthetic tests. No secret-based fallback is implemented.

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

| Method | Request | First-Pass Support |
| --- | --- | --- |
| `create` | `CreateRequest` | Cosmos native insert; Search refuses atomic-create semantics |
| `read` | `ReadRequest` | Both services, using exact addressed keys |
| `update` | `UpdateRequest` | Search merge; Cosmos replace |
| `upsert` | `UpsertRequest` | Search merge/replace; Cosmos replace |
| `delete` | `DeleteRequest` | Both services, with explicit missing-record behavior |
| `query` | `QueryRequest` | Native Search and Cosmos SQL document results |
| `ingest` | `IngestRequest` | Present, returns `unsupported` |
| `schema` | `SchemaRequest` | Search only, scoped to the configured index |
| `provision` | `ProvisionRequest` | Present, returns `unsupported` |
| `status` | `StatusRequest` | Present, returns `unsupported` |

Unsupported operations, modes and guarantees refuse before transport or token calls. No
`NotImplementedError` or missing-method branch is required by a caller.

### Request Values

Requests are frozen dataclasses with keyword-only fields. Nested containers are copied into
immutable mappings/tuples, so changing the caller's original payload does not change a queued
request. Operation validation rejects malformed values before provider execution.

Common fields: `target=None`, generated bounded `request_id`, `limits=None`, empty
`Requirements`, `Verification(kind="none")`, and namespaced `service_options={}`.

- `RecordKey(parts, partition=None)` currently accepts one string key part named by config.
  Cosmos requires a non-null scalar partition. Hierarchical/composite keys beyond ID plus
  scalar partition are deferred, not silently encoded into strings.
- `ContentValue(data, kind="json", media_type="application/json")` snapshots the value;
  current mutation adapters require JSON document mappings. Bytes/tabular forms exist as
  values but are not supported mutation forms in this pass.
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
- `IngestRequest`, `ProvisionRequest` and `StatusRequest` are modeled values, not delivered
  provider functionality. Their uniform refusal is tested for both adapters.

### Native Queries

`QueryRequest(dialect, expression, parameters={}, projection=(), continuation=None, ...)`
is the same class for both services. Expressions are bounded to 12,000 characters. Parameters
are separate data values; no generic string interpolation is performed.

Search uses `dialect="search"` and namespaced `service_options={"search": {...}}`.
It maps keyword/full/semantic query type, semantic configuration, filter/order/search fields,
search mode, language and explicit numeric-vector queries to the native API. Arbitrary query
parameters refuse because Search has no corresponding binding API here. Count/facet/answer/
caption metadata are explicitly unsupported in the current result model; they are not silently
requested and discarded. Unknown/reserved option names refuse.

Cosmos uses `dialect="cosmos-sql"`. Queries use the native read-only query endpoint, a SELECT
prefix guard and bounded response pages; that guard is not a general SQL parser or replacement
for read-scoped credentials. Parameter names must be `@name` and are passed in native parameter
objects. `service_options={"cosmos": {"partition": value}}` limits a query to that partition;
otherwise query scope is the configured container. Object-shaped result rows are supported;
scalar `SELECT VALUE` projections are not supported in this alpha.

Continuation tokens are opaque, authenticated with a connector-local random key, and bound
to endpoint, target, principal, grants and query settings. They cannot be reused on another
connector instance or after restart. Search uses bounded offset pagination and does not claim
snapshot consistency. Cosmos wraps a native continuation. A local byte truncation returns
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

`OperationResult` contains request/operation/service/target identity, aggregate `status`,
ordered `items`, `errors`, `verification`, `continuation`, `truncated`, `operation_ref`,
`caveats`, measured `metrics` and `contract_version`. Description and results provide
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
| `content` | Search matches the requested field projection; Cosmos compares the complete writable replacement excluding known server-owned fields |
| `absence` | An authorized read confirms absence at the supplied address/partition |
| `schema` | Requested Search schema fields read back, or confirmed absence after deletion |

Verification states are `not_requested`, `satisfied`, `pending`, `unknown` or `failed`, with
requested/achieved evidence and observed attempt counts. Polling is bounded by the operation
deadline, at most 20 requested observations and intervals between 0 and 5 seconds.

Search `content` evidence requires operator-declared `retrievable_fields` that cover the
requested fields. Null and complex-object comparison is conservatively unsupported. Values
are compared without conflating JSON bool and integer. Presence of stale content does not
verify an update. Cosmos comparison preserves partition scalar types and excludes only its
known server metadata. Absence in one partition does not establish global ID absence.

## Transport And Resource Safety

The default transport reuses the standard-library REST approach from the existing Search
client, with redirects disabled, response-size bounds, no error-body logging and no SDK
retry layer. Search uses bearer authorization; Cosmos uses the AAD REST authorization form.
Live wire compatibility remains unverified until the separately authorized live pass.

One token is cached per connector and refreshed when within 300 seconds of expiry. Sync
credentials and blocking HTTP run off the event loop. Borrowed credentials are never closed.
The per-connector semaphore bounds concurrency but is not a distributed endpoint-wide gate.

Mutations make one submission attempt per native call. Eligible read calls may retry
429/502/503/504 under `Limits.max_attempts`; a numeric Retry-After beyond the remaining deadline
does not get shortened to force another request. Overall work has a finite deadline. A timeout
after mutation submission is `unknown`, never evidence nothing was stored.

The default response byte cap covers native response bodies; returned content also has an
aggregate bound. Truncated query pages must not be silently represented as complete. Blocking
thread cancellation cannot terminate an already-running HTTP operation, and closing local
resources cannot cancel or roll back remote work. No durable operation journal is implemented.

## Offline Checks

Run from the repository root:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=libraries/azure-data-connectors/src \
  python3 -B -m unittest discover -s libraries/azure-data-connectors/tests -q
```

All tests use synthetic identities/transports or mocked local HTTP. The
[stateful consumer](tests/integration/test_consumer.py) writes, reads back, queries and deletes
through both public connectors, and proves create never overwrites its pre-existing fixture.
The same tests run against an offline-built wheel in a fresh environment without repository
`PYTHONPATH`, Azure SDKs or access to the skill packages.

`tests/live_tests/` contains [the numbered live-test design](tests/live_tests/LIVE_TEST_DESIGN.md).
No executable live test, fixture or cloud call is included. The design separates positive
CRUD evidence, valid unsupported-operation refusals and blocked service prerequisites.

## Limits And Deferred Work

- Only Search and Cosmos are registered. Other services and all ingestion/provision/status
  implementations are deferred; methods still have the common callable refusal interface.
- No real cloud identity, permissions, consistency, network or provider-version guarantee
  has been verified. Offline tests validate this implementation against controlled fixtures.
- No legacy skill, MCP or template consumer has been migrated; old implementations and
  existing `azdata` 3.x APIs remain unchanged. This alpha is not an in-place upgrade.
- Search query aggregation metadata, nested projections, null/object content comparisons,
  automatic schema migration and update-only replacement are not implemented.
- Cosmos merge, hierarchical/null partition keys, scalar query rows, batch atomicity and
  schema/provisioning are not implemented.
- Continuations are process/connector-local; there is no durable restart recovery or status
  journal. Cancellation handling makes no remote rollback claim.
- Retry/gate handling is bounded per connector, not yet the legacy endpoint-wide breaker
  and adaptive-throttle system. Retry-After HTTP-date interpretation is deferred.
- Full legacy SDK behavior parity, redistribution/release review and consumer migration are
  subsequent passes, not proof implied by a working wheel.