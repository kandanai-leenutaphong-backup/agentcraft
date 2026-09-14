/**
 * GraphView — the visual half of the graph archetype.
 *
 * Renders the deterministic layout from `graphLayout` as SVG: one circle per
 * node, one line per edge, a legend for the kinds. Selecting a node dims
 * everything it does not touch, which is the one interaction a topology view
 * actually needs — "what is connected to this?" — and the one a table cannot
 * answer at a glance.
 *
 * No graph library. A layered layout, six colours and a click handler do not
 * justify a dependency, and a dependency here would be the largest thing in
 * the box.
 */

import { useMemo, useState } from "react";
import {
  buildGraphLayout,
  distinctKinds,
  kindIndex,
  type LayoutEdge,
  type LayoutNode,
} from "./graphLayout";

/** Six kind colours, cycled. Distinguishable, and readable on a dark panel. */
const KIND_COLOURS = [
  "#38bdf8", "#a78bfa", "#34d399", "#fbbf24", "#fb7185", "#94a3b8",
];

const NODE_RADIUS = 17;

export interface GraphViewProps {
  nodes: unknown[];
  edges: unknown[];
  /** Height cap. The SVG scales to fit rather than growing without bound. */
  maxHeight?: number;
}

export function GraphView({ nodes, edges, maxHeight = 320 }: GraphViewProps) {
  const layout = useMemo(() => buildGraphLayout(nodes, edges), [nodes, edges]);
  const [selected, setSelected] = useState<string | null>(null);

  const kinds = useMemo(() => distinctKinds(layout.nodes), [layout.nodes]);

  if (layout.nodes.length === 0) return null;

  const touching = (edge: LayoutEdge) =>
    !selected || edge.source === selected || edge.target === selected;

  const connected = new Set<string>();
  if (selected) {
    connected.add(selected);
    for (const edge of layout.edges) {
      if (edge.source === selected) connected.add(edge.target);
      if (edge.target === selected) connected.add(edge.source);
    }
  }
  const lit = (node: LayoutNode) => !selected || connected.has(node.id);

  return (
    <div data-testid="graph-view" className="rounded border border-neutral-border bg-neutral-bg2">
      <svg
        role="img"
        aria-label={`Graph of ${layout.nodes.length} nodes and ${layout.edges.length} edges`}
        viewBox={`0 0 ${layout.width} ${layout.height}`}
        style={{ maxHeight, width: "100%" }}
        data-node-count={layout.nodes.length}
        data-edge-count={layout.edges.length}
      >
        {layout.edges.map((edge, index) => {
          const from = layout.nodes.find((n) => n.id === edge.source);
          const to = layout.nodes.find((n) => n.id === edge.target);
          if (!from || !to) return null;
          return (
            <g key={`${edge.source}->${edge.target}-${index}`} opacity={touching(edge) ? 1 : 0.15}>
              <line
                x1={from.x}
                y1={from.y}
                x2={to.x}
                y2={to.y}
                stroke="#64748b"
                strokeWidth={1.4}
              />
              {edge.label && (
                <text
                  x={(from.x + to.x) / 2}
                  y={(from.y + to.y) / 2 - 4}
                  textAnchor="middle"
                  fill="#94a3b8"
                  fontSize={9}
                >
                  {edge.label}
                </text>
              )}
            </g>
          );
        })}

        {layout.nodes.map((node) => (
          <g
            key={node.id}
            data-testid="graph-node"
            data-node-id={node.id}
            opacity={lit(node) ? 1 : 0.2}
            onClick={() => setSelected(selected === node.id ? null : node.id)}
            style={{ cursor: "pointer" }}
          >
            <circle
              cx={node.x}
              cy={node.y}
              r={NODE_RADIUS}
              fill={KIND_COLOURS[kindIndex(node.kind, kinds)]}
              stroke={selected === node.id ? "#f8fafc" : "transparent"}
              strokeWidth={2}
            />
            <text
              x={node.x}
              y={node.y + NODE_RADIUS + 12}
              textAnchor="middle"
              fill="#e2e8f0"
              fontSize={10}
            >
              {node.label}
            </text>
          </g>
        ))}
      </svg>

      <div className="flex flex-wrap items-center gap-3 border-t border-neutral-border px-2 py-1 text-micro text-text-muted">
        {kinds.map((kind) => (
          <span key={kind} className="flex items-center gap-1">
            <span
              className="inline-block h-2 w-2 rounded-full"
              style={{ background: KIND_COLOURS[kindIndex(kind, kinds)] }}
            />
            {kind}
          </span>
        ))}
        {selected && <span className="ml-auto">selected: {selected} — click again to clear</span>}
        {/* An edge naming a node that was never returned is a real finding: the
            traversal is incomplete. Saying so beats drawing a tidy lie. */}
        {layout.danglingEdges.length > 0 && (
          <span className="ml-auto text-status-warning">
            {layout.danglingEdges.length} edge(s) reference nodes not in the result
          </span>
        )}
      </div>
    </div>
  );
}
