/**
 * The row-sample table model: which columns exist, what a cell reads as, and
 * how a column sorts.
 *
 * Adopted verbatim from `resource_explorer/frontend/src/api/rows.ts` except
 * this note. See PROVENANCE.md.
 *
 * A graph vertex is not a flat record — a cell can hold an object or an array —
 * so a cell renders as text but keeps the value. Sorting is stable and puts
 * absent values last in both directions, because a missing value is not the
 * smallest value.
 */

export type SortDirection = "asc" | "desc";

export interface SortState {
  column: string;
  direction: SortDirection;
}

export const NULL_CELL = "(null)";
export const ABSENT_CELL = "";
export const MAX_CELL_CHARS = 400;

export function columnsOf(
  rows: Record<string, unknown>[],
  declared: string[] | null,
): string[] {
  if (declared !== null && declared.length > 0) return declared;
  const seen: string[] = [];
  const known = new Set<string>();
  for (const row of rows) {
    for (const key of Object.keys(row)) {
      if (!known.has(key)) {
        known.add(key);
        seen.push(key);
      }
    }
  }
  return seen;
}

export function cellText(value: unknown): string {
  if (value === undefined) return ABSENT_CELL;
  if (value === null) return NULL_CELL;
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  try {
    return JSON.stringify(value) ?? String(value);
  } catch {
    return String(value);
  }
}

export function truncateCell(text: string): { text: string; truncated: boolean } {
  if (text.length <= MAX_CELL_CHARS) return { text, truncated: false };
  return { text: `${text.slice(0, MAX_CELL_CHARS)}…`, truncated: true };
}

function rank(value: unknown): number {
  if (value === undefined) return 3;
  if (value === null) return 2;
  return 0;
}

export function compareValues(left: unknown, right: unknown): number {
  const leftRank = rank(left);
  const rightRank = rank(right);
  if (leftRank !== rightRank) return leftRank - rightRank;
  if (leftRank !== 0) return 0;
  if (typeof left === "number" && typeof right === "number") return left - right;
  if (typeof left === "boolean" && typeof right === "boolean") {
    return Number(left) - Number(right);
  }
  return cellText(left).localeCompare(cellText(right), "en", { numeric: true });
}

/** Absent values stay last however the column is sorted. */
export function sortRows(
  rows: Record<string, unknown>[],
  sort: SortState | null,
): Record<string, unknown>[] {
  if (sort === null) return rows;
  const factor = sort.direction === "asc" ? 1 : -1;
  const decorated = rows.map((row, index) => ({ row, index }));
  decorated.sort((left, right) => {
    const leftValue = left.row[sort.column];
    const rightValue = right.row[sort.column];
    const leftRank = rank(leftValue);
    const rightRank = rank(rightValue);
    if (leftRank !== rightRank) return leftRank - rightRank;
    const compared = compareValues(leftValue, rightValue) * factor;
    return compared !== 0 ? compared : left.index - right.index;
  });
  return decorated.map((entry) => entry.row);
}

export function nextSort(current: SortState | null, column: string): SortState | null {
  if (current === null || current.column !== column) return { column, direction: "asc" };
  if (current.direction === "asc") return { column, direction: "desc" };
  return null;
}

export function sortAriaValue(
  current: SortState | null,
  column: string,
): "ascending" | "descending" | "none" {
  if (current === null || current.column !== column) return "none";
  return current.direction === "asc" ? "ascending" : "descending";
}
