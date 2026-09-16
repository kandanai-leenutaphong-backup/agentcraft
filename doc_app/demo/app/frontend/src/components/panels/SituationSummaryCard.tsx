/**
 * SituationSummaryCard — operator-driven summary panel above priorities.
 *
 * Displays the latest persisted :class:`SituationSummary` for the
 * active session. The **Summarize** button posts to
 * ``POST /api/summaries/{session_id}/run`` which dumps the
 * GridManager transcript (user prompt, assistant text, every tool
 * call's name + arguments + result) to the hidden summarizer agent
 * and replaces the card's contents with one glance-readable
 * headline + 3–4 bullets.
 */

import { Activity, Loader2, Sparkles } from "lucide-react";
import { useSummaryStore } from "@/stores/summaryStore";
import { useSessionStore } from "@/stores/sessionStore";

// Confidence chip removed 2026-05-18 (Phase 2 workstream F). Operators
// could not interpret what HIGH/MEDIUM/LOW meant or what action it
// implied. The field is still emitted by the summarizer and persisted
// on `SituationSummary.confidence` for back-compat, but no longer
// rendered. Remove the field entirely in a later cleanup once no
// dashboards or audits read it.

export function SituationSummaryCard() {
  const sessionId = useSessionStore((s) => s.activeSessionId);
  const summaryState = useSummaryStore((s) => s.summaryState);
  const loading = useSummaryStore((s) => s.loading);
  const error = useSummaryStore((s) => s.error);
  const streamingText = useSummaryStore((s) => s.streamingText);
  const run = useSummaryStore((s) => s.run);

  const current = summaryState.current;
  const updatedAt = current?.updated_at ? new Date(current.updated_at) : null;
  /* Show the streaming-banner UI while loading AND we have tokens but
     the final SummaryState hasn't been swapped in yet. The streaming
     text is raw model output (often partial JSON braces) so we render
     it as muted body text behind a "Summarising…" label rather than as
     the final glance-readable bullet list. */
  const isStreaming = loading && streamingText.length > 0;

  const onSummarize = () => {
    if (!sessionId || loading) return;
    void run(sessionId);
  };

  return (
    <div
      data-testid="situation-summary-card"
      className="mb-3 rounded-lg border border-border bg-neutral-bg2 px-4 py-3"
    >
      {/* Header row */}
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-text-tertiary font-bold">
          <Activity className="h-3.5 w-3.5" />
          Situation summary
        </div>
        <button
          type="button"
          data-testid="summary-run-button"
          onClick={onSummarize}
          disabled={!sessionId || loading}
          className="inline-flex items-center gap-1.5 rounded-md bg-brand px-2.5 py-1 text-xs font-semibold text-on-accent shadow hover:bg-brand-hover disabled:cursor-not-allowed disabled:bg-brand/40 disabled:text-on-accent/70"
          title={
            !sessionId
              ? "Open a session first"
              : loading
                ? "Summarising…"
                : "Run the summarizer over the current GridManager transcript"
          }
        >
          {loading ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Sparkles className="h-3.5 w-3.5" />
          )}
          {loading ? "Summarising" : "Summarize"}
        </button>
      </div>

      {/* Headline */}
      <h3
        data-testid="situation-summary-headline"
        className="mt-2 text-sm font-semibold text-text-primary leading-snug"
      >
        {current?.headline || "Click Summarize to generate a glance-readable recap."}
      </h3>

      {/* Streaming token banner — only while the SSE stream is in flight
          and the operator has seen at least one token. Renders raw model
          tokens (often partial JSON) as muted preformatted text so the
          operator sees activity within ~1.5s of clicking Summarize.
          Swapped out for the parsed bullets on the terminal `complete`
          event. Phase 2 workstream E (2026-05-18). */}
      {isStreaming && (
        <div
          data-testid="situation-summary-streaming"
          className="mt-3 rounded border border-dashed border-border bg-neutral-bg3/40 px-3 py-2"
        >
          <div className="text-label font-semibold uppercase tracking-wider text-text-tertiary mb-1">
            Summarising…
          </div>
          <pre
            data-testid="situation-summary-streaming-text"
            className="whitespace-pre-wrap break-words font-mono text-xs text-text-muted leading-snug max-h-40 overflow-y-auto"
          >
            {streamingText}
          </pre>
        </div>
      )}

      {/* Bullets — the operationally valuable part. Hidden while
          streaming so the operator's eye lands on the live feed; once
          the SummaryState swaps in we drop the banner and render here. */}
      {!isStreaming && current && current.bullets.length > 0 && (
        <ul className="mt-3 space-y-1.5 text-sm text-text-secondary list-disc pl-5">
          {current.bullets.map((bullet, idx) => (
            <li
              data-testid="situation-summary-bullet"
              key={`${current.updated_at}-${idx}`}
            >
              {bullet}
            </li>
          ))}
        </ul>
      )}

      {/* Open questions — only when present */}
      {current && current.open_questions && current.open_questions.length > 0 && (
        <div className="mt-3">
          <div className="text-label font-semibold uppercase tracking-wider text-text-tertiary">
            Open questions
          </div>
          <ul className="mt-1 space-y-1 text-xs text-text-secondary list-disc pl-5">
            {current.open_questions.map((q, idx) => (
              <li key={`${current.updated_at}-q-${idx}`}>{q}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Footer — last-updated only. Confidence chip removed 2026-05-18. */}
      {current && updatedAt && (
        <div className="mt-3 flex items-center gap-2 text-label text-text-tertiary">
          <span data-testid="situation-summary-updated">
            Updated {updatedAt.toLocaleTimeString()}
          </span>
        </div>
      )}

      {error && (
        <p className="mt-2 text-xs text-status-error" data-testid="situation-summary-error">
          {error}
        </p>
      )}
    </div>
  );
}
