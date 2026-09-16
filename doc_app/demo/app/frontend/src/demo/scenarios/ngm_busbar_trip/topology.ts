/**
 * Topology graph payload for the NGM busbar trip demo scenario.
 *
 * Module role:
 *   Exports the full topology graph centered on MARRABEL_NX, including
 *   7 stations (1 center + 3 one-hop neighbors + 3 two-hop neighbors),
 *   their equipment, live telemetry, and inter-station links.
 *
 * Key collaborators:
 *   - phases/03_topology.ts — uses TOPOLOGY_PAYLOAD in the topology.set op.
 *
 * All station names, equipment IDs, SCADA tags, and telemetry values are
 * fictional. See DEMO_SCENARIO_SPEC.md §6 for the design rationale.
 */

import type { TopologySetOp } from "../../scenarioSchema";

/** Complete topology.set op payload — center station + overlay + graph. */
export const TOPOLOGY_PAYLOAD: TopologySetOp = {
  station: "MARRABEL_NX",
  overlay: {
    equipmentIds: ["MARRABEL_NX::G3", "MARRABEL_NX::G4"],
    severity: "CRITICAL",
  },
  graph: {
    center: {
      station: "MARRABEL_NX",
      region: "EHR",
      equipment: [
        {
          equipment: "MARRABEL_NX::G3",
          scada_composite_id: "MARRABEL_NX::G3",
          cim_classes: ["SynchronousMachine"],
          nominal_kv: 15.75,
          mw_max: 250,
          mva_rated: 295,
          live: {
            mw: 0.0, mvar: 0.0, kv: 14.8, hz: 49.71,
            ts: "2026-02-12T11:15:18+10:00",
            tags: { MW: "MARRABEL_NX::G3::pwr_real" },
          },
        },
        {
          equipment: "MARRABEL_NX::G4",
          scada_composite_id: "MARRABEL_NX::G4",
          cim_classes: ["SynchronousMachine"],
          nominal_kv: 15.75,
          mw_max: 250,
          mva_rated: 295,
          live: {
            mw: 0.0, mvar: 0.0, kv: 14.6, hz: 49.71,
            ts: "2026-02-12T11:15:22+10:00",
            tags: { MW: "MARRABEL_NX::G4::pwr_real" },
          },
        },
        {
          equipment: "MARRABEL_NX::G1",
          scada_composite_id: "MARRABEL_NX::G1",
          cim_classes: ["SynchronousMachine"],
          nominal_kv: 15.75,
          mw_max: 250,
          mva_rated: 295,
          live: {
            mw: 248.0, mvar: 38.5, kv: 15.7, hz: 49.93,
            ts: "2026-02-12T11:16:55+10:00",
            tags: { MW: "MARRABEL_NX::G1::pwr_real" },
          },
        },
        {
          equipment: "MARRABEL_NX::G2",
          scada_composite_id: "MARRABEL_NX::G2",
          cim_classes: ["SynchronousMachine"],
          nominal_kv: 15.75,
          mw_max: 250,
          mva_rated: null,
          live: null,
        },
        {
          equipment: "MARRABEL_NX::B275-1",
          scada_composite_id: "MARRABEL_NX::B275-1",
          cim_classes: ["BusbarSection"],
          nominal_kv: 220,
          mw_max: null,
          mva_rated: null,
          live: { kv: 0.0, hz: 49.71, ts: "2026-02-12T11:15:14+10:00" },
        },
        {
          equipment: "MARRABEL_NX::B275-2",
          scada_composite_id: "MARRABEL_NX::B275-2",
          cim_classes: ["BusbarSection"],
          nominal_kv: 220,
          mw_max: null,
          mva_rated: null,
          live: { kv: 217.8, hz: 49.93, ts: "2026-02-12T11:16:55+10:00" },
        },
        /* Bus section isolators on Bus 275-1. Authored explicitly so the
           precursor-reveal overlay (07_precursor.ts f032) has equipment
           rows to spotlight when GridIQ names DS-275-13 as the asset that
           flashed over and DS-275-11/12/14 as the rest of the recommended
           thermal-scan list. The flashover unit (DS-275-13) carries the
           CRITICAL-state ts; the others carry pre-event ts so they read
           as adjacent plant rather than as participants in the trip. */
        {
          equipment: "MARRABEL_NX::DS-275-11",
          scada_composite_id: "MARRABEL_NX::DS-275-11",
          cim_classes: ["DisconnectorSwitch"],
          nominal_kv: 275,
          mw_max: null,
          mva_rated: null,
          live: { ts: "2026-02-12T11:00:00+10:00" },
        },
        {
          equipment: "MARRABEL_NX::DS-275-12",
          scada_composite_id: "MARRABEL_NX::DS-275-12",
          cim_classes: ["DisconnectorSwitch"],
          nominal_kv: 275,
          mw_max: null,
          mva_rated: null,
          live: { ts: "2026-02-12T11:00:00+10:00" },
        },
        {
          equipment: "MARRABEL_NX::DS-275-13",
          scada_composite_id: "MARRABEL_NX::DS-275-13",
          cim_classes: ["DisconnectorSwitch"],
          nominal_kv: 275,
          mw_max: null,
          mva_rated: null,
          live: { ts: "2026-02-12T11:15:14+10:00" },
        },
        {
          equipment: "MARRABEL_NX::DS-275-14",
          scada_composite_id: "MARRABEL_NX::DS-275-14",
          cim_classes: ["DisconnectorSwitch"],
          nominal_kv: 275,
          mw_max: null,
          mva_rated: null,
          live: { ts: "2026-02-12T11:00:00+10:00" },
        },
        {
          equipment: "MARRABEL_NX::TX-T1",
          scada_composite_id: "MARRABEL_NX::TX-T1",
          cim_classes: ["PowerTransformer"],
          nominal_kv: 220,
          mw_max: 500,
          mva_rated: 600,
          live: {
            mw: 248.0, mvar: 38.5, kv: 217.8,
            ts: "2026-02-12T11:16:55+10:00",
          },
        },
      ],
      live_summary: {
        mw_output: 248.0,
        mw_cap: 1000,
        freq: 49.93,
        ts: "2026-02-12T11:16:55+10:00",
      },
    },
    neighbors: [
      /* ── 1-hop: KETTERING_NX (switching station, 275 kV interconnector) ── */
      {
        station: "KETTERING_NX",
        region: "EHR",
        hops: 1,
        path_classes: ["ACLineSegment"],
        equipment: [
          {
            equipment: "KETTERING_NX::B275-1",
            scada_composite_id: "KETTERING_NX::B275-1",
            cim_classes: ["BusbarSection"],
            nominal_kv: 220,
            mw_max: null,
            mva_rated: null,
            live: { kv: 214.2, hz: 49.93, ts: "2026-02-12T11:16:55+10:00" },
          },
        ],
        live_summary: { mw_output: null, mw_cap: null, freq: 49.93, ts: "2026-02-12T11:16:55+10:00" },
      },
      /* ── 1-hop: GLENRIDGE_NX (hydro, 2 × 180 MW) ── */
      {
        station: "GLENRIDGE_NX",
        region: "EHR",
        hops: 1,
        path_classes: ["ACLineSegment"],
        equipment: [
          {
            equipment: "GLENRIDGE_NX::G1",
            scada_composite_id: "GLENRIDGE_NX::G1",
            cim_classes: ["SynchronousMachine"],
            nominal_kv: 15.75,
            mw_max: 180,
            mva_rated: 210,
            live: { mw: 178.0, mvar: 28.0, kv: 15.6, ts: "2026-02-12T11:16:55+10:00", tags: { MW: "GLENRIDGE_NX::G1::pwr_real" } },
          },
          {
            equipment: "GLENRIDGE_NX::G2",
            scada_composite_id: "GLENRIDGE_NX::G2",
            cim_classes: ["SynchronousMachine"],
            nominal_kv: 15.75,
            mw_max: 180,
            mva_rated: 210,
            live: { mw: 178.0, mvar: 27.0, kv: 15.6, ts: "2026-02-12T11:16:55+10:00", tags: { MW: "GLENRIDGE_NX::G2::pwr_real" } },
          },
        ],
        live_summary: { mw_output: 356.0, mw_cap: 360, freq: 49.93, ts: "2026-02-12T11:16:55+10:00" },
      },
      /* ── 1-hop: OAKBANK_NX (switching station, 132 kV sub-transmission) ── */
      {
        station: "OAKBANK_NX",
        region: "EHR",
        hops: 1,
        path_classes: ["ACLineSegment", "PowerTransformer"],
        equipment: [
          {
            equipment: "OAKBANK_NX::B132-1",
            scada_composite_id: "OAKBANK_NX::B132-1",
            cim_classes: ["BusbarSection"],
            nominal_kv: 132,
            mw_max: null,
            mva_rated: null,
            live: { kv: 129.4, hz: 49.93, ts: "2026-02-12T11:16:55+10:00" },
          },
          {
            equipment: "OAKBANK_NX::TX-T2",
            scada_composite_id: "OAKBANK_NX::TX-T2",
            cim_classes: ["PowerTransformer"],
            nominal_kv: 132,
            mw_max: 60,
            mva_rated: 75,
            live: { mw: 0.0, kv: 129.4, ts: "2026-02-12T11:23:12+10:00" },
          },
        ],
        live_summary: { mw_output: null, mw_cap: null, freq: 49.93, ts: "2026-02-12T11:16:55+10:00" },
      },
      /* ── 2-hop: BIRRALEE_NX (inter-regional terminus, 330 kV, NER region) ── */
      {
        station: "BIRRALEE_NX",
        region: "NER",
        hops: 2,
        path_classes: ["ACLineSegment", "ACLineSegment"],
        parent_station: "KETTERING_NX",
        equipment: [
          {
            equipment: "BIRRALEE_NX::B330-1",
            scada_composite_id: "BIRRALEE_NX::B330-1",
            cim_classes: ["BusbarSection"],
            nominal_kv: 330,
            mw_max: null,
            mva_rated: null,
            live: { kv: 326.4, hz: 49.93, ts: "2026-02-12T11:16:55+10:00" },
          },
          {
            equipment: "BIRRALEE_NX::TX-AT1",
            scada_composite_id: "BIRRALEE_NX::TX-AT1",
            cim_classes: ["PowerTransformer"],
            nominal_kv: 330,
            mw_max: 750,
            mva_rated: 850,
            live: { mw: 698.0, mvar: 112.0, kv: 326.4, ts: "2026-02-12T11:16:55+10:00", tags: { MW: "BIRRALEE_NX::TX-AT1::pwr_real" } },
          },
        ],
        live_summary: { mw_output: null, mw_cap: null, freq: 49.93, ts: "2026-02-12T11:16:55+10:00" },
      },
      /* ── 2-hop: ELDERMOUNT_NX (wind farm, 96 MW aggregated) ── */
      {
        station: "ELDERMOUNT_NX",
        region: "EHR",
        hops: 2,
        path_classes: ["ACLineSegment", "ACLineSegment"],
        parent_station: "GLENRIDGE_NX",
        equipment: [
          {
            equipment: "ELDERMOUNT_NX::B132-1",
            scada_composite_id: "ELDERMOUNT_NX::B132-1",
            cim_classes: ["BusbarSection"],
            nominal_kv: 132,
            mw_max: null,
            mva_rated: null,
            live: { kv: 130.8, hz: 49.93, ts: "2026-02-12T11:16:55+10:00" },
          },
          {
            equipment: "ELDERMOUNT_NX::WTG-AGG",
            scada_composite_id: "ELDERMOUNT_NX::WTG-AGG",
            cim_classes: ["AsynchronousMachine"],
            nominal_kv: 0.69,
            mw_max: 96,
            mva_rated: 105,
            live: { mw: 71.4, mvar: 8.2, kv: 0.69, ts: "2026-02-12T11:16:55+10:00", tags: { MW: "ELDERMOUNT_NX::WTG-AGG::pwr_real" } },
          },
        ],
        live_summary: { mw_output: 71.4, mw_cap: 96, freq: 49.93, ts: "2026-02-12T11:16:55+10:00" },
      },
      /* ── 2-hop: KILBARRA_DS (distribution sub, 66/22 kV, downstream load) ── */
      {
        station: "KILBARRA_DS",
        region: "EHR",
        hops: 2,
        path_classes: ["ACLineSegment", "PowerTransformer", "ACLineSegment"],
        parent_station: "OAKBANK_NX",
        equipment: [
          {
            equipment: "KILBARRA_DS.BUS.66KV_A",
            scada_composite_id: "KILBARRA_DS.BUS.66KV_A",
            cim_classes: ["BusbarSection"],
            nominal_kv: 66,
            mw_max: null,
            mva_rated: null,
            live: { kv: 0.0, hz: 49.93, ts: "2026-02-12T11:23:12+10:00" },
          },
          {
            equipment: "KILBARRA_DS.LOAD.FEEDER_F4",
            scada_composite_id: "KILBARRA_DS.LOAD.FEEDER_F4",
            cim_classes: ["EnergyConsumer"],
            nominal_kv: 22,
            mw_max: 18,
            mva_rated: 20,
            live: { mw: 0.0, mvar: 0.0, kv: 0.0, ts: "2026-02-12T11:23:12+10:00" },
          },
        ],
        live_summary: { mw_output: null, mw_cap: null, freq: 49.93, ts: "2026-02-12T11:23:12+10:00" },
      },
    ],
    links: [
      {
        from: "MARRABEL_NX", to: "KETTERING_NX",
        path_classes: ["ACLineSegment"], hops: 1, nominal_kv: 220,
        lines: [{ line_name: "KTG-01", line_mrid: "ln-rc-nv-1", near_terminal: "MARRABEL_NX::B275-2", far_terminal: "KETTERING_NX::B275-1", nominal_kv: 275, via_class: "ACLineSegment" }],
      },
      {
        from: "MARRABEL_NX", to: "GLENRIDGE_NX",
        path_classes: ["ACLineSegment"], hops: 1, nominal_kv: 220,
        lines: [{ line_name: "GLN-01", line_mrid: "ln-rc-bk-1", near_terminal: "MARRABEL_NX::B275-2", far_terminal: "GLENRIDGE_NX::B275-1", nominal_kv: 275, via_class: "ACLineSegment" }],
      },
      {
        from: "MARRABEL_NX", to: "OAKBANK_NX",
        path_classes: ["ACLineSegment", "PowerTransformer"], hops: 1, nominal_kv: 220,
        lines: [{ line_name: "OAK-01", line_mrid: "ln-rc-ww-1", near_terminal: "MARRABEL_NX::B275-2", far_terminal: "OAKBANK_NX::B132-1", nominal_kv: 275, via_class: "ACLineSegment" }],
      },
      {
        from: "KETTERING_NX", to: "BIRRALEE_NX",
        path_classes: ["ACLineSegment"], hops: 1, nominal_kv: 330,
        lines: [{ line_name: "BIR-01", line_mrid: "ln-nv-hb-1", near_terminal: "KETTERING_NX::B275-1", far_terminal: "BIRRALEE_NX::B330-1", nominal_kv: 330, via_class: "ACLineSegment" }],
      },
      {
        from: "GLENRIDGE_NX", to: "ELDERMOUNT_NX",
        path_classes: ["ACLineSegment"], hops: 1, nominal_kv: 132,
        lines: [{ line_name: "ELD-01", line_mrid: "ln-bk-em-1", near_terminal: "GLENRIDGE_NX::B132-1", far_terminal: "ELDERMOUNT_NX::B132-1", nominal_kv: 132, via_class: "ACLineSegment" }],
      },
      {
        from: "OAKBANK_NX", to: "KILBARRA_DS",
        path_classes: ["ACLineSegment"], hops: 1, nominal_kv: 66,
        lines: [{ line_name: "KILBARRA-1", line_mrid: "ln-ww-kb-1", near_terminal: "OAKBANK_NX.66KV_A", far_terminal: "KILBARRA_DS.66KV_A", nominal_kv: 66, via_class: "ACLineSegment" }],
      },
    ],
  },
};
