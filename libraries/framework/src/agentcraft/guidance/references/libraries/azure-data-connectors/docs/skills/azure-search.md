# Azure Search

Use installed `azdata[search]` v4 and `connect("search", config, ...)`.
The `harness-azure-search` distribution and `azure_search` import are retired.
No second Search transport, schema engine or token cache remains in the skill.
The [v4 contract](../../CONTRACT.md) and [data guide](azure-data-connectors.md)
own common request/result, limit, authorization and lifecycle behavior.

## Requests And Host Boundary

Supply `ConnectorConfig` with one HTTPS Search origin, explicit `allowed_hosts`,
exact `target={"index": "authorized-index"}`, key field and, for content evidence,
declared retrievable fields. Borrow a host-owned Entra credential; optionally
inject the public `AsyncTransport`. No ambient credential or application import
is selected by the uniform factory. A descriptor is not a live permission check.

Use public `QueryRequest`, `ReadRequest`, `UpdateRequest`, `UpsertRequest`,
`DeleteRequest`, `SchemaRequest`, `RecordKey`, `RecordInput`, `ContentValue`,
`Verification`, `Requirements` and `Policy`. A query uses `dialect="search"` and
namespaced `service_options={"search": {...}}`. Keyword, semantic and explicit
numeric-vector/hybrid queries use the same result contract. The host supplies
vectors separately; no embedder callback causes an implicit model call.

Counts, facets and answers are result metadata; captions remain structured document
annotations. Metadata shares the output byte budget. Unknown options, arbitrary
query parameter bindings, unbounded requests and unsupported guarantees refuse.
Semantic quota errors do not silently retry as differently ranked keyword queries.

## Schema And Write Safety

Index definitions are native JSON, not the retired skill's independent schema
DSL. Operator review must establish exactly one key, intended retrievability,
vector fields/profiles and semantic configuration. Vector data is not implicitly
safe to expose: choose retrievability deliberately and keep output projections
inside the host's authorization boundary.

Schema list/read is limited to the configured index. Create uses a native
non-overwrite condition. Update/delete require exact versions. Update accepts
conservative additive fields, not field removal/replacement, migration or
drop-and-recreate. Deletion separately needs `schema.delete`, `schema.read`,
`Policy(destructive=True)` and a request-bound `confirmation_digest`. A digest
alone grants nothing. Schema writes require authorized schema readback.

Document create-if-absent is unsupported because Search cannot honor its required
semantics. Upsert requires explicit merge or replace; update is merge. There is
no automatic meaning guessed from an `upload` alias. Inspect every ordered
`ItemResult`, aggregate status and effect, not just HTTP 200/207. Missing or
duplicated acknowledgments cannot erase known accepted items or claim rollback.
Ambiguous mutations are not automatically retried.

Document acceptance can precede visibility. Request bounded presence/content/absence
evidence where supported. Content evidence requires declared retrievable fields;
stale presence does not verify an update. Null/complex comparisons and document
versions are explicitly unsupported. Polling shares the configured deadline.

## Errors, Limits And Lifecycle

Use standard `OperationResult` statuses, not retired `azure_search` exception
signatures. Invalid configuration raises `ConfigurationError`; programming defects
and cancellation propagate. Expected provider errors have bounded safe codes,
not raw responses. Default ceilings: 30 seconds, 100 items, 1 MiB input/output and
one native attempt. Request bounds only narrow policy; per-connector concurrency
defaults to 4. `aclose()` or async context management closes owned resources,
not injected credentials/transports. Cancellation makes no rollback promise.

## Retirement And Verification

Exact retired paths, hashes and replacement:
retirement manifest (source-or-asset-not-bundled; source reference: `azure-search-retirement.json`). The canonical Search suite
covers native requests, batching/outcomes, schema conditions, refusal and readback;
the shared data suite covers target/grant integrity and transport limits.

```bash
PYTHONPATH=libraries/azure-data-connectors/src python -B -m unittest discover \
  -s libraries/azure-data-connectors/tests -t libraries/azure-data-connectors \
  -p test_search.py -q
```

No live Search permission, network policy, model behavior or write was verified.
Native skill name/triggers and Microsoft MIT notice remain. Old convenience
signatures, service-wide enumeration and auto-embedding are intentionally retired,
not emulated. Parent integration owns discovery and old MCP registration removal.