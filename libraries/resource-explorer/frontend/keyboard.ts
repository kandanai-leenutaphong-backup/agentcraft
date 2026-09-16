/**
 * Tree keyboard model, as a pure function over the visible rows.
 *
 * ADAPTED from `resource_explorer/frontend/src/api/keyboard.ts`. See
 * PROVENANCE.md. The `/` move is dropped — this surface has no search box to
 * jump to — and `t` is added, which toggles the focused source on or off
 * without leaving the tree.
 *
 * The moves are the WAI-ARIA tree pattern minus expand-all: Up/Down walk what
 * is visible, Right opens then descends, Left collapses then ascends,
 * Home/End jump, Enter and Space open the node.
 */

import { rowIndex, type Row } from "./state.js";

export type KeyMove =
  | { kind: "focus"; id: string }
  | { kind: "open"; id: string }
  | { kind: "close"; id: string }
  | { kind: "activate"; id: string }
  | { kind: "toggleSource"; id: string }
  | null;

export const HANDLED_KEYS = [
  "ArrowUp",
  "ArrowDown",
  "ArrowRight",
  "ArrowLeft",
  "Home",
  "End",
  "Enter",
  " ",
  "t",
] as const;

export function keyboardMove(rows: Row[], activeId: string | null, key: string): KeyMove {
  if (rows.length === 0) return null;
  const index = Math.max(rowIndex(rows, activeId), 0);
  const row = rows[index];
  if (row === undefined) return null;

  switch (key) {
    case "ArrowDown": {
      const next = rows[Math.min(index + 1, rows.length - 1)];
      return next ? { kind: "focus", id: next.node.id } : null;
    }
    case "ArrowUp": {
      const previous = rows[Math.max(index - 1, 0)];
      return previous ? { kind: "focus", id: previous.node.id } : null;
    }
    case "Home": {
      const first = rows[0];
      return first ? { kind: "focus", id: first.node.id } : null;
    }
    case "End": {
      const last = rows[rows.length - 1];
      return last ? { kind: "focus", id: last.node.id } : null;
    }
    case "ArrowRight": {
      if (!row.node.expandable) return null;
      if (!row.expanded) return { kind: "open", id: row.node.id };
      const child = rows[index + 1];
      return child && child.parentId === row.node.id
        ? { kind: "focus", id: child.node.id }
        : null;
    }
    case "ArrowLeft": {
      if (row.expanded) return { kind: "close", id: row.node.id };
      if (row.parentId === null) return null;
      const parentId = row.parentId;
      const parent = rows.find((candidate) => candidate.node.id === parentId);
      return parent ? { kind: "focus", id: parent.node.id } : null;
    }
    case "t":
    case "T":
      return row.node.kind === "source"
        ? { kind: "toggleSource", id: row.node.id }
        : null;
    case "Enter":
    case " ":
      return { kind: "activate", id: row.node.id };
    default:
      return null;
  }
}
