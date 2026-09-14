/**
 * MetricsRenderer — a handful of numbers, as numbers.
 *
 * A one-row table is the worst way to show four scalars: the reader gets
 * column headers, a horizontal scroll and a value in six-point mono. A metric
 * grid puts the number first, at a readable size, with its label above it.
 *
 * Accepts an explicit `{metrics: [{label, value, unit?, tone?}]}` or a bare
 * scalar map, because a tool that computed three numbers should not have to
 * learn a wrapper shape to display them.
 */

import { ToolResultCard, type SignalTone } from "../ToolResultCard";
import { formatCell, parseToolResult, scopeBadges } from "../helpers";
import {
  ArchetypeEmpty,
  ArchetypeUnresolved,
  renderEnvelopeState,
  type ArchetypeRendererProps,
} from "./_common";

interface Metric {
  label: string;
  value: unknown;
  unit?: string;
  tone?: SignalTone;
}

const SCALAR_TYPES = ["number", "string", "boolean"];

function coerceMetrics(parsed: Record<string, unknown>): Metric[] | null {
  if (Array.isArray(parsed.metrics)) {
    return (parsed.metrics as Record<string, unknown>[])
      .filter((metric) => metric && typeof metric === "object" && typeof metric.label === "string")
      .map((metric) => ({
        label: metric.label as string,
        value: metric.value,
        unit: typeof metric.unit === "string" ? metric.unit : undefined,
        tone: typeof metric.tone === "string" ? (metric.tone as SignalTone) : undefined,
      }));
  }

  /* A bare scalar map. `scope` is excluded: it is provenance, and the card
     already renders it as badges. */
  const entries = Object.entries(parsed).filter(
    ([key, value]) =>
      key !== "scope" && (value === null || SCALAR_TYPES.includes(typeof value)),
  );
  return entries.length === 0
    ? null
    : entries.map(([label, value]) => ({ label, value }));
}

export function MetricsRenderer({ resizeKey, result }: ArchetypeRendererProps) {
  const parsed = parseToolResult<Record<string, unknown>>(result);
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    return <ArchetypeUnresolved archetype="metrics" result={result} />;
  }

  const envelopeState = renderEnvelopeState(parsed);
  if (envelopeState) return envelopeState;

  const metrics = coerceMetrics(parsed);
  if (metrics === null) return <ArchetypeUnresolved archetype="metrics" result={result} />;

  const scope = scopeBadges(parsed);
  if (metrics.length === 0) {
    return <ArchetypeEmpty label="metrics" message="No metrics returned" scope={scope} />;
  }

  return (
    <ToolResultCard resizeKey={resizeKey} scope={scope} signal={[{ label: "metrics", value: metrics.length }]}>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        {metrics.map((metric, index) => (
          <div
            key={index}
            className="rounded-lg border border-border/50 bg-neutral-bg2 px-2 py-1.5"
          >
            <div className="truncate text-micro uppercase tracking-wider text-text-muted">
              {metric.label}
            </div>
            <div className="font-mono text-sm text-text-primary">
              {formatCell(metric.value)}
              {metric.unit && (
                <span className="ml-0.5 text-micro text-text-muted">{metric.unit}</span>
              )}
            </div>
          </div>
        ))}
      </div>
    </ToolResultCard>
  );
}
