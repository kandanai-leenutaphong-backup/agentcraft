/**
 * ResultTable — the scrollable table every tabular result renders through.
 *
 * Two behaviours that only matter once results reach real size, and that a
 * hand-rolled `<table>` never has:
 *
 * **A preview cap.** A thirty-row result pushes the conversation off screen,
 * and the operator scrolls past it to find the next message. Five rows plus
 * "show all (25 more)" keeps the transcript readable and the data one click
 * away.
 *
 * **Prominent columns.** A tool returning twelve columns has two the reader
 * needs and ten that are provenance. Naming the salient ones hides the rest
 * behind a "show metadata" toggle so the eye lands on the signal. With no
 * hint every column shows, which is the right default for a tool nobody has
 * tuned yet.
 */

import { useState } from "react";
import { useCardBody } from "./ToolResultCard";
import { formatCell } from "./helpers";

export interface ResultTableProps {
  headers: string[];
  rows: unknown[][];
  /** Rows shown collapsed. Pass `rows.length` to disable the cap. */
  previewRows?: number;
  /** Columns treated as the signal; the rest hide behind a toggle. */
  prominentColumns?: string[];
  maxHeightClass?: string;
}

const DEFAULT_PREVIEW = 5;

export function ResultTable({
  headers,
  rows,
  previewRows = DEFAULT_PREVIEW,
  prominentColumns,
  maxHeightClass = "max-h-64",
}: ResultTableProps) {
  const { resizable } = useCardBody();
  const [showAll, setShowAll] = useState(false);
  const hasProminentHint = !!prominentColumns && prominentColumns.length > 0;
  // Metadata starts hidden only when the caller actually named the signal
  // columns; otherwise hiding would remove the whole table.
  const [showMetadata, setShowMetadata] = useState(!hasProminentHint);

  const prominent = new Set(prominentColumns ?? []);
  const visibleColumns = headers
    .map((header, index) => ({ header, index }))
    .filter(({ header }) => showMetadata || !hasProminentHint || prominent.has(header));
  const hiddenColumnCount = headers.length - visibleColumns.length;

  const limit = showAll ? rows.length : Math.min(previewRows, rows.length);
  const visibleRows = rows.slice(0, limit);
  const hiddenRowCount = rows.length - limit;

  return (
    <div className="flex flex-col gap-1">
      {hasProminentHint && (
        <div className="flex items-center justify-end gap-2 text-label text-text-muted">
          {hiddenColumnCount > 0 && !showMetadata && (
            <button
              type="button"
              onClick={() => setShowMetadata(true)}
              className="transition-colors hover:text-text-secondary"
            >
              show metadata ({hiddenColumnCount})
            </button>
          )}
          {showMetadata && (
            <button
              type="button"
              onClick={() => setShowMetadata(false)}
              className="transition-colors hover:text-text-secondary"
            >
              hide metadata
            </button>
          )}
        </div>
      )}

      <div
        // Inside a resizable card the card owns the height; keeping the cap
        // here would make dragging reveal blank space instead of rows.
        className={`overflow-x-auto rounded-lg border border-border overflow-y-auto ${
          resizable ? "flex-1 min-h-0" : maxHeightClass
        }`}
      >
        <table className="w-full border-collapse text-xs">
          <thead className="sticky top-0 bg-neutral-bg3 text-label uppercase tracking-wider text-text-muted">
            <tr>
              {visibleColumns.map(({ header, index }) => (
                <th
                  key={index}
                  className="whitespace-nowrap border-b border-border px-3 py-2 text-left font-semibold"
                >
                  {header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {visibleRows.map((row, rowIndex) => (
              <tr
                key={rowIndex}
                className="transition-colors even:bg-neutral-bg2/30 hover:bg-neutral-bg3/50"
              >
                {visibleColumns.map(({ header, index }) => {
                  const isProminent = !hasProminentHint || prominent.has(header);
                  return (
                    <td
                      key={index}
                      className={`whitespace-nowrap border-b border-border/30 px-3 py-1.5 font-mono ${
                        isProminent ? "text-text-secondary" : "text-text-muted"
                      }`}
                    >
                      {formatCell(row[index])}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {hiddenRowCount > 0 && (
        <button
          type="button"
          onClick={() => setShowAll(true)}
          className="self-start text-label text-text-muted transition-colors hover:text-text-secondary"
        >
          show all ({hiddenRowCount} more)
        </button>
      )}
      {showAll && rows.length > previewRows && (
        <button
          type="button"
          onClick={() => setShowAll(false)}
          className="self-start text-label text-text-muted transition-colors hover:text-text-secondary"
        >
          collapse
        </button>
      )}
    </div>
  );
}
