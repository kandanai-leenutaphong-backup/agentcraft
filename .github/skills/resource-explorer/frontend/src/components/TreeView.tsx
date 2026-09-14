/**
 * The tree. A flat list of `treeitem` rows in one `tree` container, each
 * carrying its own `aria-level`/`aria-posinset`, which is what lets a lazily
 * loaded branch appear without restructuring the DOM around it.
 *
 * A branch that did not answer keeps its row and gains a diagnosis inside it.
 * No expand-all: the point of a lazy tree is that opening a branch is a
 * decision the reader makes one level at a time, and 213 resources across 20
 * groups is real latency.
 */

import { useEffect, useRef, type JSX, type KeyboardEvent, type MouseEvent } from "react";

import { KIND_ICON, KIND_LABEL } from "../api/kinds";
import { keyboardMove } from "../api/keyboard";
import { childCountText } from "../api/format";
import { answered, LOADING_LABEL, statusLabel } from "../api/status";
import { effectiveActiveId, findRow, type Row } from "../api/state";
import { Icon } from "./Icon";
import { Badge, StatusBadge, StatusNote } from "./StatusNote";

const INDENT_STEP = 13;
const MAX_INDENT = 104;

export interface TreeViewProps {
  rows: Row[];
  activeId: string | null;
  selectedId: string | null;
  loadingRoot: boolean;
  rootFailure: string | null;
  onFocusRow: (id: string) => void;
  onToggle: (id: string, open: boolean) => void;
  onSelect: (id: string) => void;
  onRetry: (id: string) => void;
  onSearchShortcut: () => void;
}

export function TreeView(props: TreeViewProps): JSX.Element {
  const {
    rows,
    selectedId,
    loadingRoot,
    rootFailure,
    onFocusRow,
    onToggle,
    onSelect,
    onRetry,
    onSearchShortcut,
  } = props;
  const containerRef = useRef<HTMLDivElement>(null);
  const activeId = effectiveActiveId(rows, props.activeId);

  useEffect(() => {
    const container = containerRef.current;
    if (container === null || activeId === null) return;
    if (!container.contains(document.activeElement)) return;
    const target = container.querySelector<HTMLElement>(
      `[data-node-id="${CSS.escape(activeId)}"]`,
    );
    if (target !== null && target !== document.activeElement) target.focus();
  }, [activeId]);

  // A revealed search hit is often below the fold; scrolling to it is the
  // difference between "opened" and "found".
  useEffect(() => {
    const container = containerRef.current;
    if (container === null || selectedId === null) return;
    const target = container.querySelector<HTMLElement>(
      `[data-node-id="${CSS.escape(selectedId)}"]`,
    );
    target?.scrollIntoView({ block: "nearest" });
  }, [selectedId, rows.length]);

  function handleKeyDown(event: KeyboardEvent<HTMLDivElement>): void {
    const move = keyboardMove(rows, activeId, event.key);
    if (move === null) return;
    event.preventDefault();
    switch (move.kind) {
      case "search":
        onSearchShortcut();
        return;
      case "focus":
        onFocusRow(move.id);
        return;
      case "open":
        onToggle(move.id, true);
        onFocusRow(move.id);
        return;
      case "close":
        onToggle(move.id, false);
        onFocusRow(move.id);
        return;
      case "activate": {
        const row = findRow(rows, move.id);
        onSelect(move.id);
        if (row !== null && row.node.expandable) onToggle(move.id, !row.expanded);
        onFocusRow(move.id);
      }
    }
  }

  return (
    <div
      ref={containerRef}
      role="tree"
      aria-label="Azure estate"
      aria-busy={loadingRoot}
      data-testid="tree"
      className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden px-1 py-2"
      onKeyDown={handleKeyDown}
    >
      {loadingRoot && rows.length === 0 ? (
        <p data-testid="tree-loading" className="px-3 py-2 text-sm text-secondary">
          {LOADING_LABEL} reading the subscription.
        </p>
      ) : null}
      {rootFailure !== null ? (
        <div className="mx-2 rounded border border-critical bg-critical-tint px-3 py-2">
          <p data-testid="root-failure" className="text-sm text-critical">
            The estate could not be read: {rootFailure}
          </p>
          <button
            type="button"
            onClick={() => onRetry("root")}
            className="mt-2 min-h-[44px] rounded border border-border px-3 text-sm text-primary"
          >
            Try again
          </button>
        </div>
      ) : null}
      {rows.map((row) => (
        <TreeRow
          key={row.node.id}
          row={row}
          active={row.node.id === activeId}
          selected={row.node.id === selectedId}
          onToggle={onToggle}
          onSelect={onSelect}
          onFocusRow={onFocusRow}
          onRetry={onRetry}
        />
      ))}
    </div>
  );
}

interface TreeRowProps {
  row: Row;
  active: boolean;
  selected: boolean;
  onToggle: (id: string, open: boolean) => void;
  onSelect: (id: string) => void;
  onFocusRow: (id: string) => void;
  onRetry: (id: string) => void;
}

function TreeRow({
  row,
  active,
  selected,
  onToggle,
  onSelect,
  onFocusRow,
  onRetry,
}: TreeRowProps): JSX.Element {
  const { node, expansion } = row;
  const indent = Math.min((row.level - 1) * INDENT_STEP, MAX_INDENT);
  const expansionFailed = row.expanded && expansion !== null && !answered(expansion.status);
  const expansionEmpty =
    row.expanded &&
    expansion !== null &&
    answered(expansion.status) &&
    expansion.children.length === 0;

  const accessibleName = [
    node.label,
    KIND_LABEL[node.kind],
    node.status === "ok" ? null : statusLabel(node.status),
  ]
    .filter((part): part is string => part !== null)
    .join(", ");

  function stopBubble(event: MouseEvent<HTMLElement>): void {
    event.stopPropagation();
  }

  return (
    <div
      role="treeitem"
      data-testid="tree-row"
      data-node-id={node.id}
      data-label={node.label}
      data-kind={node.kind}
      data-status={node.status}
      aria-level={row.level}
      aria-posinset={row.posinset}
      aria-setsize={row.setsize}
      aria-selected={selected}
      aria-busy={row.loading}
      aria-label={accessibleName}
      {...(node.expandable ? { "aria-expanded": row.expanded } : {})}
      tabIndex={active ? 0 : -1}
      onFocus={() => onFocusRow(node.id)}
      onClick={() => {
        onSelect(node.id);
        if (node.expandable && !row.expanded) onToggle(node.id, true);
      }}
      className={[
        "cursor-pointer select-none rounded border-l-2",
        selected
          ? "border-flow bg-flow-tint"
          : "border-transparent hover:bg-surface",
      ].join(" ")}
    >
      <div
        className="flex min-h-[44px] w-full items-center gap-2 py-1 pr-2 md:min-h-[30px] md:py-0.5"
        style={{ paddingLeft: `${String(indent + 4)}px` }}
      >
        {node.expandable ? (
          <button
            type="button"
            tabIndex={-1}
            data-testid="tree-twisty"
            aria-label={`${row.expanded ? "Collapse" : "Expand"} ${node.label}`}
            onClick={(event) => {
              stopBubble(event);
              onToggle(node.id, !row.expanded);
            }}
            className="flex h-11 w-8 shrink-0 items-center justify-center rounded text-muted hover:text-primary md:h-6 md:w-5"
          >
            <svg
              viewBox="0 0 16 16"
              width="11"
              height="11"
              aria-hidden="true"
              className={`transition-transform ${row.expanded ? "rotate-90" : ""}`}
              fill="currentColor"
            >
              <path d="M5 2.5 11.5 8 5 13.5Z" />
            </svg>
          </button>
        ) : (
          <span aria-hidden="true" className="h-11 w-8 shrink-0 md:h-6 md:w-5" />
        )}
        <span className={selected ? "text-flow" : "text-muted"}>
          <Icon name={KIND_ICON[node.kind]} />
        </span>
        <span className="flex min-w-0 flex-1 flex-col">
          <span className="flex min-w-0 items-center gap-1.5">
            <span
              className="truncate text-[13px] leading-5 text-primary"
              title={`${node.label} — ${KIND_LABEL[node.kind]}`}
            >
              {node.label}
            </span>
            {row.loading ? (
              <Badge tone="flow" testId="row-loading">
                {LOADING_LABEL}
              </Badge>
            ) : null}
            {node.status === "ok" ? null : <StatusBadge status={node.status} />}
            {row.expanded && expansion !== null && expansion.status !== node.status ? (
              <StatusBadge status={expansion.status} />
            ) : null}
            {row.expanded && expansion?.truncated === true ? (
              <Badge tone="warning" testId="row-truncated">
                {childCountText(expansion.children.length, true)}
              </Badge>
            ) : null}
          </span>
          {node.error !== null ? (
            <span className="truncate text-[11px] text-muted" title={node.error}>
              {node.error}
            </span>
          ) : null}
        </span>
      </div>

      {expansionFailed || expansionEmpty || row.failure !== null ? (
        <div
          onClick={stopBubble}
          className="mb-1 mr-2"
          style={{ marginLeft: `${String(indent + 34)}px` }}
        >
          {row.failure !== null ? (
            <div className="rounded border border-critical bg-critical-tint px-3 py-2">
              <p data-testid="row-failure" className="text-sm text-critical">
                {row.failure}
              </p>
              <button
                type="button"
                onClick={() => onRetry(node.id)}
                className="mt-2 min-h-[44px] rounded border border-border px-3 text-sm text-primary"
              >
                Try again
              </button>
            </div>
          ) : null}
          {expansionFailed && expansion !== null ? (
            <StatusNote
              status={expansion.status}
              error={expansion.error}
              action="open this branch"
              testId="branch-note"
            />
          ) : null}
          {expansionEmpty ? (
            <p
              data-testid="branch-empty"
              className="rounded border border-border-soft bg-canvas2 px-3 py-1.5 text-[13px] text-secondary"
            >
              Nothing here. The call succeeded and returned no items.
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
