# SPEC — Azure Data Connector Library (`azdata`)

Status: built; this file is the design record the code is annotated against
(`SPEC 7.1`, `SPEC 7.4` and similar references in source comments).
Import name: `azdata`

---

## 1. Why this exists as a project

The connector code is real and proven offline: 12,444 lines, three planes
(read, write, deploy), five services, 303 framework-free checks passing with no
SDKs, no network and no cloud account.

Three things were wrong with where it sat and what it proved.

**Wrong location.** It lived inside a consuming application's vendored
reference tree, as a copy with its own remote and uncommitted changes. Nothing
in the application could import it. Every consumer copied the folder, and every
copy forked a moving target.

**Wrong shape.** `azdata/` is 22 flat private modules whose service boundary is
a filename prefix. Adding a sixth service means editing five shared files and
guessing which prefix convention applies. A reader cannot see where Cosmos ends
and Search begins.

**Wrong evidence.** Every one of the 303 checks runs against fake SDKs. Not one
line of this library has been proven against a live Azure data service. The two
mutating planes make a claim — *an accepted write is not evidence of changed
state* — that has never been tested where it matters, against a service that
actually accepts writes and actually reverts them.

This project fixes all three, and adds the two capabilities the library needs
before a host application can drive it: **verification** and **observability**.

---

## 2. Outcome

When this is done:

1. `import azdata` works anywhere in the host application after one editable
   install.
2. Each Azure data service owns one folder. Adding a sixth service touches that
   folder plus one registry line.
3. A resource group `rg-azdata-live` holds one live instance of every
   ARM-provisionable service the library supports.
4. Every plane has been exercised against those live instances, and the
   evidence is a recorded transcript, not an assertion.
5. After any CRUD operation a caller can ask *what actually changed* and get a
   measured answer, not a success code.
6. For any target a caller can ask *how is this doing* and get key stats:
   counts, sizes, throughput, latency, throttling, cost signal.

---

## 3. Placement

```
azure-data-connectors/            <- this project
  pyproject.toml               makes `azdata` a real top-level import
  SPEC.md                      this file
  README.md                    failure model and rationale
  SKILL.md                     agent-facing usage
  CONTRACT.md                  exact shapes, for reimplementation
  GOTCHAS.md                   symptom-first production failures
  src/azdata/                  the package
  tests/                       offline + live suites
  scripts/                     probe, stats, environment lifecycle
  examples/
```

`src/` layout, deliberately: it makes an accidental import of the working
directory impossible, so a passing test proves the *installed* package works.

Install: `pip install -e <this directory>`.

The harness copy is removed in the same change. There is one library, in one
place. Divergence is not managed, it is prevented.

---

## 4. Package architecture

### 4.1 One folder per Azure data service

```
src/azdata/
  __init__.py            public surface — the only stable import path
  core/                  service-blind mechanism
  search/                Azure AI Search
  cosmos/                Cosmos DB NoSQL
  gremlin/               Cosmos DB Gremlin
  kusto/                 Azure Data Explorer / Fabric Eventhouse
  fabric_graph/          Fabric GraphModel (GQL over HTTPS)
  live/                  the rg-azdata-live topology, as code
```

### 4.2 Uniform service folder

Every service folder uses the same five names. A file is absent when the plane
does not exist for that service; it is never renamed.

| File | Contains | Plane |
| --- | --- | --- |
| `read.py` | the query connector | read |
| `write.py` | the `CrudConnector` subclass | write |
| `deploy.py` | the `Provisioner` subclasses | deploy |
| `observe.py` | the `StatsProvider` — key stats for this service | observe |
| `verify.py` | what "changed state" means here — snapshot and delta | verify |
| `__init__.py` | this service's exports, and nothing else | — |

Coverage per service:

| Service | read | write | deploy | observe | verify |
| --- | :-: | :-: | :-: | :-: | :-: |
| `search` | yes | yes | yes | yes | yes |
| `cosmos` | yes | yes | yes | yes | yes |
| `gremlin` | yes | yes | yes | yes | yes |
| `kusto` | yes | ingest | yes | yes | yes |
| `fabric_graph` | yes | no | no | yes | no |

`kusto.write` is ingestion, not CRUD: Kusto has no update and no per-row
delete, so it implements a narrower `IngestConnector` rather than pretending to
satisfy `CrudConnector`. Naming the difference is the point.

`fabric_graph` gets no deploy plane because Fabric GraphModels are not ARM
resources and cannot be created in a resource group. This is a platform
constraint, stated once here and once in the service `__init__`.

### 4.3 `core/`

Everything with no service opinion. Migrated from the current flat modules,
renamed from `_x.py` to `x.py` — a package folder already carries the
privacy signal, and a leading underscore on every file makes grep useless.

| Module | From | Purpose |
| --- | --- | --- |
| `config.py` | `_config.py` | `AzureDataConfig`, read once, frozen |
| `credentials.py` | `_credentials.py` | three-tier `TokenCredential`, cached |
| `token.py` | `_token.py` | bearer cache with stale-token fallback |
| `optional.py` | `_optional.py` | per-connector SDK loading, and the test seam |
| `envelope.py` | `_envelope.py` | error / degraded / ok result shapes |
| `breaker.py` | `_breaker.py` | circuit breaker, registry, throttle gate |
| `guardrails.py` | `_guardrails.py` | read-only enforcement, row caps |
| `crud.py` | `_crud.py` | `CrudConnector`, `WritePolicy`, verification |
| `provision.py` | `_provision.py` | `Provisioner`, `ProvisionPolicy`, drift |
| `connect.py` | `_connect.py` | the injection seam |
| `verify.py` | **new** | snapshot / delta / effect assertion |
| `observe.py` | **new** | `StatsProvider` contract, stat envelope |
| `metrics.py` | **new** | Azure Monitor metric reads, service-blind |
| `journal.py` | **new** | in-process operation log for every plane call |

### 4.4 Compatibility

`azdata.__init__` re-exports every name currently in `__all__` at the same
path. Existing callers written against the harness copy keep working. Deep
imports of `azdata._search` do not, and were never public.

New names are added to `__all__`, never substituted for old ones. Version goes
to `3.0.0` because the internal layout is a breaking change for anyone who
reached past the public surface.

---

## 5. New capability — the verification plane

### 5.1 The claim being tested

The library already verifies writes by reading back the keys it was handed.
That answers *did my item land*. It does not answer the question a caller
operating a system actually has: **what changed, and did anything change that I
did not ask for.**

A create that succeeds while a concurrent process deletes forty documents
returns `{"ok": true, "count": 1, "verified": true}`. That envelope is true and
useless.

### 5.2 Mechanism

Three service-blind types in `core/verify.py`, one implementation per service
in `<service>/verify.py`.

```python
@dataclass(frozen=True)
class StateSnapshot:
    service: str          # "search" | "cosmos" | "gremlin" | "kusto"
    target: str           # index / container / graph / table
    taken_at: str         # ISO-8601, UTC
    count: int            # total addressable items, -1 when uncountable
    keys: tuple[str, ...] # sampled or full key set, bounded
    digest: str           # sha256 over the sorted key set
    stats: Mapping        # the observe-plane stats at capture time
```

```python
@dataclass(frozen=True)
class StateDelta:
    added:     tuple[str, ...]
    removed:   tuple[str, ...]
    changed:   tuple[str, ...]   # key present in both, content digest differs
    unchanged: int
    count_before: int
    count_after:  int
```

```python
async def verify_effect(
    connector, target, *, expect: Effect, operation: Callable[[], Awaitable[str]]
) -> str
```

`verify_effect` snapshots, runs the operation, snapshots again, diffs, and
returns a `verify` envelope. `Effect` declares what the caller intended:

```python
Effect.added(keys)      Effect.removed(keys)     Effect.changed(keys)
Effect.unchanged()      Effect.count_delta(n)    Effect.any()
```

`Effect.unchanged()` is not decoration. It is how a refusal is proven: a write
denied by policy must leave a byte-identical digest, and that is the negative
test the positive one is worthless without.

### 5.3 Envelope

```json
{"ok": true, "operation": "verify", "service": "search", "target": "hc-docs",
 "matched": true, "expected": {"added": ["d1","d2"]},
 "observed": {"added": ["d1","d2"], "removed": [], "changed": [],
              "unchanged": 40, "count_before": 40, "count_after": 42},
 "before": {...snapshot...}, "after": {...snapshot...},
 "elapsed_ms": 812}
```

A mismatch returns an **error** envelope carrying the same observation. A
verification that does not match is a failure, not a warning with `ok: true`.

### 5.4 Bounds

Key enumeration is capped (`AZDATA_VERIFY_MAX_KEYS`, default 5000). Above the
cap, `keys` holds a deterministic sample and `digest` covers only the sample;
`sampled: true` appears in the snapshot. A verification that silently degrades
to a count comparison without saying so is the failure mode being designed out.

---

## 6. New capability — the observability plane

### 6.1 Contract

```python
class StatsProvider(Protocol):
    service: str
    async def stats(self, target: str | None = None) -> str: ...
```

Returns a `stats` envelope:

```json
{"ok": true, "operation": "stats", "service": "cosmos", "target": "hc/items",
 "collected_at": "2026-08-30T12:00:00Z", "source": "data-plane",
 "stats": {...}, "partial": []}
```

`source` is `"data-plane"`, `"management-plane"` or `"monitor"`. `partial`
lists stat names that could not be collected and why — a stats call never fails
wholesale because one counter was unavailable, and never omits a counter
silently.

### 6.2 Per-service key stats

**Search** — `get_service_statistics` plus per-index counts.

| Stat | Source |
| --- | --- |
| `document_count`, `storage_bytes`, `vector_index_bytes` | index statistics |
| `index_count`, `indexer_count`, `synonym_map_count` | service statistics |
| `quota_*` and `usage_*` for each counter | service statistics |
| `semantic_query_usage` | service statistics |
| `search_latency_p50_ms`, `throttled_query_pct` | Azure Monitor |

**Cosmos NoSQL**

| Stat | Source |
| --- | --- |
| `item_count` | `SELECT VALUE COUNT(1)` |
| `throughput_ru`, `autoscale_max_ru`, `is_serverless` | management plane |
| `partition_key_paths`, `indexing_mode`, `ttl_seconds` | container properties |
| `last_request_charge_ru`, `session_token` | data-plane response headers |
| `total_request_units`, `normalized_ru_pct`, `server_side_latency_ms` | Azure Monitor |

**Gremlin**

| Stat | Source |
| --- | --- |
| `vertex_count`, `edge_count` | `g.V().count()`, `g.E().count()` |
| `label_histogram` | `g.V().groupCount().by(label)` |
| `last_request_charge_ru` | traversal status attributes |
| `throughput_ru`, `graph_partition_key` | management plane |

**Kusto**

| Stat | Source |
| --- | --- |
| `cluster_state`, `sku`, `instance_count` | management plane |
| `table_row_count`, `table_extent_bytes`, `hot_extent_bytes` | `.show table … details` |
| `ingestion_failures_24h` | `.show ingestion failures` |
| `cache_utilisation_pct`, `cpu_pct`, `ingestion_latency_s` | Azure Monitor |

**Fabric GraphModel**

| Stat | Source |
| --- | --- |
| `node_types`, `edge_types`, `schema_version` | metadata endpoint |
| `last_query_status_code` | query response `status` block |

### 6.3 Journal

`core/journal.py` records every plane call in-process: operation, service,
target, outcome, `elapsed_ms`, RU charge where the service reports one, and
whether verification ran. Bounded ring buffer, no I/O, off by default,
subscribable.

This is the seam a host application's agent telemetry consumes. It exists here
because only the connector knows the RU charge and the verification outcome,
and reconstructing either from a log line is guesswork.

### 6.4 Azure Monitor

`core/metrics.py` wraps `azure-mgmt-monitor` behind one service-blind call:

```python
await metrics.read(resource_id, names=[...], window=timedelta(minutes=30),
                   aggregation="Average")
```

Never required. When `azure-mgmt-monitor` is absent or the caller lacks
`Monitoring Reader`, the affected stat names appear in `partial` and every
data-plane stat still returns.

---

## 7. The live environment — `rg-azdata-live`

### 7.1 Topology

The subscription and tenant are supplied by the operator at every entry point
and are recorded nowhere here. Region `eastus` — choose a region whose policy
assignments do not revert storage and networking settings; see GOTCHAS.

| Purpose | Resource | SKU | Idle cost | Notes |
| --- | --- | --- | --- | --- |
| AI Search | `srch-azdatalive` | **basic** | ~US$74/mo | one free service per subscription, commonly already consumed |
| Cosmos NoSQL | `cosmos-azdata-nosql` | serverless | ~US$0 | pay per RU |
| Cosmos Gremlin | `cosmos-azdata-gremlin` | serverless, `EnableGremlin` | ~US$0 | Gremlin needs its own account; capability is account-level |
| Kusto | `adx-azdatalive` | Dev/No-SLA `Standard_D11_v2`, 1 instance | ~US$0.10/hr running, **US$0 stopped** | 10–15 min to create; left running by decision §11, `pause` stops it. `Standard_E2a_v4` was refused for want of capacity |
| Telemetry sink | `log-azdatalive` | Log Analytics, pay-per-GB | ~US$0 | diagnostic settings from all four |
| Fabric GraphModel | *none* | — | — | not an ARM resource; cannot live in a resource group |

Standing cost with ADX stopped: **~US$74/month**, entirely the Search basic
tier. All three cost decisions are answered in §11.

### 7.2 Seeded content

Each live instance carries one small fixed dataset so verification has
something to diff. The dataset is domain-blind — synthetic asset records — so
no caller's schema leaks into the library.

| Service | Object | Seed |
| --- | --- | --- |
| Search | index `azdata-assets` | 40 documents, keyword + vector field |
| Cosmos | db `azdatalive` / container `assets`, pk `/site` | 40 items across 4 partitions |
| Gremlin | db `azdatalive` / graph `assets` | 40 vertices, 60 edges, 3 labels |
| Kusto | db `azdatalive` / table `Assets` | 40 rows |

### 7.3 Lifecycle, as code

`azdata.live` describes the topology declaratively and drives it through the
existing deploy plane — the environment is itself a test of the provisioners.

```bash
python -m azdata.live up        # create RG, all resources, roles, seed
python -m azdata.live status    # describe + stats for everything
python -m azdata.live pause     # stop ADX; leave data intact
python -m azdata.live resume
python -m azdata.live down      # delete the resource group, verified
```

`down` deletes the whole resource group and then re-reads to prove absence.
It refuses unless the group carries tag `azdatalive-owned=true`, applied at
creation. A teardown that can reach a resource group it did not create is a
teardown that will eventually reach the wrong one.

### 7.4 Role assignments

Management-plane `Contributor` on the resource group does not grant Cosmos data
access. `up` assigns, to the running identity:

| Scope | Role |
| --- | --- |
| resource group | `Contributor` |
| `srch-azdatalive` | `Search Index Data Contributor` |
| `cosmos-azdata-nosql` | `Cosmos DB Built-in Data Contributor` (via `az cosmosdb sql role assignment create`) |
| `cosmos-azdata-gremlin` | same data-plane contributor role |
| `adx-azdatalive` db | `Admin` on database `azdatalive` |
| resource group | `Monitoring Reader` |

Each assignment is followed by a read-back. Role propagation is eventually
consistent; `up` polls until a real data-plane call succeeds rather than
sleeping a guessed interval.

---

## 8. Test strategy

Two suites. They test different things and neither substitutes for the other.

### 8.1 Offline conformance — `tests/unit/`

The existing 303 checks, migrated. Fake SDKs, no network, no account, runs in
CI and on a laptop with nothing installed. Proves shape, policy, guardrails and
failure handling. Extended with:

- verification: delta computation, sampling behaviour at the key cap, digest
  stability under key reordering;
- observability: envelope shape, `partial` population when a counter raises,
  journal bounds and ordering;
- **negative policy tests, paired to every positive one**: refused write leaves
  `Effect.unchanged()` satisfied; a `ProvisionPolicy` without teardown refuses;
  a read-only `WritePolicy` cannot be widened by cache lookup
  (note `note-20260830T105501Z-908c197a`).

### 8.2 Live conformance — `tests/live/`

Skipped unless `AZDATA_LIVE=1` and the environment is up. Never runs in CI.

For each service, one full cycle against the real instance:

1. `describe` — resource exists, state read back
2. `stats` — every declared stat present or explained in `partial`
3. snapshot
4. create → `verify_effect(Effect.added(keys))`
5. retrieve — content matches what was written
6. upload/replace → `verify_effect(Effect.changed(keys))`
7. query — the read plane returns the written items
8. delete → `verify_effect(Effect.removed(keys))`
9. snapshot equals step-3 snapshot: **digest identical**, not merely count equal
10. refused write with a read-only policy → `Effect.unchanged()` holds
11. `stats` again — deltas consistent with the operations performed

Step 9 and step 10 are the reason this suite exists. Step 9 proves the test
left no residue. Step 10 proves the grant model is enforced by the service and
not just by the Python.

Deliberate live negatives, each recorded with its refusal:

| Negative | Expected |
| --- | --- |
| write with `WritePolicy.read_only()` | `WriteRefused`, digest unchanged |
| delete without `allow_delete` | `WriteRefused`, digest unchanged |
| `teardown` without `ProvisionPolicy.allow_teardown` | `ProvisionRefused`, resource still present |
| `ensure` a field Azure Policy reverts | drift reported as **error**, not `ok` |
| Search read-back immediately after upload | eventual consistency handled by polling, not by sleep (G20) |
| Cosmos delete of an absent id | per-item `ok: false`, batch continues |
| query without `limit` | guardrail injects it; row cap holds |

### 8.3 Evidence

Live runs write a transcript to `tests/live/_evidence/<utc>.json`: every
envelope, in order, with timings. A live claim in the notebook cites a
transcript path. An untranscripted live claim is not evidence.

---

## 9. Security posture

- Identity only. No connection string, account key or SAS token anywhere,
  including in the live environment scripts.
- The library never logs a credential and never writes one to disk. Details in
  every envelope are URL-stripped and capped at 500 characters before they
  reach a caller or an LLM context.
- Denied by default on both mutating planes; delete is always a separate grant.
- `client_secret` is excluded from the config repr.
- Notebook notes reference the live environment by resource name only. No
  endpoint hostnames, no ids beyond the subscription already recorded here, no
  secrets.
- Teardown is tag-gated (§7.3).

---

## 10. Delivery phases

Each phase ends with executable evidence. No phase begins before the previous
one's evidence exists.

| # | Phase | Done when |
| --- | --- | --- |
| 1 | **Move and install** — relocate to `components/data_connector_library`, add `pyproject.toml`, `src/` layout, delete the harness copy | `pip install -e` succeeds; `import azdata` from an unrelated cwd; all 303 existing checks pass unchanged |
| 2 | **Modularise** — split flat modules into `core/` + five service folders, drop the underscore prefixes, keep `__init__` exports byte-identical | 303 checks still pass; no test file edited except its import line; `grep -r "azdata\._" src` returns nothing |
| 3 | **Verification plane** — `core/verify.py` + five `verify.py` | new offline checks pass, including every negative pairing |
| 4 | **Observability plane** — `core/observe.py`, `metrics.py`, `journal.py` + five `observe.py` | new offline checks pass; `partial` proven populated by a raising counter |
| 5 | **Live environment** — `azdata.live up` builds `rg-azdata-live` | every resource read back after creation; `status` returns full stats for all four; cost recorded |
| 6 | **Live conformance** — `tests/live/` full cycle per service | transcript exists; step 9 digests identical; every §8.2 negative refused as specified |
| 7 | **Documentation** — SKILL / CONTRACT / GOTCHAS updated for the two new planes and the new layout | CONTRACT documents the `verify` and `stats` envelopes exactly; new gotchas recorded from what live testing actually broke |
| 8 | **Close** — notebook notes published, environment left standing per §11 | work-issue note transitioned `inactive` with evidence |

Phases 3 and 4 are independent and may run in parallel. Phase 6 cannot start
until 5 is verified, and phase 5 is the first billable step.

---

## 11. Cost decisions — answered

All three are decided. The figures below are unchanged and still true;
what changed is that they are no longer questions.

1. **Search SKU — create `srch-azdatalive` at `basic`.** A subscription's one
   free search service is commonly already in use elsewhere, and sharing it
   would mean a 3-index limit shared with unrelated work and no isolation
   between the two. A new basic service costs ~US$74/mo standing and is the
   whole standing cost of this environment.
2. **Kusto — included, as a Dev/No-SLA cluster.** ~US$0.10/hr running,
   US$0 stopped, 10–15 minutes to create. The KQL connector is therefore
   tested against a real cluster rather than only offline.
3. **Teardown — the environment stays running between sessions.** `down`
   still exists and is still tag-gated, but nothing calls it
   automatically, and the ADX cluster is **not** stopped by default.
   `pause` and `resume` are implemented because stopping ADX is the only
   real cost lever here, not because anything invokes them on a schedule.
   Recreating from nothing is ~20 minutes, dominated by ADX, which is why
   leaving it standing is the cheaper trade at this cadence.

Standing cost under these answers: **~US$74/month with ADX stopped**, plus
~US$0.10/hr for the hours the cluster is left running. `status` reports
the standing cost so a forgotten environment announces itself.

Everything in phases 1–4 was free, local and reversible and did not depend
on these answers.

---

## 12. Risks

| Risk | Handling |
| --- | --- |
| Management SDK model-shape disagreement silently reports drift on healthy deployments | Already known and normalised per SDK (note `note-20260830T102956Z-602b33ec`); `azure-mgmt-kusto` 4.x introspected as the JSON-backed camelCase style and pinned by a test; live testing is the first real check of that normalisation |
| Role propagation delay makes phase 5 look like an auth failure | `up` polls a real data-plane call, never sleeps a guessed interval |
| ADX creation timeout inside a single agent run | Creation is async with a resumable poll; `up` is idempotent |
| Live tests leave residue and the next run diffs against a dirty baseline | Step 9 digest equality; a run that cannot restore its baseline fails loudly |
| Search eventual consistency read as a bug | Verification polls with a bounded budget and reports the wait (G20) |
| Harness clone diverges again after the move | The harness copy is deleted, not left as a fork |
| Cost drift from a forgotten environment | `status` reports standing cost; the environment stays running by decision §11, so the cost is stated rather than assumed away; `pause` stops ADX and teardown is one command |
