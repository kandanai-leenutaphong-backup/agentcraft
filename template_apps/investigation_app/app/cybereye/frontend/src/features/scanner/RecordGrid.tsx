import type { ReactNode } from "react";
import { ChevronDown } from "lucide-react";

export interface GridColumn {
  key: string;
  label: string;
  align?: "left" | "right";
  /** Numeric columns get tabular figures so magnitudes compare down the column. */
  numeric?: boolean;
  width?: string;
}

export interface GridRow {
  id: string;
  tone?: string;
  cells: Record<string, ReactNode>;
  detail?: ReactNode;
}

interface Props {
  columns: GridColumn[];
  rows: GridRow[];
  openIds?: Set<string>;
  onToggle?: (id: string) => void;
  caption?: string;
  className?: string;
  empty?: ReactNode;
}

/**
 * One aligned record grid for factors, rule runs, and tool inputs alike. Column headings are
 * emitted once instead of repeating a label on every row.
 */
export function RecordGrid({ columns, rows, openIds, onToggle, caption, className = "", empty }: Props) {
  const expandable = Boolean(onToggle);
  const template = `${expandable ? "14px " : ""}${columns.map((column) => column.width ?? "minmax(0,1fr)").join(" ")}`;

  if (!rows.length && empty) return <div className={`rgrid-empty ${className}`}>{empty}</div>;

  return (
    <div className={`rgrid ${className}`} role="table" aria-label={caption}>
      <div className="rgrid-head" role="row" style={{ gridTemplateColumns: template }}>
        {expandable && <span aria-hidden="true" />}
        {columns.map((column) => (
          <span key={column.key} role="columnheader" className={column.align === "right" ? "right" : ""}>{column.label}</span>
        ))}
      </div>
      {rows.map((row) => {
        const open = openIds?.has(row.id) ?? false;
        return (
          <div key={row.id} className={`rgrid-record ${row.tone ?? ""} ${open ? "open" : ""}`}>
            {expandable ? (
              <button
                type="button" role="row" className="rgrid-row" style={{ gridTemplateColumns: template }}
                aria-expanded={open} onClick={() => onToggle?.(row.id)}
              >
                <ChevronDown size={11} className={open ? "" : "closed"} />
                {columns.map((column) => (
                  <span
                    key={column.key} role="cell"
                    className={`${column.align === "right" ? "right" : ""} ${column.numeric ? "numeric" : ""}`}
                  >{row.cells[column.key]}</span>
                ))}
              </button>
            ) : (
              <div role="row" className="rgrid-row static" style={{ gridTemplateColumns: template }}>
                {columns.map((column) => (
                  <span
                    key={column.key} role="cell"
                    className={`${column.align === "right" ? "right" : ""} ${column.numeric ? "numeric" : ""}`}
                  >{row.cells[column.key]}</span>
                ))}
              </div>
            )}
            {open && row.detail && <div className="rgrid-detail">{row.detail}</div>}
          </div>
        );
      })}
    </div>
  );
}
