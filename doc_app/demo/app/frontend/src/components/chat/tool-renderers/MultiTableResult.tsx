/**
 * MultiTableResult — renders grouped tabular tool envelopes.
 *
 * Used by find_scada when one call requests several equipment filters.
 * The backend returns one KQL table per requested equipment value so the
 * operator can compare waveforms without reading one large undifferentiated
 * table or forcing the agent to make many serial tool calls.
 */

import type { ToolResultProps } from "./index";
import { getProminentColumns } from "./index";
import { JsonFallback } from "./JsonFallback";
import { ResultTable } from "./ResultTable";
import { TabularResult } from "./TabularResult";
import { ToolResultCard } from "./ToolResultCard";
import { extractError, parseToolResult } from "./helpers";

interface MultiTableEnvelope {
  kind?: string;
  scope?: Record<string, unknown>;
  summary?: Record<string, unknown>;
  tables?: Array<{
    equipment?: string;
    columns?: Array<{ name?: string } | string>;
    rows?: Array<Record<string, unknown>>;
  }>;
}

function normalizeColumns(columns: Array<{ name?: string } | string> | undefined): string[] {
  return (columns ?? []).map((column) =>
    typeof column === "string" ? column : column.name ?? String(column),
  );
}

export function MultiTableResult({ result, toolName }: ToolResultProps) {
  const parsed = parseToolResult(result) as MultiTableEnvelope | null;
  if (!parsed) return <JsonFallback result={result} />;

  const errDetail = extractError(parsed as Record<string, unknown>);
  if (errDetail) return <ToolResultCard error={{ detail: errDetail }} />;

  if (parsed.kind !== "multi_table" || !Array.isArray(parsed.tables)) {
    return <TabularResult result={result} toolName={toolName} />;
  }

  const scope = parsed.scope ?? {};
  const summary = parsed.summary ?? {};
  const station = typeof scope.station === "string" ? scope.station : undefined;
  const totalRows = typeof summary.total_rows === "number" ? summary.total_rows : 0;
  const requested = typeof summary.equipment_requested === "number" ? summary.equipment_requested : parsed.tables.length;

  return (
    <ToolResultCard
      scope={station ? [{ label: "station", value: station }] : undefined}
      signal={[
        { label: "equipment", value: requested },
        { label: "rows", value: totalRows },
      ]}
    >
      <div className="flex flex-col gap-3">
        {parsed.tables.map((table, index) => {
          const headers = normalizeColumns(table.columns);
          const rows = (table.rows ?? []).map((row) => headers.map((header) => row[header]));
          const equipment = table.equipment || `equipment ${index + 1}`;
          return (
            <section key={`${equipment}-${index}`} className="rounded border border-border bg-neutral-bg2/40 p-2">
              <div className="mb-2 flex flex-wrap items-center gap-1.5 text-label">
                <span className="rounded bg-neutral-bg3 px-1.5 py-0.5 font-mono text-text-secondary">
                  <span className="text-text-muted">equipment:</span> {equipment}
                </span>
                <span className="rounded bg-accent/10 px-1.5 py-0.5 font-mono text-accent">
                  rows: {rows.length}
                </span>
              </div>
              {rows.length > 0 ? (
                <ResultTable
                  headers={headers}
                  rows={rows}
                  prominentColumns={getProminentColumns(toolName)}
                  previewRows={5}
                  maxHeightClass="max-h-56"
                />
              ) : (
                <div className="py-1 text-xs italic text-text-muted">No rows returned</div>
              )}
            </section>
          );
        })}
      </div>
    </ToolResultCard>
  );
}
