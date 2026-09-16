import { useState } from "react";
import {
  cellText,
  columnsOf,
  nextSort,
  sortAriaValue,
  sortRows,
  truncateCell,
  type SortState,
} from "./rows.js";

/**
 * A bounded row sample as a sortable table.
 *
 * ADAPTED from `resource_explorer/frontend/src/components/content/RowsTable.tsx`.
 * See PROVENANCE.md. Tailwind classes become scoped ones, and the caption is
 * new: a sample must say what it is a sample *of*, or a reader takes 25 rows
 * for the whole table. The notes list is new for the same reason: a bound that
 * shortened a cell or stopped at a byte budget has to be legible, or the copy
 * in someone's clipboard is silently not what the source holds.
 *
 * Every cell renders as text. Nothing here is HTML, a link or a fetch: a row
 * out of a telemetry table can hold anything, and it is evidence to read, not
 * markup to run.
 *
 * Sorting is client-side over the rows already returned. It never re-queries,
 * so it can never quietly widen the bound the server applied.
 */

export interface RowsTableProps {
  rows: Record<string, unknown>[];
  columns: string[] | null;
  rowLimit: number;
  sampleOf: number | null;
  truncated: boolean;
  /** What a bound cut from this sample. Rendered; never summarised away. */
  notes: string[];
  caption: string;
}

export function RowsTable({
  rows,
  columns,
  rowLimit,
  sampleOf,
  truncated,
  notes,
  caption,
}: RowsTableProps) {
  const [sort, setSort] = useState<SortState | null>(null);
  const headers = columnsOf(rows, columns);
  const ordered = sortRows(rows, sort);

  const scale =
    sampleOf !== null
      ? `${rows.length.toLocaleString("en")} of ${sampleOf.toLocaleString("en")}`
      : truncated
        ? `${rows.length.toLocaleString("en")} shown, more exist`
        : `${rows.length.toLocaleString("en")} shown`;

  return (
    <div className="inv-rows">
      <p className="inv-rows-scale">
        <b>{scale}</b>
        <span>
          {" "}
          · sample limit {rowLimit.toLocaleString("en")} row
          {rowLimit === 1 ? "" : "s"}
          {truncated ? " · truncated" : ""}
        </span>
      </p>
      {notes.length > 0 ? (
        <ul className="inv-rows-notes" aria-label="What this sample leaves out">
          {notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      ) : null}
      <div className="inv-rows-scroll">
        <table>
          <caption className="inv-visually-hidden">{caption}</caption>
          <thead>
            <tr>
              {headers.map((column) => (
                <th
                  key={column}
                  scope="col"
                  aria-sort={sortAriaValue(sort, column)}
                >
                  <button
                    type="button"
                    onClick={() => setSort((current) => nextSort(current, column))}
                  >
                    {column}
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {ordered.map((row, index) => (
              <tr key={index}>
                {headers.map((column) => {
                  const { text, truncated: cut } = truncateCell(cellText(row[column]));
                  return (
                    <td key={column} title={cut ? text : undefined}>
                      {text}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
