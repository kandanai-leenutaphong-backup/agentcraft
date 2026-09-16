import { useEffect, useRef, type KeyboardEvent } from "react";
import { ChevronDown, ChevronRight, Database } from "lucide-react";
import { HANDLED_KEYS, keyboardMove } from "./keyboard";
import { effectiveActiveId, type Row } from "./state";
import { StatusBadge } from "./StatusNote";
import { LOADING_LABEL, showsStatusBadge } from "./status";

/**
 * The tree, as `role="tree"` over the flattened visible rows.
 *
 * ADAPTED from `resource_explorer/frontend/src/components/TreeView.tsx`. See
 * PROVENANCE.md. Tailwind classes become scoped ones, the estate icon set is
 * dropped, and each source row gains a switch. The ARIA contract is unchanged:
 * exactly one row is tabbable, `aria-level`/`aria-posinset`/`aria-setsize` come
 * from the same projection the renderer uses, and every move is the WAI-ARIA
 * tree pattern.
 */

export interface TreeViewProps {
  rows: Row[];
  activeId: string | null;
  selectedId: string | null;
  onFocus: (id: string) => void;
  onOpen: (id: string, open: boolean) => void;
  onSelect: (id: string) => void;
  onToggleSource: (id: string) => void;
  label: string;
  highlightedSourceIds?: readonly string[];
}

export function TreeView({
  rows,
  activeId,
  selectedId,
  onFocus,
  onOpen,
  onSelect,
  onToggleSource,
  label,
  highlightedSourceIds = [],
}: TreeViewProps) {
  const active = effectiveActiveId(rows, activeId);
  const container = useRef<HTMLDivElement>(null);
  const shouldRefocus = useRef(false);
  const rowById = new Map(rows.map((row) => [row.node.id, row]));

  useEffect(() => {
    if (!shouldRefocus.current || active === null) return;
    shouldRefocus.current = false;
    const node = container.current?.querySelector<HTMLElement>(
      `[data-node-id="${CSS.escape(active)}"]`,
    );
    node?.focus();
  }, [active, rows]);

  function handleKey(event: KeyboardEvent<HTMLDivElement>) {
    if (!(HANDLED_KEYS as readonly string[]).includes(event.key)) return;
    const origin = event.target as HTMLElement | null;
    const onRow = origin?.getAttribute("role") === "treeitem";
    // Enter and Space belong to whichever control has focus. Handling them here
    // stopped a focused switch from toggling at all: preventDefault cancelled the
    // native activation and the row stole the focus. Navigation keys still reach
    // the tree from inside a row, because no control in one uses them.
    if (!onRow && (event.key === "Enter" || event.key === " ")) return;
    const move = keyboardMove(rows, active, event.key);
    if (move === null) return;
    event.preventDefault();
    shouldRefocus.current = true;
    switch (move.kind) {
      case "focus":
        onFocus(move.id);
        return;
      case "open":
        onOpen(move.id, true);
        onFocus(move.id);
        return;
      case "close":
        onOpen(move.id, false);
        onFocus(move.id);
        return;
      case "toggleSource":
        onToggleSource(move.id);
        return;
      case "activate":
        onSelect(move.id);
        onFocus(move.id);
    }
  }

  return (
    <div
      className="inv-tree"
      role="tree"
      aria-label={label}
      ref={container}
      onKeyDown={handleKey}
    >
      {rows.map((row) => {
        const { node } = row;
        const isSource = node.kind === "source";
        const dependency = isSource && highlightedSourceIds.includes(node.sourceId ?? "");
        const isActive = node.id === active;
        // Two use cases can declare a slot with the same label. The row keeps the
        // label it renders and the accessible name carries the owner, so the two
        // "Retrieval index" rows are distinguishable to a reader who cannot see
        // which branch they sit under.
        const parent = row.parentId === null ? undefined : rowById.get(row.parentId);
        const owner = parent?.node.kind === "use_case" ? parent.node.label : "";
        const qualified = isSource && owner ? `${node.label}, ${owner}` : node.label;
        return (
          <div
            key={node.id}
            role="treeitem"
            aria-level={row.level}
            aria-posinset={row.posinset}
            aria-setsize={row.setsize}
            aria-expanded={node.expandable ? row.expanded : undefined}
            aria-selected={node.id === selectedId}
            aria-label={
              isSource
                ? `${qualified}, ${node.enabled === false ? "disabled" : "enabled"}${dependency ? ", used by selected tool" : ""}`
                : node.label
            }
            data-node-id={node.id}
            data-kind={node.kind}
            data-source-id={node.sourceId || undefined}
            data-enabled={isSource ? String(node.enabled !== false) : undefined}
            data-tool-dependency={dependency ? "true" : undefined}
            className={`inv-row inv-row-${node.kind}${node.id === selectedId ? " selected" : ""}${
              isSource && node.enabled === false ? " disabled" : ""
            }${dependency ? " inv-tool-dependency" : ""}`}
            style={{ paddingLeft: `${8 + (row.level - 1) * 16}px` }}
            tabIndex={isActive ? 0 : -1}
            onFocus={() => onFocus(node.id)}
          >
            {node.expandable ? (
              <button
                type="button"
                className="inv-twisty"
                aria-label={`${row.expanded ? "Collapse" : "Expand"} ${node.label}`}
                aria-expanded={row.expanded}
                onClick={() => {
                  onOpen(node.id, !row.expanded);
                  onFocus(node.id);
                }}
              >
                {row.expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
              </button>
            ) : (
              <span className="inv-twisty inv-twisty-leaf" aria-hidden="true">
                <Database size={14} />
              </span>
            )}

            <button
              type="button"
              className="inv-row-label"
              onClick={() => {
                onSelect(node.id);
                onFocus(node.id);
              }}
            >
              <b>{node.label}</b>
              {dependency && <span className="inv-tag inv-dependency-tag">Tool dependency</span>}
              {node.tags.map((tag) => (
                <span key={tag} className="inv-tag">
                  {tag}
                </span>
              ))}
              {row.loading ? <span className="inv-loading">{LOADING_LABEL}</span> : null}
              {showsStatusBadge(node.status) ? <StatusBadge status={node.status} /> : null}
            </button>

            {isSource ? (
              <label className="inv-switch">
                <input
                  type="checkbox"
                  checked={node.enabled !== false}
                  onChange={() => onToggleSource(node.id)}
                  onKeyDown={(event) => {
                    // Space is native on a checkbox; Enter is not, and a reader who
                    // has just tabbed to it expects both to work.
                    if (event.key !== "Enter") return;
                    event.preventDefault();
                    onToggleSource(node.id);
                  }}
                  aria-label={`Use ${qualified} in this session`}
                />
                <span aria-hidden="true">{node.enabled === false ? "off" : "on"}</span>
              </label>
            ) : null}
          </div>
        );
      })}
      {rows.length === 0 ? <p className="inv-empty">{LOADING_LABEL}</p> : null}
    </div>
  );
}
