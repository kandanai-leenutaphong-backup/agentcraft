# Integration Evidence

Observed 2026-09-15. This supplements the [historical research](README.md), not a live-access claim.
The [implemented contract](../CONTRACT.md) owns current behavior.

## Reuse Decisions

| Area | Decision And Evidence |
| --- | --- |
| Blob/Table | Extend the existing Azure Core bridge, use official async clients and native pagination/conditions. SDK tests exposed case-insensitive headers and Blob stream `response`, `content_length`, `properties` and primary-location metadata requirements. JSON blobs retain exact bytes. |
| Kusto | Reuse public `ClientRequestProperties`, `DataFormat`, `IngestionProperties` and response models. The installed 5.0.2 async client constructs its own HTTP session without a public bounded-transport hook; the ingestion package has no `aio` module. One guarded Azure Core path preserves the shared safety contract. |
| SQL/PostgreSQL | Use Microsoft `mssql-python`, Psycopg and SQLGlot. Driver-bound values follow rendered placeholder order, not AST traversal order. No SDK-specific object escapes the common result. Blocking workers own their connections through cleanup; PostgreSQL read queries also use read-only transactions. |
| GraphModel | Use documented REST query, definition and refresh/job APIs over Azure Core. Check GQL status separately from HTTP; bind operation references to connector/target/principal; respect each Retry-After. Graph refresh is not record CRUD or batch-content proof. |
| Gremlin | Reuse Gremlin Python protocol/SASL and GraphSON v2. A small implementation of its public transport contract uses aiohttp for exact-URL, redirect, frame and deadline enforcement. The driver is not an authorization or read-only-query parser. |

## Gremlin Prerequisites

Microsoft documents [resource tokens for Gremlin](https://learn.microsoft.com/en-us/azure/cosmos-db/gremlin/how-to-use-resource-tokens),
including the native driver username and token-as-password shape. Issuing those tokens is a
privileged external workflow; this library neither obtains account keys nor creates permissions.
The host supplies `get_token(scope)` returning a scoped resource token and expiry, and selects
`credential_kind="resource_token"`. Default Entra mode refuses Gremlin traversal execution.

The [compatibility page](https://learn.microsoft.com/en-us/azure/cosmos-db/gremlin/support)
recommends 3.4.x and rejects bytecode/GraphSON v3/lambdas/transactions. Installing 3.4.13 here
selected Tornado 5.1.1, which failed importing `collections.MutableMapping` on Python 3.11.
That dependency was removed. Version 3.7.7 imports and its real GraphSON-v2 eval/SASL path
passes offline tests, but this is not proof of cloud compatibility. No obsolete dependency
was monkey-patched and no direct Entra traversal recipe was invented.

## Current Official References

Fetched with the repository web-resource tool, public-only/robots/rate-limit checks enabled:

- [Gremlin security](https://learn.microsoft.com/en-us/azure/cosmos-db/gremlin/security).
- [Resource tokens](https://learn.microsoft.com/en-us/azure/cosmos-db/gremlin/how-to-use-resource-tokens).
- [Gremlin compatibility](https://learn.microsoft.com/en-us/azure/cosmos-db/gremlin/support).
- [GraphModel beta query](https://learn.microsoft.com/en-us/rest/api/fabric/graphmodel/items/execute-query%28beta%29).
- [GraphModel definition](https://learn.microsoft.com/en-us/rest/api/fabric/graphmodel/items/get-graph-model-definition).
- [Graph refresh](https://learn.microsoft.com/en-us/rest/api/fabric/graphmodel/background-jobs/run-on-demand-refresh-graph).

The implementation pass stored its acquisition cache and URL/time/SHA-256 provenance at
`/tmp/agentcraft-azdata-all-docs/manifest.json`. That temporary cache was absent after crash
recovery on 2026-09-15; its hashes were not reverified during recovery. The source links above
permit reacquisition, not a promise that future source bytes match. The earlier research
baseline still has committed [acquisition metadata](acquisitions.json). Third-party pages
remain internal reference material, not vendored documentation or copied runtime code.

## Dependency Terms

Provider packages are dependencies, not copied source. Azure SDKs and SQLGlot carry their
upstream license metadata; TinkerPop uses Apache-2.0; Psycopg uses LGPLv3. The Microsoft SQL
wrapper's license does not relicense its native binaries. Hosts must review current native
driver/platform redistribution terms. No claim that all installed dependencies are MIT is made.