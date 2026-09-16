/**
 * Which sources this browser tab has switched on.
 *
 * NEW IN THIS COMPONENT. Semantics: `../README.md`, "Selection".
 *
 * Held in `sessionStorage`, which is the lifetime wanted: it survives a reload
 * and same-tab navigation, and a second tab gets its own. The value is sent as
 * a request header on every call; the server treats it as a scope filter, not
 * as an authorisation.
 *
 * `all` and `none` are spelled out rather than encoded as a full or empty list
 * because "the user turned everything off" must never be mistaken for "the
 * user has not chosen yet".
 */

import type { SelectionMode } from "./wire";

export const SELECTION_HEADER = "X-Inventory-Selection";
export const STORAGE_KEY = "cybereye.inventory.selection";

export interface StoredSelection {
  mode: SelectionMode;
  ids: string[];
}

export const ALL_SELECTED: StoredSelection = { mode: "all", ids: [] };

type Store = Pick<Storage, "getItem" | "setItem" | "removeItem">;

function store(): Store | null {
  try {
    return window.sessionStorage;
  } catch {
    // A privacy mode or a sandboxed frame can refuse storage. The selection
    // then lasts one page rather than the tab, which is degraded, not broken.
    return null;
  }
}

export function readSelection(from: Store | null = store()): StoredSelection {
  if (from === null) return ALL_SELECTED;
  try {
    const raw = from.getItem(STORAGE_KEY);
    if (raw === null) return ALL_SELECTED;
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed !== "object" || parsed === null) return ALL_SELECTED;
    const value = parsed as { mode?: unknown; ids?: unknown };
    const mode =
      value.mode === "all" || value.mode === "none" || value.mode === "explicit"
        ? value.mode
        : "all";
    const ids = Array.isArray(value.ids)
      ? value.ids.filter((item): item is string => typeof item === "string")
      : [];
    return { mode, ids };
  } catch {
    return ALL_SELECTED;
  }
}

export function writeSelection(
  selection: StoredSelection,
  to: Store | null = store(),
): void {
  if (to === null) return;
  try {
    to.setItem(STORAGE_KEY, JSON.stringify(selection));
  } catch {
    // Storage full or refused. The in-memory selection still governs this page.
  }
}

/** The header value for one request. Never a full or empty list. */
export function selectionHeader(selection: StoredSelection): string {
  if (selection.mode === "all") return "all";
  if (selection.mode === "none" || selection.ids.length === 0) return "none";
  return selection.ids.join(",");
}

/** Which ids are on, given everything the registry currently declares. */
export function enabledIds(selection: StoredSelection, known: string[]): string[] {
  if (selection.mode === "all") return [...known];
  if (selection.mode === "none") return [];
  const chosen = new Set(selection.ids);
  return known.filter((id) => chosen.has(id));
}

export function isEnabled(selection: StoredSelection, sourceId: string): boolean {
  if (selection.mode === "all") return true;
  if (selection.mode === "none") return false;
  return selection.ids.includes(sourceId);
}

/**
 * Turn one source on or off.
 *
 * Normalised against what the registry declares so a stale id from a previous
 * manifest is dropped here rather than rejected by the server, and so an
 * explicit list that happens to cover everything collapses back to `all`.
 */
export function toggle(
  selection: StoredSelection,
  sourceId: string,
  known: string[],
): StoredSelection {
  const current = new Set(enabledIds(selection, known));
  if (current.has(sourceId)) current.delete(sourceId);
  else current.add(sourceId);
  const ids = known.filter((id) => current.has(id));
  if (ids.length === known.length) return { mode: "all", ids: [] };
  if (ids.length === 0) return { mode: "none", ids: [] };
  return { mode: "explicit", ids };
}

export function selectAll(): StoredSelection {
  return { mode: "all", ids: [] };
}

export function selectNone(): StoredSelection {
  return { mode: "none", ids: [] };
}

/** Drop ids the registry no longer declares, so a stale tab self-heals. */
export function prune(selection: StoredSelection, known: string[]): StoredSelection {
  if (selection.mode !== "explicit") return selection;
  const ids = known.filter((id) => selection.ids.includes(id));
  if (ids.length === known.length) return { mode: "all", ids: [] };
  if (ids.length === 0) return { mode: "none", ids: [] };
  if (ids.length === selection.ids.length) return selection;
  return { mode: "explicit", ids };
}

/**
 * Reconcile a rejected selection against the ids that are still declared.
 *
 * Narrowing only, and that is the whole point. A stored selection that names
 * one id the server has stopped declaring is refused wholesale, and the
 * tempting repair — start again with everything on — switches back on every
 * source the reader had deliberately switched off. `explicit` keeps its
 * surviving ids and nothing else; an explicit list with no survivors becomes
 * `none` and says so; `all` and `none` already name no id and cannot be stale.
 *
 * Unlike `prune` this never collapses a surviving list to `all`, because `all`
 * means "and whatever is declared next" and the reader chose these.
 */
export function intersect(
  selection: StoredSelection,
  known: string[],
): StoredSelection {
  if (selection.mode !== "explicit") return selection;
  const ids = known.filter((id) => selection.ids.includes(id));
  if (ids.length === 0) return { mode: "none", ids: [] };
  return { mode: "explicit", ids };
}

/** The one selection that reads nothing, used to re-ask what exists. */
export const NO_SOURCES: StoredSelection = { mode: "none", ids: [] };
