/**
 * SearchResultCards — renders search tool results as a stacked card list,
 * wrapped in the shared ToolResultCard scaffold.
 *
 * Shape: `{results: [{title, source, score, text}], count: N}`. Each
 * result is a clickable button-card (R7 a11y) opening a full markdown
 * overlay with a Tailwind-token-driven text-scale slider.
 */

import { useState, useEffect } from "react";
import { MarkdownRenderer } from "../../shared/MarkdownRenderer";
import type { ToolResultProps } from "./index";
import { JsonFallback } from "./JsonFallback";
import { ToolResultCard } from "./ToolResultCard";
import { extractError, parseToolResult } from "./helpers";

interface SearchResult {
  title: string;
  source: string;
  score: number;
  text: string;
}

interface SearchEnvelope {
  results?: SearchResult[];
  count?: number;
}

export function SearchResultCards({ result }: ToolResultProps) {
  const [selectedResult, setSelectedResult] = useState<SearchResult | null>(null);

  const parsed = parseToolResult<SearchEnvelope & Record<string, unknown>>(result);
  if (!parsed) return <JsonFallback result={result} />;

  const errDetail = extractError(parsed);
  if (errDetail) return <ToolResultCard error={{ detail: errDetail }} />;

  const results = parsed.results;
  if (!Array.isArray(results) || results.length === 0) {
    return (
      <ToolResultCard signal={[{ label: "hits", value: 0, tone: "neutral" }]}>
        <div className="text-xs text-text-muted italic py-1">No results found</div>
      </ToolResultCard>
    );
  }

  return (
    <>
      <ToolResultCard signal={[{ label: "hits", value: results.length }]}>
        <div className="space-y-2 max-h-64 overflow-y-auto">
          {results.map((r, i) => (
            <button
              key={i}
              type="button"
              onClick={() => setSelectedResult(r)}
              title="Click to expand"
              className="w-full text-left rounded-lg border border-border/50 bg-neutral-bg1 px-3 py-2 space-y-1 cursor-pointer hover:border-brand/40 hover:bg-brand/5 focus-visible:border-brand focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-brand transition-colors"
            >
              <div className="flex items-center gap-2">
                <span className="text-xs font-semibold text-text-primary truncate flex-1">
                  {r.title || "Untitled"}
                </span>
                {r.score != null && (
                  <span className="shrink-0 text-micro px-1.5 py-0.5 rounded bg-brand/10 text-brand font-mono font-medium">
                    {r.score.toFixed(2)}
                  </span>
                )}
              </div>
              {r.source && (
                <div className="text-micro text-text-muted truncate">{r.source}</div>
              )}
              <p className="text-xs text-text-secondary leading-relaxed line-clamp-3">
                {r.text}
              </p>
            </button>
          ))}
        </div>
      </ToolResultCard>

      {selectedResult && (
        <SearchResultOverlay
          result={selectedResult}
          onClose={() => setSelectedResult(null)}
        />
      )}
    </>
  );
}

/** Full-viewport overlay showing a search result as formatted markdown. */
function SearchResultOverlay({
  result,
  onClose,
}: {
  result: SearchResult;
  onClose: () => void;
}) {
  const [textScale, setTextScale] = useState(100);

  /* Close on Escape. */
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-overlay-backdrop-heavy backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="relative w-full max-w-4xl max-h-[85vh] mx-4 rounded-xl bg-neutral-bg1 border border-border shadow-2xl overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-5 py-3 border-b border-border bg-neutral-bg2">
          <div className="flex-1 min-w-0">
            <h3 className="text-base font-bold text-text-primary truncate">
              {result.title || "Document"}
            </h3>
            <div className="flex items-center gap-3 mt-1">
              {result.source && (
                <span className="text-label text-text-muted truncate max-w-[300px]">
                  {result.source}
                </span>
              )}
              <span className="text-label px-1.5 py-0.5 rounded bg-brand/10 text-brand font-mono font-medium">
                Score: {result.score.toFixed(3)}
              </span>
            </div>
          </div>
          {/* Text scale slider — R8: Tailwind utilities replace inline style geometry. */}
          <div className="flex items-center gap-2 shrink-0 ml-4">
            <input
              type="range"
              min={70}
              max={180}
              step={5}
              value={textScale}
              onChange={(e) => setTextScale(Number(e.target.value))}
              className="accent-brand cursor-pointer w-20 h-1"
              title={`Text scale: ${textScale}%`}
            />
            <span className="text-micro font-mono text-text-muted w-8 text-right">
              {textScale}%
            </span>
          </div>
          <button
            onClick={onClose}
            className="ml-3 text-text-muted hover:text-text-primary text-lg transition-colors"
            title="Close"
          >
            ✕
          </button>
        </div>

        {/* Scrollable markdown content — fontSize remains inline because
            it is dynamic per slider position and per-user. */}
        <div
          className="overflow-y-auto p-5"
          style={{ fontSize: `${Math.round(14 * textScale / 100)}px` }}
        >
          <div className="prose max-w-none text-text-secondary [font-size:inherit]">
            <MarkdownRenderer content={result.text} />
          </div>
        </div>
      </div>
    </div>
  );
}
