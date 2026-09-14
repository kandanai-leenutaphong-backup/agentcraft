# Resource Explorer contract

Component id: `resource-explorer`
Artifacts: `resource_explorer_api` (python, `0.1.0`), contribution kind `http-app`, entry `resource_explorer_api.app:app`; `resource-explorer-frontend` (npm, `0.1.0`), contribution kind `spa`, entry `frontend`
Depends: `azdata>=3.2.0,<4` (bundled snapshot in this skill, public top-level surface only)

Version `1` of the wire schema. [`contracts/tree.schema.json`](contracts/tree.schema.json) is the machine-readable authority; where prose and schema disagree, the schema wins.

This document is written so a client can be built from it without asking a question. Everything a caller may observe is here: every route, every node kind, every status, every payload field, every bound, every rejection.

## Portable And MCP Adapters

The Python integration boundary is `ExplorerService(settings=Settings(...), access=...)`.
`build_access(settings)` selects the existing fixture or live dependency implementation. Consumers
can inject another access bundle without changing the hierarchy, content typing or wire models.

The skill-local runtime declares `azdata` as a local dependency and bundles its source, metadata
and gotchas under [vendor/azdata](vendor/azdata). No runtime import or install path points into a
sibling skill or the original repository. The browser remains an optional build, not an MCP dependency.

| MCP tool | Input | Result |
| --- | --- | --- |
| `resource_explorer_status` | empty object | configuration, scope, grants, fixture marker and config path; no network |
| `resource_explorer_tree` | optional `node` | existing `TreeResponse` wire payload |
| `resource_explorer_content` | `node` | existing `ContentResponse` wire payload |
| `resource_explorer_search` | `query`; optional `limit` | existing `SearchResponse` wire payload |

The official SDK validates tool input. Unknown arguments and malformed nodes are refused. MCP
grant or scope failures use `isError` and a fixed error category; degraded branches still return
the existing wire response, preserving `status`, `error`, `fixtures` and `truncated`.

Operator configuration is a JSON object with exactly these optional fields: `fixtures` (default
false), `allow_live_reads` (default false), `subscription_id`, `resource_group`, `max_children`
(default 100, range 1-500), `max_content_rows` (default 50, range 1-100), and `max_content_bytes`
(default 262144, range 1-1048576). Unknown fields and credential fields are refused.

Without fixture mode, reads require both the explicit grant and a subscription. Node coordinates
outside that subscription or configured resource group are refused before calling the service.
Tool input cannot change grants or targets. Scope checks are an MCP adapter policy; the underlying
HTTP application retains its original trusted-edge principal contract and is not made public by MCP.
Local stdio access is authorized through the client's process/tool permissions and operator settings.

Fixtures are explicit and stamp every response. No live target is inferred from ambient variables
by the MCP adapter. There are no write, deployment, secret-value, or arbitrary-query tools.

## 1. Routes

| Method | Path | Auth | Success | Failure |
| --- | --- | --- | --- | --- |
| GET | `/api/tree?node=<id>` | principal | `200` whenever the process can serve | `400` malformed node, `401` no principal |
| GET | `/api/content?node=<id>` | principal | `200` whenever the process can serve | `400` malformed node, `401` no principal |
| GET | `/api/search?q=<term>&limit=<n>` | principal | `200` whenever the process can serve | `400` unusable term, `422` `limit` out of range, `401` no principal |
| GET | `/health/live` | anonymous | `200 {"status":"live"}` | — |
| GET | `/health/ready` | anonymous | `200 {"status":"ready"}` | `503 {"status":"not-ready","reason":"settings"\|"static"}` |
| GET | `/` | principal | index or placeholder | `401` |
| GET | `/assets/{path}` | principal | asset | `401`, `404` |
| GET | `/api/openapi.json` | principal | generated schema | `401` |

On `/api/tree`, `node` omitted, empty, or the literal `root` all request the root expansion. On `/api/content` a missing `node` is a `400`.

**A discovery or read failure is data, never a status code.** Only malformed input and missing identity are non-200 on the three API routes.

Every non-anonymous response carries `Cache-Control: no-store, private` and `Vary: Cookie`. The payload names resources in a subscription and can carry their contents; a shared cache holding it for the next viewer is a disclosure, and `private` alone would still permit a browser store.

## 2. Types

```ts
type NodeStatus =
  | "ok" | "empty" | "forbidden" | "unreachable" | "unconfigured" | "unavailable";

type ContentKind =
  | "none" | "text" | "json" | "csv" | "markdown" | "image" | "binary" | "rows";

type NodeKind =
  | "root" | "resource_group" | "resource_type" | "resource"
  | "collection" | "arm_child" | "properties"
  | "blob_container" | "blob_folder" | "blob"
  | "cosmos_database" | "cosmos_container"
  | "gremlin_database" | "gremlin_graph"
  | "kusto_database" | "kusto_table"
  | "search_index" | "search_field"
  | "log_table"
  | "registry_repository" | "registry_tag";

type DetailValue = string | number | boolean | null;

interface TreeNode {
  id: string;                                   // opaque token, or "root"
  label: string;
  kind: NodeKind;
  expandable: boolean;                          // GET /api/tree returns children
  hasContent: boolean;                          // GET /api/content returns a payload
  status: NodeStatus;                           // what is known about this child
  detail: Record<string, DetailValue> | null;
  error: string | null;                         // null iff status is "ok" or "empty"
}

interface TreeResponse {
  schemaVersion: 1;
  fixtures: boolean;                            // true when fake discovery produced this
  node: string;
  label: string;
  kind: NodeKind;
  breadcrumb: string[];                         // labels root -> this node, inclusive
  status: NodeStatus;                           // the outcome of THIS expansion
  children: TreeNode[];
  truncated: boolean;
  hasContent: boolean;
  detail: Record<string, DetailValue> | null;
  error: string | null;
  observedAt: string;                           // UTC ISO-8601, second resolution, Z
}

interface ContentResponse {
  schemaVersion: 1;
  fixtures: boolean;
  node: string;
  label: string;
  kind: NodeKind;
  breadcrumb: string[];
  status: NodeStatus;
  contentKind: ContentKind;
  mediaType: string;
  text: string | null;                          // text | json | csv | markdown | binary preview
  dataBase64: string | null;                    // image | binary
  rows: Record<string, unknown>[] | null;       // rows
  columns: string[] | null;                     // rows
  sizeBytes: number;                            // size of the UNDERLYING object
  truncated: boolean;
  detail: Record<string, DetailValue> | null;
  error: string | null;
  observedAt: string;
}

interface SearchHit {
  node: string;                                 // expandable directly
  label: string;
  kind: NodeKind;                               // "resource" or "resource_group"
  resourceGroup: string;
  type: string;
  location: string;
  matchedIn: string;                            // name|type|resourceGroup|location|tags|properties
  detail: Record<string, DetailValue> | null;
}

interface SearchResponse {
  schemaVersion: 1;
  fixtures: boolean;
  query: string;                                // the trimmed term that ran
  status: NodeStatus;
  hits: SearchHit[];
  truncated: boolean;
  error: string | null;
  observedAt: string;
}
```

JSON keys are camelCase; the server's attributes are snake_case. `schemaVersion` is `1` and a breaking change to any field above requires `2` or a parallel endpoint.

`status` on a response describes *this* call. `status` on a child describes only what is already known about the child: a child is never speculatively probed, so a successfully discovered child is `ok` even where expanding it would fail.

`expandable` and `hasContent` are independent. A Kusto table has contents and no children; a Search index has both; a resource group has children and no contents.

`fixtures` is mandatory on all three payloads. Numbers from nowhere presented as real is the failure a fixture mode exists to avoid.

## 3. Statuses

| Status | Means | Who fixes it |
| --- | --- | --- |
| `ok` | children or contents returned | — |
| `empty` | the call succeeded and there is nothing there | nobody; it is a true answer |
| `forbidden` | the identity lacks a data or control-plane role | a role grant |
| `unreachable` | network, private DNS, a storage network rule, or a budget overrun | a network change; **a role grant does nothing** |
| `unconfigured` | a coordinate nobody set | an operator, and `error` names the variable |
| `unavailable` | the service refused, an SDK is missing, or a provider declares no api-version | depends; `error` says |

`truncated` is a boolean beside these, not a seventh status: a truncated listing did succeed.

A storage account blocked by a network rule answers HTTP 403 `AuthorizationFailure`, which is indistinguishable from a missing role by status code alone. `azdata` separates them: `AuthorizationFailure` renders `unreachable` with a cause naming public network access, and `AuthorizationPermissionMismatch` stays `forbidden`.

## 4. Hierarchy

The tree is the subscription, and every level below it is discovered rather than configured.

| Node | Expands into | Child kind |
| --- | --- | --- |
| `root` | every resource group in the subscription, or the one `AZDATA_RESOURCE_GROUP` names | `resource_group` |
| `resource_group` | one group per ARM type, labelled `Type (n)` | `resource_type` |
| `resource_type` | the resources of that type in that group | `resource` |
| `resource` | its `properties` leaf, then the branches its type declares | `properties`, `collection` |
| `collection` (ARM) | one ARM child collection: `GET {resourceId}/{collection}` | `arm_child` |
| `arm_child` | its own `properties` leaf, plus any branches its own type declares | `properties`, `collection` |
| `collection` (blob) | the account's containers | `blob_container` |
| `blob_container`, `blob_folder` | one prefix level, folders and blobs together | `blob_folder`, `blob` |
| `collection` (cosmos / gremlin) | databases | `cosmos_database`, `gremlin_database` |
| `cosmos_database`, `gremlin_database` | containers or graphs | `cosmos_container`, `gremlin_graph` |
| `collection` (kusto) | databases | `kusto_database` |
| `kusto_database` | tables | `kusto_table` |
| `collection` (search) | indexes | `search_index` |
| `search_index` | fields, flattened three levels as `parent/child` | `search_field` |
| `collection` (logs) | the workspace's tables, its own tables first | `log_table` |
| `collection` (acr) | repositories | `registry_repository` |
| `registry_repository` | tags | `registry_tag` |

Leaves — `properties`, `blob`, `cosmos_container`, `gremlin_graph`, `kusto_table`, `search_field`, `log_table`, `registry_tag` — answer `empty` with no children and make no call. Several of them still have contents; having nothing below you and having nothing to say are different facts.

Grouping a resource group's resources by type is **this component's** composition. `azdata` returns the flat listing.

### 4.1 What each resource type opens into

Every resource of every type, known or unknown, gets a `properties` leaf holding its complete ARM JSON. That is what makes the tree general: a type nobody anticipated is browsable the day it appears. The table below adds branches on top of that leaf, and is the whole of [`backend/src/resource_explorer_api/facets.py`](backend/src/resource_explorer_api/facets.py).

| ARM type | Branches |
| --- | --- |
| `microsoft.storage/storageaccounts` | Blob containers (data plane); Tables, Queues, File shares (ARM) |
| `microsoft.documentdb/databaseaccounts` | SQL databases, Gremlin databases (both, always) |
| `microsoft.search/searchservices` | Indexes |
| `microsoft.kusto/clusters` | Databases |
| `microsoft.operationalinsights/workspaces` | Log tables |
| `microsoft.containerregistry/registries` | Repositories |
| `microsoft.app/containerapps` | Revisions |
| `microsoft.app/containerapps/revisions` | Replicas |
| `microsoft.app/jobs` | Executions |
| `microsoft.app/managedenvironments` | Certificates, Storages |
| `microsoft.cognitiveservices/accounts` | Model deployments, Projects |
| `microsoft.keyvault/vaults` | Secrets (names only), Keys (names only) |
| `microsoft.network/virtualnetworks` | Subnets |
| `microsoft.network/networksecuritygroups` | Security rules |
| `microsoft.eventgrid/systemtopics` | Event subscriptions |
| anything else | the `properties` leaf alone |

Both Cosmos branches appear on every account because the API is not reliably readable from the ARM type. Showing both and letting the wrong one answer `empty` is honest; guessing is not.

Key Vault lists secret and key **names and metadata**. Values need a data-plane read this component never issues.

## 5. Contents

`GET /api/content?node=<id>` answers for any node whose `hasContent` is true. Any other node answers `200` with `status: "empty"` and `contentKind: "none"`.

| Kind | Source | `contentKind` |
| --- | --- | --- |
| `properties` | ARM `GET {resourceId}` at the resolved api-version | `json` |
| `blob` | a ranged blob download | typed, see below |
| `cosmos_container` | `SELECT TOP n * FROM c` over the SQL endpoint | `rows` |
| `gremlin_graph` | the same query; a graph's vertices are documents | `rows` |
| `kusto_table` | `["table"] \| take n` | `rows` |
| `search_index` | `search("*", top=n)` | `rows` |
| `log_table` | `table \| take n` over `api.loganalytics.io`, timespan `P7D` | `rows` |

Exactly one of `text`, `dataBase64` and `rows` carries the payload, named by `contentKind`:

| `contentKind` | `text` | `dataBase64` | `rows` / `columns` |
| --- | --- | --- | --- |
| `text`, `csv`, `markdown` | the decoded text | — | — |
| `json` | pretty-printed, two-space indent | — | — |
| `image` | — | the bytes | — |
| `binary` | a hex-and-ASCII preview, 512 bytes | the bytes | — |
| `rows` | — | — | the sample |
| `none` | — | — | — |

`sizeBytes` is the size of the *underlying* object, not of what was returned; they differ exactly when `truncated` is true, which is how a client says "64 KiB of 4 GiB" rather than implying the file is small. For `rows` it is the number of rows returned.

### 5.1 How bytes are typed

Claimed media type first, then the name, then the bytes. Any of the three can settle it, because blob storage defaults an unset content type to `application/octet-stream` and a great many real blobs are uploaded that way.

- `image/png|jpeg|gif|webp|bmp|avif|x-icon` → `image`. **`image/svg+xml` is never `image`**: it is a script-bearing document, and rendering one from a storage account inside the explorer's own origin would be a stored-XSS surface. It arrives as `binary`.
- `application/json`, `text/json`, `*+json` → `json`, pretty-printed. JSON that no longer parses (a truncated read) degrades to `text` rather than failing.
- `text/markdown` → `markdown`; `text/csv`, `text/tab-separated-values` → `csv`; other `text/*` → `text`.
- An uninformative claim falls back to the file suffix, then to magic numbers (`PNG`, `JPEG`, `GIF`, `PDF`, `ZIP`, `GZIP`, `ELF`) and a JSON sniff.
- Anything undecodable as UTF-8, or containing control bytes, is `binary` — including a blob that *claimed* to be text. A mojibake pane is worse than an honest hex dump.

`mediaType` is the resolved type, safe to place in a `data:` URL for `image`.

## 6. Search

`GET /api/search?q=<term>&limit=<n>` runs one Azure Resource Graph query across the subscription. It matches a resource's name, type, resource group, location, tags and property bag, and separately matches resource-group names and locations. `matchedIn` says which.

Every hit carries a `node` the tree accepts, so a hit opens without walking down to it.

`q` is trimmed, must be 1–200 characters, and is interpolated as a verbatim KQL literal (`@'...'`, doubling any quote, control characters stripped). Nothing else from the caller reaches the query. An empty or oversized term answers `400 {"error":"invalid_query","schemaVersion":1}`. `limit` is clamped to 1–200 by the route; a value outside that range is a `422` from validation.

`query` in the response is the one place client input is echoed, and only after it has passed the length bound.

## 7. Node ids

```
token   = base64url( json(payload, sort_keys=True, separators=(",", ":")) ).rstrip("=")
payload = {"v":1, "s":"<service>", "l":"<level>", "p":[<coordinate strings>], "k":"<kind>"}
```

`root` is the one literal id. Everything else is opaque: a client constructs no ids, parses none, and derives nothing from one. Base64url is query-safe, so names containing `/`, `:`, spaces and unicode round-trip — an index literally named `assets/v1: beta` is addressable.

`p[0]` is always the ARM resource id the node hangs off; every service coordinate — subscription, resource group, account name, blob endpoint, Cosmos endpoint, search endpoint, registry login server — is derived from it server-side. Only the Kusto query URI cannot be, because it carries a region, so it is read from ARM once per cluster and cached.

Addressable coordinates:

| Service | Levels |
| --- | --- |
| `estate` | `resource_group`, `type`, `resource`, `collection`, `child`, `properties` |
| `blob` | `account`, `container`, `blob` |
| `cosmos` | `account`, `database`, `container` |
| `gremlin` | `account`, `database`, `graph` |
| `kusto` | `cluster`, `database`, `table` |
| `search` | `service`, `index`, `field` |
| `logs` | `workspace`, `table` |
| `acr` | `registry`, `repository`, `tag` |

Every rejection answers `400 {"error":"invalid_node","schemaVersion":1}` with `no-store`:

| Input | Behaviour |
| --- | --- |
| token longer than 8192 chars | 400, checked before decoding |
| non-base64url characters, bad padding, non-UTF-8 | 400 |
| payload not a JSON object | 400 |
| `v` absent or not `1` | 400 |
| `s` not a registered service | 400 |
| `l` not a level that service declares | 400 |
| `k` not a known kind, or inconsistent with `(s, l)` | 400 |
| `p` not a list of strings, more than 4 elements, or an element over 1024 chars | 400 |

The response **never echoes the submitted token or any decoded fragment**. The client already has the token; reflecting it makes the endpoints that accept client input a reflection surface for no benefit. A rejected token is logged at debug as a 12-character SHA-256 prefix only.

Depth is intrinsically bounded: `l` must be a declared level, levels are finite, and `p` is capped, so no crafted id can walk deeper than the deepest declared level.

## 8. Bounds

| Constant | Value | Where |
| --- | --- | --- |
| `MAX_CHILDREN` | 500 | final server clamp, and `DiscoveryBounds.max_items` |
| `MAX_DETAIL_KEYS` | 40 | per node |
| `MAX_DETAIL_VALUE_CHARS` | 500 | per value, truncated with `…` |
| `MAX_CONTENT_BYTES` | 1 048 576 | one content read |
| `MAX_CONTENT_ROWS` | 100 | one row sample |
| `MAX_TEXT_CHARS` | 200 000 | rendered text, truncated with `…` |
| `MAX_HEX_PREVIEW_BYTES` | 512 | binary preview |
| `MAX_SEARCH_TERM_CHARS` | 200 | one query |
| `MAX_SEARCH_HITS` | 200 | one result set |
| `DISCOVERY_TIMEOUT_SECS` | 15.0 | one expansion's discovery budget |
| `CONTENT_TIMEOUT_SECS` | 25.0 | one content read's budget |
| `REQUEST_TIMEOUT_SECS` | 20.0 | whole-request budget; exceeding it renders `unreachable` |
| `INVENTORY_TTL_SECS` | 30 | resource-group listing and cluster-URI caches, single-flighted |
| `MAX_TOKEN_CHARS` | 8192 | node id |
| `MAX_PATH_SEGMENTS` | 4 | node id |
| `MAX_PATH_SEGMENT_CHARS` | 1024 | node id |

`truncated` is true when `azdata` truncated **or** the server clamp applied. There is no paging cursor: a cursor is a contract, and no observed estate has needed one. A Log Analytics workspace declares around 690 tables against the 500 clamp, so that branch is routinely `truncated: true`; the workspace's own custom tables are ordered first, because those are the ones holding data.

## 9. Configuration

The only coordinate the tree needs is `AZDATA_SUBSCRIPTION_ID`. Everything else — resource groups, storage accounts, Cosmos accounts, search endpoints, Kusto clusters, workspaces, registries — is discovered.

| Variable | Effect |
| --- | --- |
| `AZDATA_SUBSCRIPTION_ID` | **required**; absent, the root renders `unconfigured` naming it |
| `AZDATA_RESOURCE_GROUP` | optional; narrows the root to one group |
| `RESOURCE_EXPLORER_FAKE_DISCOVERY=1` | serve the fixture estate; every response is `fixtures: true` |
| `RESOURCE_EXPLORER_DEV_PRINCIPAL=1` | skip the principal check; **ignored whenever `CONTAINER_APP_NAME` is set** |
| `RESOURCE_EXPLORER_STATIC_DIR` | where the built SPA lives |
| `RESOURCE_EXPLORER_MAX_CHILDREN` | lower the clamp; can never raise it above 500 |
| `RESOURCE_EXPLORER_MAX_CONTENT_BYTES`, `RESOURCE_EXPLORER_MAX_CONTENT_ROWS` | lower the content caps; never raise them |
| `RESOURCE_EXPLORER_DISCOVERY_TIMEOUT_SECS`, `RESOURCE_EXPLORER_CONTENT_TIMEOUT_SECS`, `RESOURCE_EXPLORER_REQUEST_TIMEOUT_SECS`, `RESOURCE_EXPLORER_INVENTORY_TTL_SECS` | budgets |

An unparseable number falls back to its default rather than raising. One bad variable must not stop an explorer whose job is to be reachable when the estate is not.

## 10. Permissions

Read only, at subscription scope. Operation class: **read**. Nothing here writes, provisions, ingests or deletes, and `tests/fitness.py` check 3 fails on any reference to `azdata`'s write or deploy planes.

| Branch | Required role |
| --- | --- |
| Resource groups, resources, ARM children, `properties`, search | `Reader` on the subscription |
| Blob containers, folders, blob bytes | `Storage Blob Data Reader` |
| Cosmos and Gremlin databases, containers, graphs | ARM `Reader` (management plane) |
| Cosmos and Gremlin documents | a Cosmos DB built-in data reader role assignment |
| Search indexes and fields | `Search Service Contributor` grade (index *definitions* are control plane) |
| Search documents | `Search Index Data Reader` (a different grant from the one above) |
| Kusto databases | ARM `Reader` on the cluster |
| Kusto tables and rows | `AllDatabasesViewer` on the cluster |
| Log Analytics tables | ARM `Reader`; rows additionally need `Log Analytics Reader` |
| Registry repositories and tags | `AcrPull` grade on the registry |

Credentials are injected, never constructed from another component's state. The identity is the caller's workload identity via `azdata`'s credential provider.

**No credential value ever leaves this process.** ARM documents pass through `azdata`'s `redact_credentials`, which replaces any value under a credential-shaped key — `primaryKey`, `connectionString`, `clientSecret`, `password` and seventeen other fragments — at any depth. Key Vault values are never read at all.

## 11. Health and lifecycle

`/health/live` reads no configuration and makes no Azure call. `/health/ready` asks two local questions — did settings parse, is `index.html` on disk — and never depends on Azure reachability: a fully 403'd estate is a *healthy* explorer showing forbidden branches, and a readiness probe that failed on it would restart the one process able to explain the problem. Neither body carries a resource, subscription or tenant identifier, which is why both may answer anonymously.

Initialization builds no credential and opens no socket. There is no durable state, no migration and no background worker; shutdown is process exit. Removal is deleting the app-manifest entry and the package dependency.

## 12. Security

`PrincipalGuard` is pure ASGI, added last so it wraps routing: an unknown path answers `401` to an anonymous caller, not `404`, because a 404 tells a prober which paths exist. Accepted headers are `x-ms-client-principal` and `x-ms-client-principal-id`, non-empty. A `401` carries zero bytes.

It is a component-owned copy of the pattern, deliberately not an import from a sibling component: that edge is forbidden, and a shared guard would make two deployments share one lock.

`/assets/{path}` resolves per request — a start-time mount 404s every asset built after the image layer that installed this package — and rejects anything not `is_relative_to` the resolved assets directory with `404`.

## 13. Errors

| Category | Status | Retryable |
| --- | --- | --- |
| `invalid_node` | 400 | no; the client must re-request from a payload this server produced |
| `invalid_query` | 400 | no; the term must change |
| `limit` outside 1–200 | 422 | no |
| missing principal | 401 | no |
| unknown path, absent asset | 404 (authenticated) | no |
| not ready | 503 | yes |
| every discovery or read failure | 200 with a `status` | `unreachable` and `unavailable` yes; `forbidden` and `unconfigured` need an operator |

No response body contains a secret, a key, a connection string or a full URL: every string that came from an exception passes through `azdata`'s `sanitize_detail`.

## 14. Evidence

- `backend/tests/` — 180 tests, no network: node codec round-trip and every rejection row, hierarchy composition covering every declared kind by walking from the root, prefix-to-tree synthesis, content typing for each rendering, each failure status as node state, estate search including hit addressability, guard behaviour including the Azure-marker bypass refusal, health, static, and payload/schema agreement in both directions.
- `tests/fitness.py` — 6 checks, each run against a mutated copy that must trip it.
- `frontend/tests/` — 85 vitest tests across 4 files: wire parsing, tree and selection state, keyboard navigation, and content rendering.
- `frontend/e2e/` — 103 Playwright tests, 2 skipped, run against the fixture estate: expansion, breadcrumbs, search, the help dialog, both themes, every content kind, every status branch, and the shipped viewports.
- `npm run typecheck`, `npm run lint`, `npm run build` — clean; the production bundle is 260.47 kB, 80.06 kB gzipped.
- Live acceptance from the source was not rerun during migration. Azure access, trusted-proxy authentication and private-network reachability remain unverified here. The marked fixture results above do not substitute for those checks; no original subscription or resource identifiers are needed to replicate them.
