/**
 * SignalEvidenceDisclosure — click-to-expand panel rendered beneath an
 * alarm signal, SCADA signal, or pattern chip on `SituationCard`.
 *
 * Surfaces the rule the backend used to count the signal + the actual
 * rows that matched it, cap-limited per
 * `tools/situations/detector/layers/signal_evidence.py` (default 10).
 *
 * Operator brief 2026-05-25: "I see Alarm Signals unreas=2 but no rows;
 * if I click the chip, show me which two rows fired." Wire shape lives
 * in [specs/signal_evidence_2026-05-24_proposal.md].
 */

import type {
  AlarmSignalEvidence,
  PatternEvidence,
  ScadaSignalEvidence,
} from "@/api/situationApi";

interface AlarmDisclosureProps {
  signalId: string;
  evidence: AlarmSignalEvidence;
}

interface ScadaDisclosureProps {
  signalId: string;
  evidence: ScadaSignalEvidence;
}

interface PatternDisclosureProps {
  patternId: string;
  evidence: PatternEvidence;
}

/** Render an alarm-rule sentence: e.g. `alarm_label == "UNREAS" → +1 pt`. */
function formatAlarmRule(rule: AlarmSignalEvidence["rule"]): string {
  const op = rule.op === "==" ? "==" : "contains";
  const main = `${rule.col} ${op} "${rule.val}"`;
  const extra = rule.extra_col
    ? ` AND ${rule.extra_col} ${rule.extra_op ?? "contains"} "${rule.extra_val}"`
    : "";
  const minCount = rule.min_count ? ` (min ${rule.min_count})` : "";
  return `${main}${extra} → +${rule.points} pt${minCount}`;
}

/** Render a SCADA-rule sentence: e.g.
 *  `TagId contains [".GEN.", ".UNIT."] · MW · drops_to_near_zero (threshold 1, baseline 5) → +3 pt`. */
function formatScadaRule(rule: ScadaSignalEvidence["rule"]): string {
  const tags = rule.tag_contains.map((t) => `"${t}"`).join(", ");
  const parts = [`tag in [${tags}]`, rule.meas, rule.cond_type];
  const args: string[] = [];
  if (rule.threshold !== undefined) args.push(`threshold ${rule.threshold}`);
  if (rule.baseline !== undefined) args.push(`baseline ${rule.baseline}`);
  if (rule.direction && rule.direction !== "any") args.push(`direction ${rule.direction}`);
  if (args.length > 0) parts.push(`(${args.join(", ")})`);
  return `${parts.join(" · ")} → +${rule.points} pt`;
}

export function AlarmSignalDisclosure({ signalId, evidence }: AlarmDisclosureProps) {
  const { rule, rows, count } = evidence;
  return (
    <div
      data-testid={`signal-evidence-alarm-${signalId}`}
      className="mt-1 ml-1 rounded border border-tag-alarm-text/30 bg-tag-alarm-bg/30 p-1.5 space-y-1"
    >
      <div className="text-micro text-text-muted font-mono">{formatAlarmRule(rule)}</div>
      {rows.length === 0 ? (
        <div className="text-micro italic text-text-muted">No matching rows captured.</div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-micro">
            <thead className="text-text-muted uppercase tracking-wider">
              <tr>
                <th className="px-1 py-0.5 text-left font-semibold">Time</th>
                <th className="px-1 py-0.5 text-left font-semibold">Equipment</th>
                <th className="px-1 py-0.5 text-left font-semibold">Label</th>
                <th className="px-1 py-0.5 text-left font-semibold">P</th>
                <th className="px-1 py-0.5 text-left font-semibold">Text</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={i} className="even:bg-neutral-bg2/30">
                  <td className="px-1 py-0.5 font-mono text-text-secondary whitespace-nowrap">
                    {r.timestamp_aest?.slice(11, 19) ?? ""}
                  </td>
                  <td className="px-1 py-0.5 font-mono text-text-secondary whitespace-nowrap">
                    {r.client_composite_id ?? ""}
                  </td>
                  <td className="px-1 py-0.5 font-semibold text-tag-alarm-text">{r.alarm_label}</td>
                  <td className="px-1 py-0.5 font-mono text-text-secondary">P{r.priority}</td>
                  <td className="px-1 py-0.5 text-text-secondary truncate max-w-[200px]">{r.alarm_text}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {count > rows.length && (
        <div className="text-micro italic text-text-muted">
          Showing {rows.length} of {count} matched rows.
        </div>
      )}
    </div>
  );
}

export function ScadaSignalDisclosure({ signalId, evidence }: ScadaDisclosureProps) {
  const { rule, rows, count } = evidence;
  return (
    <div
      data-testid={`signal-evidence-scada-${signalId}`}
      className="mt-1 ml-1 rounded border border-tag-scada-text/30 bg-tag-scada-bg/30 p-1.5 space-y-1"
    >
      <div className="text-micro text-text-muted font-mono">{formatScadaRule(rule)}</div>
      {rows.length === 0 ? (
        <div className="text-micro italic text-text-muted">No matching rows captured.</div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-micro">
            <thead className="text-text-muted uppercase tracking-wider">
              <tr>
                <th className="px-1 py-0.5 text-left font-semibold">Time</th>
                <th className="px-1 py-0.5 text-left font-semibold">Tag</th>
                <th className="px-1 py-0.5 text-left font-semibold">Meas</th>
                <th className="px-1 py-0.5 text-right font-semibold">Prev</th>
                <th className="px-1 py-0.5 text-right font-semibold">Value</th>
                <th className="px-1 py-0.5 text-right font-semibold">Δ</th>
                <th className="px-1 py-0.5 text-right font-semibold">%</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={i} className="even:bg-neutral-bg2/30">
                  <td className="px-1 py-0.5 font-mono text-text-secondary whitespace-nowrap">
                    {r.timestamp_aest?.slice(11, 19) ?? ""}
                  </td>
                  <td className="px-1 py-0.5 font-mono text-text-secondary whitespace-nowrap truncate max-w-[180px]">
                    {r.TagId}
                  </td>
                  <td className="px-1 py-0.5 font-semibold text-tag-scada-text">{r.measurement}</td>
                  <td className="px-1 py-0.5 text-right font-mono text-text-secondary tabular-nums">{r.prev_val}</td>
                  <td className="px-1 py-0.5 text-right font-mono text-text-secondary tabular-nums">{r.Value}</td>
                  <td className="px-1 py-0.5 text-right font-mono text-status-error tabular-nums">
                    {r.abs_drop > 0 ? "−" : "+"}{Math.abs(r.abs_drop)}
                  </td>
                  <td className="px-1 py-0.5 text-right font-mono text-text-secondary tabular-nums">
                    {r.pct_change}%
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {count > rows.length && (
        <div className="text-micro italic text-text-muted">
          Showing {rows.length} of {count} matched rows.
        </div>
      )}
    </div>
  );
}

export function PatternDisclosure({ patternId, evidence }: PatternDisclosureProps) {
  const entries = Object.entries(evidence.details ?? {});
  return (
    <div
      data-testid={`signal-evidence-pattern-${patternId}`}
      className="mt-1 ml-1 rounded border border-tag-pattern-text/30 bg-tag-pattern-bg/30 p-1.5"
    >
      {entries.length === 0 ? (
        <div className="text-micro italic text-text-muted">
          No structured pattern details for {patternId}.
        </div>
      ) : (
        <table className="w-full border-collapse text-micro">
          <tbody>
            {entries.map(([k, v]) => (
              <tr key={k} className="even:bg-neutral-bg2/30">
                <td className="px-1 py-0.5 font-mono text-text-muted whitespace-nowrap align-top">{k}</td>
                <td className="px-1 py-0.5 font-mono text-text-secondary break-all">
                  {typeof v === "object" ? JSON.stringify(v) : String(v)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
