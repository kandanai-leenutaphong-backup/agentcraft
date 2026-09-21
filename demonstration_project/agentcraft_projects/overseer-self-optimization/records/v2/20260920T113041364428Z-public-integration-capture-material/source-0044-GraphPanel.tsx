import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Crosshair, Loader2, Locate, Maximize2, RefreshCw, Search, X, ZoomIn, ZoomOut } from "lucide-react";
import { api } from "../../shared/api";
import { layout, placeEdgeLabels, type LayoutNode } from "./forceLayout";
import { TimeWindowControl, type TimeWindow } from "./TimeWindowControl";
import type { GraphEdge, GraphNode, GraphOverview, GraphScope, GraphStatus } from "../../shared/types";

// Close to the stage's rendered size, so 100% zoom is near 1:1 and label type is legible.
const WIDTH = 780;
const HEIGHT = 700;
//: Full screen is wider than it is tall, so the layout is recomputed for that shape.
const WIDE_WIDTH = 1500;
const WIDE_HEIGHT = 720;

/** Colour and radius per ontology class, so a class is readable without hovering. */
const LABEL_STYLE: Record<string, { fill: string; ring: string; radius: number; blurb: string }> = {
  Host: { fill: "#1d4f6b", ring: "#67e8f9", radius: 17, blurb: "Named asset observed in telemetry" },
  Identity: { fill: "#4a3570", ring: "#c4b5fd", radius: 16, blurb: "Account observed acting or targeted" },
  IpAddress: { fill: "#1f4a3a", ring: "#6ee7b7", radius: 11, blurb: "Network address endpoint" },
  DnsName: { fill: "#3d3a20", ring: "#fde68a", radius: 8, blurb: "Queried DNS name" },
  KerberosService: { fill: "#4a2f1d", ring: "#fdba74", radius: 12, blurb: "Kerberos service principal" },
  Application: { fill: "#233f5c", ring: "#93c5fd", radius: 11, blurb: "Application named by the firewall" },
  Session: { fill: "#2c3550", ring: "#a5b4fc", radius: 10, blurb: "Logon or privileged session handle" },
  Sensor: { fill: "#2c2c34", ring: "#a1a1aa", radius: 9, blurb: "Reporting sensor" },
  SecurityAlert: { fill: "#5c1f24", ring: "#fca5a5", radius: 15, blurb: "Vendor alert representation" },
  VaultSafe: { fill: "#1f4a4a", ring: "#5eead4", radius: 13, blurb: "CyberArk safe holding an account" },
  SoftwareReference: { fill: "#5c2a1a", ring: "#fdba74", radius: 13, blurb: "Tool name referenced in a session record" },
  Domain: { fill: "#3a2b52", ring: "#d8b4fe", radius: 14, blurb: "Directory domain or realm named by the source" },
  Process: { fill: "#26483d", ring: "#91d8ad", radius: 14, blurb: "Source-qualified process GUID; observed role retained" },
  Event: { fill: "#3d4149", ring: "#c8d2dd", radius: 11, blurb: "Exact normalized source event" },
  Incident: { fill: "#51412b", ring: "#e2c188", radius: 16, blurb: "Derived public emulation case" },
};

const FALLBACK = { fill: "#243040", ring: "#7f96a7", radius: 10, blurb: "Ontology entity" };
const styleFor = (label: string) => LABEL_STYLE[label] ?? FALLBACK;

/** Direction is meaningful in this ontology, so every edge gets a plain-language reading. */
const EDGE_READING: Record<string, string> = {
  POSSIBLY_SAME_AS: "may be the same object as (unconfirmed)",
  SPN_FOR_HOST: "is the service principal of",
  RESOLVES_TO_HOST: "names",
  MONITORS_HOST: "reports telemetry for",
  CUSTODIES_ACCOUNT: "holds the credentials for",
  MEMBER_OF_DOMAIN: "belongs to",
  AUTHENTICATED_TO: "authenticated to",
  REQUESTED_SERVICE: "requested a ticket for",
  SIGNED_IN_FROM: "signed in from",
  HAS_ADDRESS: "was observed at",
  QUERIED: "resolved",
  RESOLVED_BY: "was answered by",
  CONNECTED_TO: "connected to",
  USED_APPLICATION: "carried traffic for",
  OPENED_SESSION: "opened",
  SESSION_ON_HOST: "ran on",
  OBSERVED_BY: "was reported by",
  ALERT_ON_HOST: "was raised on",
  ALERT_NAMES_IDENTITY: "names",
  USED_ACCOUNT: "checked out",
  RETRIEVED_FROM_SAFE: "was retrieved from",
  REFERENCED_SOFTWARE: "referenced",
  PROCESS_ON_HOST: "was referenced on",
  EXECUTED_AS: "executed as",
  PARENT_OF: "was named as parent of",
  EVIDENCES_ENTITY: "provides evidence for",
  CONTAINS_EVENT: "contains",
  HAS_ALARM: "has derived alarm",
  SUPPORTED_BY: "is supported by",
};

const SCOPE_STEPS: [GraphScope, string, string][] = [
  ["only", "only these", "Just the selected entities and the relationships between them"],
  ["shared", "+ shared", "Adds the entities two or more selections both reach"],
  ["all", "+ neighbours", "Adds everything each selection reaches"],
];

interface Slice { nodes: Map<string, GraphNode>; edges: Map<string, GraphEdge>; }

interface Props {
  scenarioWindow: { id: number; start: string; end: string; label: string } | null;
  focusRequest: { id: number; nodeId: string; name: string } | null;
  selectionRequest: { id: number; ids: string[] } | null;
  wide?: boolean;
  onEvidence?: (resourceId: string) => void;
}

export function GraphPanel({ scenarioWindow, focusRequest, selectionRequest, wide = false, onEvidence }: Props) {
  const width = wide ? WIDE_WIDTH : WIDTH;
  const height = wide ? WIDE_HEIGHT : HEIGHT;
  const [status, setStatus] = useState<GraphStatus | null>(null);
  const [overview, setOverview] = useState<GraphOverview | null>(null);
  const [slice, setSlice] = useState<Slice>({ nodes: new Map(), edges: new Map() });
  const [positions, setPositions] = useState<Map<string, LayoutNode>>(new Map());
  const [selected, setSelected] = useState<GraphNode | null>(null);
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [expanding, setExpanding] = useState("");
  const [error, setError] = useState("");
  const [term, setTerm] = useState("");
  const [matches, setMatches] = useState<GraphNode[]>([]);
  const [attempt, setAttempt] = useState(0);
  const [timeWindow, setTimeWindow] = useState<TimeWindow | null>(null);
  const [followed, setFollowed] = useState("");
  const [hovered, setHovered] = useState<{ id: string; edge: GraphEdge; rect: DOMRect } | null>(null);
  const [peeked, setPeeked] = useState<{ node: GraphNode; rect: DOMRect } | null>(null);
  const [focusId, setFocusId] = useState("");
  const [depth, setDepth] = useState(1);
  const [chosen, setChosen] = useState<string[]>([]);
  const [scope, setScope] = useState<GraphScope>("only");
  const [shared, setShared] = useState<Set<string>>(new Set());
  const appliedFocus = useRef(0);
  const appliedSelection = useRef(0);
  const placed = useRef<Map<string, LayoutNode>>(new Map());
  const appliedScenario = useRef(0);
  const stage = useRef<SVGSVGElement>(null);
  const [view, setView] = useState({ scale: 1, x: 0, y: 0 });
  const pan = useRef<{ x: number; y: number; vx: number; vy: number } | null>(null);
  const nodeDrag = useRef<{ id: string; moved: boolean } | null>(null);

  /** Client pixels to SVG user units, which is the space positions are stored in. */
  const toUser = useCallback((clientX: number, clientY: number) => {
    const svg = stage.current;
    if (!svg) return { x: 0, y: 0 };
    const matrix = svg.getScreenCTM();
    if (!matrix) return { x: 0, y: 0 };
    const point = new DOMPoint(clientX, clientY).matrixTransform(matrix.inverse());
    return { x: point.x, y: point.y };
  }, []);

  const zoomBy = useCallback((factor: number, anchor?: { x: number; y: number }) => {
    setView((current) => {
      const scale = Math.min(4, Math.max(0.35, current.scale * factor));
      if (!anchor) return { ...current, scale };
      // Keep the point under the cursor fixed while the scale changes.
      return {
        scale,
        x: anchor.x - ((anchor.x - current.x) / current.scale) * scale,
        y: anchor.y - ((anchor.y - current.y) / current.scale) * scale,
      };
    });
  }, []);

  // Choosing a scenario in the scanner moves the graph to the same interval, so both
  // panels always describe the same slice of the replay.
  useEffect(() => {
    if (!scenarioWindow || scenarioWindow.id === appliedScenario.current) return;
    appliedScenario.current = scenarioWindow.id;
    setTimeWindow({ start: scenarioWindow.start.slice(0, 16), end: scenarioWindow.end.slice(0, 16) });
    setFollowed(scenarioWindow.label);
  }, [scenarioWindow]);

  const retry = useCallback(() => {
    placed.current = new Map();
    setError(""); setStatus(null); setLoading(true); setAttempt((value) => value + 1);
  }, []);

  const merge = useCallback((nodes: GraphNode[], edges: GraphEdge[], replace = false) => {
    setSlice((current) => {
      const nextNodes = replace ? new Map<string, GraphNode>() : new Map(current.nodes);
      const nextEdges = replace ? new Map<string, GraphEdge>() : new Map(current.edges);
      for (const node of nodes) nextNodes.set(node.id, node);
      for (const edge of edges) if (nextNodes.has(edge.from) && nextNodes.has(edge.to)) nextEdges.set(edge.id, edge);
      return { nodes: nextNodes, edges: nextEdges };
    });
  }, []);

  useEffect(() => {
    let cancelled = false;
    api.graphStatus()
      .then((value) => {
        if (cancelled) return;
        setStatus(value);
        if (!value.available) { setLoading(false); return; }
        return api.graphOverview().then((summary) => { if (!cancelled) setOverview(summary); });
      })
      .catch((err: Error) => !cancelled && setError(err.message))
      .finally(() => !cancelled && setLoading(false));
    return () => { cancelled = true; };
  }, [attempt]);

  // One fetcher for the canvas. Focus, depth, and window are inputs to it rather than
  // separate requests, so a late core response cannot overwrite a pending focus.
  useEffect(() => {
    if (!status?.available) return;
    let cancelled = false;
    const pending = chosen.length > 0
      ? api.graphSelection(chosen, timeWindow ?? undefined, depth, scope)
      : focusId
        ? api.graphNode(focusId, timeWindow ?? undefined, 220, depth)
        : api.graphCore(timeWindow ?? undefined);
    pending
      .then((slice) => {
        if (cancelled) return;
        merge(slice.nodes, slice.edges, true);
        setShared(new Set(slice.shared ?? []));
        if (focusId) setSelected(slice.nodes.find((node) => node.id === focusId) ?? null);
      })
      .catch((err: Error) => !cancelled && setError(err.message));
    return () => { cancelled = true; };
  }, [timeWindow, focusId, chosen, depth, scope, status?.available, merge]);

  // The tray hands over several entities at once. It opens on the picks and the relationships
  // between them; widening to their reach is a deliberate second step.
  useEffect(() => {
    if (!selectionRequest || selectionRequest.id === appliedSelection.current) return;
    appliedSelection.current = selectionRequest.id;
    placed.current = new Map();
    setView({ scale: 1, x: 0, y: 0 });
    setHidden(new Set());
    setSelected(null);
    setFocusId("");
    setDepth(1);
    setScope("only");
    setChosen(selectionRequest.ids);
  }, [selectionRequest]);

  // An entity mentioned in the analysis opens here at second-order reach.
  useEffect(() => {
    if (!focusRequest || focusRequest.id === appliedFocus.current) return;
    appliedFocus.current = focusRequest.id;
    placed.current = new Map();
    setView({ scale: 1, x: 0, y: 0 });
    setHidden(new Set());
    setChosen([]);
    setDepth((current) => (current > 1 ? current : 2));
    setFocusId(focusRequest.nodeId);
  }, [focusRequest]);

  // React attaches wheel passively, which forbids preventDefault, so bind it directly.
  useEffect(() => {
    const svg = stage.current;
    if (!svg) return;
    const onWheel = (event: WheelEvent) => {
      event.preventDefault();
      zoomBy(event.deltaY < 0 ? 1.12 : 0.89, toUser(event.clientX, event.clientY));
    };
    svg.addEventListener("wheel", onWheel, { passive: false });
    return () => svg.removeEventListener("wheel", onWheel);
  }, [zoomBy, toUser, loading, status?.available]);

  const visible = useMemo(() => {
    const shown = [...slice.nodes.values()].filter((node) => !hidden.has(node.label));
    const ids = new Set(shown.map((node) => node.id));
    const edges = [...slice.edges.values()].filter((edge) => ids.has(edge.from) && ids.has(edge.to));
    // An entity with no visible relationship is a dot with nothing to say: it is on screen
    // only because of an edge the current window or class filter removed. A picked entity is
    // the exception - its absence of relationships is itself the answer.
    const connected = new Set<string>(focusId ? [focusId, ...chosen] : chosen);
    for (const edge of edges) { connected.add(edge.from); connected.add(edge.to); }
    const nodes = shown.filter((node) => connected.has(node.id));
    return { nodes, edges, hiddenOrphans: shown.length - nodes.length };
  }, [slice, hidden, focusId, chosen]);

  useEffect(() => {
    if (visible.nodes.length === 0) { setPositions(new Map()); return; }
    const next = layout(
      visible.nodes.map((node) => node.id),
      visible.edges.map((edge) => ({ from: edge.from, to: edge.to })),
      width, height, placed.current,
      new Map(visible.nodes.map((node) => [node.id, shortLabel(node).length * 9])),
    );
    placed.current = next;
    setPositions(next);
  }, [visible, width, height]);

  // A different canvas shape needs a fresh layout, not the old one stretched.
  useEffect(() => {
    placed.current = new Map();
    setView({ scale: 1, x: 0, y: 0 });
  }, [width, height]);

  const readingOf = (edge: GraphEdge) =>
    EDGE_READING[edge.label] ?? edge.label.toLowerCase().replace(/_/g, " ");
  const chipWidth = (reading: string) => reading.length * 6.2 + 20;

  const labelSpots = useMemo(() => placeEdgeLabels(
    visible.edges.map((edge) => ({
      id: edge.id, from: edge.from, to: edge.to,
      w: chipWidth(readingOf(edge)), h: 21,
    })),
    positions,
    visible.nodes
      .map((node) => {
        const spot = positions.get(node.id);
        if (!spot) return null;
        const style = styleFor(node.label);
        // The node's footprint is its circle plus the two label lines beneath it.
        const width = Math.max(style.radius * 2, node.name.length * 7.4, node.label.length * 6);
        return { x: spot.x, y: spot.y + 10, w: width, h: style.radius * 2 + 34 };
      })
      .filter((box): box is { x: number; y: number; w: number; h: number } => box !== null),
    width, height,
  ), [visible, positions, width, height]);

  function expand(node: GraphNode) {
    setSelected(node);
    setExpanding(node.id);
    api.graphNode(node.id, timeWindow ?? undefined)
      .then((value) => merge(value.nodes, value.edges))
      .catch((err: Error) => setError(err.message))
      .finally(() => setExpanding(""));
  }

  function focusOnly(node: GraphNode) {
    placed.current = new Map();
    setChosen([]);
    setSelected(node);
    setFocusId(node.id);
  }

  function runSearch(value: string) {
    setTerm(value);
    if (value.trim().length < 2) { setMatches([]); return; }
    api.graphSearch(value).then(setMatches).catch(() => setMatches([]));
  }

  function moveNode(id: string, clientX: number, clientY: number) {
    const spot = toUser(clientX, clientY);
    const node = placed.current.get(id);
    if (!node) return;
    node.x = (spot.x - view.x) / view.scale;
    node.y = (spot.y - view.y) / view.scale;
    node.pinned = true;
    setPositions(new Map(placed.current));
  }

  function onStageMove(event: React.PointerEvent<SVGSVGElement>) {
    if (nodeDrag.current) {
      nodeDrag.current.moved = true;
      moveNode(nodeDrag.current.id, event.clientX, event.clientY);
      return;
    }
    // Read the ref before the state updater runs: pointerup can clear it in between.
    const origin = pan.current;
    if (!origin) return;
    setView((current) => ({
      ...current,
      x: origin.vx + (event.clientX - origin.x),
      y: origin.vy + (event.clientY - origin.y),
    }));
  }

  function endDrag() {
    pan.current = null;
    nodeDrag.current = null;
  }

  if (loading) return <div className="graph-state"><Loader2 className="spin" size={16} /> Reading the ontology graph…</div>;
  if (status && !status.available) {
    const dropped = /closed|reset|timed out|timeout|broken pipe/i.test(status.detail ?? "");
    return (
      <div className="graph-state error">
        <b>Graph unavailable</b>
        <p>{status.detail ?? "The Cosmos DB Gremlin graph is not reachable from this backend."}</p>
        <p className="graph-hint">
          {dropped
            ? "Cosmos closes an idle Gremlin websocket. Retrying reconnects it."
            : <>Build and load it with <code>build_ontology.py</code> then <code>load_to_gremlin.py</code>, and start the backend with <code>gremlin.env</code> sourced.</>}
        </p>
        <button type="button" className="graph-reset" onClick={retry}>
          <RefreshCw size={12} /> Retry
        </button>
      </div>
    );
  }

  const counts = overview?.nodes_by_label ?? {};
  const shownLabels = Object.keys(counts).sort();

  return (
    <div className="graph-panel">
      <div className="graph-toolbar">
        <label className="graph-search">
          <Search size={13} />
          <input
            value={term} placeholder="Find a host, account, address, or name…"
            onChange={(event) => runSearch(event.target.value)}
            aria-label="Search the ontology graph"
          />
          {term && <button type="button" aria-label="Clear search" onClick={() => runSearch("")}><X size={12} /></button>}
        </label>
        <button type="button" className="graph-reset" onClick={() => {
          placed.current = new Map(); setSelected(null); setHidden(new Set()); setFocusId("");
          setChosen([]); setShared(new Set()); setScope("only");
          setView({ scale: 1, x: 0, y: 0 });
        }}><Maximize2 size={12} /> Reset to core</button>
        {chosen.length > 0 && <span className="graph-scope" role="group" aria-label="How much of the selection to draw">
          show
          {SCOPE_STEPS.map(([key, label, hint]) => (
            <button
              key={key} type="button" className={scope === key ? "on" : ""}
              aria-pressed={scope === key} title={hint}
              onClick={() => { placed.current = new Map(); setScope(key); }}
            >{label}</button>
          ))}
        </span>}
        {(focusId || (chosen.length > 0 && scope !== "only")) && <span className="graph-depth" role="group" aria-label="Relationship reach from the focused entity">
          reach
          {[1, 2, 3].map((step) => (
            <button
              key={step} type="button" className={depth === step ? "on" : ""}
              aria-pressed={depth === step}
              title={`${step === 1 ? "Direct" : `${step} hops of`} relationships from the focused entity`}
              onClick={() => setDepth(step)}
            >{step}</button>
          ))}
        </span>}
        <span className="graph-scale">
          {status?.vertices ?? 0} vertices · {status?.edges ?? 0} edges in Cosmos · showing {visible.nodes.length} nodes, {visible.edges.length} relationship{visible.edges.length === 1 ? "" : "s"}
          {visible.hiddenOrphans > 0 && ` · ${visible.hiddenOrphans} with no relationship here hidden`}
          {visible.edges.length > labelSpots.size && ` · ${visible.edges.length - labelSpots.size} label${visible.edges.length - labelSpots.size === 1 ? "" : "s"} too crowded to place`}
          {chosen.length > 1 && ` · ${shared.size} shared by all ${chosen.length}`}
        </span>
      </div>

      {overview?.observed_window?.start && <TimeWindowControl
        extentStart={overview.observed_window.start}
        extentEnd={overview.observed_window.end}
        window={timeWindow}
        eventEdgeCount={visible.edges.filter((edge) => edge.kind === "event").length}
        followedScenario={followed}
        onChange={(next) => { setFollowed(""); setTimeWindow(next); }}
      />}

      {matches.length > 0 && (
        <ul className="graph-matches">
          {matches.slice(0, 8).map((node) => (
            <li key={node.id}>
              <button type="button" onClick={() => { focusOnly(node); setMatches([]); setTerm(""); }}>
                <i style={{ background: styleFor(node.label).ring }} />
                <b>{node.name}</b><small>{node.label}</small><span>{node.event_count} events</span>
              </button>
            </li>
          ))}
        </ul>
      )}

      <div className="graph-legend" role="group" aria-label="Entity classes — select to show or hide">
        {shownLabels.map((label) => {
          const style = styleFor(label);
          const off = hidden.has(label);
          return (
            <button
              key={label} type="button" className={`graph-chip ${off ? "off" : ""}`}
              aria-pressed={!off} title={style.blurb}
              onClick={() => setHidden((current) => {
                const next = new Set(current);
                if (next.has(label)) next.delete(label); else next.add(label);
                return next;
              })}
            >
              <i style={{ background: style.ring }} />{label}<span>{counts[label] ?? 0}</span>
            </button>
          );
        })}
      </div>

      <div className="graph-stage">
        <div className="graph-nav" role="group" aria-label="Graph viewport">
          <button type="button" onClick={() => zoomBy(1.25)} aria-label="Zoom in"><ZoomIn size={13} /></button>
          <button type="button" onClick={() => zoomBy(0.8)} aria-label="Zoom out"><ZoomOut size={13} /></button>
          <button type="button" onClick={() => { setView({ scale: 1, x: 0, y: 0 }); }} aria-label="Reset the view"><Locate size={13} /></button>
          <span>{Math.round(view.scale * 100)}%</span>
        </div>
        <svg
          ref={stage}
          viewBox={`0 0 ${width} ${height}`}
          role="application"
          aria-label="Ontology relationship graph. Drag to pan, scroll to zoom, drag a node to move it."
          onPointerDown={(event) => {
            if (nodeDrag.current) return;
            pan.current = { x: event.clientX, y: event.clientY, vx: view.x, vy: view.y };
            event.currentTarget.setPointerCapture(event.pointerId);
          }}
          onPointerMove={onStageMove}
          onPointerUp={(event) => {
            if (event.currentTarget.hasPointerCapture(event.pointerId)) {
              event.currentTarget.releasePointerCapture(event.pointerId);
            }
            endDrag();
          }}
          onPointerCancel={endDrag}
        >
          <defs>
            <marker id="graph-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
              <path d="M0 0 L10 5 L0 10 z" fill="#3c5a6d" />
            </marker>
          </defs>
          <g transform={`translate(${view.x} ${view.y}) scale(${view.scale})`}>
            {visible.edges.map((edge) => {
              const from = positions.get(edge.from);
              const to = positions.get(edge.to);
              if (!from || !to) return null;
              const active = selected && (edge.from === selected.id || edge.to === selected.id);
              const structural = edge.kind === "structural";
              const reading = readingOf(edge);
              const spot = labelSpots.get(edge.id);
              const boxWidth = chipWidth(reading);
              // No collision-free slot: draw the relationship, not an unreadable pile of text.
              const mx = spot?.x ?? (from.x + to.x) / 2;
              const my = spot?.y ?? (from.y + to.y) / 2;
              return (
                <g
                  key={edge.id}
                  className={`graph-edge ${edge.kind} ${active ? "active" : ""} ${hovered?.id === edge.id ? "hovered" : ""}`}
                >
                  <line
                    x1={from.x} y1={from.y} x2={to.x} y2={to.y}
                    strokeDasharray={edge.label === "POSSIBLY_SAME_AS" ? "5 4" : structural ? "2 3" : undefined}
                    markerEnd="url(#graph-arrow)"
                  />
                  {/* The label box is the hover target: a 1px stroke is not a usable one. */}
                  <g
                    className="graph-edge-chip"
                    onMouseEnter={(event) => setHovered({ id: edge.id, edge, rect: boxOf(event.currentTarget) })}
                    onMouseLeave={() => setHovered((current) => (current?.id === edge.id ? null : current))}
                  >
                    <rect
                      x={mx - boxWidth / 2} y={my - 10.5} width={boxWidth} height={21} rx={5}
                      className={spot ? "" : "bare"}
                    />
                    {spot && <text className="graph-edge-label" x={mx} y={my + 4} textAnchor="middle">{reading}</text>}
                  </g>
                </g>
              );
            })}
            {visible.nodes.map((node) => {
              const spot = positions.get(node.id);
              if (!spot) return null;
              const style = styleFor(node.label);
              const isSelected = selected?.id === node.id;
              const isChosen = chosen.includes(node.id);
              const isShared = shared.has(node.id);
              return (
                <g
                  key={node.id}
                  className={`graph-node ${isSelected ? "selected" : ""} ${isChosen ? "chosen" : ""} ${isShared ? "shared" : ""} ${expanding === node.id ? "busy" : ""}`}
                  transform={`translate(${spot.x} ${spot.y})`}
                  tabIndex={0} role="button"
                  aria-label={`${node.label} ${node.name}, ${node.event_count} events. Activate to expand its relationships.`}
                  onPointerDown={(event) => {
                    event.stopPropagation();
                    nodeDrag.current = { id: node.id, moved: false };
                    event.currentTarget.setPointerCapture(event.pointerId);
                  }}
                  onPointerMove={(event) => {
                    if (nodeDrag.current?.id !== node.id) return;
                    event.stopPropagation();
                    nodeDrag.current.moved = true;
                    moveNode(node.id, event.clientX, event.clientY);
                  }}
                  onPointerUp={(event) => {
                    event.stopPropagation();
                    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
                      event.currentTarget.releasePointerCapture(event.pointerId);
                    }
                    const wasDrag = nodeDrag.current?.moved;
                    nodeDrag.current = null;
                    if (!wasDrag) expand(node);
                  }}
                  onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); expand(node); } }}
                >
                  {isChosen && <circle className="graph-ring chosen" r={style.radius + 6} />}
                  {isShared && !isChosen && <circle className="graph-ring shared" r={style.radius + 4} />}
                  <circle
                    r={style.radius} fill={style.fill} stroke={style.ring} strokeWidth={isSelected ? 3 : 1.5}
                    onMouseEnter={(event) => setPeeked({ node, rect: boxOf(event.currentTarget) })}
                    onMouseLeave={() => setPeeked((current) => (current?.node.id === node.id ? null : current))}
                  />
                  <text className="graph-node-name" y={style.radius + 15} textAnchor="middle">{shortLabel(node)}</text>
                  <text className="graph-node-class" y={style.radius + 28} textAnchor="middle" fill={style.ring}>{node.label}</text>
                </g>
              );
            })}
          </g>
        </svg>
        {visible.nodes.length === 0 && <p className="graph-state">
          {hidden.size > 0
            ? "Every remaining class is hidden. Re-enable one above."
            : "No entity has a relationship in this window. Widen it or switch to Structural."}
        </p>}
        {hovered && <AnchoredTip rect={hovered.rect} className="edge-tip">
          <EdgeTipBody edge={hovered.edge} name={(id: string) => slice.nodes.get(id)?.name ?? id} />
        </AnchoredTip>}
        {peeked && !hovered && <AnchoredTip rect={peeked.rect} className="node-tip">
          <NodeTipBody node={peeked.node} />
        </AnchoredTip>}
      </div>

      {selected && <NodeDetail
        node={selected}
        edges={[...slice.edges.values()].filter((edge) => edge.from === selected.id || edge.to === selected.id)}
        nodes={slice.nodes}
        onOpen={(node) => focusOnly(node)}
        onClose={() => setSelected(null)}
        onEvidence={onEvidence}
      />}
      {error && <div className="error-box">{error}<button type="button" className="graph-reset" onClick={retry}><RefreshCw size={12} /> Retry</button></div>}
    </div>
  );
}

function NodeDetail({ node, edges, nodes, onOpen, onClose, onEvidence }: {
  node: GraphNode; edges: GraphEdge[]; nodes: Map<string, GraphNode>;
  onOpen: (node: GraphNode) => void; onClose: () => void;
  onEvidence?: (resourceId: string) => void;
}) {
  const style = styleFor(node.label);
  return (
    <section className="graph-detail" aria-label={`${node.name} detail`}>
      <header>
        <i style={{ background: style.ring }} />
        <div><b>{node.name}</b><small>{node.label} · {style.blurb}</small></div>
        <button type="button" onClick={onClose} aria-label="Close detail"><X size={13} /></button>
      </header>
      <dl className="graph-facts">
        <div><dt>Entity ID</dt><dd>{node.id}</dd></div>
        <div><dt>Events</dt><dd>{node.event_count}</dd></div>
        <div><dt>First seen</dt><dd>{node.first_seen || "—"}</dd></div>
        <div><dt>Last seen</dt><dd>{node.last_seen || "—"}</dd></div>
        {Object.entries(node.properties).map(([key, value]) => (
          <div key={key}><dt>{key.replace(/_/g, " ")}</dt><dd>{key === "evidence_refs" && Array.isArray(value) && onEvidence
            ? value.map((ref) => <button className="public-graph-evidence" type="button" key={String(ref)}
                onClick={() => onEvidence(String(ref))}>{String(ref)}</button>) : formatValue(value)}</dd></div>
        ))}
      </dl>
      <b className="graph-rel-title">Relationships in view ({edges.length})</b>
      <ul className="graph-relations">
        {[...edges].sort((a, b) => (a.kind === b.kind ? 0 : a.kind === "structural" ? -1 : 1)).map((edge) => {
          const outbound = edge.from === node.id;
          const other = nodes.get(outbound ? edge.to : edge.from);
          const reading = EDGE_READING[edge.label] ?? edge.label.toLowerCase().replace(/_/g, " ");
          const subject = outbound ? node.name : (other?.name ?? "unknown");
          const object = outbound ? (other?.name ?? "unknown") : node.name;
          const structural = edge.kind === "structural";
          return (
            <li key={edge.id} className={edge.kind}>
              <span className="graph-rel-line">
                <em>{subject}</em> <b>{reading}</b> <em>{object}</em>
              </span>
              <span className="graph-rel-meta">
                <i className={`graph-kind ${edge.kind}`}>{structural ? "timeless" : "event"}</i>
                {structural
                  ? String(edge.properties.basis ?? "derived from the export")
                  : `${edge.event_count} event${edge.event_count === 1 ? "" : "s"}${edge.window_scoped ? " in window" : ""}`}
                {other ? ` · ${other.label}` : ""}
                {other && <button type="button" onClick={() => onOpen(other)}><Crosshair size={11} /> focus {other.name}</button>}
              </span>
              {Object.entries(edge.properties).length > 0 && !structural && (
                <span className="graph-rel-props">
                  {Object.entries(edge.properties).map(([key, value]) => `${key.replace(/_/g, " ")}: ${formatValue(value)}`).join(" · ")}
                </span>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

/** A DOMRect for an SVG element, usable directly as a fixed-position anchor. */
function boxOf(element: SVGGraphicsElement): DOMRect {
  return element.getBoundingClientRect();
}

/** Places a tooltip beside the element it describes, clamped into the viewport. */
function AnchoredTip({ rect, className, children }: {
  rect: DOMRect; className: string; children: ReactNode;
}) {
  const panel = useRef<HTMLDivElement>(null);
  const [box, setBox] = useState({ top: -9999, left: -9999 });

  useLayoutEffect(() => {
    const width = panel.current?.offsetWidth ?? 300;
    const height = panel.current?.offsetHeight ?? 120;
    const gap = 14;
    const left = Math.min(Math.max(rect.left + rect.width / 2 - width / 2, 10), window.innerWidth - width - 10);
    const below = rect.bottom + gap;
    setBox({ left, top: below + height > window.innerHeight - 10 ? Math.max(10, rect.top - height - gap) : below });
  }, [rect]);

  return <div ref={panel} className={className} role="tooltip" style={box}>{children}</div>;
}

function NodeTipBody({ node }: { node: GraphNode }) {
  const style = styleFor(node.label);
  const entries = Object.entries(node.properties)
    .filter(([, value]) => value !== "" && value !== null)
    .slice(0, 4);
  return (
    <>
      <span className="edge-tip-line"><em>{node.name}</em></span>
      <span className="edge-tip-meta">
        <i className="graph-kind structural" style={{ background: "none", color: style.ring }}>{node.label}</i>
        <code>{node.event_count} events</code>
      </span>
      <p className="edge-tip-detail">{style.blurb}</p>
      {node.first_seen && (
        <p className="edge-tip-detail mono">{node.first_seen.slice(0, 19)}Z → {node.last_seen.slice(0, 19)}Z</p>
      )}
      {entries.map(([key, value]) => (
        <p className="edge-tip-detail" key={key}>
          <span className="edge-tip-key">{key.replace(/_/g, " ")}</span> {formatValue(value).slice(0, 90)}
        </p>
      ))}
      <p className="edge-tip-detail hint">Click to expand · drag to move</p>
    </>
  );
}

function EdgeTipBody({ edge, name }: { edge: GraphEdge; name: (id: string) => string }) {
  const reading = EDGE_READING[edge.label] ?? edge.label.toLowerCase().replace(/_/g, " ");
  const structural = edge.kind === "structural";
  return (
    <>
      <span className="edge-tip-line">
        <em>{name(edge.from)}</em> <b>{reading}</b> <em>{name(edge.to)}</em>
      </span>
      <span className="edge-tip-meta">
        <i className={`graph-kind ${edge.kind}`}>{structural ? "timeless" : "event"}</i>
        <code>{edge.label}</code>
      </span>
      <p className="edge-tip-detail">
        {structural
          ? String(edge.properties.basis ?? "derived from the export")
          : `${edge.event_count} event${edge.event_count === 1 ? "" : "s"}${edge.window_scoped ? " in the selected window" : " across the export"}`}
      </p>
      {!structural && edge.first_seen && (
        <p className="edge-tip-detail mono">{edge.first_seen.slice(0, 19)}Z → {edge.last_seen.slice(0, 19)}Z</p>
      )}
      {structural && edge.properties.confirmed_by !== undefined && (
        <p className="edge-tip-detail warn">Unconfirmed: {String(edge.properties.confirmed_by)}</p>
      )}
    </>
  );
}

function shortLabel(node: GraphNode): string {
  // Session handles and long DNS names are opaque at circle size; the detail panel carries them in full.
  if (node.label === "Session") return `session ${node.name.replace(/^0x/, "").slice(0, 6)}…`;
  return node.name.length > 24 ? `${node.name.slice(0, 23)}…` : node.name;
}

function formatValue(value: unknown): string {
  if (Array.isArray(value)) return value.map(String).join(", ");
  if (value !== null && typeof value === "object") return JSON.stringify(value);
  const text = String(value ?? "");
  if (text.startsWith("[") && text.endsWith("]")) {
    try { return (JSON.parse(text) as unknown[]).map(String).join(", "); } catch { return text; }
  }
  return text;
}
