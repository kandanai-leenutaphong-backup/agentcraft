# Demo Scenario Spec — Generic NGM Busbar Trip

> **Disclaimer:** Due to the highly sensitive and mission-critical nature of the data, this demo has been fully anonymised to avoid all reference to real power assets, activities, or configurations, while showcasing the unique advantages of GridIQ.

> **Status:** Spec only — not yet implemented.
> **Last updated:** 2026-04-20
> **Target file:** `app/frontend/src/demo/scenarios/ngm_busbar_trip.json`

---

## 1. Design Intent

A fully fictional NGM (National Grid Market) scenario with the
sophistication of a real NGA (National Grid Authority) incident
review. No real station names, no real data, no real NGM
naming conventions — but plausible enough to convince a power-systems
audience. Every station, equipment ID, SCADA tag, alarm label, and
telemetry value is invented.

The scenario demonstrates every GridIQ surface:
- Situation scan (10s radar animation)
- Situation cards (4 severities, each with classification)
- Topology graph (center station + 3 neighbors + live telemetry)
- Investigator chat (tool calls + streamed narrative)
- Delegation to Dispatcher
- Priority actions panel (contacts, procedure references)
- Data Search dock agent (canned telemetry/alarm/frequency replies)

---

## 2. Fictional Grid Topology

### Region: **SER** (South-East Region)

| Station | Type | Capacity | Role |
|---------|------|----------|------|
| REDCLIFF_PS | Thermal power station | 4 × 250 MW = 1000 MW | **Center.** The incident station. |
| NORTHVALE_SS | Switching station | — | Neighbor 1-hop. 220 kV interconnector. |
| BANKSIA_PS | Hydro power station | 2 × 180 MW | Neighbor 1-hop. Generation peer. |
| WENTWORTH_SS | Switching station | — | Neighbor 1-hop. Feeds 132 kV sub-transmission. |
| HARROWBRIDGE_TS | Transmission station | — | Neighbor 2-hop (via NORTHVALE_SS). NER–SER inter-regional terminus, 330 kV. |
| ELDERMOUNT_WF | Wind farm | 24 × 4 MW = 96 MW | Neighbor 2-hop (via BANKSIA_PS). Variable generation peer. |
| KILBARRA_DS | Distribution substation | — | Neighbor 2-hop (via WENTWORTH_SS). 66/22 kV, downstream load. |

### Grid Conventions (fictional)

- Station IDs: `STATION_TYPE` (e.g. `REDCLIFF_PS`, `NORTHVALE_SS`)
- Equipment IDs: `STATION.CLASS.NAME` (e.g. `REDCLIFF_PS.GEN.1`, `REDCLIFF_PS.BUS.220KV_A`)
- SCADA tags: `STATION.CLASS.NAME.MEASUREMENT` (e.g. `REDCLIFF_PS.GEN.3.MW`)
- Circuit breaker naming: `CB-NNN` where NNN is a three-digit bay number (e.g. `CB-052`)
- Alarm labels: short uppercase codes — `CB TRIP`, `KV EMER`, `BUS DIFF`, `PROT OP`, `CB FAIL`
- Time format: `hhmm.ss` in report, ISO 8601 in JSON
- Voltage levels: 220 kV transmission, 15.75 kV generator terminals, 132 kV sub-transmission

---

## 3. Incident Narrative

### Pre-conditions (14:30 AEST, 17 June 2025)
- REDCLIFF_PS Unit 3 generating 241 MW
- REDCLIFF_PS Unit 4 generating 189 MW
- REDCLIFF_PS Unit 1 generating 248 MW (unaffected)
- REDCLIFF_PS Unit 2 offline for scheduled maintenance
- 220 kV A busbar energised, B busbar energised
- NGM total demand: ~23,400 MW
- SER region: ~6,200 MW live, ~8,100 MW capacity
- Frequency: 50.02 Hz

### Event Sequence

| Time | Event |
|------|-------|
| 13:55.30 | **PRECURSOR.** REDCLIFF_PS 220 kV A busbar voltage sags from 220.1 kV to 198.4 kV (10% depression) and recovers to 220.0 kV after **15 seconds**. No protection operates. No alarms raised at the regional control room — the dip is below the standard `KV LOW` alarm threshold (90% sustained) because of its short duration. SCADA records the transient. **GridIQ flags it as INVESTIGATE — transient bus voltage event, possible insulation degradation on a connected element.** |
| 13:56.00 | GridIQ recommendation: contact SERNetworks (the local RTO) for a thermal scan of the 220 kV A busbar bay. *(In the actual demo: this recommendation appears in the Data Search agent on request.)* |
| 14:32.14 | REDCLIFF_PS 220 kV A busbar trips due to inter-phase flashover on Bus Section Isolator ISO-A3. Red phase to earth fault detected by A busbar differential protection (Scheme A). **The faulty asset is the same insulator that caused the 13:55 transient — the precursor was the first sign of insulation breakdown.** |
| 14:32.14 | Busbar protection Scheme A sends trip signal to all CBs connected to 220 kV A busbar. CB-031 (Unit 3 HV side) and CB-041 (Unit 4 HV side) open. |
| 14:32.18 | Unit 3 reverse-power protection operates — generator trips from 241 MW to 0 MW. |
| 14:32.22 | Unit 4 under-frequency protection operates — generator trips from 189 MW to 0 MW. |
| 14:32.25 | 220 kV B busbar remains energised. Unit 1 continues via B busbar (248 MW, stable). Transformer T1 transfers load to B busbar path. |
| 14:32.30 | SCADA alarm burst: 6 alarms arrive at regional control in <1 second (CB-031 TRIP, CB-041 TRIP, GEN.3 PROT OP, GEN.4 PROT OP, BUS.A DIFF TRIP, ISO-A3 EARTH FAULT). |
| 14:32.45 | Frequency in SER drops to nadir of 49.68 Hz. Inter-regional flow on NORTHVALE interconnector surges from 320 MW import to 710 MW import. |
| 14:33.10 | FRS (frequency response service) response: 430 MW of contingency raise dispatched across NGM within 6 seconds. Frequency recovering. |
| 14:33.55 | Frequency returns to SOFB (Standard Operating Frequency Band, 49.85–50.15 Hz). Stabilises at 49.93 Hz. |
| 14:35.00 | NORTHVALE–REDCLIFF 220 kV No. 1 line loading at 89% thermal limit (pre-event: 52%). Operator advisory issued. |
| 14:38.00 | Regional control confirms both units tripped, A busbar isolated. No cascading. |
| 14:52.00 | Market notice issued: non-credible contingency at REDCLIFF_PS — 430 MW generation lost. |
| 15:15.00 | A busbar energisation test commenced. ISO-A3 confirmed faulty — busbar re-energised bypassing ISO-A3. |
| 15:42.00 | Unit 4 resynchronised to B busbar via CB-042. Ramping to 180 MW. |
| 16:10.00 | Unit 3 resynchronised. A busbar returned to service (ISO-A3 bypassed, replacement scheduled). |

### Generation Impact
- Unit 3: 241 MW lost (14:32 → 16:10, ~98 min offline)
- Unit 4: 189 MW lost (14:32 → 15:42, ~70 min offline)
- Total: **430 MW** lost from REDCLIFF_PS
- Unit 1: unaffected (248 MW via B busbar)
- Unit 2: already offline (maintenance)

### Frequency Impact
- SER nadir: **49.68 Hz** (below SOFEB (Std Operating Frequency Excursion Band) 49.75 Hz for 3.8 s, below SOFB 49.85 Hz for 8.2 s)
- GFS (Grid Frequency Standard) met: containment band 47–52 Hz (reasonable endeavours)
- Inter-regional FRS response cleared the deviation within ~100 seconds

### The Two Value-Add Wins (the narration must hammer these)

**Win 1 — Correct classification from the first scan.**
Without GridIQ, the operator's first read of the alarm burst would be "CB-031 has tripped" — a single circuit breaker trip on Unit 3. That's what the loudest alarm says. The truth — that the **busbar** has faulted and ISO-A3 is the suspect asset — typically takes 30+ minutes of phone calls and protection log review to establish. (Comparable industry precedent: in one documented grid incident, the local RTO initially advised the grid authority that the fault was on a single circuit breaker; the correct root cause — a busbar-section fault — was identified **3 hours 20 minutes later**.)
**GridIQ classifies the event as a 220 kV A busbar trip with consequential unit and line outages within seconds of the alarm burst, and flags ISO-A3 as the likely faulty asset.**

**Win 2 — Precursor detection 37 minutes ahead.**
At 13:55:30 — **37 minutes before the busbar trip** — REDCLIFF_PS 220 kV A bus voltage dipped 10% and recovered in 15 seconds. No alarm fired (the dip was below the sustained-low threshold). A human operator scanning SCADA trends would have dismissed it as a sensor glitch or not seen it at all.
**GridIQ flagged the 15-second transient as INVESTIGATE-grade and recommended a thermal scan of the busbar bay. Had operators acted on this 37-minute warning, the trip — and the 430 MW generation loss — could have been prevented or mitigated by switching Units 3+4 onto B busbar before the flashover.**

---

## 4. Situation Cards (5 results from scan)

Each situation must include a **classification** (credible / non_credible / non_event) with a rationale and GOR (Grid Operating Rules) citation. This requires a new frame patch operation: `panel.situations.classify`.

The scan returns **five** situations — the four post-event situations plus **one precursor** detected 37 minutes before the busbar trip. The precursor is the headline "AI win" of the demo.

### Situation 0 — INVESTIGATE (PRECURSOR — the win moment)

```jsonc
{
  "situation_id": "ngm-pre-1",
  "window_start": "2025-06-17 13:55:00",
  "window_end": "2025-06-17 14:00:00",
  "station": "REDCLIFF_PS",
  "severity": "INVESTIGATE",
  "total_score": 4,
  "alarm_score": 0,
  "scada_score": 4,
  "mw_boost": 0,
  "total_mw_lost": 0,
  "max_mw_drop": 0,
  "alarm_count": 0,
  "step_changes": 2,
  "alarm_signals": "{}",
  "scada_signals": "{\"kv_transient\": 1, \"sub_threshold\": 1}",
  "alarm_mrids": "[]",
  "affected_tags": "[\"REDCLIFF_PS.BUS.220KV_A\"]",
  "affected_equipment": "[{\"equipment_id\":\"REDCLIFF_PS.BUS.220KV_A\",\"alarms\":[],\"scada\":[{\"timestamp_aest\":\"2025-06-17 13:55:30\",\"TagId\":\"REDCLIFF_PS.BUS.220KV_A.KV\",\"measurement\":\"KV\",\"Value\":198.4,\"prev_val\":220.1,\"abs_drop\":21.7,\"pct_change\":9.9},{\"timestamp_aest\":\"2025-06-17 13:55:45\",\"TagId\":\"REDCLIFF_PS.BUS.220KV_A.KV\",\"measurement\":\"KV\",\"Value\":220.0,\"prev_val\":198.4,\"abs_drop\":-21.6,\"pct_change\":-10.9}]}]",
  "patterns": "transient_kv_dip,sub_alarm_threshold",
  "pattern_details": "[{\"pattern\":\"transient_kv_dip\",\"duration_s\":15,\"depth_pct\":9.9,\"recovered\":true}]",
  "detected_at": "2025-06-17 13:56:00",
  "detector_version": "v4",
  "config_hash": "demo",
  "station_region": "SER",
  "station_rated_mw": 1000,
  "station_unit_count": 4,
  "region_rated_mw": 8100,
  "region_live_mw": 6200,
  "ngm_live_mw": 23400,
  "impact_station_pct": 0,
  "impact_region_pct": 0,
  "impact_ngm_pct": 0
}
```

**Classification:**

| Field | Value |
|-------|-------|
| classification | `non_event` |
| rule_citation | `GOR 5.8.15(a) — precursor advisory` |
| rationale | A 15-second voltage transient on the 220 kV A busbar (dip to 198.4 kV, 9.9% depression, recovered to nominal) does not meet the threshold for a reportable grid incident — no protection operated and no equipment was lost. However, the depth and shape of the transient are consistent with early-stage insulation breakdown on a connected primary plant element. **GridIQ recommends an immediate thermal/insulation inspection of all bay equipment connected to the 220 kV A busbar, prioritising bus section isolators.** This is an early-warning advisory, not a contingency event. |

### Situation 1 — CRITICAL

```jsonc
{
  "situation_id": "ngm-crit-1",
  "window_start": "2025-06-17 14:30:00",
  "window_end": "2025-06-17 14:40:00",
  "station": "REDCLIFF_PS",
  "severity": "CRITICAL",
  "total_score": 25,
  "alarm_score": 8,
  "scada_score": 12,
  "mw_boost": 5,
  "total_mw_lost": 430,
  "max_mw_drop": 241,
  "alarm_count": 6,
  "step_changes": 8,
  "alarm_signals": "{\"bus_diff\": 1, \"cb_trip\": 2, \"prot_op\": 2, \"earth_fault\": 1}",
  "scada_signals": "{\"gen_trip\": 2, \"gen_major_loss\": 1, \"bus_collapse\": 1, \"line_overload\": 1}",
  "alarm_mrids": "[]",
  "affected_tags": "[\"REDCLIFF_PS.GEN.3\", \"REDCLIFF_PS.GEN.4\"]",
  "affected_equipment": "[{\"equipment_id\":\"REDCLIFF_PS.GEN.3\",\"alarms\":[{\"timestamp_aest\":\"2025-06-17 14:32:18\",\"alarm_label\":\"PROT OP\",\"alarm_text\":\"REDCLIFF_PS GEN 3 REVERSE POWER PROTECTION OPERATED\",\"priority\":1,\"mrid\":\"mrid-rc-g3-01\"},{\"timestamp_aest\":\"2025-06-17 14:32:14\",\"alarm_label\":\"CB TRIP\",\"alarm_text\":\"REDCLIFF_PS 220KV CB-031 TRIPPED\",\"priority\":1,\"mrid\":\"mrid-rc-cb031\"}],\"scada\":[{\"timestamp_aest\":\"2025-06-17 14:32:18\",\"TagId\":\"REDCLIFF_PS.GEN.3.MW\",\"measurement\":\"MW\",\"Value\":0.0,\"prev_val\":241.0,\"abs_drop\":241.0,\"pct_change\":100.0}]},{\"equipment_id\":\"REDCLIFF_PS.GEN.4\",\"alarms\":[{\"timestamp_aest\":\"2025-06-17 14:32:22\",\"alarm_label\":\"PROT OP\",\"alarm_text\":\"REDCLIFF_PS GEN 4 UNDER-FREQUENCY PROTECTION OPERATED\",\"priority\":1,\"mrid\":\"mrid-rc-g4-01\"},{\"timestamp_aest\":\"2025-06-17 14:32:14\",\"alarm_label\":\"CB TRIP\",\"alarm_text\":\"REDCLIFF_PS 220KV CB-041 TRIPPED\",\"priority\":1,\"mrid\":\"mrid-rc-cb041\"}],\"scada\":[{\"timestamp_aest\":\"2025-06-17 14:32:22\",\"TagId\":\"REDCLIFF_PS.GEN.4.MW\",\"measurement\":\"MW\",\"Value\":0.0,\"prev_val\":189.0,\"abs_drop\":189.0,\"pct_change\":100.0}]}]",
  "patterns": "busbar_fault,dual_unit_trip",
  "pattern_details": "[]",
  "detected_at": "2025-06-17 14:41:00",
  "detector_version": "v4",
  "config_hash": "demo",
  "station_region": "SER",
  "station_rated_mw": 1000,
  "station_unit_count": 4,
  "region_rated_mw": 8100,
  "region_live_mw": 6200,
  "ngm_live_mw": 23400,
  "impact_station_pct": 43.0,
  "impact_region_pct": 6.9,
  "impact_ngm_pct": 1.8
}
```

**Classification:**

| Field | Value |
|-------|-------|
| classification | `non_credible` |
| rule_citation | `GOR 5.2.3A(c)` |
| rationale | The simultaneous loss of two generating units connected to the same busbar section constitutes a non-credible contingency under the GOR, as credible contingency assessment considers the loss of a single generating unit or single network element. The busbar fault affected two independent units via shared protection, which exceeds the single-element boundary. NGA assessed reclassification under GOR 5.2.3A(c) and determined recurrence was not reasonably possible after the faulty isolator was identified and bypassed. |

### Situation 2 — MAJOR

```jsonc
{
  "situation_id": "ngm-maj-1",
  "window_start": "2025-06-17 14:30:00",
  "window_end": "2025-06-17 14:40:00",
  "station": "NORTHVALE_SS",
  "severity": "MAJOR",
  "total_score": 14,
  "alarm_score": 5,
  "scada_score": 8,
  "mw_boost": 1,
  "total_mw_lost": 0,
  "max_mw_drop": 0,
  "alarm_count": 4,
  "step_changes": 5,
  "alarm_signals": "{\"line_loading\": 2, \"thermal_advisory\": 1, \"flow_reversal\": 1}",
  "scada_signals": "{\"line_overload\": 1, \"flow_surge\": 1, \"kv_depression\": 1}",
  "alarm_mrids": "[]",
  "affected_tags": "[\"NORTHVALE_SS.LINE.REDCLIFF_1\", \"NORTHVALE_SS.BUS.220KV_A\"]",
  "affected_equipment": "[{\"equipment_id\":\"NORTHVALE_SS.LINE.REDCLIFF_1\",\"alarms\":[{\"timestamp_aest\":\"2025-06-17 14:35:00\",\"alarm_label\":\"THERMAL\",\"alarm_text\":\"NORTHVALE 220KV LINE REDCLIFF NO.1 LOADING 89% THERMAL LIMIT\",\"priority\":2,\"mrid\":\"mrid-nv-ln1-01\"}],\"scada\":[{\"timestamp_aest\":\"2025-06-17 14:32:50\",\"TagId\":\"NORTHVALE_SS.LINE.REDCLIFF_1.MW\",\"measurement\":\"MW\",\"Value\":710.0,\"prev_val\":320.0,\"abs_drop\":-390.0,\"pct_change\":-121.9}]},{\"equipment_id\":\"NORTHVALE_SS.BUS.220KV_A\",\"alarms\":[{\"timestamp_aest\":\"2025-06-17 14:32:48\",\"alarm_label\":\"KV LOW\",\"alarm_text\":\"NORTHVALE 220KV BUS A VOLTAGE LOW 214.2KV\",\"priority\":3,\"mrid\":\"mrid-nv-bus-01\"}],\"scada\":[{\"timestamp_aest\":\"2025-06-17 14:32:48\",\"TagId\":\"NORTHVALE_SS.BUS.220KV_A.KV\",\"measurement\":\"KV\",\"Value\":214.2,\"prev_val\":219.8,\"abs_drop\":5.6,\"pct_change\":2.5}]}]",
  "patterns": "",
  "pattern_details": "[]",
  "detected_at": "2025-06-17 14:41:30",
  "detector_version": "v4",
  "config_hash": "demo",
  "station_region": "SER",
  "station_rated_mw": 0,
  "station_unit_count": 0,
  "region_rated_mw": 8100,
  "region_live_mw": 6200,
  "ngm_live_mw": 23400,
  "impact_station_pct": 0,
  "impact_region_pct": 0,
  "impact_ngm_pct": 0
}
```

**Classification:**

| Field | Value |
|-------|-------|
| classification | `non_event` |
| rule_citation | `GOR 5.8.15(a)(1)(i)` |
| rationale | The NORTHVALE interconnector loading surge is a consequential power system response to the REDCLIFF_PS generation loss, not an independent contingency. No protection operated at NORTHVALE — the alarms are thermal loading advisories. The interconnector remained within its emergency rating. This does not meet the threshold for a reportable grid incident as no critical transmission element was lost or at risk of loss. |

### Situation 3 — SERIOUS

```jsonc
{
  "situation_id": "ngm-ser-1",
  "window_start": "2025-06-17 14:30:00",
  "window_end": "2025-06-17 14:40:00",
  "station": "BANKSIA_PS",
  "severity": "SERIOUS",
  "total_score": 9,
  "alarm_score": 4,
  "scada_score": 4,
  "mw_boost": 1,
  "total_mw_lost": 0,
  "max_mw_drop": 0,
  "alarm_count": 3,
  "step_changes": 3,
  "alarm_signals": "{\"gov_response\": 1, \"agc_override\": 1, \"mw_ramp\": 1}",
  "scada_signals": "{\"gen_ramp\": 2, \"freq_deviation\": 1}",
  "alarm_mrids": "[]",
  "affected_tags": "[\"BANKSIA_PS.GEN.1\", \"BANKSIA_PS.GEN.2\"]",
  "affected_equipment": "[{\"equipment_id\":\"BANKSIA_PS.GEN.1\",\"alarms\":[{\"timestamp_aest\":\"2025-06-17 14:32:50\",\"alarm_label\":\"GOV RESP\",\"alarm_text\":\"BANKSIA_PS GEN 1 GOVERNOR RESPONSE ACTIVE\",\"priority\":3,\"mrid\":\"mrid-bk-g1-01\"}],\"scada\":[{\"timestamp_aest\":\"2025-06-17 14:32:50\",\"TagId\":\"BANKSIA_PS.GEN.1.MW\",\"measurement\":\"MW\",\"Value\":178.0,\"prev_val\":165.0,\"abs_drop\":-13.0,\"pct_change\":-7.9}]},{\"equipment_id\":\"BANKSIA_PS.GEN.2\",\"alarms\":[],\"scada\":[{\"timestamp_aest\":\"2025-06-17 14:32:52\",\"TagId\":\"BANKSIA_PS.GEN.2.MW\",\"measurement\":\"MW\",\"Value\":178.0,\"prev_val\":164.0,\"abs_drop\":-14.0,\"pct_change\":-8.5}]}]",
  "patterns": "",
  "pattern_details": "[]",
  "detected_at": "2025-06-17 14:42:00",
  "detector_version": "v4",
  "config_hash": "demo",
  "station_region": "SER",
  "station_rated_mw": 360,
  "station_unit_count": 2,
  "region_rated_mw": 8100,
  "region_live_mw": 6200,
  "ngm_live_mw": 23400,
  "impact_station_pct": 0,
  "impact_region_pct": 0,
  "impact_ngm_pct": 0
}
```

**Classification:**

| Field | Value |
|-------|-------|
| classification | `non_event` |
| rule_citation | `GOR 5.8.15(a)` |
| rationale | BANKSIA_PS experienced automatic governor response to the NGM frequency excursion. Both units ramped from 165 MW to 178 MW (within rated capacity) as part of normal FRS fast-raise response. No protection operated. No equipment tripped. The SCADA step-changes reflect controlled frequency response, not a fault or contingency. Does not meet the definition of a reportable grid incident. |

### Situation 4 — INVESTIGATE

```jsonc
{
  "situation_id": "ngm-inv-1",
  "window_start": "2025-06-17 14:38:00",
  "window_end": "2025-06-17 14:48:00",
  "station": "WENTWORTH_SS",
  "severity": "INVESTIGATE",
  "total_score": 5,
  "alarm_score": 2,
  "scada_score": 2,
  "mw_boost": 1,
  "total_mw_lost": 12.4,
  "max_mw_drop": 12.4,
  "alarm_count": 2,
  "step_changes": 2,
  "alarm_signals": "{\"prot_op\": 1, \"tx_trip\": 1}",
  "scada_signals": "{\"tx_overload\": 1, \"load_shed\": 1}",
  "alarm_mrids": "[]",
  "affected_tags": "[\"WENTWORTH_SS.TX.T2\"]",
  "affected_equipment": "[{\"equipment_id\":\"WENTWORTH_SS.TX.T2\",\"alarms\":[{\"timestamp_aest\":\"2025-06-17 14:40:12\",\"alarm_label\":\"PROT OP\",\"alarm_text\":\"WENTWORTH_SS 132KV TX T2 OVERCURRENT PROTECTION OPERATED\",\"priority\":1,\"mrid\":\"mrid-ww-tx2-01\"},{\"timestamp_aest\":\"2025-06-17 14:40:12\",\"alarm_label\":\"TX TRIP\",\"alarm_text\":\"WENTWORTH_SS 132/66KV TRANSFORMER T2 TRIPPED\",\"priority\":1,\"mrid\":\"mrid-ww-tx2-02\"}],\"scada\":[{\"timestamp_aest\":\"2025-06-17 14:40:12\",\"TagId\":\"WENTWORTH_SS.TX.T2.MW\",\"measurement\":\"MW\",\"Value\":0.0,\"prev_val\":52.4,\"abs_drop\":52.4,\"pct_change\":100.0}]}]",
  "patterns": "",
  "pattern_details": "[]",
  "detected_at": "2025-06-17 14:49:00",
  "detector_version": "v4",
  "config_hash": "demo",
  "station_region": "SER",
  "station_rated_mw": 0,
  "station_unit_count": 0,
  "region_rated_mw": 8100,
  "region_live_mw": 6200,
  "ngm_live_mw": 23400,
  "impact_station_pct": 0,
  "impact_region_pct": 0.2,
  "impact_ngm_pct": 0.1
}
```

**Classification:**

| Field | Value |
|-------|-------|
| classification | `credible` |
| rule_citation | `GOR 5.2.3(b)` |
| rationale | WENTWORTH_SS 132/66 kV transformer T2 tripped on overcurrent protection following the redistribution of load after the REDCLIFF_PS event. The loss of a single transformer constitutes a credible contingency under GOR 5.2.3(b). However, the trip occurred 8 minutes after the initiating event and was caused by load redistribution, not equipment failure. The transformer was tested and returned to service within 25 minutes. NGA determined the overcurrent condition was transient and not indicative of a persistent risk. |

---

## 5. Classification System — New Frame Patch Op

### Gap in Current System

The kiosk/demo mode has **no way to inject classifications**. The
`SituationCard` component fires `POST /api/situations/classify` on
mount, which fails in kiosk mode (no backend). We need:

### Proposed: `panel.situations.classify` frame patch op

```typescript
// In scenarioSchema.ts:
export interface SituationsClassifyOp {
  classifications: SituationClassificationEntry[];
}

export interface SituationClassificationEntry {
  situation_id: string;
  classification: "credible" | "non_credible" | "non_event";
  rule_citation: string;
  rationale: string;
}

// In FramePatch:
export interface FramePatch {
  // ... existing ops ...
  "panel.situations.classify"?: SituationsClassifyOp;
}
```

### Proposed: Kiosk gate on classify API call

In `SituationCard.tsx`, the `useEffect` that calls `triggerClassify`
should early-return when `IS_KIOSK` is true. Classifications will be
injected by the frame patch instead.

### Proposed: `kiosk_bootstrap.classifications` section

Pre-seed classifications in the JSON bootstrap so they're available
immediately when situations render (before the classify frame fires):

```jsonc
"kiosk_bootstrap": {
  // ... main_agents, dock_agents as before ...
  "classifications": {
    "ngm-pre-1": {
      "classification": "non_event",
      "rule_citation": "GOR 5.8.15(a) — precursor advisory",
      "rationale": "A 15-second voltage transient on the 220 kV A busbar (dip to 198.4 kV, 9.9% depression, recovered to nominal) does not meet the threshold for a reportable grid incident — no protection operated and no equipment was lost. However, the depth and shape of the transient are consistent with early-stage insulation breakdown on a connected primary plant element. GridIQ recommends an immediate thermal/insulation inspection of all bay equipment connected to the 220 kV A busbar, prioritising bus section isolators. This is an early-warning advisory, not a contingency event."
    },
    "ngm-crit-1": {
      "classification": "non_credible",
      "rule_citation": "GOR 5.2.3A(c)",
      "rationale": "The simultaneous loss of two generating units connected to the same busbar section constitutes a non-credible contingency under the GOR, as credible contingency assessment considers the loss of a single generating unit or single network element. The busbar fault affected two independent units via shared protection, which exceeds the single-element boundary. NGA assessed reclassification under GOR 5.2.3A(c) and determined recurrence was not reasonably possible after the faulty isolator was identified and bypassed."
    },
    "ngm-maj-1": {
      "classification": "non_event",
      "rule_citation": "GOR 5.8.15(a)(1)(i)",
      "rationale": "The NORTHVALE interconnector loading surge is a consequential power system response to the REDCLIFF_PS generation loss, not an independent contingency. No protection operated at NORTHVALE — the alarms are thermal loading advisories. The interconnector remained within its emergency rating. This does not meet the threshold for a reportable grid incident as no critical transmission element was lost or at risk of loss."
    },
    "ngm-ser-1": {
      "classification": "non_event",
      "rule_citation": "GOR 5.8.15(a)",
      "rationale": "BANKSIA_PS experienced automatic governor response to the NGM frequency excursion. Both units ramped from 165 MW to 178 MW (within rated capacity) as part of normal FRS fast-raise response. No protection operated. No equipment tripped. The SCADA step-changes reflect controlled frequency response, not a fault or contingency. Does not meet the definition of a reportable grid incident."
    },
    "ngm-inv-1": {
      "classification": "credible",
      "rule_citation": "GOR 5.2.3(b)",
      "rationale": "WENTWORTH_SS 132/66 kV transformer T2 tripped on overcurrent protection following the redistribution of load after the REDCLIFF_PS event. The loss of a single transformer constitutes a credible contingency under GOR 5.2.3(b). However, the trip occurred 8 minutes after the initiating event and was caused by load redistribution, not equipment failure. The transformer was tested and returned to service within 25 minutes. NGA determined the overcurrent condition was transient and not indicative of a persistent risk."
    }
  }
}
```

The `kioskBootstrap.ts` adapter would write these into the
`situationStore.classifications` map as `status: "ready"` entries.

**Decision needed:** Bootstrap pre-seed (instant) vs. frame patch
(animated delay)? Recommend: **both**. Bootstrap pre-seeds them, but
the classify frame can also be used to animate the "Classifying per
GOR 5.2.3..." spinner for a few seconds if you want the drama.

---

## 6. Topology Graph — REDCLIFF_PS Center

```jsonc
{
  "station": "REDCLIFF_PS",
  "overlay": {
    "equipmentIds": ["REDCLIFF_PS.GEN.3", "REDCLIFF_PS.GEN.4"],
    "severity": "CRITICAL"
  },
  "graph": {
    "center": {
      "station": "REDCLIFF_PS",
      "region": "SER",
      "equipment": [
        {
          "equipment": "REDCLIFF_PS.GEN.3",
          "scada_composite_id": "REDCLIFF_PS.GEN.3",
          "cim_classes": ["SynchronousMachine"],
          "nominal_kv": 15.75,
          "mw_max": 250,
          "mva_rated": 295,
          "live": {
            "mw": 0.0, "mvar": 0.0, "kv": 14.8,
            "hz": 49.68,
            "ts": "2025-06-17T14:32:18+10:00",
            "tags": {"MW": "REDCLIFF_PS.GEN.3.MW"}
          }
        },
        {
          "equipment": "REDCLIFF_PS.GEN.4",
          "scada_composite_id": "REDCLIFF_PS.GEN.4",
          "cim_classes": ["SynchronousMachine"],
          "nominal_kv": 15.75,
          "mw_max": 250,
          "mva_rated": 295,
          "live": {
            "mw": 0.0, "mvar": 0.0, "kv": 14.6,
            "hz": 49.68,
            "ts": "2025-06-17T14:32:22+10:00",
            "tags": {"MW": "REDCLIFF_PS.GEN.4.MW"}
          }
        },
        {
          "equipment": "REDCLIFF_PS.GEN.1",
          "scada_composite_id": "REDCLIFF_PS.GEN.1",
          "cim_classes": ["SynchronousMachine"],
          "nominal_kv": 15.75,
          "mw_max": 250,
          "mva_rated": 295,
          "live": {
            "mw": 248.0, "mvar": 38.5, "kv": 15.7,
            "hz": 49.93,
            "ts": "2025-06-17T14:33:55+10:00",
            "tags": {"MW": "REDCLIFF_PS.GEN.1.MW"}
          }
        },
        {
          "equipment": "REDCLIFF_PS.GEN.2",
          "scada_composite_id": "REDCLIFF_PS.GEN.2",
          "cim_classes": ["SynchronousMachine"],
          "nominal_kv": 15.75,
          "mw_max": 250,
          "mva_rated": null,
          "live": null
        },
        {
          "equipment": "REDCLIFF_PS.BUS.220KV_A",
          "scada_composite_id": "REDCLIFF_PS.BUS.220KV_A",
          "cim_classes": ["BusbarSection"],
          "nominal_kv": 220,
          "mw_max": null,
          "mva_rated": null,
          "live": {
            "kv": 0.0, "hz": 49.68,
            "ts": "2025-06-17T14:32:14+10:00"
          }
        },
        {
          "equipment": "REDCLIFF_PS.BUS.220KV_B",
          "scada_composite_id": "REDCLIFF_PS.BUS.220KV_B",
          "cim_classes": ["BusbarSection"],
          "nominal_kv": 220,
          "mw_max": null,
          "mva_rated": null,
          "live": {
            "kv": 217.8, "hz": 49.93,
            "ts": "2025-06-17T14:33:55+10:00"
          }
        },
        {
          "equipment": "REDCLIFF_PS.TX.T1",
          "scada_composite_id": "REDCLIFF_PS.TX.T1",
          "cim_classes": ["PowerTransformer"],
          "nominal_kv": 220,
          "mw_max": 500,
          "mva_rated": 600,
          "live": {
            "mw": 248.0, "mvar": 38.5, "kv": 217.8,
            "ts": "2025-06-17T14:33:55+10:00"
          }
        }
      ],
      "live_summary": {
        "mw_output": 248.0,
        "mw_cap": 1000,
        "freq": 49.93,
        "ts": "2025-06-17T14:33:55+10:00"
      }
    },
    "neighbors": [
      {
        "station": "NORTHVALE_SS",
        "region": "SER",
        "hops": 1,
        "path_classes": ["ACLineSegment"],
        "equipment": [
          {
            "equipment": "NORTHVALE_SS.BUS.220KV_A",
            "scada_composite_id": "NORTHVALE_SS.BUS.220KV_A",
            "cim_classes": ["BusbarSection"],
            "nominal_kv": 220,
            "mw_max": null,
            "mva_rated": null,
            "live": {"kv": 214.2, "hz": 49.93, "ts": "2025-06-17T14:33:55+10:00"}
          }
        ],
        "live_summary": {"mw_output": null, "mw_cap": null, "freq": 49.93, "ts": "2025-06-17T14:33:55+10:00"}
      },
      {
        "station": "BANKSIA_PS",
        "region": "SER",
        "hops": 1,
        "path_classes": ["ACLineSegment"],
        "equipment": [
          {
            "equipment": "BANKSIA_PS.GEN.1",
            "scada_composite_id": "BANKSIA_PS.GEN.1",
            "cim_classes": ["SynchronousMachine"],
            "nominal_kv": 15.75,
            "mw_max": 180,
            "mva_rated": 210,
            "live": {"mw": 178.0, "mvar": 28.0, "kv": 15.6, "ts": "2025-06-17T14:33:55+10:00", "tags": {"MW": "BANKSIA_PS.GEN.1.MW"}}
          },
          {
            "equipment": "BANKSIA_PS.GEN.2",
            "scada_composite_id": "BANKSIA_PS.GEN.2",
            "cim_classes": ["SynchronousMachine"],
            "nominal_kv": 15.75,
            "mw_max": 180,
            "mva_rated": 210,
            "live": {"mw": 178.0, "mvar": 27.0, "kv": 15.6, "ts": "2025-06-17T14:33:55+10:00", "tags": {"MW": "BANKSIA_PS.GEN.2.MW"}}
          }
        ],
        "live_summary": {"mw_output": 356.0, "mw_cap": 360, "freq": 49.93, "ts": "2025-06-17T14:33:55+10:00"}
      },
      {
        "station": "WENTWORTH_SS",
        "region": "SER",
        "hops": 1,
        "path_classes": ["ACLineSegment", "PowerTransformer"],
        "equipment": [
          {
            "equipment": "WENTWORTH_SS.BUS.132KV_A",
            "scada_composite_id": "WENTWORTH_SS.BUS.132KV_A",
            "cim_classes": ["BusbarSection"],
            "nominal_kv": 132,
            "mw_max": null,
            "mva_rated": null,
            "live": {"kv": 129.4, "hz": 49.93, "ts": "2025-06-17T14:33:55+10:00"}
          },
          {
            "equipment": "WENTWORTH_SS.TX.T2",
            "scada_composite_id": "WENTWORTH_SS.TX.T2",
            "cim_classes": ["PowerTransformer"],
            "nominal_kv": 132,
            "mw_max": 60,
            "mva_rated": 75,
            "live": {"mw": 0.0, "kv": 129.4, "ts": "2025-06-17T14:40:12+10:00"}
          }
        ],
        "live_summary": {"mw_output": null, "mw_cap": null, "freq": 49.93, "ts": "2025-06-17T14:33:55+10:00"}
      },
      {
        "station": "HARROWBRIDGE_TS",
        "region": "NER",
        "hops": 2,
        "path_classes": ["ACLineSegment", "ACLineSegment"],
        "parent_station": "NORTHVALE_SS",
        "equipment": [
          {
            "equipment": "HARROWBRIDGE_TS.BUS.330KV_A",
            "scada_composite_id": "HARROWBRIDGE_TS.BUS.330KV_A",
            "cim_classes": ["BusbarSection"],
            "nominal_kv": 330,
            "mw_max": null,
            "mva_rated": null,
            "live": {"kv": 326.4, "hz": 49.93, "ts": "2025-06-17T14:33:55+10:00"}
          },
          {
            "equipment": "HARROWBRIDGE_TS.TX.AT1",
            "scada_composite_id": "HARROWBRIDGE_TS.TX.AT1",
            "cim_classes": ["PowerTransformer"],
            "nominal_kv": 330,
            "mw_max": 750,
            "mva_rated": 850,
            "live": {"mw": 698.0, "mvar": 112.0, "kv": 326.4, "ts": "2025-06-17T14:33:55+10:00", "tags": {"MW": "HARROWBRIDGE_TS.TX.AT1.MW"}}
          }
        ],
        "live_summary": {"mw_output": null, "mw_cap": null, "freq": 49.93, "ts": "2025-06-17T14:33:55+10:00"}
      },
      {
        "station": "ELDERMOUNT_WF",
        "region": "SER",
        "hops": 2,
        "path_classes": ["ACLineSegment", "ACLineSegment"],
        "parent_station": "BANKSIA_PS",
        "equipment": [
          {
            "equipment": "ELDERMOUNT_WF.BUS.132KV_A",
            "scada_composite_id": "ELDERMOUNT_WF.BUS.132KV_A",
            "cim_classes": ["BusbarSection"],
            "nominal_kv": 132,
            "mw_max": null,
            "mva_rated": null,
            "live": {"kv": 130.8, "hz": 49.93, "ts": "2025-06-17T14:33:55+10:00"}
          },
          {
            "equipment": "ELDERMOUNT_WF.WTG.AGG",
            "scada_composite_id": "ELDERMOUNT_WF.WTG.AGG",
            "cim_classes": ["AsynchronousMachine"],
            "nominal_kv": 0.69,
            "mw_max": 96,
            "mva_rated": 105,
            "live": {"mw": 71.4, "mvar": 8.2, "kv": 0.69, "ts": "2025-06-17T14:33:55+10:00", "tags": {"MW": "ELDERMOUNT_WF.WTG.AGG.MW"}}
          }
        ],
        "live_summary": {"mw_output": 71.4, "mw_cap": 96, "freq": 49.93, "ts": "2025-06-17T14:33:55+10:00"}
      },
      {
        "station": "KILBARRA_DS",
        "region": "SER",
        "hops": 2,
        "path_classes": ["ACLineSegment", "PowerTransformer", "ACLineSegment"],
        "parent_station": "WENTWORTH_SS",
        "equipment": [
          {
            "equipment": "KILBARRA_DS.BUS.66KV_A",
            "scada_composite_id": "KILBARRA_DS.BUS.66KV_A",
            "cim_classes": ["BusbarSection"],
            "nominal_kv": 66,
            "mw_max": null,
            "mva_rated": null,
            "live": {"kv": 0.0, "hz": 49.93, "ts": "2025-06-17T14:40:12+10:00"}
          },
          {
            "equipment": "KILBARRA_DS.LOAD.FEEDER_F4",
            "scada_composite_id": "KILBARRA_DS.LOAD.FEEDER_F4",
            "cim_classes": ["EnergyConsumer"],
            "nominal_kv": 22,
            "mw_max": 18,
            "mva_rated": 20,
            "live": {"mw": 0.0, "mvar": 0.0, "kv": 0.0, "ts": "2025-06-17T14:40:12+10:00"}
          }
        ],
        "live_summary": {"mw_output": null, "mw_cap": null, "freq": 49.93, "ts": "2025-06-17T14:40:12+10:00"}
      }
    ],
    "links": [
      {
        "from": "REDCLIFF_PS", "to": "NORTHVALE_SS",
        "path_classes": ["ACLineSegment"], "hops": 1, "nominal_kv": 220,
        "lines": [
          {"line_name": "NORTHVALE-1", "line_mrid": "ln-rc-nv-1", "near_terminal": "REDCLIFF_PS.220KV_B", "far_terminal": "NORTHVALE_SS.220KV_A", "nominal_kv": 220, "via_class": "ACLineSegment"}
        ]
      },
      {
        "from": "REDCLIFF_PS", "to": "BANKSIA_PS",
        "path_classes": ["ACLineSegment"], "hops": 1, "nominal_kv": 220,
        "lines": [
          {"line_name": "BANKSIA-1", "line_mrid": "ln-rc-bk-1", "near_terminal": "REDCLIFF_PS.220KV_B", "far_terminal": "BANKSIA_PS.220KV_A", "nominal_kv": 220, "via_class": "ACLineSegment"}
        ]
      },
      {
        "from": "REDCLIFF_PS", "to": "WENTWORTH_SS",
        "path_classes": ["ACLineSegment", "PowerTransformer"], "hops": 1, "nominal_kv": 220,
        "lines": [
          {"line_name": "WENTWORTH-1", "line_mrid": "ln-rc-ww-1", "near_terminal": "REDCLIFF_PS.220KV_B", "far_terminal": "WENTWORTH_SS.132KV_A", "nominal_kv": 220, "via_class": "ACLineSegment"}
        ]
      },
      {
        "from": "NORTHVALE_SS", "to": "HARROWBRIDGE_TS",
        "path_classes": ["ACLineSegment"], "hops": 1, "nominal_kv": 330,
        "lines": [
          {"line_name": "HARROWBRIDGE-1", "line_mrid": "ln-nv-hb-1", "near_terminal": "NORTHVALE_SS.220KV_A", "far_terminal": "HARROWBRIDGE_TS.330KV_A", "nominal_kv": 330, "via_class": "ACLineSegment"}
        ]
      },
      {
        "from": "BANKSIA_PS", "to": "ELDERMOUNT_WF",
        "path_classes": ["ACLineSegment"], "hops": 1, "nominal_kv": 132,
        "lines": [
          {"line_name": "ELDERMOUNT-1", "line_mrid": "ln-bk-em-1", "near_terminal": "BANKSIA_PS.132KV_A", "far_terminal": "ELDERMOUNT_WF.132KV_A", "nominal_kv": 132, "via_class": "ACLineSegment"}
        ]
      },
      {
        "from": "WENTWORTH_SS", "to": "KILBARRA_DS",
        "path_classes": ["ACLineSegment"], "hops": 1, "nominal_kv": 66,
        "lines": [
          {"line_name": "KILBARRA-1", "line_mrid": "ln-ww-kb-1", "near_terminal": "WENTWORTH_SS.66KV_A", "far_terminal": "KILBARRA_DS.66KV_A", "nominal_kv": 66, "via_class": "ACLineSegment"}
        ]
      }
    ]
  }
}
```

**Notes on the second-order neighbors:**

- **HARROWBRIDGE_TS** is the inter-regional terminus on the other end of the NORTHVALE 220 kV interconnector — different region (NER), 330 kV step-up via autotransformer AT1. Carries the bulk of the inter-regional flow that surged after REDCLIFF tripped.
- **ELDERMOUNT_WF** is a wind farm aggregated as a single 96 MW asynchronous machine, fed via BANKSIA_PS at 132 kV. Demonstrates a non-synchronous generation neighbor — useful for showing that the topology view handles WTG (wind turbine generator) equipment classes, not just thermal/hydro.
- **KILBARRA_DS** is a downstream distribution substation behind WENTWORTH_SS, connected at 66 kV with a 22 kV feeder load. Shows the load lost when WENTWORTH T2 tripped at 14:40:12 (12.4 MW load_lost in situation `ngm-inv-1` corresponds to KILBARRA feeders).

These 2-hop neighbors don't need overlays or alarm highlights — they're rendered for context only. The operator can click them to expand further if the topology UI supports it.

---

## 7. Frame Sequence — Full Playback Script

~30 frames, ~95 seconds total runtime. Every string below is the
literal value that goes into the JSON. Nothing is summarized.

**Narration discipline:** every `narration` field is a presenter
script line. It says what just appeared on screen AND why it matters.
Value-add moments (§3 "Two Wins") are explicitly called out — see the
Ⓢ markers in narration text and the catalog in §11.

---

### Phase 1: Situation Scan (frames f000a–f000c, ~12s)

#### f000a — Scan start
```jsonc
{
  "id": "f000a",
  "chapter": "Situation scan",
  "narration": "GridIQ runs continuously. Every five minutes it sweeps every alarm, every SCADA tag, and every frequency reading across the NGM — looking for the events that matter. Let's watch one scan execute.",
  "transition_ms": 200,
  "patch": {
    "panel.situations.scan_start": { "estimate_ms": 10000 }
  }
}
```

#### f000b — Scan wait (10s)
```jsonc
{
  "id": "f000b",
  "narration": "The scan is processing roughly 40,000 SCADA tags and the last hour of alarm history. In ten seconds it'll come back with a ranked list of situations — the events the operator needs to know about right now.",
  "transition_ms": 10000,
  "patch": {}
}
```

#### f000c — Situations detected
```jsonc
{
  "id": "f000c",
  "chapter": "Situations detected",
  "narration": "Five situations detected, ranked by severity. One CRITICAL, one MAJOR, one SERIOUS, and — importantly — two INVESTIGATE-grade items. The first INVESTIGATE card is dated 13:55, before the main event. We'll come back to it. Ⓢ",
  "transition_ms": 1500,
  "patch": {
    "panel.situations.set": {
      "situations": [
        // << Situation 0 (ngm-pre-1) full JSON from §4 — PRECURSOR >>
        // << Situation 1 (ngm-crit-1) full JSON from §4 >>
        // << Situation 2 (ngm-maj-1) full JSON from §4 >>
        // << Situation 3 (ngm-ser-1) full JSON from §4 >>
        // << Situation 4 (ngm-inv-1) full JSON from §4 >>
      ]
    }
  }
}
```
> The 5 situation objects are the exact JSON blocks from §4 above.
> Order in the array: precursor first (oldest detected_at), then
> CRITICAL, MAJOR, SERIOUS, INVESTIGATE. The UI will sort by
> severity — the precursor will visually appear at the bottom of
> the list, which is exactly the framing we want for the reveal in
> Phase 7.

---

### Phase 2: Classification (frames f000d–f000e, ~4s)

#### f000d — Classification spinner
```jsonc
{
  "id": "f000d",
  "narration": "Each card is now being classified against the Grid Operating Rules — credible, non-credible, or non-event. This is the analysis NGA normally publishes in incident review reports days after an event. GridIQ does it in seconds, on every situation, automatically.",
  "transition_ms": 3000,
  "patch": {}
}
```

#### f000e — Classifications appear
```jsonc
{
  "id": "f000e",
  "chapter": "Classifications",
  "narration": "Classifications back. The CRITICAL is non-credible — two units lost from a single busbar fault, that exceeds the single-element boundary. The INVESTIGATE on WENTWORTH is credible — a single transformer trip. The other two are non-events — normal system response. Each classification cites the GOR clause and includes a written rationale. Ⓢ",
  "transition_ms": 1000,
  "patch": {
    "panel.situations.classify": {
      "classifications": [
        {
          "situation_id": "ngm-pre-1",
          "classification": "non_event",
          "rule_citation": "GOR 5.8.15(a) — precursor advisory",
          "rationale": "A 15-second voltage transient on the 220 kV A busbar (dip to 198.4 kV, 9.9% depression, recovered to nominal) does not meet the threshold for a reportable grid incident — no protection operated and no equipment was lost. However, the depth and shape of the transient are consistent with early-stage insulation breakdown on a connected primary plant element. GridIQ recommends an immediate thermal/insulation inspection of all bay equipment connected to the 220 kV A busbar, prioritising bus section isolators. This is an early-warning advisory, not a contingency event."
        },
        {
          "situation_id": "ngm-crit-1",
          "classification": "non_credible",
          "rule_citation": "GOR 5.2.3A(c)",
          "rationale": "The simultaneous loss of two generating units connected to the same busbar section constitutes a non-credible contingency under the GOR, as credible contingency assessment considers the loss of a single generating unit or single network element. The busbar fault affected two independent units via shared protection, which exceeds the single-element boundary. NGA assessed reclassification under GOR 5.2.3A(c) and determined recurrence was not reasonably possible after the faulty isolator was identified and bypassed."
        },
        {
          "situation_id": "ngm-maj-1",
          "classification": "non_event",
          "rule_citation": "GOR 5.8.15(a)(1)(i)",
          "rationale": "The NORTHVALE interconnector loading surge is a consequential power system response to the REDCLIFF_PS generation loss, not an independent contingency. No protection operated at NORTHVALE — the alarms are thermal loading advisories. The interconnector remained within its emergency rating. This does not meet the threshold for a reportable grid incident as no critical transmission element was lost or at risk of loss."
        },
        {
          "situation_id": "ngm-ser-1",
          "classification": "non_event",
          "rule_citation": "GOR 5.8.15(a)",
          "rationale": "BANKSIA_PS experienced automatic governor response to the NGM frequency excursion. Both units ramped from 165 MW to 178 MW (within rated capacity) as part of normal FRS fast-raise response. No protection operated. No equipment tripped. The SCADA step-changes reflect controlled frequency response, not a fault or contingency. Does not meet the definition of a reportable grid incident."
        },
        {
          "situation_id": "ngm-inv-1",
          "classification": "credible",
          "rule_citation": "GOR 5.2.3(b)",
          "rationale": "WENTWORTH_SS 132/66 kV transformer T2 tripped on overcurrent protection following the redistribution of load after the REDCLIFF_PS event. The loss of a single transformer constitutes a credible contingency under GOR 5.2.3(b). However, the trip occurred 8 minutes after the initiating event and was caused by load redistribution, not equipment failure. The transformer was tested and returned to service within 25 minutes. NGA determined the overcurrent condition was transient and not indicative of a persistent risk."
        }
      ]
    }
  }
}
```

---

### Phase 3: Topology (frame f000f, ~1s)

#### f000f — Topology graph loads
```jsonc
{
  "id": "f000f",
  "chapter": "Topology",
  "narration": "The topology view auto-loads, centred on REDCLIFF — the station behind the CRITICAL card. Units 3 and 4 in red, both at zero. Unit 1 still online via the B busbar at 248 MW. The 220 kV A busbar shows zero volts — collapsed. And look at the NORTHVALE link out to the right: 710 MW, 89% thermal. The grid is compensating, hard. Ⓢ GridIQ pre-loaded the right station and pre-highlighted the right equipment — the operator didn't have to navigate.",
  "transition_ms": 600,
  "patch": {
    "topology.set": {
      // << Full topology.set payload from §6 >>
    }
  }
}
```
> The topology payload is the exact JSON from §6. Not duplicated here.

---

### Phase 4: Investigator Chat (frames f001–f014, ~25s)

#### f001 — User message
```jsonc
{
  "id": "f001",
  "chapter": "Investigation",
  "narration": "The operator opens the Investigator agent and asks the obvious question. Note the framing — the operator already knows two units dropped because GridIQ surfaced it on the situation card. They're now asking 'why', not 'what'.",
  "transition_ms": 600,
  "patch": {
    "chat.append": {
      "agent": "investigator",
      "role": "user",
      "text": "There's been a major generation trip at REDCLIFF. Two units down, frequency dropped. What happened?"
    }
  }
}
```

#### f002 — Investigator: find_alarms tool call
```jsonc
{
  "id": "f002",
  "narration": "The agent doesn't guess. It calls a tool. First step — pull the alarm log for REDCLIFF in the event window. You can see the tool name, the arguments, and the spinner — every step is auditable.",
  "transition_ms": 200,
  "patch": {
    "chat.append": {
      "agent": "investigator",
      "role": "assistant",
      "agent_name": "Investigator",
      "text": "",
      "tool_calls": [
        {
          "id": "tc-alarms-1",
          "name": "find_alarms",
          "arguments": {
            "station": "REDCLIFF_PS",
            "start": "2025-06-17 14:30",
            "end": "2025-06-17 14:45"
          },
          "status": "running"
        }
      ]
    }
  }
}
```

#### f003 — find_alarms result
```jsonc
{
  "id": "f003",
  "narration": "Six alarms in 16 seconds. Notice the loudest first-impression alarm here would be 'CB-031 has tripped' — a single circuit breaker. That's what a human operator's eye lands on. But the agent sees the bus differential trip and the earth fault on ISO-A3 in the same burst — the real story. Ⓢ In a comparable grid incident, the RTO initially told the grid authority it was a different breaker; that advice was corrected three hours and twenty minutes later. GridIQ is about to get this right in seconds.",
  "transition_ms": 2000,
  "patch": {
    "chat.update_tool": {
      "agent": "investigator",
      "id": "tc-alarms-1",
      "status": "complete",
      "duration_ms": 2000,
      "result": "{\"columns\":[\"timestamp_aest\",\"equipment\",\"alarm_label\",\"alarm_text\",\"priority\"],\"rows\":[[\"2025-06-17 14:32:14\",\"REDCLIFF_PS.CB.031\",\"CB TRIP\",\"REDCLIFF_PS 220KV CB-031 TRIPPED\",1],[\"2025-06-17 14:32:14\",\"REDCLIFF_PS.CB.041\",\"CB TRIP\",\"REDCLIFF_PS 220KV CB-041 TRIPPED\",1],[\"2025-06-17 14:32:18\",\"REDCLIFF_PS.GEN.3\",\"PROT OP\",\"REDCLIFF_PS GEN 3 REVERSE POWER PROTECTION OPERATED\",1],[\"2025-06-17 14:32:22\",\"REDCLIFF_PS.GEN.4\",\"PROT OP\",\"REDCLIFF_PS GEN 4 UNDER-FREQUENCY PROTECTION OPERATED\",1],[\"2025-06-17 14:32:14\",\"REDCLIFF_PS.BUS.220KV_A\",\"BUS DIFF\",\"REDCLIFF_PS 220KV A BUSBAR DIFFERENTIAL PROTECTION OPERATED\",1],[\"2025-06-17 14:32:14\",\"REDCLIFF_PS.ISO.A3\",\"EARTH FLT\",\"REDCLIFF_PS BUS SECTION ISOLATOR ISO-A3 EARTH FAULT DETECTED\",1]]}"
    }
  }
}
```

#### f004 — Investigator: find_scada tool call
```jsonc
{
  "id": "f004",
  "narration": "Second tool call — SCADA telemetry to quantify the MW loss and confirm which busbar collapsed. Same pattern: explicit tool, explicit arguments, traceable.",
  "transition_ms": 200,
  "patch": {
    "chat.append": {
      "agent": "investigator",
      "role": "assistant",
      "agent_name": "Investigator",
      "text": "",
      "tool_calls": [
        {
          "id": "tc-scada-1",
          "name": "find_scada",
          "arguments": {
            "tags": [
              "REDCLIFF_PS.GEN.3.MW",
              "REDCLIFF_PS.GEN.4.MW",
              "REDCLIFF_PS.GEN.1.MW",
              "REDCLIFF_PS.BUS.220KV_A.KV"
            ],
            "start": "2025-06-17 14:30",
            "end": "2025-06-17 14:45"
          },
          "status": "running"
        }
      ]
    }
  }
}
```

#### f005 — find_scada result
```jsonc
{
  "id": "f005",
  "narration": "Confirmed. Unit 3 dropped from 241 to zero, Unit 4 from 189 to zero — 430 MW gone. Unit 1 holding steady at 248 MW on the B busbar. The A busbar voltage is at zero — it has collapsed and isolated.",
  "transition_ms": 1500,
  "patch": {
    "chat.update_tool": {
      "agent": "investigator",
      "id": "tc-scada-1",
      "status": "complete",
      "duration_ms": 1500,
      "result": "{\"columns\":[\"TagId\",\"timestamp_aest\",\"Value\",\"prev_val\",\"change\"],\"rows\":[[\"REDCLIFF_PS.GEN.3.MW\",\"2025-06-17 14:32:18\",0.0,241.0,\"-241.0 (100%)\",\"TRIP\"],[\"REDCLIFF_PS.GEN.4.MW\",\"2025-06-17 14:32:22\",0.0,189.0,\"-189.0 (100%)\",\"TRIP\"],[\"REDCLIFF_PS.GEN.1.MW\",\"2025-06-17 14:32:30\",248.0,248.0,\"0.0 (0%)\",\"STABLE\"],[\"REDCLIFF_PS.BUS.220KV_A.KV\",\"2025-06-17 14:32:14\",0.0,220.1,\"-220.1 (100%)\",\"COLLAPSED\"]]}"
    }
  }
}
```

#### f006 — Start streaming response
```jsonc
{
  "id": "f006",
  "chapter": "Analysis",
  "narration": "Now the agent synthesises. It's about to give the operator the causal chain in plain English — watch for the words 'busbar' and 'ISO-A3'. Ⓢ That's the correct classification, arrived at within seconds of the alarm burst.",
  "transition_ms": 90,
  "patch": {
    "chat.append": {
      "agent": "investigator",
      "role": "assistant",
      "agent_name": "Investigator",
      "text": ""
    }
  }
}
```

#### f007–f018 — Streamed tokens (12 chunks)

Each chunk is a `chat.append_token` op on the `investigator` agent.
The full assembled text reads:

> At 14:32 AEST, the 220 kV A busbar at REDCLIFF_PS tripped following
> an inter-phase flashover on bus section isolator ISO-A3. Busbar
> differential protection (Scheme A) operated correctly and tripped
> CB-031 and CB-041, disconnecting Units 3 and 4 from 241 MW and
> 189 MW respectively — 430 MW total generation loss.
>
> Unit 1 was unaffected as it was connected via the B busbar and
> continues generating 248 MW.
>
> Frequency in SER dropped to a nadir of 49.68 Hz — below SOFEB
> (49.75 Hz) for 3.8 seconds and below SOFB (49.85 Hz) for
> 8.2 seconds. FRS contingency raise of 430 MW was dispatched
> across the NGM and frequency recovered within 100 seconds.
>
> The NORTHVALE interconnector surged from 320 MW to 710 MW (89%
> thermal limit) as inter-regional flows compensated for the
> REDCLIFF generation loss.
>
> Root cause: inter-phase flashover on ISO-A3. The isolator was open
> but tracking across the red phase insulator caused a phase-to-earth
> fault, triggering the A busbar differential relay.
>
> I'm handing this to the Dispatcher for recommended operator actions.

Token chunks:

```jsonc
// f007
{ "id": "f007", "transition_ms": 60, "patch": { "chat.append_token": { "agent": "investigator", "text": "At 14:32 AEST, the 220 kV A busbar at REDCLIFF_PS tripped " } } }

// f008
{ "id": "f008", "transition_ms": 60, "patch": { "chat.append_token": { "agent": "investigator", "text": "following an inter-phase flashover on bus section isolator ISO-A3. " } } }

// f009
{ "id": "f009", "transition_ms": 60, "patch": { "chat.append_token": { "agent": "investigator", "text": "Busbar differential protection (Scheme A) operated correctly and tripped CB-031 and CB-041, " } } }

// f010
{ "id": "f010", "transition_ms": 60, "patch": { "chat.append_token": { "agent": "investigator", "text": "disconnecting Units 3 and 4 from 241 MW and 189 MW respectively — **430 MW total generation loss.**\n\n" } } }

// f011
{ "id": "f011", "transition_ms": 60, "patch": { "chat.append_token": { "agent": "investigator", "text": "Unit 1 was unaffected as it was connected via the B busbar and continues generating 248 MW.\n\n" } } }

// f012
{ "id": "f012", "transition_ms": 60, "patch": { "chat.append_token": { "agent": "investigator", "text": "Frequency in SER dropped to a nadir of **49.68 Hz** — below SOFEB (49.75 Hz) for 3.8 s " } } }

// f013
{ "id": "f013", "transition_ms": 60, "patch": { "chat.append_token": { "agent": "investigator", "text": "and below SOFB (49.85 Hz) for 8.2 s. FRS contingency raise of 430 MW was dispatched across the NGM " } } }

// f014
{ "id": "f014", "transition_ms": 60, "patch": { "chat.append_token": { "agent": "investigator", "text": "and frequency recovered within 100 seconds.\n\n" } } }

// f015
{ "id": "f015", "transition_ms": 60, "patch": { "chat.append_token": { "agent": "investigator", "text": "The NORTHVALE interconnector surged from 320 MW to 710 MW (89% thermal limit) " } } }

// f016
{ "id": "f016", "transition_ms": 60, "patch": { "chat.append_token": { "agent": "investigator", "text": "as inter-regional flows compensated for the REDCLIFF generation loss.\n\n" } } }

// f017
{ "id": "f017", "transition_ms": 60, "patch": { "chat.append_token": { "agent": "investigator", "text": "**Root cause:** inter-phase flashover on ISO-A3. The isolator was open but tracking across the red phase insulator caused a phase-to-earth fault, triggering the A busbar differential relay.\n\n" } } }

// f018
{ "id": "f018", "transition_ms": 200, "patch": { "chat.append_token": { "agent": "investigator", "text": "I'm handing this to the Dispatcher for recommended operator actions." } } }
```

---

### Phase 5: Delegation + Dispatcher (frames f019–f024, ~15s)

#### f019 — Delegation message
```jsonc
{
  "id": "f019",
  "chapter": "Delegation to Dispatcher",
  "narration": "The investigator hands the case to the Dispatcher agent. The hand-off is a structured summary, not a transcript dump — the dispatcher gets the facts it needs to act. The tab will switch automatically.",
  "transition_ms": 400,
  "patch": {
    "chat.append": {
      "agent": "dispatcher",
      "role": "user",
      "is_delegation": true,
      "text": "Investigation summary: REDCLIFF_PS 220 kV A busbar fault caused 430 MW generation loss (Units 3 and 4). Frequency nadir 49.68 Hz in SER, FRS responded. NORTHVALE interconnector at 89% thermal. Root cause: inter-phase flashover on bus section isolator ISO-A3. Unit 1 unaffected (B busbar). Recommend operator actions for isolation, restoration, and market notification."
    }
  }
}
```

#### f020 — Switch to Dispatcher tab
```jsonc
{
  "id": "f020",
  "transition_ms": 200,
  "patch": {
    "agent.set_active": { "agent": "dispatcher" }
  }
}
```

#### f021 — Dispatcher: search_procedures tool call
```jsonc
{
  "id": "f021",
  "narration": "Dispatcher's first move is the same discipline — a tool call, not a guess. It's pulling the operating procedures library for anything relevant to a busbar trip with generation loss.",
  "transition_ms": 1200,
  "patch": {
    "chat.append": {
      "agent": "dispatcher",
      "role": "assistant",
      "agent_name": "Dispatcher",
      "text": "",
      "tool_calls": [
        {
          "id": "tc-proc-1",
          "name": "search_procedures",
          "arguments": {
            "query": "220kV busbar trip isolation restoration generator resynchronisation market notice non-credible contingency"
          },
          "status": "running"
        }
      ]
    }
  }
}
```

#### f022 — search_procedures result
```jsonc
{
  "id": "f022",
  "narration": "Two procedures matched: PROC-BUS-220 for busbar restoration, and PROC-GEN-RESYNC for getting the units back. The dispatcher will cite both in the action cards.",
  "transition_ms": 1500,
  "patch": {
    "chat.update_tool": {
      "agent": "dispatcher",
      "id": "tc-proc-1",
      "status": "complete",
      "duration_ms": 1500,
      "result": "[{\"doc_id\":\"PROC-BUS-220\",\"title\":\"220 kV Busbar Restoration After Protection Trip\",\"snippet\":\"Following a busbar protection operation, confirm the busbar is earthed and isolated. Conduct visual inspection of all bus section equipment. Request insulation resistance testing before re-energisation. If the fault is confirmed on a bus section isolator, the busbar may be re-energised with the faulty section bypassed, subject to network security assessment.\"},{\"doc_id\":\"PROC-GEN-RESYNC\",\"title\":\"Generator Resynchronisation After Forced Outage\",\"snippet\":\"After a forced trip, confirm all protection has reset. Check AVR, governor, and excitation system health. For units tripped by reverse-power or under-frequency protection (not internal fault), resynchronisation may proceed once the network fault is cleared. Ramp to target output over 15 minutes minimum. For units tripped by differential or overcurrent protection, an insulation resistance test is required before restart.\"}]"
    }
  }
}
```

---

### Phase 6: Priority Actions (frames f023–f027, ~15s)

#### f023 — Action 1: Confirm isolation
```jsonc
{
  "id": "f023",
  "chapter": "Operator actions",
  "narration": "Five prioritised actions are about to drop into the panel. These aren't generic advice — each one cites the procedure, names the people to call, and explains the reasoning. Action one: confirm the busbar is isolated and inspect the suspect isolator. Highest priority because nothing else can happen until ISO-A3 is physically checked.",
  "transition_ms": 600,
  "patch": {
    "panel.priority_action.append": {
      "action": "Confirm A busbar isolation and assess ISO-A3 damage",
      "reasoning": "Busbar differential protection operated correctly, but the root cause — inter-phase flashover on bus section isolator ISO-A3 — requires physical inspection before the A busbar can be re-energised. The flashover may have caused insulation damage to adjacent equipment.",
      "guide": "1. Confirm 220 kV A busbar is earthed and all associated CBs are locked open.\n2. Visual inspection of ISO-A3 — check for arc damage, tracking marks, and insulation degradation.\n3. Request insulation resistance test on ISO-A3 and adjacent bus section.\n4. Report findings to regional control desk.\n5. If ISO-A3 is confirmed faulty, busbar may be re-energised with ISO-A3 bypassed per PROC-BUS-220.",
      "priority": 1,
      "contacts": [
        { "name": "SER Regional Control Desk", "role": "Duty Operator", "phone": "+61 3 0000 0001", "teams": "ser-regional-control" },
        { "name": "REDCLIFF Station Manager", "role": "Station Manager", "phone": "+61 3 0000 0002", "teams": "redcliff-station" }
      ]
    }
  }
}
```

#### f024 — Action 2: Monitor interconnector
```jsonc
{
  "id": "f024",
  "narration": "Action two: monitor the NORTHVALE interconnector. It's the secondary risk — if loading creeps past 95%, the operator needs a redispatch plan ready before automatic protection trips the line.",
  "transition_ms": 600,
  "patch": {
    "panel.priority_action.append": {
      "action": "Monitor NORTHVALE interconnector thermal loading",
      "reasoning": "The NORTHVALE–REDCLIFF 220 kV No. 1 line is at 89% thermal rating following the generation loss. While within emergency rating, any further contingency on the SER–adjacent interconnector could cause thermal overload and automatic line trip, risking cascading.",
      "guide": "1. Monitor NORTHVALE_SS.LINE.REDCLIFF_1.MW on 5-minute trend — currently 710 MW.\n2. If loading exceeds 95% thermal (approx. 755 MW), initiate pre-emptive generation redispatch.\n3. Consider constraining the REDCLIFF–NORTHVALE flow path until REDCLIFF generation is partially restored.\n4. Coordinate with NGM dispatch to ensure adequate inter-regional headroom.",
      "priority": 2
    }
  }
}
```

#### f025 — Action 3: Resynchronise Unit 4
```jsonc
{
  "id": "f025",
  "narration": "Action three: get Unit 4 back. The dispatcher distinguishes Unit 4 (under-frequency trip, system condition — safe to restart) from Unit 3 (reverse-power trip, possible internal fault — needs an insulation test first). That nuance is in PROC-GEN-RESYNC; the agent applies it.",
  "transition_ms": 600,
  "patch": {
    "panel.priority_action.append": {
      "action": "Prepare Unit 4 for resynchronisation to B busbar",
      "reasoning": "Unit 4 tripped on under-frequency protection — this is a system-condition trip, not an internal equipment fault. Unit 4 is likely clear to restart once the network fault is confirmed isolated. Unit 3 tripped on reverse-power protection, which may indicate backfeed through the generator transformer — an insulation resistance test is recommended before Unit 3 restart.",
      "guide": "1. Confirm Unit 4 protection has reset — check reverse-power, under-frequency, and differential relays.\n2. Verify AVR and governor are healthy.\n3. Synchronise Unit 4 via CB-042 to 220 kV B busbar.\n4. Ramp to 180 MW over 15 minutes per PROC-GEN-RESYNC.\n5. Unit 3 restart: defer until insulation resistance test confirms no winding damage.",
      "priority": 2,
      "contacts": [
        { "name": "REDCLIFF Generation Controller", "role": "Unit Controller", "phone": "+61 3 0000 0003", "teams": "redcliff-generation" }
      ]
    }
  }
}
```

#### f026 — Action 4: Market notice
```jsonc
{
  "id": "f026",
  "narration": "Action four: the market notice. Required within 30 minutes of a non-credible contingency. The dispatcher has drafted the substance — station, MW, frequency, cause, reclassification assessment — and given the operator the 15:02 deadline.",
  "transition_ms": 600,
  "patch": {
    "panel.priority_action.append": {
      "action": "Issue market notice — non-credible contingency event",
      "reasoning": "The simultaneous loss of two generating units (430 MW) from a single busbar fault is a non-credible contingency event under GOR 5.8.15(a)(1)(i). A market notice is required within 30 minutes of the event. The reclassification assessment under GOR 5.2.3A(c) should confirm that recurrence is not reasonably possible, as the faulty isolator has been identified.",
      "guide": "1. Draft market notice: REDCLIFF_PS, 430 MW generation lost (Units 3 and 4), frequency nadir 49.68 Hz in SER, cause identified as inter-phase flashover on bus section isolator ISO-A3.\n2. Include reclassification assessment: not reclassified as credible — faulty isolator identified and will be bypassed/replaced. Recurrence not reasonably possible.\n3. Submit via market systems within 30 minutes of event (deadline: 15:02 AEST).",
      "priority": 3
    }
  }
}
```

#### f027 — Action 5: Incident report
```jsonc
{
  "id": "f027",
  "narration": "Action five: the 24-hour reportable grid incident report. The agent has pre-listed every artefact the report needs — alarm log, SCADA snapshots, protection sequence, frequency trace, interconnector chart, ISO-A3 findings. The operator's job is to attach them, not assemble them.",
  "transition_ms": 1200,
  "patch": {
    "panel.priority_action.append": {
      "action": "File reportable grid incident report within 24 hours",
      "reasoning": "Non-credible contingency events impacting critical transmission elements require a reportable grid incident report under GOR 5.8.15(c). The report must cover the event sequence, protection performance, frequency impact, and rectification actions.",
      "guide": "Attach the following to incident report form IR-22B:\n- Alarm log: 6 alarms from 14:32:14 to 14:32:30\n- SCADA snapshots: GEN.3, GEN.4, GEN.1, BUS.A, BUS.B, T1\n- Protection operation sequence: bus diff Scheme A → CB-031/CB-041 → GEN.3 reverse-power → GEN.4 under-frequency\n- Frequency trace: 50.02 Hz → 49.68 Hz nadir → 49.93 Hz recovery\n- NORTHVALE interconnector loading chart: 320 MW → 710 MW\n- ISO-A3 inspection findings and rectification plan",
      "priority": 3
    }
  }
}
```

### Total: 33 frames (~32 rendered frames + f000b empty wait), ~95 seconds runtime

---

### Phase 7: Precursor Reveal (frames f028–f032, ~16s) — the headline win

The purpose of this phase is to leave the audience with the most
powerful message of the demo: **GridIQ saw it coming.** The presenter
scrolls back to the situation list, clicks the precursor card, and
GridIQ replays what it knew — 37 minutes before the trip.

#### f028 — Scroll back, highlight precursor card
```jsonc
{
  "id": "f028",
  "chapter": "The precursor",
  "narration": "One last thing. Remember the INVESTIGATE card from 13:55 — the one I said we'd come back to. Watch this.",
  "transition_ms": 1500,
  "patch": {
    "agent.set_active": { "agent": "investigator" }
  }
}
```
> Implementation note: this frame switches the active agent back to
> the Investigator (which causes the situation list to be in focus on
> the right panel). If a `panel.situations.focus` op is added later,
> use it here to highlight the `ngm-pre-1` card visually.

#### f029 — User asks about the precursor
```jsonc
{
  "id": "f029",
  "narration": "The operator asks the obvious follow-up.",
  "transition_ms": 600,
  "patch": {
    "chat.append": {
      "agent": "investigator",
      "role": "user",
      "text": "What was the 13:55 INVESTIGATE on REDCLIFF? Same station, just before the trip."
    }
  }
}
```

#### f030 — Investigator: pattern_history tool call
```jsonc
{
  "id": "f030",
  "narration": "Tool call — the agent pulls the pattern detail for the precursor situation.",
  "transition_ms": 200,
  "patch": {
    "chat.append": {
      "agent": "investigator",
      "role": "assistant",
      "agent_name": "Investigator",
      "text": "",
      "tool_calls": [
        {
          "id": "tc-pre-1",
          "name": "pattern_history",
          "arguments": {
            "equipment": "REDCLIFF_PS.BUS.220KV_A",
            "window_start": "2025-06-17 13:50",
            "window_end": "2025-06-17 14:00"
          },
          "status": "running"
        }
      ]
    }
  }
}
```

#### f031 — pattern_history result
```jsonc
{
  "id": "f031",
  "narration": "There it is. A 15-second voltage transient on the same busbar that just tripped. Dipped to 198.4 kV — nearly 10 percent depression — and recovered. No alarm fired because the duration was below the sustained-low threshold. Blink and you would miss it.",
  "transition_ms": 1500,
  "patch": {
    "chat.update_tool": {
      "agent": "investigator",
      "id": "tc-pre-1",
      "status": "complete",
      "duration_ms": 1500,
      "result": "{\"columns\":[\"timestamp_aest\",\"TagId\",\"Value\",\"prev_val\",\"event\"],\"rows\":[[\"2025-06-17 13:55:30\",\"REDCLIFF_PS.BUS.220KV_A.KV\",198.4,220.1,\"DIP -9.9%\"],[\"2025-06-17 13:55:45\",\"REDCLIFF_PS.BUS.220KV_A.KV\",220.0,198.4,\"RECOVER +10.9%\"]],\"pattern\":\"transient_kv_dip\",\"duration_s\":15,\"depth_pct\":9.9,\"alarm_raised\":false,\"sub_threshold_reason\":\"sustained-low alarm requires >60s below 90% nominal\",\"gridiq_advisory\":\"Insulation degradation pattern \u2014 recommend thermal scan of all bay equipment connected to 220 kV A busbar, prioritising bus section isolators (ISO-A1, ISO-A2, ISO-A3, ISO-A4).\"}"
    }
  }
}
```

#### f032 — Closing analysis (streamed)
```jsonc
{
  "id": "f032",
  "narration": "The agent draws the line for the operator. Ⓢ GridIQ flagged this 37 minutes before the trip and recommended a thermal scan of the bus section isolators — ISO-A3 was on that list. If a maintenance crew had been dispatched at 13:56, the units could have been switched to the B busbar before the flashover, and the 430 MW loss would not have happened.",
  "transition_ms": 200,
  "patch": {
    "chat.append": {
      "agent": "investigator",
      "role": "assistant",
      "agent_name": "Investigator",
      "text": "At **13:55:30** — **37 minutes before the busbar trip** — the 220 kV A busbar voltage at REDCLIFF_PS dipped from 220.1 kV to 198.4 kV (9.9% depression) and recovered after **15 seconds**. No SCADA alarm was raised because the duration was below the sustained-low threshold (60 s).\n\nGridIQ flagged the transient as INVESTIGATE-grade based on the dip depth and shape — consistent with early-stage insulation breakdown on a connected primary plant element. The recommendation issued at 13:56 was a thermal scan of all bay equipment on the 220 kV A busbar, prioritising bus section isolators (ISO-A1 through ISO-A4).\n\n**ISO-A3 — the asset that flashed over at 14:32 — was on that recommended scan list.**\n\nHad the precursor advisory been actioned, the trip and the 430 MW generation loss were preventable."
    }
  }
}
```

---

## 8. Data Search Dock Agent — Canned Replies

Agent ID: `data_search`. Same pattern as existing — keyword match on
lowercased prompt, first match wins, empty-string match is fallback.

### Welcome Message

```markdown
**Data Search agent — ready.**

I can pull operational data for the REDCLIFF_PS event and related stations:

- Alarm queries (`find_alarms` — by station + time window)
- SCADA telemetry snapshots (`find_scada` — any TagId)
- Frequency excursion profiles (`frequency_summary` — per region)
- Historical pattern data (`pattern_history` — by equipment)

Try *"Show REDCLIFF alarms around 14:32"* or *"Frequency profile for SER region"*.
```

### Reply 1 — match: `redcliff`

```markdown
**REDCLIFF_PS — event window 14:30–14:45 AEST**

**Alarm log** (6 alarms in 16 seconds):

| Time (AEST)   | Equipment              | Label     | Description                                            | Pri |
|---------------|------------------------|-----------|--------------------------------------------------------|-----|
| 14:32:14      | REDCLIFF_PS.CB.031     | CB TRIP   | REDCLIFF_PS 220KV CB-031 TRIPPED                       | 1   |
| 14:32:14      | REDCLIFF_PS.CB.041     | CB TRIP   | REDCLIFF_PS 220KV CB-041 TRIPPED                       | 1   |
| 14:32:14      | REDCLIFF_PS.BUS.220KV_A| BUS DIFF  | REDCLIFF_PS 220KV A BUSBAR DIFFERENTIAL PROTECTION OPERATED | 1 |
| 14:32:14      | REDCLIFF_PS.ISO.A3     | EARTH FLT | REDCLIFF_PS BUS SECTION ISOLATOR ISO-A3 EARTH FAULT DETECTED | 1 |
| 14:32:18      | REDCLIFF_PS.GEN.3      | PROT OP   | REDCLIFF_PS GEN 3 REVERSE POWER PROTECTION OPERATED    | 1   |
| 14:32:22      | REDCLIFF_PS.GEN.4      | PROT OP   | REDCLIFF_PS GEN 4 UNDER-FREQUENCY PROTECTION OPERATED  | 1   |

**SCADA snapshot** (post-event):

```
TagId                         Value    Prev     Drop
REDCLIFF_PS.GEN.3.MW           0.0   241.0   100.0%
REDCLIFF_PS.GEN.4.MW           0.0   189.0   100.0%
REDCLIFF_PS.GEN.1.MW         248.0   248.0   stable
REDCLIFF_PS.GEN.2.MW       offline       –        –
REDCLIFF_PS.BUS.220KV_A.KV    0.0   220.1   100.0%
REDCLIFF_PS.BUS.220KV_B.KV  217.8   220.0     1.0%
REDCLIFF_PS.TX.T1.MW        248.0   539.4    54.0%
```

Total generation lost: **430 MW** (Units 3 + 4). Unit 1 stable on B busbar.
```

### Reply 2 — match: `frequency`

```markdown
**NGM frequency — SER region, 14:30–14:40 AEST**

| Metric                        | Value       |
|-------------------------------|-------------|
| Pre-event frequency           | 50.02 Hz    |
| Nadir                         | 49.68 Hz    |
| Time below SOFEB (49.75 Hz)   | 3.8 s       |
| Time below SOFB (49.85 Hz)    | 8.2 s       |
| Recovery to SOFB              | ~100 s      |
| Post-recovery frequency       | 49.93 Hz    |
| FRS contingency raise        | 430 MW      |
| GFS containment band          | 47–52 Hz    |
| **GFS met?**                  | **Yes**     |

Adjacent regions:
- NER (North-East Region): 49.82 Hz min — no band breach
- WER (West Region): 49.85 Hz min — at SOFB boundary, no breach
- NOR (North Region): 49.88 Hz min — within SOFB

Frequency was restored by FRS contingency raise dispatched across the NGM within 6 seconds of the event.
```

### Reply 3 — match: `alarm`

```markdown
**Alarm sequence — REDCLIFF_PS, 14:32:14 → 14:32:30 AEST**

6 alarms received in 16 seconds. Sequence:

1. **14:32:14** — `CB TRIP` — REDCLIFF_PS 220KV CB-031 TRIPPED (Pri 1)
2. **14:32:14** — `CB TRIP` — REDCLIFF_PS 220KV CB-041 TRIPPED (Pri 1)
3. **14:32:14** — `BUS DIFF` — REDCLIFF_PS 220KV A BUSBAR DIFFERENTIAL PROTECTION OPERATED (Pri 1)
4. **14:32:14** — `EARTH FLT` — REDCLIFF_PS BUS SECTION ISOLATOR ISO-A3 EARTH FAULT DETECTED (Pri 1)
5. **14:32:18** — `PROT OP` — REDCLIFF_PS GEN 3 REVERSE POWER PROTECTION OPERATED (Pri 1)
6. **14:32:22** — `PROT OP` — REDCLIFF_PS GEN 4 UNDER-FREQUENCY PROTECTION OPERATED (Pri 1)

**Causal chain:** ISO-A3 inter-phase flashover → bus differential protection (Scheme A) → CB-031 + CB-041 open → GEN.3 reverse-power trip → GEN.4 under-frequency trip.

No protection mis-operation detected. All protection elements operated within design parameters.
```

### Reply 4 — match: `scada`

```markdown
**SCADA snapshot — REDCLIFF_PS post-event**

```
TagId                          Value    Prev     Change
REDCLIFF_PS.GEN.3.MW            0.0   241.0   -241.0 (100%) TRIP
REDCLIFF_PS.GEN.4.MW            0.0   189.0   -189.0 (100%) TRIP
REDCLIFF_PS.GEN.1.MW          248.0   248.0      0.0  (0%)  STABLE
REDCLIFF_PS.GEN.2.MW        offline       –         –       MAINT
REDCLIFF_PS.BUS.220KV_A.KV     0.0   220.1   -220.1 (100%) COLLAPSED
REDCLIFF_PS.BUS.220KV_B.KV   217.8   220.0     -2.2  (1%)  STABLE
REDCLIFF_PS.TX.T1.MW          248.0   539.4   -291.4 (54%)  REDUCED
REDCLIFF_PS.TX.T1.MVAR         38.5    81.0    -42.5 (52%)  REDUCED
```

Notes:
- T1 load dropped from 539 MW to 248 MW — now carrying only Unit 1 output via B busbar.
- B busbar voltage at 217.8 kV (99% of nominal) — healthy.
- A busbar collapsed to 0 kV — isolated by protection.
```

### Reply 5 — match: `northvale`

```markdown
**NORTHVALE_SS — interconnector response**

**Line loading:**

| Metric                          | Pre-event   | Post-event  | Change       |
|---------------------------------|-------------|-------------|--------------|
| LINE.REDCLIFF_1.MW              | 320 MW      | 710 MW      | +390 MW      |
| LINE.REDCLIFF_1 thermal loading | 52%         | 89%         | +37 pp       |
| BUS.220KV_A.KV                  | 219.8 kV    | 214.2 kV    | -5.6 kV (2.5%) |

**Alarms:**
- 14:32:48 — `KV LOW` — NORTHVALE 220KV BUS A VOLTAGE LOW 214.2KV (Pri 3)
- 14:35:00 — `THERMAL` — NORTHVALE 220KV LINE REDCLIFF NO.1 LOADING 89% THERMAL LIMIT (Pri 2)

No protection operated at NORTHVALE. The interconnector loading increase is a consequential response to the 430 MW generation loss at REDCLIFF_PS. The line remains within its emergency thermal rating (100% = ~800 MW).

**Recommendation:** Monitor 5-minute trend. If loading exceeds 95%, initiate generation redispatch.
```

### Reply 6 — match: `history`

```markdown
**REDCLIFF_PS — protection event history (12 months)**

**GEN.3 events:**

| Date       | Time  | Event                                        | MW Impact |
|------------|-------|----------------------------------------------|-----------|
| 2025-06-17 | 14:32 | Reverse power protection — current event      | -241 MW   |
| 2025-12-14 | 03:18 | Excitation system fault — AVR runback          | -80 MW    |
| 2025-08-03 | 10:00 | Scheduled insulation resistance test — planned | 0 MW      |

**GEN.4 events:**

| Date       | Time  | Event                                        | MW Impact |
|------------|-------|----------------------------------------------|-----------|
| 2025-06-17 | 14:32 | Under-frequency protection — current event    | -189 MW   |
| 2025-11-20 | 16:45 | Governor instability — AGC removal            | 0 MW      |

**ISO-A3 events:**

| Date       | Event                                         |
|------------|-----------------------------------------------|
| 2025-06-17 | Inter-phase flashover — **first recorded failure since commissioning (2014)** |

No prior fault history on ISO-A3. OEM has been notified for root cause analysis of the insulation failure.
```

### Reply 7 — match: `wentworth`

```markdown
**WENTWORTH_SS — transformer T2 trip**

| Metric                    | Value                          |
|---------------------------|--------------------------------|
| Equipment                 | 132/66 kV Transformer T2       |
| Rated capacity            | 60 MVA                         |
| Pre-event loading         | 38 MW (63% rated)              |
| Post-redistribution load  | 52.4 MW (87% rated)            |
| Overcurrent pickup        | 50 MW                          |
| Trip time                 | 14:40:12 AEST                  |
| Time after REDCLIFF event | +8 minutes                     |
| Cause                     | Overcurrent (load redistribution) |
| Equipment fault?          | No — tested OK                 |
| Return to service         | 15:05 AEST (25 min outage)     |
| Load lost                 | 12.4 MW (downstream 66 kV)     |

**Alarms:**
- 14:40:12 — `PROT OP` — WENTWORTH_SS 132KV TX T2 OVERCURRENT PROTECTION OPERATED (Pri 1)
- 14:40:12 — `TX TRIP` — WENTWORTH_SS 132/66KV TRANSFORMER T2 TRIPPED (Pri 1)

The overcurrent was caused by load redistribution following the REDCLIFF_PS event, not by an equipment fault. T2 was tested and returned to service at 15:05.
```

### Reply 8 — match: `""` (fallback)

```markdown
I can pull alarms, SCADA snapshots, frequency summaries, or historical pattern data for any station in the SER region. Try:

- *"Show REDCLIFF alarms around 14:32"*
- *"What's the NGM frequency profile for SER?"*
- *"NORTHVALE interconnector loading"*
- *"GEN.3 protection history"*
- *"WENTWORTH transformer details"*
- *"SCADA snapshot for REDCLIFF"*
```

---

## 9. Implementation Plan (when ready)

### Step 1: Add `panel.situations.classify` frame patch op
- **scenarioSchema.ts**: Add `SituationsClassifyOp` and `SituationClassificationEntry` types. Add `"panel.situations.classify"` to `FramePatch`.
- **applyPatch.ts**: Handle `panel.situations.classify` — write entries into `useSituationStore.getState().classifications` with `status: "ready"`.

### Step 2: Kiosk-gate the classify API call
- **SituationCard.tsx**: Wrap the `useEffect` that calls `triggerClassify` with `if (IS_KIOSK) return;`.

### Step 3: Add bootstrap classifications support
- **scenarioSchema.ts**: Add `classifications?: Record<string, SituationClassificationEntry>` to `KioskBootstrap`.
- **kioskBootstrap.ts**: Read `kiosk_bootstrap.classifications` and write into `useSituationStore.getState().classifications`.

### Step 4: Create `ngm_busbar_trip.json`
- New file at `app/frontend/src/demo/scenarios/ngm_busbar_trip.json`
- Contains: `kiosk_bootstrap` (agents, dock agent, classifications) + ~35 frames per §7 above.
- All station names, equipment IDs, SCADA tags, and telemetry values are fictional per this spec.

### Step 5: Register the new scenario
- **scenarios/index.ts**: Add import + export for `ngm_busbar_trip`.
- If scenario picker exists, add to the list.

### Step 6: Update placeholder.json
- Add `classifications` to existing `kiosk_bootstrap` for the 4 current situations (CAL_C_PS, LIAPOOTA, etc.) so those also render properly in kiosk mode.

---

## 10. What This Demo Shows (Presenter Talking Points)

1. **Automated situation detection** — GridIQ scans thousands of alarm/SCADA signals across the NGM and surfaces the events that matter. The operator doesn't have to hunt.

2. **GOR-aligned classification** — Every situation is automatically classified as credible, non-credible, or non-event with a cited GOR clause and written rationale. This is the exact analysis NGA performs for reportable grid incident reports — done in seconds instead of days.

3. **Cascading impact awareness** — The 4 situations aren't isolated. GridIQ shows the chain: REDCLIFF busbar fault → NORTHVALE thermal stress → BANKSIA governor response → WENTWORTH transformer overload. An operator sees the full picture, not just the loudest alarm.

4. **Topology context** — The map shows affected equipment in context: which generators tripped, which busbars are de-energised, which interconnectors are stressed. Live telemetry values are right there.

5. **AI-driven investigation** — The Investigator agent pulls alarms and SCADA, correlates the sequence, identifies the root cause (ISO-A3 flashover → busbar diff protection → dual unit trip), and summarises in seconds.

6. **Actionable response** — The Dispatcher produces prioritised operator actions with specific procedures, contacts, and regulatory requirements (market notice, incident report). Not generic advice — concrete next steps.

7. **On-demand data access** — The Data Search agent lets the operator dig deeper at any point: frequency profiles, interconnector loading, historical patterns, transformer test results. No context-switching to separate SCADA systems.

8. **All four classification outcomes visible** — The demo deliberately includes a credible (WENTWORTH transformer), non-credible (REDCLIFF dual-unit), and two non-event classifications (NORTHVALE loading, BANKSIA governor response). This shows the system's judgment isn't binary.

---

## 11. Value-Add Narration Catalog

This section is the **presenter's checklist**. Every value-add the demo
exists to communicate has a row here, mapped to the exact frame where
it lands, the exact line the presenter speaks, and the on-screen
evidence that backs the claim. If a row's evidence isn't visible when
the line is spoken, the demo is broken — fix the frame.

The wins are grouped by category. **Win 1** and **Win 2** are the
flagship wins (see §3); the others are supporting value-adds that
should be acknowledged but not dwelled on.

### Win 1 — Correct classification from the first scan (3h20m head start)

| # | Frame | Presenter line (verbatim) | On-screen evidence |
|---|-------|---------------------------|--------------------|
| 1.1 | f000c | "Five situations detected, ranked by severity. One CRITICAL, one MAJOR, one SERIOUS, and — importantly — two INVESTIGATE-grade items." | Situation list panel populated with 5 ranked cards, REDCLIFF CRITICAL at the top. |
| 1.2 | f000e | "The CRITICAL is non-credible — two units lost from a single busbar fault, that exceeds the single-element boundary." | REDCLIFF card now shows `non_credible` badge with GOR 5.2.3A(c) citation and rationale text. |
| 1.3 | f003 | "Notice the loudest first-impression alarm here would be 'CB-031 has tripped' — a single circuit breaker. … But the agent sees the bus differential trip and the earth fault on ISO-A3 in the same burst — the real story. In a comparable grid incident, the RTO told the grid authority it was a different breaker; that advice was corrected three hours and twenty minutes later." | `find_alarms` result table visible — 6 alarm rows including BUS DIFF and ISO-A3 EARTH FLT. |
| 1.4 | f017 (token) | "Root cause: inter-phase flashover on ISO-A3." | The streamed text in the investigator chat reaches the **Root cause** line. |
| 1.5 | f023 | "Action one: confirm the busbar is isolated and inspect the suspect isolator." | Priority Action #1 card lists ISO-A3 explicitly in the guide steps. |

**Headline number to land in the audience's head:** *3 hours 20 minutes
saved on getting the classification right.*

### Win 2 — Precursor detection 37 minutes ahead

| # | Frame | Presenter line (verbatim) | On-screen evidence |
|---|-------|---------------------------|--------------------|
| 2.1 | f000c | "The first INVESTIGATE card is dated 13:55, before the main event. We'll come back to it." | The `ngm-pre-1` card visible at bottom of situations list with timestamp `2025-06-17 13:55`. |
| 2.2 | f028 | "One last thing. Remember the INVESTIGATE card from 13:55 — the one I said we'd come back to. Watch this." | Active agent switches to Investigator; situations list back in focus. |
| 2.3 | f031 | "There it is. A 15-second voltage transient on the same busbar that just tripped. Dipped to 198.4 kV — nearly 10 percent depression — and recovered. No alarm fired because the duration was below the sustained-low threshold. Blink and you would miss it." | `pattern_history` tool result table shows two SCADA rows: 13:55:30 dip, 13:55:45 recovery. |
| 2.4 | f032 | "GridIQ flagged this 37 minutes before the trip and recommended a thermal scan of the bus section isolators — ISO-A3 was on that list." | Investigator's streamed assistant message names ISO-A3 in bold and states the trip was preventable. |

**Headline number to land in the audience's head:** *37 minutes of
warning, a 430 MW preventable loss.*

### Supporting wins (mention, don't dwell)

| # | Category | Frame | Presenter line (verbatim) | On-screen evidence |
|---|----------|-------|---------------------------|--------------------|
| S.1 | Speed | f000a | "GridIQ runs continuously. Every five minutes it sweeps every alarm, every SCADA tag, and every frequency reading across the NGM." | Scan progress indicator starts. |
| S.2 | Speed | f005 | "Confirmed. Unit 3 dropped from 241 to zero, Unit 4 from 189 to zero — 430 MW gone." | `find_scada` result table fully rendered. |
| S.3 | Auditable AI | f002 | "The agent doesn't guess. It calls a tool. … every step is auditable." | Tool call card showing `find_alarms`, arguments, running spinner. |
| S.4 | Cascading awareness | f000f | "And look at the NORTHVALE link out to the right: 710 MW, 89% thermal. The grid is compensating, hard." | Topology link from REDCLIFF to NORTHVALE highlighted with 710 MW label. |
| S.5 | Cascading awareness | f024 | "Action two: monitor the NORTHVALE interconnector. … if loading creeps past 95%, the operator needs a redispatch plan ready before automatic protection trips the line." | Priority Action #2 card visible. |
| S.6 | Procedural nuance | f025 | "The dispatcher distinguishes Unit 4 (under-frequency trip … safe to restart) from Unit 3 (reverse-power trip … needs an insulation test first). That nuance is in PROC-GEN-RESYNC; the agent applies it." | Priority Action #3 card guide steps differentiate Unit 3 vs Unit 4 handling. |
| S.7 | Regulatory automation | f026 | "Action four: the market notice. Required within 30 minutes of a non-credible contingency. The dispatcher has drafted the substance … and given the operator the 15:02 deadline." | Priority Action #4 card with drafted notice text and 15:02 deadline. |
| S.8 | Regulatory automation | f027 | "The agent has pre-listed every artefact the report needs … The operator's job is to attach them, not assemble them." | Priority Action #5 card listing 6 attachment categories. |
| S.9 | GOR fluency | f000e | "Each classification cites the GOR clause and includes a written rationale." | All 5 situation cards now display GOR citations beneath the classification badges. |
| S.10 | One-pane operator surface | f001 | "The operator already knows two units dropped because GridIQ surfaced it on the situation card. They're now asking 'why', not 'what'." | Operator's chat message visible alongside the still-populated situation panel. |

### Presenter's pre-flight check

Before going live, walk the demo end-to-end and confirm:

- [ ] At f000c the precursor card is **visible** (bottom of list) and the line "We'll come back to it" is delivered with eye contact, not as a throwaway.
- [ ] At f000e the audience sees a `non_credible` badge appear on REDCLIFF — pause for it to register before reading the rationale.
- [ ] At f003 the precedent comparison ("3 hours 20 minutes later") is delivered slowly. This is the headline of Win 1.
- [ ] At f028–f032 the precursor reveal is given **at least 16 seconds of stage time**. Do not rush it. This is the headline of Win 2.
- [ ] At f032 the line "ISO-A3 was on that list" is the closing punchline. Leave a beat of silence after it.

If any checkbox fails on rehearsal, fix the frame before showing the demo to anyone.
