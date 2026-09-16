/**
 * ActionRenderer — a proposed or executed action, and whether it was real.
 *
 * The one thing this archetype exists to make impossible: a simulated action
 * reading as a performed one. When the envelope flags `simulated`, the card
 * says so in a warning banner. Anything a reviewer could mistake for a live
 * side effect has to announce itself, every time, in the same place.
 */

import { ToolResultCard, type SignalTone } from "../ToolResultCard";
import { parseToolResult, scopeBadges } from "../helpers";
import {
  ArchetypeUnresolved,
  renderEnvelopeState,
  type ArchetypeRendererProps,
} from "./_common";

const PROSE_FIELDS = ["recommendation", "rationale", "detail"] as const;

export function ActionRenderer({ resizeKey, result }: ArchetypeRendererProps) {
  const parsed = parseToolResult(result);
  if (!parsed) return <ArchetypeUnresolved archetype="action" result={result} />;

  const envelopeState = renderEnvelopeState(parsed);
  if (envelopeState) return envelopeState;

  const action = typeof parsed.action === "string" ? parsed.action : null;
  const status = typeof parsed.status === "string" ? parsed.status : null;
  if (!action && !status) return <ArchetypeUnresolved archetype="action" result={result} />;

  const signal: { label: string; value: string; tone?: SignalTone }[] = [];
  if (action) signal.push({ label: "action", value: action, tone: "accent" });
  if (status) {
    signal.push({
      label: "status",
      value: status,
      tone: status === "error" ? "error" : "success",
    });
  }

  const simulated = parsed.simulated === true;
  const note = simulated
    ? "Simulated action — no live side effect was performed."
    : typeof parsed.note === "string"
      ? parsed.note
      : null;

  const lines = PROSE_FIELDS.map((field) =>
    typeof parsed[field] === "string" ? (parsed[field] as string) : null,
  ).filter((line): line is string => line !== null);

  return (
    <ToolResultCard
      resizeKey={resizeKey}
      scope={scopeBadges(parsed)}
      signal={signal}
      note={note}
      noteTone={simulated ? "warning" : "info"}
    >
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
