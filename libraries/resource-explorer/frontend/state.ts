/**
 * Inventory state: what has been loaded, what is open, what is selected.
 *
 * ADAPTED from `resource_explorer/frontend/src/api/state.ts`. See PROVENANCE.md.
 * Estate search, the sign-in session and the reveal note are dropped — this
 * surface has none of them. Two things are added: a `resources` map, because a
 * source's metadata is a separate read from its preview, and a `generation`
 * counter that drops an answer to a question the reader has already changed.
 *
 * Children live in `expansions`, keyed by the node id that produced them, and
 * previews in `contents`, so each is fetched at most once per node however
 * often it is collapsed and re-opened. Refresh is the only thing that evicts.
 *
 * Kept free of React on purpose — the visible-row projection and the keyboard
 * moves are the parts most worth testing without a DOM.
 */

import {
  ROOT_ID,
  type ContentResponse,
  type DetailValue,
  type NodeStatus,
  type ResourceResponse,
  type SelectionMode,
  type TreeNode,
  type TreeResponse,
} from "./wire.js";

export interface Expansion {
  status: NodeStatus;
  children: TreeNode[];
  truncated: boolean;
  error: string | null;
  observedAt: string;
  breadcrumb: string[];
  detail: Record<string, DetailValue> | null;
  /** The generation this branch was read in. An older one is refetched, not shown as fact. */
  generation: number;
}

export interface InventoryState {
  rootNode: TreeNode | null;
  expansions: Record<string, Expansion>;
  resources: Record<string, ResourceResponse>;
  contents: Record<string, ContentResponse>;
  loading: Record<string, boolean>;
  resourceLoading: Record<string, boolean>;
  contentLoading: Record<string, boolean>;
  failures: Record<string, string>;
  resourceFailures: Record<string, string>;
  contentFailures: Record<string, string>;
  open: Record<string, boolean>;
  selectedId: string | null;
  activeId: string | null;
  fixtures: boolean;
  announcement: string;
  rootObservedAt: string | null;
  selectionScope: string;
  /**
   * Bumped whenever the reader changes what they asked for. A response
   * carrying an older generation is discarded rather than rendered: a preview
   * that repopulates from a source the reader just switched off is worse than
   * a blank pane, because it looks like the switch did nothing.
   */
  generation: number;
}

export const initialState: InventoryState = {
  rootNode: null,
  expansions: {},
  resources: {},
  contents: {},
  loading: {},
  resourceLoading: {},
  contentLoading: {},
  failures: {},
  resourceFailures: {},
  contentFailures: {},
  open: { [ROOT_ID]: true },
  selectedId: null,
  activeId: null,
  fixtures: false,
  announcement: "",
  rootObservedAt: null,
  selectionScope: "",
  generation: 0,
};

export type Action =
  | { type: "request"; id: string }
  | { type: "loaded"; id: string; response: TreeResponse; generation: number }
  | { type: "failed"; id: string; message: string; generation: number }
  | { type: "resourceRequest"; id: string }
  | { type: "resourceLoaded"; id: string; response: ResourceResponse; generation: number }
  | { type: "resourceFailed"; id: string; message: string; generation: number }
  | { type: "contentRequest"; id: string }
  | { type: "contentLoaded"; id: string; response: ContentResponse; generation: number }
  | { type: "contentFailed"; id: string; message: string; generation: number }
  | { type: "setOpen"; id: string; open: boolean }
  | { type: "select"; id: string | null }
  | { type: "focus"; id: string | null }
  | { type: "evict"; id: string }
  | { type: "invalidate"; message: string; selection: { mode: SelectionMode; ids: string[] } }
  | { type: "reset" }
  | { type: "announce"; message: string };

export interface Row {
  node: TreeNode;
  level: number;
  parentId: string | null;
  posinset: number;
  setsize: number;
  expanded: boolean;
  loading: boolean;
  expansion: Expansion | null;
  failure: string | null;
}

function without<T>(source: Record<string, T>, ids: Iterable<string>): Record<string, T> {
  const next = { ...source };
  for (const id of ids) delete next[id];
  return next;
}

/** Ids below `id` that are currently cached — the eviction frontier. */
export function descendantIds(state: InventoryState, id: string): string[] {
  const found: string[] = [];
  const queue: string[] = [id];
  while (queue.length > 0) {
    const current = queue.shift() as string;
    for (const child of state.expansions[current]?.children ?? []) {
      found.push(child.id);
      queue.push(child.id);
    }
  }
  return found;
}

/** The root response describes a node the tree draws like any other. */
function rootNodeOf(response: TreeResponse): TreeNode {
  return {
    id: ROOT_ID,
    label: response.label,
    kind: response.kind,
    expandable: true,
    hasContent: response.hasContent,
    status: response.status,
    useCaseId: "",
    sourceId: "",
    sourceType: null,
    tags: [],
    enabled: null,
    configured: true,
    detail: response.detail,
    error: response.error,
  };
}

function expansionOf(response: TreeResponse, generation: number): Expansion {
  return {
    status: response.status,
    children: response.children,
    truncated: response.truncated,
    error: response.error,
    observedAt: response.observedAt,
    breadcrumb: response.breadcrumb,
    detail: response.detail,
    generation,
  };
}

function loadedAnnouncement(response: TreeResponse): string {
  if (response.status !== "ok" && response.status !== "empty") {
    return `${response.label}: ${response.status}. ${response.error ?? ""}`.trim();
  }
  const count = response.children.length;
  const noun = count === 1 ? "item" : "items";
  const more = response.truncated ? ", truncated" : "";
  return `${response.label}: ${String(count)} ${noun}${more}.`;
}

/** True when this answer is to the question the reader is still asking. */
function current(state: InventoryState, generation: number): boolean {
  return generation === state.generation;
}

export function reducer(state: InventoryState, action: Action): InventoryState {
  switch (action.type) {
    case "request":
      return {
        ...state,
        loading: { ...state.loading, [action.id]: true },
        failures: without(state.failures, [action.id]),
      };

    case "loaded": {
      if (!current(state, action.generation)) return state;
      const { response } = action;
      return {
        ...state,
        rootNode: action.id === ROOT_ID ? rootNodeOf(response) : state.rootNode,
        expansions: { ...state.expansions, [action.id]: expansionOf(response, state.generation) },
        loading: without(state.loading, [action.id]),
        failures: without(state.failures, [action.id]),
        fixtures: response.fixtures,
        selectionScope: response.selectionScope || state.selectionScope,
        rootObservedAt:
          action.id === ROOT_ID ? response.observedAt : state.rootObservedAt,
        activeId: state.activeId ?? (action.id === ROOT_ID ? ROOT_ID : null),
        announcement: loadedAnnouncement(response),
      };
    }

    case "failed":
      if (!current(state, action.generation)) return state;
      return {
        ...state,
        loading: without(state.loading, [action.id]),
        failures: { ...state.failures, [action.id]: action.message },
        announcement: `Could not expand this branch: ${action.message}`,
      };

    case "resourceRequest":
      return {
        ...state,
        resourceLoading: { ...state.resourceLoading, [action.id]: true },
        resourceFailures: without(state.resourceFailures, [action.id]),
      };

    case "resourceLoaded":
      if (!current(state, action.generation)) return state;
      return {
        ...state,
        resources: { ...state.resources, [action.id]: action.response },
        resourceLoading: without(state.resourceLoading, [action.id]),
        resourceFailures: without(state.resourceFailures, [action.id]),
        fixtures: action.response.fixtures,
        announcement: `${action.response.label}: metadata read at ${action.response.observedAt}.`,
      };

    case "resourceFailed":
      if (!current(state, action.generation)) return state;
      return {
        ...state,
        resourceLoading: without(state.resourceLoading, [action.id]),
        resourceFailures: { ...state.resourceFailures, [action.id]: action.message },
        announcement: `Could not read this source: ${action.message}`,
      };

    case "contentRequest":
      return {
        ...state,
        contentLoading: { ...state.contentLoading, [action.id]: true },
        contentFailures: without(state.contentFailures, [action.id]),
      };

    case "contentLoaded":
      if (!current(state, action.generation)) return state;
      return {
        ...state,
        contents: { ...state.contents, [action.id]: action.response },
        contentLoading: without(state.contentLoading, [action.id]),
        contentFailures: without(state.contentFailures, [action.id]),
        fixtures: action.response.fixtures,
        announcement: `${action.response.label}: ${String(action.response.sizeBytes)} rows previewed.`,
      };

    case "contentFailed":
      if (!current(state, action.generation)) return state;
      return {
        ...state,
        contentLoading: without(state.contentLoading, [action.id]),
        contentFailures: { ...state.contentFailures, [action.id]: action.message },
        announcement: `Could not preview this source: ${action.message}`,
      };

    case "setOpen": {
      const open = { ...state.open };
      if (action.open) open[action.id] = true;
      else delete open[action.id];
      return { ...state, open };
    }

    case "select":
      return { ...state, selectedId: action.id };

    case "focus":
      return { ...state, activeId: action.id };

    case "evict": {
      const below = descendantIds(state, action.id);
      const all = [action.id, ...below];
      return {
        ...state,
        expansions: without(state.expansions, all),
        resources: without(state.resources, all),
        contents: without(state.contents, all),
        failures: without(state.failures, all),
        resourceFailures: without(state.resourceFailures, all),
        contentFailures: without(state.contentFailures, all),
        loading: without(state.loading, all),
        resourceLoading: without(state.resourceLoading, all),
        contentLoading: without(state.contentLoading, all),
        open: without(state.open, below),
        announcement: "Reloading this branch.",
      };
    }

    case "invalidate": {
      // The selection changed. Metadata and previews described a different scope
      // and are dropped; the shape of the tree did not, so the rows stay standing —
      // with the switches flipped locally — while each branch is re-read at the new
      // generation. Tearing them down blanked the tree and threw away the focus of
      // whoever had just operated a switch.
      const { mode, ids } = action.selection;
      const on = (sourceId: string): boolean =>
        mode === "all" ? true : mode === "none" ? false : ids.includes(sourceId);
      const expansions: Record<string, Expansion> = {};
      for (const [id, expansion] of Object.entries(state.expansions)) {
        expansions[id] = {
          ...expansion,
          children: expansion.children.map((child) =>
            child.kind === "source" ? { ...child, enabled: on(child.sourceId) } : child,
          ),
        };
      }
      return {
        ...state,
        expansions,
        resources: {},
        contents: {},
        loading: {},
        resourceLoading: {},
        contentLoading: {},
        failures: {},
        resourceFailures: {},
        contentFailures: {},
        generation: state.generation + 1,
        announcement: action.message,
      };
    }

    case "reset":
      return {
        ...initialState,
        open: state.open,
        selectedId: state.selectedId,
        activeId: state.activeId,
        selectionScope: state.selectionScope,
        generation: state.generation + 1,
        announcement: "Reloading the inventory.",
      };

    case "announce":
      return { ...state, announcement: action.message };
  }
}

/**
 * The tree, flattened to the rows a reader can currently see. `aria-level` and
 * `aria-posinset` come from here, so the projection is the accessibility
 * contract as much as the render list.
 */
export function visibleRows(state: InventoryState): Row[] {
  const rows: Row[] = [];
  if (state.rootNode === null) return rows;

  const push = (
    node: TreeNode,
    level: number,
    parentId: string | null,
    posinset: number,
    setsize: number,
  ): void => {
    const expanded = state.open[node.id] === true;
    rows.push({
      node,
      level,
      parentId,
      posinset,
      setsize,
      expanded,
      loading: state.loading[node.id] === true,
      expansion: state.expansions[node.id] ?? null,
      failure: state.failures[node.id] ?? null,
    });
    if (!expanded) return;
    const children = state.expansions[node.id]?.children ?? [];
    children.forEach((child, index) => {
      push(child, level + 1, node.id, index + 1, children.length);
    });
  };

  push(state.rootNode, 1, null, 1, 1);
  return rows;
}

export function rowIndex(rows: Row[], id: string | null): number {
  return id === null ? -1 : rows.findIndex((row) => row.node.id === id);
}

/** Exactly one row is tabbable; a collapsed-away focus falls back to the first. */
export function effectiveActiveId(rows: Row[], activeId: string | null): string | null {
  if (rows.length === 0) return null;
  if (activeId !== null && rowIndex(rows, activeId) >= 0) return activeId;
  return rows[0]?.node.id ?? null;
}

export function findRow(rows: Row[], id: string | null): Row | null {
  const index = rowIndex(rows, id);
  return index < 0 ? null : (rows[index] ?? null);
}

/** The node whose pane is showing, wherever it sits in the tree. */
export function selectedNode(state: InventoryState): TreeNode | null {
  if (state.selectedId === null) return null;
  if (state.selectedId === ROOT_ID) return state.rootNode;
  for (const expansion of Object.values(state.expansions)) {
    for (const child of expansion.children) {
      if (child.id === state.selectedId) return child;
    }
  }
  return null;
}

/** Which ids the loader should fetch: the root, plus every open node not read at this generation. */
export function pendingLoads(state: InventoryState): string[] {
  const wanted = [ROOT_ID, ...Object.keys(state.open).filter((id) => state.open[id])];
  const unique = [...new Set(wanted)];
  return unique.filter((id) => {
    const expansion = state.expansions[id];
    const fresh = expansion !== undefined && expansion.generation === state.generation;
    return !fresh && state.loading[id] !== true && state.failures[id] === undefined;
  });
}

/** The use case a node hangs under, by label, wherever it sits in the tree. */
export function useCaseLabel(state: InventoryState, node: TreeNode | null): string {
  if (node === null || node.useCaseId === "") return "";
  if (node.kind === "use_case") return node.label;
  for (const expansion of Object.values(state.expansions)) {
    for (const child of expansion.children) {
      if (child.kind === "use_case" && child.useCaseId === node.useCaseId) return child.label;
    }
  }
  return "";
}
