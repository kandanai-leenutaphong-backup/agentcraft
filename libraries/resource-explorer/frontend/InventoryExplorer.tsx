import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";
import type { ReactNode } from "react";
import { createClient, SourceDisabledError, StaleSelectionError, type ClientOptions } from "./client";
import { DetailPane } from "./DetailPane";
import {
  NO_SOURCES,
  enabledIds,
  intersect,
  isEnabled,
  prune,
  readSelection,
  selectAll,
  selectNone,
  selectionHeader,
  toggle,
  writeSelection,
  type StoredSelection,
} from "./selection";
import {
  effectiveActiveId,
  initialState,
  pendingLoads,
  reducer,
  selectedNode,
  useCaseLabel,
  visibleRows,
} from "./state";
import { TreeView } from "./TreeView";
import { ROOT_ID, type SelectionSource } from "./wire";

/**
 * The composed inventory surface: a tree of use cases and sources, a detail
 * pane, and a per-tab selection.
 *
 * NEW IN THIS COMPONENT. Upstream's `App.tsx` is a whole page with its own
 * theme switch, help dialog, search panel and breadcrumb bar; this is a panel
 * a host drops into a tab it already owns.
 *
 * Four rules the effects here exist to keep:
 *
 * 1. A response to a question the reader has changed is discarded. Every
 *    request carries the generation it was issued in, and the reducer drops a
 *    stale one; in-flight requests are also aborted at the wire.
 * 2. The selection lives in this tab and is sent per request. Nothing about it
 *    is stored on the server, so another tab is unaffected.
 * 3. A tab holding an id the server no longer declares heals itself by
 *    **narrowing**, never by widening. The catalogue is re-read with a
 *    selection that reads nothing, the surviving ids are kept, and a list with
 *    no survivors becomes "none" with an explanation. Resetting to "all" would
 *    switch back on every source the reader had switched off, which is the one
 *    thing the switch exists to prevent.
 * 4. **The set of sources comes from `/selection`, never from the tree.** The
 *    tree is lazily expanded, so the ids it has seen are the ids of whichever
 *    use cases happen to be open. Reconciling a selection against that set
 *    silently drops every source in a collapsed branch — observed, in a
 *    browser: toggling one source rewrote the selection to the three ids of
 *    the one expanded use case.
 */

export interface InventoryExplorerProps extends ClientOptions {
  /** Row bound for one preview. The server clamps it again regardless. */
  previewRows?: number;
  renderLayout?: (panes: { navigation: ReactNode; detail: ReactNode }) => ReactNode;
  onSelect?: () => void;
  selectionActive?: boolean;
  highlightedSourceIds?: readonly string[];
}

const NO_DEPENDENCIES: readonly string[] = [];
const STALE_NOTICE =
  "The declared sources changed. Checking which of this session's sources still exist; nothing is switched back on automatically.";

export function InventoryExplorer({ previewRows = 25, renderLayout, onSelect,
  selectionActive = true, highlightedSourceIds = NO_DEPENDENCIES, ...clientOptions }: InventoryExplorerProps) {
  const client = useMemo(() => createClient(clientOptions), [clientOptions.base, clientOptions.fetchImpl]);
  const [state, dispatch] = useReducer(reducer, initialState);
  const [selection, setSelection] = useState<StoredSelection>(() => readSelection());
  const [catalogue, setCatalogue] = useState<SelectionSource[]>([]);
  const [notice, setNotice] = useState<string>("");
  const [staleTick, setStaleTick] = useState(0);
  const reconciling = useRef(false);
  const inFlight = useRef<Set<AbortController>>(new Set());
  const revealedDependencies = useRef("");

  const generation = state.generation;
  const selectionRef = useRef(selection);
  selectionRef.current = selection;

  const issue = useCallback(() => {
    const controller = new AbortController();
    inFlight.current.add(controller);
    return controller;
  }, []);

  const settle = useCallback((controller: AbortController) => {
    inFlight.current.delete(controller);
  }, []);

  const abortAll = useCallback(() => {
    for (const controller of inFlight.current) controller.abort();
    inFlight.current.clear();
  }, []);

  const handle = useCallback((error: unknown): string => {
    if (error instanceof StaleSelectionError) {
      // The manifest moved under this tab. Reconcile by narrowing — see rule 3.
      if (!reconciling.current) {
        reconciling.current = true;
        setStaleTick((tick) => tick + 1);
      }
      return STALE_NOTICE;
    }
    if (error instanceof SourceDisabledError) {
      return "This source is switched off for this browser session.";
    }
    return error instanceof Error ? error.message : String(error);
  }, []);

  // ---- reconciling a rejected selection -----------------------------------
  // Re-asks what exists with a selection that reads nothing, so recovering
  // costs no source read, and keeps only the ids that survived.

  useEffect(() => {
    if (staleTick === 0) return;
    const controller = issue();
    client
      .selection(NO_SOURCES, controller.signal)
      .then((response) => {
        const valid = response.sources.map((item) => item.sourceId);
        const current = selectionRef.current;
        const next = intersect(current, valid);
        reconciling.current = false;
        if (selectionHeader(next) === selectionHeader(current)) {
          setNotice(
            "The declared sources changed and this session's selection no longer" +
              " matches them. Choose which sources to switch on; none were" +
              " switched on automatically.",
          );
          return;
        }
        const message =
          next.mode === "none"
            ? "The sources this session had on are no longer declared. Everything is off until you choose one; nothing was switched back on."
            : `The declared sources changed. Kept the ${String(next.ids.length)} still-declared source(s) that were on; nothing was switched back on.`;
        writeSelection(next);
        setSelection(next);
        setCatalogue(response.sources);
        setNotice(message);
        dispatch({ type: "invalidate", message, selection: next });
      })
      .catch((error: unknown) => {
        reconciling.current = false;
        if (controller.signal.aborted) return;
        setNotice(error instanceof Error ? error.message : String(error));
      })
      .finally(() => settle(controller));
  }, [staleTick, client, issue, settle]);

  // ---- what exists at all -------------------------------------------------
  // Authoritative, and deliberately not derived from the tree: see rule 4.

  useEffect(() => {
    const controller = issue();
    client
      .selection(selectionRef.current, controller.signal)
      .then((response) => setCatalogue(response.sources))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setNotice(handle(error));
      })
      .finally(() => settle(controller));
  }, [client, generation, issue, settle, handle]);

  const known = useMemo(() => catalogue.map((item) => item.sourceId), [catalogue]);

  useEffect(() => {
    if (highlightedSourceIds.length === 0) {
      revealedDependencies.current = "";
      return;
    }
    const root = state.expansions[ROOT_ID];
    if (!root || catalogue.length === 0) return;
    const key = `${generation}:${JSON.stringify(highlightedSourceIds)}`;
    if (revealedDependencies.current === key) return;
    revealedDependencies.current = key;
    const owners = new Set(catalogue.filter((source) => highlightedSourceIds.includes(source.sourceId))
      .map((source) => source.useCaseId));
    if (owners.size === 0) return;
    dispatch({ type: "setOpen", id: ROOT_ID, open: true });
    for (const branch of root.children) {
      if (owners.has(branch.useCaseId)) dispatch({ type: "setOpen", id: branch.id, open: true });
    }
  }, [highlightedSourceIds, catalogue, generation, state.expansions]);

  // ---- tree ---------------------------------------------------------------

  useEffect(() => {
    const wanted = pendingLoads(state);
    if (wanted.length === 0) return;
    for (const id of wanted) {
      dispatch({ type: "request", id });
      const controller = issue();
      client
        .tree(id === ROOT_ID ? "" : id, selectionRef.current, controller.signal)
        .then((response) => {
          dispatch({ type: "loaded", id, response, generation });
        })
        .catch((error: unknown) => {
          if (controller.signal.aborted) return;
          dispatch({ type: "failed", id, message: handle(error), generation });
        })
        .finally(() => settle(controller));
    }
  }, [state, client, generation, issue, settle, handle]);

  // ---- the selected source's metadata --------------------------------------

  const node = selectedNode(state);
  const selectedId = state.selectedId;

  const loadResource = useCallback(
    (id: string) => {
      dispatch({ type: "resourceRequest", id });
      const controller = issue();
      client
        .resource(id, selectionRef.current, controller.signal)
        .then((response) => {
          dispatch({ type: "resourceLoaded", id, response, generation });
        })
        .catch((error: unknown) => {
          if (controller.signal.aborted) return;
          dispatch({ type: "resourceFailed", id, message: handle(error), generation });
        })
        .finally(() => settle(controller));
    },
    [client, generation, issue, settle, handle],
  );

  const loadContent = useCallback(
    (id: string) => {
      dispatch({ type: "contentRequest", id });
      const controller = issue();
      client
        .content(id, selectionRef.current, previewRows, controller.signal)
        .then((response) => {
          dispatch({ type: "contentLoaded", id, response, generation });
        })
        .catch((error: unknown) => {
          if (controller.signal.aborted) return;
          dispatch({ type: "contentFailed", id, message: handle(error), generation });
        })
        .finally(() => settle(controller));
    },
    [client, generation, issue, settle, handle, previewRows],
  );

  useEffect(() => {
    if (node === null || node.kind !== "source" || selectedId === null) return;
    if (!node.configured || node.enabled === false) return;
    if (state.resources[selectedId] !== undefined) return;
    if (state.resourceLoading[selectedId] === true) return;
    if (state.resourceFailures[selectedId] !== undefined) return;
    loadResource(selectedId);
  }, [node, selectedId, state.resources, state.resourceLoading, state.resourceFailures, loadResource]);

  // ---- selection ----------------------------------------------------------

  const applySelection = useCallback(
    (next: StoredSelection, message: string) => {
      abortAll();
      writeSelection(next);
      setSelection(next);
      setNotice("");
      dispatch({ type: "invalidate", message, selection: next });
    },
    [abortAll],
  );

  const onToggleSource = useCallback(
    (nodeId: string) => {
      const row = visibleRows(state).find((candidate) => candidate.node.id === nodeId);
      const sourceId = row?.node.sourceId ?? "";
      if (!sourceId) return;
      const next = toggle(selectionRef.current, sourceId, known);
      applySelection(
        next,
        `${row?.node.label ?? sourceId} is now ${isEnabled(next, sourceId) ? "on" : "off"} for this session.`,
      );
    },
    [state, known, applySelection],
  );

  useEffect(() => {
    if (known.length === 0) return;
    const pruned = prune(selectionRef.current, known);
    if (pruned !== selectionRef.current) {
      writeSelection(pruned);
      setSelection(pruned);
    }
  }, [known.join(",")]);

  const enabled = enabledIds(selection, known);
  const rows = visibleRows(state);
  const active = effectiveActiveId(rows, state.activeId);

  const navigation = (
      <div className="inv-panel inv-panel-tree">
        <div className="inv-panel-head">
          <h2>Data sources</h2>
          <div className="inv-selection-controls">
            <span aria-live="polite">
              {known.length === 0
                ? "…"
                : `${String(enabled.length)}/${String(known.length)} sources on`}
            </span>
            <button
              type="button"
              className="inv-button inv-button-quiet"
              onClick={() => applySelection(selectAll(), "All sources are on for this session.")}
            >
              All on
            </button>
            <button
              type="button"
              className="inv-button inv-button-quiet"
              onClick={() => applySelection(selectNone(), "All sources are off for this session.")}
            >
              All off
            </button>
          </div>
        </div>
        <TreeView
          rows={rows}
          activeId={active}
          selectedId={selectionActive ? state.selectedId : null}
          label="Data sources by use case"
          highlightedSourceIds={highlightedSourceIds}
          onFocus={(id) => dispatch({ type: "focus", id })}
          onOpen={(id, open) => dispatch({ type: "setOpen", id, open })}
          onSelect={(id) => { dispatch({ type: "select", id }); onSelect?.(); }}
          onToggleSource={onToggleSource}
        />
        <p className="inv-scope-note">{state.selectionScope}</p>
      </div>
  );

  const detail = (
      <div className="inv-panel inv-panel-detail">
        {notice ? <p className="inv-notice">{notice}</p> : null}
        <DetailPane
          node={node}
          resource={selectedId !== null ? (state.resources[selectedId] ?? null) : null}
          content={selectedId !== null ? (state.contents[selectedId] ?? null) : null}
          resourceLoading={selectedId !== null && state.resourceLoading[selectedId] === true}
          contentLoading={selectedId !== null && state.contentLoading[selectedId] === true}
          resourceFailure={selectedId !== null ? (state.resourceFailures[selectedId] ?? null) : null}
          contentFailure={selectedId !== null ? (state.contentFailures[selectedId] ?? null) : null}
          onRetryResource={() => selectedId !== null && loadResource(selectedId)}
          onRetryContent={() => selectedId !== null && loadContent(selectedId)}
          onLoadContent={() => selectedId !== null && loadContent(selectedId)}
          useCase={useCaseLabel(state, node)}
        />
      </div>
  );

  return <>
      {renderLayout ? renderLayout({ navigation, detail })
        : <div className="inv-shell">{navigation}{detail}</div>}
      <p className="inv-visually-hidden" role="status" aria-live="polite">
        {state.announcement}
      </p>
  </>;
}
