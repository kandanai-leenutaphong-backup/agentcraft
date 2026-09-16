/**
 * SuggestedQueries — clickable suggestion pills for empty chat state.
 *
 * Renders a row of rounded pills above the chat input. Each pill
 * contains a query that, when clicked, is submitted to the agent
 * immediately. Pills disappear once messages exist.
 *
 * Used by: ChatPanel (investigator), LookupDock (dock agents).
 */

import { DEFAULT_SUGGESTIONS } from "@/config/suggestedQueries";

interface SuggestedQueriesProps {
  agentId: string;
  onSelect: (query: string) => void;
}

export function SuggestedQueries({ agentId, onSelect }: SuggestedQueriesProps) {
  const suggestions = DEFAULT_SUGGESTIONS[agentId];
  if (!suggestions || suggestions.length === 0) return null;

  return (
    <div className="flex flex-wrap gap-2 px-6 py-3 justify-center">
      {suggestions.map((query, i) => (
        <button
          key={i}
          data-testid="suggestion-bubble"
          onClick={() => onSelect(query)}
          className="px-3 py-1.5 text-xs rounded-full border border-brand/30 bg-brand/5 text-brand hover:bg-brand/15 hover:border-brand/50 transition-colors max-w-[280px] truncate"
          title={query}
        >
          {query}
        </button>
      ))}
    </div>
  );
}
