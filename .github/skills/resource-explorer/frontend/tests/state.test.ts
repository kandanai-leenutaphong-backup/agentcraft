/**
 * The state machine behind the tree: what is cached, what is visible, what a
 * reload throws away, and where a node sits.
 */

import { describe, expect, test } from "vitest";

import {
  descendantIds,
  initialState,
  pendingLoads,
  reducer,
  selectedNode,
  treePath,
  visibleRows,
  type Action,
  type ExplorerState,
} from "../src/api/state";
import { ROOT_ID, type TreeNode, type TreeResponse } from "../src/api/wire";

function node(over: Partial<TreeNode> & { id: string; label: string }): TreeNode {
  return {
    kind: "resource_group",
    expandable: true,
    hasContent: false,
    status: "ok",
    detail: null,
    error: null,
    ...over,
  };
}

function response(over: Partial<TreeResponse> = {}): TreeResponse {
  return {
    schemaVersion: 1,
    fixtures: false,
    node: ROOT_ID,
    label: "Azure subscription",
    kind: "root",
    breadcrumb: ["Azure subscription"],
    status: "ok",
    children: [],
    truncated: false,
    hasContent: false,
    detail: null,
    error: null,
    observedAt: "2026-08-31T13:00:00Z",
    ...over,
  };
}

function apply(state: ExplorerState, actions: Action[]): ExplorerState {
  return actions.reduce(reducer, state);
}

const rootLoaded = response({
  children: [node({ id: "rg-a", label: "rg-a" }), node({ id: "rg-b", label: "rg-b" })],
});

const branchLoaded = response({
  node: "rg-a",
  label: "rg-a",
  kind: "resource_group",
  breadcrumb: ["Azure subscription", "rg-a"],
  children: [
    node({ id: "type-a", label: "Microsoft.Storage/storageAccounts (1)", kind: "resource_type" }),
  ],
});

describe("loading", () => {
  test("the root load makes the subscription a row and selects it", () => {
    const state = apply(initialState, [{ type: "loaded", id: ROOT_ID, response: rootLoaded }]);
    const rows = visibleRows(state);
    expect(rows.map((row) => row.node.label)).toEqual([
      "Azure subscription",
      "rg-a",
      "rg-b",
    ]);
    expect(rows[0]?.level).toBe(1);
    expect(rows[1]?.level).toBe(2);
    expect(state.selectedId).toBe(ROOT_ID);
    expect(state.activeId).toBe(ROOT_ID);
  });

  test("a closed branch hides its children without evicting them", () => {
    const state = apply(initialState, [
      { type: "loaded", id: ROOT_ID, response: rootLoaded },
      { type: "setOpen", id: "rg-a", open: true },
      { type: "loaded", id: "rg-a", response: branchLoaded },
      { type: "setOpen", id: "rg-a", open: false },
    ]);
    expect(visibleRows(state)).toHaveLength(3);
    expect(state.expansions["rg-a"]?.children).toHaveLength(1);
    expect(pendingLoads(state)).toEqual([]);
  });

  test("only the root and open uncached nodes are queued, once", () => {
    const requested = apply(initialState, [{ type: "request", id: ROOT_ID }]);
    expect(pendingLoads(requested)).toEqual([]);

    const opened = apply(initialState, [
      { type: "loaded", id: ROOT_ID, response: rootLoaded },
      { type: "setOpen", id: "rg-a", open: true },
      { type: "setOpen", id: "rg-b", open: true },
    ]);
    expect(pendingLoads(opened).sort()).toEqual(["rg-a", "rg-b"]);
  });

  test("a failed branch is not retried in a loop", () => {
    const state = apply(initialState, [
      { type: "loaded", id: ROOT_ID, response: rootLoaded },
      { type: "setOpen", id: "rg-a", open: true },
      { type: "failed", id: "rg-a", message: "boom" },
    ]);
    expect(pendingLoads(state)).toEqual([]);
    expect(state.failures["rg-a"]).toBe("boom");
  });
});

describe("eviction", () => {
  test("reloading a branch drops it and everything cached below it", () => {
    const loaded = apply(initialState, [
      { type: "loaded", id: ROOT_ID, response: rootLoaded },
      { type: "setOpen", id: "rg-a", open: true },
      { type: "loaded", id: "rg-a", response: branchLoaded },
      { type: "setOpen", id: "type-a", open: true },
      {
        type: "loaded",
        id: "type-a",
        response: response({ node: "type-a", children: [node({ id: "res-a", label: "acct" })] }),
      },
    ]);
    expect(descendantIds(loaded, "rg-a")).toEqual(["type-a", "res-a"]);

    const evicted = reducer(loaded, { type: "evict", id: "rg-a" });
    expect(evicted.expansions["rg-a"]).toBeUndefined();
    expect(evicted.expansions["type-a"]).toBeUndefined();
    expect(evicted.open["type-a"]).toBeUndefined();
    // The branch itself stays open so the reload refills it in place.
    expect(evicted.open["rg-a"]).toBe(true);
  });

  test("a full reload keeps the fixture flag but forgets every branch", () => {
    const loaded = apply(initialState, [
      { type: "loaded", id: ROOT_ID, response: response({ ...rootLoaded, fixtures: true }) },
      { type: "setOpen", id: "rg-a", open: true },
    ]);
    const reset = reducer(loaded, { type: "reset" });
    expect(reset.fixtures).toBe(true);
    expect(reset.expansions).toEqual({});
    expect(reset.rootNode).toBeNull();
    expect(reset.open).toEqual({ [ROOT_ID]: true });
  });
});

describe("what the reader is looking at", () => {
  const walked = apply(initialState, [
    { type: "loaded", id: ROOT_ID, response: rootLoaded },
    { type: "setOpen", id: "rg-a", open: true },
    { type: "loaded", id: "rg-a", response: branchLoaded },
    { type: "select", id: "type-a" },
  ]);

  test("the selected node is found wherever it sits", () => {
    expect(selectedNode(walked)?.label).toBe("Microsoft.Storage/storageAccounts (1)");
  });

  test("the path is the walk the reader actually made", () => {
    expect(treePath(visibleRows(walked), "type-a")).toEqual([
      "Azure subscription",
      "rg-a",
      "Microsoft.Storage/storageAccounts (1)",
    ]);
  });

  test("a collapsed-away node has no tree path, and the caller falls back", () => {
    const collapsed = reducer(walked, { type: "setOpen", id: "rg-a", open: false });
    expect(treePath(visibleRows(collapsed), "type-a")).toEqual([]);
  });

  test("aria positions come from the projection", () => {
    const rows = visibleRows(walked);
    const branch = rows.find((row) => row.node.id === "rg-a");
    expect(branch?.posinset).toBe(1);
    expect(branch?.setsize).toBe(2);
    expect(branch?.expanded).toBe(true);
  });
});

describe("search state", () => {
  test("a result set replaces the previous one and announces its size", () => {
    const state = apply(initialState, [
      { type: "searchTerm", term: "store" },
      { type: "searchRequest", term: "store" },
      {
        type: "searchLoaded",
        response: {
          schemaVersion: 1,
          fixtures: false,
          query: "store",
          status: "ok",
          hits: [
            {
              node: "abc",
              label: "hcstore",
              kind: "resource",
              resourceGroup: "rg-a",
              type: "Microsoft.Storage/storageAccounts",
              location: "eastus",
              matchedIn: "name",
              detail: null,
            },
          ],
          truncated: true,
          error: null,
          observedAt: "2026-08-31T13:00:00Z",
        },
      },
    ]);
    expect(state.search.loading).toBe(false);
    expect(state.search.ran).toBe("store");
    expect(state.search.truncated).toBe(true);
    expect(state.announcement).toContain("1 estate match");
  });

  test("a failure clears the hits rather than leaving stale ones on screen", () => {
    const state = apply(initialState, [
      { type: "searchRequest", term: "x" },
      { type: "searchFailed", message: "the server answered 500" },
    ]);
    expect(state.search.hits).toEqual([]);
    expect(state.search.failure).toContain("500");
  });
});

describe("session", () => {
  test("an expired session stops every in-flight indicator", () => {
    const state = apply(initialState, [
      { type: "request", id: ROOT_ID },
      { type: "contentRequest", id: "abc" },
      { type: "expired" },
    ]);
    expect(state.session).toBe("expired");
    expect(state.loading).toEqual({});
    expect(state.contentLoading).toEqual({});
  });
});
