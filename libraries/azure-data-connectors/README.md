# Azure Data Connectors

**SDK-backed implementation: `azdata` 4.0.0a3, Python 3.11+. Ten service profiles, one interface. Offline-verified;
live Azure behavior is not yet verified.** Updated: 2026-09-15.

## Purpose And Reuse Direction

**One standardized data-service interface, tightly integrated with existing SDKs and
packages.** The goal is not another independent implementation of Azure's client libraries.
Keep `DataConnector`, its request/result types and lifecycle uniform; use maintained provider
clients, native models, pagers, conditions and ingestion mechanisms behind service adapters.

The [uv-managed library convention](../README.md) owns dependency management and release
execution. The [official-package research](research/README.md) supplies reuse candidates and
source evidence. **All ten profiles have implemented adapter paths.** Search, Cosmos, Blob
and Table use official async SDKs; SQL and PostgreSQL use native drivers; Gremlin uses
TinkerPop; Kusto reuses official request/result/ingestion models; GraphModel uses documented
Fabric REST APIs through Azure Core. The hand-written
provider URL/action builders, token cache and urllib/retry loop were removed. A small
[SDK boundary](src/azdata/sdk.py) retains bounded I/O, host checks, credential ownership and
the injectable HTTP test transport. Native database/WebSocket adapters enforce their own
protocol bounds behind the same public policy and result contract.

### What This Library Adds

The target responsibility split is more than renaming SDK methods:

| Existing Packages Provide | Our Standardized Layer Adds |
| --- | --- |
| Native clients, service protocols and typed request models | The same methods, request types, results and lifecycle for every connector; no provider-specific public escape hatch |
| Provider create, patch, replace, upsert and delete mechanisms | Precise common operation semantics, capability/guarantee checks and explicit refusal when a native operation cannot honor them |
| SDK exceptions, item acknowledgments and query responses | Ordered per-item outcomes, common error categories and honest partial, pending, unknown and unsupported results |
| Credentials, token policies and native conditional requests | Host-injected identity, trusted target binding, separate data/schema/infrastructure grants and policy checks before mutation; not a replacement for Azure or application authorization |
| Read APIs, ETags, ingestion receipts and operation pollers | Named read-back evidence for requested fields, versions, absence or batch identity; acceptance alone never becomes a persistence claim |
| Native paging, streaming and retries | Scoped continuation handling, result bounds and one coordinated retry/deadline budget without hidden unsafe mutation retries |
| Service examples and provider tests | Shared conformance tests plus service-specific and opt-in live cases proving that the same contract survives real differences |

The first pass already implements parts of this layer; [the implemented contract](CONTRACT.md)
states exactly which ones. Custom code is justified where it enforces a cross-service rule,
maps a real semantic difference, or fills a demonstrated gap that an upstream public API
cannot cover. It should not duplicate an SDK's transport, serializer, paging or provisioning
engine without a specific reason and acceptance test.

Tight integration means mapping standard requests to supported native operations, translating
native values without loss, preserving provider conditions and limits, and coordinating client
ownership and retries. It does not mean exposing raw SDK objects, hiding missing features in
`service_options`, or weakening guarantees to make every operation appear supported.

### Package Integration

Provider dependencies are optional extras, with exercised adapter consumers. `azure-core`
is the base dependency; installing the base performs no provider import, token acquisition
or network access. Install only the extras needed by the host.

| Provider Area | Implemented Dependency / Extra | Delivered Mapping |
| --- | --- | --- |
| Search | Implemented: `azure-search-documents`, extra `search` | Native document/index methods, conditions, query models, metadata and paging; public methods remain standardized |
| Cosmos NoSQL | Implemented: `azure-cosmos`, extra `cosmos` | Native item methods, partition inference, conditional replacement and paging; patch/merge and transactional batches remain deferred |
| Blob Storage | `azure-storage-blob`, extra `blobs` | Exact bytes, native non-overwrite/ETag conditions, prefix listing and SDK pagination |
| Table Storage | `azure-data-tables`, extra `tables` | Composite keys, typed entity values, merge/replace, conditions and OData pagination |
| ADX / Eventhouse | `azure-kusto-data`, `azure-kusto-ingest`, extra `kusto` | One shared KQL, streaming-ingestion and schema-read implementation; acceptance is not batch-content verification |
| SQL Database | `mssql-python`, `sqlglot`, extra `sql` | Bound keyed CRUD, transactional merge-upsert, parsed read queries and schema reads |
| PostgreSQL | `psycopg[binary]`, `sqlglot`, extra `postgresql` | Async native connections, read-only transactions, bound CRUD/merge-upsert and schema reads |
| Fabric GraphModel | Azure Core and `aiohttp`, extra `graph` | Beta GQL, definition reads, source refresh and signed/scoped job status |
| Cosmos Gremlin | `gremlinpython`, `aiohttp`, extra `gremlin` | GraphSON v2, parsed read traversals, partitioned vertex create/read/merge/delete; explicit resource-token prerequisite |

No provider SDK object is a public escape hatch. Kusto's public async client has no transport
injection for the required response cap, so its public models run over the existing guarded
Azure Core pipeline. Gremlin uses the driver's transport interface with aiohttp to refuse
redirects and bound frames. Neither path creates a second fallback implementation.

Gremlin has a material caveat: callers must supply scoped, expiring resource tokens from
their own secured authority. This library does not obtain keys or issue tokens, and does
not claim direct Entra traversal support. Microsoft recommends driver 3.4.x, whose Tornado
dependency fails on Python 3.11; the tested 3.7.7/GraphSON v2 path still needs live compatibility
verification. See [implementation evidence](research/IMPLEMENTATION.md).

## Current Implementation

The [implemented contract](CONTRACT.md) owns the actual API and current limits.
The reviewed design is retained below as the target architecture, not a claim that every
planned adapter, migration or guarantee is already delivered.

- One `DataConnector` class, ten identical async operation methods, `describe()`, `aclose()`
  and async context management for every registered service.
- Immutable request values, structured `OperationResult` values, explicit grants, trusted
  target/endpoint binding, bounded transport and named verification evidence.
- Registered profiles: `search`, `cosmos`, `blobs`, `tables`, `adx`, `eventhouse`, `graph`,
  `gremlin`, `sql`, `postgresql`. No import-time network or credential acquisition.
- Native query values stay service-specific; the request and result interfaces do not.
- `OperationResult.metadata` carries Search counts, facets and answers; captions remain
  structured per-document annotations. Metadata and records share the output byte budget.

The complete [operation matrix and configuration coordinates](CONTRACT.md) are authoritative.
Unsupported methods, modes and guarantees return standard results before I/O. Infrastructure
provisioning, cross-record transactions and automatic schema migration are not delivered.

The caller uses the same code for every profile; configuration and native query values differ:

```python
from azdata import Policy, QueryRequest, connect

async def query_data(service, config, credential, dialect, expression, parameters):
  async with connect(service, config, credential=credential, policy=Policy("host-authorized-user")) as data:
    result = await data.query(QueryRequest(
      dialect=dialect, expression=expression, parameters=parameters,
    ))
    return result.to_dict()
```

`Policy.principal` records host-established authorization; it does not authenticate a user.
The local [CyberEye template](../../template_apps/README.md) now uses this package for its
scanner/evidence/tool ADX transport through an application-owned synchronous adapter.
Successful live parity is pending because the borrowed cluster is stopped; the source project,
other application data paths, skills and MCP tools remain unchanged. The package uses the same
import name as legacy `azdata` 3.x but is **not API-compatible**; the template has its own
environment and explicit dependency rather than relying on import order.

### Development And Verification With uv

Follow the [workspace setup, commands and release sequence](../README.md). This package is
an independently installable/versioned member, initially the explicit `azdata` member of a
non-package workspace. The shared resolution and development environment belong to
`libraries/`, not to another code-bearing distribution. Select `--all-extras`
for the full offline suite. Base installation supports values, description, policy/refusal
checks and explicit `missing_dependency_<service>` results; it does
not silently install providers or use the superseded REST implementation.

- Declare dependencies in this member's [package metadata](pyproject.toml): required runtime
  imports in `project.dependencies`, implemented provider integrations in optional extras,
  and test/lint tools in development groups. Declare directly imported support packages too.
- Keep compatible published version requirements separate from the shared development lock.
  Optional dependencies must not pull every Azure SDK or database driver into a base install.
- Use the guide's `uv lock --check`, locked sync/run and explicit extras/groups. Dependency
  changes use `uv add --package azdata ...` with coordinated metadata/lock review. Do not
  use `--frozen` as a freshness check.
- One writer owns workspace resolution and sync. Concurrent workers need isolated environments
  or worktrees; sharing a directory does not create an access-library dependency or permit
  concurrent changes to the same lockfile/environment.
- Retain setuptools and Python 3.11+ unless a separately reviewed compatibility need changes
  them. Build wheel and sdist with the guide's `uv build --no-sources --package azdata` flow,
  rebuild from sdist and test artifacts outside the workspace without editable siblings or
  `PYTHONPATH`. Test the base, implemented extras and supported dependency bounds explicitly.

The existing offline suite is [under tests](tests); its contract, adapter and synthetic
integration checks must run through the selected member environment. The parent guide owns
the command sequence rather than a competing source-path installation recipe here.

The suite covers uniform signatures/refusals, target and policy boundaries, create conflicts,
merge/replace semantics, partial/uncertain outcomes, pagination, token refresh, transport
bounds, destructive confirmations, typed values and read-back. Shared conformance covers all
ten profiles. Storage/Search/Cosmos tests use real SDK serialization and paging over fake HTTP;
Kusto tests use official response models; Gremlin includes real protocol/auth serialization;
SQL/PostgreSQL tests validate calls to native driver APIs with synthetic connections. The
stateful Search/Cosmos consumer remains an additional integration fixture. Live acceptance remains separate.
No Azure resources, accounts or application data are used by the offline suite.

The locked all-extras source suite passes **126 tests** on Python 3.11.14 with uv 0.9.30.
[Verification evidence](VERIFICATION.md) records dependency versions, artifact checks and
unverified environments. Upstream generated-code warnings do not fail the suite.

### Historical a2 Footprint

For `4.0.0a2` on 2026-09-15, all **75 offline tests** passed with the locked dependency set and the
declared minimum combination. Wheel and sdist builds passed; a wheel rebuilt from the sdist
passed the same suite in a clean environment outside the checkout. Its runtime source bytes
matched the a2 source snapshot. A separate base-wheel environment verified both missing-extra paths
without provider SDKs, aiohttp, token acquisition or network I/O.

Compared with first-pass commit `59c421f`, newline-counted Python source changed as follows:

| Scope | Before | After | Net |
| --- | --- | --- | --- |
| Runtime source | 1,541 lines | 1,621 lines | +80 lines |
| Tests | 950 lines | 1,035 lines | +85 lines |

These counts exclude documentation, lockfiles, dependencies and generated environments.
**That increment was not a net source-size reduction.** It removed handwritten provider
plumbing but adds the SDK safety bridge, query metadata and regression coverage. Dependencies
are not vendored; their installation still has a footprint. Later consolidation should remove
genuine duplicate implementations, not security checks or evidence to reach a line-count goal.

Consumers install ordinary versioned Python artifacts and can use pip; uv and the workspace
lockfile are not runtime requirements or imposed consumer resolutions. External publication
and registry verification are separate authorized steps. Do not install legacy `azdata` 3.x
beside this package in one environment or mistake import order for compatibility.

### Live-Test Convention

`tests/live_tests/` contains [the numbered live-test design](tests/live_tests/LIVE_TEST_DESIGN.md),
with service-specific CRUD, refusal, verification and cleanup cases. It contains no executable
live tests or fixtures yet. Service provisioning and live execution remain separately
authorized steps; no live-test command runs as part of the offline suite.

The dedicated resource group was created and observed empty on 2026-09-14. Its non-secret targets,
operator commands and dated read-back evidence live in the [deployment runbook](../../deploy/README.md).
Future live tests must use that target authority, call the library for data operations, and
use synthetic, per-run-owned fixtures. Service provisioning, data-plane access, sample-data
loading and the live CRUD suite are not delivered by resource-group creation.

### What Remains

- Live identity, native service behavior, network policy and permission verification.
- Infrastructure provisioning, queued ingestion with batch-specific content evidence,
  durable operation references, and broader schema mutation support.
- Nested projections and supported service-specific modes identified
  in [the current limitations](CONTRACT.md#limits-and-deferred-work).
- Full SDK parity, endpoint-wide breaker coordination, broader Python/platform compatibility and migration
  of the existing skills and application callers. This first pass does not claim deduplication
  of the old implementations is complete.

[Official SDK and project research](research/README.md) maps these gaps to reusable provider
capabilities, adoption priorities, evidence and licensing considerations. It records the
research baseline; current implementation status is above, not inferred from that history.

## Retained Design

The sections below preserve the reviewed design and its considerations. Proposed coverage
and acceptance gates not listed as implemented above remain future work.
The package-reuse direction and uv convention above supersede earlier assumptions that
independent hand-written clients or source-path execution are the long-term approach.

## 1. Decision

One public connector interface for every registered Azure data-service adapter:

**Same methods. Same request types. Same result type. Same lifecycle.**

Service differences appear as validated request values, declared capabilities, guarantees,
limits, outcomes and caveats. They never require a different method signature, a missing
method, a provider SDK object, or an `as_search()` escape hatch.

An adapter unable to perform an operation returns a standard `unsupported` result before
mutating anything. An adapter unable to meet a required guarantee also refuses before
mutation. It must not approximate that guarantee and attach a warning afterwards.

This is the first proposed library capability in [the library-family design](../DESIGN.md),
replacing the earlier event-stream pilot. It consolidates runtime behavior currently owned
by [azure-data-connectors](../../.github/skills/azure-data-connectors/SKILL.md) and
[azure-search](../../.github/skills/azure-search/SKILL.md). Skills become instructional and
tool adapters around the canonical library; application consumers use that same library.

Uniform interaction does **not** imply uniform provider semantics, universal Azure coverage,
identical schemas, distributed transactions or exactly-once execution.

## 2. Scope And Non-Goals

The first implementation target is Azure AI Search. Cosmos DB NoSQL is the second contract
check, so the common interface is not accidentally a Search wrapper. Existing Gremlin,
Kusto, Blob and Fabric GraphModel mechanisms are subsequent adapter candidates.

Every implemented adapter exposes the entire interface, including operations it cannot
perform. An unimplemented service is not an adapter with fictitious coverage: the factory
rejects an unregistered service identifier explicitly.

In scope for the design:

- Standardized CRUD, query, ingestion, schema administration and provisioning interaction.
- One shared request/result model, policy enforcement, lifecycle and conformance suite.
- Service-specific translation, native query syntax, consistency and concurrency semantics.
- Consolidation of the two existing Search implementations and their real consumers.
- Packaging that works independently of skills and the investigation template.

Not implied or authorized:

- Implementing every Azure service in the first release.
- A universal query language or translating arbitrary queries between services.
- Automatic schema migration, resource creation, credential discovery or access grants.
- Cross-service joins, transaction coordination, a durable job scheduler or a new ORM.
- Automatic read-modify-write emulation, blanket retries or exactly-once claims.
- Moving application datasets, prompts, identities, domain schemas or target configuration.
- Deleting skills, replacing application code, changing public MCP tools or running cloud calls
  while this document is being reviewed.

## 3. Existing Mechanisms To Reuse

The abstraction has an existing starting point, not a blank implementation surface.

| Existing Owner                                                                                      | What To Preserve Or Reconcile                                                                                                                                              |
| --------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [Shared CRUD and ingestion core](../../.github/skills/azure-data-connectors/src/azdata/core/crud.py) | Write/delete grants, batching, breaker/gate integration and bounded verification. Replace JSON-string return values with the common structured result at the new boundary. |
| [Search document adapter](../../.github/skills/azure-data-connectors/src/azdata/search/write.py)     | Lazy SDK construction, blocking-call isolation, document result normalization and read-back behavior. Its current create pre-check is explicitly non-atomic.               |
| [Search index/document client](../../.github/skills/azure-search/python/azure_search/client.py)      | Index management, document actions, per-document failures, semantic/vector query construction and injected transport.                                                      |
| [Search schema definitions](../../.github/skills/azure-search/python/azure_search/schema.py)         | Field, index, vector and semantic configuration validation. These are service-specific values behind the standard schema request.                                          |
| [Cosmos item adapter](../../.github/skills/azure-data-connectors/src/azdata/cosmos/write.py)         | Partition-aware addressing, item operations and service failure handling.                                                                                                  |
| [Gremlin element adapter](../../.github/skills/azure-data-connectors/src/azdata/gremlin/write.py)    | Escaped traversal construction and graph-specific addressing. Validate concurrency guarantees independently.                                                               |
| [Blob adapter](../../.github/skills/azure-data-connectors/src/azdata/blobs/write.py)                 | Object addressing, byte payloads and conditional object operations.                                                                                                        |
| [Kusto ingestion adapter](../../.github/skills/azure-data-connectors/src/azdata/kusto/write.py)      | Append-oriented ingestion, accepted-versus-visible state and explicitly limited evidence.                                                                                  |

Existing behavior is evidence to compare, not a contract automatically inherited by the
new interface. For example:

- The current CRUD base describes upload as replacement; Search's implementation uses
  merge-or-upload. The new contract must distinguish those modes.
- The current shared verification checks key presence or absence. Presence alone cannot
  establish that an update stored the requested values.
- The current shared batch result can report success while carrying failed items. The new
  aggregate status must make partial completion explicit and retain every known outcome.
- Kusto already has a narrower internal ingestion abstraction. Keep that truthful mechanism
  internally while exposing the same public methods as every other connector.

Before migration, rerun the selected source owners' tests and freeze the relevant files.
No live Azure behavior or drop-in API compatibility was established by preparing this design.

## 4. Proposed Package Structure

The existing import name `azdata` is preferred where practical. Distribution name, version
transition and public namespace availability require a release decision before publishing.

```text
libraries/azure-data-connectors/
  README.md                         # This design during review
  CONTRACT.md                       # Approved public contract, created later
  pyproject.toml
  src/azdata/
    __init__.py                     # connect(), connector and public value types
    connector.py                    # Fixed facade and allowlisted adapter selection
    contracts.py                    # Requests, results, capabilities and guarantees
    policy.py                       # Data/schema/infrastructure authorization policy
    execution.py                    # Validation, bounds and execution/result handling
    adapters/
      base.py                       # Private adapter contract and unsupported handling
      search/
      cosmos/
      gremlin/
      kusto/
      blobs/
      fabric_graph/
  tests/
    contract/                       # Same suite for every adapter
    adapters/                       # Native behavior, failure and mapping tests
    integration/                    # Synthetic consumer and package checks, offline
    live_tests/                     # Numbered design only; executable live tests are deferred
```

This is an ownership sketch, not an instruction to create empty modules. Split a contracts
file or adapter directory only when its implemented responsibilities justify that split.

One Python package with optional service dependencies is the initial recommendation. Do not
make basic imports install all Azure SDKs, framework dependencies or the entire skills tree.
Default to existing provider SDKs and maintained packages, integrated through the common
facade and contract. Keep custom native mechanics only for a demonstrated gap; the current
REST implementations are a migration baseline, not a requirement to maintain parallel stacks.
Dependency ownership, shared uv resolution and independent artifact verification follow
[the library workspace convention](../README.md).

During review this README owns the design. On implementation, the stable public contract
can move to `CONTRACT.md`; this README should link to it rather than maintain a second copy.

## 5. Public Interface

The following signatures are proposed API notation, not runnable or installed code.

| Method           | Signature                                                                            | Shared Meaning                                                                                                                    |
| ---------------- | ------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------- |
| Factory          | `connect(service, config, *, credential, policy, transport=None) -> DataConnector` | Construct a connector for an allowlisted service and trusted target configuration; no network I/O.                                |
| Description      | `describe() -> ConnectorDescription`                                               | Report implemented capabilities, operation requirements, configured bounds and caveats; no credential acquisition or network I/O. |
| Create           | `async create(request: CreateRequest) -> OperationResult`                          | Insert addressed records without overwriting existing ones.                                                                       |
| Read             | `async read(request: ReadRequest) -> OperationResult`                              | Retrieve addressed records.                                                                                                       |
| Update           | `async update(request: UpdateRequest) -> OperationResult`                          | Modify existing records using an explicit merge or replace mode.                                                                  |
| Upsert           | `async upsert(request: UpsertRequest) -> OperationResult`                          | Insert or modify records using an explicit merge or replace mode.                                                                 |
| Delete           | `async delete(request: DeleteRequest) -> OperationResult`                          | Delete addressed records with explicit missing-record behavior.                                                                   |
| Query            | `async query(request: QueryRequest) -> OperationResult`                            | Execute a bounded native read query.                                                                                              |
| Ingest           | `async ingest(request: IngestRequest) -> OperationResult`                          | Submit bounded append/bulk-ingestion input.                                                                                       |
| Schema           | `async schema(request: SchemaRequest) -> OperationResult`                          | List, read, create, update or delete logical schemas/indexes.                                                                     |
| Provision        | `async provision(request: ProvisionRequest) -> OperationResult`                    | Plan, read, create, update or delete explicitly targeted infrastructure.                                                          |
| Operation status | `async status(request: StatusRequest) -> OperationResult`                          | Inspect a previous operation using a bounded operation reference; never re-execute it.                                            |
| Close            | `async aclose() -> None`                                                           | Idempotently release owned local clients and transports.                                                                          |

`status` is one proposed addition to the previously discussed verbs. It provides a uniform
follow-up for asynchronous ingestion/provisioning and uncertain outcomes. Without it, callers
would need service-specific polling outside the common interface. It also exists on adapters
without provider-side status support and returns `unsupported` there. This addition is a
specific review decision, not an already implemented feature.

All connectors support the same async context-manager lifecycle. The initial API is
async-first; synchronous SDK calls are isolated behind the adapter without blocking the
caller event loop. A sync facade is deferred. Do not hide `asyncio.run()` inside library
methods or change an operation's sync/async behavior according to service selection.

`describe` and lifecycle methods have their fixed control-plane return types. Every data,
schema, infrastructure and status operation returns the same `OperationResult` type.

Factory configuration errors are a common `ConfigurationError`: no connector exists yet
to return an operation result. Once constructed, expected operational errors and refusals
use the standard result. Cancellation, process termination and programming defects are not
disguised as ordinary provider failures.

## 6. Standard Request Model

Each operation has one request type shared by all services. The type selects the operation;
the common fields and address/content values have the same structure everywhere.

### Common Fields

| Field               | Purpose And Boundary                                                                                                                          |
| ------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| `request_id`      | Caller correlation identifier. Not a promise of deduplication or exactly-once execution.                                                      |
| `target`          | A standard`ResourceAddress` resolved within the connector's trusted configured scope. Not an arbitrary URL or SDK handle.                   |
| `limits`          | Deadline, input/output bytes, item/page bounds and permitted attempt budget. A request may narrow but never raise operator ceilings.          |
| `requirements`    | Required guarantees, such as create-if-absent, conditional version or atomic batch behavior. Unsupported requirements refuse before mutation. |
| `verification`    | Required evidence kind and bounded read-back deadline. Cannot weaken the connector's configured minimum.                                      |
| `service_options` | A standard namespaced data field for declared provider options. Validated by the selected adapter; unknown or reserved fields refuse.         |

Absent requirements do not weaken the operation's basic meaning. For example, `create`
never gains permission to overwrite because the caller omitted a guarantees object.

### Addressing And Data

- `ResourceAddress` contains an immutable mapping of named resource coordinates, resolved
  against trusted connector configuration. Names differ by provider, such as index or
  database/container; the enclosing type, validation path and authorization rules do not.
- `RecordKey` contains named scalar key parts plus an explicit partition value when needed.
  Composite and partitioned keys are not squeezed into an undocumented string format.
- Conditional version/ETag tokens are opaque values in the standard per-item precondition
  field. They are neither parsed nor synthesized by generic callers.
- `RecordInput` combines a key, a content value and optional preconditions. `ContentValue`
  distinguishes JSON/document content, tabular values and bytes with an explicit media type.
- JSON records retain field types. Tabular output retains column metadata. Blob bytes remain
  bytes in Python. Do not convert unsupported provider objects using `str()` and call that
  normalized data.
- The adapter advertises supported content forms and required coordinate/key fields through
  `describe`. Different schemas are data differences, not a second interaction interface.

Version 1 is bounded request/response access, not an unlimited stream or bulk-export API.
Large payloads use pages or explicit ingestion chunks. A future streaming interface must
also be uniform; do not bolt a provider-only public iterator onto one connector.

### Operation-Specific Fields

| Request              | Additional Standard Fields                                                                                         |
| -------------------- | ------------------------------------------------------------------------------------------------------------------ |
| `CreateRequest`    | Ordered records; per-item preconditions only where compatible with create semantics.                               |
| `ReadRequest`      | Ordered keys, optional field projection and missing-record policy.                                                 |
| `UpdateRequest`    | Ordered records, required`mode=merge\|replace`, optional expected versions.                                       |
| `UpsertRequest`    | Ordered records and required`mode=merge\|replace`; incompatible preconditions refuse.                             |
| `DeleteRequest`    | Ordered keys,`missing=ok\|error`, optional expected versions.                                                     |
| `QueryRequest`     | Native dialect, expression, separate parameters, optional projection and continuation.                             |
| `IngestRequest`    | Ordered input, declared format/mapping and optional provider-supported idempotency key.                            |
| `SchemaRequest`    | Fixed action enum, definition for changes, version precondition and destructive-change confirmation when required. |
| `ProvisionRequest` | Fixed action enum, desired resource specification, preconditions and exact-target confirmation when required.      |
| `StatusRequest`    | Operation reference issued for the same service, target and authorized caller scope.                               |

No request carries credentials, a policy object, a connection string, Python import path,
callback source or a request to disable authorization. `service_options` cannot override
those fields, the operation, target binding, verification minimum or read-only guard.

One request type does not mean every value is valid for every adapter. Unsupported dialects,
key forms, content forms or operation modes are reported through the same structured result.

## 7. Precise Operation Semantics

### CRUD

| Operation           | Required Meaning                                                                                               | Not An Acceptable Substitution                                                           |
| ------------------- | -------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------- |
| `create`          | Add a new addressed record; an existing identity produces conflict and is not overwritten.                     | Read for absence, then upsert across a race.                                             |
| `read`            | Return the addressed state or an explicit not-found outcome.                                                   | Treat forbidden or unreachable as an empty result.                                       |
| `update(merge)`   | Modify supplied fields on an existing record; other fields remain according to the declared field-merge rules. | Create a missing record, or silently replace unspecified fields.                         |
| `update(replace)` | Replace the writable representation of an existing record, preserving only documented server-owned fields.     | Upsert a missing record or pretend partial merge is replacement.                         |
| `upsert(merge)`   | Create when missing; otherwise merge supplied fields.                                                          | Full replacement disguised as merge.                                                     |
| `upsert(replace)` | Create when missing; otherwise replace the writable representation.                                            | Retain omitted writable fields without declaring that the requested mode is unsupported. |
| `delete`          | Remove addressed state under the specified missing/version policy.                                             | Claim a deleted key proves a predicate-wide purge or historical hard deletion.           |

Merge is explicit field-level behavior, not an invented recursive merge algorithm. The
adapter documents null handling, nested objects, arrays, immutable keys and server-computed
fields. A request requiring unsupported merge behavior refuses rather than guessing.

Atomicity is per item unless a batch guarantee is explicitly supported and requested.
Chunking is not a transaction. When earlier chunks have applied, a later failure must retain
those outcomes. No automatic rollback can be promised across independent provider calls.

### Search Create Semantics

The existing Search adapter checks whether keys exist and then uploads. Another writer can
insert between those operations. That is not atomic create-if-absent.

Under this design, Search `create` returns `unsupported` if its native document API cannot
guarantee non-overwrite. The method still exists. A caller may deliberately choose `upsert`,
but the library never makes that choice for it. Version 1 should not expose a best-effort
create emulation whose name violates the common contract.

Likewise, update-only replacement cannot be implemented by unconditionally uploading a
document if upload would create a missing key. Verify supported native conditions before
advertising the corresponding mode.

### Query And Pagination

`query` has one request/result shape, but expressions stay native: KQL, SQL, Gremlin,
Fabric GQL or Search expressions with semantic/vector options. A native dialect enum and
adapter-validated options do not create a universal query language.

Parameters are passed through provider parameter mechanisms where supported. Reject a
parameter form that cannot be bound safely; never make a universal string-interpolation
fallback. Read queries cannot carry schema commands or mutations. Guard the actual dialect
and rely on appropriately scoped data-plane credentials; a regex alone is not a general
SQL, KQL or traversal authorization boundary.

Continuation is one opaque token type bound to service, target, query identity, projection
and relevant policy context. Validate it before resuming. It does not authorize another
target or guarantee a stable snapshot unless the provider explicitly supports one.
Pagination limits and local truncation are distinct: a truncated result without a reliable
continuation must say it cannot be resumed. Do not silently return the first page as complete.

### Ingestion

`ingest` means append/bulk submission, not update or keyed upsert. Kusto may have no stable
row identity usable for ordinary record CRUD. Its public CRUD methods still exist and
refuse unsupported semantics; ingestion and native query remain usable through the same API.

Accepted ingestion is not necessarily queryable data. Report provider acknowledgment,
pending visibility, operation identity and evidence separately. Retrying an append can
duplicate rows; request IDs alone do not prevent that.

An observed whole-table count delta is weak evidence under concurrent ingestion and cannot
prove which batch arrived. Prefer provider-supported batch identity, tagged extents or
equivalent scoped evidence when available. If the requested evidence cannot be established,
return a bounded pending/unknown outcome, not an invented verified result.

### Schema And Infrastructure

Logical schema/index administration and infrastructure provisioning share the public facade,
not permissions or destructive semantics.

- Search index administration operates on the Search service endpoint; it must not be
  described as an ARM operation merely because it is administrative.
- Schema actions are `list`, `read`, `create`, `update`, `delete`; native differences are
  validated definitions, conditions and explicit unsupported results.
- Provision actions are `plan`, `read`, `create`, `update`, `delete`. A plan grants nothing
  and must state whether it used a live observation or only a supplied snapshot.
- Changes requiring rebuild, data migration or destructive replacement are reported and
  refused by default. No automatic drop-and-recreate hidden behind `schema(update)`.
- Confirm destructive actions against the exact target and desired-change digest, not a
  reusable blanket `force` flag. A request cannot grant itself destructive authority.
- Read back changed definitions and relevant fields. A successful HTTP response or a
  provider provisioning label is insufficient evidence that the intended setting persisted.
- Resources created or destroyed have an explicit owned scope. No automatic subscription-wide
  discovery, role assignment, teardown or deployment-script generation follows construction.

### Pending Operations And Status

An operation reference is an opaque, scoped provider handle or library receipt identifying
what is already in progress. It is not a credential and is reauthorized on every use.

`status` never repeats the original write. If the provider has no durable handle, say so;
do not imply an in-memory task survives process restart. An ambiguous write may require
authorized read-back to reconcile. If neither status nor read-back can settle it, `unknown`
is a valid final observation, not permission to retry blindly.

Remote cancellation is not promised by `aclose` or task cancellation. A future cancel
operation, if needed, must be added uniformly and versioned rather than exposed by one adapter.

## 8. Standard Result And Failure Model

Every operation returns an `OperationResult` value, not a JSON string or provider SDK result.
CLI, HTTP and MCP adapters serialize it through one deliberate representation; library
consumers use its structured fields directly.

| Result Field                                                                 | Meaning                                                                                                                |
| ---------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| `contract_version`, `request_id`, `operation`, `service`, `target` | Stable identity and correlation, without credentials or secret-bearing endpoints.                                      |
| `status`                                                                   | Standard aggregate outcome from the table below.                                                                       |
| `items`                                                                    | Ordered item outcomes with input position, key, state, returned content, version and safe error detail as appropriate. |
| `errors`                                                                   | Structured categories/codes and safe diagnostics; not raw provider exception text.                                     |
| `verification`                                                             | Requested/achieved evidence, state, timestamps and bounded observations.                                               |
| `continuation`, `truncated`                                              | Page resumption and explicit incompleteness.                                                                           |
| `operation_ref`                                                            | Optional handle for status/read-back, with persistence limits.                                                         |
| `caveats`                                                                  | Machine-readable codes, scope and explanation of relevant limitations.                                                 |
| `metrics`                                                                  | Measured timings, attempts and provider-reported usage when available. Missing is unknown, never zero by invention.    |

| Status          | Meaning                                                                                                                                                        |
| --------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `success`     | All requested items meet the operation contract and required evidence level. Unrequested verification is explicitly`not_requested`, not implicitly verified. |
| `partial`     | Different item outcomes occurred; preserve all successes, failures, pending/unknown and unattempted items.                                                     |
| `pending`     | The provider accepted work that has not reached the required terminal/evidence state.                                                                          |
| `unknown`     | The outcome cannot currently be established, including a timeout after possible write acceptance.                                                              |
| `not_found`   | Addressed state is confirmed absent through an authorized lookup. An empty query is successful with no rows.                                                   |
| `conflict`    | Existing identity or version/precondition conflict prevented the requested change.                                                                             |
| `invalid`     | Request shape, bounds, target coordinates or values failed validation.                                                                                         |
| `denied`      | Operator/application policy or service permission refused the operation.                                                                                       |
| `unsupported` | The adapter cannot provide the operation, requested mode or required guarantee.                                                                                |
| `failed`      | A definite non-success not represented by the preceding categories; never a substitute for uncertain mutation state.                                           |

Empty input is a standard no-op result with no invented verification. For batches, preserve
input order and item indices, including repeated keys. Reject ambiguous duplicate mutations
by default unless an explicitly declared ordering contract handles them. An adapter returning
too few, too many or mismatched acknowledgments is a contract failure, not partial success
silently counted by response length.

If a transport fails after some work, do not replace accumulated item outcomes with one
generic error. Distinguish applied/accepted, refused, unknown and not-attempted items. Retrying
the successful part of a partial batch must require an explicit safe policy, not happen
because the aggregate result was not `success`.

Known validation/provider failures normalize at the facade boundary. Do not swallow
`CancelledError`, `KeyboardInterrupt` or `SystemExit`. Task cancellation still propagates;
mutation may already have occurred, so retain any known operation reference in the host's
execution record and make no rollback claim. Unexpected programming errors remain diagnosable
and must not leak request payloads through logging.

## 9. Capabilities, Guarantees And Caveats

`describe` lists every public operation for every connector, even when unsupported. Each
entry declares:

- Support: `supported`, `conditional` or `unsupported`, with a reason code.
- Supported modes, formats, dialects, schema/provision actions and required address fields.
- Available guarantees and conditions: per-item/batch atomicity, create-if-absent, conditional
  version support, merge semantics, supported idempotency and read-after-write behavior.
- Verification kinds actually implementable, with limitations and prerequisites.
- Provider/configuration bounds and any narrower library policy ceilings.
- Relevant configuration/dependency state, without making a live reachability claim.

Three different facts remain separate: **implemented support**, **granted authority**, and
**observed availability**. A supported operation may be denied; a permitted service may be
unreachable. Description must not acquire credentials to guess either fact.

Capabilities can be conditional on configured provider version, resource schema or service
tier. Unknown conditions remain unknown until explicitly inspected through the authorized
interface. Requested guarantees that are not established cannot be advertised as satisfied.

The execution result records guarantees actually achieved, not a copy of the adapter's
maximum advertised capabilities. Caveats describe real limitations; they never turn a failed
requirement into success. Generic callers can inspect these fields without checking the
connector class or branching to a different SDK.

## 10. Common Execution And Security Boundaries

### Responsibility Split

| Layer            | Owns                                                                                                          | Must Not Own                                                    |
| ---------------- | ------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------- |
| Host composition | Trusted configuration, credentials, caller identity, authorization policy, target ownership and lifecycle.    | Duplicate provider CRUD rules.                                  |
| Public connector | Fixed signatures, common validation, target/policy checks, capability requirements and normalized results.    | Application knowledge or provider-specific public methods.      |
| Shared execution | Bounded execution, declared retry/verification policy, correlation and partial-result accounting.             | One universal retry algorithm that overrides service semantics. |
| Service adapter  | Native addressing, request translation, SDK/transport behavior, supported guarantees and evidence production. | Bypassing public policy or changing the result shape.           |

Adapters are trusted, allowlisted library code. The factory may start as a small static
registry; configuration may select a service ID but cannot name a module, class or executable.
Prefer small composed operation handlers over forcing the private Kusto implementation to
pretend it supports keyed CRUD. Private design can vary; the public facade cannot.

### Policy

- Deny mutation by default. Read policy still restricts caller and resource scope; a read
  method is not anonymous authorization.
- Data creation/update/upsert/ingestion, data deletion, schema changes, infrastructure changes
  and destructive actions have explicit separate grants. Read-only administrative inspection
  does not inherit infrastructure mutation authority.
- Common validation, scope authorization and required-capability checks complete before any
  provider write. Refused operations cause no mutation and should need no credential call.
- Request limits and verification settings can only narrow operator policy. No per-request
  `verify=False`, provider option or retry override can weaken an enforced minimum.
- Library grants are defense in depth, not Azure RBAC or application record ownership. A
  multi-user host supplies a scoped caller/policy context; no mutable global current user.
- Do not cache a connector solely by resource name and silently reuse a different caller's
  policy. Bind immutable authorization/target context explicitly; transport pooling must not
  pool permission decisions.

### Identity And Endpoint Trust

- Inject Entra token credentials through a declared sync/async adapter contract. No account
  keys, connection strings, SAS tokens or automatic fallback to secret-based authentication.
- Configuration is read at the composition edge. No import-time environment scanning, SDK
  client creation, token acquisition or default tenant/subscription/resource selection.
- Endpoints, audiences and target scopes are trusted operator data. HTTPS syntax alone does
  not make an arbitrary host safe to receive a bearer token. Apply host/scope restrictions,
  validate redirects and refuse user-input routing to a different authority.
- Reverify each service's identity support and required roles during implementation. Existing
  skill prose is not proof of live Gremlin, Fabric, Search or control-plane authorization.
  Missing support is reported; it does not authorize fetching account keys.
- Own and close only credentials/clients created by the connector or explicitly transferred
  to it. Never close borrowed resources still used by another consumer.
- Refresh tokens for long-lived clients without exposing token values in results or logs.

### Bounds, Retry And Concurrency

- Validate finite positive deadlines, payload sizes, item limits, page limits and concurrency
  budgets. `bool`, negative limits and silently clamped unsafe settings are not valid numbers.
- Separate provider batch caps from caller requests. Bound bytes as well as item counts.
- Share appropriate per-endpoint throttling without letting one target's failure corrupt
  another caller's authorization state. Document breaker and gate scopes.
- Retry only when the adapter establishes that the operation and observed failure are safe
  to repeat. Bound combined SDK/library attempts; avoid nested exponential retry explosions.
- Handle provider throttling signals and retry hints within the total deadline. A service
  outage, auth refusal, conflict and rate limit are not interchangeable breaker events.
- Do not automatically retry a possibly applied create, append, conditional update or other
  non-idempotent operation. Reconcile outcome or return `unknown`.
- Thread offloading does not stop the underlying SDK call on cancellation. Bound transport
  timeouts, retain pending state honestly and do not pretend a cancelled task reversed a write.
- Closing is idempotent and releases owned local resources; it does not implicitly delete
  cloud resources, flush queued work, cancel durable provider jobs or create new operations.
- Calls after close use a common `connector_closed` failure without network activity.

### Diagnostics

Results and telemetry expose bounded codes, identifiers, counters and timing, not credentials,
prompts, records, native query values or raw exception bodies by default. Service request IDs
are useful; arbitrary SDK exception strings are not automatically safe. Allow explicit host
redaction/diagnostic policy without making sensitive logging the normal failure path.

## 11. Verification Means Named Evidence

Do not collapse every check into a boolean `verified`.

| Evidence Kind               | What It Establishes                                                             | What It Does Not Establish                                                 |
| --------------------------- | ------------------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| Provider acknowledgment     | The service reported accepting an item or operation.                            | Readability, correct stored values or eventual completion.                 |
| Presence                    | The addressed item was read back.                                               | That an update replaced the previous values.                               |
| Expected projection/version | Read-back matches the requested writable fields and/or provider version.        | Equality of non-retrievable or server-computed fields not inspected.       |
| Absence                     | Authorized addressed read-back confirms the required state is absent.           | Hard deletion of historical replicas, extents or backups.                  |
| Scoped ingestion evidence   | The identified ingestion batch reached the declared visibility/count condition. | Whole-service transactional or permanent exactly-once guarantees.          |
| Schema/resource state       | Read-back of named fields matches the requested definition.                     | Uninspected fields, effective access or reachability from another network. |

Verification state is `not_requested`, `pending`, `satisfied`, `failed` or `unknown`, together
with the requested and achieved evidence kind. A provider acceptance result with
`not_requested` must never be described to a user as verified persistence.

Adapters define comparison rules for server-normalized values, omitted fields, unordered
collections, projections and ETags. They must not compare whatever subset happens to be
readable and claim complete equality. For a Search field that cannot be retrieved, disclose
that value comparison is unavailable; a caller requiring it receives `unsupported` before
write, or must explicitly choose a weaker supported requirement before submitting.

Read-back itself is subject to scope, deadlines, throttling and authorization. If a host
grants write but not the required verification read, refuse the request before mutation when
that mismatch is known. An unexpected read-back denial after acceptance does not mean the
write failed to land; preserve the accepted/unknown distinction.

## 12. Adapter Coverage Plan

The table is a design mapping from existing mechanisms, **not a verified live capability
matrix**. Every listed adapter would expose all public methods. Actual supported modes and
guarantees must be recorded by its implementation and conformance evidence.

| Service                                 | Candidate Supported Behavior                                                                                                                  | Required Caveat Or Refusal                                                                                                                                          |
| --------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Azure AI Search                         | Document reads, native merge/update/upsert/delete, semantic/vector query, index administration; service provisioning only with its own grant. | No atomic document insert-if-absent advertised from a pre-read. Verify update-only/replace support, eventual visibility and field retrievability.                   |
| Cosmos DB NoSQL                         | Partition-addressed item CRUD/upsert/query and declared version conditions.                                                                   | Require partition identity; batch atomicity only within the provider-supported boundary. No inferred cross-partition transaction.                                   |
| Cosmos DB Gremlin                       | Graph reads and graph-specific element mutations through generated traversals.                                                                | Recheck authentication, partitioning and concurrent create/update semantics. Do not assume a traversal read-then-write is atomic.                                   |
| Azure Data Explorer / Fabric Eventhouse | KQL reads and bounded ingestion; explicitly supported schema/management behavior.                                                             | Ordinary keyed update/read/delete may be unsupported. Soft-delete and ingestion are not ordinary transactional CRUD. Whole-table count delta is not batch identity. |
| Azure Blob Storage                      | Object reads/writes/deletes and supported conditional operations.                                                                             | Byte payloads, object metadata and blob kinds matter. Merge-style document update and native query/schema operations may be unsupported.                            |
| Fabric GraphModel                       | Native GQL read behavior from the existing read adapter.                                                                                      | No write, schema or provisioning support inferred from read support. Those methods refuse until explicitly implemented.                                             |

Azure SQL, Table Storage, PostgreSQL and further services can be added under the same contract
after scoped requirements and provider semantics are established. Their mention here is not
a claim of implementation or permission to expand the initial delivery.

## 13. Consolidation And Consumer Migration

### Search First

The two current Search owners must become one maintained implementation, not two clients
behind a facade that leaves duplicate rules intact.

1. Inventory current exports, schema handling, queries, document actions, errors, identity
   behavior, retry policy and per-item results from both source owners.
2. Establish common values and the facade around the smallest useful Search workflow.
   Every public method exists from the first adapter; not-yet-delivered methods explicitly
   report unsupported without advertising future support as current capability.
3. Select canonical SDK/transport mechanisms using that parity comparison. Internal document,
   schema and infrastructure clients can differ where native endpoints differ, but each
   operation has one implementation owner. No duplicate complete Search client stack.
4. Preserve native query features and schema value types through validated standard request
   values. If an existing feature lacks a mapping, retain its consumer until the gap is closed.
5. Run the same contract against Cosmos before declaring version 1 stable; partition keys,
   conflicts and conditional writes expose assumptions Search alone cannot test.

### Applications, Skills And Compatibility

- The investigation template's Search and data-connector consumers are strategic adoption
  targets, not part of this documentation change. Inventory imports, scripts, build inputs
  and tests before assigning a migration batch.
- Applications retain domain schemas, query text, projection choice, target configuration,
  identity and authorization. They do not retain another generic connector implementation.
- Existing `azdata` APIs return JSON strings and use `upload`; the new structured result and
  explicit update/upsert semantics are not a drop-in change. Use an explicit version plan.
- Short-lived compatibility adapters may translate named old callers, including exception
  behavior, but must contain no independent provider rules. Name owners and removal criteria.
- Existing skill CLI and MCP interfaces remain unchanged until separately migrated and tested.
  Current read-only MCP registration does not gain mutation tools because the library has them.
- After both sets of consumers work, consolidate Search guidance into the data-connectors skill
  with focused schema/query/write references and old-name discovery where supported. Skill
  removal needs an explicit authorized set and native-discovery checks.
- The library imports neither `.github/skills` nor template internals. Skills import installed
  library APIs. Optional self-contained distributions bundle generated, pinned library artifacts
  with provenance and licences; no second hand-edited source copy.
- Update the existing capability catalogue, package manifests and ownership documentation in
  the same approved migration, distinguishing proposed from working support.
- The template is currently a local reference and may be ignored by Git. Its presence on this
  machine is not evidence a clean checkout includes it. Release checks use committed synthetic
  consumers and must not silently unignore or publish the template or its data.

## 14. Verification And Acceptance Plan

These are implementation gates, **not tests already run by preparing this document**.
Reuse existing test frameworks and fake-service fixtures. No live calls, credentials or
billable actions are needed for baseline interface conformance.

### Common Contract Suite

Run the same assertions against every registered adapter:

- Identical public methods, type signatures, await behavior and structured result fields.
- Every operation is described; unsupported operation/mode/guarantee returns `unsupported`
  without mutation or accidental SDK invocation. No missing methods or escaped
  `NotImplementedError`.
- Invalid bounds, targets, partitions, options and reserved overrides refuse deterministically.
- Read/write/delete/schema/provision grants remain separate; request input cannot widen them.
- Result normalization preserves types, ordering, all item outcomes and explicit pagination.
- Partial batches, missing acknowledgments, timeouts after acceptance, status handles and
  unknown outcomes never collapse into unconditional success or safe-to-retry assumptions.
- Verification proves the requested evidence, including stale pre-existing values after an
  update. Required verification cannot be bypassed by a request flag.
- Cancellation propagates; borrowed credentials remain open; owned clients close exactly once.
- Token refresh, throttling, attempt budgets and no-import-side-effect claims are exercised
  with injected clocks/transports and fake identities.
- No credentials, data values or raw SDK payloads appear in default result diagnostics/logs.
- Empty operations, duplicate keys, closing twice and operations after close have standard behavior.

### Adapter And Consumer Checks

- Search: create refusal prevents overwrite races; merge differs from replace; per-document
  failures survive 200/207 responses; mapping-like SDK values remain structured; indexing
  visibility and non-retrievable fields do not produce false verification.
- Cosmos: partition identity is mandatory where required; create conflicts, version conflicts
  and wrong-partition reads/deletes cannot look like verified success.
- Kusto: append retries do not imply deduplication; count changes from unrelated writers do
  not verify the submitted batch; unsupported keyed CRUD never submits a management command.
- Gremlin/Blob/Fabric: native mutations, conditions, literals, content types and semantic
  response codes have service-specific positive and refusing cases.
- Build an isolated wheel and test a synthetic consumer without sibling skills, the template,
  a local source checkout, a preinstalled full SDK set or network downloads hiding omissions.
- Verify real migrated application/tool call paths and read back affected persisted results.
  Interface tests alone do not prove the application works.
- When authorized, run narrowly scoped live checks for identity, permissions, service semantics,
  provisioning/read-back and cleanup. Fake providers do not establish those facts.

Each batch freezes its source set, names consumers and captures rollback evidence. Remove
only authorized superseded code after focused checks pass. A failing batch is repaired or
rolled back within its owned scope; it is not a reason to weaken auth or silently drop a feature.

Success means one public interaction surface, one maintained implementation per provider
operation, honest outcomes, migrated consumers and no loss of required capabilities. Fewer
skill directories is secondary evidence, not the proof of correctness.

## 15. Decisions For Review

Settled design direction from the discussion:

- This capability is first; source authority belongs under `libraries/azure-data-connectors`.
- Every service adapter exposes the same complete interface and standardized values.
- Separate create/update/upsert semantics; no silent approximation of unsupported guarantees.
- Native queries remain native within a fixed request/result envelope.
- Data, schema and infrastructure actions share a facade but have separate authority.
- Preserve differences through capabilities, explicit outcomes and caveats, not different APIs.

Recommended defaults still requiring implementation review:

| Decision               | Recommendation                                                                         | Reason                                                                         |
| ---------------------- | -------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| Execution model        | Async-first operations and one async lifecycle.                                        | Matches most existing adapters without changing behavior by service.           |
| Long-running follow-up | Add the uniform`status(StatusRequest)` method.                                       | Pending work otherwise forces provider-specific polling.                       |
| Search create          | Return unsupported when native non-overwrite cannot be guaranteed.                     | Maintains the meaning of create under concurrent writers.                      |
| Internal values        | Lightweight, runtime-validated structured values; serialize only at external adapters. | Keeps the public contract independent of JSON strings and SDK objects.         |
| First coverage         | Search integration, then Cosmos contract cross-check.                                  | Concrete reuse with two materially different service semantics.                |
| Search transport owner | Select after existing fake-service/SDK parity comparison.                              | The facade must not conceal duplicate complete implementations or regressions. |
| Compatibility          | Explicit version transition with temporary adapters only for named consumers.          | Structured results and upload semantics change existing APIs.                  |
| Verification defaults  | Preserve explicit policy minimums; always report evidence kind.                        | A single universal boolean would overstate what different stores can prove.    |
| Packaging              | One`azdata` package with optional service extras initially.                          | Avoids a package-per-file framework while preserving dependency isolation.     |

Remaining unknowns: external consumers, precise native conditional-operation support,
provider-version compatibility, supported identity paths, clean-build requirements, required
distribution notices, live authorization/consistency behavior and native skill alias behavior.
Resolve these per adapter and migration; do not claim universal Azure support to close them.

Reviewing or accepting this design does not itself authorize cloud mutation, data migration,
skill deletion or replacement of application implementations. Those are subsequent named steps.
