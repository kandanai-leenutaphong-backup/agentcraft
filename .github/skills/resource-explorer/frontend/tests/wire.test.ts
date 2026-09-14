/**
 * The wire boundary, in both directions: every shape the contract declares
 * parses, and every shape it does not is refused rather than half-trusted.
 */

import { describe, expect, test } from "vitest";

import {
  CONTENT_KINDS,
  MalformedResponse,
  NODE_KINDS,
  NODE_STATUSES,
  parseContentResponse,
  parseSearchResponse,
  parseTreeResponse,
} from "../src/api/wire";
import { contentUrl, searchUrl, treeUrl } from "../src/api/client";

function treePayload(over: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    schemaVersion: 1,
    fixtures: true,
    node: "root",
    label: "Azure subscription",
    kind: "root",
    breadcrumb: ["Azure subscription"],
    status: "ok",
    children: [
      {
        id: "abc",
        label: "rg-one",
        kind: "resource_group",
        expandable: true,
        hasContent: false,
        status: "ok",
        detail: { location: "eastus", resources: 3, live: true, note: null },
        error: null,
      },
    ],
    truncated: false,
    hasContent: false,
    detail: null,
    error: null,
    observedAt: "2026-08-31T13:47:26Z",
    ...over,
  };
}

function contentPayload(over: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    schemaVersion: 1,
    fixtures: false,
    node: "abc",
    label: "file.txt",
    kind: "blob",
    breadcrumb: ["Azure subscription", "rg", "acct", "container", "file.txt"],
    status: "ok",
    contentKind: "text",
    mediaType: "text/plain",
    text: "hello",
    dataBase64: null,
    rows: null,
    columns: null,
    sizeBytes: 5,
    truncated: false,
    detail: null,
    error: null,
    observedAt: "2026-08-31T13:47:26Z",
    ...over,
  };
}

function searchPayload(over: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    schemaVersion: 1,
    fixtures: false,
    query: "store",
    status: "ok",
    hits: [
      {
        node: "abc",
        label: "hcstore",
        kind: "resource",
        resourceGroup: "rg-one",
        type: "Microsoft.Storage/storageAccounts",
        location: "eastus",
        matchedIn: "name",
        detail: { kind: "StorageV2" },
      },
    ],
    truncated: false,
    error: null,
    observedAt: "2026-08-31T13:47:26Z",
    ...over,
  };
}

describe("tree payloads", () => {
  test("a well-formed root parses into typed values", () => {
    const parsed = parseTreeResponse(treePayload());
    expect(parsed.children[0]?.detail?.["resources"]).toBe(3);
    expect(parsed.children[0]?.hasContent).toBe(false);
    expect(parsed.breadcrumb).toEqual(["Azure subscription"]);
  });

  test("every declared node kind and status is accepted", () => {
    for (const kind of NODE_KINDS) {
      for (const status of NODE_STATUSES) {
        const payload = treePayload({
          kind,
          status,
          children: [
            {
              id: "x",
              label: "x",
              kind,
              expandable: false,
              hasContent: true,
              status,
              detail: null,
              error: status === "ok" || status === "empty" ? null : "cause",
            },
          ],
        });
        expect(parseTreeResponse(payload).children[0]?.kind).toBe(kind);
      }
    }
  });

  test.each([
    ["schemaVersion", { schemaVersion: 2 }],
    ["children", { children: {} }],
    ["breadcrumb", { breadcrumb: "root" }],
    ["kind", { kind: "arm_inventory" }],
    ["status", { status: "degraded" }],
    ["truncated", { truncated: "yes" }],
    ["hasContent", { hasContent: null }],
  ])("a bad %s is refused", (_name, over) => {
    expect(() => parseTreeResponse(treePayload(over))).toThrow(MalformedResponse);
  });

  test("a child missing hasContent is refused, not defaulted", () => {
    const payload = treePayload({
      children: [
        {
          id: "x",
          label: "x",
          kind: "blob",
          expandable: false,
          status: "ok",
          detail: null,
          error: null,
        },
      ],
    });
    expect(() => parseTreeResponse(payload)).toThrow(MalformedResponse);
  });

  test("a nested detail value is refused; detail is a flat map of scalars", () => {
    const payload = treePayload({
      children: [
        {
          id: "x",
          label: "x",
          kind: "blob",
          expandable: false,
          hasContent: false,
          status: "ok",
          detail: { nested: { deep: 1 } },
          error: null,
        },
      ],
    });
    expect(() => parseTreeResponse(payload)).toThrow(MalformedResponse);
  });
});

describe("content payloads", () => {
  test("every content kind parses", () => {
    for (const contentKind of CONTENT_KINDS) {
      const parsed = parseContentResponse(contentPayload({ contentKind }));
      expect(parsed.contentKind).toBe(contentKind);
    }
  });

  test("rows and columns survive as arrays of records", () => {
    const parsed = parseContentResponse(
      contentPayload({
        contentKind: "rows",
        text: null,
        rows: [{ a: 1, b: { deep: true } }],
        columns: ["a", "b"],
        sizeBytes: 1,
      }),
    );
    expect(parsed.rows?.[0]?.["b"]).toEqual({ deep: true });
    expect(parsed.columns).toEqual(["a", "b"]);
  });

  test("a row that is not an object is refused", () => {
    expect(() =>
      parseContentResponse(contentPayload({ contentKind: "rows", rows: [1, 2] })),
    ).toThrow(MalformedResponse);
  });

  test("sizeBytes must be a number", () => {
    expect(() => parseContentResponse(contentPayload({ sizeBytes: "5" }))).toThrow(
      MalformedResponse,
    );
  });
});

describe("search payloads", () => {
  test("a hit keeps the node token it must be reopened with", () => {
    const parsed = parseSearchResponse(searchPayload());
    expect(parsed.hits[0]?.node).toBe("abc");
    expect(parsed.hits[0]?.matchedIn).toBe("name");
  });

  test("an empty result set is a status, not an error", () => {
    const parsed = parseSearchResponse(searchPayload({ status: "empty", hits: [] }));
    expect(parsed.status).toBe("empty");
    expect(parsed.error).toBeNull();
  });

  test("a hit missing matchedIn is refused", () => {
    const payload = searchPayload({
      hits: [
        {
          node: "abc",
          label: "x",
          kind: "resource",
          resourceGroup: "rg",
          type: "t",
          location: "eastus",
          detail: null,
        },
      ],
    });
    expect(() => parseSearchResponse(payload)).toThrow(MalformedResponse);
  });
});

describe("urls", () => {
  test("the root asks for no node at all", () => {
    expect(treeUrl("root")).toBe("/api/tree");
  });

  test("an opaque token is encoded, never interpolated raw", () => {
    const token = "a+b/c=d&e";
    expect(treeUrl(token)).toBe("/api/tree?node=a%2Bb%2Fc%3Dd%26e");
    expect(contentUrl(token)).toBe("/api/content?node=a%2Bb%2Fc%3Dd%26e");
  });

  test("a search term is encoded and the limit stays inside the contract", () => {
    expect(searchUrl("a b&c")).toBe("/api/search?q=a%20b%26c&limit=50");
  });
});
