/**
 * Topology store — per-station adjacency graph for the map tab.
 *
 * State:
 *   - activeStation:   The station currently centered on the map.
 *   - graph:           Last-loaded TopologyGraph (center + neighbors + links).
 *   - loading / error: In-flight / failure state for the active load.
 *   - overlay:         Optional {equipmentIds, severity} from a situation.
 *                      When present, the UI tints matching equipment rows red
 *                      and adds a severity halo around the center station.
 *   - breadcrumb:      Station codes in traversal order, most-recent-last.
 *                      Populated as the operator clicks through neighbors.
 *   - selectedEquipment: (station, equipmentId) of the row currently open in
 *                      the detail pane, or null.
 *
 * Actions:
 *   - loadStation(code, opts?) — Fetch topology for `code` (1 hop),
 *                                replacing graph + breadcrumb [code]. Pass
 *                                { overlay } to carry an alarm overlay from
 *                                a situation-card click.
 *   - pushBreadcrumb(code)     — Internal; appends `code` to the breadcrumb
 *                                after a neighbor-click load completes.
 *   - truncateBreadcrumbTo(code) — Drop breadcrumb entries after `code`
 *                                  (called from a breadcrumb-item click).
 *   - selectEquipment(station, equipmentId) — Open the detail pane.
 *   - clear()                  — Reset to empty.
 */

import { create } from "zustand";
import type { TopologyGraph } from "@/api/topologyApi";
import { getTopology } from "@/api/topologyApi";
import { useToastStore } from "@/stores/toastStore";
import { IS_KIOSK } from "@/foundation/constants";

export type TopologyOverlay = {
  equipmentIds: string[];
  severity: string;
};

export type TopologySelection = {
  station: string;
  equipmentId: string;
};

export type LoadOpts = {
  overlay?: TopologyOverlay | null;
  /** When true, append the station to the breadcrumb instead of resetting. */
  pushBreadcrumb?: boolean;
};

interface TopologyState {
  activeStation: string | null;
  graph: TopologyGraph | null;
  loading: boolean;
  error: string | null;
  overlay: TopologyOverlay | null;
  breadcrumb: string[];
  selectedEquipment: TopologySelection | null;
  /** Station codes whose 1-hop fan-out has already been merged into the
   *  current graph via expandStation. Reset when the center changes. */
  expandedStations: Set<string>;
  /** Station codes whose expand request is currently in flight. Drives
   *  per-card busy state on the expand button. */
  expandingStations: Set<string>;

  loadStation: (station: string, opts?: LoadOpts) => Promise<void>;
  truncateBreadcrumbTo: (station: string) => Promise<void>;
  selectEquipment: (selection: TopologySelection | null) => void;
  /** Fetch `station`'s 1-hop graph and merge its new neighbors/links into
   *  the current graph. No-op if `station` is the center or not present in
   *  the current graph, or if it has already been expanded. */
  expandStation: (station: string) => Promise<void>;
  clear: () => void;
}

export const useTopologyStore = create<TopologyState>((set, get) => ({
  activeStation: null,
  graph: null,
  loading: false,
  error: null,
  overlay: null,
  breadcrumb: [],
  selectedEquipment: null,
  expandedStations: new Set<string>(),
  expandingStations: new Set<string>(),

  loadStation: async (station, opts) => {
    /* Guard: ignore empty codes — the UI can call this on mount before a
       situation is picked. */
    const trimmed = (station ?? "").trim();
    if (!trimmed) return;

    if (IS_KIOSK) {
      const current = get();
      if (current.graph && current.activeStation === trimmed) {
        set({ overlay: opts?.overlay ?? (opts?.overlay === null ? null : current.overlay), loading: false, error: null });
        return;
      }
      set({ loading: false, error: null });
      return;
    }

    /* Snapshot the current graph state so we can roll back to it if the
       fetch fails. The previous behaviour cleared activeStation /
       breadcrumb / graph eagerly and then nulled `graph` on error, which
       wiped the operator's working topology view whenever a 404 came
       back. The new contract: optimistically mark loading, but DO NOT
       overwrite the prior graph or breadcrumb until the fetch succeeds. */
    const prev = get();

    set({
      loading: true,
      error: null,
      /* activeStation reflects the IN-FLIGHT station so the header /
         retry button can address it; the graph itself stays on the
         previously-loaded center until the fetch resolves. */
      activeStation: trimmed,
    });

    try {
      const graph = await getTopology(trimmed, 1);
      /* Success: install the new graph and rebuild breadcrumb / overlay /
         expansion markers atomically. */
      set((state) => ({
        graph,
        loading: false,
        overlay: opts?.overlay ?? (opts?.overlay === null ? null : state.overlay),
        breadcrumb: opts?.pushBreadcrumb
          ? [...prev.breadcrumb.filter((b) => b !== trimmed), trimmed]
          : [trimmed],
        selectedEquipment: null,
        expandedStations: new Set<string>(),
        expandingStations: new Set<string>(),
      }));
    } catch (err) {
      /* Failure: roll activeStation back to whatever was previously
         centred so the header / breadcrumb stay consistent with the
         graph that is still rendered. Surface the failure as a non-
         destructive toast instead of clearing the view. */
      const message = (err as Error).message;
      set({
        loading: false,
        error: null,
        activeStation: prev.activeStation,
      });
      useToastStore.getState().pushToast({
        title: `Topology unavailable for ${trimmed}`,
        body: message,
        tone: "warning",
        durationMs: 5000,
      });
    }
  },

  truncateBreadcrumbTo: async (station) => {
    const current = get().breadcrumb;
    const idx = current.indexOf(station);
    if (idx < 0) return;
    const truncated = current.slice(0, idx + 1);
    set({ breadcrumb: truncated });
    /* If the target is already the active station, nothing to reload.
       Otherwise fetch its topology but keep the truncated breadcrumb. */
    if (get().activeStation !== station) {
      const prev = get();
      set({
        loading: true,
        error: null,
        activeStation: station,
        selectedEquipment: null,
      });
      try {
        const graph = await getTopology(station, 1);
        set({
          graph,
          loading: false,
          /* Rebuilding around a new center invalidates per-neighbor expand
             markers — those referred to the previous graph. */
          expandedStations: new Set<string>(),
          expandingStations: new Set<string>(),
        });
      } catch (err) {
        /* Roll back active station + breadcrumb so the previously-shown
           graph stays consistent. Surface the failure as a toast. */
        const message = (err as Error).message;
        set({
          loading: false,
          error: null,
          activeStation: prev.activeStation,
          breadcrumb: prev.breadcrumb,
        });
        useToastStore.getState().pushToast({
          title: `Topology unavailable for ${station}`,
          body: message,
          tone: "warning",
          durationMs: 5000,
        });
      }
    }
  },

  selectEquipment: (selection) => set({ selectedEquipment: selection }),

  /**
   * expandStation — extend the currently displayed graph by fetching
   * `station`'s 1-hop neighbors and merging any new ones into the
   * existing graph object. The center is not re-assigned; breadcrumb is
   * not pushed. The station being expanded must already be present in
   * the current graph.
   *
   * Merge rules:
   *   - Stations already in the graph (center or existing neighbor) are
   *     never re-added; their equipment/hops stay as-is.
   *   - New neighbors are added with hops = (expanded.hops ?? 0) + 1 and
   *     `parent_station = station` so the map layout can cluster them
   *     radially near the expanded card.
   *   - Links are deduped by unordered pair {from, to}. Self-loops
   *     (from === to) are skipped.
   *
   * Side effects:
   *   - Marks `station` as expanded so repeated clicks are no-ops.
   *   - Tracks in-flight state in expandingStations for UI busy indicators.
   */
  expandStation: async (station) => {
    const trimmed = (station ?? "").trim();
    if (!trimmed) return;
    const state = get();
    const graph = state.graph;
    if (!graph) return;
    if (state.expandedStations.has(trimmed)) return;
    if (state.expandingStations.has(trimmed)) return;

    /* Locate the station in the current graph to derive base hops. The
       center has no explicit hops field and cannot be expanded via this
       action (its neighbors are already on the map). */
    const existing =
      graph.center.station === trimmed
        ? graph.center
        : graph.neighbors.find((n) => n.station === trimmed);
    if (!existing) return;
    const baseHops = existing.hops ?? 0;
    if (graph.center.station === trimmed) return;

    set((s) => ({
      expandingStations: new Set([...s.expandingStations, trimmed]),
    }));

    try {
      const sub = await getTopology(trimmed, 1);

      set((s) => {
        const g = s.graph;
        if (!g) {
          const nextExpanding = new Set(s.expandingStations);
          nextExpanding.delete(trimmed);
          return { ...s, expandingStations: nextExpanding };
        }

        /* Seed the known-station set with codes already on the canvas. */
        const knownStations = new Set<string>([
          g.center.station,
          ...g.neighbors.map((n) => n.station),
        ]);

        /* Append any neighbors from the sub-graph that are not already on
           the canvas. Parent assignment points back at the expanded node
           so the map can cluster children around it. */
        const addedNeighbors: typeof g.neighbors = [];
        for (const sn of sub.neighbors) {
          if (!sn.station || sn.station === trimmed) continue;
          if (knownStations.has(sn.station)) continue;
          addedNeighbors.push({
            ...sn,
            hops: baseHops + 1,
            parent_station: trimmed,
          });
          knownStations.add(sn.station);
        }

        /* Build a canonical key for each existing link so we can dedupe
           the new ones. Pairs are unordered: A↔B === B↔A. */
        const linkKey = (a: string, b: string) =>
          a < b ? `${a}|${b}` : `${b}|${a}`;
        const existingLinkKeys = new Set(
          g.links.map((l) => linkKey(l.from, l.to)),
        );

        /* The sub-graph's links are expressed with `from = trimmed` (the
           sub-center). Rewrite into the parent graph's coordinate frame
           without changing semantics — the direction is purely cosmetic
           for the label positioning. */
        const addedLinks: typeof g.links = [];
        for (const sl of sub.links) {
          if (sl.from === sl.to) continue;
          const key = linkKey(sl.from, sl.to);
          if (existingLinkKeys.has(key)) continue;
          /* Only keep links whose endpoints are now present on the canvas
             (either pre-existing or just added). This guards against a
             backend response containing links whose neighbor was dropped
             by the merge above. */
          if (!knownStations.has(sl.from) || !knownStations.has(sl.to)) continue;
          addedLinks.push(sl);
          existingLinkKeys.add(key);
        }

        const nextGraph = {
          ...g,
          neighbors: [...g.neighbors, ...addedNeighbors],
          links: [...g.links, ...addedLinks],
        };

        /* Drop `trimmed` from expandingStations and add to expandedStations. */
        const nextExpanding = new Set(s.expandingStations);
        nextExpanding.delete(trimmed);
        const nextExpanded = new Set(s.expandedStations);
        nextExpanded.add(trimmed);

        return {
          ...s,
          graph: nextGraph,
          expandingStations: nextExpanding,
          expandedStations: nextExpanded,
        };
      });
    } catch (err) {
      set((s) => {
        const nextExpanding = new Set(s.expandingStations);
        nextExpanding.delete(trimmed);
        return {
          ...s,
          expandingStations: nextExpanding,
        };
      });
      useToastStore.getState().pushToast({
        title: `Topology expansion unavailable for ${trimmed}`,
        body: (err as Error).message,
        tone: "warning",
        durationMs: 5000,
      });
    }
  },

  clear: () =>
    set({
      activeStation: null,
      graph: null,
      loading: false,
      error: null,
      overlay: null,
      breadcrumb: [],
      selectedEquipment: null,
      expandedStations: new Set<string>(),
      expandingStations: new Set<string>(),
    }),
}));

/**
 * Parse a situation's `affected_equipment` JSON string into a list of
 * equipment identifiers suitable for overlay matching. Accepts both the
 * per-equipment format (`equipment_id` key) and the raw KQL format.
 *
 * @param affectedEquipmentJson — the SituationRecord.affected_equipment string.
 * @returns                       Flat list of equipment IDs (may be empty).
 */
export function extractOverlayEquipmentIds(affectedEquipmentJson: string): string[] {
  try {
    const parsed = JSON.parse(affectedEquipmentJson ?? "[]");
    if (!Array.isArray(parsed)) return [];
    return parsed
      .map((row): string | null => {
        if (row && typeof row === "object") {
          const eid = (row as Record<string, unknown>).equipment_id
            ?? (row as Record<string, unknown>).equipment
            ?? (row as Record<string, unknown>).scada_composite_id;
          return typeof eid === "string" ? eid : null;
        }
        return typeof row === "string" ? row : null;
      })
      .filter((s): s is string => !!s && s.length > 0);
  } catch {
    return [];
  }
}
