/**
 * ToolResultCard — the scaffold every tool result renders inside.
 *
 * WHY THIS EXISTS
 * ---------------
 * Left to itself, each new tool gets a bespoke card, and after a dozen the
 * transcript is a scrapbook: different corner radii, different type scales,
 * different places to look for "what did this run against". The operator
 * relearns the layout per tool.
 *
 * One scaffold, four default bands:
 *
 *   1. scope   — what the tool ran against
 *   2. signal  — the headline number or state
 *   3. note    — a contextual banner
 *   4. body    — the detail (table, cards, prose)
 *
 * Plus three single-purpose modes that replace the card entirely, because
 * each is a complete answer on its own:
 *
 *   error     — red. The tool could not answer.
 *   refusal   — amber. The input was rejected, and here is what would work.
 *   duplicate — muted. The answer is already above in the transcript.
 *
 * Distinguishing those three visually is the whole point. Collapsing them
 * into one red banner tells an operator that a working guardrail is a fault
 * (GOTCHAS.md G13).
 *
 * Hosts may supply identity, labeled bands and note ordering without owning
 * another scaffold. Domain labels and signal calculations remain with the host.
 *
 * THE BODY IS RESIZABLE BY DEFAULT
 * -------------------------------
 * A fixed-height card is a guess about how much of the answer the reader
 * wants. Sometimes the guess is wrong in a way that matters — a table with
 * forty rows, a document worth reading, a graph worth studying — and the
 * reader has no recourse but to scroll a box the size of a postcard.
 *
 * The body carries a native resize handle. It costs no dependency, it is
 * keyboard- and pointer-accessible for free, and it is *remembered*: a card
 * that snaps back to its default the moment you scroll away has not been
 * resized, it has been argued with.
 */

import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";

/**
 * Tells a renderer inside the body that the card governs the height.
 *
 * Without it, an inner component keeps its own max-height cap and dragging the
 * card taller reveals empty space instead of more rows — the handle appears
 * broken, which is worse than not having one.
 */
export const CardBodyContext = createContext<{ resizable: boolean }>({ resizable: false });

/** True when the surrounding card body owns the height. */
export function useCardBody() {
  return useContext(CardBodyContext);
}

/** Smallest useful body. Below this a card is a scrollbar with a hint of content. */
const MIN_BODY_HEIGHT = 96;

export type SignalTone = "neutral" | "accent" | "success" | "warning" | "error";
export type NoteTone = "info" | "warning" | "error";

export interface ScopeBadge {
  label: string;
  value: string;
}

export interface SignalChip {
  label: string;
  value: string | number;
  tone?: SignalTone;
}

export interface ToolResultCardProps {
  header?: ReactNode;
  className?: string;
  bandLabels?: { scope: string; result: string };
  scopeLabel?: string;
  signalLabel?: string;
  notePosition?: "before-signal" | "after-signal";
  resizable?: boolean;
  classNames?: { scope?: string; signal?: string; note?: string; body?: string };
  /** What the tool ran against, as `label: value` badges. */
  scope?: ScopeBadge[];
  /** The headline of the answer, as chips. */
  signal?: SignalChip[];
  /** A contextual banner below the signal band. */
  note?: string | null;
  noteTone?: NoteTone;
  /** Failure envelope. Replaces the whole card with a red banner. */
  error?: { detail: string } | null;
  /** Refusal envelope. Replaces the whole card with an amber banner. */
  refusal?: { parameter: string; problem: string; accepted: string } | null;
  /** Duplicate-call notice. Replaces the whole card with a muted banner. */
  duplicate?: { tool: string; detail: string } | null;
  /**
   * Accessible name for the region. Omitted by default so a transcript of
   * twenty cards does not announce twenty boilerplate labels; the error
   * variant announces regardless, via `role="alert"`.
   */
  ariaLabel?: string;
  children?: ReactNode;
  /** Stable id this card's height is remembered against. Omit to forget it. */
  resizeKey?: string;
}

const SIGNAL_TONE_CLASS: Record<SignalTone, string> = {
  neutral: "bg-neutral-bg3 text-text-secondary",
  accent: "bg-accent/10 text-accent",
  success: "bg-status-success/10 text-status-success",
  warning: "bg-status-warning/10 text-status-warning",
  error: "bg-status-error/10 text-status-error",
};

const NOTE_TONE_CLASS: Record<NoteTone, string> = {
  info: "bg-accent/10 text-accent",
  warning: "bg-status-warning/10 text-status-warning",
  error: "bg-status-error/10 text-status-error",
};

const BANNER_LABEL = "font-semibold uppercase tracking-wider text-label";

export function ToolResultCard({
  scope,
  signal,
  note,
  noteTone = "warning",
  error,
  refusal,
  duplicate,
  ariaLabel,
  children,
  resizeKey,
  header,
  className = "",
  bandLabels,
  scopeLabel,
  signalLabel,
  notePosition = "after-signal",
  resizable = true,
  classNames = {},
}: ToolResultCardProps) {
  /* Failure: announced immediately, so an operator is not left hunting for
     a red block halfway down a long transcript. */
  if (error) {
    return (
      <section
        data-tool-card="error"
        role="alert"
        aria-label={ariaLabel}
        className={`tool-result-card rounded-lg border border-status-error/30 bg-status-error/10 px-3 py-2 text-xs text-status-error ${className}`}
      >
        {header}
        <div className={BANNER_LABEL}>error</div>
        <div className="mt-1 text-text-secondary">{error.detail}</div>
      </section>
    );
  }

  /* Refusal: amber, not red. The guardrail worked, and the banner leads with
     what would be accepted because that is the actionable half. */
  if (refusal) {
    return (
      <section
        data-tool-card="refused"
        aria-label={ariaLabel}
        className={`tool-result-card rounded-lg border border-status-warning/30 bg-status-warning/10 px-3 py-2 text-xs text-status-warning ${className}`}
      >
        {header}
        <div className={BANNER_LABEL}>
          refused · {refusal.parameter}
        </div>
        <div className="mt-1 text-text-secondary">{refusal.problem}</div>
        {refusal.accepted && (
          <div className="mt-1 text-text-muted">Accepts {refusal.accepted}</div>
        )}
      </section>
    );
  }

  /* Duplicate: muted. Nothing failed and nothing needs doing. */
  if (duplicate) {
    return (
      <section
        data-tool-card="duplicate"
        aria-label={ariaLabel}
        className={`tool-result-card rounded-lg border border-border bg-neutral-bg2 px-3 py-2 text-xs text-text-muted ${className}`}
      >
        {header}
        <div className={BANNER_LABEL}>repeat call</div>
        <div className="mt-1 text-text-secondary">{duplicate.detail}</div>
      </section>
    );
  }

  const hasScope = !!scope && scope.length > 0;
  const hasSignal = !!signal && signal.length > 0;
  const hasNote = typeof note === "string" && note.length > 0;
  const noteBand = hasNote ? (
    <div data-card-note={noteTone} role="note" className={`mb-2 rounded px-2 py-1 text-label ${NOTE_TONE_CLASS[noteTone]} ${classNames.note ?? ""}`}>
      {note}
    </div>
  ) : null;
  const resultBand = (
    <>
      {bandLabels && <span data-card-band-label>{bandLabels.result}</span>}
      {hasSignal && (
        <ul data-card-signal aria-label={signalLabel} className={`mb-2 flex flex-wrap items-center gap-1 ${classNames.signal ?? ""}`} style={{ listStyle: "none", padding: 0 }}>
          {signal!.map((chip, index) => (
            <li
              key={`${chip.label}-${index}`}
              data-card-tone={chip.tone ?? "accent"}
              className={`rounded px-1.5 py-0.5 font-mono text-label ${SIGNAL_TONE_CLASS[chip.tone ?? "accent"]}`}
            >
              {bandLabels ? <><b>{chip.value}</b><span>{chip.label}</span></> : <>{chip.label}: {chip.value}</>}
            </li>
          ))}
        </ul>
      )}
      {notePosition === "after-signal" && noteBand}
      {children !== undefined && children !== null && (
        resizable ? <CardBody storageKey={resizeKey} className={classNames.body}>{children}</CardBody> : (
          <CardBodyContext.Provider value={{ resizable: false }}>
            <div data-testid="card-body" className={classNames.body}>{children}</div>
          </CardBodyContext.Provider>
        )
      )}
    </>
  );

  return (
    <section
      data-tool-card="ok"
      aria-label={ariaLabel}
      data-card-layout={bandLabels ? "bands" : undefined}
      className={`tool-result-card rounded-lg border border-border bg-neutral-bg1 p-2 text-xs ${className}`}
    >
      {header}
      {hasScope && (
        <div data-card-band={bandLabels ? "scope" : undefined}>
          {bandLabels && <span data-card-band-label>{bandLabels.scope}</span>}
          <dl data-card-scope aria-label={scopeLabel} className={`mb-2 flex flex-wrap items-center gap-1.5 ${classNames.scope ?? ""}`}>
            {scope!.map((badge, index) => (
              <div key={`${badge.label}-${index}`} className="rounded bg-neutral-bg3 px-1.5 py-0.5 font-mono text-text-secondary">
                <dt className="text-text-muted" style={{ display: "inline" }}>{badge.label}{bandLabels ? "" : ":"}</dt>{" "}
                <dd style={{ display: "inline", margin: 0 }}>{badge.value}</dd>
              </div>
            ))}
          </dl>
        </div>
      )}
      {notePosition === "before-signal" && noteBand}
      {bandLabels ? <div data-card-band="result">{resultBand}</div> : resultBand}
    </section>
  );
}

/**
 * The resizable body region.
 *
 * Native CSS resize rather than a drag implementation: it is one line, it is
 * accessible without any work, and a hand-rolled splitter here would be a
 * hundred lines that behave slightly worse.
 */
function CardBody({ storageKey, children, className }: { storageKey?: string; children: ReactNode; className?: string }) {
  const ref = useRef<HTMLDivElement | null>(null);
  const [height, setHeight] = useState<number | null>(null);

  // Restore a remembered height before paint, so a resized card does not flash
  // at its default size on every re-render.
  useEffect(() => {
    if (!storageKey) return;
    const saved = Number(window.localStorage.getItem(`cardh:${storageKey}`) || 0);
    if (saved >= MIN_BODY_HEIGHT) setHeight(saved);
  }, [storageKey]);

  // Native resize fires no event, so the size is observed rather than listened
  // for. Cheap: one observer per card, and only while the card is mounted.
  useEffect(() => {
    const node = ref.current;
    if (!node || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => {
      const next = node.style.height ? parseInt(node.style.height, 10) : 0;
      if (!next) return;
      // Promote the browser's inline height into state: until it is state, the
      // default max-height is still applied and clamps the drag at its own
      // ceiling — the handle moves and the card refuses to grow.
      setHeight((current) => (current === next ? current : next));
      if (storageKey) window.localStorage.setItem(`cardh:${storageKey}`, String(next));
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, [storageKey]);

  return (
    <CardBodyContext.Provider value={{ resizable: true }}>
      <div
        ref={ref}
        data-testid="card-body"
        className={className}
        style={{
          resize: "vertical",
          overflow: "auto",
          display: "flex",
          flexDirection: "column",
          minHeight: MIN_BODY_HEIGHT,
          ...(height ? { height } : { maxHeight: 320 }),
        }}
      >
        {children}
      </div>
    </CardBodyContext.Provider>
  );
}
