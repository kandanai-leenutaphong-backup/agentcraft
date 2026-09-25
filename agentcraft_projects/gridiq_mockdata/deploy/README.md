# GridIQ mock data: `rg-test-grid` deployment

Deploys `../out/` into five new stores in `rg-test-grid` (australiaeast), loads it, reads it back, and runs the
real GridIQ tools against it. Entra tokens only (az CLI identity); no key, connection string or SAS is
read or stored. `deploy.sh` is the only entry point; `env/test-grid.env` holds targets only.

```
deploy.sh            entry point (preflight, plan, provision, load*, verify, smoke, outputs, teardown)
env/test-grid.env    subscription, tenant, rg, region, prefix, names, SKUs
infra/main.bicep     all resources + Azure RBAC + Cosmos data-plane grant
stores.py            load-kql / load-graph / load-search / verify (called by deploy.sh)
smoke.py             imports ../../gridiq read-only and calls its tools
records/             one JSON receipt per step run, never overwritten
```

Prerequisites: `az` (2.83, bicep), system `python3` with azure-identity, azure-kusto-data, gremlinpython,
openai, azure-storage-blob (all present on this machine; install only with `uv pip install --python "$(command -v python3)" ...`).
`az login --tenant c79ab2bb-79cb-47f1-b4da-b6852fe45ff7` as the account in the env file, with that
subscription already active. The script refuses rather than switching subscription.

## Sequence

| # | Command | Expected output | Took (this run) |
|---|---|---|---|
| 1 | `./deploy.sh preflight` | account/subscription/tenant, operator object id, `Owner User Access Administrator`, providers registered, `data: 23 files match manifest.json sha256`, `== preflight ok` | not timed |
| 2 | `./deploy.sh plan` | group absent: `plan: rg-test-grid absent; bicep compiles`. Group present: what-if, `Resource changes: N to modify, M no change` (the modifies are what-if noise on read-only properties) | not timed |
| 3 | `./deploy.sh provision` | `provisioningState=Running` every 30 s, then `Succeeded`, `adx: <upn> is Admin on <cluster>/gridiq`, `record: records/<ts>_provision.json` | 13.5 min first run (ended `Failed`, see below), 1.6 min rerun |
| 4 | `./deploy.sh load` | `load-kql: WatcherAlarmsAll rows=25`, `WatcherScadaAll rows=19455`; `load-graph: ... after={'vertices': 142, 'edges': 186}`; six `load-search: <index> uploaded n/n`; six `load-reports: reports/<index>/report.pdf`; `== load ok` | 5 min |
| 5 | `VERIFY_LABEL=<tag> ./deploy.sh verify` | `verify: kql/graph/search/blobs ok=True`, `verify: PASS`; exit 1 on any mismatch | 43 s |
| 6 | `./deploy.sh smoke` | 12 `smoke: <tool> non-empty ...` lines, `{'non-empty': 12, 'empty': 0, 'error': 0}`; exit 1 on any empty/error | 53 s |

Each `load-*` step runs alone too (`./deploy.sh load-kql`). Every step is safe to rerun: provision is
incremental, `load-kql` clears then re-ingests, graph writes are `coalesce(unfold(), addV/addE)` keyed on
source ids with `pk='mock'`, search is create-or-update + `mergeOrUpload`, blobs overwrite.

## Resources (all in `/subscriptions/67255afe-8670-4401-a1b8-df6ca63a3516/resourceGroups/rg-test-grid`)

Tags on the group: `project=gridiq-mockdata owner=admin@M365x21900035.onmicrosoft.com purpose=test`. Suffix `ans4uaeagcji4` = `uniqueString(rg id)`.

| Resource | Name | SKU / settings | Endpoint |
|---|---|---|---|
| ADX cluster (Eventhouse stand-in) | `tgridadxans4uaeagcji4`, db `gridiq` | `Dev(No SLA)_Standard_E2a_v4`, capacity 1, auto-stop on | `https://tgridadxans4uaeagcji4.australiaeast.kusto.windows.net` |
| Cosmos DB for Gremlin | `tgrid-gremlin-ans4uaeagcji4`, `cim-db`/`cim-graph`, pk `/pk` | serverless, `disableLocalAuth=true` | `wss://tgrid-gremlin-ans4uaeagcji4.gremlin.cosmos.azure.com:443/` |
| Azure AI Search | `tgrid-search-ans4uaeagcji4` | basic, 1 replica/partition, system MI, semantic `free`, `aadOrApiKey` | `https://tgrid-search-ans4uaeagcji4.search.windows.net` |
| AI Services | `tgrid-ais-ans4uaeagcji4`, deployment `text-embedding-3-large` v1 | S0, `disableLocalAuth=true`; deployment `Standard` capacity 1 (1 K TPM, 1 req/10 s) | `https://tgrid-ais-ans4uaeagcji4.openai.azure.com/` |
| Storage | `tgridstans4uaeagcji4`, container `reports` | StorageV2 LRS, `allowSharedKeyAccess=false`, no public blob | `https://tgridstans4uaeagcji4.blob.core.windows.net/` |

`./deploy.sh outputs` prints every id and endpoint.

## Grants (read back 2026-09-24; nothing else, nothing above resource scope)

| Principal | Role | Scope | Declared in |
|---|---|---|---|
| operator `b06960e4-…` | ADX database Admin | `tgridadx…/gridiq` | auto-assigned by ADX to the creator; `provision` reads it back, adds it only if absent |
| operator | Cosmos DB Built-in Data Contributor (`sqlRoleDefinitions/…0002`) | Cosmos account | Bicep `sqlRoleAssignments` |
| operator | Search Service Contributor, Search Index Data Contributor | Search service | Bicep |
| operator | Cognitive Services OpenAI User | AI Services account | Bicep |
| operator | Storage Blob Data Contributor | storage account | Bicep |
| Search MI `96c3633c-…` | Cognitive Services OpenAI User | AI Services account | Bicep |

Gremlin Entra auth: the token for `https://cosmos.azure.com/.default` is the Gremlin password, the same
recipe `gridiq/agentkit/tools/adapters/gremlin_adapter.py` uses. The generic Cosmos data-plane role
(`sqlRoleAssignments`) authorizes it. Observed: accepted with the role; a bogus password returns
`401 Invalid credentials`. Key auth is disabled on the account.

## Cost

ADX and Search bill for every hour they exist, loaded or idle. Retail list prices (Retail Prices API, USD,
australiaeast, read 2026-09-24): Search Basic unit `0.133/h`; E2a v4 Linux compute `0.151/h`. unknown:
whether the ADX `Standard Engine Cluster Markup` (`0.11/h`) applies to the Dev SKU, and the actual invoiced
rate. ADX auto-stop halts compute after a long idle period. Cosmos serverless, AI Services Standard,
and storage bill per use only (a few thousand embedding tokens per load). Tear down when finished.

## Failure playbook

| Step | Symptom | Action |
|---|---|---|
| preflight | `active subscription … != …` | `az account set --subscription 67255afe-…` yourself, then rerun |
| preflight | `… is secret-shaped` / `looks like a credential` | remove it from the env file or shell; secrets never go there |
| preflight | provider not registered | `az provider register -n <ns>` (subscription-level; your decision) |
| provision | `rg-test-grid exists without tag project=gridiq-mockdata` | the group belongs to someone else; stop |
| provision | `deployment Failed` + failed-operation JSON | fix the named resource; rerun (incremental). Seen: duplicate ADX principal assignment, now handled outside Bicep |
| provision | still `Running` after 60 min | rerun `provision`; it resubmits and keeps polling |
| provision | a written field later reads different | Azure Policy `Modify`; check Activity Log `policies/modify/action`. None seen this run |
| load-* | `retry … 401/403` for up to 15 min | role propagation; waits are bounded. If it persists, re-read the grants table |
| load-search | `RateLimitError` retries | capacity 1 = 1 K TPM; the loader retries. Raise `EMBED_CAPACITY` and rerun `provision` if it runs out |
| verify | `ok=False` | receipt shows `expected` vs `observed`; rerun the matching `load-*`, then `verify` |
| smoke | `tools are not bound to the test stores` | a GridIQ env var was overridden; smoke refuses before calling anything |

## Teardown

```bash
./deploy.sh teardown --confirm /subscriptions/67255afe-8670-4401-a1b8-df6ca63a3516/resourceGroups/rg-test-grid
```

Deletes exactly that group after checking its `project` tag, waits, confirms it is gone, writes a receipt.
The AI Services account is then soft-deleted. The same name cannot be reused until
`az cognitiveservices account purge -g rg-test-grid -n tgrid-ais-ans4uaeagcji4 -l australiaeast` runs.
Not run.

## Observed results, 2026-09-24 (UTC)

- 08:03 group created; 08:16 first deployment `Failed` (duplicate ADX principal assignment); fix applied; 08:29:14 deployment `gridiq-mockdata` `Succeeded` (correlation `03bfabec-cdf7-4216-a815-412679d9afab`).
- 08:09 / 08:18 graph and search legs loaded early against hand-built outputs while ADX was still creating (receipts `…080902Z_load-graph`, `…081811Z_load-search`).
- 08:31–08:36 `load`; 08:37 `verify-first-load` PASS; 08:38 `smoke` 12/12 non-empty; 08:38–08:43 second `load`; 08:43 `verify-second-load` PASS with identical counts.

| Check | Expected (manifest.json) | First load | Second load |
|---|---|---|---|
| `WatcherScadaAll` rows / distinct `TagId` | 19,455 / 81 | 19,455 / 81 | 19,455 / 81 |
| `WatcherAlarmsAll` rows / distinct `alarm_label` | 25 / 18 (from CSV) | 25 / 18 | 25 / 18 |
| Gremlin vertices / edges, `pk='mock'` (and whole graph) | 142 / 186 | 142 / 186 | 142 / 186 |
| Search docs: action-feedback, clues, clues-clean, smirks, paws, nearhit | 4, 4, 4, 3, 3, 3 | same | same |
| Hybrid query naming KESTREL/MARLOW, per index | ≥ 1 hit | 3 of 3 each; reranker scores on the 5 semantic indexes | same |
| Blobs `reports/<index>/report.pdf` (size + MD5) | 6 | 6 | 6 |

Smoke (`records/20260924T083804Z_smoke.json`), all tools bound to the test endpoints with no Fabric SP:

| Tool | Result | Excerpt |
|---|---|---|
| `resolve_station("Kestrel")` | non-empty | `scada_code: KESTREL` |
| `find_alarms(KESTREL, 14:00–15:00)` | non-empty | alarm rows, 2.9 KB |
| `find_scada(KESTREL, 14:00–15:00)` | non-empty | tag rows, 6.2 KB |
| `find_alarm_by_mrid` | non-empty | full alarm record |
| `graph_station_equipment(KESTREL)` | non-empty | `SynchronousMachine U2 …` |
| `graph_bus_topology(KESTREL)` | non-empty | `BUS2 Kestrel 330 kV Bus 2`, `BUS1` |
| `graph_corridor_endpoints(KM1)` | non-empty | `KESTREL MARLOW 330 KM1` |
| `search_investigation_clues` | non-empty | `KESTREL U1 Unit Trip` |
| `search_smirks` | non-empty | `Trip of KM1 and KM2 330 kV Lines` |
| `search_paws` | non-empty | `Frequency below 49.85 Hz after generation loss` |
| `search_nearhit_reports` | non-empty | `Coupler CB5 open while BUS2 fed by one line` |
| `detect_situations(2026-03-10 14:00–15:00)` | non-empty | 7 situations; patterns `unit_unplanned_offline`, `generator_degradation`, `agc_removal_instability`, `generator_motoring`, `synchronised_line_trip` |

Findings:
- `action-feedback/index.json` defines no semantic configuration, so its verify query is keyword + vector only. The app only writes to that index.
- The GridIQ search adapter logs `k_nearest_neighbors is not a known attribute of VectorizableTextQuery and will be ignored` with the installed `azure-search-documents 11.7.0b2`. The vector `k` it sets is dropped; results still return. App code, not changed.
- The `MCAPSGovDeployPolicies` DeployIfNotExists policy added the diagnostic setting `setByPolicy-MCAPSGovernance` on the AI Services account, sending to workspace `McapsGovernance/mcaps4401a1b8df6ca63a3516-la`. It is a child of the account and goes with the group. No `policies/modify` or `deny` events.
- Embeddings are built from each document's `chunk` field, as in GridIQ's own `direct_push_documents`.
