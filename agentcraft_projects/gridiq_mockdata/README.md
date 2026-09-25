# GridIQ mock data

Small deterministic mock dataset for every GridIQ data source: Eventhouse (KQL), Cosmos Gremlin EMS-CIM graph, and
the six Azure AI Search indexes. Fictional stations KESTREL (VIC, thermal) and MARLOW (NSW, BESS + SVC) are joined
by the mutually coupled 330 kV double circuit KM1/KM2; ten HZ-monitor stations come from the detector config.
Schemas follow `../gridiq_data.md`; identifiers follow the tools' own queries.

## Run

```bash
python3 generate.py                         # write out/ (seed 20260310, byte-identical on rerun)
python3 generate.py --check                 # regenerate to a temp dir, diff against out/
python3 check.py --tools ../gridiq/tools    # alignment, coverage, scenario, PDF checks; non-zero on failure
```

System `python3` only (pyyaml, pypdf reader). No network, no cloud calls. `check.py` imports
`tools.situations.config.DEFAULT_DETECTOR_CONFIG` read-only and regex-scans `tools/` (excluding `gridsfm`)
for alarm labels, measurements, TagId classes, tag literals, graph labels/properties, KQL columns and search
field names, so tool drift fails the check.

## Deploy

`deploy/` deploys `out/` into a separate Azure test environment (`rg-test-grid`: ADX, Cosmos Gremlin, AI Search,
AI Services embeddings, Storage), loads, verifies and smoke-tests it with the real GridIQ tools. Entra auth only.
Sequence, inventory, grants, cost and teardown: [deploy/README.md](deploy/README.md).

## Layout

```
generate.py, check.py
out/manifest.json                      files + sha256, counts, timeline, pattern claims, design deviations
out/kql/schema.kql                     .create-merge for WatcherAlarmsAll, WatcherScadaAll
out/kql/WatcherAlarmsAll.csv           25 alarms
out/kql/WatcherScadaAll.csv            19,455 rows, 81 tags, 15 s cadence, 2026-03-10 14:00-15:00 AEST
out/graph/vertices.jsonl               {id,label,properties{...,pk:'mock'}}
out/graph/edges.jsonl                  {id,label,out,in,properties{pk}}
out/search/<index>/index.json          index definition (3072-d HNSW, openai-vectorizer, semantic config)
out/search/<index>/report.pdf          one text-only PDF report per index
out/search/<index>/documents.jsonl     chunked index documents (vector field omitted)
```

Alignment key: composite `<STATION>.<CLASS>.<EQUIP>` is `ScadaDeviceObject.ScadaAliasName` on exactly one vertex
(line ends: on the line's Terminal at each station); TagId = composite + `.MEAS`; alarm `mrid` = owning device CIMMRID.

## Detector patterns the scenario fires

| Pattern / signal | Where |
|---|---|
| generator_degradation | KESTREL.GEN.U2, 30-min bin 14:00 (MVAR stdev 9.0, derate 25 %) |
| agc_removal_instability | KESTREL (GEN AGC 14:10) |
| unit_unplanned_offline | KESTREL U1 14:30 with CB/CB-CRIT, MWCC, KV-EMER-D |
| synchronised_line_trip | 14:40, 4 LINE tags, 2 stations |
| generator_motoring (severe) | KESTREL.GEN.U2.MW 14:52 (-8, -12, -9) |
| scada signals | gen_trip, gen_major_loss, bus_collapse, line_trip, line_kv_collapse, line_overload, transformer_trip, transformer_mva_trip |
| alarm signals | cb_trip, cb_cluster (MARLOW), kv_emer_bus, unreas, br_warn, br_ldsh, br_emer, inter_ldsh, cntr_emer |

Negative: MARLOW BESS1 passes the unit-offline drop stage but fails the inertia gate (no SynchronousMachine).

Cannot fire with two real stations (not faked): regional_cascade (needs >= 8 emergency stations),
system_reactive_event (>= 3 SVC / >= 5 unit stations), coordinated_oscillation (>= 3 inertial stations),
frequency_excursion situation (median out of band >= 2 bins, breadth >= 30). The frequency summary still shows a
mainland normal-band breach at KESTREL and MARLOW.
