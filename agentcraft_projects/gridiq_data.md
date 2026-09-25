# GridIQ data sources: sample-data specification

**Goal:** build a sample for every data source GridIQ reads. Each sample has the real schema, identifiers, join keys and signal shapes. Loaded into the live stores alongside the deployed app, the samples let us check every agent tool, query, detector pattern and UI panel end to end. The values do not need to mean anything for real grid modelling.

**The rule:** match the form, not the values. A sample passes when every consumer below gets a non-empty, correctly shaped result, and every detector pattern fires where it should and stays silent where it shouldn't.

Everything here was worked out from code in `agentcraft_projects/gridiq/` on 2026-09-24 (`tools/`, `foundation/config.py`, `control/agents/grid.yaml`, `scripts/seed/`, `evaluations/cases/`). No live store was queried. Unverified points are marked `unknown:` or `assumes:`.

---

## 1. Store inventory

| # | Store | Location (config key → default) | Auth | Consumers |
|---|---|---|---|---|
| S1 | Fabric Eventhouse (KQL) | `EVENTHOUSE_QUERY_URI`, `FABRIC_KQL_DB_NAME`, both empty by default. The code calls the live environment `gridiq-v1`. | Fabric service principal (`FABRIC_TENANT_ID`/`FABRIC_CLIENT_ID`/`FABRIC_CLIENT_SECRET`) or managed identity | `tools/watcher`, `tools/kql`, `tools/situations`, `tools/grid_reference` (region roll-up tags) |
| S2 | Cosmos DB Gremlin (EMS-CIM topology) | `COSMOS_GREMLIN_ENDPOINT` → `wss://cosmos-cim-graph-prov.gremlin.cosmos.azure.com:443/`, db `cim-db`, graph `cim-graph` | Entra (DefaultAzureCredential) | `tools/grid_reference`, `tools/watcher/_graph_tools.py`, `tools/watcher/_graph_extras/*`, `tools/gremlin`, detector inertia gates, `hosting/fastapi/topology` |
| S3a | Azure AI Search, primary service | `AI_SEARCH_ENDPOINT` | Key (`AI_SEARCH_API_KEY`) or Entra | `search_investigation_clues`, `search_smirks` |
| S3b | Azure AI Search, operator service (`aisearch-app-aemo`) | `AI_SEARCH_OPERATOR_ENDPOINT` | same | `search_paws`, `search_nearhit_reports` |
| S3c | Azure AI Search, action feedback | `ACTION_FEEDBACK_SEARCH_ENDPOINT`, index `action-feedback` | same | `tools/search/action_feedback.py` |
| S4 | ~~GridSFM what-if service~~ | **Removed 2026-09-24** — tools, config, prompts and UI renderers deleted from the app | — | — |
| S5 | Local case battery | `evaluations/cases/*.yaml` (43 cases) | — | `GET /api/evaluations/scenarios/triggers`, the evaluator/auditor agents |
| — | Cosmos DB NoSQL, sessions DB | containers `detector_configs`, `evaluations`, `audits`, plus sessions and messages | Entra | Application state, **not a dataset**: the app writes it itself, so no sample is needed |

Removed tables that must **not** be recreated: `WatcherAssetRegistryV3`, `WatcherStationRegionsV2`, `WatcherStationConnectivity`, `StationElectricalAdjacencyV2`. The graph (S2) now answers everything those tables held.

---

## 2. S1 — Eventhouse tables

### 2.1 `WatcherAlarmsAll` (discrete alarm events)

| Column | Type | Meaning / format |
|---|---|---|
| `timestamp_aest` | datetime | Event time in Australian Eastern time. assumes: stored without a timezone offset, as AEST wall-clock time |
| `alarm_label` | string | Alarm class code. The detector matches on it (see §5) |
| `alarm_text` | string | Free-text alarm message |
| `priority` | int | Alarm priority (the seed uses 1–5) |
| `client_composite_id` | string | Composite device path, dot-separated. The detector checks it for `.BUS.` (the `kv_emer_bus` signal) and counts distinct values for AGC |
| `mrid` | string | CIM mRID of the alarmed device, so it **must exist in S2** (`IdentifiedObject.CIMMRID`) |
| `station` | string | SCADA station code, which **must equal `Substation.EMSName` in S2** |

Alarm labels the code depends on (the sample must include each one):
`CB`, `CB-CRIT`, `UNREAS`, `MWCC`, `KV-EMER-D`, `KV-EMER-I` (any label containing `KV-EMER`), `BR-WARN*`, `BR-LDSH*` (`BR-LDSH-I`), `BR-EMER*` (`BR-EMER-D`, `BR-EMER-I`), `INTER-LDSH`, `CNTR-EMER`, `HZ-EMER`, `SC VR EMER`, `UN-VR-CDGN`, `GEN AGC`.
The sample also needs non-matching noise labels (e.g. `TAP_CHANGE`, `UNDERVOLTAGE`) to check that the detector ignores them.

### 2.2 `WatcherScadaAll` (continuous telemetry)

| Column | Type | Meaning / format |
|---|---|---|
| `timestamp_aest` | datetime | Sample time. Cadence matters: oscillation detection needs at least 10 samples per 5 minutes, so one sample every 30 s or faster |
| `TagId` | string | `STATION.CLASS.DEVICE.MEAS`, e.g. `STN_A.GEN.U1.MW`, `STN_A.GEN.U1.HZ`, `STN_BESS.GEN.INV1.MW`. The first part is the station; the detector's fallback key is `split(".")[0]` |
| `measurement` | string | One of `MW`, `MVAR`, `KV`, `MVA`, `HZ`, `FREQ` |
| `Value` | real | Reading; may be negative (motoring) |
| `station` | string | Same as the alarm `station`, and equal to `Substation.EMSName` |

`CLASS` segments the detector matches with `TagId contains`: `.GEN.`, `.UNIT.`, `.LINE.`, `.BUS.`, `.TRANS.`.

**System and region tags** (read by `grid_status.py` for the operator dashboard, and by `grid_reference` for live regional generation). The sample must carry every one of these literally:

```
MARKET.REGION.QLD1.CMW  MARKET.REGION.SA1.CMW  MARKET.REGION.TAS1.CMW
MARKET.SUMM.MAINLAND.INER  MARKET.SUMM.NATIONAL.MW  MARKET.SUMM.NATIONAL.RESV
NSW1.LOAD.RLOADNSW1.MW  NSW1.SUMM.MARKET_ESS.MW  NSW1.SUMM.MARKET_SOLAR.MW
NSW1.SUMM.NSW_GENERATION.MW  NSW1.SUMM.NSW_MARKET.RESV  NSW1.SUMM.WIND.MW
QLD1.LOAD.RLOADQLD1.MW  QLD1.SUMM.MARKET_ESS.MW  QLD1.SUMM.MARKET_SOLAR.MW
QLD1.SUMM.MARKET_WIND.MW  QLD1.SUMM.QLD_MARKET.RESV
SA1.LOAD.RLOADSA1.MW  SA1.SUMM.MARKET_ESS.MW  SA1.SUMM.MARKET_SOLAR.MW
SA1.SUMM.SA_MARKET.RESV  SA1.SUMM.WIND.MW
TAS1.LOAD.RLOAD_DEMAND.MW  TAS1.SUMM.TAS_MARKET.RESV  TAS1.SUMM.WIND.MW
VIC1.LOAD.RLOADVIC1.MW  VIC1.SUMM.MARKET_ESS.MW  VIC1.SUMM.TOTAL_SOLAR.MW
VIC1.SUMM.TOTAL_WIND.MW  VIC1.SUMM.VIC_GENERATION.MW  VIC1.SUMM.VIC_MARKET.RESV
```
Region roll-up tags follow the pattern `<REGION>1.SUMM.<REGION>_MARKET.MW`.
unknown: whether any other tags are read indirectly, for example through the dashboard views in `grid_status_views.py`.

---

## 3. S2 — Cosmos Gremlin EMS-CIM graph

The graph follows IEC CIM as exported from an EMS. Vertex property names carry their CIM class as a prefix.

**Vertex labels used:** `Substation`, `VoltageLevel`, `ConnectivityNode`, `Terminal` (reached through edges), `Switch`, `BusBarSection`, `PowerTransformer`, `ACLineSegment`, `GeneratingUnit`, `SynchronousMachine`, `StaticVarCompensator`, `ShuntCompensator`, `ScadaDeviceObject`.

**Edge labels used:** `Terminal.ConnectivityNode`, `Terminal.ConductingEquipment`, `Equipment.EquipmentContainer`, `VoltageLevel.Substation`, `ACLineSegment.NearVoltageLevel`, `ACLineSegment.FarVoltageLevel`, `MutualCoupling.MutualCouplingGroup`.

**Properties read (every one needs a value in the sample):**

| Class | Properties |
|---|---|
| all | `IdentifiedObject.Name`, `IdentifiedObject.CIMMRID`, `IdentifiedObject.AliasName` |
| Substation | `EMSName` (= SCADA `station`), `Company` (= NEM region `VIC/QLD/SA/NSW/TAS`), `PathName`, `NETMOMCompositeId`, `GENMOMCompositeId` |
| VoltageLevel | `PathName`: **whitespace-separated** `<REGION> <DIVISION> <STATION> <KV> …`. Token 3 is the station and token 4 is the kV (`tools/grid_reference/_shapers.py::_station_token`); neighbour adjacency is derived from this |
| ConnectivityNode | `PathName`, `EMSName` |
| Switch | `PathName`, `BayPathName`, `NormalOpen`, `CurrentOpen`, `EMSName`, `VoltageLevelContainer`, `SubstationContainer` |
| BusBarSection | `PathName` |
| PowerTransformer | `PathName`, `WindingCount`, `NETMOMCompositeId`, `VoltageLevelContainer`, `SubstationContainer` |
| ACLineSegment | `PathName`, `LinePathName`, `BayPathName` |
| GeneratingUnit | `PathName`, `MaxCapacityMW` (the rated MW actually used) |
| SynchronousMachine | `PathName`, `EMSName`, `Inertia` (the detector gate is ≥ 1.0 s), `BaseMW` (often 0; the code must not rely on it), `BaseKVPU`, `DTSMOMCompositeId`, `VoltageLevelContainer`, `SubstationContainer` |
| StaticVarCompensator / ShuntCompensator | `PathName` |
| ScadaDeviceObject | `ScadaAliasName` |

**Traversals that must work:**
- `Substation → GeneratingUnit → SynchronousMachine` through `both()` edges, for inertia and rated MW.
- `Substation ← VoltageLevel.Substation ← VoltageLevel`, then `in(ACLineSegment.Near/FarVoltageLevel)`, to find neighbour stations.
- `Equipment ↔ Terminal ↔ ConnectivityNode`, for bus topology, bus boundary, breaker neighbourhood and switch state.
- `MutualCoupling.MutualCouplingGroup` edges between line pairs, for `graph_common_mode_devices`.

**Partitioning:** the seed writes `pk='synthetic'`. assumes: the live graph's partition key property is `pk`. Every query is scoped to one station or mRID with `.limit()`, because whole-graph scans hit the 60 s Cosmos budget; the sample should be large enough to prove that scoping works.

---

## 4. S3 — AI Search indexes

| Index | Service | Semantic config | Corpus form |
|---|---|---|---|
| `investigation-clues-index` | primary | `investigation-clues-index-semantic` | Clues from past incidents: symptoms mapped to recommended next actions |
| `investigation-clues-clean-index` | primary | `…-clean-index-semantic` | The same corpus minus the 8 benchmark scenarios; selected by `AI_SEARCH_USE_CLEAN_INDEX=1` |
| `smirks-index` | primary | `smirks-index-semantic` | AEMO operational event and direction reports, Jul 2025 – Mar 2026 |
| `paws-ds-index` | operator | `paws-ds-semantic-configuration` | Operator procedures (PAWS) |
| `nearhit-ds-index` | operator | `nearhit-ds-semantic-configuration` | Near-miss incident reports and lessons |
| `action-feedback` | configurable | — | Operator feedback on actions taken |

**Standard incident schema** (from `tools/search/_aisearch/index_provisioning.py`): `chunk_id` (key, keyword analyzer), `parent_id`, `chunk`, `title`, `filename`, `report_date`, `equipment_type`, `location`, `incident_date`, `full_context` (returned, not searchable), `cause`, `conclusions`, `recommendations`, `related_incidents`, a vector field (Collection(Single), named `snippet_vector` for the clues, paws and nearhit indexes and `text_vector` for smirks and action-feedback, according to the search tools; HNSW `hnsw-config`/`hnsw-profile`; `openai-vectorizer` backed by `text-embedding-3-large`).

**Fields the result adapters also read** (`document_adapters/`):
- incidents: `title`, `creationDate`, `conclusions`, `recommendations`, `rectification`
- lessons: `lesson_id`, `what_happened`, `why_it_matters`, `if_you_see_this`, `source_document`, `source_chapter`, `guide`
- action feedback: `feedback_id`, `action_text`, `outcome`, `operator_note`, `equipment_ids`, `station`, `status`, `created_at`, `reasoning`, `tags`

unknown: the exact live field set per index. The shared schema covers the clues index; `smirks`, `paws` and `nearhit` may differ. Before building those samples, read each live index definition (read-only `GET /indexes/<name>`).

---

## 5. Situation detector: the data each pattern needs to fire

Default config `v4.3` (`tools/situations/config.py`): 10-minute window, half-window 5 minutes. Severity tiers: investigate ≥ 5, serious ≥ 8, major ≥ 12, critical ≥ 20. MW boost: 1 point per 50 MW, capped at 10.

### 5.1 Per-station signals (scored inside the window)

| Signal | Source | Trigger | Points |
|---|---|---|---|
| `cb_trip` | alarms | `alarm_label == CB` | 1 |
| `cb_cluster` | alarms | at least 3 `CB` | 3 |
| `kv_emer_bus` | alarms | label contains `KV-EMER` and `client_composite_id` contains `.BUS.` | 2 |
| `unreas` | alarms | `UNREAS` | 1 |
| `br_warn` / `br_ldsh` / `br_emer` | alarms | label contains `BR-WARN` / `BR-LDSH` / `BR-EMER` | 1 / 3 / 2 |
| `inter_ldsh` | alarms | contains `INTER-LDSH` | 3 |
| `cntr_emer` | alarms | `CNTR-EMER` | 2 |
| `gen_trip` | SCADA `.GEN.`/`.UNIT.` MW | falls to near zero (< 1) from a baseline > 5 | 3 |
| `gen_major_loss` | same | falls below 10 from > 100 | 5 |
| `bus_collapse` | `.BUS.` KV | falls below 2 from > 10 | 4 |
| `line_trip` | `.LINE.` MW | falls to near zero from > 10 | 2 |
| `line_kv_collapse` | `.LINE.` KV | falls below 2 from > 10 | 2 |
| `line_overload` | `.LINE.` MVA | rises more than 30% | 1 |
| `transformer_trip` | `.TRANS.` MW | falls to near zero from > 10 | 3 |
| `transformer_mva_trip` | `.TRANS.` MVA | falls to near zero from > 10 | 2 |

### 5.2 System patterns (each needs at least one positive and one near-miss negative scenario)

| Pattern | Data needed to fire |
|---|---|
| `unit_unplanned_offline` | `.GEN.`/`.UNIT.` MW falls ≥ 50 to ≤ 5 and stays there for ≥ 5 min (≥ 3 samples); the machine's graph inertia is ≥ 1.0 s; plus `CB`/`CB-CRIT` within 5 min, `MWCC` within 15 min, `KV-EMER-D`/`-I` within 5 min |
| `synchronised_line_trip` | ≥ 2 `.LINE.` MW tags fall from > 30 to < 5 within 2 min, together ≥ 100 MW; a cross-station bonus when ≥ 2 stations are involved |
| `regional_cascade` | Emergency labels (`BR-EMER-D`, `BR-EMER-I`, `BR-LDSH-I`, `INTER-LDSH`, `HZ-EMER`) at **≥ 8 stations within 5 min** (a bypass applies at 30 stations; ≥ 5% of stations in emergency). Tiers at 8 / 15 / 25 stations |
| `system_reactive_event` | `SC VR EMER` at ≥ 3 stations within 30 min, and/or `UN-VR-CDGN` at ≥ 5 stations within 60 min |
| `coordinated_oscillation` | `.GEN.`/`.UNIT.` MW or MVAR at ≥ 3 inertial stations: 5-min windows with ≥ 10 samples, \|mean\| ≥ 20 and coefficient of variation ≥ 0.5, sustained for ≥ 6 consecutive windows |
| `frequency_excursion` | `HZ`/`FREQ` readings (valid 45–55 Hz). Mainland bands: 49.85–50.15 normal, 49.5–50.5 generation event, 49–51 network event. Tasmania bands differ. Needs ≥ 20 readings (≥ 3 when severe), ≥ 2 breaches, and a rate-of-change-of-frequency threshold of 0.1. A situation-level alert needs **≥ 30 stations** reporting and ≥ 2 sustained 5-min bins. Stations `TTCLOCK`, `EAGLE_ST`, `LYGS`, `TIMESYNC`, `BLTS`, `MAGILL` are excluded; `BLGT`, `GTCS`, `NOCS`, `BLGC` are treated as Tasmanian |
| `agc_removal_instability` | A `GEN AGC` alarm, plus `.GEN.`/`.UNIT.` MVAR standard deviation > 3 in 10-min bins, within 30 min of each other at the same station |
| `generator_degradation` | MVAR standard deviation > 5 together with MW derating ≥ 20% over 30 min |
| `generator_motoring` | MW < -5 (severe below -10), ≥ 3 readings within 10 min |

**What this means for the sample:** the breadth rules (`regional_cascade` ≥ 8 stations, `frequency_excursion` ≥ 30 stations) mean a three-station sample like the current seed cannot exercise the system patterns. The sample needs **≥ 35 stations across all 5 regions**, with HZ tags at every station, including at least one Tasmanian station and one excluded station.

---

## 6. Agent tools and the data each one touches

Agents come from `control/agents/grid.yaml`: `grid_manager`, `investigator`, `dispatcher`, `data_assistant`, `consequence_modeler`, `evaluator`, `auditor`, `grid_summarizer`.

| Tool | Store | Sample must provide |
|---|---|---|
| `resolve_station` | S2 | Station names, aliases and paths that resolve to an `EMSName` |
| `find_asset`, `find_station_assets` | S2 via `grid_reference` | Equipment per station, with CIM class, ratings and region |
| `find_alarms`, `find_alarm_by_mrid` | S1 alarms | Alarms per station and window; mRIDs that also exist in S2 |
| `find_scada`, `find_scada_changes` | S1 SCADA | Tags per equipment filter (`TagId has`), with value steps |
| `find_event_timeline` | S1 alarms and SCADA | Interleaved alarms and SCADA changes in one window |
| `query_kql` | S1 | Any table; the guardrails add `take 50` |
| `graph_station_equipment`, `graph_equipment_connections`, `graph_bus_topology` | S2 | The full Terminal/ConnectivityNode chain for each station |
| `graph_bus_boundary`, `graph_breaker_neighbourhood`, `graph_switch_state_snapshot` | S2 | Switches with `NormalOpen` ≠ `CurrentOpen` in at least one case |
| `graph_corridor_endpoints` | S2 | Lines with near and far VoltageLevels at different stations |
| `graph_common_mode_devices` | S2 | At least one `MutualCoupling` group |
| `query_gremlin` | S2 | Any traversal; capped at `GREMLIN_MAX_RESULTS=50` |
| `detect_situations` | S1 + S2 | Everything in §5 |
| `search_investigation_clues`, `search_smirks`, `search_paws`, `search_nearhit_reports` | S3 | Documents whose text mentions the sample's stations and equipment types |
| `classify`, `push_action`, `submit_audit_report`, `delegate_to_agent` | none (app state) | — |

---

## 7. Cross-store invariants the sample must keep

1. S1 `station` = S2 `Substation.EMSName`, as an exact string match.
2. S1 alarm `mrid` = S2 `IdentifiedObject.CIMMRID` of the alarmed device.
3. The first part of an S1 `TagId` = `station`; the second part is the class (`GEN`, `UNIT`, `LINE`, `BUS`, `TRANS`), matching the device's CIM class in S2.
4. S2 `Substation.Company` gives each station a region in {VIC, QLD, SA, NSW, TAS}, and that region's tags in §2.2 exist.
5. Every generator station has a `GeneratingUnit` (with `MaxCapacityMW`) and a `SynchronousMachine` (with `Inertia`), so the inertia gates pass for some stations and fail for others (e.g. a battery station with `Inertia` < 1).
6. `VoltageLevel.PathName` parts 3 and 4 give the station and kV, and neighbour stations derived from lines agree with it.
7. S4 removed; no GridSFM constraint applies.
8. S5 cases name real stations and time windows (e.g. Davenport, 2025-08-28 07:05–07:50, `data_in_range: true`). For the eval flow to work against sample data, either write sample cases (with the same schema: `window`, `station.scada_code`, `gate1_detection.expected_event_class`, …) whose windows match the sample data, or align the sample data with a subset of the real cases.

---

## 8. Mock dataset (built 2026-09-24)

`agentcraft_projects/gridiq_mockdata/` contains a deterministic generator and a checker that reads required literals from the tools source:

```bash
cd agentcraft_projects/gridiq_mockdata
python3 generate.py            # writes out/ (byte-identical on rerun)
python3 generate.py --check    # regenerates and compares with out/
python3 check.py --tools ../gridiq/tools   # alignment, coverage, scenario, PDF checks; 76/76 pass
```

- **Stations:** two fictional stations, `KESTREL` (VIC; thermal; units U1 and U2, each with a synchronous machine of inertia 4.5) and `MARLOW` (NSW; BESS1 with no synchronous machine, so the inertia gate fails by design; SVC1; CAP1). They are joined by mutually coupled 330 kV lines `KM1` and `KM2`. The tool config names ten more stations (TTCLOCK, EAGLE_ST, LYGS, TIMESYNC, BLTS, MAGILL, BLGT, GTCS, NOCS, BLGC); each is included as a frequency-monitor-only station. The pseudo-stations `NSW1`/`QLD1`/`SA1`/`TAS1`/`VIC1`/`MARKET` carry the region and system tags.
- **Alignment key:** each device's composite id `<STATION>.<CLASS>.<EQUIP>` is used as:
  - the graph's `ScadaDeviceObject.ScadaAliasName`, `SynchronousMachine.DTSMOMCompositeId` or `PowerTransformer.NETMOMCompositeId`;
  - the `TagId` prefix;
  - the alarm `client_composite_id`.

  Line ends are identified by their terminals. Alarm `mrid` is the owning device's CIMMRID, and `station` is `Substation.EMSName`.
- **Outputs:**
  - `out/kql/`: the schema, plus `WatcherScadaAll.csv` (19,455 rows, 81 tags, 15 s cadence, 2026-03-10 14:00–15:00 AEST) and `WatcherAlarmsAll.csv` (25 rows, covering every alarm label the tools use).
  - `out/graph/`: 142 vertices and 186 edges.
  - `out/search/<index>/`: one `report.pdf`, `index.json` and `documents.jsonl` for each of the 6 indexes.
- **Coverage:** everything the tools reference is present: 20 alarm labels, 6 measurements, 5 tag classes, 36 literal tags, 11 vertex labels, 9 edge labels, 52 vertex properties, 10 KQL columns, 6 indexes and 120 document fields.
- **Scenario:**
  - U2 shows MVAR volatility and a derate, plus a `GEN AGC` alarm (14:08–14:30).
  - U1 trips at 14:30, with CB, CB-CRIT, KV-EMER, UNREAS and MWCC alarms and a mainland frequency dip with ROCOF above 0.1 Hz/s.
  - KM1 overloads at 14:38, then KM1 and KM2 trip together at 14:40 (462 MW, both stations), with emergency-band alarms.
  - U2 motors at 14:52.
- **Patterns that fire:** `unit_unplanned_offline`, `synchronised_line_trip`, `generator_degradation`, `agc_removal_instability`, `generator_motoring`, and every per-station signal.
- **Patterns that can't fire with 2 stations:** `regional_cascade` (needs 8 stations), `system_reactive_event` (needs 3 and 5), `coordinated_oscillation` (needs 3 inertial stations), and situation-level `frequency_excursion` (needs 30). Breadth was deliberately not faked.
- **Design choices beyond the tools:** the `SynchronousMachine.GeneratingUnit` and `ConnectivityNode.ConnectivityNodeContainer` edge labels, an `SVC` tag class (`MARLOW.SVC.SVC1`), and measurement = last TagId token for region tags (`CMW`, `RESV`, `INER`). Check these against the live stores before loading.

## 9. Open questions (answer before building)

- unknown: whether the live stores still exist, and in which tenant and subscription.
- unknown: live row counts, time ranges and ingestion cadence for S1.
- unknown: the live field sets of the `smirks`, `paws`, `nearhit` and `action-feedback` indexes.
- unknown: any extra KQL tables read by the dashboard views (`grid_status_views.py`) or by the topology router.
- Decided and observed (2026-09-24): the sample went into a **separate** environment, `rg-test-grid`
  (subscription `67255afe-8670-4401-a1b8-df6ca63a3516`, australiaeast). An ADX Dev cluster stands in for the Eventhouse, with
  Cosmos Gremlin serverless, AI Search Basic, AI Services `text-embedding-3-large`, and Storage. Procedure and receipts:
  `gridiq_mockdata/deploy/README.md`.
  - Every count matched `manifest.json` twice, which proves the reload is idempotent.
  - Twelve real GridIQ tools returned non-empty results using az CLI Entra auth, with no Fabric service principal:
    `resolve_station`, `find_alarms`, `find_scada`, `find_alarm_by_mrid`, three `graph_*` tools, four `search_*`
    tools and `detect_situations`.
  - `detect_situations` fired `unit_unplanned_offline`, `generator_degradation`, `agc_removal_instability`,
    `generator_motoring` and `synchronised_line_trip`.
  - The §8 design choices (the extra edge labels, the `SVC` tag class, the region-tag measurements) load into these
    test stores and the counts match. Whether each tool traverses them was not checked, and they are still unchecked
    against the live stores.
- Observed: Cosmos Gremlin accepts an Entra token (`https://cosmos.azure.com/.default`) as the Gremlin password
  when the caller holds the generic Cosmos data-plane role `Cosmos DB Built-in Data Contributor`
  (`sqlRoleAssignments`). Key auth stays disabled.
- Observed: `action-feedback/index.json` has no semantic configuration, so only keyword + vector queries apply to it.
  The GridIQ search adapter's `k_nearest_neighbors` argument is ignored by `azure-search-documents 11.7.0b2`.
