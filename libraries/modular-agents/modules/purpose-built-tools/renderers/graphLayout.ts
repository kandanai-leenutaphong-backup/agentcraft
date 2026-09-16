/**
 * graphLayout — deterministic positions for a node/edge set.
 *
 * WHY DETERMINISTIC
 * -----------------
 * A force-directed layout looks better and cannot be asserted: the same graph
 * renders differently on every mount, so a test can only check that *some*
 * circles exist. This layout is a pure function of the data, so the same graph
 * always produces the same coordinates — which makes the view testable, makes
 * a screenshot diff meaningful, and stops the picture reshuffling under a
 * reader every time the panel re-renders.
 *
 * THE LAYOUT
 * ----------
 * Layered, left to right. Roots — nodes no edge points at — go in the first
 * column, their targets in the second, and so on by breadth-first depth. A
 * cycle cannot starve the layout: anything unreached after the walk is placed
 * in a final column rather than dropped, because a node that is missing from
 * the picture is worse than a node in the wrong column.
 *
 * No dependency. The whole layout is arithmetic over the node list.
 */

/** One node, after the source keys have been normalised. */
export interface LayoutNode {
  id: string;
  label: string;
  kind: string;
  depth: number;
  x: number;
  y: number;
  raw: Record<string, unknown>;
}

/** One edge, resolved to the ids it connects. */
export interface LayoutEdge {
  source: string;
  target: string;
  label: string;
}

export interface GraphLayout {
  nodes: LayoutNode[];
  edges: LayoutEdge[];
  width: number;
  height: number;
  /** Nodes named by an edge that were never defined. Reported, never invented. */
  danglingEdges: LayoutEdge[];
}

/** Keys accepted for a node's identity, in order of preference. */
const ID_KEYS = ["id", "name", "key", "node_id", "nodeId"];
/** Keys accepted for the display label. */
const LABEL_KEYS = ["label", "name", "title", "id"];
/** Keys accepted for the node's type, which drives its colour. */
const KIND_KEYS = ["kind", "type", "category", "class", "role"];
/** Keys accepted for an edge's endpoints. */
const SOURCE_KEYS = ["source", "from", "src", "start", "parent"];
const TARGET_KEYS = ["target", "to", "dst", "end", "child"];
const EDGE_LABEL_KEYS = ["label", "relation", "type", "kind"];

const COLUMN_WIDTH = 190;
const ROW_HEIGHT = 74;
const MARGIN_X = 90;
const MARGIN_Y = 46;

function firstString(source: Record<string, unknown>, keys: string[]): string {
  for (const key of keys) {
    const value = source?.[key];
    if (typeof value === "string" && value.trim()) return value;
    if (typeof value === "number") return String(value);
  }
  return "";
}

/** True for a plain object. Arrays are not nodes. */
function isObject(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === "object" && !Array.isArray(value);
}

/**
 * Build the layout.
 *
 * Nodes without a resolvable id are given a positional one rather than being
 * discarded: an unlabelled node is still a node, and dropping it silently
 * changes what the reader believes the traversal returned.
 */
export function buildGraphLayout(
  rawNodes: unknown[],
  rawEdges: unknown[],
): GraphLayout {
  const nodes = rawNodes.filter(isObject).map((raw, index) => {
    const id = firstString(raw, ID_KEYS) || `node-${index}`;
    return {
      id,
      label: firstString(raw, LABEL_KEYS) || id,
      kind: firstString(raw, KIND_KEYS) || "node",
      raw,
    };
  });

  const byId = new Map(nodes.map((node) => [node.id, node]));

  const edges: LayoutEdge[] = [];
  const dangling: LayoutEdge[] = [];
  for (const raw of rawEdges.filter(isObject)) {
    const edge: LayoutEdge = {
      source: firstString(raw, SOURCE_KEYS),
      target: firstString(raw, TARGET_KEYS),
      label: firstString(raw, EDGE_LABEL_KEYS),
    };
    if (!edge.source || !edge.target) continue;
    if (byId.has(edge.source) && byId.has(edge.target)) edges.push(edge);
    else dangling.push(edge);
  }

  // Depth by breadth-first walk from the roots. Insertion order decides ties,
  // so the result depends only on the input order — never on hash iteration.
  const incoming = new Set(edges.map((edge) => edge.target));
  const depth = new Map<string, number>();
  const queue: string[] = [];
  for (const node of nodes) {
    if (!incoming.has(node.id)) {
      depth.set(node.id, 0);
      queue.push(node.id);
    }
  }

  const outgoing = new Map<string, string[]>();
  for (const edge of edges) {
    const list = outgoing.get(edge.source) ?? [];
    list.push(edge.target);
    outgoing.set(edge.source, list);
  }

  while (queue.length) {
    const current = queue.shift() as string;
    const currentDepth = depth.get(current) ?? 0;
    for (const next of outgoing.get(current) ?? []) {
      if (depth.has(next)) continue;
      depth.set(next, currentDepth + 1);
      queue.push(next);
    }
  }

  // A cycle with no root leaves nodes unvisited. They go in a trailing column.
  const maxDepth = Math.max(0, ...Array.from(depth.values()));
  const orphanDepth = depth.size === nodes.length ? maxDepth : maxDepth + 1;
  for (const node of nodes) {
    if (!depth.has(node.id)) depth.set(node.id, orphanDepth);
  }

  const columns = new Map<number, string[]>();
  for (const node of nodes) {
    const level = depth.get(node.id) ?? 0;
    const column = columns.get(level) ?? [];
    column.push(node.id);
    columns.set(level, column);
  }

  const positioned: LayoutNode[] = [];
  const tallest = Math.max(1, ...Array.from(columns.values(), (c) => c.length));
  for (const [level, ids] of Array.from(columns.entries()).sort((a, b) => a[0] - b[0])) {
    ids.forEach((id, row) => {
      const node = byId.get(id);
      if (!node) return;
      // Columns are centred against the tallest one, so a two-node column sits
      // beside the middle of a six-node column rather than at its top.
      const offset = (tallest - ids.length) / 2;
      positioned.push({
        ...node,
        depth: level,
        x: MARGIN_X + level * COLUMN_WIDTH,
        y: MARGIN_Y + (row + offset) * ROW_HEIGHT,
      });
    });
  }

  return {
    nodes: positioned,
    edges,
    danglingEdges: dangling,
    width: MARGIN_X * 2 + Math.max(0, columns.size - 1) * COLUMN_WIDTH,
    height: MARGIN_Y * 2 + Math.max(0, tallest - 1) * ROW_HEIGHT,
  };
}

/** Stable colour index for a node kind, so a kind keeps its colour across renders. */
export function kindIndex(kind: string, kinds: string[]): number {
  const position = kinds.indexOf(kind);
  return position < 0 ? 0 : position % 6;
}

/** Every distinct kind, in first-seen order — the legend's order. */
export function distinctKinds(nodes: LayoutNode[]): string[] {
  const seen: string[] = [];
  for (const node of nodes) {
    if (!seen.includes(node.kind)) seen.push(node.kind);
  }
  return seen;
}
