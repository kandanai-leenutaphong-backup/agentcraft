# Operational Migration Notes

For **`azdata` 4.0.0a3**. The [implemented contract](CONTRACT.md) remains the API
authority. This guide migrates reusable failure knowledge, not the v3 runtime.
The retirement assessment (outside-guidance-not-advertised; source reference: `../CONNECTOR_RETIREMENT.md`) records remaining gaps.

## Provenance

Source: the original data skill's GOTCHAS.md (missing-not-advertised; source reference: `../../.github/skills/azure-data-connectors/GOTCHAS.md`),
entries G1-G27, at Git revision `5a216df1189708999f6e47bd524092ad2b56a5b1`.
Reconciled against the current contract and source on 2026-09-15. Historical
incident descriptions are retained as leads, not newly reproduced live evidence.
G26 and G27 were explicitly qualified in the source, not live-verified findings.

The source remains with its independently installable v3 skill while that runtime
is supported. This library owns the v4 interpretation below; installing v4 does
not make the old examples, symbols, credential recipes or status envelopes valid.

## Findings And Applicability

| Source | Retained Finding | Application To v4 |
| --- | --- | --- |
| G1 | A WebSocket authenticated with an expiring credential needs renewal. | Gremlin obtains resource tokens for new connections. Direct Entra traversal authentication is **not** implemented; do not transfer the old bearer-token recipe. The host owns secure token issuance. |
| G2 | A synchronous driver that manages an event loop cannot run inline on an async request loop. | Native Gremlin work uses a worker; preserve its cancellation/cleanup behavior. Do not replace it with nested `run_until_complete`. |
| G3 | Holding a concurrency permit during retry backoff can starve other requests. | **Gap:** bounded v4 SDK retries and its per-connector gate are not the legacy permit-release/adaptive-throttle mechanism. No endpoint-wide fairness claim. |
| G4 | Search semantic quota exhaustion is different from a service outage. | **Gap:** automatic semantic-to-keyword fallback is not implemented. Choose any degradation explicitly at the host; do not promise the same ranking or silently replay a changed query. |
| G5 | Lazy Search pagers can fail during iteration, not only when created. | Test consumption as well as construction. SDK paging is reused, but the legacy semantic-quota fallback at both failure sites is not inherited. |
| G6 | Zero concurrency can deadlock without an exception. | `Policy.max_concurrency` validates 1-64. Invalid limits refuse rather than silently clamp to an invented value. |
| G7 | HTTP 200 can carry a failed or incomplete GQL result. | Graph query requires preview opt-in and checks body status/data. Native continuations and local truncation are explicit. The old `02000` handling is not an interchangeable wire contract. |
| G8 | Closing a borrowed credential can break unrelated clients. | Credentials and injected transports are borrowed. Close owned SDK/default transport resources with `aclose()`; the host closes its credential. |
| G9 | A failed refresh should not be confused with service unavailability. | Azure SDK token policies own caching/refresh. The old custom cached-token fallback is not a v4 guarantee; never introduce use of expired tokens as a recovery path. |
| G10 | Text query filters are not an authorization sandbox. | Cosmos still uses a SELECT-prefix guard. Other adapters enforce their documented subsets. Host authorization and appropriately scoped service credentials remain required. |
| G11 | Catch-all health checks can hide programming defects as an unhealthy service. | v4 leaves programming defects as exceptions. Keep a positive healthy-path test as well as provider-error tests; `describe().availability` is `unverified`, not a health probe. |
| G12 | A pre-query Gremlin 403 may involve network routing, not only identity. | Check the actual network/private-endpoint path and credential independently. A historical account observation does not justify disabling network controls or changing authentication. |
| G13 | Gremlin has no general batch mutation or automatic idempotency. | v4 vertex upsert and transactions are unsupported. Do not label repeated `addV` calls or a timeout retry safe bulk ingestion. |
| G14 | Azure Policy can rewrite an accepted ARM request. | Infrastructure provisioning is not implemented here. Any future owner must read back requested state; this finding grants no policy exemption or cloud mutation authority. |
| G15 | KQL `has` is term-based; `contains` is substring-based. | Choose the expression deliberately. The query adapter does not rewrite one into the other; matching semantics and query cost differ. |
| G16 | Parallel aggregates can exhaust shared Kusto/Fabric capacity. | Concurrency is bounded **per connector**, not across connectors/processes sharing an endpoint. Coordinate shared capacity at the host; no automatic endpoint warm-up or tuning is provided. |
| G17 | A removed SDK keyword can be silently absorbed by `**kwargs`. | Set query partition via `service_options={"cosmos": {"partition": value}}`. Without it the query covers the configured container. Do not pass the obsolete `enable_cross_partition_query` flag or invent a partition. |
| G18 | Azure management SDK model shapes differ; a generic normalizer can invent drift. | **Gap:** v4 has no management provisioner to replace these model-specific normalization/tests. Preserve them with any future infrastructure owner. |
| G19 | An accepted write is not proof that the requested setting persisted. | Infrastructure drift checks remain missing. Data operations expose acceptance and requested evidence separately; never turn `pending` or `unknown` into success. |
| G20 | Search document acceptance can precede visibility. | Request bounded `presence` or `content` verification. Content checks require declared retrievable fields; finding stale content is not proof of the requested update. |
| G21 | A wrong Cosmos partition can produce a convincing but misleading 404. | Read/delete use explicit key and partition; default missing behavior is an error. Absence evidence proves only that supplied address, not global ID absence or correct caller addressing. |
| G22 | A Gremlin `drop()` matching nothing may return without error. | Use exact key/partition and supported absence evidence. Native completion alone does not prove a previously existing vertex changed; absence is scoped to the supplied address. |
| G23 | Interpolated Gremlin property values can become traversal syntax. | Keep scalar validation, generated mutation traversals and the parsed read-only subset in the adapter. Never assemble a traversal from unchecked caller strings. |
| G24 | Missing-dependency tests are unreliable if they depend on local packages being absent. | Simulate the loader failure or use an isolated base install. A developer environment with all extras installed is not missing-extra evidence. |
| G25 | A writer cache that omits policy can leak a wider grant. | Each connector binds one immutable policy and target. Any host cache must include every authority-affecting input; never reuse a wide-grant connector for a narrow caller. |
| G26 | ARM inventory can succeed while the data plane is unreachable. | **Gap:** v4 has no hierarchical discovery/estate API. Inventory existence, data reachability and user authorization remain separate observations. |
| G27 | Reading Search schema and reading documents can require different permissions. | Local `schema.read` policy is not an Azure role assignment. Verify the exact service operation/role separately; do not automatically grant a write-capable role for a read-only workflow. |

## Evidence To Preserve

Current offline regression owners:

- Boundary tests (source-or-asset-not-bundled; source reference: `tests/contract/test_boundary.py`): configuration, grants, immutable
  target and unsupported-operation refusal.
- Search tests (source-or-asset-not-bundled; source reference: `tests/adapters/test_search.py`): native Search requests, paging,
  schema operations and read-back behavior.
- Cosmos tests (source-or-asset-not-bundled; source reference: `tests/adapters/test_cosmos.py`): partitioned requests, mutation
  outcomes and SDK behavior.
- Graph tests (source-or-asset-not-bundled; source reference: `tests/adapters/test_graph.py`): response/body evidence and job scope.
- Gremlin tests (source-or-asset-not-bundled; source reference: `tests/adapters/test_gremlin.py`) and
  transport tests (source-or-asset-not-bundled; source reference: `tests/adapters/test_gremlin_transport.py`): generated operations,
  credential restrictions and native protocol boundary.
- SDK-boundary tests (source-or-asset-not-bundled; source reference: `tests/contract/test_transport.py`) and
  dependency tests (source-or-asset-not-bundled; source reference: `tests/contract/test_dependencies.py`): bounded transport and
  optional dependency behavior.

The original skill still owns its provisioning, discovery, observation, full
snapshot/diff verification, content, estate and live-environment tests. Do not
delete those as redundant: addressed CRUD verification is a different contract.
The [verification record](VERIFICATION.md) distinguishes source tests from artifact
and live evidence. No live service behavior was reverified for this migration.