/**
 * The keyboard model and the words every state is drawn with.
 *
 * The tables are checked for completeness rather than for their wording: a
 * kind or status added to the contract and forgotten here would otherwise
 * render as `undefined` in a badge.
 */

import { describe, expect, test } from "vitest";

import { keyboardMove } from "../src/api/keyboard";
import { visibleRows, type Row } from "../src/api/state";
import { KIND_ICON, KIND_LABEL, KIND_MEANING, matchedInLabel } from "../src/api/kinds";
import {
  answered,
  CONTENT_KIND_LABEL,
  detailValueText,
  showsStatusBadge,
  statusLabel,
  statusMeaning,
  statusRemedy,
  statusTone,
} from "../src/api/status";
import { CONTENT_KINDS, NODE_KINDS, NODE_STATUSES, ROOT_ID } from "../src/api/wire";
import { pickByLabel, pickResourceType } from "../src/api/reveal";
import type { TreeNode } from "../src/api/wire";

function row(over: Partial<Row> & { id: string; label: string }): Row {
  const { id, label, ...rest } = over;
  return {
    node: {
      id,
      label,
      kind: "resource_group",
      expandable: true,
      hasContent: false,
      status: "ok",
      detail: null,
      error: null,
    },
    level: 1,
    parentId: null,
    posinset: 1,
    setsize: 1,
    expanded: false,
    loading: false,
    expansion: null,
    failure: null,
    ...rest,
  };
}

const rows: Row[] = [
  row({ id: ROOT_ID, label: "Azure subscription", expanded: true }),
  row({ id: "a", label: "rg-a", level: 2, parentId: ROOT_ID, expanded: true, posinset: 1, setsize: 2 }),
  row({ id: "a1", label: "type", level: 3, parentId: "a", posinset: 1, setsize: 1 }),
  row({ id: "b", label: "rg-b", level: 2, parentId: ROOT_ID, posinset: 2, setsize: 2 }),
];

describe("keyboard", () => {
  test("down and up walk what is visible, and stop at the ends", () => {
    expect(keyboardMove(rows, ROOT_ID, "ArrowDown")).toEqual({ kind: "focus", id: "a" });
    expect(keyboardMove(rows, "b", "ArrowDown")).toEqual({ kind: "focus", id: "b" });
    expect(keyboardMove(rows, ROOT_ID, "ArrowUp")).toEqual({ kind: "focus", id: ROOT_ID });
  });

  test("home and end jump", () => {
    expect(keyboardMove(rows, "a1", "Home")).toEqual({ kind: "focus", id: ROOT_ID });
    expect(keyboardMove(rows, ROOT_ID, "End")).toEqual({ kind: "focus", id: "b" });
  });

  test("right opens a closed branch, then steps into it", () => {
    expect(keyboardMove(rows, "b", "ArrowRight")).toEqual({ kind: "open", id: "b" });
    expect(keyboardMove(rows, "a", "ArrowRight")).toEqual({ kind: "focus", id: "a1" });
  });

  test("left closes an open branch, then steps out to the parent", () => {
    expect(keyboardMove(rows, "a", "ArrowLeft")).toEqual({ kind: "close", id: "a" });
    expect(keyboardMove(rows, "a1", "ArrowLeft")).toEqual({ kind: "focus", id: "a" });
  });

  test("left at the root is not a trap and not a move", () => {
    const closedRoot = [row({ id: ROOT_ID, label: "Azure subscription" })];
    expect(keyboardMove(closedRoot, ROOT_ID, "ArrowLeft")).toBeNull();
  });

  test("right on a leaf does nothing rather than jumping elsewhere", () => {
    const leaf = [
      row({
        id: "leaf",
        label: "file.txt",
        expanded: false,
        node: {
          id: "leaf",
          label: "file.txt",
          kind: "blob",
          expandable: false,
          hasContent: true,
          status: "ok",
          detail: null,
          error: null,
        },
      }),
    ];
    expect(keyboardMove(leaf, "leaf", "ArrowRight")).toBeNull();
  });

  test("enter and space activate; slash leaves for the search box", () => {
    expect(keyboardMove(rows, "a", "Enter")).toEqual({ kind: "activate", id: "a" });
    expect(keyboardMove(rows, "a", " ")).toEqual({ kind: "activate", id: "a" });
    expect(keyboardMove(rows, "a", "/")).toEqual({ kind: "search" });
    expect(keyboardMove([], null, "/")).toEqual({ kind: "search" });
  });

  test("an unhandled key is left to the browser", () => {
    expect(keyboardMove(rows, "a", "PageDown")).toBeNull();
    expect(keyboardMove(rows, "a", "a")).toBeNull();
  });

  test("the projection and the keyboard agree on what is reachable", () => {
    const projected = visibleRows({
      rootNode: rows[0]?.node ?? null,
      expansions: {},
      contents: {},
      loading: {},
      contentLoading: {},
      failures: {},
      contentFailures: {},
      open: {},
      selectedId: null,
      activeId: null,
      fixtures: false,
      session: "active",
      announcement: "",
      rootObservedAt: null,
      search: {
        term: "",
        ran: null,
        loading: false,
        status: null,
        hits: [],
        truncated: false,
        error: null,
        failure: null,
        observedAt: null,
      },
      revealNote: null,
    });
    expect(projected).toHaveLength(1);
  });
});

describe("every declared value has words", () => {
  test("statuses", () => {
    for (const status of NODE_STATUSES) {
      expect(statusLabel(status)).toBeTruthy();
      expect(statusMeaning(status)).toBeTruthy();
      expect(statusTone(status)).toBeTruthy();
    }
    expect(statusRemedy("unreachable")).toContain("network");
    expect(statusRemedy("forbidden")).toContain("role");
    expect(showsStatusBadge("ok")).toBe(false);
    expect(showsStatusBadge("empty")).toBe(true);
    expect(answered("empty")).toBe(true);
    expect(answered("forbidden")).toBe(false);
  });

  test("a forbidden branch and an unreachable one read differently", () => {
    expect(statusMeaning("forbidden")).not.toBe(statusMeaning("unreachable"));
    expect(statusRemedy("forbidden")).not.toBe(statusRemedy("unreachable"));
    expect(statusTone("forbidden")).not.toBe(statusTone("unreachable"));
  });

  test("all twenty-one kinds", () => {
    expect(NODE_KINDS).toHaveLength(21);
    for (const kind of NODE_KINDS) {
      expect(KIND_LABEL[kind]).toBeTruthy();
      expect(KIND_MEANING[kind]).toBeTruthy();
      expect(KIND_ICON[kind]).toBeTruthy();
    }
  });

  test("all eight content kinds", () => {
    expect(CONTENT_KINDS).toHaveLength(8);
    for (const kind of CONTENT_KINDS) expect(CONTENT_KIND_LABEL[kind]).toBeTruthy();
  });

  test("where a search matched is spelled out, including a word we did not expect", () => {
    expect(matchedInLabel("resourceGroup")).toBe("matched on resource group");
    expect(matchedInLabel("somethingNew")).toBe("matched on somethingNew");
  });

  test("an empty value and an absent one are different facts", () => {
    expect(detailValueText("")).toBe("(empty)");
    expect(detailValueText(null)).toBe("(none)");
    expect(detailValueText(false)).toBe("false");
    expect(detailValueText(0)).toBe("0");
  });
});

describe("positioning a search hit", () => {
  const children: TreeNode[] = [
    {
      id: "t1",
      label: "Microsoft.Storage/storageAccounts (1)",
      kind: "resource_type",
      expandable: true,
      hasContent: false,
      status: "ok",
      detail: { type: "Microsoft.Storage/storageAccounts", count: 1 },
      error: null,
    },
    {
      id: "t2",
      label: "Microsoft.Kusto/clusters (2)",
      kind: "resource_type",
      expandable: true,
      hasContent: false,
      status: "ok",
      detail: null,
      error: null,
    },
  ];

  test("a type is matched on the detail the server sent, not on the counted label", () => {
    expect(pickResourceType(children, "microsoft.storage/storageaccounts")?.id).toBe("t1");
  });

  test("a type with no detail still matches on its label prefix", () => {
    expect(pickResourceType(children, "Microsoft.Kusto/clusters")?.id).toBe("t2");
  });

  test("a type that is not there is null, never a wrong guess", () => {
    expect(pickResourceType(children, "Microsoft.Web/sites")).toBeNull();
    expect(pickByLabel(children, "nothing")).toBeNull();
  });

  test("labels match without regard to case", () => {
    expect(pickByLabel(children, "MICROSOFT.KUSTO/CLUSTERS (2)")?.id).toBe("t2");
  });
});
