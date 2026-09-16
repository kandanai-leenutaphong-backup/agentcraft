/**
 * StatusRenderer — a confirmation, led by its state.
 *
 * For tools that did something rather than returned something. The status
 * chip carries the whole answer; any prose the backend included follows.
 */

import { ToolResultCard, type SignalTone } from "../ToolResultCard";
import { parseToolResult, scopeBadges } from "../helpers";
import {
  ArchetypeUnresolved,
  renderEnvelopeState,
  type ArchetypeRendererProps,
} from "./_common";

const PROSE_FIELDS = ["message", "detail", "summary", "action"] as const;

export function StatusRenderer({ resizeKey, result }: ArchetypeRendererProps) {
  const parsed = parseToolResult(result);
  if (!parsed) return <ArchetypeUnresolved archetype="status" result={result} />;

  const envelopeState = renderEnvelopeState(parsed);
  if (envelopeState) return envelopeState;

  const status = typeof parsed.status === "string" ? parsed.status : "complete";
  const tone: SignalTone = status === "error" ? "error" : "success";

  const lines = PROSE_FIELDS.map((field) =>
    typeof parsed[field] === "string" ? (parsed[field] as string) : null,
  ).filter((line): line is string => line !== null);

  return (
    <ToolResultCard resizeKey={resizeKey} scope={scopeBadges(parsed)} signal={[{ label: "status", value: status, tone }]}>
      {lines.length > 0 && (
        <div className="space-y-1">
          {lines.map((line, index) => (
            <div key={index} className="text-xs text-text-secondary">
              {line}
            </div>
          ))}
        </div>
      )}
    </ToolResultCard>
  );
}
