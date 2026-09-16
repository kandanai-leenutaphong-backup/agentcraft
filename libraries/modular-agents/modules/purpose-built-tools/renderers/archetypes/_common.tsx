/**
 * Shared props and bounded states for the archetype renderers.
 *
 * THE FOUR STATES EVERY RENDERER RESOLVES TO
 * ------------------------------------------
 * happy, empty, envelope-state (error / refusal / duplicate), or unresolved.
 * There is no fifth, and in particular there is no raw-JSON dump: a
 * production transcript that falls back to pretty-printed JSON has given up
 * on the reader, and the fallback is invisible in review because it still
 * "renders".
 *
 * `ArchetypeUnresolved` is the honest version — a bounded card that names the
 * archetype it failed to match and shows a capped preview. Loud enough to
 * notice, small enough not to flood the transcript.
 */

import type { ReactElement } from "react";
import { ToolResultCard } from "../ToolResultCard";
import { extractDuplicate, extractError, extractRefusal } from "../helpers";

/** Props shared by every archetype renderer. */
export interface ArchetypeRendererProps {
  /** The raw tool result string. */
  result: string;
  /** Tool name, threaded so a renderer can resolve per-tool hints. */
  toolName?: string;
  /** Which columns are the signal, for the table archetypes. */
  prominentColumns?: string[];
  /** Stable id the reader's chosen card height is remembered against. */
  resizeKey?: string;
}

const PREVIEW_CAP = 180;

/**
 * Render the envelope state, or null when the payload is a normal result.
 *
 * Called by every archetype before it inspects the shape, so error, refusal
 * and duplicate are handled identically everywhere. Handling them per
 * renderer is how one of them ends up rendering a refusal as an error, and a
 * working guardrail starts looking like a fault (GOTCHAS.md G13).
 */
export function renderEnvelopeState(
  parsed: Record<string, unknown> | null,
): ReactElement | null {
  const refusal = extractRefusal(parsed);
  if (refusal) return <ToolResultCard refusal={refusal} />;

  const duplicate = extractDuplicate(parsed);
  if (duplicate) return <ToolResultCard duplicate={duplicate} />;

  const error = extractError(parsed);
  if (error) return <ToolResultCard error={{ detail: error }} />;

  return null;
}

/** Shape mismatch: name the archetype, cap the preview, never dump. */
export function ArchetypeUnresolved({
  archetype,
  result,
}: {
  archetype: string;
  result: string;
}) {
  const preview = result.length > PREVIEW_CAP ? `${result.slice(0, PREVIEW_CAP)}…` : result;
  return (
    <ToolResultCard note={`Result did not match the "${archetype}" shape.`} noteTone="warning">
      <pre
        data-testid="archetype-unresolved"
        data-archetype={archetype}
        className="max-h-40 overflow-auto whitespace-pre-wrap rounded bg-neutral-bg3 px-2 py-1 font-mono text-micro text-text-muted"
      >
        {preview}
      </pre>
    </ToolResultCard>
  );
}

/**
 * A definite nothing. Carries a zero chip and the scope badges, so the reader
 * can see the question was asked — which is what stops the caller repeating
 * the call to find out (GOTCHAS.md G10).
 */
export function ArchetypeEmpty({
  label,
  message,
  scope,
}: {
  label: string;
  message: string;
  scope?: { label: string; value: string }[];
}) {
  return (
    <ToolResultCard scope={scope} signal={[{ label, value: 0, tone: "neutral" }]}>
      <div className="py-1 text-xs italic text-text-muted">{message}</div>
    </ToolResultCard>
  );
}
