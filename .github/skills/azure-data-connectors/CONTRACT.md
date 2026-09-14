# CONTRACT.md — azure-data-connectors

Everything needed to reimplement this box in another language, or to write
a consumer against it without reading the Python. Shapes are exact; the
constants are the ones that were tuned against live services.

---

## 1. Result shapes

Every connector except `GraphConnector` returns a **JSON string**.
`GraphConnector` returns a **dict**, because every caller projects before
serialising and a string would force an immediate re-parse.

### 1.1 Failure envelopes

```json
{"error": true, "detail": "<sanitised, <=500 chars>"}
{"degraded": true, "detail": "<sanitised, <=500 chars>"}
```

Key order is insertion order. `error` and `degraded` are distinct and never
both present.

* `error` — the call failed and produced no answer.
* `degraded` — an answer exists at reduced fidelity (breaker open, paid
  ranker unavailable). A caller may proceed.

Sanitisation, applied to every detail string, in this order:

1. Replace every match of `https?://\S+` with the literal
   `<redacted-url>`.
2. Truncate to 500 characters.

Non-string details are coerced with the language's string conversion
before step 1.

When an exception is attached, the detail is built first as
`"{detail}: {ExceptionTypeName}: {exception}"`, or
`"{ExceptionTypeName}: {exception}"` when the detail is empty, and *then*
sanitised.

### 1.2 Success shapes

| Connector | Success payload |
| --- | --- |
| Gremlin | The driver result, serialised as a bare JSON array |
| KQL | `{"columns": [{"name": str, "type": str}, ...], "rows": [{column: value}, ...]}` |
| Search | `{"results": [<project_doc output>, ...], "count": int}` |
| Graph | `{"columns": [...], "data": [...]}` (dict, not a string) |
| Cosmos | No wire shape — exposes the container client |

Values exposing an `isoformat` method are converted to their ISO-8601
string during KQL shaping, before serialisation. Everything else is
serialised with a default `str` fallback so an unexpected SDK type cannot
raise inside the result path.

### 1.3 The `ok` envelope

Mutations — the write plane and the deploy plane — return one further
shape. Reads never do: a caller projecting search hits must not have to
unwrap an operation envelope first.

```json
{"ok": true, "operation": "<verb>", ...operation-specific keys}
```

Key order is insertion order and is part of the contract: `ok` first,
`operation` second, then the operation's own keys in the order tabulated
below. `ok` is never present together with `error` or `degraded`.
Serialisation uses the same `str` fallback as section 1.2.

Per operation:

| `operation` | Keys after `operation`, in order |
| --- | --- |
| `create`, `upload`, `delete` | `service`, `count`, `failed`, `verified` |
| `read` | `service`, `count`, `results` |
| `ensure` | `resource_kind`, `name`, `created`, `verified`, `state`, `drift` |
| `teardown` | `resource_kind`, `name`, `deleted`, `verified` |
| `describe` | `resource_kind`, `name`, `present`, `state`, `resource` |
| `stats` | `service`, `target`, `collected_at`, `source`, `stats`, `partial` |
| `verify` | `service`, `target`, `matched`, `expected`, `observed`, `before`, `after`, `elapsed_ms` |

Field meanings:

| Field | Type | Meaning |
| --- | --- | --- |
| `service` | string | `"search"`, `"cosmos"` or `"gremlin"` |
| `count` | int | Items that **succeeded**. Failures are excluded |
| `failed` | array | Per-item results whose `ok` is false. Never empty-by-omission: the key is always present |
| `verified` | bool | Whether the state was read back after the write |
| `results` | array | Zero or one item for `read`; `count` is 0 or 1 to match |
| `created` | bool | The resource was absent before this `ensure` |
| `deleted` | bool | The resource was present before this `teardown` |
| `state` | string | Provisioning state as reported, or `""` when none was found |
| `drift` | object | Requested fields that did not survive. Always `{}` on a success envelope; a non-empty drift is returned as an **error** instead |
| `present` | bool | The resource exists |
| `resource` | object | The normalised dict view of the live resource |

### 1.4 The per-item result shape

Every write and delete produces one of these per item, and they are what
`failed` contains:

```json
{"key": <any>, "ok": <bool>, "detail": "<string>"}
```

* `key` is whatever the connector's key extraction produced. For Search and
  Gremlin that is the scalar key field. For Cosmos it is the **pair**
  `[id, partition_key]`, because the base class verifies a write by
  re-reading the keys it was handed and a bare id cannot be read.
* `detail` is empty-safe: a failure with no message from the service is
  given one (`"indexing failed with status <n>"` on Search). Details in
  `failed` are sanitised with the same rule as section 1.2.
* `ok: false` is an **outcome**, not an exception. A 409 from a Cosmos
  create, a 404 from a Cosmos delete and an already-present Gremlin id all
  arrive here rather than aborting the batch.

### 1.5 The `stats` envelope

The observe plane returns one shape, for every service:

```json
{"ok": true, "operation": "stats", "service": "cosmos", "target": "hc/items",
 "collected_at": "2026-08-30T12:00:00Z", "source": "data-plane",
 "stats": {}, "partial": []}
```

Key order is insertion order and is part of the contract, in the order
above. `collected_at` is UTC, ISO-8601, second resolution, `Z`-suffixed.

`source` is exactly one of `"data-plane"`, `"management-plane"` or
`"monitor"`. It names the envelope's **principal** collector, not the only
one: a `data-plane` envelope routinely carries management-plane and Azure
Monitor stats alongside, and names in `partial` the ones it could not
reach.

`partial` is an array of `{"stat": "<name>", "detail": "<sanitised>"}`,
sanitised by the rule in section 1.1. Two rules, and they are the whole
contract:

* A stats call **never fails wholesale** because one counter was
  unavailable. A probe that raises costs its own stat names and nothing
  else, and the envelope is still `ok: true`. There is no `stats` error
  envelope for a partial collection.
* A stats call **never omits a counter silently**. Every stat name a
  service declares is either a key in `stats` or an entry in `partial`. An
  absent value is never reported as `0`, `""` or `null`.

A value present in `stats` was measured. `target` is `null` where the
service's stats are not scoped to one object.

### 1.6 The `verify` envelope

The verification plane snapshots, operates, snapshots again and diffs:

```json
{"ok": true, "operation": "verify", "service": "search", "target": "hc-docs",
 "matched": true, "expected": {"added": ["d1","d2"]},
 "observed": {"added": ["d1","d2"], "removed": [], "changed": [],
              "unchanged": 40, "count_before": 40, "count_after": 42},
 "before": {}, "after": {}, "elapsed_ms": 812}
```

A **mismatch is a failure**, not a warning. It returns an error envelope
carrying the same observation: `error` and `detail` first, per section 1.1,
then every key above from `operation` onward with `matched: false`. `ok`
is never present with `matched: false`.

`expected` is the caller's declared `Effect`, one key: `{"added": [...]}`,
`{"removed": [...]}`, `{"changed": [...]}`, `{"unchanged": true}`,
`{"count_delta": <int>}` or `{"any": true}`. Matching is strict — an
operation that also changed something unrequested does **not** match — and
`count_delta` additionally requires the key movement to be a pure net
change in one direction, because an add-and-remove nets to zero while every
key in the store moved.

`before` and `after` are snapshots:

```json
{"service": "search", "target": "hc-docs", "taken_at": "2026-08-30T12:00:00Z",
 "count": 40, "keys": ["d1"], "digest": "<sha256 hex>",
 "stats": {}, "sampled": false}
```

| Field | Meaning |
| --- | --- |
| `count` | Total addressable items, `-1` when the service will not count |
| `keys` | The enumerated key set, sorted, capped (section 2) |
| `digest` | sha256 hex of the sorted, deduplicated key set, newline-joined and UTF-8 encoded. Key order cannot change it |
| `stats` | The `stats` sub-object of that service's observe plane at capture time, `{}` when it could not be collected |
| `sampled` | True when the key space exceeded the cap, so `keys` and `digest` cover a deterministic sample and not the whole |

`unchanged` in `observed` is a **count** of keys present in both snapshots
whose content digest did not differ; `changed` is the list of those whose
content digest did. Where a service exposes no content digest, `changed` is
empty rather than guessed.

---

## 2. Configuration

Read once, frozen. Default prefix `AZDATA_`; pass an empty prefix to adopt
names a repository already sets.

| Variable (after prefix) | Field | Default |
| --- | --- | --- |
| `GREMLIN_ENDPOINT` | `gremlin_endpoint` | `""` |
| `GREMLIN_DATABASE` | `gremlin_database` | `""` |
| `GREMLIN_GRAPH` | `gremlin_graph` | `""` |
| `KQL_QUERY_URI` | `kql_query_uri` | `""` |
| `KQL_DATABASE` | `kql_database` | `""` |
| `SEARCH_ENDPOINT` | `search_endpoint` | `""` |
| `COSMOS_ENDPOINT` | `cosmos_endpoint` | `""` |
| `SUBSCRIPTION_ID` | `subscription_id` | `""` |
| `RESOURCE_GROUP` | `resource_group` | `""` |
| `LOCATION` | `location` | `""` |
| `SEARCH_SERVICE_NAME` | `search_service_name` | `""` |
| `COSMOS_ACCOUNT_NAME` | `cosmos_account_name` | `""` |
| `GREMLIN_ACCOUNT_NAME` | `gremlin_account_name` | `""` |
| `FABRIC_API_URL` | `fabric_api_url` | `https://api.fabric.microsoft.com/v1` |
| `FABRIC_WORKSPACE_ID` | `fabric_workspace_id` | `""` |
| `FABRIC_GRAPH_MODEL_ID` | `fabric_graph_model_id` | `""` |
| `FABRIC_SCOPE` | `fabric_scope` | `https://api.fabric.microsoft.com/.default` |
| `TENANT_ID` / `CLIENT_ID` / `CLIENT_SECRET` | service principal | `""` |
| `MAX_CONCURRENT` | `max_concurrent` | `2`, clamped to `>= 1` |
| `BREAKER_THRESHOLD` | `breaker_threshold` | `3` |
| `BREAKER_COOLDOWN_SECS` | `breaker_cooldown_secs` | `60.0` |
| `MAX_ROWS` | `max_rows` | `500` |
| `VERIFY_MAX_KEYS` | `verify_max_keys` | `5000`, clamped to `>= 1` |

Rules:

* Every value is stripped of surrounding whitespace.
* An unparseable integer or float falls back to the default rather than
  raising, so one bad variable cannot prevent startup.
* An empty string means **not configured**. The connector returns an error
  envelope naming the missing setting instead of failing inside an SDK.
* The six management fields are the deploy plane's coordinates. When one is
  empty, the provisioner that needs it is never constructed: `from_config`
  returns an error envelope naming the field, and `Connectors` wraps that
  in a stand-in whose every method answers with the same envelope. A
  management client is never built with an empty subscription id, because
  the resulting failure is an authentication error and the wrong diagnosis.
* The service principal is used only when all three parts are non-empty.
  A partial triple is ignored and the ambient identity is used.
* `client_secret` is excluded from the config object's representation.
* `verify_max_keys` caps key enumeration in a snapshot. Above the cap the
  snapshot carries the first `verify_max_keys` keys in sorted order — a
  deterministic sample, so two snapshots of an unchanged store sample
  identically — the digest covers only that sample, and `sampled` is true.
  Clamped to `>= 1`: a cap of `0` would digest the empty set, which matches
  every state.

Derived:

```
fabric_graph_url = {fabric_api_url}/workspaces/{ws}/graphmodels/{gm}/executeQuery
metadata_url     = {fabric_api_url}/workspaces/{ws}/graphmodels/{gm}
```

Both are empty strings when either id is unset.

---

## 3. Credential resolution

Three tiers, first match wins:

1. `ClientSecretCredential(tenant, client_id, secret)` — only when all
   three are non-empty.
2. `DefaultAzureCredential()` — when any of `WEBSITE_INSTANCE_ID`,
   `CONTAINER_APP_NAME`, `FUNCTIONS_WORKER_RUNTIME`,
   `KUBERNETES_SERVICE_HOST`, `MSI_ENDPOINT`, `IDENTITY_ENDPOINT` is set.
3. `AzureCliCredential()` — otherwise.

Cached at module scope keyed by `"sp={tenant}"` or `"default"`, so a caller
that asked for the ambient identity can never receive a service-principal
credential from an earlier call. The credential is a process-lifetime
singleton and is never closed by a connector.

Scopes:

| Service | Scope |
| --- | --- |
| Cosmos (Gremlin and NoSQL) | `https://cosmos.azure.com/.default` |
| Fabric REST / GraphModel | `https://api.fabric.microsoft.com/.default` |
| Kusto | Handled by the SDK connection string builder |
| AI Search | Handled by the SDK client |

Token cache: refresh once the cached token is older than `2700` seconds.
Double-checked locking around the refresh. On refresh failure with a
cached token present, return the cached token and log; raise only when
there is nothing cached.

---

## 4. Circuit breaker

States: `closed`, `open`, `half-open`.

| Event | closed | open | half-open |
| --- | --- | --- | --- |
| `is_open()` | `false` | `true` until cooldown expires, then transition to half-open and grant one probe | `false` for the first caller, `true` afterwards |
| `record_success()` | reset failure count | no-op | → closed, cooldown reset to base |
| `record_failure()` | count += 1; → open at threshold | no-op | → open, cooldown doubled, capped |

Defaults: `failure_threshold=3`, `cooldown_secs=60`, `max_cooldown_secs=300`.
The probe grant happens **inside** the `is_open()` check so that it is
atomic; a separate "may I probe" call races under concurrency.

`status()` returns:

```json
{"name": str, "state": str, "consecutive_failures": int,
 "cooldown_secs": float, "failure_threshold": int,
 "seconds_until_probe": float | null}
```

`seconds_until_probe` is null unless the state is `open`.

---

## 5. Throttle gate protocol

A gate is a semaphore plus a breaker. Call order is fixed:

```
was_probe = await gate.acquire()          # raises ThrottleError when open
try:
    ... perform the call ...
    await gate.record_success()           # or record_429 / record_server_error
finally:
    gate.release(was_probe=was_probe)
```

Rules a reimplementation must preserve:

1. `acquire()` returns `true` when the caller is the half-open recovery
   probe. A probe **bypasses the semaphore**, so recovery detection cannot
   queue behind saturated capacity.
2. `release(was_probe=true)` releases nothing, because a probe took nothing.
3. After waiting on the semaphore, re-check the breaker: it may have
   tripped while the caller was queued. If so, release and raise.
4. `release` must run in a `finally`. A leaked permit never returns.
5. `ThrottleError` carries `retry_after` in seconds and a caller-safe
   message that names no internal service.

---

## 6. Retry algorithms

### 6.1 Gremlin

* Rebuild the cached client when `token_expires_on - now <= 300` seconds.
* Retry **once** when the lowercased exception text contains any of:
  `401`, `403`, `unauthorized`, `unauthori`, `forbidden`, `token`,
  `expired`, `authentication`, `connection was already closed`,
  `connection is closed`, `connection reset`, `websocket`, `transport`,
  `broken pipe`, `eof`.
* The retry forces a client rebuild first. Any other failure returns an
  error envelope without a retry.
* Every submit runs on a worker thread owning a fresh event loop, which is
  closed afterwards.

### 6.2 Fabric GraphModel

Budget defaults: `http_timeout_secs=100`, `default_429_wait=5`,
`max_429_retries=5`, `max_coldstart_retries=5`,
`max_continuation_retries=50`, `continuation_wait_secs=10`,
`token_stale_secs=2700`. Total attempts are bounded by
`max_429 + max_coldstart + max_continuation + 2`.

Per response:

| Condition | Action |
| --- | --- |
| HTTP 429 | `record_429`; wait `Retry-After` (integer, kept only when `0 < v <= 120`, else 5) multiplied by a uniform jitter in `[0.75, 1.25]`; retry |
| HTTP 500, body `errorCode == "ColdStartTimeout"` | wait `min(10 * 2^(n-1), 60)` with the same jitter; clear the continuation token; refresh the token if older than `token_stale_secs`; retry |
| HTTP 500, any other body | `record_server_error`; error |
| Any other non-200 | `record_server_error`; error |
| 200, body `status.code` not in `{"00000", "02000"}` | error, detail `"GQL {code}: {description}"` |
| 200, `status.code == "02000"` with `result.nextPage` | accumulate the page, resend with `continuationToken`, wait `continuation_wait_secs` |
| 200, otherwise | `record_success`; return accumulated `{columns, data}` |

Request body: `{"query": <text>}`, plus `"continuationToken"` when paging.
Headers: `Authorization: Bearer <token>`, `Content-Type: application/json`.

Every wait releases the permit first and re-acquires afterwards.

### 6.3 AI Search

* Breakers are keyed `"{prefix}:{endpoint}"`, so services fail
  independently.
* When an exception's text contains `Free Query Semantic Usage exceeded`,
  retry once without `query_type`/`semantic_configuration_name`/
  `query_caption`, and do **not** record a breaker failure.
* Apply that same rule at two sites: the `search()` call and the iteration
  of its results.
* Any other exception records a breaker failure and returns an error
  envelope.
* An open breaker returns a degraded envelope without calling the service.

---

## 7. Guardrails

`validate_read_only(query, language)` returns a message or null.
`ensure_limit(query, language, max_rows)` returns the query, possibly with
a limit appended. Both are pure.

| Language | Write detection | Limit detection | Limit appended |
| --- | --- | --- | --- |
| `cypher` | `\b(CREATE\|DELETE\|SET\|MERGE\|REMOVE\|DETACH\|DROP\|CALL)\b` after removing string literals | `\bLIMIT\b` | ` LIMIT {n}` |
| `gql` | `\b(CREATE\|DELETE\|SET\|MERGE\|INSERT\|REMOVE\|DETACH)\b` after removing string literals | `\bLIMIT\b` | ` LIMIT {n}` |
| `kql` | any `;`-separated statement starting `.` unless it starts with `.show tables`, `.show database`, `.show table` | `\|\s*(take\|limit\|top)\s+\d+` | ` \| take {n}` |
| `gremlin` | `\.(addV\|addE\|drop\|property\|addVertex\|addEdge)\s*\(` | `\.(limit\|range\|sample)\s*\(` | `.limit({n})` |
| `sql` | `\b(INSERT\|UPDATE\|DELETE\|DROP\|TRUNCATE\|ALTER\|CREATE)\b` | `\bTOP\s+\d+` or `\bOFFSET\s+\d+\s+LIMIT\s+\d+` | `TOP {n}` inserted after the leading `SELECT` |

Additional rules:

* Length caps, checked first: cypher 2 000, gql 5 000, kql 100 000,
  gremlin 5 000, sql 5 000 characters.
* Default row caps: cypher 500, gql 50, kql 50, gremlin 500, sql 500.
* Gremlin queries containing `.count()`, `.sum()`, `.mean()`, `.max()` or
  `.min()` are returned unchanged by `ensure_limit`.
* Trailing whitespace and one trailing `;` are removed before appending.
* An unknown language passes through both functions untouched.

These are regex guards with known false negatives. They are a floor;
read-only RBAC is the boundary. See GOTCHAS.md G10.

---

## 8. Cosmos NoSQL health probe

```
async with timeout(seconds):          # default 2.0
    async for _ in container.query_items("SELECT TOP 1 c.id FROM c", []):
        break
return true
```

Timeout returns `false` and logs a warning distinguishing slow from
unreachable. Every other exception returns `false` silently, so a caller
can fall back to an in-memory store. A reimplementation **must** ship a
test asserting a healthy container returns `true`; see GOTCHAS.md G11 for
what that test prevents.

---

## 9. Write plane

### 9.1 `WritePolicy`

Immutable. Denies everything by default.

| Field | Default | Rule |
| --- | --- | --- |
| `allow_write` | `false` | `create` and `upload` are refused unless true |
| `allow_delete` | `false` | `delete` is refused unless true. **Never implied by `allow_write`** |
| `max_batch` | `100` | Chunk size. Clamped to `>= 1` at construction |
| `verify_writes` | `false` | Default for the `verify` argument of every mutation |
| `verify_attempts` | `10` | Read-back attempts. Clamped to `>= 1` at construction |
| `verify_delay_secs` | `1.0` | Seconds between attempts. Not clamped |

Two constructors:

* `read_only()` — all defaults. Every mutation refused.
* `writable(allow_delete=false, verify_writes=true, max_batch=100)` — sets
  `allow_write` true. **`verify_writes` defaults to true here**, unlike the
  raw field default, because the point of an explicit write grant is that
  somebody cares whether the write landed.

A refusal is an `error` envelope naming the constructor to use, not an
exception. The refusal happens before any client is built, so an
unconfigured or unreachable service still refuses correctly.

### 9.2 Chunking

```
chunk(items, size):
    if size < 1: size = 1
    return [items[i : i+size] for i in range(0, len(items), size)]
```

Never yields an empty chunk; yields nothing at all for empty input.
Chunks are submitted **in order**, and each chunk is one breaker record and
one throttle-gate acquisition. Services with no batch API still chunk, so
the gate sees one acquisition per chunk rather than one per item.

There is **no transaction**. A chunk that fails leaves earlier chunks
applied. There is no rollback and no compensating delete.

### 9.3 Operation order

`create` and `upload`:

1. Refuse unless `allow_write`.
2. Empty input → `ok` with `count: 0`, `failed: []`, `verified: false`.
   Nothing reaches the service.
3. Refuse the whole batch when any item's key is null, naming the count and
   the index of the first.
4. For each chunk, in order: run the service call behind the breaker and
   gate; accumulate per-item results.
5. If verifying, poll every accepted key present (9.4).
6. Return the batch envelope.

`delete`: identical, except step 1 checks `allow_delete`, step 3 does not
apply, and step 5 polls for **absence** of every key whose result was `ok`.

`read`: no grant needed. A missing item is `count: 0`, not an error —
absence is a valid answer to a lookup and a caller must not have to parse
an error string to tell it from a failure.

Any exception escaping steps 4 or 5 becomes an `error` envelope. Nothing
from an SDK reaches the caller as an exception.

### 9.4 Verification

```
poll(keys, want_present):
    outstanding = keys
    for attempt in 0 .. verify_attempts-1:
        outstanding = [k for k in outstanding
                       if (read(k) is not null) != want_present]
        if outstanding is empty: return
        if attempt < verify_attempts-1: sleep(verify_delay_secs)
    raise VerificationFailed(
        "<n> item(s) were accepted but never became "
        "<readable|absent> after <verify_attempts> checks")
```

So: at most `verify_attempts` read rounds and at most
`verify_attempts - 1` sleeps. The default budget is 10 attempts one second
apart. `VerificationFailed` is caught at the boundary and returned as an
`error` envelope, so a write that was accepted and did not land is a
**failure**, not a success carrying a warning.

The `verify` argument overrides `policy.verify_writes` per call; `null`
means use the policy.

### 9.5 Per-service obligations

A reimplementation must reproduce these, because each is a way a service
reports a write it did not apply:

| Service | Obligation |
| --- | --- |
| Search | Map every entry of the per-document result list; a `succeeded: false` inside an HTTP 200 is a failure. `create` has no service support and must pre-read every key — non-atomic, and say so |
| Search | Delete takes documents, not keys: send a stub carrying only the key field |
| Cosmos | A 404 from `delete_item` is a **failed** item, never `ok`: the same status means "wrong partition key" |
| Cosmos | Reads and deletes require a partition key. No default, no fallback, no cross-partition recovery |
| Cosmos | The extracted key is the `(id, partition_key)` pair |
| Cosmos | A query is cross-partition exactly when no `partition_key` is passed. Never send `enable_cross_partition_query` |
| Gremlin | Mutations are generated traversals; every literal escaped through one chokepoint that allow-lists `str, bool, int, float, null` |
| Gremlin | Caller-supplied traversals keep the read-only guard and limit injection. Only generated text bypasses them |
| Gremlin | A delete's outcome is decided by a count taken **before** the drop |
| Gremlin | `upload` emits `fold().coalesce(unfold(), addV(...))`; properties trail the coalesce so they land on both branches |
| Gremlin | Every item must carry the partition key property; refuse the chunk otherwise |

---

## 10. Deploy plane

### 10.1 `ProvisionPolicy`

| Field | Default | Rule |
| --- | --- | --- |
| `allow_create` | `false` | `ensure` refused unless true |
| `allow_delete` | `false` | `teardown` refused unless true. Never implied by `allow_create` |
| `poll_timeout_secs` | `900.0` | Deadline for one long-running operation |
| `verify_after_write` | `true` | Default for the `verify` argument of `ensure` and `teardown` |

Constructors: `read_only()` (all defaults; `describe` and `exists` still
work) and `deployable(allow_delete=false, poll_timeout_secs=900.0)`.

900 seconds is not a generous margin. A Cosmos account with a private
endpoint routinely takes five to eight minutes; below roughly ten minutes
this deadline fails deployments that were going to succeed.

### 10.2 Bounding a long-running operation

```
await_poller(poller, timeout):
    if poller has no `result` member: return poller
    with deadline(timeout):
        return run_off_thread(poller.result)
```

Two rules. A pollerless return value passes straight through, because not
every management operation is an LRO — `azure-mgmt-search`
`services.delete` returns `None`, and a subclass must not have to branch
for it. And `result()` runs **off** the calling thread, because it blocks
until the service finishes and a wedged deployment would otherwise hang the
process rather than fail it.

A timeout is an `error` envelope reading
`"<kind> '<name>' did not reach a terminal state within <timeout>s"`.

### 10.3 `ensure`

1. Refuse unless `allow_create`.
2. `existed = describe() is not null`.
3. Call create-or-update; bound the poller (10.2).
4. If verifying:
   a. Re-read. A resource that is not readable afterwards is a
      `ProvisionDrift` error.
   b. Read the state (10.5). A state in `{failed, canceled, cancelled,
      deleting}` is an error.
   c. Compute drift (10.4). Non-empty drift is a `ProvisionDrift`
      **error** naming the sorted field list and suggesting an Azure Policy
      `Modify` effect.
5. Return `ok` with `created: not existed`, `verified`, `state`, and
   `drift: {}`.

Step 4 is the point of the plane. ARM returns HTTP 200 with
`provisioningState: Succeeded` for writes a policy reverts moments later,
so the write response is a receipt and the read-back is the check.

`teardown` mirrors it: refuse unless `allow_delete`; describe; delete only
when present; bound the poller; if verifying and it existed, re-read and
error when it is still readable; return `deleted: existed`.

`describe` needs no grant and never throws — an SDK failure becomes an
`error` envelope. `exists` needs no grant and **never raises**: a probe that
raises is useless, so any exception is `false`.

### 10.4 Drift comparison

```
find_drift(requested, observed):
    drift = {}
    for key, want in requested:
        if key not in observed:      drift[key] = {requested: want, observed: null}
        elif observed[key] != want:  drift[key] = {requested: want, observed: observed[key]}
    return drift
```

Three rules that together decide whether the check is usable:

1. **Only keys present in `requested` are compared.** A spec is a partial
   description; the service fills in everything else.
2. **One level deep.** Nested values compare by whole-value equality, so a
   read-back must be lifted into the shape the spec is written in before
   this runs.
3. **A requested key missing from `observed` counts as drift**, because a
   silently dropped setting is the failure this exists to catch.

`requested` is not the raw spec: each provisioner narrows it first, to the
subset the service echoes verbatim. Compare more than that and every
healthy deployment reports drift, the check gets switched off, and the real
signal goes with it. The narrowing per resource:

| Resource | Compared |
| --- | --- |
| Search index | The index name and the declared field **name list** only |
| Search service | Spec keys snake-cased, then intersected with `{sku, tags, identity, hosting_mode, partition_count, replica_count, public_network_access}` |
| Cosmos account | The whole lifted spec except `location` and `locations` |
| Cosmos container | The partition key paths only |
| Gremlin graph | The partition key paths only, each rooted with `/` |
| Gremlin database | The spec except `throughput` and `autoscale_max_throughput` |

### 10.5 Read-back normalisation

The two management SDKs disagree, and a reimplementation must handle
whichever it has rather than assuming one:

| | `azure-mgmt-search` 9.x | `azure-mgmt-cosmosdb` 10.x |
| --- | --- | --- |
| Style | msrest | JSON-backed |
| Dict view | `as_dict()` | `dict(model)`, model is a `Mapping` |
| Keys | snake_case, flattened | camelCase, nested under `properties` |
| `resource` | n/a | attribute only, not a dict key |

Normalisation is therefore **per SDK**, in the module that owns it, and
deliberately not shared. For the cosmosdb style: take the dict view, lift
`properties` up one level, snake-case the keys at both lifted levels, and
`setdefault` when lifting so a top-level ARM resource id is not overwritten
by the inner one. For the search style: snake-case the *spec* keys instead,
and compare only the echoed set.

State detection, applied to the normalised dict: the first string found
among `provisioning_state`, `provisioningState`, `status`, `state`; failing
that, recurse once into a `properties` mapping; failing that, `""`.
`SUCCEEDED_STATES` is exported for callers, and `ensure` does not consult
it — only `FAILED_STATES` short-circuits.

### 10.6 Guaranteed versus best-effort

Guaranteed:

* A mutation is refused unless its policy grants it, before any client is
  constructed.
* Delete is never implied by write, on either plane.
* An SDK exception never escapes; every operation answers with an envelope.
* `count` and `failed` account for every item submitted.
* Chunks are submitted in order.
* With `verify` on, a write whose state does not read back is an error.
* A long-running operation is abandoned at `poll_timeout_secs`.
* `exists` never raises.

Best-effort, and a caller must not assume otherwise:

* **Atomicity.** None, at any level. Chunk boundaries are visible after a
  failure.
* **Search `create`.** Racy by construction: another writer can insert
  between the pre-read and the upload.
* **Verification latency.** Bounded by `verify_attempts × verify_delay_secs`
  plus the read round trips. A service slower than that budget reports a
  failure for a write that eventually lands.
* **Drift detection.** Only the narrowed field set of 10.4, one level deep.
  A field outside that set can be reverted and this will not notice.
* **Idempotence of `ensure`.** Delegated to the service's
  create-or-update semantics; nothing here diffs before writing.
* **Ordering between resources.** None. The caller ensures the account,
  then the database, then the container.

---

## 11. Discover plane

Enumeration, one level at a time, bounded in items and in seconds. Its
consumer is a lazily expanding tree, which is why this is the one plane
that returns a dataclass rather than a JSON string: a consumer must branch
on status before it renders, and re-parsing a string per node is pure cost.
`detail` still goes through `sanitize_detail`, so the redaction rule of
section 1.1 is shared, not re-implemented.

### 11.1 Types

```python
DiscoveryStatus = Literal["ok", "empty", "forbidden", "unreachable",
                          "unconfigured", "unavailable"]

@dataclass(frozen=True, slots=True)
class DiscoveryScope:
    subscription_id: str = ""
    resource_group: str = ""
    endpoint: str = ""          # data-plane endpoint where the service uses one
    account_name: str = ""      # ARM resource name where the service uses one
    path: tuple[str, ...] = ()  # ordered coordinate below the service root

@dataclass(frozen=True, slots=True)
class DiscoveryBounds:
    max_items: int = 500        # clamped >= 1
    timeout_secs: float = 15.0  # clamped > 0

@dataclass(frozen=True, slots=True)
class DiscoveryNode:
    kind: str                                     # service-defined, stable, snake_case
    name: str
    path: tuple[str, ...]                         # the scope.path that expands this node
    has_children: bool
    attributes: Mapping[str, str | int | bool | None]

@dataclass(frozen=True, slots=True)
class DiscoveryResult:
    service: str                                  # "arm"|"search"|"cosmos"|"gremlin"|"kusto"
    level: str
    scope: DiscoveryScope
    status: DiscoveryStatus
    nodes: tuple[DiscoveryNode, ...]
    truncated: bool
    detail: str                                   # sanitised; "" when ok or empty
    collected_at: str                             # UTC ISO-8601, second resolution, Z

class Discoverer(Protocol):
    service: str
    levels: tuple[str, ...]
    def child_level(self, level: str) -> str | None: ...
    async def discover(self, level: str, scope: DiscoveryScope, *,
                       bounds: DiscoveryBounds = DiscoveryBounds()) -> DiscoveryResult: ...
```

`DiscoveryBounds` clamps rather than validates. A caller that computed `0`
from a query string gets one item, not an exception out of a plane whose
whole contract is that failure is a value.

### 11.2 Invariants

1. `discover` **never raises**. Every failure is a status.
2. `status == "ok"` ⟺ `nodes` is non-empty and `detail == ""`. Zero nodes
   with no failure is `"empty"`, never `"ok"`.
3. `truncated` is independent of status: `ok` + `truncated` is normal. A
   discoverer reads `max_items + 1` and the wrapper drops the extra, so
   truncation is proven without a second call.
4. `nodes` are ordered `(kind, name)` ascending. Two calls against an
   unchanged estate are identical apart from `collected_at`.
5. A node's `path` is exactly the `DiscoveryScope.path` that expands it.
   The consumer never composes coordinates itself.
6. No secrets, connection strings, keys or full URLs in `attributes` or
   `detail`. Both go through `sanitize_detail`.
7. Construction never connects — not even to build a credential. The first
   `discover` is the first network call, so a health check may build one.

### 11.3 Degradation table

| Observed | `status` |
| --- | --- |
| required scope/config field empty | `unconfigured` |
| `MissingDependency` | `unavailable` |
| `HttpResponseError` 401/403, `ClientAuthenticationError` | `forbidden` |
| `ServiceRequestError`, `ServiceRequestTimeoutError`, `socket.gaierror`, `OSError` | `unreachable` |
| `TimeoutError` from the bounds wrapper | `unreachable`, detail `discovery exceeded {n}s` |
| `HttpResponseError` 404, coordinate absent | `unavailable` |
| `HttpResponseError` 429/5xx | `unavailable` |
| success, zero items | `empty` |
| anything else | `unavailable` |

`azure.core.exceptions` is loaded through `load(..., dist="azure-core")`,
so the mapper is testable with no SDK installed and falls back to matching
on exception type name and `status_code`.

The distinction is the point. `forbidden` is fixed by a role grant;
`unreachable` is a network, DNS or private-endpoint fact that a role grant
will not touch; `unconfigured` means nobody ever set the coordinate.

### 11.4 Hierarchy

| Service | Level | Child kind | Source plane | Required role |
| --- | --- | --- | --- | --- |
| `arm` | `resource_group` | `arm_resource` (leaf) | ARM resources collection | Reader on the RG |
| `search` | `service` | `search_index` | Search index management | Search Service Contributor |
| `search` | `index` | `search_field` (leaf) | Search index management | Search Service Contributor |
| `cosmos` | `account` | `cosmos_database` | ARM management | Reader on the account |
| `cosmos` | `database` | `cosmos_container` (leaf) | ARM management | Reader on the account |
| `gremlin` | `account` | `gremlin_database` | ARM management | Reader on the account |
| `gremlin` | `database` | `gremlin_graph` (leaf) | ARM management | Reader on the account |
| `kusto` | `cluster` | `kusto_database` | ARM management | Reader on the cluster |
| `kusto` | `database` | `kusto_table` (leaf) | data plane, `.show tables` | Kusto Database Viewer |

Cosmos and Gremlin are management-plane deliberately: DDL and metadata are
control-plane concerns for Cosmos, and an account with
`publicNetworkAccess=Disabled` answers ARM while refusing every data-plane
connection. Gremlin gains a second reason — no WebSocket is opened, so
G12 cannot occur.

Kusto tables have no management-plane listing, so the command surface is
bounded instead: `ALLOWED_COMMANDS = (".show tables",)`, indexed and never
formatted, with the database passed as the client's database argument
rather than concatenated. `validate_read_only` is the wrong tool — `.show`
is a control command and the query guardrail rejects it by design.

ARM resource `tags` are omitted from `attributes`: operator free text is a
plausible secret carrier and nothing in a browsable inventory needs it.

### 11.5 Registry

```python
class DiscovererRegistry:
    def register(self, discoverer: Discoverer) -> None: ...
    def get(self, service: str) -> Discoverer | None: ...
    def services(self) -> tuple[str, ...]: ...

def build_discovery_registry(config: AzureDataConfig,
                             credential_provider: Callable[[], Any] | None = None,
                             ) -> DiscovererRegistry: ...
```

All five are registered in the fixed order `arm, search, cosmos, gremlin,
kusto`, whether configured or not. A service whose coordinates are empty
still registers and answers `unconfigured`: a consumer has to be able to
show *why* a branch is dark, and an absent registry entry cannot say
anything at all. No module-level singleton, and no import side effects.

---

## 12. Minimal reference implementation

The smallest thing that satisfies section 1 and section 5 for one service:

```python
async def execute(query: str) -> str:
    if not endpoint:
        return json.dumps({"error": True, "detail": "endpoint not configured"})
    violation = validate_read_only(query, "kql")
    if violation:
        return json.dumps({"error": True, "detail": violation})

    was_probe = await gate.acquire()          # raises when open
    try:
        response = await run_off_loop(client.execute, database,
                                      ensure_limit(query, "kql"))
        await gate.record_success()
        return json.dumps(shape(response))
    except Exception as exc:
        if "429" in str(exc).lower():
            await gate.record_429()
        else:
            await gate.record_server_error()
        return json.dumps({"error": True, "detail": sanitize(str(exc))})
    finally:
        gate.release(was_probe=was_probe)
```

---

<!-- api-surface:start -->

## Public surface

Every name exported by `azdata`, in `__all__` order. Derived from the package itself; regenerate after changing `__all__` by walking `azdata.__all__` and taking each object's kind and first docstring line. The generator is not shipped in this folder.

| Name | Kind | Description |
| --- | --- | --- |
| `AzureDataConfig` | class | Every coordinate the connectors need. Empty string means unconfigured. |
| `CircuitBreaker` | class | Closed -> Open -> Half-Open -> Closed, with exponential re-open backoff. |
| `CircuitBreakerRegistry` | class | Named breakers, so a health endpoint can report all of them at once. |
| `CircuitState` | class | CLOSED: pass through. OPEN: fail fast. HALF_OPEN: one probe allowed. |
| `Connectors` | class | Lazily built, cached connectors sharing one config and credential. |
| `CosmosAccountProvisioner` | class | One Cosmos DB account, verified against Azure Policy after the write. |
| `CosmosContainer` | class | One Cosmos NoSQL container, with a breaker and a bounded health probe. |
| `CosmosContainerProvisioner` | class | One SQL container, verified on the partition key path above all else. |
| `CosmosDatabaseProvisioner` | class | One SQL database inside an account. Seconds, not minutes. |
| `CosmosItems` | class | Create, retrieve, upload and delete items in one Cosmos container. |
| `CosmosUnavailable` | class | The store's circuit breaker is open, or the call failed. |
| `CrudConnector` | class | Create, Retrieve, Upload, Delete over one service, one envelope. |
| `DEFAULT_MAX_BATCH` | constant | 100 |
| `DEFAULT_MAX_ROWS` | constant | {'cypher': 500, 'gql': 50, 'kql': 50, 'gremlin': 500, 'sql': 500} |
| `GraphConnector` | class | Read-only GQL execution against a Fabric GraphModel. |
| `GraphRetryBudget` | class | Every retry and timeout knob for the executeQuery loop. |
| `GremlinConnector` | class | Read-only Gremlin execution against a Cosmos DB graph. |
| `GremlinDatabaseProvisioner` | class | One Gremlin database inside an existing Cosmos account. |
| `GremlinElements` | class | Vertex CRUD over one Cosmos DB graph, by generated traversal. |
| `GremlinGraphProvisioner` | class | One graph inside a Gremlin database, checked on its partition key. |
| `GremlinTarget` | class | Endpoint coordinates for one graph. |
| `GremlinWriteError` | class | A generated traversal was submitted and the service refused it. |
| `KqlConnector` | class | Read-only KQL execution behind a concurrency gate. |
| `KqlTarget` | class | Cluster query URI plus database name. |
| `LANGUAGES` | constant | ('cypher', 'gql', 'kql', 'gremlin', 'sql') |
| `MissingDependency` | class | A connector was used without its SDK installed. |
| `ProvisionDrift` | class | The resource was written successfully and did not keep the value. |
| `ProvisionPolicy` | class | What a provisioner instance may do. Denies by default. |
| `ProvisionRefused` | class | A create or delete was attempted that the policy forbids. |
| `Provisioner` | class | Make one resource match one spec, and prove it afterwards. |
| `SearchConnector` | class | Read-only hybrid search with per-endpoint failure isolation. |
| `SearchDocuments` | class | Create, read, upload and delete documents in one Azure AI Search index. |
| `SearchIndexProvisioner` | class | Create, describe and delete one Azure AI Search index. |
| `SearchServiceProvisioner` | class | Create, describe and delete the search service itself, through ARM. |
| `ThrottleError` | class | Raised when the gate refuses a call because the circuit is open. |
| `ThrottleGate` | class | Concurrency semaphore plus circuit breaker for one shared capacity. |
| `TokenCache` | class | Caches one bearer token for one scope. |
| `VerificationFailed` | class | A write was accepted but the resulting state was not what was asked. |
| `WritePolicy` | class | What a connector instance is permitted to do. Denies by default. |
| `WriteRefused` | class | A mutation was attempted that the connector's policy forbids. |
| `connect` | function | Wire every connector from one config. This is the integration point. |
| `credential_provider_for` | function | Bind a config's service-principal triple into a zero-arg provider. |
| `default_credential_provider` | function | Return the best available ``TokenCredential`` for this environment. |
| `degraded_envelope` | function | ``{"degraded": true, "detail": "..."}`` as a JSON string. |
| `ensure_limit` | function | Append a row cap when the query has none. Idempotent. |
| `error_envelope` | function | ``{"error": true, "detail": "..."}`` as a JSON string. |
| `find_drift` | function | Return requested fields whose observed value differs, one level deep. |
| `get_gate` | function | Return the named process-wide gate, creating and publishing it once. |
| `is_error` | function | True when ``payload`` is an error envelope. Never raises on garbage. |
| `is_ok` | function | True when ``payload`` is a success envelope. Never raises on garbage. |
| `limit_injector` | function | Return a one-argument limit injector bound to ``language``. |
| `read_only_validator` | function | Return a one-argument validator bound to ``language``. |
| `registry` | instance | Named breakers, so a health endpoint can report all of them at once. |
| `reset_credential_cache` | function | Drop the cached credential. Tests and credential rotation drills only. |
| `reset_gates` | function | Drop every cached gate. Tests only. |
| `running_in_azure` | function | True when the process appears to be running on Azure compute. |
| `sanitize_detail` | function | Cap and URL-strip a caller-visible detail string. |
| `shape_kusto_response` | function | Turn a Kusto response into ``{"columns": [...], "rows": [...]}``. |
| `success_envelope` | function | ``{"ok": true, "operation": "...", ...}`` as a JSON string. |
| `validate_read_only` | function | Return an explanation when ``query`` may write, else None. |

<!-- api-surface:end -->
