/**
 * SearchRenderer — retrieval hits as a stack of readable cards.
 *
 * A table is the wrong shape for retrieval: the payload is one long text
 * field plus three short ones, and a table cell either truncates it to
 * nothing or blows the column width out. Cards give the passage room and keep
 * the title, source and score scannable down the left edge.
 */

import { ToolResultCard } from "../ToolResultCard";
import { parseToolResult, scopeBadges } from "../helpers";
import {
  ArchetypeEmpty,
  ArchetypeUnresolved,
  renderEnvelopeState,
  type ArchetypeRendererProps,
} from "./_common";

interface SearchHit {
  title?: string;
  source?: string;
  score?: number;
  text?: string;
}

export function SearchRenderer({ resizeKey, result }: ArchetypeRendererProps) {
  const parsed = parseToolResult<{ results?: SearchHit[] } & Record<string, unknown>>(result);
  if (!parsed) return <ArchetypeUnresolved archetype="search" result={result} />;

  const envelopeState = renderEnvelopeState(parsed);
  if (envelopeState) return envelopeState;

  const results = parsed.results;
  if (!Array.isArray(results)) return <ArchetypeUnresolved archetype="search" result={result} />;

  const scope = scopeBadges(parsed);
  if (results.length === 0) {
    return <ArchetypeEmpty label="hits" message="No results found" scope={scope} />;
  }

  return (
    <ToolResultCard resizeKey={resizeKey} scope={scope} signal={[{ label: "hits", value: results.length }]}>
      <div className="max-h-64 space-y-2 overflow-y-auto">
        {results.map((hit, index) => (
          <div
            key={index}
            className="space-y-1 rounded-lg border border-border/50 bg-neutral-bg1 px-3 py-2"
          >
            <div className="flex items-center gap-2">
              <span className="flex-1 truncate text-xs font-semibold text-text-primary">
                {hit.title || "Untitled"}
              </span>
              {typeof hit.score === "number" && (
                <span className="shrink-0 rounded bg-brand/10 px-1.5 py-0.5 font-mono text-micro font-medium text-brand">
                  {hit.score.toFixed(2)}
                </span>
              )}
            </div>
            {hit.source && <div className="truncate text-micro text-text-muted">{hit.source}</div>}
            {hit.text && (
              <p className="line-clamp-3 text-xs leading-relaxed text-text-secondary">
                {hit.text}
              </p>
            )}
          </div>
        ))}
      </div>
    </ToolResultCard>
  );
}
