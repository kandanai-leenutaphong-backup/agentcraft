import { text } from "./envelope";

interface Props {
  columns: string[];
  rows: unknown[][];
  rowCount: number;
  maxRows: number | null;
  truncated: boolean;
  maxVisibleRows?: number;
  maxVisibleColumns?: number;
}

export function BoundedTable({
  columns, rows, rowCount, maxRows, truncated, maxVisibleRows = 12, maxVisibleColumns = 8,
}: Props) {
  const shownColumns = columns.slice(0, maxVisibleColumns);
  const shownRows = rows.slice(0, maxVisibleRows);
  const hiddenColumns = columns.length - shownColumns.length;
  const hiddenRows = rowCount - shownRows.length;

  return (
    <div className="trender-table">
      <div className="trender-table-scroll" tabIndex={0} role="group" aria-label="Bounded result rows, horizontally scrollable">
        <table>
          <thead>
            <tr>{shownColumns.map((column) => <th key={column} scope="col">{column}</th>)}</tr>
          </thead>
          <tbody>
            {shownRows.map((row, index) => (
              <tr key={index}>
                {shownColumns.map((column, cell) => (
                  <td key={column} title={text(row[cell])}>{text(row[cell])}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="trender-cap">
        Showing {shownRows.length} of {rowCount} returned row{rowCount === 1 ? "" : "s"}
        {hiddenRows > 0 ? ` · ${hiddenRows} more not rendered` : ""}
        {hiddenColumns > 0 ? ` · ${hiddenColumns} more column${hiddenColumns === 1 ? "" : "s"} not rendered` : ""}
        {maxRows !== null ? ` · query row cap ${maxRows}` : ""}
        {truncated ? " · result hit the row cap and is truncated" : ""}
      </p>
    </div>
  );
}
