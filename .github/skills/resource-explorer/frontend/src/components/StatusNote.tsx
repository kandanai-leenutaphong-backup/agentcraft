/**
 * The two shapes every state on this surface is drawn with: a badge for a word
 * beside a label, and a note for a diagnosis that needs a sentence.
 *
 * A note never says only "empty". It names the status, what it means, what the
 * server reported, and who can fix it — the difference between a forbidden
 * branch and an unreachable one is the whole value of the reading.
 */

import type { JSX, ReactNode } from "react";

import {
  statusLabel,
  statusMeaning,
  statusRemedy,
  statusTone,
  TONE_BADGE,
  TONE_PANEL,
  TONE_TEXT,
  type Tone,
} from "../api/status";
import type { NodeStatus } from "../api/wire";

export function Badge({
  tone,
  children,
  testId,
}: {
  tone: Tone;
  children: ReactNode;
  testId?: string;
}): JSX.Element {
  return (
    <span
      {...(testId === undefined ? {} : { "data-testid": testId })}
      className={`shrink-0 whitespace-nowrap rounded border px-1.5 py-px text-[11px] font-medium leading-4 ${TONE_BADGE[tone]}`}
    >
      {children}
    </span>
  );
}

export function StatusBadge({ status }: { status: NodeStatus }): JSX.Element {
  return (
    <Badge tone={statusTone(status)} testId="status-badge">
      {statusLabel(status)}
    </Badge>
  );
}

export interface StatusNoteProps {
  status: NodeStatus;
  error: string | null;
  /** What the reader was trying to do — "expand this branch", "read these contents". */
  action: string;
  testId?: string;
}

export function StatusNote({
  status,
  error,
  action,
  testId,
}: StatusNoteProps): JSX.Element {
  const tone = statusTone(status);
  return (
    <div
      {...(testId === undefined ? {} : { "data-testid": testId })}
      data-status={status}
      className={`rounded border-l-2 border-y border-r px-3 py-2 ${TONE_PANEL[tone]}`}
    >
      <p className={`text-sm font-semibold ${TONE_TEXT[tone]}`}>
        {statusLabel(status)} — could not {action}
      </p>
      <p className="mt-1 text-sm text-secondary">{statusMeaning(status)}</p>
      {error === null ? null : (
        <p
          data-testid="status-cause"
          className="mt-1 break-words font-mono text-xs text-primary"
        >
          {error}
        </p>
      )}
      <p className="mt-1 text-xs text-muted">{statusRemedy(status)}</p>
    </div>
  );
}

/** A branch that answered and holds nothing. Not a failure, and it says so. */
export function EmptyNote({ what }: { what: string }): JSX.Element {
  return (
    <p
      data-testid="empty-note"
      className="rounded border border-border-soft bg-canvas2 px-3 py-2 text-sm text-secondary"
    >
      {what} The call succeeded — this is a true answer, not a failure.
    </p>
  );
}

export function TruncationNote({ children }: { children: ReactNode }): JSX.Element {
  return (
    <p
      data-testid="truncation-note"
      className="rounded border border-warning bg-warning-tint px-3 py-2 text-sm text-warning"
    >
      {children}
    </p>
  );
}
