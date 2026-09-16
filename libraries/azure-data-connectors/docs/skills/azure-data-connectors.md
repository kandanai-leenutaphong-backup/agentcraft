# Azure Data Connectors: Library-First Guide

Use installed `azdata` v4, currently `4.0.0a4`, with only the needed provider extras.
Import from `azdata`; never install a skill directory or mix v3 and v4 in one
environment. The [v4 contract](../../CONTRACT.md) owns behavior. This guide
supersedes statements that the old general data/Search skills remain executable.
Shared discovery, application integration and root documentation are parent-owned.

## Target Contract

`connect(service, config, *, credential, policy, transport=None,
gremlin_readonly_key_provider=None)` constructs a `DataConnector` without I/O.
Use `ConnectorConfig` and `Policy` at the trusted host boundary, then await one
request object per operation: `create`, `read`, `update`, `upsert`, `delete`,
`query`, `ingest`, `schema`, `provision`, `status`. `describe()` lists support and
caveats without proving reachability. No configuration-supplied code is imported.

Profiles: Search, Cosmos NoSQL, Blob, Table, ADX, Eventhouse, Fabric GraphModel,
Cosmos Gremlin, SQL Database and PostgreSQL. SDKs are dependencies, not vendored
source. Missing extras fail explicitly before credentials or I/O.

```python
from azdata import Policy, QueryRequest, connect

async def bounded_query(service, config, credential, dialect, expression):
    async with connect(
        service, config, credential=credential, policy=Policy("host-authorized-principal")
    ) as connector:
        return await connector.query(QueryRequest(dialect=dialect, expression=expression))
```

The caller supplies an authorized immutable endpoint, exact target, host allowlist
and credential. `Policy.principal` is an audit identity, not caller authentication.
Default grants are read/query. Data, schema and infrastructure permissions remain
separate; no package install grants them. Requests can narrow bounds, never widen
authority or retarget a connector. Do not log `to_dict()` results automatically:
they contain returned content.

## Errors, Bounds And Lifecycle

Malformed construction raises `ConfigurationError`. Operations return ordered
`OperationResult` / `ItemResult` values with explicit `success`, `partial`,
`pending`, `unknown`, `not_found`, `conflict`, `invalid`, `denied`, `unsupported`
or `failed` states. Expected service/credential failures use safe bounded codes;
programming defects and cancellation propagate. A timeout after possible submission
is not proof of no write. Never replay an ambiguous mutation blindly.

Default limits: 30 seconds, 100 items, 1 MiB input and output content, one native
attempt; concurrency is 1-64 per connector, default 4. Queries are at most 12,000
characters. Requests can only reduce configured limits. Metadata consumes the same
output budget as records. Native driver buffers are not an HTTP wire-memory cap.

Evidence is named: acknowledgment, addressed presence, requested content, addressed
absence or schema. Acceptance alone proves no persistence. Verification is bounded
by the deadline, at most 20 observations and 0-5 second intervals. A missing record
in one partition proves nothing about another. Unsupported guarantees refuse
before transport; no transaction, remote rollback or durable journal is invented.

Use async context management or idempotent `aclose()`. The connector closes owned
SDK/default transport resources, never borrowed credentials/transports. Calls
after close fail without I/O. Cancellation drains native cleanup where required
but cannot undo accepted remote work. Continuations and job references are scoped
to the connector, target, policy and principal, not durable across restarts.

## Operational Knowledge Retained

[Operational migration notes](../../OPERATIONS.md) retain all G1-G27 findings.
Their old source links and v3-retention claims are historical; exact retired bytes
are identified in the [retirement manifest](azure-data-connectors-retirement.json).
Current corrections matter:

- Gremlin does not promise direct Entra traversal authentication. Use a separately
  authorized resource token or explicit host-provided read-only-key profile. No
  automatic key lookup, token issuance or profile fallback exists. Credentials
  stay in host memory, never repository files, examples, logs or receipts.
- Read-only Gremlin mutations refuse even with broad grants, before key lookup.
  Parsed traversals, bounds, retry budget and driver cleanup have one target owner.
- Concurrency/retry limits are per connector, not an endpoint-wide adaptive breaker.
  Endpoint coordination belongs to the host. Zero concurrency refuses.
- Search semantic quota failure does not silently change query semantics. Any
  keyword degradation is a separate explicit host decision. Inspect pagers while
  consuming them, not only while constructing them.
- Graph HTTP 200 is not query success; body status and table data matter. Kusto
  partial failures are not complete success. `has` and `contains` are not synonyms.
- SDK metadata permission, data permission and schema permission differ. Confirm
  exact operations without broadening roles. ARM success may be rewritten by policy;
  authorized infrastructure owners must read back the exact requested fields.
- Schema/model normalization, full snapshot/diff verification, estate discovery,
  legacy live-environment automation and automatic provisioning are retired v3
  workflows, not hidden v4 compatibility promises. Uniform `provision` is unsupported;
  explicitly authorized ADX operators use the separate `azdata.event_store` contract.
  Native Azure administrative procedures remain guidance, not runtime grants.

## Retirement And Offline Acceptance

Retired: skill-local `azdata` 3.4.0, its read/write/deploy/discovery/content/estate
engines, MCP adapter, runners, tests and package metadata. No obsolete source is
stored under documentation. Historical design/incident bytes have an external
hash-verified recovery copy; target-facing interpretations stay in canonical docs.
The skill keeps its native name and troubleshooting triggers. The Microsoft MIT
notice is retained in the skill and copied to the library if absent.

```bash
PYTHONPATH=libraries/azure-data-connectors/src python -B -m unittest discover \
  -s libraries/azure-data-connectors/tests -t libraries/azure-data-connectors -q
```

Run with installed offline dependencies. Existing boundary, transport, provider and
synthetic consumer tests cover positive operations, refusals, partial/unknown effects,
grant/target integrity, verification and cleanup. No cloud, service, model, grant,
publication or live-identity check is authorized by this guide or this retirement.