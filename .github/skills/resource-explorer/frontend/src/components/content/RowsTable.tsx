/**
 * A real table for a row sample: sortable columns, a stated row count, and a
 * per-row JSON view for the documents that are not flat.
 *
 * A Cosmos document has nested objects in it. Flattening one to `[object
 * Object]` loses the thing the reader opened it to see, so a cell shows the
 * JSON and the row opens to the whole document.
 */

import { useMemo, useState, type JSX } from "react";

import {
  cellText,
  columnsOf,
  nextSort,
  sortAriaValue,
  sortRows,
  truncateCell,
  type SortState,
} from "../../api/rows";
import { formatCount } from "../../api/format";

export interface RowsTableProps {
  rows: Record<string, unknown>[];
  columns: string[] | null;
  caption: string;
}

export function RowsTable({ rows, columns, caption }: RowsTableProps): JSX.Element {
  const [sort, setSort] = useState<SortState | null>(null);
  const [openRow, setOpenRow] = useState<number | null>(null);
  const headers = useMemo(() => columnsOf(rows, columns), [rows, columns]);
  const ordered = useMemo(() => sortRows(rows, sort), [rows, sort]);

  if (rows.length === 0) {
    return (
      <p data-testid="rows-empty" className="text-sm text-secondary">
        The sample returned no rows.
      </p>
    );
  }

  return (
    <div className="min-w-0">
      <p className="mb-2 text-xs text-muted">
        {formatCount(rows.length, "row")} · {formatCount(headers.length, "column")} ·
        select a column header to sort, or a row to see the whole document
      </p>
      <div className="max-w-full overflow-x-auto rounded border border-border">
        <table data-testid="rows-table" className="w-full border-collapse text-left">
          <caption className="sr-only">{caption}</caption>
          <thead>
            <tr className="bg-surface2">
              {headers.map((header) => (
                <th
                  key={header}
                  scope="col"
                  aria-sort={sortAriaValue(sort, header)}
                  className="whitespace-nowrap border-b border-border p-0"
                >
                  <button
                    type="button"
                    data-testid="rows-sort"
                    data-column={header}
                    onClick={() => setSort((current) => nextSort(current, header))}
                    className="flex min-h-[44px] w-full items-center gap-1 px-3 text-left font-mono text-[12px] font-semibold text-secondary"
                  >
                    <span className="truncate">{header}</span>
                    <span aria-hidden="true" className="text-muted">
                      {sort?.column === header
                        ? sort.direction === "asc"
                          ? "▲"
                          : "▼"
                        : "↕"}
                    </span>
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {ordered.map((row, index) => {
              const expanded = openRow === index;
              return (
                <RowPair
                  key={index}
                  row={row}
                  headers={headers}
                  index={index}
                  expanded={expanded}
                  onToggle={() => setOpenRow(expanded ? null : index)}
                />
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

interface RowPairProps {
  row: Record<string, unknown>;
  headers: string[];
  index: number;
  expanded: boolean;
  onToggle: () => void;
}

function RowPair({ row, headers, index, expanded, onToggle }: RowPairProps): JSX.Element {
  return (
    <>
      <tr
        data-testid="rows-row"
        onClick={onToggle}
        className={`cursor-pointer border-b border-border-soft align-top ${
          expanded ? "bg-flow-tint" : "hover:bg-canvas2"
        }`}
      >
        {headers.map((header, cell) => {
          const raw = cellText(row[header]);
          const { text, truncated } = truncateCell(raw);
          return (
            <td
              key={header}
              className="max-w-[22rem] px-3 py-2 font-mono text-[12.5px] text-primary"
            >
              {cell === 0 ? (
                <span className="mr-1 text-muted" aria-hidden="true">
                  {expanded ? "▾" : "▸"}
                </span>
              ) : null}
              {/* Clamped, not cut: one long value must not make every row tall.
                  The whole value is in the row's own JSON, one click away. */}
              <span
                className="line-clamp-3 break-words align-top"
                title={truncated ? raw : undefined}
              >
                {text}
              </span>
            </td>
          );
        })}
      </tr>
      {expanded ? (
        <tr className="border-b border-border-soft">
          <td colSpan={headers.length} className="bg-surface px-3 py-2">
            <pre
              data-testid="rows-row-json"
              className="max-h-80 overflow-auto whitespace-pre-wrap break-words font-mono text-[12px] leading-5 text-primary"
            >
              {JSON.stringify(row, null, 2)}
            </pre>
            <button
              type="button"
              onClick={onToggle}
              className="mt-2 min-h-[44px] rounded border border-border px-3 text-sm text-primary"
            >
              Close row {index + 1}
            </button>
          </td>
        </tr>
      ) : null}
    </>
  );
}
