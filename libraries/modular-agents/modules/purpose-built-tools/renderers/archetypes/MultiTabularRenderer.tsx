/**
 * MultiTabularRenderer — several named tables in one result.
 *
 * A tool that answers "give me the ratings, the outages and the schedule for
 * this asset" returns three tables, not one. Flattening them into a single
 * table loses which rows belong to which question; rendering only the first
 * loses the rest silently.
 *
 * Shape: `{tables: [{title?, headers?|columns?, rows}], scope?}`. A single
 * table in that envelope is legal and renders as one section — the tool should
 * not have to switch archetypes when a result happens to have one part.
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

interface NamedTable {
  title?: string;
  headers?: string[];
  columns?: string[];
  rows?: unknown[][];
}

const isObject = (value: unknown): value is Record<string, unknown> =>
  !!value && typeof value === "object" && !Array.isArray(value);

/** Column headers, however the tool spelled them, or positional fallbacks. */
function headersOf(table: NamedTable): string[] {
  if (Array.isArray(table.headers)) return table.headers.map(String);
  if (Array.isArray(table.columns)) return table.columns.map(String);
  const width = Math.max(0, ...(table.rows ?? []).map((row) => (Array.isArray(row) ? row.length : 0)));
  return Array.from({ length: width }, (_, index) => `col ${index + 1}`);
}

export function MultiTabularRenderer({ resizeKey, result, prominentColumns }: ArchetypeRendererProps) {
  const parsed = parseToolResult<Record<string, unknown>>(result);
  if (!isObject(parsed)) return <ArchetypeUnresolved archetype="multi-tabular" result={result} />;

  const envelopeState = renderEnvelopeState(parsed);
  if (envelopeState) return envelopeState;

  const raw = parsed.tables;
  if (!Array.isArray(raw)) return <ArchetypeUnresolved archetype="multi-tabular" result={result} />;

  const tables = raw.filter(isObject) as NamedTable[];
  const scope = scopeBadges(parsed);
  const total = tables.reduce((sum, table) => sum + (table.rows?.length ?? 0), 0);

  if (tables.length === 0 || total === 0) {
    return <ArchetypeEmpty label="rows" message="No rows in any table" scope={scope} />;
  }

  return (
    <ToolResultCard
      resizeKey={resizeKey}
      scope={scope}
      signal={[
        { label: "tables", value: tables.length },
        { label: "rows", value: total, tone: "neutral" },
      ]}
    >
      <div data-testid="multi-tabular" className="space-y-2">
        {tables.map((table, index) => {
          const rows = Array.isArray(table.rows) ? table.rows : [];
          return (
            <section key={index}>
              {/* An untitled section still gets a heading: "table 2" tells the
                  reader there is more than one, which position alone does not. */}
              <div className="mb-0.5 text-micro font-semibold uppercase tracking-wide text-text-muted">
                {table.title || `table ${index + 1}`}
                <span className="ml-1 font-normal normal-case">({rows.length})</span>
              </div>
              {rows.length > 0 ? (
                <ResultTable
                  headers={headersOf(table)}
                  rows={rows}
                  prominentColumns={prominentColumns}
                />
              ) : (
                <div className="py-1 text-xs italic text-text-muted">No rows</div>
              )}
            </section>
          );
        })}
      </div>
    </ToolResultCard>
  );
}
