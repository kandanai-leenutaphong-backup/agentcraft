/**
 * The right-hand pane: what this node is, what it contains, and what is known
 * about it.
 *
 * Two tabs, because the two questions are different. Contents is the payload —
 * bytes, documents, rows. Details is the node's own metadata and the outcome
 * of expanding it. A node with no contents opens on Details rather than
 * showing an empty tab, and says why.
 */

import { useEffect, useRef, useState, type JSX, type KeyboardEvent } from "react";

import { childCountText, formatObservedAt } from "../api/format";
import { KIND_LABEL, KIND_MEANING } from "../api/kinds";
import { answered, detailValueText, statusLabel, statusTone } from "../api/status";
import type { Expansion } from "../api/state";
import type { ContentResponse, TreeNode } from "../api/wire";
import { Breadcrumbs } from "./Breadcrumbs";
import { ContentView } from "./content/ContentView";
import { Icon } from "./Icon";
import { KIND_ICON } from "../api/kinds";
import { Badge, StatusNote } from "./StatusNote";

type Tab = "contents" | "details";

export interface DetailPaneProps {
  node: TreeNode | null;
  path: string[];
  expansion: Expansion | null;
  expansionFailure: string | null;
  content: ContentResponse | null;
  contentLoading: boolean;
  contentFailure: string | null;
  showBack: boolean;
  onBack: () => void;
  onRefresh: () => void;
  onRetryContent: () => void;
}

export function DetailPane(props: DetailPaneProps): JSX.Element {
  const {
    node,
    path,
    expansion,
    expansionFailure,
    content,
    contentLoading,
    contentFailure,
    showBack,
    onBack,
    onRefresh,
    onRetryContent,
  } = props;
  const [tab, setTab] = useState<Tab>("details");
  const tabsRef = useRef<HTMLDivElement>(null);
  const nodeId = node?.id ?? null;
  const hasContent = node?.hasContent === true;

  useEffect(() => {
    setTab(hasContent ? "contents" : "details");
  }, [nodeId, hasContent]);

  if (node === null) {
    return (
      <section
        aria-label="Node detail"
        data-testid="detail"
        className="flex min-w-0 flex-1 flex-col items-center justify-center gap-2 p-6 text-center"
      >
        <p className="max-w-sm text-sm text-secondary">
          Select anything in the tree. Groups and containers open downwards; blobs,
          documents, tables and ARM properties show their contents here.
        </p>
      </section>
    );
  }

  function onTabKey(event: KeyboardEvent<HTMLDivElement>): void {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();
    const next: Tab = tab === "contents" ? "details" : "contents";
    if (next === "contents" && !hasContent) return;
    setTab(next);
    const button = tabsRef.current?.querySelector<HTMLElement>(`#tab-${next}`);
    button?.focus();
  }

  return (
    <section
      aria-label="Node detail"
      data-testid="detail"
      className="flex min-h-0 min-w-0 flex-1 flex-col"
    >
      <div className="flex min-w-0 flex-col gap-2 border-b border-border px-3 py-3 md:px-4">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          {showBack ? (
            <button
              type="button"
              onClick={onBack}
              data-testid="detail-back"
              className="min-h-[44px] rounded border border-border px-3 text-sm text-primary"
            >
              ← Tree
            </button>
          ) : null}
          <Breadcrumbs path={path} />
        </div>
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <span className="text-flow">
            <Icon name={KIND_ICON[node.kind]} />
          </span>
          <h2
            data-testid="detail-title"
            className="min-w-0 flex-1 break-words text-base font-semibold text-primary"
            title={node.label}
          >
            {node.label}
          </h2>
          <button
            type="button"
            onClick={onRefresh}
            data-testid="refresh-selected"
            className="min-h-[44px] shrink-0 rounded border border-border px-3 text-sm text-primary"
          >
            Reload this
          </button>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone="neutral" testId="detail-kind">
            {KIND_LABEL[node.kind]}
          </Badge>
          <Badge tone={statusTone(node.status)} testId="detail-status">
            {statusLabel(node.status)}
          </Badge>
          {expansion !== null && expansion.status !== node.status ? (
            <Badge tone={statusTone(expansion.status)} testId="detail-branch-status">
              Branch: {statusLabel(expansion.status)}
            </Badge>
          ) : null}
          <span className="text-xs text-muted">{KIND_MEANING[node.kind]}</span>
        </div>
      </div>

      <div
        ref={tabsRef}
        role="tablist"
        aria-label="What to show for this node"
        onKeyDown={onTabKey}
        className="flex shrink-0 gap-1 border-b border-border px-2 pt-2 md:px-3"
      >
        <TabButton
          id="tab-contents"
          selected={tab === "contents"}
          disabled={!hasContent}
          onSelect={() => setTab("contents")}
        >
          Contents
        </TabButton>
        <TabButton
          id="tab-details"
          selected={tab === "details"}
          disabled={false}
          onSelect={() => setTab("details")}
        >
          Details
        </TabButton>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden px-3 py-3 md:px-4">
        {tab === "contents" ? (
          <div
            role="tabpanel"
            id="panel-contents"
            aria-labelledby="tab-contents"
            tabIndex={0}
            className="min-w-0"
          >
            <ContentView
              content={content}
              loading={contentLoading}
              failure={contentFailure}
              hasContent={hasContent}
              onRetry={onRetryContent}
            />
          </div>
        ) : (
          <div
            role="tabpanel"
            id="panel-details"
            aria-labelledby="tab-details"
            tabIndex={0}
            className="min-w-0"
          >
            <DetailsBody
              node={node}
              expansion={expansion}
              expansionFailure={expansionFailure}
            />
          </div>
        )}
      </div>
    </section>
  );
}

function TabButton({
  id,
  selected,
  disabled,
  onSelect,
  children,
}: {
  id: string;
  selected: boolean;
  disabled: boolean;
  onSelect: () => void;
  children: string;
}): JSX.Element {
  return (
    <button
      type="button"
      id={id}
      role="tab"
      data-testid={id}
      aria-selected={selected}
      aria-controls={id === "tab-contents" ? "panel-contents" : "panel-details"}
      aria-disabled={disabled}
      tabIndex={selected ? 0 : -1}
      onClick={() => {
        if (!disabled) onSelect();
      }}
      className={[
        "min-h-[44px] rounded-t border-b-2 px-3 text-sm",
        selected ? "border-flow font-semibold text-primary" : "border-transparent",
        disabled ? "cursor-not-allowed text-muted" : "text-secondary",
      ].join(" ")}
    >
      {children}
    </button>
  );
}

function DetailsBody({
  node,
  expansion,
  expansionFailure,
}: {
  node: TreeNode;
  expansion: Expansion | null;
  expansionFailure: string | null;
}): JSX.Element {
  const entries = Object.entries(node.detail ?? {});
  return (
    <div className="flex min-w-0 flex-col gap-3">
      {node.error !== null ? (
        <StatusNote
          status={node.status}
          error={node.error}
          action="read this node"
          testId="detail-note"
        />
      ) : null}
      {expansionFailure !== null ? (
        <p
          data-testid="detail-failure"
          className="rounded border border-critical bg-critical-tint px-3 py-2 text-sm text-critical"
        >
          {expansionFailure}
        </p>
      ) : null}
      {expansion !== null && !answered(expansion.status) && node.error === null ? (
        <StatusNote
          status={expansion.status}
          error={expansion.error}
          action="open this branch"
          testId="detail-note"
        />
      ) : null}

      <dl
        data-testid="detail-list"
        className="grid grid-cols-1 gap-x-4 sm:grid-cols-[minmax(0,10rem)_minmax(0,1fr)]"
      >
        {entries.length === 0 ? (
          <Entry name="detail" value="The server reported no detail for this node." />
        ) : (
          entries.map(([key, value]) => (
            <Entry key={key} name={key} value={detailValueText(value)} />
          ))
        )}
        {expansion === null ? null : (
          <>
            <Entry name="branch status" value={statusLabel(expansion.status)} />
            <Entry
              name="children"
              value={
                answered(expansion.status)
                  ? childCountText(expansion.children.length, expansion.truncated)
                  : "not returned — this branch did not answer"
              }
            />
            <Entry name="read at" value={formatObservedAt(expansion.observedAt)} />
          </>
        )}
        <Entry name="has contents" value={node.hasContent ? "yes" : "no"} />
        <Entry name="opens further" value={node.expandable ? "yes" : "no"} />
      </dl>
    </div>
  );
}

function Entry({ name, value }: { name: string; value: string }): JSX.Element {
  return (
    <>
      <dt className="min-w-0 break-words font-mono text-[11px] text-muted">{name}</dt>
      <dd className="mb-2 min-w-0 break-words text-[13px] text-primary">{value}</dd>
    </>
  );
}
