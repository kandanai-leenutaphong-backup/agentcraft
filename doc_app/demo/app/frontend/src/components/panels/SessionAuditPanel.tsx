/**
 * SessionAuditPanel — center-column "System Evaluations" tab.
 *
 * Replaces the retired scenario-runner UI. One button —
 * `Evaluate current interaction` — drives a hidden auditor agent over
 * the current chat session and streams its tool sequence + final
 * audit report into the panel. While a run is in flight the button
 * becomes `Interrupt audit`.
 *
 * Layout (top → bottom):
 *   1. Control row: button + Previous-audits dropdown.
 *   2. Sticky report header — verdict + rubric + gaps.
 *   3. Investigation stream — live tool cards + auditor narration.
 *
 * See [specs/session_audit.md](../../../../specs/session_audit.md).
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { ChevronDown, Info, Loader2, ShieldCheck, StopCircle, Activity } from "lucide-react";

import {
  AuditBand,
  AuditImprovement,
  AuditImprovementCategory,
  AuditReport,
  AuditStreamEvent,
  AuditSummary,
} from "@/api/auditApi";
import { useAuditStore, AuditStatus } from "@/stores/auditStore";
import { useSessionStore } from "@/stores/sessionStore";
import { MarkdownRenderer } from "@/components/shared/MarkdownRenderer";
import { getToolResultRenderer } from "@/components/chat/tool-renderers";

const BAND_CLASS: Record<AuditBand, string> = {
  excellent: "bg-status-success-surface text-status-success border-status-success/30",
  strong: "bg-status-success-surface text-status-success border-status-success/30",
  adequate: "bg-status-warning-surface text-status-warning border-status-warning/30",
  weak: "bg-situation-major/15 text-situation-major border-situation-major/30",
  poor: "bg-status-error-surface text-status-error border-status-error/30",
};

const STATUS_LABEL: Record<AuditStatus, string> = {
  idle: "Idle",
  running: "Running",
  completed: "Completed",
  interrupted: "Interrupted",
  error: "Error",
};

function formatRelative(iso: string | null | undefined): string {
  if (!iso) return "—";
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return iso;
  const ageSec = (Date.now() - t) / 1000;
  if (ageSec < 60) return `${Math.max(0, Math.floor(ageSec))}s ago`;
  if (ageSec < 3600) return `${Math.floor(ageSec / 60)}m ago`;
  if (ageSec < 86_400) return `${Math.floor(ageSec / 3600)}h ago`;
  return `${Math.floor(ageSec / 86_400)}d ago`;
}

function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null) return "—";
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
}

// ── Sticky report header ──────────────────────────────────────────────

const IMPROVEMENT_CHIP: Record<AuditImprovementCategory, string> = {
  prompt: "bg-tag-pattern-bg text-tag-pattern-text border-tag-pattern-text/30",
  tooling: "bg-status-info-surface text-status-info border-status-info/30",
  data: "bg-status-info-surface text-status-info border-status-info/30",
  process: "bg-status-success-surface text-status-success border-status-success/30",
  other: "bg-neutral-bg3 text-text-secondary border-border",
};

function ReportHeader({ report }: { report: AuditReport }) {
  const improvements: AuditImprovement[] = report.improvements ?? [];
  return (
    <div
      className="border-b border-border bg-neutral-bg1 px-6 py-4"
      data-testid="audit-report-header"
    >
      <div className="flex flex-wrap items-center gap-3">
        <span
          className={`rounded border px-2 py-0.5 text-label font-semibold uppercase ${BAND_CLASS[report.band]}`}
          data-testid="audit-band-chip"
        >
          {report.band}
        </span>
        <span className="text-xs text-text-muted">
          {report.weighted_score} / 21
          {" · "}
          {(report.score_pct * 100).toFixed(0)}%
          {" · "}
          {report.tool_call_count ?? 0} tool calls
          {" · "}
          {formatDuration(report.duration_seconds)}
        </span>
        <span className="text-xs text-text-muted">confidence: {report.confidence}</span>
      </div>
      <div className="mt-2 text-base font-semibold text-text-primary" data-testid="audit-headline">
        {report.headline}
      </div>

      <details className="mt-4" open>
        <summary className="cursor-pointer text-xs font-semibold uppercase tracking-wider text-text-muted">
          Report
        </summary>
        <div
          className="prose prose-invert prose-sm mt-3 max-w-none text-sm leading-relaxed text-text-primary"
          data-testid="audit-markdown"
        >
          <MarkdownRenderer content={report.markdown} />
        </div>
      </details>

      <details className="mt-4" open>
        <summary className="cursor-pointer text-xs font-semibold uppercase tracking-wider text-text-muted">
          Rubric ({report.rubric.length})
        </summary>
        <table className="mt-2 w-full text-xs">
          <thead className="text-text-muted">
            <tr>
              <th className="py-1 text-left">Dimension</th>
              <th className="py-1 text-left">Band</th>
              <th className="py-1 text-left">Score</th>
              <th className="py-1 text-left">Note</th>
            </tr>
          </thead>
          <tbody>
            {report.rubric.map((item) => (
              <tr key={item.dimension} className="border-t border-border/50 align-top">
                <td className="py-1.5 pr-2 font-mono text-text-secondary">{item.dimension}</td>
                <td className="py-1.5 pr-2">
                  <span
                    className={`rounded border px-1.5 py-0.5 text-micro font-semibold uppercase ${BAND_CLASS[item.band]}`}
                  >
                    {item.band}
                  </span>
                </td>
                <td className="py-1.5 pr-2 font-mono text-text-secondary">{item.score}</td>
                <td className="py-1.5 text-text-primary">{item.note}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>

      {report.gaps.length > 0 && (
        <details className="mt-4" open>
          <summary className="cursor-pointer text-xs font-semibold uppercase tracking-wider text-text-muted">
            Missed evidence ({report.gaps.length})
          </summary>
          <ul className="mt-2 space-y-1 text-sm text-text-primary">
            {report.gaps.map((gap, idx) => (
              <li key={idx} className="flex gap-2">
                <span className="text-text-muted">·</span>
                <span className="leading-relaxed">{gap}</span>
              </li>
            ))}
          </ul>
        </details>
      )}

      {improvements.length > 0 && (
        <details className="mt-4" open data-testid="audit-improvements">
          <summary className="cursor-pointer text-xs font-semibold uppercase tracking-wider text-text-muted">
            Suggested improvements ({improvements.length})
          </summary>
          <ul className="mt-2 space-y-2 text-sm text-text-primary">
            {improvements.map((imp, idx) => (
              <li
                key={idx}
                className="flex items-start gap-2"
                data-testid="audit-improvement-row"
              >
                <span
                  className={`mt-0.5 shrink-0 rounded border px-1.5 py-0.5 text-micro font-semibold uppercase ${
                    IMPROVEMENT_CHIP[imp.category] ?? IMPROVEMENT_CHIP.other
                  }`}
                >
                  {imp.category}
                </span>
                <span className="leading-relaxed">{imp.text}</span>
              </li>
            ))}
          </ul>
        </details>
      )}

      {report.context_prompt && (
        <details className="mt-4" data-testid="audit-context-prompt">
          <summary className="cursor-pointer text-xs font-semibold uppercase tracking-wider text-text-muted">
            Operator's prompt at time of audit
          </summary>
          <p className="mt-2 whitespace-pre-wrap text-xs text-text-secondary leading-relaxed">
            {report.context_prompt}
          </p>
        </details>
      )}
    </div>
  );
}

// ── Stream rendering ─────────────────────────────────────────────────

interface ToolCardState {
  id: string;
  name: string;
  args: Record<string, unknown>;
  result: string | null;
}

/** Project the streamEvents array into a stable list of tool cards
 *  + interleaved narration paragraphs. Pure function — easy to test. */
function projectStream(events: AuditStreamEvent[]): Array<
  | { kind: "tool"; tool: ToolCardState }
  | { kind: "narration"; text: string }
> {
  const out: Array<
    | { kind: "tool"; tool: ToolCardState }
    | { kind: "narration"; text: string }
  > = [];
  const toolById = new Map<string, ToolCardState>();
  let narrationBuffer = "";

  const flushNarration = () => {
    const text = narrationBuffer.trim();
    if (text) out.push({ kind: "narration", text });
    narrationBuffer = "";
  };

  for (const event of events) {
    switch (event.kind) {
      case "token":
        narrationBuffer += event.token;
        break;
      case "tool_call_start": {
        flushNarration();
        const card: ToolCardState = { id: event.id, name: event.name, args: {}, result: null };
        toolById.set(event.id, card);
        out.push({ kind: "tool", tool: card });
        break;
      }
      case "tool_call_end": {
        const card = toolById.get(event.id);
        if (card) card.args = event.args;
        break;
      }
      case "tool_result": {
        const card = toolById.get(event.id);
        if (card) card.result = event.result;
        break;
      }
      default:
        break;
    }
  }
  flushNarration();
  return out;
}

function ToolCard({ tool }: { tool: ToolCardState }) {
  const [expanded, setExpanded] = useState(false);
  const Renderer = getToolResultRenderer(tool.name);
  return (
    <div
      className="rounded-md border border-border bg-neutral-bg2 px-3 py-2"
      data-testid={`audit-tool-card-${tool.name}`}
    >
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center justify-between text-left"
      >
        <span className="flex items-center gap-2 text-xs font-semibold text-text-primary">
          <Activity className="h-3.5 w-3.5 text-accent" />
          {tool.name}
          {tool.result == null && (
            <Loader2 className="h-3 w-3 animate-spin text-text-muted" />
          )}
        </span>
        <ChevronDown
          className={`h-3.5 w-3.5 text-text-muted transition-transform ${expanded ? "rotate-180" : ""}`}
        />
      </button>
      {expanded && tool.result != null && (
        <div className="mt-2 border-t border-border/40 pt-2">
          <Renderer result={tool.result} />
        </div>
      )}
    </div>
  );
}

// ── Top-level panel ──────────────────────────────────────────────────

export function SessionAuditPanel() {
  const sessionId = useSessionStore((s) => s.activeSessionId);
  const status = useAuditStore((s) => s.status);
  const auditId = useAuditStore((s) => s.auditId);
  const report = useAuditStore((s) => s.report);
  const reportSource = useAuditStore((s) => s.reportSource);
  const streamEvents = useAuditStore((s) => s.streamEvents);
  const history = useAuditStore((s) => s.history);
  const error = useAuditStore((s) => s.error);
  const startAudit = useAuditStore((s) => s.startAudit);
  const interrupt = useAuditStore((s) => s.interrupt);
  const loadHistory = useAuditStore((s) => s.loadHistory);
  const loadReport = useAuditStore((s) => s.loadReport);
  const reset = useAuditStore((s) => s.reset);

  /* Reset the panel state whenever the active session id changes — the
     audit history is per-session. */
  const lastSessionRef = useRef<string | null>(null);
  useEffect(() => {
    if (lastSessionRef.current !== sessionId) {
      lastSessionRef.current = sessionId;
      reset();
      if (sessionId) {
        void loadHistory(sessionId);
      }
    }
  }, [sessionId, reset, loadHistory]);

  const projection = useMemo(() => projectStream(streamEvents), [streamEvents]);

  const isRunning = status === "running";

  const handlePrimaryClick = async () => {
    if (!sessionId) return;
    if (isRunning) {
      await interrupt(sessionId);
    } else {
      await startAudit(sessionId);
    }
  };

  return (
    <div className="flex h-full flex-col" data-testid="session-audit-panel">
      {/* Control row */}
      <div className="flex flex-wrap items-center gap-3 border-b border-border px-3 py-3">
        <button
          type="button"
          onClick={handlePrimaryClick}
          disabled={!sessionId}
          data-testid={isRunning ? "audit-interrupt-button" : "audit-start-button"}
          className={
            isRunning
              ? "inline-flex items-center gap-1.5 rounded-md bg-status-error px-3 py-1.5 text-xs font-semibold text-on-accent shadow hover:bg-status-error/80 disabled:opacity-50"
              : "inline-flex items-center gap-1.5 rounded-md bg-brand px-3 py-1.5 text-xs font-semibold text-on-accent shadow hover:bg-brand-hover disabled:cursor-not-allowed disabled:bg-brand/40 disabled:text-on-accent/70"
          }
          title={
            !sessionId
              ? "Start a chat session before evaluating it"
              : isRunning
                ? "Interrupt the audit (does not save)"
                : "Run a fresh audit on the current interaction"
          }
        >
          {isRunning ? <StopCircle className="h-3.5 w-3.5" /> : <ShieldCheck className="h-3.5 w-3.5" />}
          {isRunning ? "Interrupt audit" : "Evaluate current interaction"}
        </button>

        {!sessionId && !isRunning && (
          <span className="text-xs text-text-muted" data-testid="audit-no-session-hint">
            Start a chat to enable.
          </span>
        )}

        <PreviousAuditsDropdown
          sessionId={sessionId}
          history={history}
          activeAuditId={auditId}
          onSelect={(aid) => sessionId && loadReport(sessionId, aid)}
          disabled={isRunning || !sessionId}
        />

        <span className="text-xs text-text-muted" data-testid="audit-status-chip">
          {STATUS_LABEL[status]}
          {auditId ? ` · ${auditId.slice(0, 12)}…` : ""}
        </span>

        {error && (
          <span className="text-xs text-status-error" data-testid="audit-error">
            {error}
          </span>
        )}
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto">
        {report ? <ReportHeader report={report} /> : null}

        <div className="px-4 py-3">
          {!report && status === "idle" && (
            <div
              className="rounded-md border border-dashed border-border px-4 py-6 text-center text-sm text-text-muted"
              data-testid="audit-empty-state"
            >
              Click <span className="font-semibold text-text-primary">Evaluate current interaction</span>
              {" "}to run a session audit.
            </div>
          )}

          {reportSource === "history" && status !== "running" && (
            <div
              className="mb-3 rounded-md border border-border bg-neutral-bg2 px-3 py-2 text-xs text-text-muted"
              data-testid="audit-stream-not-retained"
            >
              Stream not retained for saved audits — load a fresh audit to see the live tool sequence.
            </div>
          )}

          {(status === "running" || reportSource === "live") && projection.length > 0 && (
            <div className="space-y-2" data-testid="audit-stream">
              {projection.map((entry, idx) =>
                entry.kind === "tool" ? (
                  <ToolCard key={`${entry.tool.id}-${idx}`} tool={entry.tool} />
                ) : (
                  <p
                    key={`narr-${idx}`}
                    className="text-xs italic text-text-secondary"
                    data-testid="audit-narration"
                  >
                    {entry.text}
                  </p>
                ),
              )}
            </div>
          )}

          {status === "running" && projection.length === 0 && (
            <div className="flex items-center gap-2 text-xs text-text-muted">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              Auditor is starting up…
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Previous-audits dropdown ─────────────────────────────────────────

interface DropdownProps {
  sessionId: string | null;
  history: AuditSummary[];
  activeAuditId: string | null;
  onSelect: (auditId: string) => void;
  disabled: boolean;
}

function PreviousAuditsDropdown({ sessionId, history, activeAuditId, onSelect, disabled }: DropdownProps) {
  const [open, setOpen] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onDocClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    if (open) document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, [open]);

  if (!sessionId) return null;

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        disabled={disabled || history.length === 0}
        data-testid="audit-history-button"
        className="inline-flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1.5 text-xs text-text-secondary hover:text-text-primary disabled:cursor-not-allowed disabled:opacity-40"
      >
        Previous audits
        {history.length > 0 && (
          <span className="rounded bg-brand/15 px-1.5 py-0.5 text-micro font-semibold text-brand">
            {history.length}
          </span>
        )}
        <ChevronDown className="h-3 w-3" />
      </button>
      {open && history.length > 0 && (
        <div
          className="absolute left-0 top-full z-30 mt-1 w-96 overflow-hidden rounded-md border border-border bg-neutral-bg1 shadow-lg"
          data-testid="audit-history-menu"
        >
          {history.map((audit) => {
            const active = audit.id === activeAuditId;
            const band = (audit.band ?? "weak") as AuditBand;
            const isExpanded = expandedId === audit.id;
            const hasContext = Boolean(audit.context_prompt && audit.context_prompt.trim());
            return (
              <div
                key={audit.id}
                className={`border-b border-border/40 last:border-0 ${active ? "bg-brand/10" : ""}`}
                data-testid={`audit-history-row-${audit.id}`}
              >
                <div className="flex items-stretch">
                  <button
                    type="button"
                    onClick={() => {
                      setOpen(false);
                      onSelect(audit.id);
                    }}
                    className="min-w-0 flex-1 px-3 py-2 text-left hover:bg-neutral-bg2"
                  >
                    <div className="flex items-center gap-2">
                      <span
                        className={`rounded border px-1.5 py-0.5 text-micro font-semibold uppercase ${BAND_CLASS[band]}`}
                      >
                        {audit.band ?? "—"}
                      </span>
                      <span className="text-label text-text-muted">{formatRelative(audit.started_at)}</span>
                      <span className="text-label text-text-muted">
                        {audit.weighted_score ?? "?"} / 21
                      </span>
                    </div>
                    <div className="mt-1 truncate text-xs text-text-primary">
                      {audit.headline ?? audit.id}
                    </div>
                  </button>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      setExpandedId(isExpanded ? null : audit.id);
                    }}
                    disabled={!hasContext}
                    className="shrink-0 border-l border-border/40 px-2.5 text-text-muted hover:bg-neutral-bg2 hover:text-text-primary disabled:cursor-not-allowed disabled:opacity-40"
                    title={hasContext ? "Show context — what was being audited" : "No context recorded for this audit"}
                    data-testid={`audit-history-context-toggle-${audit.id}`}
                  >
                    <Info className="h-3.5 w-3.5" />
                  </button>
                </div>
                {isExpanded && hasContext && (
                  <div
                    className="border-t border-border/40 bg-neutral-bg2 px-3 py-2"
                    data-testid={`audit-history-context-${audit.id}`}
                  >
                    <div className="text-micro font-semibold uppercase tracking-wider text-text-tertiary">
                      Operator's prompt at audit time
                    </div>
                    <p className="mt-1 whitespace-pre-wrap text-xs text-text-secondary leading-relaxed">
                      {audit.context_prompt}
                    </p>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
