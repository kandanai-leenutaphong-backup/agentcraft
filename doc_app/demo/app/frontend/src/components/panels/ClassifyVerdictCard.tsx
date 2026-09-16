/**
 * ClassifyVerdictCard — operator-facing classify verdict panel.
 *
 * Restored 2026-05-18 (Phase 2 workstream C) in the slot the retired
 * `classifier_verdict` banner used to occupy. Renders below the
 * `SituationSummaryCard` and above `PriorityActionsPanel`. Always
 * present even when empty so the operator's eye knows exactly where
 * to look for the verdict during an emergency.
 *
 * Data flow:
 *   - grid_manager calls `classify(verdict, justification, sources?)`.
 *   - The tool envelope returns `panel: "event_classification"`.
 *   - `panelStore.updatePanel("classify", args)` updates the slot.
 *   - This card consumes `classifyVerdict` and renders.
 *
 * Empty state: shows a muted placeholder so the panel never collapses
 * to zero height. Operators read the panel's *presence* as part of the
 * cognitive map — disappearing on empty would force them to wonder
 * where the verdict went.
 *
 * The verdict pill colour palette intentionally matches
 * `CLASS_PILL_SOFT` in `SituationCard.tsx` so the chat tool-card and
 * the panel agree visually.
 */

import { Gavel } from "lucide-react";
import { usePanelStore, type ClassifyVerdict } from "@/stores/panelStore";
import { useVocab } from "@/stores/vocabularyStore";

/* Pill styling per verdict — tone follows disposition semantics that hold
   across every domain: the "this is real / a threat" verdict is alarming
   (red), the "not a threat / safe" verdict is reassuring (green), the
   "related-but-secondary / suspicious" verdict is cautionary (amber),
   and "evidence insufficient" is neutral grey. (Previously credible was
   amber and non_event red, which read backwards for a SOC verdict.) */
const VERDICT_PILL: Record<ClassifyVerdict, string> = {
  credible_event:     "bg-status-error/15 text-status-error",
  non_credible_event: "bg-status-warning/15 text-status-warning",
  non_event:          "bg-status-success/15 text-status-success",
  indeterminate:      "bg-neutral-bg3 text-text-muted",
};

/* Fallback labels. The displayed label is taken from the scenario
   vocabulary (classificationLabels) when present. */
const VERDICT_FALLBACK_LABEL: Record<ClassifyVerdict, string> = {
  credible_event:     "Credible",
  non_credible_event: "Non-Credible",
  non_event:          "Safe",
  indeterminate:      "Indeterminate",
};

/* Maps the internal verdict literal onto the vocabulary classification
   key so the banner and the per-alert card badge always agree. */
const VERDICT_VOCAB_KEY: Record<ClassifyVerdict, "credible" | "non_credible" | "non_event" | null> = {
  credible_event:     "credible",
  non_credible_event: "non_credible",
  non_event:          "non_event",
  indeterminate:      null,
};

export function ClassifyVerdictCard() {
  const verdict = usePanelStore((s) => s.classifyVerdict);
  const classificationLabels = useVocab("classificationLabels");

  /* Empty state — render the panel chrome but no verdict pill. The
     placeholder text tells the operator the agent has not classified
     yet, which is itself useful information during an investigation. */
  if (!verdict) {
    return (
      <div
        data-testid="classify-verdict-card"
        data-state="empty"
        className="mb-3 rounded-lg border border-border bg-neutral-bg2 px-4 py-3"
      >
        <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-text-tertiary font-bold">
          <Gavel className="h-3.5 w-3.5" />
          Event classification
        </div>
        <p
          data-testid="classify-verdict-empty"
          className="mt-2 text-sm text-text-muted italic leading-snug"
        >
          No classification yet — the agent has not called `classify`.
        </p>
      </div>
    );
  }

  const pillClasses = VERDICT_PILL[verdict.verdict] ?? VERDICT_PILL.indeterminate;
  const vocabKey = VERDICT_VOCAB_KEY[verdict.verdict];
  const label =
    (vocabKey ? classificationLabels[vocabKey] : undefined) ??
    VERDICT_FALLBACK_LABEL[verdict.verdict] ??
    verdict.verdict;
  const updatedAt = verdict.updated_at ? new Date(verdict.updated_at) : null;

  return (
    <div
      data-testid="classify-verdict-card"
      data-spotlight-id="classify-verdict"
      data-state="ready"
      data-verdict={verdict.verdict}
      className="mb-3 rounded-lg border border-border bg-neutral-bg2 px-4 py-3"
    >
      {/* Header row — caption + verdict pill on the right edge. The pill
          is the highest-priority glance read in this card, so it sits
          opposite the caption rather than buried under the justification. */}
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-text-tertiary font-bold">
          <Gavel className="h-3.5 w-3.5" />
          Event classification
        </div>
        <span
          data-testid="classify-verdict-pill"
          className={`shrink-0 rounded px-2 py-0.5 text-xs font-bold uppercase tracking-wide ${pillClasses}`}
        >
          {label}
        </span>
      </div>

      {/* Justification — single concise paragraph (2026-05-19). The
          grid_manager prompt + classify tool both now mandate one
          sentence \u2264 240 chars; rendered as plain wrapped body text so
          the operator absorbs it in < 5 s. `break-words` keeps long
          equipment IDs from overflowing the panel chrome. */}
      <p
        data-testid="classify-verdict-justification"
        className="mt-3 break-words text-sm text-text-secondary leading-snug"
      >
        {verdict.justification}
      </p>

      {/* Sources block intentionally removed 2026-05-19 \u2014 the
          justification stands on its own; the chat reply and
          push_action.reasoning carry the evidence trail. Operator
          feedback: the sources block formatting was broken and added
          no decision-relevant signal at the verdict-banner read. */}

      {/* Footer \u2014 last-updated only, matches the SituationSummaryCard
          footer shape so the two panels read as a stack of siblings. */}
      {updatedAt && (
        <div className="mt-3 flex items-center gap-2 text-label text-text-tertiary">
          <span data-testid="classify-verdict-updated">
            Updated {updatedAt.toLocaleTimeString()}
          </span>
        </div>
      )}
    </div>
  );
}
