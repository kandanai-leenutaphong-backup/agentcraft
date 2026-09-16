/**
 * Topology API — fetches the abstract NEM station adjacency graph.
 *
 * Backed by the backend GET /api/topology endpoint. One HTTP call per
 * station change. Auth headers injected by the shared client module.
 */

import { BASE, authHeaders, handleResponse } from "./client";

/** One equipment row within a station — matches tools/topology/_topology.py. */
export interface TopologyEquipment {
  equipment: string;
  scada_composite_id: string;
  cim_classes: string[];
  nominal_kv: number | null;
  mw_max: number | null;
  mva_rated: number | null;
  /** Latest SCADA reading attached at response build time. Null when the
   *  equipment has no reading inside the backend's live lookback window
   *  (currently 15 min). Any individual field inside may also be null if
   *  that specific measurement was not present. */
  live?: TopologyEquipmentLive | null;
}

/** Latest live telemetry for one piece of equipment. */
export interface TopologyEquipmentLive {
  /** Real-time MW reading (generator output / load draw). Null if absent. */
  mw?: number | null;
  /** Real-time MVAR (reactive) reading. Null if absent. */
  mvar?: number | null;
  /** Real-time bus/line voltage reading, in kV. Null if absent. */
  kv?: number | null;
  /** Real-time frequency reading in Hz. Folded from either HZ or FREQ
   *  measurement types so the UI never branches. Null if absent. */
  hz?: number | null;
  /** Most recent timestamp across all measurements on this equipment.
   *  ISO 8601 string; empty or absent when no data. */
  ts?: string | null;
  /** Originating SCADA TagId per measurement, for operator traceability.
   *  Not every measurement is guaranteed to have an entry. */
  tags?: Record<string, string>;
}

/** Station-level rollup of live telemetry, computed from equipment rows. */
export interface StationLiveSummary {
  /** Sum of live MW across all equipment at the station. Null when no
   *  equipment carried a live MW reading. */
  mw_output: number | null;
  /** Sum of rated `mw_max` across generating/load equipment. Null when
   *  no equipment carried a positive rated value. Represents capacity. */
  mw_cap: number | null;
  /** Latest frequency reading at the station, in Hz. Null when no HZ tag
   *  was present inside the live lookback window. */
  freq: number | null;
  /** Most recent timestamp across all measurements contributing to this
   *  summary. Null when no live data. */
  ts: string | null;
}

/** A station in the topology graph — center or neighbor. */
export interface TopologyStation {
  station: string;
  region: string;
  equipment: TopologyEquipment[];
  /** Hop distance from the center. Absent on the center itself. */
  hops?: number;
  /** CIM classes describing the link back to the center. Absent on the center. */
  path_classes?: string[];
  /** Rolled-up live telemetry for the station. Emitted by the backend for
   *  both center and neighbor stations; absent only on historic responses. */
  live_summary?: StationLiveSummary | null;
  /** Station code this neighbor was expanded from. Absent on stations that
   *  came from the initial center-load (they attach to the center). Set
   *  only by frontend graph-merge logic after an "expand neighbors" click,
   *  never populated by the backend. Used by the map layout to cluster
   *  expansion fan-outs near their parent. */
  parent_station?: string;
}

/** One line or transformer winding making up a link between two stations. */
export interface TopologyLine {
  line_name: string;
  line_mrid: string;
  near_terminal: string;
  far_terminal: string;
  nominal_kv: number | null;
  via_class: string;
}

/** A link between the center and one neighbor. */
export interface TopologyLink {
  from: string;
  to: string;
  path_classes: string[];
  hops: number;
  nominal_kv: number | null;
  /** Per-line identity rows — one entry per ACLineSegment or TransformerWinding
   *  that makes up the link. Used by the hover-card UX. */
  lines: TopologyLine[];
}

/** The full topology response from GET /api/topology. */
export interface TopologyGraph {
  center: TopologyStation;
  neighbors: TopologyStation[];
  links: TopologyLink[];
}

/**
 * Fetch the topology graph for a station.
 *
 * @param station   Station code (e.g. "STN_A").
 * @param hops      1 (direct neighbors) or 2 (one-hop-away). Default 1.
 * @returns         Topology graph dict.
 * @throws ApiError On non-2xx response.
 */
export async function getTopology(
  station: string,
  hops: 1 | 2 = 1,
): Promise<TopologyGraph> {
  const headers = await authHeaders();
  const qs = new URLSearchParams({ station, hops: String(hops) });
  const res = await fetch(`${BASE}/topology/?${qs.toString()}`, { headers });
  return handleResponse<TopologyGraph>(res);
}
