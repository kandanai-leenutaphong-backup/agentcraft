/**
 * Estate search results.
 *
 * Every hit says where it matched, because "why is this in my results" is the
 * first question a name-only list cannot answer. Opening a hit walks the tree
 * down to it rather than replacing the tree, so the reader keeps their place
 * in the estate.
 */

import type { JSX } from "react";

import { KIND_ICON, KIND_LABEL, matchedInLabel } from "../api/kinds";
import { formatObservedAt } from "../api/format";
import { LOADING_LABEL } from "../api/status";
import type { SearchState } from "../api/state";
import type { SearchHit } from "../api/wire";
import { Icon } from "./Icon";
import { Badge, StatusNote, TruncationNote } from "./StatusNote";

export interface SearchPanelProps {
  search: SearchState;
  onOpenHit: (hit: SearchHit) => void;
  onClose: () => void;
}

export function SearchPanel({ search, onOpenHit, onClose }: SearchPanelProps): JSX.Element {
  return (
    <section
      aria-label="Estate search results"
      data-testid="search-panel"
      className="flex max-h-[38vh] shrink-0 flex-col border-b border-border bg-canvas2"
    >
      <div className="flex items-center gap-2 px-3 py-2">
        <h2 className="mr-auto min-w-0 truncate text-sm font-semibold text-primary">
          {search.ran === null
            ? "Searching the estate"
            : `Estate matches for “${search.ran}” — ${String(search.hits.length)} found`}
        </h2>
        <button
          type="button"
          onClick={onClose}
          data-testid="search-close"
          className="min-h-[44px] shrink-0 rounded border border-border px-3 text-sm text-primary"
        >
          Close results
        </button>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-3 pb-3">
        {search.loading ? (
          <p data-testid="search-loading" className="text-sm text-secondary">
            {LOADING_LABEL} querying every resource in the subscription.
          </p>
        ) : null}

        {search.failure !== null ? (
          <p
            data-testid="search-failure"
            className="rounded border border-critical bg-critical-tint px-3 py-2 text-sm text-critical"
          >
            {search.failure}
          </p>
        ) : null}

        {!search.loading && search.status !== null && search.status !== "ok" && search.status !== "empty" ? (
          <StatusNote
            status={search.status}
            error={search.error}
            action="run this search"
            testId="search-note"
          />
        ) : null}

        {!search.loading && search.status === "empty" && search.hits.length === 0 ? (
          <p data-testid="search-empty" className="text-sm text-secondary">
            Nothing in this subscription matches that term. Search covers a resource&rsquo;s
            name, type, resource group, location, tags and property bag.
          </p>
        ) : null}

        {search.truncated ? (
          <div className="mb-2">
            <TruncationNote>
              Only the first {search.hits.length} matches are shown. Narrow the term to see
              the rest.
            </TruncationNote>
          </div>
        ) : null}

        <ul className="flex flex-col gap-1.5">
          {search.hits.map((hit) => (
            <li key={hit.node}>
              <button
                type="button"
                data-testid="search-hit"
                data-label={hit.label}
                data-kind={hit.kind}
                onClick={() => onOpenHit(hit)}
                className="flex min-h-[44px] w-full min-w-0 items-start gap-2 rounded border border-border bg-canvas px-3 py-2 text-left hover:bg-surface"
              >
                <span className="mt-0.5 text-muted">
                  <Icon name={KIND_ICON[hit.kind]} />
                </span>
                <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                  <span className="flex min-w-0 flex-wrap items-center gap-2">
                    <span className="min-w-0 break-words text-[13px] font-semibold text-primary">
                      {hit.label}
                    </span>
                    <Badge tone="neutral">{KIND_LABEL[hit.kind]}</Badge>
                    <Badge tone="flow">{matchedInLabel(hit.matchedIn)}</Badge>
                  </span>
                  <span className="min-w-0 break-words font-mono text-[11px] text-muted">
                    {hit.type} · {hit.resourceGroup} · {hit.location}
                  </span>
                </span>
              </button>
            </li>
          ))}
        </ul>

        {search.observedAt === null ? null : (
          <p className="mt-2 text-[11px] text-muted">
            Queried {formatObservedAt(search.observedAt)}
          </p>
        )}
      </div>
    </section>
  );
}
