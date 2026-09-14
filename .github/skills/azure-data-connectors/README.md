# azure-data-connectors

Connect to Azure data services with **identity, limits and a failure model
already in place**. Five connectors — Cosmos DB Gremlin, Fabric Eventhouse
(Kusto), Azure AI Search, Fabric GraphModel, Cosmos DB NoSQL — behind one
wiring call, returning one result shape.

Self-contained. Copy this folder anywhere. Python 3.11+, plus one Azure SDK
per connector you actually use. Nothing is imported until it is called.

## The planes

The read plane answers questions. The others exist because an agent that
has to find a service, stand it up, load it, query it and tear it down
inside one run has no deployment pipeline in that loop.

| Plane | Surface | Denied until | Proof of success |
| --- | --- | --- | --- |
| Read | `execute` on a connector | — (read-only guard is always on) | The payload |
| Write | `SearchDocuments`, `CosmosItems`, `GremlinElements` | a `WritePolicy` grants it | A read-back of every accepted key |
| Deploy | the `*Provisioner` classes | a `ProvisionPolicy` grants it | A read-back of every requested field |
| Discover | the `*Discoverer` classes, `build_discovery_registry` | — (enumeration only; no call can mutate) | A `DiscoveryResult` whose status says `ok`, or says exactly why not |

The two mutating planes share one rule the read plane does not need:
**an accepted write is not evidence of changed state.** Every claim below
about verification comes back to that sentence.

The discover plane has its own: **a failure is a value with a reason.**
`forbidden` is fixed by a role grant, `unreachable` is a network fact that
a role grant will not touch, and `unconfigured` means nobody set the
coordinate. Collapsing the three into "error" sends an operator to the
wrong console.

```
azure-data-connectors/
  README.md            you are here — failure model and rationale
  SKILL.md             agent-facing: decide, install, use, verify, remove
  CONTRACT.md          exact shapes, constants and retry algorithms
  GOTCHAS.md           twenty-seven production failures, symptom-first
  azdata/              the mechanism
    __init__.py          public surface
    _connect.py          the injection seam: connect(config, credential_provider)
    _config.py           AzureDataConfig — coordinates, read once, frozen
    _credentials.py      three-tier TokenCredential, cached
    _optional.py         per-connector SDK loading, and the test seam
    _envelope.py         error / degraded / ok result shapes
    _breaker.py          circuit breaker, registry, throttle gate
    _guardrails.py       read-only enforcement, row caps
    _token.py            bearer token cache with stale-token fallback
    _gremlin.py          Cosmos DB Gremlin                      read
    _kql.py              Fabric Eventhouse / Azure Data Explorer read
    _search.py           Azure AI Search                        read
    _graph.py            Fabric GraphModel (GQL over HTTPS)     read
    _cosmos.py           Cosmos DB NoSQL                        read
    _crud.py             CrudConnector, WritePolicy, verification  write
    _search_data.py      Search document CRUD                   write
    _cosmos_data.py      Cosmos item CRUD, partition-scoped     write
    _gremlin_data.py     Gremlin vertex CRUD by generated traversal write
    _provision.py        Provisioner, ProvisionPolicy, drift    deploy
    _search_infra.py     Search index (data plane) and service (ARM) deploy
    _cosmos_infra.py     Cosmos account, database, container    deploy
    _gremlin_infra.py    Gremlin database and graph             deploy
  scripts/
    probe.py             live reachability check, exit-code driven.
                         Reads only; never writes, never provisions.
  examples/
    agent_tools.py       the seam, worked, as agent-callable tools
  tests/
    selftest.py          full transport proof with fake SDKs, no framework
    test_guardrails.py   guardrail edge cases (pytest module)
    test_search_planes.py   Search write and deploy planes
    test_cosmos_planes.py   Cosmos write and deploy planes
    test_gremlin_planes.py  Gremlin write and deploy planes
```

---

## 1. The problem

Every Azure SDK sample connects in four lines, and every one of those four
lines is wrong for a service that stays up.

| The sample does | What it costs in production |
| --- | --- |
| Connection string or account key | Unscopable, unrotatable, ends up in a config file |
| Builds a client per call | A TLS handshake and a token fetch on every request |
| Builds a client once, forever | Works for an hour, then the token expires (G1) |
| Raises the SDK exception | The caller gets a stack trace where it needed an answer |
| Retries on failure | Turns a throttled service into a throttled dead service |
| No concurrency limit | Your dashboard endpoint throttles someone else's job (G16) |
| Unbounded query | The whole graph, into memory, into a context window |
| Unbounded health probe | Nine SDK retries block your readiness endpoint (G11) |

None of these is hard. All of them are a day each to find, and the finding
happens in production because none of them fail on a laptop.

## 2. What this is

The five connectors share one behaviour model:

**Identity, never keys.** Every connector authenticates with a
`TokenCredential`. Managed identity inside Azure, `az login` locally, and a
service principal only for genuine cross-tenant access. Same code path in
all three; rotation needs no redeploy. Access is a role assignment, which
means the permission surface is reviewable in your infrastructure code.

**Failure is a value, not an exception.** Connectors return
`{"error": true, "detail": ...}` or `{"degraded": true, "detail": ...}`.
The distinction is load-bearing: degraded means an answer exists at lower
fidelity and the caller should continue. Details are URL-stripped and
capped, because SDK exception text carries your endpoint hostnames and the
caller is frequently an LLM context or a log aggregator.

**Bounded by default.** Read-only guards and row caps are on unless you
switch them off. A circuit breaker per endpoint, so one failing service
cannot disable a healthy one. A semaphore where capacity is shared, because
Fabric bills concurrency against a fixed capacity unit and your parallelism
is someone else's outage.

**Nothing loads until it is used.** SDKs are imported through
`src/azdata/core/optional.py` on first call. Installing the box does not install
five client libraries, importing it cannot fail on a missing one, and a
missing SDK produces a message naming the distribution to install.

**Denied by default, on the two planes that can do damage.** Nothing
mutates data or infrastructure until a policy object says it may, and
delete is always a grant of its own. A read-only credential is still the
real boundary; the policy is the guard that fails closed at the point of
use, in front of it, and it names what is missing when it refuses.

## 3. The injection seam

One function. This is the whole integration surface:

```python
from azdata import AzureDataConfig, connect

connectors = connect(AzureDataConfig.from_env())

rows  = await connectors.kql.execute("Events | where Level == 'Error'")
graph = await connectors.gremlin.execute("g.V().hasLabel('device')")
hits  = connectors.search.execute("query", index_name="kb",
                                  project_doc=my_projection)
```

Both arguments are overridable. Supply your own `credential_provider` for a
cross-tenant identity; construct a connector directly when targets vary per
request. `AzureDataConfig.from_env(prefix="")` adopts environment variable
names a repository already sets, so adoption needs no rename.

**What crosses the boundary, and what does not.** Connectors return generic
shapes — a bare list, `{columns, rows}`, `{results, count}`,
`{columns, data}`. Projection into your vocabulary happens in an injected
callable, on your side. `SearchConnector` goes further and *requires*
`project_doc`: it cannot know which field holds your text, and a default
would silently truncate someone's data. That inversion is why no field name
from any application appears in this package.

### 3.1 The write plane

Asking for a writer is the moment you state what you intend to mutate, so
it is a method taking a policy rather than a property with a default:

```python
from azdata import WritePolicy

writer = connectors.documents("knowledge-base",
                              policy=WritePolicy.writable(verify_writes=True))
result = await writer.upload([{"id": "d1", "chunk": "..."}])
```

`Connectors` caches one write connector per name **and policy**, so asking
for the same index under a narrower grant returns a narrower object rather
than the wider one built earlier (G25).

**Writes and deletes are separate grants.** Not ceremony: the two have
different blast radii and are almost never needed together by the same
caller. An ingest path writes and never deletes; a retention job deletes
and never writes. `WritePolicy.writable()` grants write only, and
`allow_delete=True` is a second, deliberate decision. A path that can only
write cannot remove a document however wrong its input is.

**Verification defaults on once a write grant is given.** The point of an
explicit grant is that somebody cares whether the write landed, and each of
these three services will tell you it landed when it did not:

| Service | The lie | What catches it |
| --- | --- | --- |
| Search | `succeeded=True` seconds before the document is retrievable | Bounded polling read-back (G20) |
| Cosmos | `delete_item` against the wrong partition key raises 404, identical to "already gone" | 404 from a delete is a *failed* result, and reads require a partition key (G21) |
| Gremlin | `drop()` matching nothing succeeds silently | A count taken before the drop, plus a re-read after (G22) |

`verify=True` re-reads every accepted key, polling up to `verify_attempts`
times with `verify_delay_secs` between attempts, and fails the operation
with `VerificationFailed` when the state never becomes what was asked for.
It costs one read per key. Turn it off per call with `verify=False` when
you are loading a million rows and will check the count instead.

**What the write plane does not guarantee.** There is no transaction. A
batch larger than `max_batch` is chunked and submitted in order, and a
chunk that fails leaves the earlier chunks applied — there is no rollback
and no compensating delete. `create` on Search is not atomic either: it
reads every key first because the service has no insert-if-absent, and
another writer can insert between that check and the upload. Callers
needing exactly-once semantics need a different store; callers needing
idempotence should use `upload`.

### 3.2 The deploy plane

This README used to say "provision with your infrastructure code", and for
a long-lived service that is still the right answer. It is worth being
explicit about what changed rather than quietly deleting the sentence.

What changed is the agent lifecycle. The old advice assumed a deployment
pipeline exists somewhere outside the process: somebody runs Bicep, then
the application starts and connects to what is already there. An agent that
has to stand a service up, load it, query it and tear it down **inside one
run** has no such pipeline in that loop. Its options were shelling out to
`az` — which turns every failure into a string to parse, drags in a CLI
dependency, and abandons the identity, breaker and envelope model the rest
of this package is built on — or a hand-rolled `begin_create_or_update`
wrapper per resource, which is this module without the read-back.

So the reversal is narrow, and it is not "provision your production
infrastructure from application code":

```python
from azdata import ProvisionPolicy

index = connectors.provision_search_index(
    "scratch-index", policy=ProvisionPolicy.deployable(allow_delete=True))
await index.ensure({"name": "scratch-index", "fields": [...]})
...
await index.teardown()
```

Create and delete are separate grants for the same reason as the write
plane. `describe` and `exists` need no grant at all. Long-running
operations are bounded: the management SDKs are synchronous and
`LROPoller.result()` blocks until the service finishes, which for a Cosmos
account is five to eight minutes and for a wedged one is forever, so the
poller is resolved off the event loop against a deadline and a stuck
deployment fails the run rather than hanging it.

And every `ensure` re-reads. That check is the reason this is worth having
over a wrapper around the SDK call; see section 4.

## 4. Design decisions a reimplementation would get wrong

**The half-open probe bypasses the semaphore.** If the recovery probe
queued for a permit like everything else, recovery detection would depend
on load — a busy service could never be observed to have recovered.

**The retry loop releases its permit before sleeping.** Backoffs here are
seconds to a minute. A retrying call that holds a permit across its own
sleep starves every other caller of the same capacity (G3).

**HTTP 200 is not success for GQL.** Fabric GraphModel reports query
outcome in the response body. A transport-level check reports invalid
queries as empty successes, and ignoring the `02000` continuation status
silently truncates results (G7).

**Semantic quota exhaustion is not a failure.** Azure AI Search refuses
semantic queries when the free monthly allowance runs out. Counted as
failures, three of those trip the breaker and take search down for a month.
Retry without the ranker instead, and leave the breaker alone (G4).

**Gremlin needs its own thread and its own loop.** The driver builds and
drives an asyncio loop inside `submit()`, which is illegal from a running
loop and wrong under uvloop (G2).

**The Gremlin client is cached with its token expiry.** Cosmos passes the
access token as the connection password and never refreshes it. The
connection does not fail at expiry; it fails on the next call, an hour after
deployment, with an opaque transport error (G1).

**`is_healthy` returns False and never raises — and that is dangerous.**
The bare `except` that makes a fallback safe will also swallow a `NameError`
from a missing import and pin a service on its in-memory store forever, with
nothing logged. The `import asyncio` in `_cosmos.py` is load-bearing, and
the selftest asserts a *healthy* container probes `True` — the only test
that catches it (G11).

**The deploy plane must read the resource back.** ARM returns HTTP 200 with
`provisioningState: Succeeded` for a write an Azure Policy `Modify` effect
reverted moments later. Nothing in the response says so. `ensure` re-reads
and reports a field that did not survive as an **error**, not a warning:
the infrastructure is not in the requested state, and a caller that
proceeds is building on a false premise (G19, mechanism in G14).

**But the read-back must compare only what the service echoes.** Comparing
everything reports drift on every healthy deployment, and a check that
cries wolf is switched off within a week, taking the real signal with it.
So `location` is excluded (ARM answers `"australiaeast"` to
`"Australia East"`), the Cosmos `locations` list is excluded (reordered and
enriched), Search index fields are narrowed to the declared name list
(analyzers and defaults are filled in), throughput hints are excluded (sent
and never returned) — and what remains is exactly what a `Modify` effect
rewrites illegitimately (G18).

**The two management SDKs have opposite model styles.**
`azure-mgmt-search` 9 is msrest: a `SearchService` is not a `Mapping` and
`as_dict()` is flattened snake_case with no `properties`.
`azure-mgmt-cosmosdb` 10 is JSON-backed: models *are* `Mapping`s,
`dict(model)` is the raw camelCase REST payload nested under `properties`,
and `resource` is an attribute but not a top-level dict key. A normaliser
written for one is wrong for the other, and the failure mode is drift on
every healthy deployment. Hence one normaliser per SDK, in the module that
owns it, deliberately not shared (G18).

**Cross-partition is the absence of a partition key, not a flag.**
`azure-cosmos` 4.x removed `enable_cross_partition_query`, and because
`query_items` takes `**kwargs` the removed flag is absorbed in silence — it
reads like an enforced scope and does nothing. A query is cross-partition
exactly when no `partition_key` is passed, so the connector forwards the
key when the caller supplied one and omits it otherwise, and never invents
one to recover from a key it could not determine (G17).

**Gremlin mutations are generated, never forwarded.** Gremlin has no write
API: a mutation is a traversal, so a write plane has to get past the
read-only guard. The safety model is *which* traversals get past it. Only
text this package built character by character reaches the unguarded
connector; a caller-supplied traversal keeps the guard and the limit
injection. Every literal goes through one escaping chokepoint, which
allow-lists by type rather than falling through to `str()` (G23).

## 5. What this is not

* **Not an ORM or a repository.** It owns connection, resilience and
  lifecycle. You write your own queries.
* **Not a query sandbox.** The read-only guards are regexes with known
  false negatives. Defence in depth in front of a read-only role
  assignment, not a substitute for one (G10).
* **Not infrastructure-as-code.** The deploy plane is not a state store.
  There is no plan, no dependency graph, no reconciliation loop and no
  drift remediation: it makes one resource match one spec and tells you
  when it did not. You order account, then database, then container,
  because nothing here will do it for you. Long-lived production
  infrastructure still belongs in Bicep.
* **Not a transaction manager.** Batches are chunked and submitted in
  order. A chunk that fails leaves earlier chunks applied, and there is no
  rollback. Cosmos transactional batch is a different API with a
  same-partition constraint and is not wrapped.
* **Not a bulk loader.** No parallel fan-out, because the throttle gate
  exists precisely to keep concurrency below what the service starts
  rejecting. Gremlin runs at roughly four writes per second (G13).
* **Not a retry library.** The retry policies here are specific to how these
  five services fail. That specificity is the value.

## 6. Verify it works here

```bash
python3 tests/unit/selftest.py           # no SDKs, no cloud account, no framework
python3 tests/unit/test_search_planes.py
python3 tests/unit/test_cosmos_planes.py
python3 tests/unit/test_gremlin_planes.py
python3 -m pytest tests/unit/test_guardrails.py -q
```

The first four are self-running and exit non-zero on a failed check.
`test_guardrails.py` is a pytest module and asserts nothing when run as a
script, so it is invoked through pytest.

Every Azure SDK is substituted with a fake through
`azdata.core.optional.override`, and the fakes assert on what the connector
sent. That is what makes token refresh, transient retry, permit release
during backoff, continuation paging and quota fallback testable at all —
and it is available to you for testing your own code against these
connectors.

The plane suites work the same way, against fakes that model a hazard
rather than a happy path: an index whose documents become readable on the
third attempt, a `delete_item` that returns and changes nothing, a `drop()`
that is a no-op, an ARM read-back in the exact model style each management
SDK really uses. **None of it touches Azure.** Where this documentation
says a behaviour is proven, it is proven against those fakes; the live
behaviours they imitate were observed against real services, but no test
here re-observes them.

Against real services:

```bash
python3 scripts/probe.py                      # every configured service
python3 scripts/probe.py --service kql
python3 scripts/probe.py --service cosmos-account
```

Unconfigured services are skipped; exit code 1 means a configured service
failed; exit code 2 means nothing was configured.

The probe is safe to run against production because it **never writes**.
The write-plane connectors are built with `WritePolicy.read_only()` and
probed with their `query` method; the provisioners are built with
`ProvisionPolicy.read_only()` and probed with `describe`. That proves the
endpoint, the credential and the *reader* role assignment. It does not
prove the write or contributor role assignments, and there is no way to
prove those without mutating something, so the probe does not try.

## 7. Removal

Nothing is registered globally and no import is patched, so removal is
deletion:

1. Replace `connect(...)` calls with your own client construction.
2. Delete the `azdata/` folder.
3. Drop the rows you added to `requirements.txt`.

Nothing in the package writes to global state except the circuit-breaker
registry and the named gate cache, both of which are plain module-level
dictionaries that disappear with the process. Configuration is read at your
composition root, so the environment variables are the last thing to remove
and can go at any time.
