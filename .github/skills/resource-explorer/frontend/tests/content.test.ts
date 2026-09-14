/**
 * The rendering boundary: delimited text, markdown, JSON colouring, image
 * bytes, row sorting and the honest numbers beside them.
 *
 * The security-relevant cases are here rather than in a browser test, because
 * a link scheme and a media type are decided before anything reaches the DOM.
 */

import { describe, expect, test } from "vitest";

import { delimiterFor, parseDelimited, toDelimitedTable } from "../src/api/delimited";
import { parseMarkdown, parseInline, safeHref } from "../src/api/markdown";
import { imageDataUrl, tokenizeJson } from "../src/api/render";
import {
  cellText,
  columnsOf,
  compareValues,
  nextSort,
  sortAriaValue,
  sortRows,
  truncateCell,
} from "../src/api/rows";
import {
  childCountText,
  formatBytes,
  formatCount,
  formatObservedAt,
  rowSampleText,
  truncationText,
} from "../src/api/format";

describe("delimited text", () => {
  test("a quoted field keeps its commas and newlines", () => {
    const records = parseDelimited('a,b\n"x,1","y\n2"\n', ",");
    expect(records).toEqual([
      ["a", "b"],
      ["x,1", "y\n2"],
    ]);
  });

  test("a doubled quote is one quote", () => {
    expect(parseDelimited('a\n"say ""hi"""\n', ",")).toEqual([["a"], ['say "hi"']]);
  });

  test("tab-separated is taken from the media type, not guessed", () => {
    expect(delimiterFor("text/tab-separated-values", "a\tb\n")).toBe("\t");
    expect(delimiterFor("text/csv", "a,b\n")).toBe(",");
    expect(delimiterFor("text/plain", "a;b;c\n")).toBe(";");
  });

  test("a header row becomes addressable columns", () => {
    const table = toDelimitedTable("day,requests\n2026-08-29,1204\n", "text/csv");
    expect(table.columns).toEqual(["day", "requests"]);
    expect(table.rows).toEqual([{ day: "2026-08-29", requests: "1204" }]);
  });

  test("blank and duplicate header names are still addressable", () => {
    const table = toDelimitedTable("a,,a\n1,2,3\n", "text/csv");
    expect(table.columns).toEqual(["a", "column 2", "a (2)"]);
    expect(table.rows[0]).toEqual({ a: "1", "column 2": "2", "a (2)": "3" });
  });

  test("a short row leaves the missing cells empty rather than shifting them", () => {
    const table = toDelimitedTable("a,b,c\n1,2\n", "text/csv");
    expect(table.rows[0]).toEqual({ a: "1", b: "2", c: "" });
  });

  test("text with no delimiter at all is a one-column table, not a crash", () => {
    const table = toDelimitedTable("only\nlines\n", "text/csv");
    expect(table.columns).toEqual(["only"]);
    expect(table.rows).toEqual([{ only: "lines" }]);
  });
});

describe("markdown", () => {
  test("headings, lists, code and rules parse", () => {
    const blocks = parseMarkdown(
      "# Title\n\nsome text\n\n- one\n- two\n\n```json\n{}\n```\n\n---\n",
    );
    expect(blocks.map((block) => block.type)).toEqual([
      "heading",
      "paragraph",
      "list",
      "code",
      "rule",
    ]);
  });

  test("a table with a divider row parses as a table", () => {
    const blocks = parseMarkdown("| a | b |\n| --- | --- |\n| 1 | 2 |\n");
    expect(blocks[0]?.type).toBe("table");
  });

  test("inline emphasis, code and links parse", () => {
    const nodes = parseInline("a **b** and `c` and [d](https://example.com)");
    expect(nodes.map((node) => node.type)).toEqual([
      "text",
      "strong",
      "text",
      "code",
      "text",
      "link",
    ]);
  });

  test("only http, https and mailto links are followed", () => {
    expect(safeHref("https://example.com/x")).toBe("https://example.com/x");
    expect(safeHref("mailto:a@b.c")).toBe("mailto:a@b.c");
    expect(safeHref("javascript:alert(1)")).toBeNull();
    expect(safeHref("data:text/html,<script>alert(1)</script>")).toBeNull();
    expect(safeHref("vbscript:msgbox(1)")).toBeNull();
    expect(safeHref("/relative/path")).toBeNull();
  });

  test("a refused link stays as text, so nothing becomes clickable by accident", () => {
    const source = "[click](javascript:alert(1))";
    const nodes = parseInline(source);
    expect(nodes.every((node) => node.type === "text")).toBe(true);
    expect(nodes.map((node) => (node.type === "text" ? node.value : "")).join("")).toBe(
      source,
    );
  });

  test("raw HTML is content, never markup", () => {
    const blocks = parseMarkdown("<img src=x onerror=alert(1)>\n");
    expect(blocks[0]).toEqual({
      type: "paragraph",
      children: [{ type: "text", value: "<img src=x onerror=alert(1)>" }],
    });
  });
});

describe("json colouring", () => {
  test("keys, strings, numbers and keywords are separated", () => {
    const tokens = tokenizeJson('{\n  "a": "x",\n  "b": 12,\n  "c": true,\n  "d": null\n}');
    const kinds = tokens.filter((token) => token.kind !== "punct").map((token) => token.kind);
    expect(kinds).toEqual(["key", "string", "key", "number", "key", "keyword", "key", "keyword"]);
  });

  test("colouring never changes the text", () => {
    const text = '{"a": "b\\"c", "n": -1.5e3}';
    expect(tokenizeJson(text).map((token) => token.text).join("")).toBe(text);
  });
});

describe("image bytes", () => {
  test("a bitmap type becomes a data url", () => {
    expect(imageDataUrl("image/png", "iVBORw0KGgo=")).toBe(
      "data:image/png;base64,iVBORw0KGgo=",
    );
    expect(imageDataUrl("image/JPEG; charset=binary", "AAAA")).toBe(
      "data:image/jpeg;base64,AAAA",
    );
  });

  test("svg is refused however it is spelled, because it would execute here", () => {
    expect(imageDataUrl("image/svg+xml", "PHN2Zz48L3N2Zz4=")).toBeNull();
    expect(imageDataUrl("IMAGE/SVG+XML", "PHN2Zz48L3N2Zz4=")).toBeNull();
  });

  test("a non-image type and a non-base64 payload are both refused", () => {
    expect(imageDataUrl("text/html", "AAAA")).toBeNull();
    expect(imageDataUrl("image/png", 'AA"><script>')).toBeNull();
    expect(imageDataUrl("image/png", null)).toBeNull();
  });
});

describe("rows", () => {
  const rows = [
    { name: "b", size: 2, nested: { x: 1 } },
    { name: "a", size: 10 },
    { name: "c", size: null },
  ];

  test("columns come from the server when it declares them", () => {
    expect(columnsOf(rows, ["size", "name"])).toEqual(["size", "name"]);
  });

  test("columns are the union of the keys when it does not", () => {
    expect(columnsOf(rows, null)).toEqual(["name", "size", "nested"]);
  });

  test("a nested value renders as its JSON, not as [object Object]", () => {
    expect(cellText({ x: 1 })).toBe('{"x":1}');
    expect(cellText(null)).toBe("(null)");
    expect(cellText(undefined)).toBe("");
    expect(cellText(false)).toBe("false");
  });

  test("a long cell is cut with a mark and reports that it was cut", () => {
    const long = "x".repeat(500);
    const { text, truncated } = truncateCell(long);
    expect(truncated).toBe(true);
    expect(text.endsWith("…")).toBe(true);
    expect(truncateCell("short").truncated).toBe(false);
  });

  test("numbers sort numerically, not as strings", () => {
    expect(compareValues(10, 2)).toBeGreaterThan(0);
    expect(compareValues("10", "2")).toBeGreaterThan(0);
  });

  test("absent values stay last in both directions", () => {
    const ascending = sortRows(rows, { column: "size", direction: "asc" });
    const descending = sortRows(rows, { column: "size", direction: "desc" });
    expect(ascending.map((row) => row["name"])).toEqual(["b", "a", "c"]);
    expect(descending.map((row) => row["name"])).toEqual(["a", "b", "c"]);
  });

  test("sorting is stable for equal values", () => {
    const equal = [
      { k: 1, id: "first" },
      { k: 1, id: "second" },
    ];
    expect(
      sortRows(equal, { column: "k", direction: "desc" }).map((row) => row["id"]),
    ).toEqual(["first", "second"]);
  });

  test("a header cycles ascending, descending, unsorted", () => {
    const first = nextSort(null, "size");
    expect(first).toEqual({ column: "size", direction: "asc" });
    const second = nextSort(first, "size");
    expect(second).toEqual({ column: "size", direction: "desc" });
    expect(nextSort(second, "size")).toBeNull();
    expect(nextSort(second, "name")).toEqual({ column: "name", direction: "asc" });
  });

  test("the sort state is announced on the column that carries it", () => {
    expect(sortAriaValue({ column: "size", direction: "asc" }, "size")).toBe("ascending");
    expect(sortAriaValue({ column: "size", direction: "asc" }, "name")).toBe("none");
    expect(sortAriaValue(null, "size")).toBe("none");
  });
});

describe("honest numbers", () => {
  test("bytes read as bytes", () => {
    expect(formatBytes(0)).toBe("0 bytes");
    expect(formatBytes(116)).toBe("116 bytes");
    expect(formatBytes(24_522)).toBe("23.9 KiB");
    expect(formatBytes(4 * 1024 ** 3)).toBe("4.0 GiB");
  });

  test("a truncated read says how big the whole object is", () => {
    expect(truncationText(4 * 1024 ** 3, true)).toContain("4.0 GiB");
    expect(truncationText(100, false)).toBeNull();
  });

  test("a sampled table says the sample is not the table", () => {
    expect(rowSampleText(100, true)).toContain("100 rows");
    expect(rowSampleText(100, false)).toBeNull();
  });

  test("a truncated listing still says it succeeded", () => {
    expect(childCountText(500, true)).toBe("500 items shown — more exist");
    expect(childCountText(1, false)).toBe("1 item");
    expect(formatCount(0, "row")).toBe("0 rows");
  });

  test("an unparseable timestamp is shown as it arrived rather than as Invalid Date", () => {
    expect(formatObservedAt("not a time")).toBe("not a time");
    expect(formatObservedAt("2026-08-31T13:47:26Z")).toContain("2026-08-31T13:47:26Z");
  });
});
