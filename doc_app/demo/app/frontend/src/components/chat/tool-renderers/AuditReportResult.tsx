/**
 * AuditReportResult — compact inline summary for `submit_audit_report`,
 * inside the ToolResultCard scaffold.
 *
 * Signal band: status + band + score% + confidence. Body: headline +
 * rubric/gap/improvement chip row + pointer to the full report panel.
 * Error envelopes from the auditor short-circuit to the red banner.
 */

import type { ToolResultProps } from "./index";
import { JsonFallback } from "./JsonFallback";
import { ToolResultCard, type SignalTone } from "./ToolResultCard";
import { extractError, parseToolResult } from "./helpers";

/* Band → tone class for the band chip inside the body. */
const BAND_TONE: Record<string, string> = {
  excellent: "bg-status-success/15 text-status-success border-status-success/30",
  good: "bg-accent/15 text-accent border-accent/30",
  fair: "bg-status-warning/15 text-status-warning border-status-warning/30",
  poor: "bg-status-error/15 text-status-error border-status-error/30",
};

const BAND_SIGNAL_TONE: Record<string, SignalTone> = {
  excellent: "success",
  good: "accent",
  fair: "warning",
  poor: "error",
};

export function AuditReportResult({ result }: ToolResultProps) {
  const parsed = parseToolResult(result);
  if (!parsed) return <JsonFallback result={result} />;

  const errDetail = extractError(parsed);
  if (errDetail) return <ToolResultCard error={{ detail: errDetail }} />;

  const status = typeof parsed.status === "string" ? parsed.status : "submitted";
  const headline = typeof parsed.headline === "string" ? parsed.headline : null;
  const band = typeof parsed.band === "string" ? parsed.band : null;
  const scorePct = typeof parsed.score_pct === "number" ? parsed.score_pct : null;
  const confidence = typeof parsed.confidence === "number" ? parsed.confidence : null;
  const rubricCount = typeof parsed.rubric_count === "number" ? parsed.rubric_count : null;
  const gapCount = typeof parsed.gap_count === "number" ? parsed.gap_count : null;
  const improvementCount =
    typeof parsed.improvement_count === "number" ? parsed.improvement_count : null;

  if (headline === null && band === null && scorePct === null) {
    return <JsonFallback result={result} />;
  }

  const bandLower = band?.toLowerCase();
  const signalChips: { label: string; value: string | number; tone?: SignalTone }[] = [
    { label: "status", value: status, tone: "success" },
  ];
  if (band) {
    signalChips.push({
      label: "band",
      value: band,
      tone: bandLower ? BAND_SIGNAL_TONE[bandLower] ?? "warning" : "warning",
    });
  }
  if (scorePct !== null) {
    signalChips.push({ label: "score", value: `${Math.round(scorePct * 100)}%`, tone: "neutral" });
  }
  if (confidence !== null) {
    signalChips.push({ label: "conf", value: `${Math.round(confidence * 100)}%`, tone: "neutral" });
  }

  return (
    <ToolResultCard signal={signalChips}>
      {headline && (
        <div className="text-text-primary font-medium leading-snug">{headline}</div>
      )}
      {(rubricCount !== null || gapCount !== null || improvementCount !== null) && (
        <div className="mt-2 flex flex-wrap items-center gap-1.5 text-xs">
          {rubricCount !== null && (
            <span className="rounded bg-accent/10 text-accent px-1.5 py-0.5 font-mono">
              rubric: {rubricCount}
            </span>
          )}
          {gapCount !== null && (
            <span className="rounded bg-status-warning/10 text-status-warning px-1.5 py-0.5 font-mono">
              gaps: {gapCount}
            </span>
          )}
          {improvementCount !== null && (
            <span className="rounded bg-status-success/10 text-status-success px-1.5 py-0.5 font-mono">
              improvements: {improvementCount}
            </span>
          )}
        </div>
      )}
      <div className="mt-2 text-label text-text-muted">
        Full report available in the System Evaluations panel.
      </div>
      {/* Hidden band keyword retained for any consumer style hook on
          the body region — kept in a non-rendered comment so the band
          colour scale (`BAND_TONE`) does not become dead code. */}
      {bandLower && BAND_TONE[bandLower] ? <span hidden data-band-tone={BAND_TONE[bandLower]} /> : null}
    </ToolResultCard>
  );
}
