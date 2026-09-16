/**
 * TabularResult — renders columnar tool results inside the ToolResultCard
 * scaffold, using the shared ResultTable primitive.
 *
 * Handles two shapes:
 *   - Fabric GQL / NetworkX: `{columns: string[], data: any[][] | object[]}`
 *   - KQL telemetry:          `{columns: {name, type}[], rows: object[]}`
 *
 * Signal band: row count chip. Body: ResultTable with `previewRows=5`
 * and per-tool `prominentColumns` hint (see index.ts).
 */

import type { ToolResultProps } from "./index";
import { getProminentColumns } from "./index";
import { JsonFallback } from "./JsonFallback";
import { ToolResultCard } from "./ToolResultCard";
import { ResultTable } from "./ResultTable";
import { extractError, parseToolResult } from "./helpers";

export function TabularResult({ result, toolName }: ToolResultProps) {
  const parsed = parseToolResult(result);
  if (!parsed) return <JsonFallback result={result} />;

  /* Typed-error envelope short-circuit (R3). */
  const errDetail = extractError(parsed);
  if (errDetail) {
    return <ToolResultCard error={{ detail: errDetail }} />;
  }

  /* Detect shape and normalize to headers + rows. */
  let headers: string[];
  let rows: unknown[][];

  if (Array.isArray(parsed.columns) && Array.isArray(parsed.data)) {
    headers = (parsed.columns as unknown[]).map((c) =>
      typeof c === "string" ? c : (c as { name?: string }).name ?? String(c),
    );
    rows = (parsed.data as unknown[]).map((row) => {
      if (Array.isArray(row)) return row;
      if (row && typeof row === "object") {
        return headers.map((h) => (row as Record<string, unknown>)[h]);
      }
      return [row];
    });
  } else if (Array.isArray(parsed.columns) && Array.isArray(parsed.rows)) {
    headers = (parsed.columns as { name: string }[]).map((c) => c.name);
    rows = (parsed.rows as Record<string, unknown>[]).map((row) =>
      headers.map((h) => row[h]),
    );
  } else {
    return <JsonFallback result={result} />;
  }

  if (rows.length === 0) {
    return (
      <ToolResultCard signal={[{ label: "rows", value: 0, tone: "neutral" }]}>
        <div className="text-xs text-text-muted italic py-1">No rows returned</div>
      </ToolResultCard>
    );
  }

  return (
    <ToolResultCard signal={[{ label: "rows", value: rows.length }]}>
      <ResultTable
        headers={headers}
        rows={rows}
        prominentColumns={getProminentColumns(toolName)}
      />
    </ToolResultCard>
  );
}
