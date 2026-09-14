# Official Connector Reuse Research

**Research completed: 2026-09-14. Recommendation, not implementation.** No dependency
installation, cloud operation, live test or public API change was performed.

## Question

Which official service APIs, SDKs and maintained projects can fill the gaps in the
[current connector contract](../CONTRACT.md) while preserving one fixed public interface,
explicit policy, supported guarantees and honest read-back evidence?

## Recommendation

**Keep the public connector contract; reuse official clients behind it.** Most missing
provider operations have SDK implementations already. Their request signing, typed models,
native pagination and service-specific operation handling are better reuse targets than
another locally implemented REST stack. Our library still owns authorization, target binding,
cross-provider request/result normalization, unsupported guarantees and verification policy.

Recommended order:

1. Complete Search query results and paging using the official async client/pager contract.
2. Add Blob Storage and Table Storage adapters after expanding common address/content values.
3. Add precisely defined Cosmos patch-backed updates and same-partition transactional batches.
4. Add Kusto query/ingestion and administrative operation status, with batch-specific evidence.
5. Add SQL/PostgreSQL drivers and Fabric item/query/refresh adapters under their actual native
   connection and authorization models. Keep Gremlin blocked until the keyless path is proved.

This order optimizes verified coverage gained against interface and integration risk. It is
not a time estimate. No package was installed or exercised in this research, so SDK integration
and service behavior remain unverified.

## Evidence And Scope

The baseline is the [registered adapters](../src/azdata/connector.py),
[current limitations](../CONTRACT.md#limits-and-deferred-work), and
[104-case live-test design](../tests/live_tests/LIVE_TEST_DESIGN.md). Only Search and Cosmos
are currently registered. The matrix below covers all ten service profiles in that test plan;
Azure SDK availability does not make any of them installed, authorized or live verified.

Sources were acquired through [web-resource](../../../.github/skills/web-resource/SKILL.md)
with robots checks, per-host pacing, source URLs, UTC retrieval times and SHA-256 provenance.
All acquired artifacts passed the catalogue's existence and hash checks. Source pointers are
recorded in [sources.txt](sources.txt); exact retrieved metadata is in
[acquisitions.json](acquisitions.json).

Full third-party pages remain in an internal temporary reference cache, not in this repository.
This report contains original analysis, links and metadata, not vendored documentation or SDK
source. The cache is disposable; the source list permits reacquisition, which may retrieve newer
content. A matching URL alone does not reproduce the recorded bytes.

No ranked search provider was configured. The available DuckDuckGo Instant Answer fallback
is not a ranked research engine; direct official references were used instead. This is a
bounded primary-source review, not an exhaustive search of the Azure ecosystem.

## Service Reuse Matrix

| Service Profile | Verified Upstream Capability | What We Can Add | Contract And Safety Work Still Ours |
| --- | --- | --- | --- |
| Azure AI Search | `azure-search-documents`: async `SearchClient`, `AsyncSearchItemPaged`, document merge/upload methods | Native paging, count/facets/semantic answers, captions, typed vector options and reusable per-item result handling | Same `query()` and result type; add common metadata rather than public SDK methods. Preserve merge/replace distinctions and atomic-create refusal. |
| Cosmos DB NoSQL | `azure-cosmos`: async `ContainerProxy.patch_item`, `execute_item_batch`, native key/partition types and conditions | Partial document update, conditional operations, same-partition atomic batches, richer partition representations | Patch is not arbitrary JSON merge or merge-upsert. Define field/null/array semantics, partition scope and exact conditions before declaring support. |
| Azure Blob Storage | `azure-storage-blob`: async `BlobClient.upload_blob`, `download_blob`, conditional ETags and stream download | Binary object create/replace/read/delete, metadata, ranges, chunked reading and conditional writes | Common bytes/content model and bounds; enforce blob-kind semantics, exact versions, leases and version/soft-delete evidence. |
| Azure Table Storage | `azure-data-tables`: async `TableClient.create_entity`, `get_entity`, `update_entity`, `upsert_entity`, `delete_entity`, `submit_transaction` | One of the closest native fits for standardized CRUD: merge/replace, composite identity, ETags and entity batches | Represent PartitionKey/RowKey and native scalar types; enforce same-partition transaction limits and preserve all batch outcomes. |
| Azure Data Explorer | Official `azure-kusto-data` and `azure-kusto-ingest`, including async extras and queued/streaming ingestion | Native KQL, mappings, queued/streaming/managed-streaming ingestion and provider result/status mechanisms | Append is not keyed CRUD. Track batch identity, mapping and scoped visibility; never equate accepted submission or whole-table count growth with that batch's arrival. |
| Fabric Eventhouse | Kusto data/ingestion family plus official Fabric Eventhouse/KQL Database item APIs | Query/ingestion behind the same facade; workspace item creation and definition lifecycle through the administrative plane | Fabric workspace/capacity and permissions are distinct from an ARM group. Verify ADX and Eventhouse separately. |
| Fabric GraphModel | Official item creation/definition APIs, graph refresh job, beta `executeQuery` with pagination | `schema`/administrative item lifecycle, query and refresh/status capability | Graph-model lifecycle is not vertex/edge CRUD. Query API is beta; do not invent direct node mutation or treat OneLake refresh as `update(record)`. |
| Cosmos DB Gremlin | Microsoft quickstart uses `gremlinpython` and GraphSON v2 for vertices and edges | Reuse Apache TinkerPop transport/serialization if a compliant credential path is established | The concrete quickstart uses an account key. A generic managed-identity security paragraph does not establish traversal authentication. No key fallback is authorized. |
| Azure SQL Database | Microsoft `mssql-python`, DB-API 2.0, Entra authentication, query parameters and transactions | Official SQL driver behind the fixed CRUD/query surface; real transaction and version-aware implementations | TDS is not HTTP. Define schema/identifier binding, connection ownership, pool identity and cancellation; keep native binary requirements optional. |
| PostgreSQL Flexible Server | Microsoft quickstart recommends `psycopg`; upstream Psycopg 3 has async connections/cursors, transactions and identifier composition | Async relational CRUD/query, safe parameter/identifier handling and explicit transactions | PostgreSQL protocol/configuration must not be forced through an HTTPS origin. Define supported types, concurrency version strategy, token refresh and LGPL obligations. |

### Search: The Smallest High-Value Gap

The official [SearchClient reference](https://learn.microsoft.com/en-us/python/api/azure-search-documents/azure.search.documents.aio.searchclient?view=azure-python)
documents query count/facets, semantic answers/captions and numeric vector options. Its
[async pager](https://learn.microsoft.com/en-us/python/api/azure-search-documents/azure.search.documents.aio.asyncsearchitempaged?view=azure-python)
exposes `by_page(continuation_token=...)`, `get_count()`, `get_facets()` and `get_answers()`.
The [SDK project README](https://github.com/Azure/azure-sdk-for-python/tree/main/sdk/search/azure-search-documents)
provides canonical examples and testable client behavior.

The current wrapper explicitly refuses this metadata and implements offset-based continuation.
Recommendation: add a uniform optional query metadata field and preserve native paging behind
our scoped continuation reference. Captions and scores remain result data, not extra public
methods. Native continuation does not itself promise snapshot consistency, permanence or
authorization; keep query/target/principal binding and result-byte limits.

`merge_documents` updates existing documents; `merge_or_upload_documents` is merge-upsert;
`upload_documents` is full replacement/upsert. No inspected source supplied an atomic document
create-if-absent. Keep that refusal and do not label an SDK method called upload as create.
Service acknowledgment and requested-field verification remain separate checks.

### Cosmos: Useful Native Operations, Different Guarantees

The official [async container reference](https://learn.microsoft.com/en-us/python/api/azure-cosmos/azure.cosmos.aio.containerproxy?view=azure-python)
documents patch operations with a filter predicate and conditional arguments, and
`execute_item_batch` with one explicit partition key. Its key types distinguish null/missing
representations and sequences for hierarchical keys. The
[project README](https://github.com/Azure/azure-sdk-for-python/tree/main/sdk/cosmos/azure-cosmos)
documents transaction rollback within a partition and explicitly distinguishes transactional
batch from general bulk execution.

Recommended additions:

- Map a precisely documented `update(merge)` subset to native patch operations; test null,
  nested objects, array replacement, missing keys and immutable partition fields.
- Advertise `atomic_batch` only for compatible operations inside a supported partition and
  within the pinned SDK/service limits. Multiple partitions are not one transaction.
- Expand `RecordKey.partition` with explicit unspecified/null/scalar/hierarchical variants;
  `None` cannot simultaneously mean missing partition and a real null partition.
- Preserve session/version/result evidence rather than manufacturing it from SDK success.

Native patch does not directly solve `upsert(merge)`: patch-existing plus create-missing is
a multi-step algorithm with races. It needs an explicit concurrency contract or must remain
unsupported. Do not use a native stored procedure as an unreviewed workaround.

The SDK's `retry_write` option explicitly tolerates a risk of duplicated/non-idempotent
effects. Leave unsafe write retries disabled; pin SDK defaults and total retry budgets so a
SDK migration cannot bypass the facade's one-submission/unknown-outcome behavior.

### Blob And Tables: Strong Next Adapters

[BlobClient](https://learn.microsoft.com/en-us/python/api/azure-storage-blob/azure.storage.blob.aio.blobclient?view=azure-python)
provides overwrite controls, ETag/match conditions, range downloads and a downloader with
`readinto`/`chunks`. Reuse it for block-blob bytes and conditions; do not pretend a JSON merge
is meaningful for arbitrary bytes. Native chunking removes transport work but still needs
our aggregate bounds, cancellation behavior and exact byte-digest read-back.

[TableClient](https://learn.microsoft.com/en-us/python/api/azure-data-tables/azure.data.tables.aio.tableclient?view=azure-python)
already has entity create/read/update/upsert/delete, merge/replace modes, conditions and
`submit_transaction`. This is a good second shape test for the generic model: two named key
parts, native values, property removal and partition-local batches expose assumptions that
Search's single string key does not.

Do not import SDK `EntityProperty`, enum or pager objects into the public contract. Translate
them into common address, content, version and outcome values. A SDK or emulator pass cannot
prove actual cloud RBAC, soft-delete behavior or region/network support.

### Kusto And Eventhouse: Reuse Ingestion, Do Not Invent CRUD

Microsoft's [Kusto Python SDK documentation](https://learn.microsoft.com/en-us/kusto/api/python/kusto-python-client-library?view=microsoft-fabric)
names data, ingest and management clients. The
[official project](https://github.com/Azure/azure-kusto-python) has async extras and examples;
the [ingestion sample](https://github.com/Azure/azure-kusto-python/blob/master/azure-kusto-ingest/tests/sample.py)
shows `QueuedIngestClient`, `KustoStreamingIngestClient`, `ManagedStreamingIngestClient`,
ingestion properties and managed-identity connection builders.

Reuse query/mapping/ingestion machinery and status observation. Host-owned token configuration
must replace example secret/password setup. Some project prose still names old ADAL/user-secret
flows; official origin does not make every sample an approved security pattern.

Queued ingestion can outlive the request. Persist the operation/batch identity and mapping,
then verify that specific batch with bounded native reads. Counts alone are insufficient under
concurrent ingestion. Record deduplication windows; request IDs do not provide permanent
exactly-once delivery. Keeping keyed create/update/upsert/delete unsupported can remain correct.

For Fabric, the [Eventhouse API](https://learn.microsoft.com/en-us/rest/api/fabric/eventhouse/items/create-eventhouse)
and [KQL Database API](https://learn.microsoft.com/en-us/rest/api/fabric/kqldatabase/items/create-kql-database)
document item creation, supported capacity requirements, and user/service-principal/managed-
identity support. Use Kusto-compatible data APIs for query/ingestion and Fabric APIs for item
lifecycle; their ownership, token audiences and result/status mechanisms differ.

### Fabric Graph: More Administrative Capability Than The Initial Plan Assumed

The official [GraphModel catalogue](https://learn.microsoft.com/en-us/rest/api/fabric/toc.json)
lists create/read/update/delete item and definition operations, query and refresh jobs.
Inspected concrete references:

- [Create Graph Model](https://learn.microsoft.com/en-us/rest/api/fabric/graphmodel/items/create-graph-model)
  supports user, service-principal and managed identities, subject to workspace role/scope and capacity.
- [Execute Query](https://learn.microsoft.com/en-us/rest/api/fabric/graphmodel/items/execute-query%28beta%29)
  requires the beta flag, documents pagination, and supports those identity types. The page
  labels the API beta and not recommended for production, and the item preview.
- [Refresh Graph](https://learn.microsoft.com/en-us/rest/api/fabric/graphmodel/background-jobs/run-on-demand-refresh-graph)
  returns a job location and Retry-After; it is a refresh job, not a row update.
- [Manage and refresh data](https://learn.microsoft.com/en-us/fabric/graph/manage-data)
  explains that graph data is ingested from underlying lakehouse tables when the model is
  saved/refreshed. The GQL material inspected does not establish direct node/edge CRUD.

Add query plus graph-model definition/lifecycle/refresh handling under the same facade only
with explicit resource-kind and administrative semantics. Do not implement `update(record)`
by quietly rewriting a lakehouse or rebuilding a graph. These are credible additions, but
capacity, grants and beta feature approval remain prerequisites.

### Gremlin: A Real Authentication Gap, Not Just Missing Python Code

The concrete [Microsoft Python quickstart](https://learn.microsoft.com/en-us/azure/cosmos-db/gremlin/quickstart-python)
uses `gremlinpython`, a GraphSON v2 serializer and an account key as the connection password.
The [security overview](https://learn.microsoft.com/en-us/azure/cosmos-db/gremlin/security)
mentions managed identity but links only to the generic identity overview, not a demonstrated
Gremlin traversal token/role recipe. The [FAQ](https://learn.microsoft.com/en-us/azure/cosmos-db/gremlin/faq)
does not settle that mismatch in the inspected material.

Conclusion: the transport library is reusable, but a compliant keyless traversal path was
**not established** by this research. This is not proof such a path can never exist. Keep
the positive live profile blocked until current supported authentication, audience, roles,
serializer and driver-version compatibility are established. Do not copy the key-fetching
quickstart or reuse Cosmos NoSQL role assumptions as proof.

### Relational Services: Reuse Drivers, Not HTTP Adapters

Microsoft's [mssql-python project](https://github.com/microsoft/mssql-python) documents GA
status, DB-API 2.0 operations/parameters/transactions, Linux support and Entra authentication.
The inspected [v1.15.0 release](https://github.com/microsoft/mssql-python/releases/tag/v1.15.0)
is non-prerelease, published 2026-09-11. Its README documents a native ODBC companion package
and platform requirements; it is not a pure-Python/no-native-dependency promise.

The driver supports injected tokens but caller-owned token lifetime/pooling rules still need
care. Do not use process-wide interactive/default identity pools to imply per-user isolation.
Use driver parameter substitution for values, explicit transactions and safely generated
identifiers. A stable row-version contract must be chosen; SQL does not automatically give
every table a universal ETag.

Microsoft's [PostgreSQL Python quickstart](https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/connect-python)
uses Psycopg and has a passwordless path. The upstream
[async guide](https://www.psycopg.org/psycopg3/docs/advanced/async.html),
[transaction guide](https://www.psycopg.org/psycopg3/docs/basic/transactions.html) and
[identifier-composition API](https://www.psycopg.org/psycopg3/docs/api/sql.html)
provide reusable primitives for safe queries and connection ownership. Multiple cursors on
one async connection share a session; they are not independent concurrent transactions.

Both drivers require protocol-specific trusted connection settings instead of extending the
current HTTPS-origin validator with exceptions. Preserve the same factory/method/request/result
surface. Build internal driver configuration from validated fields; never accept arbitrary
credential-bearing connection text through `service_options`. Do not cache an Entra token as
a permanent database password. Refresh on new connections according to the documented driver
mechanism, and prove TLS/identity behavior live.

## Shared Official Building Blocks

| Existing Capability | Reuse Candidate | Remaining Library Responsibility |
| --- | --- | --- |
| Retry and transport policy | [azure-core AsyncRetryPolicy](https://learn.microsoft.com/en-us/python/api/azure-core/azure.core.pipeline.policies.asyncretrypolicy?view=azure-python) and SDK-native transports | One total deadline/attempt budget, no hidden unsafe write retries, appropriate redirect/host restrictions, bounded diagnostics and resource ownership. |
| Azure resource lifecycle | [Search management operations](https://learn.microsoft.com/en-us/python/api/azure-mgmt-search/azure.mgmt.search.operations.servicesoperations?view=azure-python), with service-specific `azure-mgmt-*` clients | Explicit grants, target confirmation, allowed plans, exact owned resource sets and read-back. Validate each additional client's concrete API before adoption. |
| Long-running status | [AsyncLROPoller](https://learn.microsoft.com/en-us/python/api/azure-core/azure.core.polling.asynclropoller?view=azure-python) and its continuation/resume contract | Scoped authenticated operation references, bounded polling and fresh authorization. Poller success does not prove requested data/fields; a SDK continuation is not a public trusted token. |
| Fabric asynchronous completion | [Fabric long-running operations](https://learn.microsoft.com/en-us/rest/api/fabric/articles/long-running-operation) with Location, operation ID and Retry-After | Separate Fabric workspace ownership, supported identity/scope, job-versus-operation handling and field/data read-back. |
| Fabric environment setup | [microsoft/fabric-cicd](https://github.com/microsoft/fabric-cicd) | Useful optional deployment reference/tool, not the data connector and not blanket authority to publish/delete workspace items. Verify supported item types before use. |
| Real SDK behavior fixtures | [Azure SDK Python test guidance](https://github.com/Azure/azure-sdk-for-python/blob/main/doc/dev/tests.md) and [Azure SDK Tools Test Proxy](https://github.com/Azure/azure-sdk-tools/tree/main/tools/test-proxy/Azure.Sdk.Tools.TestProxy) | Opt-in live execution, exact ownership and secret/data sanitization. Playback gives offline regression evidence, not a current live CRUD pass. |

Prefer package dependencies and public APIs. Reuse selected source/test patterns only with
versioned provenance and required notices; do not vendor whole SDK trees, adopt a new test
framework solely for symmetry, or leave SDK and hand-written stacks both owning the same rule.
The current endpoint-wide breaker/adaptive-throttle gap is not solved merely by adding
`AsyncRetryPolicy`; state scopes and feedback behavior still require explicit design and tests.

## Common Contract Additions Needed

These are proposals only. Every connector retains the same public interaction surface.

- **Query metadata:** bounded structured counts/facets/answers/captions, returned through a
  common optional field rather than silently discarded provider data or new Search methods.
- **Typed content and identity:** binary values, table/SQL scalar metadata, multiple named key
  parts and distinct absent/null/hierarchical partition values. Avoid SDK objects and ambiguous
  sentinel overloading in public values.
- **Conditional mutation:** existing common preconditions plus adapter-supported native
  patch/batch operations. Advertise each guarantee and its resource/partition boundary.
- **Native execution contexts:** HTTP, TDS, PostgreSQL and Gremlin transports behind trusted
  adapters; no requirement that a standardized connector must use standardized wire transport.
- **Scoped operation references:** `status()` over provider LRO/ingestion/job identities,
  without confusing completion of an administrative operation with record persistence.

Before a versioned change, run the same common negative tests against every adapter. Expanded
SDK support does not justify widening grants, leaking raw responses, allowing arbitrary native
commands through `query`, or relaxing the missing/unsupported/unknown distinctions.

## Suggested Adoption Slices

| Slice | Small Demonstrable Outcome | Required Check From The Live Plan |
| --- | --- | --- |
| Search query completion | Counts/facets/semantic answers and native paging round-trip through one result class | Cases 18-21, plus tampered/out-of-scope continuation and bounds. Update the frozen metadata expectations explicitly because current requests refuse. |
| Blob adapter | Create/read/replace/upsert/delete known bytes with conditions and content evidence | Cases 68-77; digest, overwrite-race, version and residual-history checks. |
| Table adapter | Composite-key CRUD with merge/replace and ETags | Cases 85-92; two partitions, type preservation, exact conditions and batch scope. |
| Cosmos extension | Native patch-backed existing-record update and declared transactional batch | Cases 25-35; update missing never inserts, stale conditions refuse, batch rollback is observed. Change the current merge-refusal oracle only after a contract decision. |
| Kusto/ADX and Eventhouse | Identified ingestion followed by native query and truthful status | Cases 45-60; batch-scoped evidence, duplicate policy and separate Fabric results. |
| Administrative completion | One allowlisted resource kind implements provision/status with read-back | Common cases 1-5 and 10-12, plus provider-specific owned-fixture lifecycle. No cloud action is authorized here. |
| Relational drivers | One owned schema/table per backend through the same methods | SQL cases 78-84 and PostgreSQL cases 93-100; type/transaction/TLS/Entra evidence, no hidden insert during update. |
| Fabric Graph | Scoped beta query and model/refresh administration | Cases 61-67; capability classification, semantic status, ownership and explicit beta acceptance. |

Do not start every slice at once. For the next implementation decision, Search query completion
has the smallest gap to an already documented SDK surface. For the next new adapter, Blob or
Table offers the clearest native fit. Keep Gremlin authentication as a bounded investigation,
not a promise hidden in the implementation plan.

## Licensing, Versions And Limits

- [Azure SDK for Python](https://github.com/Azure/azure-sdk-for-python/blob/main/LICENSE),
  [Kusto Python](https://github.com/Azure/azure-kusto-python/blob/master/LICENSE) and
  [fabric-cicd](https://github.com/microsoft/fabric-cicd/blob/main/LICENSE) have MIT notices in
  the inspected repositories. Dependency/binary notices still need their own review.
- [mssql-python licensing](https://github.com/microsoft/mssql-python/blob/main/LICENSE)
  distinguishes MIT wrapper code from separately licensed Microsoft native driver/runtime
  components. Its README and license refer to different historical packaging paths; inspect
  the pinned release and companion wheel rather than assuming all redistributed bytes are MIT.
- [Psycopg's upstream license](https://github.com/psycopg/psycopg/blob/master/LICENSE.txt)
  is LGPLv3. It is a PostgreSQL ecosystem dependency, not a Microsoft SDK. Preserve applicable
  terms/notices and review packaging obligations; do not relicense copied driver code as ours.
- Several sources track default branches/latest docs; the fetched Psycopg pages identify a
  development documentation version. Select and test released package versions before adoption,
  and verify signatures against those exact releases rather than pinning documentation heads.
- Official examples contain secret-authentication, environment/global-client and permissive
  retry patterns we must not import wholesale. Source authority is evidence of an API, not an
  instruction overriding this repository's credential/authorization rules.
- Retrieved 404 leads were corrected for Kusto and Gremlin documentation. A guessed
  `microsoft/FabricRestClient` repository URL was not found and is not a verified dependency;
  the actual inspected first-party deployment project is `microsoft/fabric-cicd`.

No speed, cost, integration success or live permission measurement is claimed. No official
library eliminates our need to test unsupported operations, atomicity, stored values,
credential lifetimes, cancellation and cleanup against the real services under explicit grants.