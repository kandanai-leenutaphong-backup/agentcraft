/**
 * TopologyMap — radial canvas that renders the center station + neighbors.
 *
 * Layout:
 *   Center station fixed at (0,0) in the virtual coordinate space.
 *   Each neighbor placed on a circle of radius R, angle_i = i * 2π/n - π/2.
 *   (Offset of -π/2 puts the first neighbor directly above the center.)
 *
 * Rendering:
 *   A fixed-size positioned inner box holds the SVG link layer and the
 *   station cards. The outer container applies a `translate / scale`
 *   transform so the operator can pan and zoom:
 *     - Wheel event → zoom around cursor (0.3 – 2.5× clamp).
 *     - Pointer drag on empty surface → pan.
 *     - +/−/⟲ buttons → discrete zoom / recentre.
 *   No graph library — the data is small (≤24 neighbors) and a custom
 *   radial layout is cheaper and more legible than a forced simulation.
 *
 * Interactions:
 *   - Click a neighbor's re-center button → swap the center via
 *     topologyStore.loadStation(code, { pushBreadcrumb: true }).
 */

import { useMemo, useRef, useEffect, useState, useCallback } from "react";
import { Plus, Minus, Maximize2 } from "lucide-react";
import type { TopologyGraph, TopologyLink } from "@/api/topologyApi";
import { useTopologyStore } from "@/stores/topologyStore";
import { StationNode } from "./StationNode";

/** Station card dimensions — must match the Tailwind `w-[280px]` in StationNode. */
const NODE_WIDTH = 280;
/** Approximate expanded height of a station card (used for virtual layout). */
const NODE_HEIGHT = 320;
/** Radius of the neighbor ring around the center. */
const RING_RADIUS = 420;
/** Minimum visual gap between station cards in the virtual layout. */
const NODE_GAP = 72;
/** Upper bound for collision relaxation passes; keeps layout deterministic and cheap. */
const MAX_LAYOUT_RELAXATIONS = 80;
/** Zoom bounds — below 0.3 the labels vanish; above 2.5 cards clip the viewport. */
const ZOOM_MIN = 0.3;
const ZOOM_MAX = 2.5;
/** Mouse-wheel zoom speed; small enough that a single notch is a gentle nudge. */
const ZOOM_STEP_WHEEL = 0.0015;
/** Button zoom step — coarser than wheel so one click visibly moves the scale. */
const ZOOM_STEP_BUTTON = 0.2;

interface TopologyMapProps {
  graph: TopologyGraph;
  alarmedIds: Set<string>;
  overlaySeverity: string | null;
}

type Positioned = { code: string; x: number; y: number };

type LayoutNode = Positioned & { fixed?: boolean; minRadius: number };

/** Pan+zoom transform state — applied to the inner canvas as translate+scale. */
type Transform = { tx: number; ty: number; scale: number };

/** Keep one node outside the center exclusion zone while preserving its bearing. */
function enforceMinimumRadius(node: LayoutNode): void {
  if (node.fixed) return;
  const distance = Math.hypot(node.x, node.y);
  if (distance >= node.minRadius) return;
  const angle = distance === 0 ? -Math.PI / 2 : Math.atan2(node.y, node.x);
  node.x = Math.cos(angle) * node.minRadius;
  node.y = Math.sin(angle) * node.minRadius;
}

/** Separate two cards if their virtual rectangles overlap. */
function separateOverlappingNodes(a: LayoutNode, b: LayoutNode): boolean {
  const overlapX = NODE_WIDTH + NODE_GAP - Math.abs(a.x - b.x);
  const overlapY = NODE_HEIGHT + NODE_GAP - Math.abs(a.y - b.y);
  if (overlapX <= 0 || overlapY <= 0) return false;

  const pushX = a.x <= b.x ? -overlapX / 2 : overlapX / 2;
  const pushY = a.y <= b.y ? -overlapY / 2 : overlapY / 2;
  const moveAlongX = overlapX < overlapY;
  const deltaX = moveAlongX ? pushX : 0;
  const deltaY = moveAlongX ? 0 : pushY;

  if (a.fixed && b.fixed) return false;
  if (a.fixed) {
    b.x -= deltaX * 2;
    b.y -= deltaY * 2;
  } else if (b.fixed) {
    a.x += deltaX * 2;
    a.y += deltaY * 2;
  } else {
    a.x += deltaX;
    a.y += deltaY;
    b.x -= deltaX;
    b.y -= deltaY;
  }

  enforceMinimumRadius(a);
  enforceMinimumRadius(b);
  return true;
}

/** Reflow station coordinates until cards no longer overlap. */
function relaxTopologyLayout(nodes: LayoutNode[]): void {
  for (let pass = 0; pass < MAX_LAYOUT_RELAXATIONS; pass += 1) {
    let moved = false;
    for (let i = 0; i < nodes.length; i += 1) {
      for (let j = i + 1; j < nodes.length; j += 1) {
        moved = separateOverlappingNodes(nodes[i], nodes[j]) || moved;
      }
    }
    if (!moved) return;
  }
}

/**
 * Resolve the live MW flow at one endpoint of a link.
 *
 * Scans `station.equipment` for an ACLineSegment or TransformerWinding
 * record whose identifier references the neighbour station, and returns
 * its most recent live MW reading. This works because asset-registry
 * line equipment follows the `STATION.LINE.NEIGHBOUR` / `STATION.TX.*`
 * naming convention and carries its own SCADA tag, which the backend
 * already folds into `equipment.live.mw` via the live-telemetry join.
 *
 * Matching order:
 *   1. Exact line_mrid hit (when the link carries a `lines[]` payload).
 *   2. Equipment name / scada_composite_id containing the neighbour code.
 *   3. None — returns null so the label falls back to "—".
 *
 * Returns the equipment's MW reading and the matching equipment code so
 * the edge label can explain the source on hover.
 */
function resolveTerminalFlow(
  station: { equipment: { equipment: string; scada_composite_id: string; cim_classes: string[]; live?: { mw?: number | null } | null }[] } | undefined,
  neighbourCode: string,
  lineMrids: string[],
): { mw: number; source: string } | null {
  if (!station) return null;
  const lineClasses = new Set(["ACLineSegment", "TransformerWinding"]);
  const neighbourUpper = neighbourCode.toUpperCase();
  let fallback: { mw: number; source: string } | null = null;
  for (const equip of station.equipment) {
    if (!equip.cim_classes.some((c) => lineClasses.has(c))) continue;
    const mw = equip.live?.mw;
    if (typeof mw !== "number") continue;

    /* 1. Exact MRID hit beats everything else. */
    const idBlob = `${equip.equipment} ${equip.scada_composite_id}`.toUpperCase();
    if (lineMrids.some((m) => m && idBlob.includes(m.toUpperCase()))) {
      return { mw, source: equip.equipment };
    }

    /* 2. Neighbour-name substring on either equipment or SCADA id. */
    if (idBlob.includes(neighbourUpper) && !fallback) {
      fallback = { mw, source: equip.equipment };
    }
  }
  return fallback;
}

export function TopologyMap({ graph, alarmedIds, overlaySeverity }: TopologyMapProps) {
  const loadStation = useTopologyStore((s) => s.loadStation);
  const overlay = useTopologyStore((s) => s.overlay);
  const expandStation = useTopologyStore((s) => s.expandStation);
  const expandedStations = useTopologyStore((s) => s.expandedStations);
  const expandingStations = useTopologyStore((s) => s.expandingStations);

  /* Compute (x, y) in virtual coordinates for each station. The center
     sits at (0,0). Neighbors fan out on concentric rings keyed by hop
     count:
       hop 1 → RING_RADIUS
       hop 2 → RING_RADIUS × 2
       hop N → RING_RADIUS × N
     Within each ring, first-hop neighbors spread evenly (2π / n). Later
     hops cluster in an arc around their `parent_station`'s angle so an
     expansion fan-out stays visually near the card it came from. Layout
     is memoized on the graph identity to avoid reshuffling on overlay
     or alarm re-renders. */
  const positioned: {
    center: Positioned;
    neighbors: Positioned[];
  } = useMemo(() => {
    /* First pass: place hop-1 neighbors evenly on the inner ring and
       record each one's angle so children can reference it. */
    const firstHops = graph.neighbors.filter((n) => (n.hops ?? 1) <= 1);
    const angleByCode = new Map<string, number>();
    const positionByCode = new Map<string, Positioned>();
    firstHops.forEach((n, idx) => {
      const angle = (idx * 2 * Math.PI) / Math.max(firstHops.length, 1) - Math.PI / 2;
      angleByCode.set(n.station, angle);
      positionByCode.set(n.station, {
        code: n.station,
        x: Math.round(Math.cos(angle) * RING_RADIUS),
        y: Math.round(Math.sin(angle) * RING_RADIUS),
      });
    });

    /* Subsequent hops: iterate by ascending hop count so a child always
       finds its parent's angle already populated. Children of the same
       parent spread in an arc of ±ARC_SPREAD centered on the parent. */
    const ARC_SPREAD = Math.PI / 3;  // ~60° total fan per parent.
    const remaining = graph.neighbors
      .filter((n) => (n.hops ?? 1) > 1)
      .slice()
      .sort((a, b) => (a.hops ?? 1) - (b.hops ?? 1));

    /* Group children by parent so we can distribute them evenly inside
       that parent's fan slice. */
    const childrenByParent = new Map<string, typeof remaining>();
    for (const child of remaining) {
      const parent = child.parent_station ?? graph.center.station;
      const bucket = childrenByParent.get(parent) ?? [];
      bucket.push(child);
      childrenByParent.set(parent, bucket);
    }

    for (const [parent, children] of childrenByParent) {
      /* Parent's angle defaults to 0 (east) if the parent is the center
         or unknown; otherwise use the angle assigned above. */
      const parentAngle = angleByCode.get(parent) ?? 0;
      children.forEach((child, idx) => {
        const count = children.length;
        /* Offset within the fan: ‑ARC_SPREAD/2 … +ARC_SPREAD/2. */
        const offset =
          count === 1 ? 0 : (idx / (count - 1) - 0.5) * ARC_SPREAD;
        const angle = parentAngle + offset;
        const radius = RING_RADIUS * (child.hops ?? 2);
        angleByCode.set(child.station, angle);
        positionByCode.set(child.station, {
          code: child.station,
          x: Math.round(Math.cos(angle) * radius),
          y: Math.round(Math.sin(angle) * radius),
        });
      });
    }

    /* Relax all station cards together after radial placement. Expansion
       can add multiple children near one parent; this pass lets the whole
       graph reshape so every card remains separated instead of stacking
       tightly around the expanded station. */
    const layoutNodes: LayoutNode[] = [
      { code: graph.center.station, x: 0, y: 0, fixed: true, minRadius: 0 },
      ...graph.neighbors.map((neighbor) => {
        const positionedNode = positionByCode.get(neighbor.station) ?? {
          code: neighbor.station,
          x: RING_RADIUS,
          y: 0,
        };
        const hops = Math.max(1, neighbor.hops ?? 1);
        return {
          ...positionedNode,
          minRadius: RING_RADIUS * hops,
        };
      }),
    ];
    relaxTopologyLayout(layoutNodes);
    for (const node of layoutNodes) {
      positionByCode.set(node.code, {
        code: node.code,
        x: Math.round(node.x),
        y: Math.round(node.y),
      });
    }

    /* Assemble the ordered neighbor position list in the same order as
       graph.neighbors so downstream indexing lines up. */
    const neighbors: Positioned[] = graph.neighbors.map(
      (n) =>
        positionByCode.get(n.station) ?? {
          code: n.station,
          x: RING_RADIUS,
          y: 0,
        },
    );

    return {
      center: { code: graph.center.station, x: 0, y: 0 },
      neighbors,
    };
  }, [graph]);

  /* Compute the bounding box of the virtual layout so we can set the
     wrapper's inner dimensions and offset everything into positive space. */
  const bounds = useMemo(() => {
    const all = [positioned.center, ...positioned.neighbors];
    const minX = Math.min(...all.map((p) => p.x)) - NODE_WIDTH / 2 - 40;
    const maxX = Math.max(...all.map((p) => p.x)) + NODE_WIDTH / 2 + 40;
    const minY = Math.min(...all.map((p) => p.y)) - NODE_HEIGHT / 2 - 40;
    const maxY = Math.max(...all.map((p) => p.y)) + NODE_HEIGHT / 2 + 40;
    return { minX, maxX, minY, maxY, width: maxX - minX, height: maxY - minY };
  }, [positioned]);

  /* Lookup to resolve neighbor positions by code when drawing links. */
  const byCode = useMemo(() => {
    const map = new Map<string, Positioned>();
    map.set(positioned.center.code, positioned.center);
    positioned.neighbors.forEach((n) => map.set(n.code, n));
    return map;
  }, [positioned]);

  /* Lookup to resolve the full TopologyStation record (with equipment +
     live readings) by code. Used by the edge-label path to pull per-line
     MW flow out of whichever line-equipment lives at the endpoint
     stations. No backend changes needed \u2014 line flow is just the live
     MW on a station's ACLineSegment/TransformerWinding equipment whose
     `equipment` or `scada_composite_id` points at the neighbour. */
  const stationByCode = useMemo(() => {
    const map = new Map<string, typeof graph.center>();
    map.set(graph.center.station, graph.center);
    graph.neighbors.forEach((n) => map.set(n.station, n));
    return map;
  }, [graph]);

  const handleRecenter = (code: string) => {
    /* Preserve the current overlay — the operator walking to a neighbor
       should still see the overlay information if it is relevant. The
       matching set applies on whichever station is in scope. */
    loadStation(code, {
      pushBreadcrumb: true,
      overlay: overlay ?? null,
    });
  };

  /* ── Pan + zoom state ───────────────────────────────────────────────
     The inner canvas is rendered at its natural size and positioned by
     applying `translate(tx, ty) scale(scale)` on a wrapper. tx/ty are in
     outer-container pixel space (not scaled). */
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [transform, setTransform] = useState<Transform>({ tx: 0, ty: 0, scale: 1 });

  /* Fit the whole graph into the visible viewport so neighbor controls are
     reachable immediately after load and after re-centering. */
  const fitToCenter = useCallback(() => {
    const node = containerRef.current;
    if (!node) return;
    const vw = node.clientWidth;
    const vh = node.clientHeight;
    if (vw <= 0 || vh <= 0) return;
    const scale = Math.max(
      ZOOM_MIN,
      Math.min(1, (vw - 32) / bounds.width, (vh - 32) / bounds.height),
    );
    setTransform({
      tx: (vw - bounds.width * scale) / 2,
      ty: (vh - bounds.height * scale) / 2,
      scale,
    });
  }, [bounds]);

  /* Re-fit whenever the graph's center changes (new station loaded). */
  useEffect(() => {
    fitToCenter();
  }, [graph.center.station, fitToCenter]);

  useEffect(() => {
    const node = containerRef.current;
    if (!node) return;
    const observer = new ResizeObserver(() => fitToCenter());
    observer.observe(node);
    return () => observer.disconnect();
  }, [fitToCenter]);

  /* Wheel zoom — anchor at the cursor so zooming toward a neighbor keeps
     that neighbor under the pointer. */
  const handleWheel = useCallback((e: React.WheelEvent<HTMLDivElement>) => {
    /* Ignore modified-wheel (ctrl+wheel for browser zoom, etc.). */
    if (e.ctrlKey && e.deltaY === 0) return;
    e.preventDefault();
    const node = containerRef.current;
    if (!node) return;
    const rect = node.getBoundingClientRect();
    const cx = e.clientX - rect.left;
    const cy = e.clientY - rect.top;
    setTransform((prev) => {
      const nextScale = Math.min(
        ZOOM_MAX,
        Math.max(ZOOM_MIN, prev.scale * Math.exp(-e.deltaY * ZOOM_STEP_WHEEL)),
      );
      if (nextScale === prev.scale) return prev;
      /* Keep the point under the cursor fixed during zoom:
         cursor = tx + scale * p  ⇒  p = (cursor - tx) / scale
         new_tx = cursor - nextScale * p                              */
      const p_x = (cx - prev.tx) / prev.scale;
      const p_y = (cy - prev.ty) / prev.scale;
      return {
        scale: nextScale,
        tx: cx - nextScale * p_x,
        ty: cy - nextScale * p_y,
      };
    });
  }, []);

  /* Attach wheel handler with passive:false so preventDefault() works in
     Chromium (React's onWheel is passive by default). */
  useEffect(() => {
    const node = containerRef.current;
    if (!node) return;
    const handler = (e: WheelEvent) => {
      e.preventDefault();
      const rect = node.getBoundingClientRect();
      const cx = e.clientX - rect.left;
      const cy = e.clientY - rect.top;
      setTransform((prev) => {
        const nextScale = Math.min(
          ZOOM_MAX,
          Math.max(ZOOM_MIN, prev.scale * Math.exp(-e.deltaY * ZOOM_STEP_WHEEL)),
        );
        if (nextScale === prev.scale) return prev;
        const p_x = (cx - prev.tx) / prev.scale;
        const p_y = (cy - prev.ty) / prev.scale;
        return {
          scale: nextScale,
          tx: cx - nextScale * p_x,
          ty: cy - nextScale * p_y,
        };
      });
    };
    node.addEventListener("wheel", handler, { passive: false });
    return () => node.removeEventListener("wheel", handler as EventListener);
  }, []);

  /* Drag-to-pan. Uses pointer events so touch + mouse work identically.
     Drags only begin on the outer surface — station cards call
     stopPropagation on their own pointer events to avoid interfering. */
  const dragStateRef = useRef<{ startX: number; startY: number; origTx: number; origTy: number; pointerId: number } | null>(null);
  const [isPanning, setIsPanning] = useState(false);

  const onPointerDown = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    /* Only handle left button / primary pointer. Right-click and middle
       stay out of the way. */
    if (e.button !== 0) return;
    /* Cards live inside this container — ignore drag if the press landed
       on an interactive element. `closest('[data-no-pan]')` matches the
       station-card wrapper which sets this marker. */
    const target = e.target as HTMLElement;
    if (target.closest("[data-no-pan]")) return;
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    dragStateRef.current = {
      startX: e.clientX,
      startY: e.clientY,
      origTx: transform.tx,
      origTy: transform.ty,
      pointerId: e.pointerId,
    };
    setIsPanning(true);
  }, [transform.tx, transform.ty]);

  const onPointerDownCapture = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    if (e.button !== 0) return;
    const hitPadding = 6;
    const expandButtons = e.currentTarget.querySelectorAll<HTMLButtonElement>(
      "[data-topology-expand-station]",
    );
    for (const button of expandButtons) {
      if (button.disabled) continue;
      const rect = button.getBoundingClientRect();
      const withinX = e.clientX >= rect.left - hitPadding && e.clientX <= rect.right + hitPadding;
      const withinY = e.clientY >= rect.top - hitPadding && e.clientY <= rect.bottom + hitPadding;
      if (!withinX || !withinY) continue;
      const station = button.dataset.topologyExpandStation;
      if (!station) return;
      e.stopPropagation();
      void expandStation(station);
      return;
    }
  }, [expandStation]);

  const onPointerMove = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    const s = dragStateRef.current;
    if (!s || s.pointerId !== e.pointerId) return;
    setTransform((prev) => ({
      ...prev,
      tx: s.origTx + (e.clientX - s.startX),
      ty: s.origTy + (e.clientY - s.startY),
    }));
  }, []);

  const onPointerUp = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    if (dragStateRef.current?.pointerId === e.pointerId) {
      (e.currentTarget as HTMLElement).releasePointerCapture?.(e.pointerId);
      dragStateRef.current = null;
      setIsPanning(false);
    }
  }, []);

  /* Button-driven zoom — anchors on the viewport centre so the active
     card stays visible. */
  const zoomBy = useCallback((delta: number) => {
    const node = containerRef.current;
    if (!node) return;
    const cx = node.clientWidth / 2;
    const cy = node.clientHeight / 2;
    setTransform((prev) => {
      const nextScale = Math.min(
        ZOOM_MAX,
        Math.max(ZOOM_MIN, prev.scale + delta),
      );
      if (nextScale === prev.scale) return prev;
      const p_x = (cx - prev.tx) / prev.scale;
      const p_y = (cy - prev.ty) / prev.scale;
      return {
        scale: nextScale,
        tx: cx - nextScale * p_x,
        ty: cy - nextScale * p_y,
      };
    });
  }, []);

  return (
    <div
      ref={containerRef}
      data-testid="topology-map"
      /* `topology-dot-grid` paints a subtle 24 px dot pattern so pan/zoom
         has a frame of reference. Cards render on top unchanged. */
      className="relative h-full w-full overflow-hidden topology-dot-grid select-none"
      onPointerDown={onPointerDown}
      onPointerDownCapture={onPointerDownCapture}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
      onWheel={handleWheel}
      style={{ cursor: isPanning ? "grabbing" : "grab", touchAction: "none" }}
    >
      {/* Zoom / recentre controls — floating top-right. */}
      <div
        className="absolute top-2 right-2 z-10 flex flex-col gap-1 rounded border border-border/50 bg-neutral-bg1/90 p-1 shadow-md backdrop-blur-sm"
        data-no-pan="true"
        onPointerDown={(e) => e.stopPropagation()}
      >
        <button
          type="button"
          data-testid="topology-zoom-in"
          onClick={() => zoomBy(ZOOM_STEP_BUTTON)}
          title="Zoom in"
          className="h-6 w-6 flex items-center justify-center rounded hover:bg-neutral-bg3 text-text-muted hover:text-text-primary"
        >
          <Plus className="h-3.5 w-3.5" />
        </button>
        <button
          type="button"
          data-testid="topology-zoom-out"
          onClick={() => zoomBy(-ZOOM_STEP_BUTTON)}
          title="Zoom out"
          className="h-6 w-6 flex items-center justify-center rounded hover:bg-neutral-bg3 text-text-muted hover:text-text-primary"
        >
          <Minus className="h-3.5 w-3.5" />
        </button>
        <button
          type="button"
          data-testid="topology-zoom-reset"
          onClick={fitToCenter}
          title="Reset view"
          className="h-6 w-6 flex items-center justify-center rounded hover:bg-neutral-bg3 text-text-muted hover:text-text-primary"
        >
          <Maximize2 className="h-3 w-3" />
        </button>
        <div className="text-[9px] font-mono text-text-muted text-center mt-0.5" title="Current zoom">
          {Math.round(transform.scale * 100)}%
        </div>
      </div>

      {/* Pan+zoom transform wrapper. `transform-origin: 0 0` matches the
          math in the wheel handler, which derives the inverse in the
          same frame. */}
      <div
        className="absolute top-0 left-0"
        style={{
          transform: `translate(${transform.tx}px, ${transform.ty}px) scale(${transform.scale})`,
          transformOrigin: "0 0",
          width: `${bounds.width}px`,
          height: `${bounds.height}px`,
          willChange: "transform",
        }}
      >
        {/* SVG layer — one line per link, drawn behind station cards. */}
        <svg
          className="absolute inset-0 pointer-events-none"
          width={bounds.width}
          height={bounds.height}
          style={{ left: 0, top: 0 }}
        >
          {graph.links.map((link: TopologyLink) => {
            const from = byCode.get(link.from);
            const to = byCode.get(link.to);
            if (!from || !to) return null;
            const x1 = from.x - bounds.minX;
            const y1 = from.y - bounds.minY;
            const x2 = to.x - bounds.minX;
            const y2 = to.y - bounds.minY;
            /* Position the label at the midpoint of the line. */
            const mx = (x1 + x2) / 2;
            const my = (y1 + y2) / 2;
            const dashed = link.hops > 1;

            /* Primary label shows the most informative line identity we
               have. When the adjacency table yields a `lines[]` array we
               render the first entry's name + via-class on separate rows;
               falling back to the aggregated `path_classes`. kV is always
               rendered first because it is the single most scanned field.
               A detailed `title` is attached for the operator who hovers
               \u2014 it carries every line's terminals and MRID. */
            const primaryLine = link.lines?.[0];
            const kvLabel = link.nominal_kv != null
              ? `${link.nominal_kv.toFixed(0)} kV`
              : null;
            const classLabel =
              primaryLine?.via_class
              ?? link.path_classes?.[0]
              ?? null;
            const extraLineCount = Math.max(0, (link.lines?.length ?? 0) - 1);

            /* Resolve live MW flow at each endpoint via the helper.
               When both endpoints report a value we average the signed
               readings (flows should sum to ~zero if perfectly balanced;
               averaging reduces noise from sensor offsets). When only one
               end reports, we take that value at face value and tag the
               label with the originating station so the operator can
               read the sign correctly (positive = out of `from`). */
            const lineMrids = (link.lines ?? []).map((ln) => ln.line_mrid).filter(Boolean) as string[];
            const fromFlow = resolveTerminalFlow(stationByCode.get(link.from), link.to, lineMrids);
            const toFlow = resolveTerminalFlow(stationByCode.get(link.to), link.from, lineMrids);
            let flowMw: number | null = null;
            let flowSource = "";
            if (fromFlow && toFlow) {
              /* Endpoint readings have opposite signs when measured from
                 each terminal. Use from's magnitude with from's sign. */
              flowMw = fromFlow.mw;
              flowSource = `${link.from}:${fromFlow.source}`;
            } else if (fromFlow) {
              flowMw = fromFlow.mw;
              flowSource = `${link.from}:${fromFlow.source}`;
            } else if (toFlow) {
              flowMw = -toFlow.mw;
              flowSource = `${link.to}:${toFlow.source}`;
            }
            const tooltip = (() => {
              /* Build a multi-line hover tooltip listing every line on
                 the pair with its identity and terminals. SVG `<title>`
                 renders as the browser's native tooltip and supports
                 line breaks. */
              if (!link.lines || link.lines.length === 0) {
                return [
                  `${link.from} \u2194 ${link.to}`,
                  kvLabel,
                  classLabel,
                ].filter(Boolean).join("\n");
              }
              const header = `${link.from} \u2194 ${link.to}`;
              const lineLines = link.lines.map((ln) => {
                const name = ln.line_name || ln.line_mrid || "(unnamed line)";
                const kv = ln.nominal_kv != null ? `${ln.nominal_kv.toFixed(0)} kV` : "? kV";
                return [
                  `\u2022 ${name} (${ln.via_class}, ${kv})`,
                  `    ${ln.near_terminal || "?"} \u2192 ${ln.far_terminal || "?"}`,
                ].join("\n");
              });
              return [header, ...lineLines].join("\n");
            })();

            /* `<foreignObject>` hosts an HTML div whose width is driven
               by the content, so the label no longer overflows a
               hard-coded rect. We centre the object by sizing it wide
               enough for the longest label and using CSS flex. Height
               accommodates up to four rows (name, kV/class, flow, terminals). */
            const FO_WIDTH = 240;
            const FO_HEIGHT = 72;

            return (
              <g
                key={`${link.from}-${link.to}`}
                data-testid={`topology-edge-${link.from}-${link.to}`}
              >
                <title>{tooltip}</title>
                <line
                  x1={x1} y1={y1} x2={x2} y2={y2}
                  stroke="currentColor"
                  className="text-brand/60"
                  strokeWidth={2}
                  strokeDasharray={dashed ? "6 4" : undefined}
                />
                <foreignObject
                  x={mx - FO_WIDTH / 2}
                  y={my - FO_HEIGHT / 2}
                  width={FO_WIDTH}
                  height={FO_HEIGHT}
                  style={{ overflow: "visible", pointerEvents: "none" }}
                  data-testid={`topology-edge-label-${link.from}-${link.to}`}
                >
                  <div
                    className="h-full w-full flex items-center justify-center pointer-events-none"
                  >
                    <div
                      className="max-w-full rounded border border-border bg-neutral-bg1 px-1.5 py-0.5 text-center shadow-md"
                    >
                      {primaryLine?.line_name && (
                        <div
                          className="text-micro font-mono font-semibold text-text-primary truncate leading-tight"
                          title={primaryLine.line_name}
                        >
                          {primaryLine.line_name}
                        </div>
                      )}
                      <div className="text-[9px] font-mono text-text-secondary leading-tight whitespace-nowrap">
                        {kvLabel && <span className="text-brand/90">{kvLabel}</span>}
                        {kvLabel && classLabel && <span className="text-text-muted">{" · "}</span>}
                        {classLabel && <span>{classLabel}</span>}
                        {extraLineCount > 0 && (
                          <span className="text-text-muted">{` · +${extraLineCount}`}</span>
                        )}
                      </div>
                      {/* Live MW flow row. Shows the resolved endpoint
                          reading with a direction arrow; hidden when no
                          line equipment on either station reported a
                          live MW value in the lookback window. */}
                      {flowMw != null && (
                        <div
                          data-testid={`topology-edge-flow-${link.from}-${link.to}`}
                          title={`Live MW flow resolved from ${flowSource}`}
                          className={[
                            "text-micro font-mono font-semibold leading-tight tabular-nums",
                            Math.abs(flowMw) < 0.5 ? "text-text-muted" : "text-brand",
                          ].join(" ")}
                        >
                          {flowMw >= 0
                            ? `${link.from} → ${link.to}  ${flowMw.toFixed(1)} MW`
                            : `${link.to} → ${link.from}  ${Math.abs(flowMw).toFixed(1)} MW`}
                        </div>
                      )}
                      {primaryLine && (primaryLine.near_terminal || primaryLine.far_terminal) && (
                        <div
                          className="text-[9px] font-mono text-text-muted truncate leading-tight"
                          title={`${primaryLine.near_terminal || "?"} \u2192 ${primaryLine.far_terminal || "?"}`}
                        >
                          {`${primaryLine.near_terminal || "?"} → ${primaryLine.far_terminal || "?"}`}
                        </div>
                      )}
                    </div>
                  </div>
                </foreignObject>
              </g>
            );
          })}
        </svg>

        {/* Center station card. `data-no-pan` opts the card out of the
            outer drag surface so clicks inside the card never initiate a
            pan. The card's own buttons handle clicks in the normal way. */}
        <div
          className="absolute"
          data-no-pan="true"
          onPointerDown={(e) => e.stopPropagation()}
          style={{
            left: `${positioned.center.x - bounds.minX - NODE_WIDTH / 2}px`,
            top: `${positioned.center.y - bounds.minY - 30}px`,
          }}
        >
          <StationNode
            station={graph.center}
            variant="center"
            alarmedIds={alarmedIds}
            overlaySeverity={overlaySeverity}
          />
        </div>

        {/* Neighbor station cards. */}
        {graph.neighbors.map((neighbor, idx) => {
          const pos = positioned.neighbors[idx];
          return (
            <div
              key={neighbor.station}
              className="absolute"
              data-no-pan="true"
              onPointerDown={(e) => e.stopPropagation()}
              style={{
                left: `${pos.x - bounds.minX - NODE_WIDTH / 2}px`,
                top: `${pos.y - bounds.minY - 30}px`,
              }}
            >
              <StationNode
                station={neighbor}
                variant="neighbor"
                alarmedIds={alarmedIds}
                overlaySeverity={null}
                onRecenter={handleRecenter}
                onExpand={(code) => { void expandStation(code); }}
                isExpanded={expandedStations.has(neighbor.station)}
                isExpanding={expandingStations.has(neighbor.station)}
              />
            </div>
          );
        })}
      </div>
    </div>
  );
}
