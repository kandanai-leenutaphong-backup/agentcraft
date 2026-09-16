/**
 * PriorityActionsPanel — Center panel with operator actions for crisis response.
 *
 * Design principles:
 *   - Action text is the hero — largest, boldest element on each card
 *   - Priority drives card visual weight via colored left border
 *   - Guide visible by default on pending cards — no click to see what to do
 *   - Single "Done" button — binary triage (pending or done)
 *   - Reasoning + citations expand inline — no full-screen modal
 *   - Done cards collapse to one line below a "COMPLETED" separator
 */

import { usePanelStore, type PriorityAction } from "@/stores/panelStore";
import { useState, useCallback, useRef } from "react";
import { Check, ClipboardList, ExternalLink, Pin, Phone, RotateCcw, XCircle } from "lucide-react";
import { MarkdownRenderer, normalizeBullets } from "@/components/shared";
import { TeamsCallModal } from "@/components/shared/TeamsCallModal";
import { usePlaceholderStore, PLACEHOLDER_ACTIONS } from "@/stores/placeholderStore";
import { useSessionStore } from "@/stores/sessionStore";
import type { PriorityActionStatus } from "@/api/types";
import * as api from "@/api/client";
import { SituationSummaryCard } from "./SituationSummaryCard";
// ClassifierVerdictCard removed 2026-05-18 with the classifier retirement.
// Replacement: ClassifyVerdictCard re-introduced 2026-05-18 (Phase 2
// workstream C) to surface the grid_manager `classify` tool verdict
// in a dedicated panel below the summary panel — always rendered.
import { ClassifyVerdictCard } from "./ClassifyVerdictCard";

/* ── Priority visual config ──────────────────────────────────────────────── */

const PRIORITY_META: Record<number, { label: string; border: string; badge: string; dot?: boolean }> = {
  5: { label: "P5 · Critical", border: "border-l-priority-critical",    badge: "text-priority-critical-text",  dot: true },
  4: { label: "P4 · Urgent",   border: "border-l-priority-urgent",      badge: "text-priority-urgent-text"             },
  3: { label: "P3 · Standard", border: "border-l-priority-standard",    badge: "text-priority-standard-text"           },
  2: { label: "P2 · Low",      border: "border-l-priority-low",         badge: "text-priority-low-text"                },
  1: { label: "P1 · Info",     border: "border-l-priority-info",        badge: "text-priority-info-text"               },
};

/* ── Citation placeholders (empty — no sample source links) ──────────────── */

const PLACEHOLDER_SOURCES: { id: string; label: string; href: string }[] = [];

/** Extract a short label from a blob URL for display. */
function sourceLabel(url: string): string {
  try {
    const parts = url.split("/");
    const filename = decodeURIComponent(parts[parts.length - 1] || url);
    return filename.replace(/\.[^.]+$/, "").replace(/_/g, " ").slice(0, 80);
  } catch {
    return url.slice(0, 80);
  }
}

/* ── Pending Action Card ─────────────────────────────────────────────────── */

function DecisionNoteForm({ status, onSubmit, onCancel, isBusy }: {
  status: Exclude<PriorityActionStatus, "pending">;
  onSubmit: (note: string) => void;
  onCancel: () => void;
  isBusy: boolean;
}) {
  const [note, setNote] = useState("");
  const label = status === "completed" ? "complete" : "decline";
  return (
    <div className="px-4 py-3 border-t border-border/30 bg-neutral-bg1/70 space-y-2">
      <p className="text-micro text-text-tertiary">
        Optional note. This helps improve GridIQ's future action quality and records your operator decision trail.
      </p>
      <textarea
        value={note}
        onChange={(event) => setNote(event.target.value)}
        maxLength={2000}
        rows={3}
        className="w-full resize-y rounded border border-border bg-neutral-bg2 px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-1 focus:ring-brand"
        placeholder={`Why did you ${label} this action?`}
        data-testid={`priority-action-${label}-note`}
      />
      <div className="flex items-center justify-end gap-2">
        <button onClick={onCancel} className="px-3 py-1 rounded text-xs text-text-muted hover:text-text-primary hover:bg-neutral-bg3">
          Cancel
        </button>
        <button
          onClick={() => onSubmit(note)}
          disabled={isBusy}
          className="px-3 py-1 rounded text-xs font-medium text-on-accent bg-brand hover:bg-brand-hover disabled:opacity-50"
          data-testid={`confirm-${label}-action`}
        >
          {isBusy ? "Saving" : `Save ${label}`}
        </button>
      </div>
    </div>
  );
}

function PendingCard({ action, onDecision, onSendToTop, onSendToBottom, isFirst, isLast, isBusy }: {
  action: PriorityAction;
  onDecision: (status: Exclude<PriorityActionStatus, "pending">, note: string) => void;
  onSendToTop: () => void;
  onSendToBottom: () => void;
  isFirst: boolean;
  isLast: boolean;
  isBusy: boolean;
}) {
  const [showWhy, setShowWhy] = useState(false);
  const [showGuide, setShowGuide] = useState(false);
  const [showSources, setShowSources] = useState(false);
  const [showContacts, setShowContacts] = useState(false);
  const [decisionIntent, setDecisionIntent] = useState<Exclude<PriorityActionStatus, "pending"> | null>(null);
  const [callingContact, setCallingContact] = useState<{name:string;role:string;phone:string;teams:string}|null>(null);
  const togglePin = usePanelStore((s) => s.togglePin);
  const meta = PRIORITY_META[action.priority] ?? PRIORITY_META[3];
  const locked = action.pinned;

  return (
    <div
      data-testid={`priority-action-card-${action.step}`}
      data-spotlight-id={`priority-action-${action.step}`}
      className={`border border-border ${meta.border} border-l-4 rounded-lg bg-neutral-bg2 overflow-hidden`}
    >
      {/* Priority + Pin row */}
      <div className="flex items-center justify-between px-4 pt-3 pb-1">
        <span className={`text-xs font-semibold ${meta.badge} flex items-center gap-1.5`}>
          {meta.dot && <span className="inline-block h-2 w-2 rounded-full bg-priority-critical" />}
          {meta.label}
        </span>
        <button
          onClick={() => togglePin(action.step)}
          className={`flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium transition-colors ${
            locked
              ? "text-accent bg-accent-soft"
              : "text-text-muted hover:text-text-primary hover:bg-neutral-bg3"
          }`}
          title={locked ? "Unpin" : "Pin position"}
          data-testid={`pin-action-${action.step}`}
        >
          {locked ? "Pinned" : "Pin"}
          <Pin className="h-3.5 w-3.5" style={locked ? { transform: "rotate(-45deg)" } : undefined} />
        </button>
      </div>

      {/* Hero action text — the one thing on the card that should read loud. */}
      <div className="px-4 pb-3">
        <h4 className="text-base font-semibold text-text-primary leading-snug">
          {action.action}
        </h4>
      </div>

      {/* ── GUIDE BAR — gentle grey gradient, click anywhere ── */}
      <button
        onClick={() => setShowGuide((v) => !v)}
        className="w-full px-4 py-2.5 bg-gradient-to-r from-section-gradient-from via-section-gradient-via to-transparent hover:from-section-gradient-hover transition-colors text-left flex items-center justify-between mt-2"
      >
        <span className="text-xs font-medium text-section-label flex items-center gap-2">
          <span className="text-lg leading-none text-section-indicator">{showGuide ? "▾" : "▸"}</span>
          Step-by-step guide
        </span>
        <span className="text-micro text-section-indicator">
          {showGuide ? "Collapse" : "Expand"}
        </span>
      </button>
      {showGuide && (
        <div className="px-4 py-3 prose prose-sm max-w-none text-sm prose-p:my-1 prose-li:my-0.5 prose-ol:my-1 prose-ul:my-1">
          {action.guide
            ? <MarkdownRenderer content={action.guide} />
            : <p className="text-section-empty italic text-sm">Section is empty. Operator hasn't filled it in yet.</p>
          }
        </div>
      )}

      {/* spacer between the two bars */}
      <div className="h-1" />

      {/* ── WHY THIS ACTION BAR — gentle grey gradient, click anywhere ── */}
      <button
        onClick={() => setShowWhy((v) => !v)}
        className="w-full px-4 py-2.5 bg-gradient-to-r from-section-gradient-from via-section-gradient-via to-transparent hover:from-section-gradient-hover transition-colors text-left flex items-center justify-between"
      >
        <span className="text-xs font-medium text-section-label flex items-center gap-2">
          <span className="text-lg leading-none text-section-indicator">{showWhy ? "▾" : "▸"}</span>
          Why this action
        </span>
        <span className="text-micro text-section-indicator">
          {showWhy ? "Collapse" : "Expand"}
        </span>
      </button>
      {showWhy && (
        <div className="px-4 py-3 space-y-3">
          <div className="prose prose-sm max-w-none text-sm prose-p:my-1 prose-li:my-0.5 prose-ol:my-1 prose-ul:my-1">
            {action.reasoning
              ? <MarkdownRenderer content={normalizeBullets(action.reasoning)} />
              : <p className="text-section-empty italic text-sm">Section is empty. Operator hasn't filled it in yet.</p>
            }
          </div>

          {/* spacer */}
          <div className="h-1" />

          {/* Sources bar — matching gradient style */}
          {(() => {
            const actionSources = action.sources?.filter(Boolean) ?? [];
            const allSources = actionSources.length > 0 ? actionSources : PLACEHOLDER_SOURCES.map((s) => s.href);
            if (allSources.length === 0) return null;
            return (
              <>
              <button
                onClick={() => setShowSources((v) => !v)}
                className="w-full px-3 py-2 bg-gradient-to-r from-subsection-gradient-from via-subsection-gradient-via to-transparent hover:from-subsection-gradient-hover rounded transition-colors text-left flex items-center justify-between"
              >
                <span className="text-micro font-medium text-section-label flex items-center gap-1.5">
                  <span className="text-lg leading-none text-section-indicator">{showSources ? "▾" : "▸"}</span>
                  Sources ({allSources.length})
                </span>
                <span className="text-micro text-section-indicator">
                  {showSources ? "Collapse" : "Expand"}
                </span>
              </button>
              {showSources && (
                <div className="rounded-md border border-border/70 bg-neutral-bg2 px-3 py-2">
                  <ol className="space-y-1.5 text-xs text-text-secondary list-decimal list-inside">
                    {allSources.map((url, i) => (
                      <li key={i}>
                        <a href={url} target="_blank" rel="noopener noreferrer"
                          className="inline-flex items-start gap-1.5 text-status-info hover:underline">
                          <span>{sourceLabel(url)}</span>
                          <ExternalLink className="mt-0.5 h-3 w-3 shrink-0" />
                        </a>
                      </li>
                    ))}
                  </ol>
                </div>
              )}
              </>
            );
          })()}
        </div>
      )}

      {/* ── CONTACTS BAR ── shown when action has contacts ── */}
      {Array.isArray(action.contacts) && action.contacts.length > 0 && (
        <>
          <div className="h-1" />
          <button
            onClick={() => setShowContacts((v) => !v)}
            className="w-full px-4 py-2.5 bg-gradient-to-r from-section-gradient-from via-section-gradient-via to-transparent hover:from-section-gradient-hover transition-colors text-left flex items-center justify-between"
          >
            <span className="text-xs font-medium text-section-label flex items-center gap-2">
              <span className="text-lg leading-none text-section-indicator">{showContacts ? "▾" : "▸"}</span>
              Contacts ({action.contacts.length})
            </span>
            <span className="text-micro text-section-indicator">
              {showContacts ? "Collapse" : "Expand"}
            </span>
          </button>
          {showContacts && (
            <div data-testid="action-contact-section" className="px-4 py-2 space-y-1">
              {action.contacts.map((c: any, i: number) => (
                <div key={i} className="flex items-center gap-2 px-2 py-1.5 rounded bg-neutral-bg1 text-xs">
                  <span className="font-semibold text-text-primary truncate">{c.name}</span>
                  <span className="text-text-muted truncate flex-1">{c.role}</span>
                  <span className="font-mono text-text-secondary shrink-0 text-micro">{c.phone}</span>
                  <button
                    data-testid="action-contact-call-button"
                    onClick={(e) => { e.stopPropagation(); setCallingContact(c); }}
                    className="shrink-0 p-1 rounded bg-brand/15 text-brand hover:bg-brand/25 transition-colors"
                    title={`Call ${c.name} on Teams`}
                  >
                    <Phone className="h-3 w-3" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </>
      )}

      {/* Teams call modal */}
      {callingContact && (
        <TeamsCallModal contact={callingContact} onClose={() => setCallingContact(null)} />
      )}

      {/* ── Action buttons — send to top / bottom / mark done ── */}
      <div className="flex items-center gap-2 px-4 py-2.5 bg-neutral-bg1/50 border-t border-border/30">
        <button
          onClick={onSendToTop}
          disabled={isFirst || locked}
          className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
            isFirst || locked
              ? "text-text-muted/30 cursor-default"
              : "text-text-muted hover:text-text-primary hover:bg-neutral-bg3"
          }`}
        >
          ▲ Top
        </button>
        <button
          onClick={onSendToBottom}
          disabled={isLast || locked}
          className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
            isLast || locked
              ? "text-text-muted/30 cursor-default"
              : "text-text-muted hover:text-text-primary hover:bg-neutral-bg3"
          }`}
        >
          ▼ Bottom
        </button>
        <div className="flex-1" />
        <button
          onClick={() => setDecisionIntent("declined")}
          className="flex items-center gap-1.5 px-3 py-1 rounded text-xs font-medium text-text-muted hover:text-status-error hover:bg-status-error/10 transition-colors"
          data-testid={`decline-action-${action.step}`}
        >
          <XCircle className="h-3.5 w-3.5" />
          Decline
        </button>
        <button
          onClick={() => setDecisionIntent("completed")}
          className="flex items-center gap-1.5 px-3 py-1 rounded text-xs font-medium text-text-muted hover:text-status-success hover:bg-status-success-surface transition-colors"
          data-testid={`complete-action-${action.step}`}
        >
          <Check className="h-3.5 w-3.5" />
          Complete
        </button>
      </div>
      {decisionIntent && (
        <DecisionNoteForm
          status={decisionIntent}
          isBusy={isBusy}
          onCancel={() => setDecisionIntent(null)}
          onSubmit={(note) => onDecision(decisionIntent, note)}
        />
      )}
    </div>
  );
}

/* ── Resolved Card (collapsed) ───────────────────────────────────────────── */

function ResolvedCard({ action, onUndo, isBusy }: { action: PriorityAction; onUndo: () => void; isBusy: boolean }) {
  const [expanded, setExpanded] = useState(false);
  const meta = PRIORITY_META[action.priority] ?? PRIORITY_META[3];
  const isDeclined = action.status === "declined";
  const label = isDeclined ? "Declined" : "Completed";
  const icon = isDeclined ? <XCircle className="h-4 w-4 text-status-error shrink-0" /> : <Check className="h-4 w-4 text-status-success shrink-0" />;

  if (!expanded) {
    return (
      <div
        data-testid={`priority-action-card-${action.step}`}
        className="border border-border border-l-4 border-l-priority-done rounded-lg bg-neutral-bg3 opacity-50 overflow-hidden"
      >
        <div className="flex items-center gap-3 px-4 py-2">
          {icon}
          <span className="text-sm font-semibold text-text-secondary flex-1 truncate">
            {action.action}
          </span>
          <span className="text-micro text-text-tertiary">{label}</span>
          <span className={`text-micro font-medium ${meta.badge}`}>{meta.label.split(" ")[0]}</span>
          <button
            onClick={() => setExpanded(true)}
            className="text-micro text-text-muted hover:text-text-primary transition-colors"
          >
            Expand ▸
          </button>
          <button
            onClick={onUndo}
            disabled={isBusy}
            className="inline-flex items-center gap-1 text-micro text-text-muted hover:text-status-warning transition-colors disabled:opacity-50"
            title="Undo — return to pending"
          >
            <RotateCcw className="h-3 w-3" />
            Undo
          </button>
        </div>
      </div>
    );
  }

  return (
    <div
      data-testid={`priority-action-card-${action.step}`}
      className="border border-border border-l-4 border-l-priority-done rounded-lg bg-neutral-bg3 opacity-60 overflow-hidden"
    >
      <div className="px-4 py-3 space-y-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            {icon}
            <span className="text-sm font-semibold text-text-secondary">{action.action}</span>
            <span className="text-micro text-text-tertiary uppercase font-bold">{label}</span>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={() => setExpanded(false)} className="text-micro text-text-muted hover:text-text-primary">Collapse ▾</button>
            <button onClick={onUndo} disabled={isBusy} className="text-micro text-text-muted hover:text-status-warning disabled:opacity-50">Undo</button>
          </div>
        </div>
        {action.note && (
          <p className="text-xs text-text-secondary rounded bg-neutral-bg2 px-3 py-2">
            {action.note}
          </p>
        )}
        {action.guide && (
          <div className="prose prose-sm max-w-none text-sm opacity-70">
            <MarkdownRenderer content={action.guide} />
          </div>
        )}
      </div>
    </div>
  );
}

function ActionTimeline({ actions }: { actions: PriorityAction[] }) {
  const timeline = usePanelStore((s) => s.priorityActionState.timeline);
  if (timeline.length === 0) return null;
  const actionById = new Map(actions.map((action) => [action.action_id, action.action]));
  return (
    <div data-testid="priority-action-timeline" className="border border-border rounded-lg bg-neutral-bg2 px-4 py-3 space-y-3">
      <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-text-tertiary font-bold">
        <ClipboardList className="h-3.5 w-3.5" />
        Action timeline
      </div>
      <ol className="space-y-2">
        {[...timeline].reverse().map((entry) => {
          const statusLabel = entry.status === "completed" ? "Completed" : entry.status === "declined" ? "Declined" : "Reopened";
          return (
            <li key={entry.event_id} className="rounded border border-border/60 bg-neutral-bg1 px-3 py-2 text-xs text-text-secondary">
              <div className="flex items-center justify-between gap-3">
                <span className="font-semibold text-text-primary">{statusLabel}</span>
                <time className="text-micro text-text-tertiary">{new Date(entry.created_at).toLocaleString()}</time>
              </div>
              <p className="mt-1 text-text-secondary">{entry.action_text || actionById.get(entry.action_id) || "Priority action"}</p>
              {entry.note && <p className="mt-1 text-text-tertiary">Note: {entry.note}</p>}
            </li>
          );
        })}
      </ol>
    </div>
  );
}

/* ── Panel ────────────────────────────────────────────────────────────────── */

export function PriorityActionsPanel() {
  const data = usePanelStore((s) => s.priorityActions);
  const reorderActions = usePanelStore((s) => s.reorderActions);
  const hydratePriorityActionState = usePanelStore((s) => s.hydratePriorityActionState);
  const recordLocalPriorityActionDecision = usePanelStore((s) => s.recordLocalPriorityActionDecision);
  const activeSessionId = useSessionStore((s) => s.activeSessionId);
  const placeholderEnabled = usePlaceholderStore((s) => s.enabled);
  const [busyActionId, setBusyActionId] = useState<string | null>(null);
  const [decisionError, setDecisionError] = useState<string | null>(null);

  /* ── FLIP animation state ─────────────────────────────────────────── */
  /* Stores the Y offset the card needs to travel (old position → new position). */
  const [flyStep, setFlyStep] = useState<number | null>(null);
  const [flyDistance, setFlyDistance] = useState(0);
  const flyKeyRef = useRef(0);
  const highlightTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  /* Map of action step → DOM element ref for measuring positions. */
  const cardRefs = useRef<Map<number, HTMLDivElement>>(new Map());

  /* Derive pending/done from data — fall back to placeholders when enabled. */
  const realActions = data?.actions ?? [];
  const actions = realActions.length > 0 ? realActions : (placeholderEnabled ? PLACEHOLDER_ACTIONS : []);
  const pending = actions.filter((a) => a.status === "pending");
  const resolved = actions.filter((a) => a.status !== "pending");

  /* Sync cardRefs with current pending actions — prune stale entries. */
  const activeSteps = new Set(pending.map((a) => a.step));
  for (const key of cardRefs.current.keys()) {
    if (!activeSteps.has(key)) cardRefs.current.delete(key);
  }

  /* Collect all critical (P5) and urgent (P4) pending actions. */
  const criticals = pending.filter((a) => a.priority === 5);
  const urgents = pending.filter((a) => a.priority === 4);

  /* Bring the furthest-away item of a given priority to position 1.
     FLIP animation: measure old position, reorder, then animate from old → new. */
  const bringFurthestToTop = useCallback((priority: number) => {
    const matches = pending
      .map((a, idx) => ({ ...a, _idx: idx }))
      .filter((a) => a.priority === priority && !a.pinned);
    if (matches.length === 0) return;
    const furthest = matches[matches.length - 1];
    if (furthest._idx === 0) return;

    /* FLIP step 1: measure the card's current Y position ("First"). */
    const cardEl = cardRefs.current.get(furthest.step);
    const firstCardEl = cardRefs.current.get(pending[0]?.step);
    let distance = 600; /* fallback if measurement fails */
    if (cardEl && firstCardEl) {
      const oldY = cardEl.getBoundingClientRect().top;
      const newY = firstCardEl.getBoundingClientRect().top;
      distance = oldY - newY;
    }

    const reordered = [...pending];
    const [moved] = reordered.splice(furthest._idx, 1);
    reordered.unshift(moved);
    const all = [...reordered, ...resolved].map((a, i) => ({ ...a, step: i + 1 }));

    /* Set animation state — the new step=1 card will fly from `distance` px below. */
    flyKeyRef.current += 1;
    setFlyDistance(distance);
    setFlyStep(1);
    if (highlightTimerRef.current) clearTimeout(highlightTimerRef.current);
    highlightTimerRef.current = setTimeout(() => setFlyStep(null), 3200);
    reorderActions(all);
  }, [pending, resolved, reorderActions]);

  const sendToTop = (step: number) => {
    const idx = pending.findIndex((a) => a.step === step);
    if (idx <= 0) return;
    /* Respect pins — pinned cards cannot be moved */
    if (pending[idx].pinned) return;
    const reordered = [...pending];
    const [moved] = reordered.splice(idx, 1);
    reordered.unshift(moved);
    const all = [...reordered, ...resolved].map((a, i) => ({ ...a, step: i + 1 }));
    reorderActions(all);
  };

  const sendToBottom = (step: number) => {
    const idx = pending.findIndex((a) => a.step === step);
    if (idx < 0 || idx === pending.length - 1) return;
    /* Respect pins — pinned cards cannot be moved */
    if (pending[idx].pinned) return;
    const reordered = [...pending];
    const [moved] = reordered.splice(idx, 1);
    reordered.push(moved);
    const all = [...reordered, ...resolved].map((a, i) => ({ ...a, step: i + 1 }));
    reorderActions(all);
  };

  const recordDecision = async (action: PriorityAction, status: PriorityActionStatus, note: string) => {
    setDecisionError(null);
    if (!activeSessionId || realActions.length === 0) {
      recordLocalPriorityActionDecision(action, status, note);
      return;
    }
    setBusyActionId(action.action_id);
    try {
      const state = await api.updatePriorityActionDecision(activeSessionId, action.action_id, {
        status,
        note,
        action_text: action.action,
        reasoning: action.reasoning,
        guide: action.guide,
        priority: action.priority,
      });
      hydratePriorityActionState(state);
    } catch (error) {
      setDecisionError((error as Error).message);
    } finally {
      setBusyActionId(null);
    }
  };

  /* Sub-tabs are a fixed skeleton, so the panel always renders even when
     no actions exist. The empty-state UI moves into a per-slot placeholder
     card below the sub-tab bar. This avoids a layout swap on first action
     arrival, which previously caused operators to lose scroll position. */
  const isEmpty = actions.length === 0;

  return (
    <div data-testid="priority-actions-panel" className="relative">
      <SituationSummaryCard />
      <ClassifyVerdictCard />
      {isEmpty && (
        <div className="border border-border rounded-lg p-4 bg-neutral-bg2">
          <h3 className="text-xs uppercase tracking-wider text-text-tertiary font-bold">
            Operator priorities — awaiting actions
          </h3>
          <p className="text-text-tertiary text-sm mt-2 italic">
            Ask GridIQ to investigate an event.
          </p>
        </div>
      )}

      {!isEmpty && (
      <>
      {decisionError && (
        <div className="mb-3 rounded border border-status-error/30 bg-status-error/10 px-3 py-2 text-xs text-status-error" role="alert">
          {decisionError}
        </div>
      )}
      {/* ── Sticky alert banners — follow the operator as they scroll ── */}
      {(criticals.length > 0 || urgents.length > 0) && (
        <div className="sticky top-0 z-10 space-y-1.5 pb-3 bg-center-panel-bg">
          {criticals.length > 0 && (
            <button
              onClick={() => bringFurthestToTop(5)}
              className="w-full flex items-center gap-2 px-3 py-2 rounded-md bg-priority-critical-surface text-left hover:bg-priority-critical-hover transition-colors cursor-pointer"
            >
              <span className="inline-block h-2 w-2 rounded-full bg-priority-critical" />
              <span className="text-sm font-medium text-priority-critical-text">
                {criticals.length} critical {criticals.length === 1 ? "action" : "actions"} — tap to bring to top
              </span>
            </button>
          )}
          {urgents.length > 0 && (
            <button
              onClick={() => bringFurthestToTop(4)}
              className="w-full flex items-center gap-2 px-3 py-2 rounded-md bg-priority-urgent-surface text-left hover:bg-priority-urgent-hover transition-colors cursor-pointer"
            >
              <span className="inline-block h-2 w-2 rounded-full bg-priority-urgent" />
              <span className="text-sm font-medium text-priority-urgent-text">
                {urgents.length} urgent {urgents.length === 1 ? "action" : "actions"} — tap to bring to top
              </span>
            </button>
          )}
        </div>
      )}

      {/* ── Action cards ── */}
      <div className="space-y-3">
        <h3 className="text-xs text-text-muted font-medium px-1">
          Operator priorities
        </h3>

      {pending.map((action, idx) => {
        const isFlying = action.step === flyStep;
        const highlightColor = action.priority === 5
          ? "var(--color-priority-critical-border)"
          : "var(--color-priority-urgent-border)";
        return (
          <div
            key={isFlying ? `fly-${flyKeyRef.current}` : `card-${action.step}`}
            ref={(el) => { if (el) cardRefs.current.set(action.step, el); }}
            className={`rounded-lg ${isFlying ? "animate-highlight-pulse" : ""}`}
            style={isFlying ? {
              "--highlight-color": highlightColor,
              "--fly-distance": `${flyDistance}px`,
              animation: `fly-from-origin 0.55s cubic-bezier(0.22, 1, 0.36, 1) both, highlight-pulse 0.8s ease-out 0.55s 3`,
            } as React.CSSProperties : undefined}
          >
            <PendingCard
              action={action}
              onDecision={(status, note) => void recordDecision(action, status, note)}
              onSendToTop={() => sendToTop(action.step)}
              onSendToBottom={() => sendToBottom(action.step)}
              isFirst={idx === 0}
              isLast={idx === pending.length - 1}
              isBusy={busyActionId === action.action_id}
            />
          </div>
        );
      })}

      {resolved.length > 0 && (
        <>
          <div className="flex items-center gap-2 px-1 pt-2">
            <div className="flex-1 border-t border-border/40" />
            <span className="text-micro uppercase tracking-wider text-text-tertiary font-bold">Resolved</span>
            <div className="flex-1 border-t border-border/40" />
          </div>
          {resolved.map((action) => (
            <ResolvedCard
              key={action.step}
              action={action}
              isBusy={busyActionId === action.action_id}
              onUndo={() => void recordDecision(action, "pending", "")}
            />
          ))}
        </>
      )}
      <ActionTimeline actions={actions} />
      </div>
      </>
      )}
    </div>
  );
}
