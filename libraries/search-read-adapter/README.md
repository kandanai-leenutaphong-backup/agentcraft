# Search Read Adapter

`search-read-adapter==0.1.0a1`, public import `search_read_adapter`.
The fixed-index `SearchReadClient` serves the two existing synchronous knowledge callers.
It delegates every query/count/keyed read to public `azdata`, not a second connector or
raw transport. New asynchronous callers should use `azdata` directly.

Public API: `SearchReadClient`, `SearchError`, `safe_key`. Preserved limits: query/read only,
one concurrent operation, one attempt, at most 30 seconds, 100 items and 1 MiB. Missing counts,
incomplete results, invalid keys, wrong targets, active event loops and closed clients refuse.
Credential and transport are borrowed; closure drains the active operation without closing them.

The host owns credentials, grants, domain filters/projections/citations and caller authorization.
`SearchError.status` mapping and reranker annotation spelling preserve the existing consumers.
No schema builder, publishing operation, ambient credential fallback or raw REST client is included.

Source and focused tests moved from `template_apps/shared` at baseline
`00c76c6bb55190877c3d4d4b5b3a14e55bce2cb4`. Public owner adoption is checked in shared's
template integration tests; real MITRE read-back uses only the existing local application.
Potential follow-up owner: `azdata` may absorb this sync facade if its parent accepts the
distinct sync/lifetime contract. Do not add a competing service implementation here.
