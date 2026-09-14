# Azure Data Connector Live Test Design

**Status: planned, not executed.** Prepared 2026-09-14. This document creates no service,
role assignment, fixture, executable test or cloud authorization.

## Objective

Verify the standardized connector against real cloud data services: create, read, update,
upsert and delete, including their exact semantics, native queries, read-back evidence and
failure cases. The same public interface must be used for every service. An SDK or Azure
CLI call performing CRUD directly is not a test of this library.

The [implemented contract](../../CONTRACT.md) is the current behavior authority. The
[library design](../../README.md) describes subsequent coverage. The
[factory](../../src/azdata/connector.py) currently registers only `search` and `cosmos`.
Other service profiles below require adapter work before their live cases can run.

"Every data service" means every distinct service named in this library's design or its
existing connector baseline, as enumerated below. It does not claim coverage of every
Azure product. Additional services need their own profile and CRUD cases before they can
be included in a coverage claim. Cosmos MongoDB/Cassandra/Table APIs, for example, are
not implied by testing Cosmos NoSQL, Gremlin or Azure Storage Tables.

## Service Inventory

| Profile | Current Library State | Cloud Fixture Required | Numbered Cases |
| --- | --- | --- | --- |
| Azure AI Search | `search` implemented; modes limited by the current contract | Dedicated index in an approved Search service | 13-24 |
| Cosmos DB NoSQL | `cosmos` implemented; explicit scalar partition, replace-only updates/upserts | Dedicated database/container with a declared partition path | 25-36 |
| Cosmos DB Gremlin | Not registered; legacy mechanism is a migration candidate | Dedicated graph plus valid identity-based data access | 37-44 |
| Azure Data Explorer | Not registered; Kusto ingestion/query mechanisms exist in skills | Dedicated database/table on an approved ADX cluster | 45-53 |
| Fabric Eventhouse | Not registered; same KQL family, different deployment/identity target | Approved Fabric workspace, Eventhouse and KQL database | 54-60 |
| Fabric GraphModel | Not registered; legacy coverage is read-only GQL | Approved workspace/graph item containing a synthetic graph | 61-67 |
| Azure Blob Storage | Not registered; legacy object adapter is a migration candidate | Dedicated container in an approved storage account | 68-77 |
| Azure SQL Database | Not registered; legacy SQL access is not proof of new-library CRUD | Dedicated database/schema/table and Entra database principal | 78-84 |
| Azure Table Storage | Future candidate named in the library design | Dedicated Storage Table with run-owned partitions | 85-92 |
| Azure Database for PostgreSQL Flexible Server | Future candidate named in the library design | Dedicated database/schema/table and Entra database role | 93-100 |

The [legacy package metadata](../../../../.github/skills/azure-data-connectors/pyproject.toml)
includes SQL, storage and other service dependencies; installing them does not register
adapters in the new library. A successful ADX run does not certify Eventhouse, and a working
Cosmos NoSQL account does not certify Gremlin. Fabric resources are workspace/capacity
artifacts; do not assume the Azure resource-group boundary owns or cleans them up.

Shared cases 1-12 apply independently to each service profile. Closing cases 101-104 apply
to the entire run. Numbers identify test specifications, not a measured count of executions.

## Coverage Rules

All cases start as `NOT_RUN`. Record one outcome per service, case and operation mode:

- `PASS_LIVE`: the library used a real authorized service and met the stated evidence rule.
- `PASS_REFUSAL`: a contractually unsupported operation/guarantee refused correctly, with
  fixture state unchanged. Report separately from positive live CRUD coverage.
- `FAIL`: the observed result contradicts the pinned contract or provider-backed oracle.
- `BLOCKED`: missing adapter, fixture, identity, permission, service tier, capacity, cost
  authorization or a way to observe the required result. Never count as a pass.
- `NOT_RUN`: not attempted. Optional cases must retain their reason and remain visible.

Maintain a coverage row for each profile and every operation: `create`, `read`,
`update(merge)`, `update(replace)`, `upsert(merge)`, `upsert(replace)`, `delete`, `query`,
`ingest`, `schema` actions, `provision` actions and `status`. Conditions/versions are separate
variants where supported. This matrix is a test report derived from the existing catalogue
and contract, not a second capability registry.

Freeze expected capabilities before execution using the public contract and reviewed provider
documentation for the actual API version. Do not let `describe()` supply its own pass criteria.
Removing support from an adapter must not make a failing positive test turn green. A missing
adapter or missing implementation is `BLOCKED`, not proof the provider cannot perform CRUD.

Search atomic document create can be an expected refusal because the library deliberately
does not emulate insert-if-absent. Kusto keyed row updates/deletes and Fabric GraphModel
mutations may similarly be inapplicable to the declared native surface. Label such profiles
"supported operations plus refusal coverage", not "full transactional CRUD verified".

## Environment And Execution Boundaries

The [deployment runbook](../../../../deploy/README.md) and
[non-secret target configuration](../../../../deploy/env/azdata-live.env) own Azure targets.
The [existing resource-group receipt](../../../../deploy/records/azdata-live-resource-group-2026-09-14.json)
records an empty group at its observation time; it is not proof that any listed service exists
or that the current caller has data-plane permissions. No fresh Azure inspection occurs here.

Before execution, approve service names, regions, SKUs/capacities, cost ceiling, maximum run
duration, retention, network restrictions and exact cleanup scope. Add service setup/verification
to the existing deployment entry point; do not invent a second operator sequence. The current
group-only runner does not provision services and refuses teardown of a non-empty group.

Use Entra credentials, with separately authorized writer, reader and denied test principals
where needed. A broad logged-in CLI identity is not a valid least-privilege denial fixture.
Do not revoke a human's existing grants to manufacture a negative test. Unsupported identity
access is a blocker, never permission to use account keys, connection strings or SAS tokens.

Live execution must be explicit and opt-in, with exact target confirmation. It must never
become part of default offline test discovery or run merely on import. Setup, execution and
cleanup grants remain distinct. This document specifies tests, not runnable commands or a
completed runner. Existing offline tests must still pass before an authorized live run starts.

## Synthetic Fixtures And Evidence

Every case gets a fresh `run_id` and case-specific namespace, sanitized for native naming
limits with collision detection. Reuse of a name must require its own ownership check.
Maintain an exact seed/cleanup manifest; never delete by a broad prefix alone.

- Document/row fixtures have stable keys, `run_id`, `revision`, a changed field and an
  unchanged sentinel. Replacement input deliberately omits a previously writable field.
- Use a small declared set of booleans, numbers, text with quotes/escaped Unicode, null or
  missing fields and timestamps where the provider supports them. Declare normalization rules.
- Cosmos/Table/graph fixtures include two owned partitions with repeated logical IDs, plus
  an untouched neighboring object to detect overbroad operations.
- Graph fixtures use a bounded set of labeled vertices and explicitly identified edges.
- Search vectors are deterministic numeric fixtures of the configured dimension; no paid
  embedding/model call is necessary. Semantic-search features require a permitted service tier.
- Blob fixtures include empty, text and binary payloads, with an independent byte digest.
- Kusto-family fixtures carry event identity and batch/run identity. Record the mapping,
  expected rows and provider-supported ingestion receipt/tags.

Construct immutable expected values before writing. Read back through a fresh connector
instance where practical, so an in-memory cache cannot impersonate persistence. Use native
query/read observations to corroborate results when needed. Setup may use separately approved
CLI/SDK calls, but setup operations are not positive CRUD evidence for the library.

Record `service_profile`, case number, operation/mode, library version and artifact digest,
provider API version, target ID, non-secret principal ID, run ID, request ID, UTC times,
aggregate/item statuses, requested/achieved verification, observed digest/count/version,
latency, attempts, caveats and cleanup outcome. Do not log credentials or raw `to_dict()`
payloads. Retain only approved synthetic artifacts. Proposed reports belong with the host's
deployment evidence; fixtures/test specifications belong with this suite.

Use bounded deadlines and provider-aware read-back, not arbitrary fixed waits. HTTP acceptance,
key presence and equality of the requested stored state are different evidence levels. Record
unobserved branches as such. A real operation plus an explicitly controlled response-loss
experiment is a hybrid resilience test; it is not proof Azure naturally returned that fault.

## Numbered Test Catalogue

### Shared Contract And Safety

1. **Freeze the real target and artifact.** Verify the approved cloud/tenant/subscription or
   Fabric workspace, resource owner, endpoint, API version and installed library artifact.
   Use the normal service adapter and real credential, with no mock responses. Wrong target,
   missing grants or absent resources must block the run before fixture mutations.

2. **Verify identical interfaces and honest support.** Compare all public method signatures,
   request/result classes and lifecycle behavior across profiles. Compare `describe()` with
   the frozen expected operation/mode matrix. Run a real bounded read/query canary separately;
   description alone must not claim reachability or elevate unsupported methods to support.

3. **Reject scope escape.** With two approved test targets, attempt to redirect a connector
   to the other target through request coordinates, options and continuation input. Require
   `denied` or `invalid` before submission and read both targets back unchanged. Never use
   a production endpoint as the out-of-scope probe.

4. **Enforce local policy independently of Azure privilege.** With a valid writer credential
   but read-only library policy, attempt each implemented mutating operation, including
   schema/provisioning mutations where available. Require local refusal, no write submission
   and unchanged before/after fixture digests. Default grants must not create data.

5. **Enforce real cloud permissions.** Give the library an explicit mutation grant but use a
   separately provisioned reader-only or denied principal. Require the provider denial to
   survive normalization and prove through an authorized observer that no state changed.
   Test document access and administrative access separately; unavailable restricted identity
   is `BLOCKED`, not a permission test passed with an Owner account.

6. **Preserve types, bounds and ordered outcomes.** Send supported scalar/collection fixtures,
   repeated read keys and requests just inside declared item/byte bounds. Read exact normalized
   values back in the required order. Duplicate mutation keys, non-finite/invalid values and
   attempts to raise policy ceilings must refuse without partial unintended writes.

7. **Page without claiming completeness incorrectly.** Query a quiescent fixture larger than
   one configured page, using deterministic native ordering where supported. Read all pages,
   detecting missing/duplicate IDs and dishonest truncation. Alter query/target/caller context
   when reusing a token and require rejection. A nonresumable byte-truncated prefix must be
   reported as incomplete, not as a complete empty-tail result.

8. **Distinguish absence from failure.** Compare a missing owned key, an empty native query,
   malformed input, a reader denied by Azure and an unreachable approved test endpoint where
   safely available. Require `not_found`, successful empty query, `invalid`, `denied` and
   failed/unknown transport outcomes respectively. Never convert access failure into absence.

9. **Account for every batch item.** Submit an adapter-valid mixed batch with one native
   conflict or validation failure and other valid items. Correlate each submitted key/index
   with the service result and read-back. Retain successes and unattempted/unknown items;
   no blanket success or automatic retry of already accepted items. If the native API rejects
   the entire batch atomically, assert that documented behavior instead of inventing partiality.

10. **Verify actual values and required evidence.** Seed version A, write version B with a
    changed field, and require content or version evidence rather than presence alone. Fresh
    read-back must match B. An attempt to weaken the policy's verification requirement must
    refuse before writing. Non-retrievable fields must not be silently omitted from the proof.

11. **Exercise real credential renewal and lifetime.** In a separately approved bounded soak,
    cross an observed token-refresh boundary, then perform a read and authorized mutation.
    Require fresh authentication and correct results without printing tokens. Closing twice
    must be safe, borrowed credentials must remain usable and post-close operations must not
    submit requests. Without observing renewal, report that branch `NOT_RUN`.

12. **Reconcile ambiguity without duplication.** Under separately approved, low-volume fault
    control, interrupt a real response after submission or cancel a real in-flight operation.
    Require preserved accepted/unknown outcomes and no blind mutation retry. Use authorized
    read/status to reconcile state and clean it up. Test natural throttling only if encountered
    or safely inducible within budget; do not overload a service to force 429s or label injected
    transport faults as native-provider evidence.

### Azure AI Search

13. **Create and inspect the test index.** Through `schema(create)`, submit the run-owned
    definition with a retrievable key, writable scalar fields, a sentinel and an optional
    fixed-dimension vector field. Require conditional creation and `schema` read-back.
    `schema(read/list)` must show the configured index only and preserve the requested field,
    key, vector and semantic settings, with documented provider defaults.

14. **Refuse atomic document create honestly.** Call `create` for both a missing key and an
    existing fixture. Under the current contract both return `unsupported` without upload.
    Read back the existing document unchanged and the missing key absent. This is refusal
    coverage; seed through explicit upsert, never relabel that upsert as successful create.

15. **Upsert in merge mode.** Insert a fresh document using `upsert(merge)`, then send a
    second partial value with the same key. Require one stored document, changed supplied
    fields and preserved omitted fields. Repeat the same request safely and verify native
    values rather than relying on the number of accepted actions.

16. **Upsert in replace mode.** Replace a document while omitting its old writable sentinel
    field. Fresh read-back must show native replacement semantics, accounting explicitly for
    null/default field representation. It must not retain the old value or pass solely because
    the newly supplied subset matches. Upserting a missing key must insert it.

17. **Update an existing or absent document.** `update(merge)` must change only supplied
    fields of an existing key and report `not_found` for a missing key without creating it.
    `update(replace)` is currently an explicit refusal; the missing key remains absent after
    that call too. Include collection-field replacement, not an assumed recursive merge.

18. **Read keys, projections and missing records.** Read single and repeated keys, including
    a missing key and top-level field projection. Require correct per-item ordering, values
    and missing policy. Nested projections currently refuse before I/O rather than returning
    a silently incomplete record. Compare results from a second connector instance.

19. **Observe native per-document errors.** Submit valid documents alongside a document that
    passes library shape validation but violates the declared Search field/vector schema.
    Inspect actual 200/207/native outcomes and compare successful items against persisted
    documents. Invalid items must not be claimed stored; errors must not log raw payloads.

20. **Query real indexes.** Verify keyword/filter/order and supported semantic/vector queries
    against known synthetic documents; use deterministic vectors, not paid inference. Check
    projected rows, ranking properties that are actually deterministic and multi-page behavior.
    Required tier/features unavailable is `BLOCKED`. In `azdata` 4.0.0a2, count/facet/answer
    metadata and caption annotations are supported through the official SDK. Request them and
    compare the structured results, pagination and byte bounds; an offline SDK pass is not
    evidence that the real service tier or live query has been verified.

21. **Test document conditions and indexing visibility.** Require exact document-version or
    atomic-batch guarantees that the current adapter cannot supply; expect refusal and unchanged
    state. Separately write a document and observe bounded acknowledgment-to-readability/content
    verification. Immediate visibility is valid; do not manufacture eventual delay or pretend an
    observed pending result proves content already matches.

22. **Update schemas with real ETags.** Read the actual index version, add one permitted field
    through `schema(update)`, then read the schema and sentinel documents back. A stale version,
    missing exact version, removed field or changed field type must conflict/refuse without a
    drop-and-recreate. Confirm provider normalization does not produce false schema success.

23. **Delete documents and verify absence.** Delete exact owned keys with explicit
    `missing="ok"` and required absence evidence. Confirm unrelated documents survive and a
    repeated delete has the documented outcome. Current `missing="error"` and document-version
    conditions refuse rather than use a racy pre-read to manufacture guarantees.

24. **Delete only the confirmed index.** After data cases, test missing/wrong endpoint-bound
    confirmation and wrong version against the owned index; no deletion may occur. Then use
    the approved destructive policy, exact digest and current version with `schema(delete)`.
    Read back index absence; another test index must remain untouched.

### Cosmos DB NoSQL

25. **Validate the partitioned fixture.** Use an approved run-owned database/container with
    a declared top-level partition path. Record that path independently of connector settings.
    Confirm the adapter requires `id` and the actual partition type, and no constructor or
    ordinary data call creates the account, database, container or role assignment implicitly.

26. **Create without overwrite.** Create a fresh ID/partition pair and read exact content and
    returned version back. Create the same identity with different content; require `conflict`
    and preservation of the original. The duplicate must not be silently upserted.

27. **Race two creates.** Synchronize two live `create` requests for the same fresh ID/partition
    with different payloads. Require one successful create and one conflict, and one persisted
    winning payload. Two successes or a silently overwritten winner fails atomic create semantics.

28. **Read partition-specific identities.** Create the same ID in two owned partitions with
    different sentinels. Read each exact pair, missing IDs and a wrong partition. Values must
    not cross partitions, and missing partition input must refuse before I/O. A not-found
    result says nothing about the ID in other partitions.

29. **Replace only existing items.** `update(replace)` with a changed field and omitted
    sentinel must produce the exact writable replacement, ignoring only declared server fields.
    The same update for a missing identity returns `not_found` and does not insert. Reject
    mismatching payload ID/partition and type-confused partition values before submission.

30. **Enforce optimistic concurrency.** Read a real version, perform one conditional replace,
    then attempt another update and delete with the stale version. Require `conflict` and no
    lost update. A current version succeeds; wildcard versions or a requested exact-version
    guarantee without versions must refuse. Test two competing conditional writers as well.

31. **Upsert explicitly in replace mode.** Upsert a missing identity, then replace it with
    different content and repeat the second request. Verify one item under that exact key,
    no old sentinel value, and unchanged neighboring partition data. A request ID alone is
    not used as proof of service deduplication.

32. **Refuse undeclared merge semantics.** Current `update(merge)` and `upsert(merge)` return
    `unsupported` without mutations for both missing and existing identities. Record this
    as an adapter limitation, not a claim Cosmos has no native patch mechanism. Future merge
    support requires separate positive and missing-record cases before changing this oracle.

33. **Query using bound native parameters.** Query known values, including quote/injection-like
    text as parameter data, with an explicit partition and then an approved container-wide scope.
    Verify native continuation, projection, item/byte bounds and unchanged fixture state.
    Mutation-shaped query text must not become a command; unsupported scalar result forms
    remain explicit gaps rather than successful document queries.

34. **Preserve conflict and partial batch results.** Submit creates containing an existing
    key and new keys. Verify each result, exact persisted set and per-item order; a conflict
    must not hide later successful inserts. If a real transport failure interrupts a separate
    run, report preceding successes and remaining unattempted/unknown items honestly.

35. **Delete with partition and version discipline.** Delete an existing ID/partition pair,
    verify absence, and test repeated delete under both missing policies. Deleting the wrong
    partition with `missing="error"` cannot claim success. With `missing="ok"`, absence
    evidence is explicitly scoped to that address, while the same ID elsewhere remains intact.

36. **Keep undeveloped planes explicit.** Call schema, ingestion, provisioning and status
    methods against the real configured target. Current results must be `unsupported` without
    service mutations. Retain those implementation gaps in the report; do not count them as
    proven Cosmos schema or infrastructure CRUD.

### Cosmos DB Gremlin

37. **Establish actual identity-based access.** Verify the authorized Gremlin endpoint,
    database, graph and partition mapping with a bounded live canary. Reverify supported
    token audience and roles for this API, not NoSQL by analogy. Unsupported keyless access
    or an unregistered adapter blocks positive cases; never fetch account keys as a workaround.

38. **Test vertex creation guarantees.** For an implemented create mode, create a new
    vertex, attempt duplicate creation and race two writers. Require native/otherwise proven
    non-overwrite semantics and one vertex per declared identity. If those guarantees cannot
    be supplied, `create` must refuse before traversal submission; a pre-read followed by
    `addV` is not a passing atomic-create test.

39. **Read vertices and graph properties.** Round-trip supported scalar/collection properties,
    labels, partition identities and escaped quotes/backslashes. Query exact vertices to
    corroborate values and missing results. Invalid identifiers or traversal-shaped property
    data must not create extra vertices, edges or commands.

40. **Distinguish update merge from replace.** Exercise every implemented mode on an existing
    vertex and a missing identity. Merge retains omitted properties; replace removes only
    the contractually writable omitted properties; neither may insert on update. Unsupported
    modes refuse. Confirm the adapter states whether edge relationships are outside replacement.

41. **Upsert without duplicate graph identity.** For declared upsert modes, insert then change
    the same partitioned vertex and repeat. Verify exact cardinality and properties using
    native read traversals. When edges are supported, repeat with explicitly addressed edge
    endpoints/labels; vertex-only support cannot be reported as tested edge CRUD.

42. **Bound read traversals and isolate graph scope.** Run allowed native queries with declared
    bindings/literal encoding and limits. Mutation-bearing queries must refuse; repeat logical
    IDs in another owned partition remain isolated. A result cap is not permission to traverse
    or modify arbitrary graphs or neighboring partitions.

43. **Verify concurrent updates and caveats.** Test advertised version/atomic-batch guarantees
    with competing writes. If native conditional semantics are unavailable, require the same
    standardized `unsupported` response without a best-effort transaction. Do not interpret
    a returned Gremlin success envelope as proof of the requested final properties.

44. **Delete exact graph elements.** Delete owned edges/vertices supported by the adapter,
    then query absence and inspect neighboring vertices and their relationships. Test missing
    identity/partition policies and any documented cascade behavior. Never use an unscoped
    `g.V().drop()` for cleanup or call partial graph cleanup a complete deletion.

### Azure Data Explorer

45. **Establish an ADX schema and mapping.** In an approved isolated database, create/read
    the owned table and ingestion mapping through supported administrative methods. Verify
    ordered column names/types and mapping identity. If setup uses an external approved tool
    because the adapter is missing, mark library schema coverage `BLOCKED`, not passed.

46. **Ingest an identified batch.** Submit a small deterministic event batch with run/event
    identities and a known mapping. Capture real acknowledgment and operation/tag identity.
    Use scoped KQL read-back to verify all expected rows and values, not just a whole-table
    count increase. A timeout after submission remains pending/unknown until reconciled.

47. **Read through native KQL.** Query the owned run using native parameters, time bounds,
    projections and result caps. Compare column types, timestamps, dynamic values, rows and
    truncation to fixtures. Never substitute a generic SQL translator or unparameterized
    interpolation for supported Kusto parameter binding.

48. **Reject fictitious record CRUD.** Attempt ordinary keyed create/read/update/upsert/delete
    under the frozen ADX adapter contract. Where stable keyed rows and those semantics are not
    supported, require `unsupported` without ingestion or management commands. Query existing
    events unchanged; an append, materialized view or soft-delete is not a row replacement.

49. **State ingestion idempotency honestly.** Repeat a batch only under an approved duplicate
    budget. If scoped ingestion deduplication is advertised, test its identity and documented
    retention window; otherwise require an explicit unsupported exactly-once guarantee before
    submitting it. Demonstrate the actual duplicate policy rather than assuming request IDs
    make repeat appends harmless.

50. **Handle schema and ingestion failures.** Submit a declared malformed/mismapped fixture
    separately from a valid batch. Verify genuine provider outcomes and query the exact run
    to determine whether none, some or all rows landed. Do not report success from submission
    alone or lose the failed tail because only readable rows were counted.

51. **Resist misleading count deltas.** Ingest two bounded, differently tagged batches under
    separate owned run IDs into the same test table. Each verification must identify its own
    expected rows. One batch's count increase must not verify the other's failed or delayed
    ingestion. This directly tests the weakness of whole-table delta verification.

52. **Keep management separate from reads.** Attempt mutation/management KQL through `query`
    and require refusal. Exercise any declared additive schema or soft-delete administration
    only through the authorized administrative contract; read its exact effect back. If no
    suitable public mapping exists, retain a blocked capability rather than execute raw code
    under a read grant.

53. **Retire only the owned table/mapping.** After tests, use authorized supported schema
    deletion or separately recorded fixture cleanup to remove exact run artifacts. Read table/
    mapping absence and preserve other tables. Soft row deletion, dropping an extent and
    removing a whole database are distinct actions; none proves physical erasure of backups.

### Fabric Eventhouse

54. **Validate a separate Fabric target.** Record the approved workspace/capacity, Eventhouse,
    KQL database and endpoints. Verify identity, feature availability and access on that
    target. The Azure RG and a passing ADX cluster test cannot stand in for this profile.
    Missing Fabric capacity or authorization is `BLOCKED`.

55. **Verify Eventhouse table/mapping administration.** Repeat case 45 on the actual Eventhouse
    database, with a new owned table and mapping. Record native API differences and unsupported
    actions; imported setup artifacts do not count as library schema creation.

56. **Ingest and verify an Eventhouse batch.** Repeat case 46 with separate Eventhouse run/batch
    identities. Require provider-specific acknowledgment and scoped visibility evidence for the
    exact rows. Success on ADX is not evidence of the Fabric ingestion endpoint working.

57. **Query Eventhouse data and permissions.** Repeat case 47 against Eventhouse, plus a real
    reader/denied principal comparison. Verify known rows, typed projections and result bounds;
    distinguish workspace permission failure, unconfigured target and an empty event window.

58. **Reject unsupported keyed CRUD.** Repeat case 48 on the real Eventhouse target. Calls use
    the identical public connector methods and standard outcomes, not a special public
    Eventhouse API. No unsupported update may be silently implemented as another ingestion.

59. **Verify batch identity under repeats and failures.** Repeat cases 49-51 independently on
    Eventhouse: duplicate policy, malformed input and simultaneous identified batches. Record
    only the actual evidence achieved; an ingestion count from another batch is not a pass.

60. **Respect Fabric lifecycle ownership.** Test allowed schema changes and exact fixture
    deletion as in cases 52-53. Query residual state and leave unrelated workspace items
    intact. Do not delete a shared workspace or capacity; RG teardown does not retire the
    Fabric data artifacts created for this run.

### Fabric GraphModel

61. **Identify the actual graph API and rights.** Pin the supported API version, workspace,
    graph item and token audience. Load a bounded known graph using a separately approved
    fixture procedure if needed. Record that setup separately; it cannot prove library create.

62. **Read known graph structure.** Execute native GQL through `query` against seeded vertices,
    edges and attributes. Compare actual columns, typed values, cardinality and empty matches.
    Verify endpoint-reported semantic status as well as HTTP status; a 200 with a failed query
    status is not a successful empty result.

63. **Classify create precisely.** Submit `create` for a new and existing graph identity.
    A read-only native surface must refuse before mutation. If a future reviewed adapter
    exposes real creation, require read-back and conflict/race behavior from case 38.
    Merely missing adapter code remains `BLOCKED`, not proof GraphModel cannot create data.

64. **Classify update and upsert separately.** Exercise merge/replace on existing and missing
    graph identities. Read-only declared capabilities must refuse with unchanged graph state.
    Any future implemented mode must preserve the exact update/upsert distinctions and
    relationship rules from cases 40-41; never route a write through GQL read machinery.

65. **Classify delete and administrative methods.** Attempt exact-element deletion and all
    schema/ingest/provision/status operations. Require the frozen support matrix: read-only
    capabilities refuse without graph mutation; newly implemented deletes must have exact
    absence and neighbor-preservation evidence. No library functionality is inferred from a
    workspace-admin SDK used for fixture setup.

66. **Exercise real semantic errors and bounds.** Submit safe malformed/read-only GQL and
    requests over a configured result bound. Preserve actual semantic errors, response shape
    and explicit truncation. Test an unauthorized principal separately. Never fabricate a
    semantic-error body when claiming live provider evidence.

67. **Clean up the independently owned graph fixture.** Use the approved graph item's lifecycle
    path to remove only run-owned content/items, verify absence and retain other workspace
    objects. If the library is read-only, cleanup is infrastructure/fixture evidence rather
    than positive library delete coverage.

### Azure Blob Storage

68. **Validate a container with Entra access.** Establish an approved dedicated container and
    prefix, with synthetic neighboring objects owned by the same test run. Confirm the
    identity/endpoint and declared blob kind. Account keys/SAS are not allowed fallback paths;
    no fixture enables anonymous blob access.

69. **Create objects conditionally.** Create empty, text and binary block-blob fixtures with
    true non-overwrite semantics. Duplicate create and two competing creates must conflict
    rather than overwrite an existing object. Verify the winner's byte digest and metadata.

70. **Read exact bytes and metadata.** Read through the connector from a fresh instance and
    compare length, media type, byte digest and native version/ETag. Include embedded zero
    bytes and content exceeding one output page/bound. No byte-to-string fallback, silent
    clipping or SDK object stringification is acceptable evidence.

71. **Replace an existing object without inserting accidentally.** Use `update(replace)`
    where supported, including a shorter new body to detect stale trailing bytes. Compare
    complete content and declared metadata behavior. A missing key must not be created by
    an update, and stale conditions must preserve the existing object.

72. **Upsert and replay the same replacement.** Upsert a fresh object, replace it with a
    different body, then repeat the final upsert. Require one current object with the exact
    latest digest. No append-style duplication is allowed under replacement semantics.

73. **Refuse fabricated merge semantics.** Request `update(merge)` and `upsert(merge)` for
    object bytes unless the adapter defines a real supported content form. A metadata merge
    or append must not impersonate JSON/document merge. Unsupported modes leave bytes and
    metadata unchanged.

74. **Enumerate or query only the declared native surface.** If object listing is mapped to
    `query`, test prefix scope, continuation and bounds against known names. Otherwise require
    explicit query refusal and retain the listing gap. Do not invent SQL execution over blob
    bytes or bypass the public connector with a storage SDK to claim query coverage.

75. **Delete with exact versions and missing policy.** Use a stale then current ETag on a
    run-owned object. Require conflict followed by deletion and authorized absence read-back.
    Test repeated deletion under both missing policies and prove neighboring objects survive.

76. **Separate current-object absence from retained history.** Where already authorized and
    enabled, observe soft-delete/version/snapshot behavior. Report which view deletion affects;
    do not claim all historical content was physically erased. Enabling retention or purging
    retained versions solely for a test requires separate authorization and cleanup scope.

77. **Test object-operation failures and cleanup.** Exercise a provider-valid conflict or
    service size/type refusal with other successful objects, preserving individual outcomes.
    Enumerate the exact manifest after cleanup, including any owned versions/snapshots whose
    retention was approved. Unknown write outcome must remain until reconciled.

### Azure SQL Database

78. **Create a declared relational fixture.** Establish an approved database schema/table with
    primary key, nullable fields, scalar types and a documented concurrency column if used.
    Verify Entra database principal rights independently of ARM access. Run library schema
    methods only if implemented; external setup is not library schema coverage.

79. **Insert, read and reject duplicate keys.** Use `create` for a new row and read exact values
    back through a new connector/connection. Duplicate and synchronized competing creates
    must preserve one row and produce native conflict semantics, not a read-then-upsert race.

80. **Run parameterized SQL reads.** Query known strings containing quotes and SQL-looking
    text as bound parameter values. Require unchanged table/sentinel state, typed columns,
    correct projection, pagination/bounds and missing-record behavior. Query must not accept
    DDL/DML under a read policy; a prefix regex alone is not a complete read-only guard.

81. **Update with explicit field semantics.** Test merge and full writable replacement modes
    that the adapter actually supports, existing versus missing keys, nullable/default values
    and generated columns. Require retained/removed values per contract and no implicit insert.
    Native type rounding or normalization must be explicit in the comparison oracle.

82. **Upsert and enforce concurrency guarantees.** Insert via upsert, update the same row,
    repeat, and race writers under advertised key/version guarantees. Require one identity and
    real transactional/conditional behavior. Test stale versions; unsupported atomic batches
    refuse. Do not mark an unprotected existence-check algorithm atomic because it passed
    a sequential test.

83. **Delete addressed rows without widening a predicate.** Test exact primary-key deletion,
    stale/current preconditions and both missing policies. Fresh reads must prove addressed
    absence while same-value or neighboring rows remain. Verify no table-wide delete is
    synthesized from a missing key.

84. **Verify administrative and transaction boundaries.** Exercise supported additive schema
    changes, negative destructive-change confirmation and final owned-table removal. If the
    adapter advertises atomic batch behavior, a forced constraint failure must roll back that
    batch; otherwise record independent item effects. Database/server deletion is not fixture
    cleanup and requires its own approved lifecycle step.

### Azure Table Storage

85. **Validate native entity addressing.** Establish the owned table with explicit
    PartitionKey/RowKey mapping. The future adapter must accommodate this through the standard
    address types; the current ID-only factory is not sufficient. Duplicate row keys in two
    test partitions must remain distinct. Azure Storage Tables are not Cosmos Table API coverage.

86. **Create entities without overwrite.** Create an entity, read it back, then submit duplicate
    and competing creates for the same key pair. Require one persisted winner and conflict
    outcomes. Same RowKey in another partition is not a create conflict for this pair.

87. **Read typed entity properties.** Compare supported text, integers, bools, date/time,
    GUID/binary properties and ETags with native type metadata. Verify missing key pairs,
    top-level projection and ordering. Document unsupported/null property behavior rather
    than silently losing fields during serialization.

88. **Distinguish entity merge and replacement.** Update selected properties while preserving
    omitted ones, then replace the writable entity and confirm omitted old properties are
    removed under native semantics. Updating a missing pair must not insert it. Unimplemented
    modes remain blocked positive coverage, not automatic provider limitations.

89. **Test both upsert modes.** Upsert missing and existing entities using merge and replace
    where declared. Repeat with the same key pair, verify no duplicate current entity and
    compare omitted-field behavior. A single generic insert-or-merge implementation cannot
    pass the replacement case.

90. **Enforce ETag conditions.** Read the real ETag, update once and attempt stale conditional
    update/delete. Require conflict, with current-version operations succeeding. Wildcard
    conditions cannot satisfy an exact-version requirement. Verify no other partition changed.

91. **Verify queries, continuation and transaction limits.** Query owned PartitionKey/RowKey
    ranges through the declared OData/native mapping with safe literals and bounds. Bind
    continuation to the query. When entity transactions are advertised, verify same-partition
    atomicity and refusal of an unsupported cross-partition atomic batch before mutation.

92. **Delete and account for entities.** Delete exact owned key pairs, test missing policies,
    prove pair-scoped absence and preserve neighboring entities. Clean the manifest completely
    before any separately authorized table deletion; a wrong-partition lookup is not global
    proof that the RowKey no longer exists.

### Azure Database For PostgreSQL Flexible Server

93. **Establish real PostgreSQL transport and identity.** Validate approved host/database,
    TLS certificate/hostname, Entra principal and database grants. A future adapter must support
    the real database protocol without weakening host validation; the current HTTPS-origin-only
    configuration is an implementation blocker, not a reason to call PostgreSQL supported.

94. **Create rows and verify native conflicts.** Insert a fresh primary key, read complete
    normalized content, attempt duplicate creation and race two creates. Require one winner
    and no overwrite of its values. Permission/constraint failures remain distinct from absence.

95. **Read typed rows through bound queries.** Use supported decimal, timestamp, nullable,
    JSON and binary fixtures with a documented type mapping. Parameterize quote/injection-like
    strings and verify no command runs. Check page/row/byte limits and projections; unsupported
    types must not be converted to misleading strings.

96. **Update only existing rows.** Exercise declared merge and replacement semantics against
    existing/missing keys. Verify changed values, retained/removed sentinel fields and native
    default/generated-column handling. Update cannot silently use `INSERT ... ON CONFLICT`
    and create a missing row.

97. **Upsert under concurrent load.** Use a proven native atomic upsert strategy for supported
    key constraints, then race a bounded pair of writers. Verify one row per key and the
    declared final-value/version semantics. A pre-read followed by separate insert/update is
    not a substitute for an advertised atomic guarantee.

98. **Verify an explicit concurrency contract.** If conditional versions are supported, pin
    the actual version strategy, reject stale writes/deletes and test concurrent updates.
    Do not assume a timestamp or arbitrary system column is an ETag. If no strategy is
    implemented, exact-version requests must refuse with unchanged state and conditional
    coverage remains unavailable.

99. **Delete addressed rows.** Test current/stale conditions where supported and repeated
    deletion under each missing policy. Use a fresh connection to prove committed absence
    and unchanged neighbors. A command count of zero is not automatically proof the desired
    record was deleted from the correct database/schema.

100. **Verify schema and transaction lifecycle.** Perform supported additive schema changes,
     refuse destructive changes without exact authorization, and read definitions back. Test
     rollback on a real constraint failure only if atomic batch behavior is advertised. Remove
     the owned table/schema after its cases without changing shared server roles or other data.

### Run Closure And Coverage Claims

101. **Complete the per-service operation matrix.** For each of the ten profiles, reconcile
     cases with every operation/mode/action from the frozen contract. List positive live passes,
     contract-backed refusals, failures, blocked prerequisites and unrun branches separately.
     An unregistered adapter, missing Fabric capacity or absent test identity cannot disappear
     from the denominator or be presented as complete service coverage.

102. **Verify exact fixture cleanup.** Read back the owned resource/record manifest after
     each case and at run end, including failed/cancelled cases. Delete only authorized fixtures
     with confirmed ownership. If cleanup fails, stop further mutation where necessary and
     report exact residual IDs and costs/retention risks; never discard evidence or delete an
     unrelated group to obtain a green run. Fabric artifacts require their separate check.

103. **Repeat with a new isolated run.** Repeat the approved cases with fresh run/case IDs,
     inspect that neither run touches the other's sentinels, and verify continuation/credential
     contexts remain separate. Sequential repeatability does not prove concurrency guarantees;
     only the explicit race cases support those claims.

104. **Publish an honest evidence report.** Record the required metadata, outcome matrix,
     measured values and remaining resources in the host-owned evidence location, with links
     from the library's current status. Report native-provider versus controlled-fault evidence
     separately. A release may claim only the operations/services actually observed; "all
     services CRUD verified" is invalid while any required positive case is blocked or unrun.

## Delivery Order And Stop Condition

Implement the shared runner and Search/Cosmos cases first, through separately approved service
setup. Then add each remaining adapter/profile with its positive and refusal cases. Fabric,
SQL, Table and PostgreSQL prerequisites are explicit future work; this plan authorizes none
of their costs or identity changes.

No cloud pass is claimed today. Once executable tests are added, preserve this catalogue's
case numbers in their names or report metadata. Update expectations only for reviewed contract
changes, not to relabel defects as unsupported features. The suite is complete for a service
only when its required cases, evidence and cleanup have run and its honest support boundary
is documented. Overall coverage is the conjunction of those separate service results.
