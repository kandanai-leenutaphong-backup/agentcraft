/** Minimal force-directed layout: repulsion, edge springs, and centring with damping.
 *
 * Sized for the few hundred nodes an analyst has on screen at once, so it runs a fixed
 * number of ticks synchronously rather than animating a full simulation.
 */

export interface LayoutNode {
  id: string;
  x: number;
  y: number;
  vx: number;
  vy: number;
  pinned?: boolean;
  /** Rendered width of the name drawn beneath the node, in user units. */
  labelWidth?: number;
}

export interface LayoutEdge {
  from: string;
  to: string;
}

interface Options {
  width: number;
  height: number;
  ticks?: number;
  repulsion?: number;
  springLength?: number;
  springStrength?: number;
  centring?: number;
  damping?: number;
}

/** Deterministic placement so a re-render of the same graph does not reshuffle it. */
export function seedPositions(ids: string[], width: number, height: number): Map<string, LayoutNode> {
  const seeded = new Map<string, LayoutNode>();
  const radius = Math.min(width, height) * 0.38;
  ids.forEach((id, index) => {
    const angle = (index / Math.max(ids.length, 1)) * Math.PI * 2;
    const ring = 0.55 + ((index * 37) % 100) / 220;
    seeded.set(id, {
      id,
      x: width / 2 + Math.cos(angle) * radius * ring,
      y: height / 2 + Math.sin(angle) * radius * ring,
      vx: 0, vy: 0,
    });
  });
  return seeded;
}

//: Nodes carry a name and a class label, so they need more clearance than their radius.
const MARGIN_X = 88;
const MARGIN_Y = 44;

const clampX = (value: number, width: number) => Math.min(width - MARGIN_X, Math.max(MARGIN_X, value));
const clampY = (value: number, height: number) => Math.min(height - MARGIN_Y, Math.max(MARGIN_Y, value));

export function relax(
  nodes: Map<string, LayoutNode>,
  edges: LayoutEdge[],
  options: Options,
): Map<string, LayoutNode> {
  const list = [...nodes.values()];
  if (list.length === 0) return nodes;
  const {
    width, height,
    ticks = 320,
    // A dense hub needs more room per node than a sparse one, but uncapped repulsion
    // pins a small graph to the canvas walls instead of spreading it evenly.
    repulsion = Math.max(9000, Math.min(16000, (width * height) / Math.max(list.length, 8) * 1.5)),
    springLength = Math.max(90, Math.min(190, 900 / Math.sqrt(Math.max(list.length, 4)))),
    springStrength = 0.02,
    centring = 0.0035,
    damping = 0.88,
  } = options;

  // Hubs push their spokes further out so a high-degree node does not become a black hole.
  const degree = new Map<string, number>();
  for (const edge of edges) {
    degree.set(edge.from, (degree.get(edge.from) ?? 0) + 1);
    degree.set(edge.to, (degree.get(edge.to) ?? 0) + 1);
  }

  for (let step = 0; step < ticks; step++) {
    for (let i = 0; i < list.length; i++) {
      const a = list[i];
      for (let j = i + 1; j < list.length; j++) {
        const b = list[j];
        let dx = a.x - b.x;
        let dy = a.y - b.y;
        let distanceSquared = dx * dx + dy * dy;
        if (distanceSquared < 0.01) {
          dx = (i % 7) - 3 + 0.5;
          dy = (j % 5) - 2 + 0.5;
          distanceSquared = dx * dx + dy * dy;
        }
        const distance = Math.sqrt(distanceSquared);
        const force = repulsion / distanceSquared;
        const fx = (dx / distance) * force;
        const fy = (dy / distance) * force;
        a.vx += fx; a.vy += fy;
        b.vx -= fx; b.vy -= fy;
      }
    }

    for (const edge of edges) {
      const a = nodes.get(edge.from);
      const b = nodes.get(edge.to);
      if (!a || !b) continue;
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      const distance = Math.max(Math.sqrt(dx * dx + dy * dy), 0.01);
      const busiest = Math.max(degree.get(edge.from) ?? 1, degree.get(edge.to) ?? 1);
      const rest = springLength * (1 + Math.min(Math.log2(busiest + 1) * 0.32, 1.6));
      const force = (distance - rest) * springStrength;
      const fx = (dx / distance) * force;
      const fy = (dy / distance) * force;
      a.vx += fx; a.vy += fy;
      b.vx -= fx; b.vy -= fy;
    }

    for (const node of list) {
      node.vx += (width / 2 - node.x) * centring;
      node.vy += (height / 2 - node.y) * centring;
      if (node.pinned) { node.vx = 0; node.vy = 0; continue; }
      node.vx *= damping;
      node.vy *= damping;
      node.x = clampX(node.x + node.vx, width);
      node.y = clampY(node.y + node.vy, height);
    }
  }
  separate(list, width, height);
  spreadLabels(list, width, height);
  return nodes;
}

/** Final hard-collision pass: labels are unreadable long before circles actually touch. */
const LABEL_BAND = 26;

function spreadLabels(list: LayoutNode[], width: number, height: number): void {
  for (let pass = 0; pass < 40; pass++) {
    let moved = false;
    for (let i = 0; i < list.length; i++) {
      for (let j = i + 1; j < list.length; j++) {
        const a = list[i];
        const b = list[j];
        const need = ((a.labelWidth ?? 0) + (b.labelWidth ?? 0)) / 2 + 12;
        if (!need) continue;
        const dx = b.x - a.x;
        const dy = b.y - a.y;
        if (Math.abs(dy) >= LABEL_BAND || Math.abs(dx) >= need) continue;
        const push = (need - Math.abs(dx)) / 2 + 0.5;
        const direction = dx === 0 ? (i % 2 ? 1 : -1) : Math.sign(dx);
        a.x = clampX(a.x - direction * push, width);
        b.x = clampX(b.x + direction * push, width);
        a.y = clampY(a.y, height);
        b.y = clampY(b.y, height);
        moved = true;
      }
    }
    if (!moved) return;
  }
}

function separate(list: LayoutNode[], width: number, height: number, minimum = 84): void {
  for (let pass = 0; pass < 60; pass++) {
    let moved = false;
    for (let i = 0; i < list.length; i++) {
      for (let j = i + 1; j < list.length; j++) {
        const a = list[i];
        const b = list[j];
        let dx = b.x - a.x;
        let dy = b.y - a.y;
        let distance = Math.sqrt(dx * dx + dy * dy);
        if (distance >= minimum) continue;
        if (distance < 0.01) { dx = (i % 3) - 1 || 1; dy = (j % 3) - 1 || 1; distance = Math.sqrt(dx * dx + dy * dy); }
        const shift = (minimum - distance) / 2;
        const ux = (dx / distance) * shift;
        const uy = (dy / distance) * shift;
        a.x = clampX(a.x - ux, width);
        a.y = clampY(a.y - uy, height);
        b.x = clampX(b.x + ux, width);
        b.y = clampY(b.y + uy, height);
        moved = true;
      }
    }
    if (!moved) return;
  }
}

export function layout(
  ids: string[],
  edges: LayoutEdge[],
  width: number,
  height: number,
  previous?: Map<string, LayoutNode>,
  labelWidths?: Map<string, number>,
): Map<string, LayoutNode> {
  const seeded = seedPositions(ids, width, height);
  if (labelWidths) for (const [id, node] of seeded) node.labelWidth = labelWidths.get(id);
  if (previous) {
    // Keep already-placed nodes where the analyst last saw them so expansion feels stable.
    for (const [id, node] of seeded) {
      const known = previous.get(id);
      if (known) { node.x = known.x; node.y = known.y; }
    }
  }
  return relax(seeded, edges, { width, height });
}

interface Box { x: number; y: number; w: number; h: number; }

const overlaps = (a: Box, b: Box) =>
  Math.abs(a.x - b.x) * 2 < a.w + b.w && Math.abs(a.y - b.y) * 2 < a.h + b.h;

/**
 * Choose a spot for each edge label that avoids node labels and other edge labels.
 *
 * Greedy over a fixed candidate set — along the edge and perpendicular to it — so the result
 * is deterministic: the same graph always draws the same way.
 */
export function placeEdgeLabels(
  edges: { id: string; from: string; to: string; w: number; h: number }[],
  nodes: Map<string, LayoutNode>,
  nodeBoxes: Box[],
  width = 0,
  height = 0,
): Map<string, { x: number; y: number }> {
  const along = [0.5, 0.44, 0.56, 0.38, 0.62, 0.32, 0.68, 0.26, 0.74, 0.2, 0.8];
  const across = [0, 14, -14, 26, -26, 38, -38, 52, -52, 66, -66, 80, -80];
  const taken: Box[] = [];
  const placedLabels = new Map<string, { x: number; y: number }>();

  // Shortest edges first: they have the fewest viable slots, so they choose before the rest.
  const ordered = [...edges].sort((left, right) => {
    const la = nodes.get(left.from); const lb = nodes.get(left.to);
    const ra = nodes.get(right.from); const rb = nodes.get(right.to);
    if (!la || !lb || !ra || !rb) return 0;
    return Math.hypot(lb.x - la.x, lb.y - la.y) - Math.hypot(rb.x - ra.x, rb.y - ra.y);
  });

  for (const edge of ordered) {
    const a = nodes.get(edge.from);
    const b = nodes.get(edge.to);
    if (!a || !b) continue;
    const dx = b.x - a.x;
    const dy = b.y - a.y;
    const span = Math.hypot(dx, dy) || 1;
    let best: Box | null = null;
    let bestCost = Infinity;

    for (const t of along) {
      for (const offset of across) {
        const box: Box = {
          x: a.x + dx * t + (-dy / span) * offset,
          y: a.y + dy * t + (dx / span) * offset,
          w: edge.w, h: edge.h,
        };
        if (width && height) {
          box.x = Math.min(width - box.w / 2 - 2, Math.max(box.w / 2 + 2, box.x));
          box.y = Math.min(height - box.h / 2 - 2, Math.max(box.h / 2 + 2, box.y));
        }
        if ([...nodeBoxes, ...taken].some((obstacle) => overlaps(box, obstacle))) continue;
        const cost = Math.abs(offset) * 0.6 + Math.abs(t - 0.5) * 40;
        if (cost < bestCost) { bestCost = cost; best = box; }
      }
      if (best) break;
    }
    // An overlapping label is worse than none: the relationship is still readable on hover.
    if (!best) continue;
    taken.push(best);
    placedLabels.set(edge.id, { x: best.x, y: best.y });
  }
  return placedLabels;
}
