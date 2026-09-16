import type { NodeStatus } from "./wire";
import {
  TONE_CLASS,
  isRetryable,
  statusLabel,
  statusMeaning,
  statusRemedy,
  statusTone,
} from "./status";

/**
 * A status, in words, with what it means and who fixes it.
 *
 * ADAPTED from `resource_explorer/frontend/src/components/StatusNote.tsx`. See
 * PROVENANCE.md. Tailwind utility strings are replaced by one scoped class per
 * tone; the retry affordance is new, and is offered only where retrying could
 * plausibly change the answer.
 *
 * Colour never carries the diagnosis on its own: `forbidden` and `unavailable`
 * share a tone and are told apart by their text.
 */

export function StatusBadge({ status }: { status: NodeStatus }) {
  return (
    <span className={`inv-badge ${TONE_CLASS[statusTone(status)]}`}>
      {statusLabel(status)}
    </span>
  );
}

export interface StatusNoteProps {
  status: NodeStatus;
  cause?: string | null;
  onRetry?: () => void;
  retrying?: boolean;
}

export function StatusNote({ status, cause, onRetry, retrying = false }: StatusNoteProps) {
  const remedy = statusRemedy(status);
  const canRetry = onRetry !== undefined && isRetryable(status) && status !== "ok";
  return (
    <div className={`inv-note ${TONE_CLASS[statusTone(status)]}`} role="status">
      <div className="inv-note-head">
        <StatusBadge status={status} />
        <b>{statusMeaning(status)}</b>
      </div>
      {cause ? <p className="inv-note-cause">{cause}</p> : null}
      {remedy ? <p className="inv-note-remedy">{remedy}</p> : null}
      {canRetry ? (
        <button type="button" className="inv-retry" onClick={onRetry} disabled={retrying}>
          {retrying ? "Retrying…" : "Retry"}
        </button>
      ) : null}
    </div>
  );
}
