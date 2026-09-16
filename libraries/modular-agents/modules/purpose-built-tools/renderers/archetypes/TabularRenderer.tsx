/**
 * TabularRenderer — the columnar baseline.
 *
 * Accepts both table shapes a tool layer produces: `{columns, rows}` where
 * rows are objects keyed by column name, and `{columns, data}` where columns
 * may be `{name, type}` descriptors and rows may be arrays. Supporting both
 * is not indulgence — the query backends genuinely emit both, and a renderer
 * that handled one would push the conversion into every tool.
 */

import { ToolResultCard } from "../ToolResultCard";
import { ResultTable } from "../ResultTable";
import { parseToolResult, scopeBadges } from "../helpers";
import {
  ArchetypeEmpty,
  ArchetypeUnresolved,
  renderEnvelopeState,
  type ArchetypeRendererProps,
} from "./_common";

function headerName(column: unknown): string {
  if (typeof column === "string") return column;
  if (column && typeof column === "object") {
    const named = column as { name?: string };
    if (typeof named.name === "string") return named.name;
  }
  return String(column);
}

export function TabularRenderer({ resizeKey, result, prominentColumns }: ArchetypeRendererProps) {
  const parsed = parseToolResult(result);
  if (!parsed) return <ArchetypeUnresolved archetype="tabular" result={result} />;

  const envelopeState = renderEnvelopeState(parsed);
  if (envelopeState) return envelopeState;

  const rawColumns = parsed.columns;
  const rawRows = Array.isArray(parsed.rows) ? parsed.rows : parsed.data;
  if (!Array.isArray(rawColumns) || !Array.isArray(rawRows)) {
    return <ArchetypeUnresolved archetype="tabular" result={result} />;
  }

  const headers = rawColumns.map(headerName);
  const rows = rawRows.map((row) => {
    if (Array.isArray(row)) return row;
    if (row && typeof row === "object") {
      return headers.map((header) => (row as Record<string, unknown>)[header]);
    }
    return [row];
  });

  const scope = scopeBadges(parsed);
  if (rows.length === 0) {
    return <ArchetypeEmpty label="rows" message="No rows returned" scope={scope} />;
  }

  return (
    <ToolResultCard resizeKey={resizeKey} scope={scope} signal={[{ label: "rows", value: rows.length }]}>
      <ResultTable headers={headers} rows={rows} prominentColumns={prominentColumns} />
    </ToolResultCard>
  );
}
