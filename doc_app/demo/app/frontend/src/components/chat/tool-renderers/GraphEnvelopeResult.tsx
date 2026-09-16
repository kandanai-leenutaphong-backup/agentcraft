/**
 * GraphEnvelopeResult — renders the typed envelopes returned by the
 * `graph_*` extras tools (graph_bus_boundary, graph_corridor_endpoints,
 * graph_breaker_neighbourhood, graph_common_mode_devices,
 * graph_switch_state_snapshot) inside the ToolResultCard scaffold.
 *
 * Envelope shape:
 *   {
 *     <scope keys>: ...   // e.g. station, voltage_kv, bus, device, scope
 *     summary: { ...counts },
 *     <list_a>: [ {...}, ... ],
 *     <list_b>: [ {...}, ... ],
 *     <nested_a>: { ...scalars-or-string-arrays },
 *     note?: string,
 *     error?: bool | string,
 *   }
 *
 * Render strategy (each list section is one of):
 *   - "Simple table" — every row is purely scalar after pre-formatting
 *     (string arrays collapsed to "a, b, c +N more"; nested single
 *     objects collapsed to "k=v · k=v"). Uses the shared ResultTable.
 *   - "Card list"   — at least one row carries a nested array-of-objects
 *     (e.g. graph_breaker_neighbourhood.terminals[*].neighbours). Each
 *     row renders as an open <details> with its scalar fields as a chip
 *     strip and each nested array-of-objects field as its own sub-table.
 *
 * Top-level nested single objects (e.g. graph_common_mode_devices.shared
 * / verdict) render as their own labelled signal band beneath the lists,
 * so they are not silently dropped.
 *
 * Audit invariant: every body lands inside ToolResultCard
 * ([app/frontend/tests/chat/toolResultCard.test.tsx](../../../../../tests/chat/toolResultCard.test.tsx)).
 */

import { JsonFallback } from "./JsonFallback";
import { ToolResultCard } from "./ToolResultCard";
import { ResultTable } from "./ResultTable";
import { extractError, parseToolResult } from "./helpers";
import { getProminentColumns, type ToolResultProps } from "./index";
import type { ReactElement } from "react";

/* Keys that name the investigation scope (badges). */
const SCOPE_KEYS = [
  "station",
  "voltage_kv",
  "bus",
  "bus_resolved_to",
  "scope",
  "device",
];

/* Keys handled outside the "list section" loop. */
const META_KEYS = new Set<string>([
  ...SCOPE_KEYS,
  "summary",
  "note",
  "error",
  "detail",
  "resolved_via",
  "bus_resolved_path",
  "inputs", // common_mode_devices: also a list, but better as a side panel
]);

export function GraphEnvelopeResult({ result, toolName }: ToolResultProps) {
  const parsed = parseToolResult(result);
  if (!parsed) return <JsonFallback result={result} />;

  /* Error envelope short-circuit. */
  const errDetail = extractError(parsed);
  if (errDetail) {
    return <ToolResultCard error={{ detail: errDetail }} />;
  }

  const prominent = getProminentColumns(toolName);
  const scope = buildScopeBadges(parsed);
  const signal = buildSummaryChips(parsed.summary);
  const listSections = buildListSections(parsed);
  const sideObjects = buildSideObjects(parsed);
  const inputsSection = buildInputsSection(parsed.inputs);
  const note = typeof parsed.note === "string" ? parsed.note : null;

  const hasAnyBody =
    scope.length > 0 ||
    signal.length > 0 ||
    listSections.length > 0 ||
    sideObjects.length > 0 ||
    inputsSection !== null ||
    !!note;

  if (!hasAnyBody) return <JsonFallback result={result} />;

  return (
    <ToolResultCard scope={scope} signal={signal} note={note} noteTone="warning">
      <div className="flex flex-col gap-2">
        {inputsSection}
        {listSections.map((s) => (
          <ListSectionRenderer key={s.key} section={s} prominent={prominent} />
        ))}
        {sideObjects.map((obj) => (
          <SidePanel key={obj.key} title={obj.key} entries={obj.entries} />
        ))}
      </div>
    </ToolResultCard>
  );
}

/* ── scope badges ─────────────────────────────────────────────────────── */

function buildScopeBadges(parsed: Record<string, unknown>): { label: string; value: string }[] {
  const out: { label: string; value: string }[] = [];

  const scope = parsed.scope;
  if (scope && typeof scope === "object" && !Array.isArray(scope)) {
    for (const [k, v] of Object.entries(scope as Record<string, unknown>)) {
      if (isScalar(v) && String(v).length > 0) {
        out.push({ label: k, value: String(v) });
      }
    }
  }

  for (const key of SCOPE_KEYS) {
    if (key === "scope" || key === "device") continue;
    const v = parsed[key];
    if (isScalar(v) && String(v).length > 0) {
      out.push({ label: key, value: String(v) });
    }
  }

  const device = parsed.device;
  if (device && typeof device === "object" && !Array.isArray(device)) {
    const d = device as Record<string, unknown>;
    const label = (d.name as string) || (d.path as string) || (d.mrid as string);
    if (label) out.push({ label: String(d.type || "device"), value: String(label) });
  }

  return out;
}

/* ── summary chips ────────────────────────────────────────────────────── */

function buildSummaryChips(summary: unknown): { label: string; value: string }[] {
  if (!summary || typeof summary !== "object" || Array.isArray(summary)) return [];
  const out: { label: string; value: string }[] = [];
  for (const [k, v] of Object.entries(summary as Record<string, unknown>)) {
    if (isScalar(v)) out.push({ label: k, value: String(v) });
  }
  return out;
}

/* ── list sections ────────────────────────────────────────────────────── */

interface ListSection {
  key: string;
  rows: Record<string, unknown>[];
  hasNestedObjectArray: boolean;
}

function buildListSections(parsed: Record<string, unknown>): ListSection[] {
  const out: ListSection[] = [];
  for (const [k, v] of Object.entries(parsed)) {
    if (META_KEYS.has(k)) continue;
    if (!Array.isArray(v) || v.length === 0) continue;
    const objectRows = v.filter(
      (it) => it && typeof it === "object" && !Array.isArray(it),
    ) as Record<string, unknown>[];
    if (objectRows.length === 0) continue;
    const hasNestedObjectArray = objectRows.some((row) =>
      Object.values(row).some(
        (val) =>
          Array.isArray(val) &&
          val.length > 0 &&
          val.some((it) => it && typeof it === "object" && !Array.isArray(it)),
      ),
    );
    out.push({ key: k, rows: objectRows, hasNestedObjectArray });
  }
  return out;
}

/* ── side panels for top-level nested single objects ──────────────────── */

interface SideObject {
  key: string;
  entries: { label: string; value: string }[];
}

function buildSideObjects(parsed: Record<string, unknown>): SideObject[] {
  const out: SideObject[] = [];
  for (const [k, v] of Object.entries(parsed)) {
    if (META_KEYS.has(k)) continue;
    if (!v || typeof v !== "object" || Array.isArray(v)) continue;
    const entries = flattenObjectToEntries(v as Record<string, unknown>);
    if (entries.length === 0) continue;
    out.push({ key: k, entries });
  }
  return out;
}

function flattenObjectToEntries(
  obj: Record<string, unknown>,
): { label: string; value: string }[] {
  const out: { label: string; value: string }[] = [];
  for (const [k, v] of Object.entries(obj)) {
    if (isScalar(v)) {
      out.push({ label: k, value: String(v) });
    } else if (Array.isArray(v)) {
      if (v.length === 0) {
        out.push({ label: k, value: "—" });
      } else if (v.every((it) => it == null || typeof it !== "object")) {
        out.push({ label: k, value: formatPrimitiveArray(v) });
      } else {
        out.push({ label: k, value: `${v.length} items` });
      }
    }
  }
  return out;
}

function SidePanel({ title, entries }: { title: string; entries: { label: string; value: string }[] }) {
  return (
    <details className="rounded border border-border/50 bg-neutral-bg2/40 open:bg-neutral-bg2/60" open>
      <summary className="cursor-pointer select-none px-2 py-1 text-xs font-semibold text-text-secondary">
        {title}
        <span className="ml-1 text-text-muted font-normal">· {entries.length}</span>
      </summary>
      <div className="border-t border-border/30 px-2 py-1 flex flex-wrap gap-x-3 gap-y-1 text-xs">
        {entries.map((e, i) => (
          <span key={i} className="text-text-muted">
            <span className="text-text-secondary font-semibold">{e.label}:</span>{" "}
            <span className="font-mono">{e.value}</span>
          </span>
        ))}
      </div>
    </details>
  );
}

/* ── inputs side panel (common_mode_devices) ──────────────────────────── */

function buildInputsSection(inputs: unknown): ReactElement | null {
  if (!Array.isArray(inputs) || inputs.length === 0) return null;
  const rows = inputs.filter(
    (it) => it && typeof it === "object" && !Array.isArray(it),
  ) as Record<string, unknown>[];
  if (rows.length === 0) return null;
  const headers = uniqueKeys(rows);
  const tableRows = rows.map((r) => headers.map((h) => preFormatCell(r[h])));
  return (
    <details className="rounded border border-border/50 bg-neutral-bg2/40 open:bg-neutral-bg2/60" open>
      <summary className="cursor-pointer select-none px-2 py-1 text-xs font-semibold text-text-secondary">
        inputs<span className="ml-1 text-text-muted font-normal">· {rows.length}</span>
      </summary>
      <div className="border-t border-border/30 p-1">
        <ResultTable headers={headers} rows={tableRows} previewRows={5} maxHeightClass="max-h-48" />
      </div>
    </details>
  );
}

/* ── list section renderer ────────────────────────────────────────────── */

function ListSectionRenderer({
  section,
  prominent,
}: {
  section: ListSection;
  prominent: string[] | undefined;
}) {
  if (!section.hasNestedObjectArray) {
    /* Simple table — pre-format complex cells so ResultTable's formatCell
       does not fall through to truncated JSON. */
    const headers = uniqueKeys(section.rows);
    const rows = section.rows.map((r) => headers.map((h) => preFormatCell(r[h])));
    return (
      <details className="rounded border border-border/50 bg-neutral-bg2/40 open:bg-neutral-bg2/60" open>
        <summary className="cursor-pointer select-none px-2 py-1 text-xs font-semibold text-text-secondary">
          {section.key}
          <span className="ml-1 text-text-muted font-normal">· {section.rows.length}</span>
        </summary>
        <div className="border-t border-border/30 p-1">
          <ResultTable
            headers={headers}
            rows={rows}
            previewRows={5}
            prominentColumns={prominent}
            maxHeightClass="max-h-64"
          />
        </div>
      </details>
    );
  }

  /* Card list — at least one parent row carries a nested array-of-objects. */
  return (
    <details className="rounded border border-border/50 bg-neutral-bg2/40 open:bg-neutral-bg2/60" open>
      <summary className="cursor-pointer select-none px-2 py-1 text-xs font-semibold text-text-secondary">
        {section.key}
        <span className="ml-1 text-text-muted font-normal">· {section.rows.length}</span>
      </summary>
      <div className="border-t border-border/30 p-1 flex flex-col gap-2">
        {section.rows.map((row, i) => (
          <RowCard key={i} row={row} prominent={prominent} />
        ))}
      </div>
    </details>
  );
}

function RowCard({
  row,
  prominent,
}: {
  row: Record<string, unknown>;
  prominent: string[] | undefined;
}) {
  /* Split the row's keys into (scalar/primitive-summary) chips vs
     (array-of-objects) sub-tables. */
  const chipEntries: { label: string; value: string }[] = [];
  const subTables: { key: string; rows: Record<string, unknown>[] }[] = [];
  for (const [k, v] of Object.entries(row)) {
    if (Array.isArray(v) && v.length > 0 && v.some((it) => it && typeof it === "object" && !Array.isArray(it))) {
      const objRows = v.filter(
        (it) => it && typeof it === "object" && !Array.isArray(it),
      ) as Record<string, unknown>[];
      subTables.push({ key: k, rows: objRows });
    } else if (isScalar(v)) {
      const s = String(v);
      if (s.length > 0) chipEntries.push({ label: k, value: s });
    } else if (Array.isArray(v) && v.length > 0) {
      chipEntries.push({ label: k, value: formatPrimitiveArray(v) });
    } else if (v && typeof v === "object") {
      const inner = flattenObjectToEntries(v as Record<string, unknown>);
      if (inner.length > 0) {
        chipEntries.push({ label: k, value: inner.map((e) => `${e.label}=${e.value}`).slice(0, 4).join(" · ") });
      }
    }
  }

  return (
    <div className="rounded border border-border/40 bg-neutral-bg3/30 p-1">
      <div className="px-1 py-0.5 flex flex-wrap gap-x-3 gap-y-1 text-xs">
        {chipEntries.map((e, i) => (
          <span key={i} className="text-text-muted">
            <span className="text-text-secondary font-semibold">{e.label}:</span>{" "}
            <span className="font-mono">{e.value}</span>
          </span>
        ))}
      </div>
      {subTables.map((t) => {
        const headers = uniqueKeys(t.rows);
        const tableRows = t.rows.map((r) => headers.map((h) => preFormatCell(r[h])));
        return (
          <details key={t.key} className="mt-1 rounded border border-border/30 bg-neutral-bg2/40" open>
            <summary className="cursor-pointer select-none px-2 py-0.5 text-label text-text-muted">
              {t.key}
              <span className="ml-1 font-normal">· {t.rows.length}</span>
            </summary>
            <div className="border-t border-border/20 p-1">
              <ResultTable
                headers={headers}
                rows={tableRows}
                previewRows={5}
                prominentColumns={prominent}
                maxHeightClass="max-h-48"
              />
            </div>
          </details>
        );
      })}
    </div>
  );
}

/* ── shared cell helpers ──────────────────────────────────────────────── */

function uniqueKeys(rows: Record<string, unknown>[]): string[] {
  const out: string[] = [];
  const seen = new Set<string>();
  for (const r of rows) {
    for (const k of Object.keys(r)) {
      if (!seen.has(k)) {
        seen.add(k);
        out.push(k);
      }
    }
  }
  return out;
}

/** Pre-format a cell value so ResultTable's `formatCell` (which falls
 * through to truncated JSON for anything non-scalar) receives a scalar
 * it can render directly.
 *
 * - array of primitives → "a, b, c +N more"
 * - empty array         → "—"
 * - array of objects    → "[N items]" (parent should have switched to
 *                        Card mode; defensive fallback)
 * - nested single obj   → "k=v · k=v +N more"
 * - everything else     → passthrough (scalar or null)
 */
function preFormatCell(v: unknown): unknown {
  if (v === null || v === undefined) return v;
  if (Array.isArray(v)) {
    if (v.length === 0) return "—";
    if (v.every((it) => it == null || (typeof it !== "object"))) {
      return formatPrimitiveArray(v);
    }
    return `[${v.length} items]`;
  }
  if (typeof v === "object") {
    const inner = flattenObjectToEntries(v as Record<string, unknown>);
    if (inner.length === 0) return "{…}";
    const head = inner.slice(0, 4).map((e) => `${e.label}=${e.value}`).join(" · ");
    return inner.length > 4 ? `${head} +${inner.length - 4} more` : head;
  }
  return v;
}

function formatPrimitiveArray(v: unknown[]): string {
  const items = v.filter((x) => x !== null && x !== undefined).map((x) => String(x));
  if (items.length === 0) return "—";
  const head = items.slice(0, 5).join(", ");
  return items.length > 5 ? `${head} +${items.length - 5} more` : head;
}

function isScalar(v: unknown): boolean {
  return v !== null && (typeof v === "string" || typeof v === "number" || typeof v === "boolean");
}
