/**
 * Where the selected node sits, root first.
 *
 * The hierarchy is deep — subscription, group, account, containers, folders,
 * blob is eight levels on a real estate — so the path wraps rather than
 * truncating, and the last entry is marked as the current one.
 */

import type { JSX } from "react";

export function Breadcrumbs({ path }: { path: string[] }): JSX.Element | null {
  if (path.length === 0) return null;
  return (
    <nav aria-label="Path to this node" data-testid="breadcrumbs">
      <ol className="flex flex-wrap items-center gap-x-1 gap-y-0.5 text-xs text-muted">
        {path.map((label, index) => {
          const last = index === path.length - 1;
          return (
            <li key={`${label}-${String(index)}`} className="flex items-center gap-1">
              {index > 0 ? (
                <span aria-hidden="true" className="text-border">
                  /
                </span>
              ) : null}
              <span
                data-testid="breadcrumb-item"
                {...(last ? { "aria-current": "page" as const } : {})}
                className={last ? "font-medium text-secondary" : ""}
              >
                {label}
              </span>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
