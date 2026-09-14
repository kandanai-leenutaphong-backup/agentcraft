---
name: azure-data-connectors
description: Read, write and provision Azure data services - Cosmos DB Gremlin, Fabric Eventhouse (Kusto/KQL), Azure AI Search, Fabric GraphModel (GQL), Cosmos DB NoSQL - with managed identity, circuit breakers, concurrency limits, read-only guards, retry policies, denied-by-default write grants and read-back verification already in place. Use when wiring an app or agent tool to any of those services, when loading documents or items or graph vertices into them, when an agent must stand a service up and tear it down inside one run, when a Gremlin query starts failing about an hour after deploy, when Kusto returns 429 or a dashboard endpoint 502s, when AI Search reports "Free Query Semantic Usage exceeded", when a Fabric GQL query returns 200 with no rows, when a delete reported success but nothing was deleted, when an ARM write returned 200 and Succeeded and the setting reverted anyway, when a just-uploaded Search document is not retrievable, or when tempted to use a connection string, account key or SAS token.
license: MIT
---

# Azure data connectors

Five services, one wiring call, one result shape. Identity-based auth,
bounded queries, per-endpoint circuit breakers, and the retry policies these
specific services actually need.

| Connector | Service | SDK |
| --- | --- | --- |
| `gremlin` | Cosmos DB Gremlin | `gremlinpython` |
| `kql` | Fabric Eventhouse / Azure Data Explorer | `azure-kusto-data` |
| `search` | Azure AI Search | `azure-search-documents` |
| `graph` | Fabric GraphModel (GQL over HTTPS) | `httpx` |
| `cosmos` | Cosmos DB NoSQL | `azure-cosmos` |

Three planes. Read is always available; the other two are refused until a
policy object grants them.

| Plane | Surface | Grant | SDK added |
| --- | --- | --- | --- |
| Read | `execute` | none needed | as above |
| Write | `documents()` / `items()` / `elements()` | `WritePolicy` | none |
| Deploy | `provision_*()` | `ProvisionPolicy` | `azure-mgmt-search`, `azure-mgmt-cosmosdb` |

## Decide in one line

| Situation | Action |
| --- | --- |
| Wiring any of the five services | Install this box |
| Need to load documents, items or vertices | Write plane; `WritePolicy` below |
| Need to stand a service up inside one run | Deploy plane; `ProvisionPolicy` below |
| A delete reported success and deleted nothing | G21 (Cosmos), G22 (Gremlin) — use `verify=True` |
| An ARM write said `Succeeded` and did not stick | G19 — `ensure` re-reads; mechanism in G14 |
| An accepted Search upload is not retrievable yet | G20 — not a bug; verification polls |
| A Gremlin property value contains a quote | G23 — already escaped; never f-string a traversal |
| A healthy deployment reports drift | G18 — the two mgmt SDKs disagree on model style |
| A "partition-scoped" query costs a full scan | G17 — the 4.x flag is gone and absorbed silently |
| Gremlin worked, now fails ~1 h after deploy | Already fixed here; see G1 |
| `This event loop is already running` from Gremlin | Already fixed here; G2 |
| KQL 429, or a multi-query endpoint 502s | Use the gate; G16 |
| `Free Query Semantic Usage exceeded` | Already handled; G4 |
| Fabric GQL returns 200 and no rows | G7 — check `status.code`, not HTTP |
| Cosmos health check always false | G11 |
| Gremlin 403 before any query is sent | G12 — private endpoint, not auth |
| Tempted to use a connection string or key | Use `TokenCredential`; below |
| Reimplementing in another language | `CONTRACT.md` only |
| Removing it | Removal, below |

## Use As An Installed Plugin

When the `azure-data-connectors` MCP server is available, call `azdata_status` first. It reports
which targets are configured and the path to the operator's non-secret configuration file.
Unconfigured targets are not reachable; installation does not grant Azure permissions.

The MCP tools expose KQL, Gremlin, Fabric GQL and AI Search queries. Write, delete and provisioning
tools are not exposed. Do not widen that policy or configure a new cloud target without approval.
The MCP adapter reads its explicit configuration file, not the calling project's `AZDATA_*` environment.

The client supplies the loaded skill's location. Resolve this directory's documentation and examples
from that location, not from a hardcoded workspace path. A Python application can use the library
directly; it does not need an MCP client.

## Install As A Python Library

Use the application's Python environment. Replace `<skill-directory>` with the absolute directory
containing this file, and select the connector extras the application needs:

```bash
python3 -m pip install "<skill-directory>[search]"
```

The write plane needs no SDK the read plane does not already need. The
deploy plane is the only reason a management SDK appears, so a process that
only reads and writes data should not install one. The discover plane is
management-plane too, and `pip install -e ".[discover]"` installs the five
distributions it can reach.

Wire once, at your composition root:

```python
from azdata import AzureDataConfig, connect

CONFIG = AzureDataConfig.from_env()      # AZDATA_* variables, read once, frozen
CONNECTORS = connect(CONFIG)             # nothing connects yet
```

`connect(config, credential_provider=...)` is the entire integration
surface. Both arguments are optional and both are overridable.

Already have environment variable names? Adopt them instead of renaming:

```python
CONFIG = AzureDataConfig.from_env(prefix="")   # COSMOS_ENDPOINT, KQL_DATABASE, ...
```

### Grant access

Role assignments, not keys. Never a connection string, account key or SAS
token — every connector here authenticates with a `TokenCredential`.

Read plane:

| Service | Role |
| --- | --- |
| Cosmos NoSQL | `Cosmos DB Built-in Data Reader` (data plane, assigned with `az cosmosdb sql role assignment create`) |
| Cosmos Gremlin | Same data-plane role model; the token scope is `https://cosmos.azure.com/.default` |
| AI Search | `Search Index Data Reader` |
| Kusto / Eventhouse | Database `Viewer` |
| Fabric GraphModel | Workspace `Viewer` or above |

Write plane — additional, and only where you actually write:

| Service | Role |
| --- | --- |
| AI Search documents | `Search Index Data Contributor` |
| Cosmos NoSQL items | `Cosmos DB Built-in Data Contributor` (data plane, same `az cosmosdb sql role assignment create` path) |
| Cosmos Gremlin vertices | Same data-plane contributor role; scope is still `https://cosmos.azure.com/.default` |

Deploy plane — a **management**-plane role, which the data-plane roles above
are not:

| Scope | Role |
| --- | --- |
| The resource group the run owns | `Contributor` |

Narrower built-ins exist (`Search Service Contributor` for the search
service, `DocumentDB Account Contributor` for Cosmos), and a run that only
touches one service should use them. The Search **index** provisioner is
the exception: index management is a data-plane operation on the search
endpoint, so it needs `Search Index Data Contributor` and no subscription
at all.

A management role does not grant data access on Cosmos. Cosmos data-plane
RBAC is assigned separately, and `Contributor` on the account gives you
nothing inside it.

Locally, `az login` is enough. In Azure, the workload identity is picked up
automatically — same code, no branching.

## Use

### The read plane

```python
# Cosmos DB Gremlin — writes refused, .limit() injected
payload = await CONNECTORS.gremlin.execute("g.V().hasLabel('device')")

# Kusto — {"columns": [...], "rows": [...]}, | take injected
payload = await CONNECTORS.kql.execute("Events | where Level == 'Error'")

# AI Search — synchronous SDK; project_doc is required
payload = await asyncio.to_thread(
    CONNECTORS.search.execute,
    "how do I reset it",
    index_name="knowledge-base",
    semantic_config="knowledge-base-semantic",
    project_doc=lambda d: {"title": d.get("title", ""), "text": d["chunk"][:2000]},
)

# Fabric GraphModel — returns a dict, not a string (projection seam)
result = await CONNECTORS.graph.execute("MATCH (n:Asset) RETURN n LIMIT 10")

# Cosmos NoSQL — you own the query, the box owns the connection
store = CONNECTORS.cosmos("sessions", "conversations")
store.check_breaker()
async for item in store.container.query_items(
    query="SELECT TOP 1 * FROM c WHERE c.id = @id",
    parameters=[{"name": "@id", "value": sid}],
):
    ...
```

### The write plane

Denied until a `WritePolicy` grants it, and delete is a second grant.
Construct the policies where the rest of your wiring lives, so the
permission list is one block somebody can read.

```python
from azdata import WritePolicy

INGEST    = WritePolicy.writable(verify_writes=True)     # write, not delete
RETENTION = WritePolicy(allow_delete=True, verify_writes=True)  # delete only
```

```python
# AI Search documents. upload is the idempotent write; prefer it.
writer = CONNECTORS.documents("knowledge-base", policy=INGEST)
payload = await writer.upload([{"id": "d1", "title": "t", "chunk": "..."}])

# Read one back. A missing document is count: 0, not an error.
payload = await writer.read("d1")

# Free-form search from the write connector. project_doc is still required.
payload = await writer.query(
    "how do I reset it",
    project_doc=lambda d: {"title": d.get("title", ""), "text": d["chunk"][:2000]},
    top=5,
)

# Delete needs its own connector, because the grant is different. Build it
# directly: CONNECTORS.documents() caches one connector per index NAME, so
# asking the same index for a second policy hands back the first one.
from azdata import SearchDocuments

purger = SearchDocuments.from_config(
    CONFIG,
    CONNECTORS.credential_provider,
    index_name="knowledge-base",
    policy=RETENTION,
)
payload = await purger.delete(["d1", "d2"])
```

```python
# Cosmos NoSQL items. partition_key_field has no default, deliberately.
items = CONNECTORS.items(
    "telemetry", "readings", partition_key_field="site", policy=INGEST
)
payload = await items.upload([{"id": "r1", "site": "north", "value": 3}])

# Reads and deletes REQUIRE a partition key. There is no fallback: an
# unqualified read 404s without proving anything (G21).
payload = await items.read("r1", partition_key="north")
payload = await items.query("SELECT * FROM c", partition_key="north")

# Cross-partition is the absence of the key, not a flag (G17).
payload = await items.query("SELECT * FROM c", max_rows=100)
```

```python
# Gremlin vertices, written as generated traversals with every literal
# escaped. A caller-supplied traversal keeps the read-only guard.
elements = CONNECTORS.elements(
    "asset", partition_key_field="site", policy=INGEST
)
payload = await elements.upload([{"id": "v1", "site": "north", "name": "o'brien"}])
payload = await elements.query("g.V().hasLabel('asset')")   # guarded, capped
```

Every mutation returns the `ok` envelope. `count` excludes failures,
`failed` lists them per item, `verified` says whether the state was read
back:

```json
{"ok": true, "operation": "upload", "service": "search",
 "count": 2, "failed": [{"key": "d3", "ok": false, "detail": "..."}],
 "verified": true}
```

Pass `verify=False` per call to skip the read-back when you are loading in
bulk and will check the total afterwards. Leave it on otherwise: each of
these three services will report a write it did not apply (G20, G21, G22).

### The deploy plane

For a run that owns the resource it stands up. Long-lived production
infrastructure still belongs in Bicep.

```python
from azdata import ProvisionPolicy

DEPLOY   = ProvisionPolicy.deployable()                     # create/update
TEARDOWN = ProvisionPolicy.deployable(allow_delete=True)    # and destroy
```

```python
# Search index. Data plane: needs the search endpoint, no subscription.
index = CONNECTORS.provision_search_index("scratch-index", policy=DEPLOY)
payload = await index.ensure({
    "name": "scratch-index",
    "fields": [
        {"name": "id", "type": "Edm.String", "key": True},
        {"name": "chunk", "type": "Edm.String", "searchable": True},
    ],
})

# Cosmos, in dependency order. Nothing here orders it for you.
account   = CONNECTORS.provision_cosmos_account(policy=DEPLOY)
database  = CONNECTORS.provision_cosmos_database("telemetry", policy=DEPLOY)
container = CONNECTORS.provision_cosmos_container(
    "telemetry", "readings", policy=DEPLOY
)
payload = await container.ensure({
    "location": CONFIG.location,
    "properties": {
        "resource": {
            "id": "readings",
            "partitionKey": {"paths": ["/site"], "kind": "Hash"},
        },
        "options": {"throughput": 400},
    },
})

# Gremlin. partition_key_paths is mandatory and cannot be changed later.
graph = CONNECTORS.provision_gremlin_graph(policy=TEARDOWN)
payload = await graph.ensure({"partition_key_paths": ["/site"], "throughput": 400})

# Read without any grant at all.
payload = await graph.describe()
present = await graph.exists()

# Destroy. Requires the delete grant, separately.
payload = await graph.teardown()
```

`ensure` re-reads the resource afterwards and compares the fields the spec
asked for. `drift` is non-empty when a field did not survive the write, and
that is returned as an **error**, not a warning (G19):

```json
{"ok": true, "operation": "ensure", "resource_kind": "gremlin-graph",
 "name": "graph", "created": true, "verified": true,
 "state": "Succeeded", "drift": {}}
```

Unconfigured coordinates never build a management client that 401s later:
every method answers with an error envelope naming the missing config
field.

`examples/agent_tools.py` is the same thing as agent-callable tools, with
the projections written out.

### The observe plane

*How is this doing.* One `stats` call per target, from the data plane, the
management plane and Azure Monitor at once.

```python
from azdata import CosmosStats, MetricsReader, SearchStats

stats = SearchStats.from_config(CONFIG, my_provider, index_name="azdata-assets")
payload = json.loads(await stats.stats())

payload["stats"]["document_count"]     # 40
payload["partial"]                     # what could not be collected, and why
```

Two rules, and they are the whole contract:

* **Nothing fails wholesale.** A counter that could not be read costs its
  own name and nothing else. The envelope is still `ok: true`.
* **Nothing is omitted silently.** Every stat the service declares is
  either in `stats` or named in `partial` with a reason. An absent value is
  never reported as `0`.

Azure Monitor is never load-bearing. Without `azure-mgmt-monitor` installed
or `Monitoring Reader` granted, the Monitor stats appear in `partial` and
every data-plane stat still returns:

```python
stats = CosmosStats(
    container=CONNECTORS.cosmos("azdatalive", "assets").container,
    database="azdatalive", container_name="assets",
    metrics=MetricsReader.from_config(CONFIG, my_provider),  # optional
)
```

The journal is the telemetry seam. Off by default, bounded, no I/O:

```python
from azdata import journal
journal.enable()
journal.subscribe(lambda record: my_sink(record.as_dict()))
```

### The verify plane

*What actually changed, and did anything change that I did not ask for.*
The write plane's `verified: true` means the keys you handed it read back.
It says nothing about the forty documents a concurrent process deleted
while you were writing.

```python
from azdata import CosmosKeys, Effect, verify_effect

keys = CosmosKeys(container=container, database="azdatalive",
                  container_name="assets", stats_provider=stats)

payload = json.loads(await verify_effect(
    keys,
    expect=Effect.added(["asset-41"]),
    operation=lambda: items.upload([{"id": "asset-41", "site": "north"}]),
))
payload["observed"]   # added / removed / changed / unchanged / counts
payload["before"]["digest"] != payload["after"]["digest"]
```

`Effect.added` / `removed` / `changed` / `unchanged` / `count_delta` /
`any`. Matching is strict: an operation that also changed something you did
not declare **fails**. A mismatch is an error envelope carrying the whole
observation, never `ok: true` with `matched: false`.

`Effect.unchanged()` is how a refusal is proven, and it is the check worth
writing first:

```python
# A read-only connector must leave a byte-identical digest.
payload = json.loads(await verify_effect(
    keys, expect=Effect.unchanged(),
    operation=lambda: read_only_items.upload([{"id": "x", "site": "north"}]),
))
assert payload["ok"] and payload["before"]["digest"] == payload["after"]["digest"]
```

Enumeration is capped by `AZDATA_VERIFY_MAX_KEYS` (default 5000). Above the
cap the snapshot samples deterministically, the digest covers only the
sample, and `sampled: true` says so — a verification that silently degraded
to a count comparison is the failure this plane exists to prevent.

`fabric_graph` has no verify plane. Nothing there mutates, so there is no
delta to take; the reason is in its `__init__` docstring.

### The discover plane

*What is actually there.* Enumeration one level at a time, bounded, and
never raising: a dark branch reports why it is dark.

```python
from azdata import DiscoveryBounds, DiscoveryScope, build_discovery_registry

registry = build_discovery_registry(CONFIG)          # no I/O; all five registered
search = registry.get("search")

result = await search.discover("service", DiscoveryScope())
if result.status == "ok":
    for node in result.nodes:                        # ordered (kind, name)
        child = await search.discover(search.child_level("service"),
                                      DiscoveryScope(path=node.path),
                                      bounds=DiscoveryBounds(max_items=100))
```

`status` is `ok`, `empty`, `forbidden`, `unreachable`, `unconfigured` or
`unavailable` — never an exception. `forbidden` wants a role grant;
`unreachable` wants a network fix and a role grant will not help.
`truncated` means more existed past `max_items`. Install with
`pip install -e ".[discover]"`.

### Reading the result

Everything except `graph` returns a JSON string in one of three shapes:

```json
{"error": true, "detail": "..."}       // failed; no answer
{"degraded": true, "detail": "..."}    // reduced fidelity; keep going
{"ok": true, "operation": "upload", ...}  // a mutation completed
```

...or, on a read, the success payload. `azdata.is_error(payload)` and
`azdata.is_ok(payload)` are the cheap checks; both return False on garbage
rather than raising. `degraded` is deliberately distinct — treating it as
failure discards a usable answer.

The `ok` envelope is for mutations only. Reads keep their own
service-shaped payloads, because a caller projecting search hits should not
have to unwrap an operation envelope first.

Details are URL-stripped and capped at 500 characters, because SDK
exception text carries your endpoint hostnames and the reader is often an
LLM context or a log aggregator.

### Guardrails

On by default: read-only validation and row-cap injection, per language.

```python
from azdata import ensure_limit, validate_read_only

validate_read_only("g.V().drop()", "gremlin")   # -> refusal message
ensure_limit("Events", "kql", 50)               # -> "Events | take 50"
```

Turn them off explicitly if a read-only role already covers you:

```python
GremlinConnector.from_config(cfg, provider, validate_fn=None, transform_query=None)
```

These are regexes with known false negatives. They are a floor, not a
sandbox — the real boundary is a reader role assignment (G10).

### Concurrency and failure

* A **circuit breaker per endpoint**, so one failing service cannot disable
  a healthy one.
* A **semaphore** where capacity is shared (Fabric bills concurrency
  against a fixed capacity unit).
* `azdata.registry.all_statuses()` feeds a health endpoint with every
  breaker at once.

```python
from azdata import registry
health = {"dependencies": registry.all_statuses()}
```

Tune through config: `max_concurrent`, `breaker_threshold`,
`breaker_cooldown_secs`.

### Per-request targets

When the target varies per request, build the connector directly and give
it a resolver instead of a fixed config:

```python
from azdata import KqlConnector, KqlTarget, get_gate

connector = KqlConnector(
    resolve_target=lambda: KqlTarget(*current_request_cluster()),
    credential_provider=my_provider,
    gate_provider=lambda: _gate(),          # async, returns a ThrottleGate
)
```

## Verify

```bash
python3 tests/unit/selftest.py            # no SDKs, no cloud, no test framework
python3 tests/unit/test_search_planes.py  # Search write + deploy
python3 tests/unit/test_cosmos_planes.py  # Cosmos write + deploy
python3 tests/unit/test_gremlin_planes.py # Gremlin write + deploy
python3 -m pytest tests/unit/test_guardrails.py -q     # guardrail edge cases
python3 -m pytest tests/unit/test_observe_plane.py -q  # stats, metrics, journal
python3 -m pytest tests/unit/test_verify_plane.py -q   # snapshots and deltas
python3 -m pytest tests -q                             # everything
```

The first four are self-running scripts and exit non-zero on any failed
check. `test_guardrails.py` is a pytest module: running it as a script
exits 0 without asserting anything, so use the pytest invocation. The
observe and verify suites are pytest modules for the same reason.

The selftest substitutes every Azure SDK with a fake that asserts on what
the connector sent, so it proves token refresh, transient retry, permit
release during backoff, continuation paging and quota fallback — offline.
The plane suites do the same for verification, partial batch failure,
chunking, traversal escaping, LRO bounding and drift detection. Every one
of those is proven **against a fake SDK**, not against Azure.

Use the same seam to test your own code:

```python
from azdata.core.optional import clear_overrides, override
override("azure.kusto.data", my_fake_module)
...
clear_overrides()
```

To prove a *missing* SDK path, simulate the absence rather than relying on
it — several of these SDKs are installed in most environments (G24):

```python
sys.modules["azure.mgmt.cosmosdb"] = None   # import_module now raises
```

Against real services:

```bash
export AZDATA_KQL_QUERY_URI=... AZDATA_KQL_DATABASE=...
python3 scripts/probe.py                       # every configured surface
python3 scripts/probe.py --service kql
python3 scripts/probe.py --search-index my-index
python3 scripts/probe.py --service documents --search-index my-index
python3 scripts/probe.py --service cosmos-container \
    --cosmos-database db --cosmos-container items
```

The probe **never writes**: write-plane connectors are built with
`WritePolicy.read_only()` and probed with `query`, provisioners with
`ProvisionPolicy.read_only()` and probed with `describe`. That proves the
endpoint, the credential and the reader role. It does not prove a
contributor role, and nothing can prove one without mutating something.

Unconfigured surfaces are skipped. Exit 1 means a configured surface
failed; exit 2 means nothing was configured.

## Troubleshoot

Start from the symptom in `GOTCHAS.md`:

| Symptom | Entry |
| --- | --- |
| Gremlin fails about an hour after deploy | G1 |
| `This event loop is already running` | G2 |
| One slow query stalls everything else | G3 |
| `Free Query Semantic Usage exceeded` | G4, G5 |
| Every call hangs, nothing logged | G6 |
| GQL 200 with no rows, or truncated results | G7 |
| Closing one store breaks the others | G8 |
| A brief token blip causes a wave of 500s | G9 |
| A write query got past the guard | G10 |
| Health check always false | G11 |
| Gremlin 403 at the WebSocket upgrade | G12 |
| Graph load is slow and unresumable | G13 |
| An Azure setting reverts after a 200 | G14 |
| A KQL `has` filter matches nothing | G15 |
| Intermittent 502 on a multi-query endpoint | G16 |
| A "scoped" Cosmos query costs a full scan | G17 |
| A healthy deployment is reported as drifted | G18 |
| `ensure` said ok and the setting is wrong | G19 |
| An uploaded Search document is not retrievable | G20 |
| A Cosmos delete succeeded and the item is there | G21 |
| A Gremlin `drop()` deleted nothing, silently | G22 |
| A name with an apostrophe breaks a traversal | G23 |
| A missing-SDK test passes for the wrong reason | G24 |
| A delete-granted writer is refused the delete | Fixed; see G25 |

## Remove

Nothing is registered globally and no import is patched.

1. Replace `connect(...)` with your own client construction.
2. Delete `azdata/`.
3. Drop the rows you added to `requirements.txt`.
4. Remove the `AZDATA_*` variables last — they are inert once the code is
   gone.

The only module-level state is the breaker registry and the named gate
cache, both plain dictionaries that die with the process.
