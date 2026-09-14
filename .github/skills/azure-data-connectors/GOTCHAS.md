# GOTCHAS.md — azure-data-connectors

Failures that cost real time. Each was hit against live Azure services, not
theorised, unless the entry carries an explicit **Provenance** line saying
otherwise.

Numbers are stable. Code comments cite them; a citation with no entry fails
`validate_box.py`.

---

## G1 — A Gremlin client that worked for an hour starts failing

**Symptom.** Gremlin queries succeed after deployment and then, roughly an
hour later, every one fails. The error is a transport or authentication
message with no status code — "connection was already closed", or a bare
401 — and restarting the process fixes it completely.

**Cause.** Cosmos authenticates the Gremlin WebSocket with an access token
supplied as the connection password. That token expires in about an hour.
The driver does not refresh it and does not notice: the connection stays
open and fails on the next call.

**Fix.** Cache the client *with* its token expiry and rebuild before the
margin runs out (300 s by default). Then retry once on a transient-looking
failure, because a query can still race an expiry that happens mid-flight.
Both are implemented in `src/azdata/gremlin/read.py`.

**Rule.** Any long-lived connection authenticated by a bearer token needs
an expiry-aware cache. The SDK's connection pool is not one.

---

## G2 — "This event loop is already running" from a Gremlin query

**Symptom.** A Gremlin traversal that works in a script raises
`RuntimeError: This event loop is already running`, or hangs, or fails with
an unrelated-looking error inside the driver, as soon as it is called from
a web request handler. Under `uvloop` the failure is different again.

**Cause.** `gremlin_python`'s driver creates and drives its own asyncio
loop inside `submit()`. Called from a running loop, that is illegal. Under
`uvloop` the driver's assumptions about the loop implementation do not
hold either.

**Fix.** Run each submit on a worker thread that creates a fresh standard
library loop, uses it, and closes it. `src/azdata/gremlin/read.py` does this in
`_run()` inside `asyncio.to_thread`. Do not "simplify" it into an await.

**Rule.** A synchronous SDK that manages its own loop must be isolated on a
thread. Wrapping it in `run_until_complete` moves the failure, not fixes it.

---

## G3 — One retrying query starves every other query

**Symptom.** A single throttled or cold-starting query makes every other
query against the same service hang for the length of its backoff. Total
throughput collapses far below the configured concurrency.

**Cause.** The retry loop held its concurrency permit across
`asyncio.sleep`. With a small semaphore — 2 is a sane default for shared
capacity — two backing-off queries occupy the whole gate for a minute
while doing nothing.

**Fix.** Release the permit before sleeping and re-acquire after.
`GraphConnector._sleep_without_permit` does this, and `tests/unit/selftest.py`
asserts the permit is genuinely free during the wait.

**Rule.** Never hold a shared resource across a sleep you chose.

---

## G4 — Search fails for a month, then works again

**Symptom.** Azure AI Search returns errors containing
`Free Query Semantic Usage exceeded`. The service is otherwise healthy, the
index is fine, and the failure clears at the start of the next month.

**Cause.** Semantic ranking is metered separately. The free allowance runs
out; the service refuses the semantic query rather than degrading. Treated
as a normal failure, three of these trip the circuit breaker and take
search down entirely — a paid-feature limit becomes an outage.

**Fix.** Match on the marker, retry the same query without
`query_type=SEMANTIC`, and do not record a breaker failure. Keyword and
vector results are still good. `src/azdata/search/read.py` implements it.

**Rule.** Classify errors before counting them. A quota is not an outage,
and a breaker that cannot tell the difference will invent one.

---

## G5 — The quota retry works, and then it does not

**Symptom.** The G4 fallback works in a test and fails in production: the
same quota error escapes, this time from the loop that formats results, not
from the search call.

**Cause.** The Search SDK returns a lazy pager. `client.search(...)` may not
have issued the HTTP request at all; the failure surfaces on first
iteration. A `try` around the call alone misses it.

**Fix.** Guard both sites — the call and the iteration — with the same
fallback. `tests/unit/selftest.py` covers each separately.

**Rule.** With a lazy client, the call site and the consumption site are two
different failure points. Wrap both.

---

## G6 — Every call blocks forever, with no error anywhere

**Symptom.** After a configuration change, every query against one service
hangs. No timeout, no log line, no exception. The process must be
restarted.

**Cause.** `max_concurrent` was set to `0` — a typo, or an unset variable
parsed as zero. `asyncio.Semaphore(0)` is a valid object that never admits
anyone.

**Fix.** Clamp to a minimum of 1 where the value is read
(`AzureDataConfig.from_env`) and again where it is used (`ThrottleGate`).
Two clamps, because a caller can construct the gate directly.

**Rule.** A configuration value that can produce a permanent deadlock is
validated at the boundary, not documented.

---

## G7 — A failed GQL query is reported as a success

**Symptom.** A Fabric GraphModel query returns HTTP 200 and the caller
reports success with zero rows. The query was invalid.

**Cause.** The GQL endpoint reports query outcomes in the response body,
not the HTTP status. `status.code == "00000"` is success; `"02000"` means a
partial result with a continuation token; anything else is a failure that
arrived with a 200.

**Fix.** Branch on the body status. `src/azdata/fabric_graph/read.py` treats any other code
as an error and surfaces `status.cause.description`.

**Corollary.** Ignoring `02000` + `nextPage` silently truncates results,
which is worse than an error — nothing anywhere says the answer is partial.
Follow the continuation token and accumulate.

---

## G8 — Closing one store breaks every other service in the process

**Symptom.** Shutting down or reconfiguring one connector makes unrelated
connectors fail authentication immediately afterwards.

**Cause.** The credential is a process-lifetime singleton shared by every
connector. A `close()` that tears down the credential along with its client
revokes it for everyone.

**Fix.** `close()` releases only the client. The credential is never owned
by a connector. `Connectors.aclose()` follows the same rule.

**Rule.** Close what you constructed. A shared singleton is not yours.

---

## G9 — A transient Entra blip takes down a healthy service

**Symptom.** A brief token-endpoint failure produces a wave of 500s, even
though the cached token was still valid for another twenty minutes.

**Cause.** The refresh path discarded the cached token before attempting
re-acquisition, so a failed refresh left nothing to serve.

**Fix.** On refresh failure, log and return the cached token if one exists;
raise only when there is nothing to fall back to (`src/azdata/core/token.py`).
Refresh early — 45 minutes against a 60-90 minute expiry — so there is
always margin to fail inside.

**Rule.** Refresh is an optimisation. Do not let it become a new way to
fail.

---

## G10 — A write query gets through the read-only guard

**Symptom.** A query the guard should have refused reaches the service. It
was hidden in a comment, in an unusual clause, or in a language the guard
does not know.

**Cause.** `validate_read_only` is a regular expression, not a parser. It
strips string literals for some languages, does not strip comments for
any, and passes unknown languages through untouched.

**Fix.** Treat it as a floor. The real boundary is RBAC: give the process a
reader role and the question stops being interesting. Keep the guard
anyway — it fails closed at the point of use and costs nothing.

**Rule.** A text-level guard in front of a query language is defence in
depth. Anyone calling it a sandbox has not read it.

---

## G11 — The service permanently runs on its fallback store

**Symptom.** A store designed to boot in memory and upgrade to Cosmos never
upgrades. `is_healthy()` returns `False` forever. Cosmos is reachable from
the same container, credentials are correct, and no error is logged
anywhere.

**Cause.** `is_healthy` wraps its probe in `asyncio.timeout(...)` and ends
with `except Exception: return False` so that a caller can fall back
safely. When the `import asyncio` was missing, the resulting `NameError`
was caught by that same handler and reported as an unhealthy store. The
mechanism designed to make failure safe made a bug invisible.

**Fix.** The import in `src/azdata/cosmos/read.py` is load-bearing and commented as
such. `tests/unit/selftest.py` asserts that a *healthy* container probes `True`
— the only assertion that fails when the swallow is hiding something.

**Rule.** Every bare `except: return False` needs a positive test. Testing
only the failure path proves the handler works, not that the happy path is
reachable.

---

## G12 — Gremlin 403s at the WebSocket upgrade, before any query

**Symptom.** A Cosmos Gremlin connection fails with 403 during the
WebSocket upgrade — before a single Gremlin byte is sent. The body is
empty, there is no activity id, and both key auth and Entra auth fail
identically. `publicNetworkAccess` is `Enabled` and there are no IP rules.

**Cause.** The account has a private endpoint with the `Gremlin` group id.
Public network access being enabled is necessary but not sufficient; the
Gremlin data plane is reachable only from inside the VNet. A control
experiment against an otherwise identical account without a private
endpoint connects immediately.

**Fix.** Localise it in one command pair: `GET https://<account>.documents.azure.com/`
returning 401 (SQL plane alive) while `GET https://<account>.gremlin.cosmos.azure.com/`
returns 500 means SQL answers and Gremlin refuses. Confirm with
`az network private-endpoint show --query privateLinkServiceConnections[0].groupIds[0]`.
Then run from inside the VNet, or use an account without the endpoint. A
private endpoint never helps a workstation outside the network.

**Rule.** When auth fails before the protocol starts, suspect the network
path, not the credential.

---

## G13 — A graph load takes hours and cannot be resumed

**Symptom.** Loading a graph through `gremlinpython` runs at roughly four
writes per second. A failure part-way through leaves a partial graph, and
re-running it creates duplicates.

**Cause.** Gremlin has no batch mutation. Every vertex and every edge is a
separate round trip, and `addV` is not idempotent.

**Fix.** Write with `coalesce(unfold(), addV(...))` so re-running is safe,
and expect the throughput. Anything time-sensitive belongs in a bulk-import
path against a different API, not in Gremlin.

**Rule.** Make every bulk write idempotent before you start it, not after
the first failure.

---

## G14 — A resource setting reverts after a successful write

**Symptom.** An ARM write returns HTTP 200, `provisioningState` is
`Succeeded`, compliance is clean — and the field is back to its old value
when you read it. `az policy assignment list` at resource, resource group
and subscription scope shows nothing.

**Cause.** An Azure Policy assignment with the **`Modify`** effect, applied
at a management group scope above your subscription. `Modify` rewrites the
request rather than denying it, so nothing anywhere reports a failure.

**Fix.** Look in the Activity Log for
`Microsoft.Authorization/policies/modify/action`. Resolve with
`az policy exemption create --exemption-category Waiver` scoped to the
resource, naming the `--policy-definition-reference-id`. That requires
rights at the management group the assignment lives on.

**Rule.** A setting that will not stick is being overwritten by something
you cannot see from the resource. Read the Activity Log, not the resource.

---

## G15 — A KQL `has` filter matches nothing, and the syntax is fine

**Symptom.** `where host has "scan"` returns no rows even though hosts
containing that substring plainly exist in the table.

**Cause.** `has` is **token**-based, not substring-based. A hostname with no
delimiters is a single token, so `has` only matches the whole thing.

**Fix.** Use `contains` for substring matching, and accept that it does not
use the term index and is slower. Reach for `has` only when the field is
genuinely tokenised.

**Rule.** Kusto string operators differ in indexing strategy, not just in
spelling. Check which one you are getting.

---

## G16 — A dashboard endpoint 502s intermittently under no real load

**Symptom.** An endpoint that fires several aggregate queries fails
intermittently with a 502 while each of its queries runs fine alone.

**Cause.** The queries were issued concurrently with `asyncio.gather`. A
handful of simultaneous aggregates saturate a shared capacity unit; the
service throttles and the gateway returns 502. The first request after a
deployment is worse, because nothing is warm.

**Fix.** Bound the concurrency — that is what `ThrottleGate` is for — or
sequence the queries. Warm a heavy endpoint with one request after
deployment before trusting a measurement taken from it.

**Rule.** Shared capacity is a global resource. Parallelism that helps your
request hurts everyone's, including your own next one.

---

## G17 — A "partition-scoped" Cosmos query scans every partition

**Symptom.** A query passing `enable_cross_partition_query=False` costs the
RU of a full scan and throttles a container it should barely have touched.
Nothing errors, nothing warns, and the argument is right there in the code
review.

**Cause.** `azure-cosmos` 4.x removed the flag. The aio `query_items`
accepts `parameters`, `partition_key`, `max_item_count`,
`enable_scan_in_query`, `populate_query_metrics`, `populate_index_metrics`,
`session_token`, `initial_headers`, `max_integrated_cache_staleness_in_ms`,
`priority`, `continuation_token_limit` and `**kwargs`. The `**kwargs` is
what makes this silent: the removed 3.x argument is absorbed rather than
rejected, so it reads like an enforced scope and does nothing at all. On
4.x a query is cross-partition **exactly when no `partition_key` is
passed**, and there is no other switch.

**Fix.** Pass `partition_key` when you know it and omit it when you do not.
Never send the removed flag, and never invent a partition key to recover
from one you could not determine — a wrong key is a query that finds
nothing rather than a query that is cheap. `CosmosItems.query` in
`src/azdata/cosmos/write.py` does exactly this;
`tests/unit/test_cosmos_planes.py::test_query_partition_scope` asserts both that
the key is forwarded when supplied and that the 3.x flag is never sent.

**Rule.** An argument absorbed by `**kwargs` is not an argument. When an
SDK removes a keyword, the call site keeps compiling and stops meaning
anything; assert on what went on the wire.

---

## G18 — Every healthy deployment is reported as drifted

**Symptom.** A provisioner that re-reads its resource reports drift on
every single call, for infrastructure that is exactly right. Within a week
the drift check is disabled, and the one failure it existed to catch
(G19) goes with it.

**Cause.** The management SDKs this package uses do **not** agree on model
style, and a read-back normaliser written for one is wrong for another.

| | `azure-mgmt-search` 9.2.0 | `azure-mgmt-cosmosdb` 10.0.0 | `azure-mgmt-kusto` 4.0.0 |
| --- | --- | --- | --- |
| Style | msrest | JSON-backed | JSON-backed |
| Model is a `Mapping` | No | Yes | Yes |
| Dict view | `as_dict()` | `dict(model)` | `dict(model)` |
| Key case | snake_case | camelCase | camelCase |
| Nesting | Flattened, no `properties` | Everything under `properties` | Everything under `properties` |
| `resource` | n/a | Attribute only — **not** a top-level dict key | n/a |

The Kusto column is introspection, not inference:
`isinstance(Cluster(...), collections.abc.Mapping)` is `True`, the MRO runs
through `_MyMutableMapping`, and
`Cluster(location="eastus", enable_streaming_ingest=True).as_dict()` is
`{'location': 'eastus', 'properties': {'enableStreamingIngest': True}}`.
A 3.x pin is msrest and hands over the flattened shape instead, which is
why `lift_kusto_model` passes an already-flat payload through untouched.

So `dict(SqlContainerGetResults(...))` is `{'id', 'name', 'type',
'properties'}` and a comparison against the top level of that finds none of
the fields it asked for, while `SearchService.as_dict()` has no
`properties` block at all and a spec key written in the wire's camelCase is
absent from it.

**Fix.** Normalise per SDK, in the module that owns it, and never share the
helper. `azdata.cosmos.deploy.lift_management_model` lifts `properties` up
one level and snake-cases both levels; `azdata.kusto.deploy.lift_kusto_model`
does the same for its own SDK rather than importing the Cosmos one, because
a helper shared between SDKs that disagree is how the wrong shape gets
applied to the wrong service; `azdata.search.deploy._verifiable`
snake-cases the spec keys and compares only the keys ARM echoes verbatim.
`tests/unit/test_search_planes.py::test_service_readback_shape`,
`tests/unit/test_cosmos_planes.py::test_v10_account_readback` and
`tests/unit/test_kusto_planes.py::test_model_shape_is_the_json_backed_camelcase_style`
each assert that a correct deployment reports **no** drift and a reverted
field still does. All three use fakes reproducing the introspected model
shapes, not live services.

**Rule.** A check that cries wolf gets switched off, and takes the real
signal with it. Prove the healthy case is quiet before trusting the noisy
one.

---

## G19 — The deploy plane reports success for infrastructure that reverted

**Symptom.** `ensure` returns success. `provisioningState` is `Succeeded`,
the HTTP status was 200, and the setting is wrong the moment anything reads
it. The next failure arrives somewhere else entirely, inside a connection
timeout.

**Cause.** ARM genuinely accepted the write. An Azure Policy `Modify`
effect at a management-group scope reverted the field immediately
afterwards, and nothing in the write response says so — that mechanism is
G14. This entry is its consequence for code: **an accepted write response
is not evidence of state.** This tenant is known to hold storage
`allowSharedKeyAccess=false` and `publicNetworkAccess=Disabled` that way.

**Fix.** Never trust the write response. `Provisioner.ensure` in
`src/azdata/core/provision.py` re-reads the resource, compares the fields the spec
asked for, and returns a `ProvisionDrift` **error** rather than a warning:
the infrastructure is not in the requested state and a caller that
continues is building on a false premise. Fields the service legitimately
normalises are excluded from the comparison per resource, or the check
becomes G18.

**Rule.** For anything that can be rewritten behind you, the read-back is
the check and the write response is a receipt.

---

## G20 — A test that writes then reads a Search document is flaky

**Symptom.** Upload a document, read it back, get a 404. Sometimes. The
test passes locally, fails in CI, acquires a `sleep(2)`, and fails again
under load.

**Cause.** Azure AI Search indexes asynchronously. `upload_documents`
returns HTTP 200 with `succeeded=True` per document the moment the change
is durably queued; the document becomes retrievable some time later. The
accepted write is real and the immediate read is honest — they are just
describing different points in time.

**Fix.** Poll, bounded, instead of sleeping. `WritePolicy.verify_writes`
re-reads every accepted key up to `verify_attempts` times with
`verify_delay_secs` between attempts and fails the operation with
`VerificationFailed` if a key never appears.
`tests/unit/test_search_planes.py::test_verification` proves both halves with a
fake index that models the lag: a document readable on the third attempt
succeeds, one that never indexes fails after exactly the budgeted attempts.

**Rule.** "Accepted" and "visible" are two events. Code that assumes they
are one is not wrong on your laptop, which is the problem.

---

## G21 — A Cosmos delete reports success and the item is still there

**Symptom.** A retention job reports every item deleted. The container size
does not change. Re-reading the ids with the job's own code confirms they
are gone.

**Cause.** `delete_item(id, partition_key=...)` raises 404 for **two**
different situations: the item does not exist, and the item exists in a
different partition. A caller that treats "already gone" as success
swallows the second one. Worse, the obvious verification — re-reading with
the same wrong partition key — also 404s, and "confirms" the delete.

**Fix.** Two rules, both in `src/azdata/cosmos/write.py`. A 404 from a delete is
a **failed** per-item result carried in `failed`, never an `ok` one. And
reads require a partition key: there is no default and no fallback, because
an unqualified read is a bug in the caller rather than a lookup that
happens to be broad. `tests/unit/test_cosmos_planes.py::test_wrong_partition_key`
deletes against the wrong partition and asserts `count == 0`, the key in
`failed`, and the item still readable under the right key.

**Rule.** When one status code means two things, the caller must supply the
third fact that tells them apart. Never guess it.

---

## G22 — A Gremlin `drop()` deletes nothing and says nothing

**Symptom.** A cleanup traversal runs, returns without error, and the
vertices are still there.

**Cause.** `drop()` on a traversal that matches nothing succeeds. No error,
no count, no signal of any kind. A delete against a key that was never
there and a delete that failed to match are indistinguishable from the
response.

**Fix.** Take a count **before** the drop and decide the per-item result
from that, then verify afterwards.
`GremlinElements._do_delete` in `src/azdata/gremlin/write.py` counts, drops,
and reports `no vertex matched` as a failure; `verify=True` re-reads
through the base class's polling.
`tests/unit/test_gremlin_planes.py::test_silent_delete` asserts that a fake
whose `drop` is a no-op produces an **error**, and that a key which never
existed is not counted as deleted.

**Rule.** A mutation with no result is a mutation you have not observed.
Bracket it with reads.

---

## G23 — A property value containing an apostrophe executes

**Symptom.** Loading a vertex for `o'brien` fails with a Gremlin syntax
error. The same shape with a hostile value does not fail — it runs.

**Cause.** Gremlin has no write API and no parameter binding in this path:
a mutation *is* a traversal string. An interpolated value containing `'`
closes the literal, and everything after it is executable Gremlin.
`o'brien` is a name; `x' ; g.V().drop() ; '` is a graph wipe with exactly
the same shape.

**Fix.** One chokepoint, allow-listed by type.
`azdata.gremlin.write._literal` escapes backslash first, then quote,
newline, carriage return and tab; refuses control characters that have no
escape form; refuses NaN and infinity; and raises on any type outside
`str, bool, int, float, None` rather than falling through to `str()`, since
a dict's `repr` interpolates into syntax that parses and means something
else. No f-string in that module ever sees a raw caller value.
`tests/unit/test_gremlin_planes.py::test_injection` asserts on the exact escaped
traversal string and that no quote or `;` escapes a literal.

**Corollary.** Caller-supplied traversals never bypass the read-only
guard — `GremlinElements.query` runs them on the read-only connector.
Only traversals this package generated character by character reach the
mutation connector.

---

## G24 — A missing-dependency test passes for the wrong reason

**Symptom.** A test asserting "no SDK installed produces a
`MissingDependency` envelope" passes on a laptop and fails in CI, or passes
in CI for months and silently stops testing anything once somebody adds the
SDK to a requirements file.

**Cause.** The test relied on the SDK genuinely being absent. That is a
property of the environment, not of the code, and this repository's
environment already has several of these SDKs installed for other reasons.

**Fix.** Simulate absence rather than depending on it. Setting
`sys.modules["azure.mgmt.cosmosdb"] = None` makes `import_module` raise
`ImportError`, which is exactly what the loader in `src/azdata/core/optional.py`
sees for a package that is not installed. Restore the previous value in a
`finally`, distinguishing "was not in `sys.modules`" from "was `None`", or
the next test in the same process inherits the block.
`tests/unit/test_search_planes.py::test_missing_dependency`,
`tests/unit/test_cosmos_planes.py::test_missing_sdk` and
`tests/unit/test_gremlin_planes.py::test_missing_sdk` all use this seam.

**Rule.** A test whose outcome depends on what happens to be installed is
not a test of your code. Make the condition, do not wait for it.

---

## G25 — A cached writer carries someone else's grant

**Symptom.** Two connectors are asked for on the same index, container or
label with different policies. The second call returns the first object,
so a caller that asked to be read-only silently holds a delete grant, or a
delete-granted caller is refused with `has no delete grant` naming the
exact constructor it did use.

**Cause.** `Connectors.documents`, `.items` and `.elements` cached one
connector per **name** — `documents::<index>`, `items::<db>::<container>`,
`elements::<label>` — and the key did not include the policy. The grant
argument was silently discarded on every call after the first.

The dangerous direction is the widening one. A refusal is loud; a
read-only caller quietly holding a delete grant is not.

**Fix.** Applied in `src/azdata/core/connect.py`: `_policy_key(policy)` contributes
`allow_write`, `allow_delete`, `verify_writes` and `max_batch` to every
write-plane cache key, and the partition key field is in the key too. Two
different grants are now two different objects; the same grant is still
cached.

Proven directly: with a fake SDK, a wide and a narrow request for the same
index return distinct objects, the narrow one reports
`policy.allow_delete is False`, and a repeat of the wide request is
returned from cache.

The deploy plane never had this defect — `provision_*` builds a fresh
provisioner on every call and does not cache.

**Rule.** A cache key must include everything that changes the object's
behaviour. A policy is not metadata.

---

## G26 — Discovery works against a Cosmos account whose data plane is closed

**Symptom.** The account has `publicNetworkAccess=Disabled`, every
data-plane call times out, and the databases and containers still list
perfectly. It reads like discovery is quietly using cached or fabricated
data.

**Cause.** It is not the same plane. `CosmosDiscoverer` and
`GremlinDiscoverer` list through `azure-mgmt-cosmosdb` — ARM — not through
`azure-cosmos` or `gremlinpython`. ARM is reachable from anywhere the
control plane is, regardless of the account's data-plane network rules.

This is deliberate, for three reasons: DDL and metadata are control-plane
concerns for Cosmos anyway; discovery then needs only ARM `Reader` rather
than a data-plane role assignment; and Gremlin never opens a WebSocket, so
G12 cannot happen during a browse.

**Consequence to expect.** Everything visible in discovery may still be
unreachable for a *query*. A container listed here is not proof that
`CosmosContainer.execute` will connect, and `unreachable` from a future
data-plane level is the honest answer rather than a contradiction.

**Rule.** Name the plane a listing came from. "It exists" and "I can read
its contents" are different claims and only one of them was made.

**Provenance.** Design-time, from the plane split in the code and from the
observed `publicNetworkAccess=Disabled` state of the estate. The
simultaneous "ARM lists, data plane times out" pairing has not yet been
observed live from a deployed identity.

---

## G27 — Discovery lists indexes and returns nothing for their fields

**Symptom.** `search/service` returns every index name. `search/index`
returns `forbidden` on the same credential, in the same process, against
the same endpoint.

**Cause.** Azure AI Search splits these across role families. Reading index
*definitions* — which is what a field schema is — is service-management
grade: `Search Service Contributor`. `Search Index Data Reader` can read
documents and cannot read the schema, and `Search Index Data Contributor`
does not help either.

**Fix.** Grant `Search Service Contributor` scoped to the one search
service, and accept what that means: the role is write-capable, so the
scope is the mitigation, not the role name. The alternative is to drop the
field level entirely and derive names from a document projection with the
data-reader role.

**Rule.** A read-only feature can still require a write-capable role. Scope
it to the single resource and say so out loud rather than discovering it
during an incident.

**Provenance.** From the Azure AI Search role documentation, not yet
reproduced here against a `Search Index Data Reader` credential.


