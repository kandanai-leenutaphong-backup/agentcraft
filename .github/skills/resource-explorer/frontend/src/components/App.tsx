/**
 * One operational view: a toolbar, the tree, and whatever the selected node
 * is. No landing page and no dashboard — this surface exists to answer "what
 * is in this subscription, what is inside it, and which parts of it will not
 * answer".
 *
 * Loading is lazy, per node, and cached: a branch is expanded once and kept
 * until a reload evicts it, and one slow branch never blocks another. There is
 * no polling. Identity is the platform's; this bundle holds no token and
 * speaks to no identity provider.
 */

import {
  useCallback,
  useEffect,
  useMemo,
  useReducer,
  useRef,
  useState,
  useSyncExternalStore,
  type FormEvent,
  type JSX,
} from "react";

import { fetchContent, fetchSearch, fetchTree, MAX_SEARCH_TERM_CHARS } from "../api/client";
import { pickByLabel, pickResourceType } from "../api/reveal";
import {
  findRow,
  initialState,
  pendingLoads,
  reducer,
  selectedNode,
  treePath,
  visibleRows,
} from "../api/state";
import { applyTheme, readTheme, type Theme } from "../api/theme";
import { formatObservedAt } from "../api/format";
import { RejectedRequest, ROOT_ID, SessionExpired, type SearchHit, type TreeNode } from "../api/wire";
import { DetailPane } from "./DetailPane";
import { HelpDialog } from "./HelpDialog";
import { SearchPanel } from "./SearchPanel";
import { TreeView } from "./TreeView";

const LOGOUT_URL = "/.auth/logout?post_logout_redirect_uri=%2F";
const DESKTOP_QUERY = "(min-width: 768px)";

function useIsDesktop(): boolean {
  const subscribe = useCallback((notify: () => void) => {
    const query = window.matchMedia(DESKTOP_QUERY);
    query.addEventListener("change", notify);
    return () => query.removeEventListener("change", notify);
  }, []);
  return useSyncExternalStore(
    subscribe,
    () => window.matchMedia(DESKTOP_QUERY).matches,
    () => true,
  );
}

function messageOf(error: unknown): string {
  if (error instanceof RejectedRequest) return error.message;
  if (error instanceof Error) return error.message;
  return "An unknown error stopped this request.";
}

export function App(): JSX.Element {
  const [state, dispatch] = useReducer(reducer, initialState);
  const stateRef = useRef(state);
  stateRef.current = state;

  const treeInFlight = useRef<Set<string>>(new Set());
  const contentInFlight = useRef<Set<string>>(new Set());
  const searchInputRef = useRef<HTMLInputElement>(null);

  const isDesktop = useIsDesktop();
  const [detailOpen, setDetailOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const [resultsOpen, setResultsOpen] = useState(false);
  const [theme, setTheme] = useState<Theme>("sand");

  useEffect(() => {
    const initial = readTheme();
    setTheme(initial);
    applyTheme(initial);
  }, []);

  const loadTree = useCallback(async (id: string): Promise<void> => {
    if (treeInFlight.current.has(id)) return;
    treeInFlight.current.add(id);
    dispatch({ type: "request", id });
    try {
      const response = await fetchTree(id);
      dispatch({ type: "loaded", id, response });
    } catch (error) {
      if (error instanceof SessionExpired) dispatch({ type: "expired" });
      else dispatch({ type: "failed", id, message: messageOf(error) });
    } finally {
      treeInFlight.current.delete(id);
    }
  }, []);

  const loadContent = useCallback(async (id: string): Promise<void> => {
    if (contentInFlight.current.has(id)) return;
    contentInFlight.current.add(id);
    dispatch({ type: "contentRequest", id });
    try {
      const response = await fetchContent(id);
      dispatch({ type: "contentLoaded", id, response });
    } catch (error) {
      if (error instanceof SessionExpired) dispatch({ type: "expired" });
      else dispatch({ type: "contentFailed", id, message: messageOf(error) });
    } finally {
      contentInFlight.current.delete(id);
    }
  }, []);

  const rows = useMemo(() => visibleRows(state), [state]);
  const selected = selectedNode(state);
  const selectedId = state.selectedId;

  useEffect(() => {
    if (state.session === "expired") return;
    for (const id of pendingLoads(state)) void loadTree(id);
  }, [state, loadTree]);

  useEffect(() => {
    if (state.session === "expired") return;
    if (selected === null || !selected.hasContent) return;
    const id = selected.id;
    if (state.contents[id] !== undefined) return;
    if (state.contentLoading[id] === true) return;
    if (state.contentFailures[id] !== undefined) return;
    void loadContent(id);
  }, [state, selected, loadContent]);

  const onToggle = useCallback((id: string, open: boolean) => {
    dispatch({ type: "setOpen", id, open });
  }, []);

  const onSelect = useCallback(
    (id: string) => {
      dispatch({ type: "select", id });
      const row = findRow(visibleRows(stateRef.current), id);
      if (!isDesktop && row !== null && !row.node.expandable) setDetailOpen(true);
    },
    [isDesktop],
  );

  const onFocusRow = useCallback((id: string) => {
    dispatch({ type: "focus", id });
  }, []);

  const onRetryBranch = useCallback(
    (id: string) => {
      dispatch({ type: "evict", id });
      dispatch({ type: "setOpen", id, open: true });
    },
    [],
  );

  const onRetryContent = useCallback(() => {
    if (selectedId === null) return;
    dispatch({ type: "contentRequest", id: selectedId });
    void loadContent(selectedId);
  }, [selectedId, loadContent]);

  const refreshAll = useCallback(() => {
    treeInFlight.current.clear();
    contentInFlight.current.clear();
    dispatch({ type: "reset" });
  }, []);

  const refreshSelected = useCallback(() => {
    if (selected === null) return;
    treeInFlight.current.delete(selected.id);
    contentInFlight.current.delete(selected.id);
    dispatch({ type: "evict", id: selected.id });
    if (selected.expandable) dispatch({ type: "setOpen", id: selected.id, open: true });
  }, [selected]);

  const focusSearch = useCallback(() => {
    searchInputRef.current?.focus();
    searchInputRef.current?.select();
  }, []);

  const runSearch = useCallback(
    async (event: FormEvent<HTMLFormElement>): Promise<void> => {
      event.preventDefault();
      const term = stateRef.current.search.term.trim();
      if (term === "") {
        dispatch({
          type: "searchFailed",
          message: `Type something to search for — 1 to ${String(MAX_SEARCH_TERM_CHARS)} characters.`,
        });
        setResultsOpen(true);
        return;
      }
      dispatch({ type: "searchRequest", term });
      setResultsOpen(true);
      try {
        const response = await fetchSearch(term);
        dispatch({ type: "searchLoaded", response });
      } catch (error) {
        if (error instanceof SessionExpired) dispatch({ type: "expired" });
        else dispatch({ type: "searchFailed", message: messageOf(error) });
      }
    },
    [],
  );

  /** Children of a node, from cache when possible, fetched and cached when not. */
  const childrenOf = useCallback(
    async (id: string): Promise<TreeNode[]> => {
      const cached = stateRef.current.expansions[id];
      if (cached !== undefined) return cached.children;
      const response = await fetchTree(id);
      dispatch({ type: "loaded", id, response });
      return response.children;
    },
    [],
  );

  const openHit = useCallback(
    async (hit: SearchHit): Promise<void> => {
      setResultsOpen(false);
      dispatch({ type: "revealNote", message: `Opening ${hit.label} in the tree…` });
      const land = (id: string): void => {
        dispatch({ type: "select", id });
        dispatch({ type: "focus", id });
        dispatch({ type: "revealNote", message: null });
        dispatch({ type: "announce", message: `Opened ${hit.label} in the tree.` });
        if (!isDesktop) setDetailOpen(false);
      };
      const lost = (): void => {
        dispatch({
          type: "revealNote",
          message: `${hit.label} was not found under ${hit.resourceGroup} in the tree. It may have been created or removed since the tree was read — reload the tree and search again.`,
        });
      };
      try {
        dispatch({ type: "setOpen", id: ROOT_ID, open: true });
        const groups = await childrenOf(ROOT_ID);
        const group = pickByLabel(groups, hit.resourceGroup);
        if (group === null) {
          lost();
          return;
        }
        dispatch({ type: "setOpen", id: group.id, open: true });
        if (hit.kind === "resource_group") {
          land(group.id);
          return;
        }
        const types = await childrenOf(group.id);
        const type = pickResourceType(types, hit.type);
        if (type === null) {
          lost();
          return;
        }
        dispatch({ type: "setOpen", id: type.id, open: true });
        const resources = await childrenOf(type.id);
        const resource = pickByLabel(resources, hit.label);
        if (resource === null) {
          lost();
          return;
        }
        land(resource.id);
      } catch (error) {
        if (error instanceof SessionExpired) dispatch({ type: "expired" });
        else dispatch({ type: "revealNote", message: messageOf(error) });
      }
    },
    [childrenOf, isDesktop],
  );

  const toggleTheme = useCallback(() => {
    setTheme((current) => {
      const next: Theme = current === "sand" ? "dark" : "sand";
      applyTheme(next);
      return next;
    });
  }, []);

  if (state.session === "expired") return <SessionExpiredView />;

  const selectedContent = selectedId === null ? null : (state.contents[selectedId] ?? null);
  const selectedExpansion =
    selectedId === null ? null : (state.expansions[selectedId] ?? null);
  // The path the reader walked, which is what is on screen. The server's own
  // breadcrumb is the fallback for a node whose ancestors have been collapsed
  // out from under it.
  const walked = selected === null ? [] : treePath(rows, selected.id);
  const path =
    walked.length > 0
      ? walked
      : (selectedContent?.breadcrumb ?? selectedExpansion?.breadcrumb ?? []);

  const showDetail = isDesktop || detailOpen;
  const showTree = isDesktop || !detailOpen;
  const searchActive =
    resultsOpen && (state.search.loading || state.search.ran !== null || state.search.failure !== null);

  return (
    <div className="flex h-full min-w-0 flex-col bg-canvas text-primary">
      <header className="flex shrink-0 flex-wrap items-center gap-2 border-b border-border px-3 py-2">
        <h1 className="shrink-0 text-sm font-semibold tracking-tight sm:text-base">
          Azure Resource Explorer
        </h1>

        <form
          onSubmit={(event) => void runSearch(event)}
          role="search"
          className="order-last flex w-full min-w-0 items-center gap-1 md:order-none md:w-auto md:flex-1 md:max-w-lg"
        >
          <label htmlFor="estate-search" className="sr-only">
            Search every resource in the subscription
          </label>
          <input
            id="estate-search"
            ref={searchInputRef}
            type="search"
            value={state.search.term}
            maxLength={MAX_SEARCH_TERM_CHARS}
            onChange={(event) =>
              dispatch({ type: "searchTerm", term: event.target.value })
            }
            placeholder="Search the estate — name, type, group, location, tag"
            data-testid="search-input"
            className="min-h-[44px] min-w-0 flex-1 rounded border border-border bg-canvas2 px-3 text-sm text-primary placeholder:text-muted"
          />
          <button
            type="submit"
            data-testid="search-submit"
            className="min-h-[44px] shrink-0 rounded border border-border px-3 text-sm"
          >
            Search
          </button>
          {state.search.ran !== null && !resultsOpen ? (
            <button
              type="button"
              onClick={() => setResultsOpen(true)}
              data-testid="search-reopen"
              className="min-h-[44px] shrink-0 rounded border border-flow px-3 text-sm text-flow"
            >
              {state.search.hits.length} found
            </button>
          ) : null}
        </form>

        <div className="ml-auto flex shrink-0 items-center gap-1">
          <button
            type="button"
            onClick={() => setHelpOpen(true)}
            data-testid="help-open"
            aria-haspopup="dialog"
            className="min-h-[44px] min-w-[44px] rounded border border-border px-3 text-sm"
          >
            Help
          </button>
          <button
            type="button"
            onClick={toggleTheme}
            data-testid="theme-toggle"
            className="min-h-[44px] min-w-[44px] rounded border border-border px-3 text-sm"
          >
            {theme === "sand" ? "Dark" : "Light"}
          </button>
          <button
            type="button"
            onClick={refreshAll}
            data-testid="refresh-all"
            className="min-h-[44px] min-w-[44px] rounded border border-border px-3 text-sm"
          >
            Reload all
          </button>
          <a
            href={LOGOUT_URL}
            data-testid="sign-out"
            className="flex min-h-[44px] min-w-[44px] items-center rounded border border-border px-3 text-sm"
          >
            Sign out
          </a>
        </div>
      </header>

      {state.fixtures ? (
        <p
          data-testid="fixture-banner"
          className="shrink-0 border-b border-warning bg-warning-tint px-3 py-1.5 text-xs font-semibold text-warning"
        >
          Fixture data — this is a synthetic estate for testing, not a real subscription.
        </p>
      ) : null}

      <p
        data-testid="observed-at"
        className="shrink-0 border-b border-border-soft px-3 py-1 text-[11px] text-secondary"
      >
        {state.rootObservedAt === null
          ? "Reading the subscription…"
          : `Subscription read ${formatObservedAt(state.rootObservedAt)} · this view only reads, and never changes anything`}
      </p>

      {state.revealNote === null ? null : (
        <p
          data-testid="reveal-note"
          className="shrink-0 border-b border-flow bg-flow-tint px-3 py-1.5 text-xs text-flow"
        >
          {state.revealNote}
        </p>
      )}

      <div role="status" aria-live="polite" data-testid="live-region" className="sr-only">
        {state.announcement}
      </div>

      {searchActive ? (
        <SearchPanel
          search={state.search}
          onOpenHit={(hit) => void openHit(hit)}
          onClose={() => setResultsOpen(false)}
        />
      ) : null}

      <main className="flex min-h-0 min-w-0 flex-1 flex-col md:flex-row">
        {showTree ? (
          <div className="flex min-h-0 min-w-0 flex-1 flex-col border-border md:w-[22rem] md:flex-none md:border-r lg:w-[26rem]">
            <TreeView
              rows={rows}
              activeId={state.activeId}
              selectedId={selectedId}
              loadingRoot={state.loading[ROOT_ID] === true}
              rootFailure={state.failures[ROOT_ID] ?? null}
              onFocusRow={onFocusRow}
              onToggle={onToggle}
              onSelect={onSelect}
              onRetry={onRetryBranch}
              onSearchShortcut={focusSearch}
            />
            {!isDesktop ? (
              <button
                type="button"
                onClick={() => setDetailOpen(true)}
                disabled={selected === null}
                data-testid="open-detail"
                className="m-2 min-h-[44px] shrink-0 truncate rounded border border-border px-3 text-sm disabled:opacity-50"
              >
                {selected === null ? "Nothing selected yet" : `Open: ${selected.label}`}
              </button>
            ) : null}
          </div>
        ) : null}
        {showDetail ? (
          <DetailPane
            node={selected}
            path={path}
            expansion={selectedExpansion}
            expansionFailure={selectedId === null ? null : (state.failures[selectedId] ?? null)}
            content={selectedContent}
            contentLoading={selectedId !== null && state.contentLoading[selectedId] === true}
            contentFailure={selectedId === null ? null : (state.contentFailures[selectedId] ?? null)}
            showBack={!isDesktop}
            onBack={() => setDetailOpen(false)}
            onRefresh={refreshSelected}
            onRetryContent={onRetryContent}
          />
        ) : null}
      </main>

      <HelpDialog open={helpOpen} onClose={() => setHelpOpen(false)} />
    </div>
  );
}

function SessionExpiredView(): JSX.Element {
  return (
    <div
      data-testid="session-expired"
      className="flex h-full flex-col items-center justify-center gap-3 bg-canvas p-6 text-center text-primary"
    >
      <h1 className="text-lg font-semibold">Session expired</h1>
      <p className="max-w-md text-sm text-secondary">
        The identity provider no longer recognises this session. Sign in again to keep
        exploring; nothing was lost, and this page holds no credential of its own.
      </p>
      <button
        type="button"
        onClick={() => window.location.reload()}
        data-testid="session-retry"
        className="min-h-[44px] rounded border border-border px-4 text-sm"
      >
        Sign in again
      </button>
      <a href={LOGOUT_URL} data-testid="sign-out" className="text-sm text-flow underline">
        Sign out
      </a>
    </div>
  );
}
