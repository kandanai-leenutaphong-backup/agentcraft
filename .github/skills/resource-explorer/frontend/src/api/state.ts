/**
 * Explorer state: what has been loaded, what is open, what is selected, and
 * what the last search returned.
 *
 * Children live in `expansions`, keyed by the node id that produced them, and
 * contents in `contents`, so each is fetched at most once per node however
 * often it is collapsed and re-opened. Refresh is the only thing that evicts:
 * the global one clears everything, the branch one clears exactly that
 * subtree.
 *
 * Kept free of React on purpose — the visible-row projection and the keyboard
 * moves are the parts most worth testing without a DOM.
 */

import {
  ROOT_ID,
  type ContentResponse,
  type DetailValue,
  type NodeStatus,
  type SearchHit,
  type SearchResponse,
  type TreeNode,
  type TreeResponse,
} from "./wire";

export interface Expansion {
  status: NodeStatus;
  children: TreeNode[];
  truncated: boolean;
  error: string | null;
  observedAt: string;
  breadcrumb: string[];
  detail: Record<string, DetailValue> | null;
}

export type Session = "active" | "expired";

export interface SearchState {
  term: string;
  ran: string | null;
  loading: boolean;
  status: NodeStatus | null;
  hits: SearchHit[];
  truncated: boolean;
  error: string | null;
  failure: string | null;
  observedAt: string | null;
}

export const emptySearch: SearchState = {
  term: "",
  ran: null,
  loading: false,
  status: null,
  hits: [],
  truncated: false,
  error: null,
  failure: null,
  observedAt: null,
};

export interface ExplorerState {
  rootNode: TreeNode | null;
  expansions: Record<string, Expansion>;
  contents: Record<string, ContentResponse>;
  loading: Record<string, boolean>;
  contentLoading: Record<string, boolean>;
  failures: Record<string, string>;
  contentFailures: Record<string, string>;
  open: Record<string, boolean>;
  selectedId: string | null;
  activeId: string | null;
  fixtures: boolean;
  session: Session;
  announcement: string;
  rootObservedAt: string | null;
  search: SearchState;
  /** Set when a search hit was opened but could not be positioned in the tree. */
  revealNote: string | null;
}

export const initialState: ExplorerState = {
  rootNode: null,
  expansions: {},
  contents: {},
  loading: {},
  contentLoading: {},
  failures: {},
  contentFailures: {},
  open: { [ROOT_ID]: true },
  selectedId: null,
  activeId: null,
  fixtures: false,
  session: "active",
  announcement: "",
  rootObservedAt: null,
  search: emptySearch,
  revealNote: null,
};

export type Action =
  | { type: "request"; id: string }
  | { type: "loaded"; id: string; response: TreeResponse }
  | { type: "failed"; id: string; message: string }
  | { type: "contentRequest"; id: string }
  | { type: "contentLoaded"; id: string; response: ContentResponse }
  | { type: "contentFailed"; id: string; message: string }
  | { type: "expired" }
  | { type: "setOpen"; id: string; open: boolean }
  | { type: "select"; id: string | null }
  | { type: "focus"; id: string | null }
  | { type: "evict"; id: string }
  | { type: "reset" }
  | { type: "searchTerm"; term: string }
  | { type: "searchRequest"; term: string }
  | { type: "searchLoaded"; response: SearchResponse }
  | { type: "searchFailed"; message: string }
  | { type: "searchClear" }
  | { type: "revealNote"; message: string | null }
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
export function descendantIds(state: ExplorerState, id: string): string[] {
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
    detail: response.detail,
    error: response.error,
  };
}

function expansionOf(response: TreeResponse): Expansion {
  return {
    status: response.status,
    children: response.children,
    truncated: response.truncated,
    error: response.error,
    observedAt: response.observedAt,
    breadcrumb: response.breadcrumb,
    detail: response.detail,
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

export function reducer(state: ExplorerState, action: Action): ExplorerState {
  switch (action.type) {
    case "request":
      return {
        ...state,
        loading: { ...state.loading, [action.id]: true },
        failures: without(state.failures, [action.id]),
      };

    case "loaded": {
      const { response } = action;
      return {
        ...state,
        rootNode: action.id === ROOT_ID ? rootNodeOf(response) : state.rootNode,
        expansions: { ...state.expansions, [action.id]: expansionOf(response) },
        loading: without(state.loading, [action.id]),
        failures: without(state.failures, [action.id]),
        fixtures: response.fixtures,
        rootObservedAt:
          action.id === ROOT_ID ? response.observedAt : state.rootObservedAt,
        activeId: state.activeId ?? (action.id === ROOT_ID ? ROOT_ID : null),
        // The pane opens on the subscription rather than on a blank panel that
        // has to be earned with a click.
        selectedId: state.selectedId ?? (action.id === ROOT_ID ? ROOT_ID : null),
        announcement: loadedAnnouncement(response),
      };
    }

    case "failed":
      return {
        ...state,
        loading: without(state.loading, [action.id]),
        failures: { ...state.failures, [action.id]: action.message },
        announcement: `Could not expand this branch: ${action.message}`,
      };

    case "contentRequest":
      return {
        ...state,
        contentLoading: { ...state.contentLoading, [action.id]: true },
        contentFailures: without(state.contentFailures, [action.id]),
      };

    case "contentLoaded":
      return {
        ...state,
        contents: { ...state.contents, [action.id]: action.response },
        contentLoading: without(state.contentLoading, [action.id]),
        contentFailures: without(state.contentFailures, [action.id]),
        fixtures: action.response.fixtures,
        announcement: `${action.response.label}: contents loaded as ${action.response.contentKind}.`,
      };

    case "contentFailed":
      return {
        ...state,
        contentLoading: without(state.contentLoading, [action.id]),
        contentFailures: { ...state.contentFailures, [action.id]: action.message },
        announcement: `Could not read these contents: ${action.message}`,
      };

    case "expired":
      return {
        ...state,
        session: "expired",
        loading: {},
        contentLoading: {},
        announcement: "The sign-in session expired.",
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
        contents: without(state.contents, all),
        failures: without(state.failures, all),
        contentFailures: without(state.contentFailures, all),
        loading: without(state.loading, all),
        contentLoading: without(state.contentLoading, all),
        open: without(state.open, below),
        announcement: "Reloading this branch.",
      };
    }

    case "reset":
      return {
        ...initialState,
        fixtures: state.fixtures,
        session: state.session,
        search: state.search,
        announcement: "Reloading the whole tree.",
      };

    case "searchTerm":
      return { ...state, search: { ...state.search, term: action.term } };

    case "searchRequest":
      return {
        ...state,
        search: { ...state.search, term: action.term, loading: true, failure: null },
      };

    case "searchLoaded": {
      const { response } = action;
      const count = response.hits.length;
      return {
        ...state,
        fixtures: response.fixtures,
        search: {
          term: state.search.term,
          ran: response.query,
          loading: false,
          status: response.status,
          hits: response.hits,
          truncated: response.truncated,
          error: response.error,
          failure: null,
          observedAt: response.observedAt,
        },
        announcement:
          count === 0
            ? `No estate matches for ${response.query}.`
            : `${String(count)} estate ${count === 1 ? "match" : "matches"} for ${response.query}.`,
      };
    }

    case "searchFailed":
      return {
        ...state,
        search: { ...state.search, loading: false, failure: action.message, hits: [] },
        announcement: `Search failed: ${action.message}`,
      };

    case "searchClear":
      return { ...state, search: emptySearch, announcement: "Search cleared." };

    case "revealNote":
      return { ...state, revealNote: action.message };

    case "announce":
      return { ...state, announcement: action.message };
  }
}

/**
 * The tree, flattened to the rows a reader can currently see. `aria-level` and
 * `aria-posinset` come from here, so the projection is the accessibility
 * contract as much as the render list.
 */
export function visibleRows(state: ExplorerState): Row[] {
  const rows: Row[] = [];
  if (state.rootNode === null) return rows;

  const push = (node: TreeNode, level: number, parentId: string | null, posinset: number, setsize: number): void => {
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
export function selectedNode(state: ExplorerState): TreeNode | null {
  if (state.selectedId === null) return null;
  if (state.selectedId === ROOT_ID) return state.rootNode;
  for (const expansion of Object.values(state.expansions)) {
    for (const child of expansion.children) {
      if (child.id === state.selectedId) return child;
    }
  }
  return null;
}

/**
 * The path to a node through the tree the reader actually walked. The server
 * sends its own breadcrumb on any node it answered for; this is the fallback
 * for a node that has neither children nor contents.
 */
export function treePath(rows: Row[], id: string): string[] {
  const labels: string[] = [];
  let current: string | null = id;
  const guard = new Set<string>();
  while (current !== null && !guard.has(current)) {
    guard.add(current);
    const row: Row | null = findRow(rows, current);
    if (row === null) break;
    labels.unshift(row.node.label);
    current = row.parentId;
  }
  return labels;
}

/** Which ids the loader should fetch: the root, plus every open, uncached node. */
export function pendingLoads(state: ExplorerState): string[] {
  const wanted = [ROOT_ID, ...Object.keys(state.open).filter((id) => state.open[id])];
  const unique = [...new Set(wanted)];
  return unique.filter(
    (id) =>
      state.expansions[id] === undefined &&
      state.loading[id] !== true &&
      state.failures[id] === undefined,
  );
}
