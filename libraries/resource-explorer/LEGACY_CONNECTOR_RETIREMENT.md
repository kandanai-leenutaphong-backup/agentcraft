# Legacy Connector Retirement

This record covers the authorized Investigation component cull, not a cloud lifecycle change.
Baseline: `00c76c6bb55190877c3d4d4b5b3a14e55bce2cb4`.

## Decisions

| Source | Decision / Replacement | Reachability And Preserved Evidence |
| --- | --- | --- |
| `app/components/data_connector_library/core` and `graph/content.py` | Extracted into `resource_explorer.content` | Real catalogue and host probes import the public content contract; original bounds, status, fidelity and graph-preview tests retained |
| Legacy `kusto/{client,config,connector,crud,errors,identifiers,ingest,models,provision,retry,schema}.py` | Retired; public `azdata.event_store` | No remaining app/deploy caller; canonical operator retry and deny-by-default tests run before removal |
| Legacy `kusto/{content,metadata,read}.py`, `search/content.py` | Retired | Catalogue probes already call public bounded `azdata`; only obsolete component tests instantiate these raw readers |
| Legacy `graph/{connector,control}.py` | Retired | No supported application caller; parent `backend/data/graph.py` owns the existing read-only transport; no provisioning/CRUD surface is offered by this template |
| Broad connector export/signature and Function App staging tests | Retired historical contracts | Pipeline modules/staging scripts are absent in this template; old signatures include ungranted writes intentionally superseded by `EventStorePolicy` |
| `app/components/azure_arm` | Retained pending parent graph extraction | Protected graph service still imports it. Do not delete until parent migrates that caller |

No `.local`, environment file, data, installed dependency, credential or receipt is in the cull.
Frozen paths, original SHA-256 values, retained test classes and recovery copies live under
`/tmp/agentcraft-migration.KbnBod/connector-cull`. Baseline Git restores tracked source;
private recovery also preserves this worktree's pre-cull bytes.

## Preserved Findings

- Error sanitization must not rewrite evidence cells: content retains URLs and values under
  its explicit cell limit. Truncated cells carry a visible count; UTF-8 byte and column bounds
  produce notes. One over-budget row may still be sampled under the inherited preview contract.
- Legacy Kusto `take n` cannot independently prove truncation. Current catalogue combines
  bounded public queries with independent count metadata; no legacy reader is needed.
- Graph preview target identity includes account, database and graph. Caller-supplied source
  returns at most `n + 1` elements to detect truncation; no key reaches content normalization.
- Historical Gremlin write encoder kept mapping values whole but capped serialized free text.
  Passing pre-serialized bucket JSON truncated busy-edge payloads. Future authorized writers
  must preserve structured values and verify round trips; this migration runs no graph write.
- Historical Gremlin scripts bound all caller values and rejected unsafe property names;
  missing/forbidden ARM reads must never trigger creation. Removing unsupported provisioning
  does not remove these obligations from any future implementation.
- ADX mutation safety now belongs to `azdata.event_store.EventStorePolicy`: empty grants by
  default, distinct ingestion/schema/deletion/provisioning authority, named destructive
  confirmation, and refusal before SDK calls. The async v4 query path remains separate.

The [original connector provenance](docs/legacy-connector-provenance.md) preserves source
revisions, original hashes and prior behavior. It is historical evidence, not a current API map.
