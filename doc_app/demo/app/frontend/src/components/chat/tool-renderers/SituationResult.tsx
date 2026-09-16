/**
 * SituationResult — renders detect_situations results as ranked situation
 * cards inside the ToolResultCard scaffold.
 *
 * Signal band: total situations + filtered count (score ≥ 5). Body: the
 * top filtered situations using the shared SituationCard component.
 */

import type { ToolResultProps } from "./index";
import { SituationCard } from "@/components/panels/SituationCard";
import { JsonFallback } from "./JsonFallback";
import { ToolResultCard } from "./ToolResultCard";
import { extractError, parseToolResult } from "./helpers";

interface SituationEnvelope {
  situations?: unknown[];
  count?: number;
}

export function SituationResult({ result }: ToolResultProps) {
  const parsed = parseToolResult<SituationEnvelope & Record<string, unknown>>(result);
  if (!parsed) return <JsonFallback result={result} />;

  const errDetail = extractError(parsed);
  if (errDetail) return <ToolResultCard error={{ detail: errDetail }} />;

  const situations = Array.isArray(parsed.situations) ? parsed.situations : [];

  if (situations.length === 0) {
    return (
      <ToolResultCard signal={[{ label: "situations", value: 0, tone: "neutral" }]}>
        <div className="text-xs text-text-muted italic py-1">No situations detected</div>
      </ToolResultCard>
    );
  }

  /* Show top 10 situations with score >= 5. */
  const filtered = situations
    .filter((s: any) => (s.total_score ?? 0) >= 5)
    .slice(0, 10);

  if (filtered.length === 0) {
    return (
      <ToolResultCard
        signal={[
          { label: "total", value: situations.length, tone: "neutral" },
          { label: "score≥5", value: 0, tone: "neutral" },
        ]}
      >
        <div className="text-xs text-text-muted italic py-1">All minor.</div>
      </ToolResultCard>
    );
  }

  return (
    <ToolResultCard
      signal={[
        { label: "shown", value: filtered.length },
        { label: "total", value: situations.length, tone: "neutral" },
      ]}
    >
      <div className="space-y-1.5 max-h-72 overflow-y-auto">
        {filtered.map((sit: any, i: number) => (
          <SituationCard key={sit.situation_id ?? i} situation={sit} />
        ))}
      </div>
    </ToolResultCard>
  );
}
