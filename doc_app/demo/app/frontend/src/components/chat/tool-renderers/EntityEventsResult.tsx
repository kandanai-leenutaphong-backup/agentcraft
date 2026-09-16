/**
 * EntityEventsResult — side-by-side SCADA and alarm correlation view,
 * inside the ToolResultCard scaffold.
 *
 * Scope band: entity_id + time range. Body: two TabularResult blocks
 * (SCADA readings + alarm events) reusing the same table primitive.
 */

import type { ToolResultProps } from "./index";
import { TabularResult } from "./TabularResult";
import { JsonFallback } from "./JsonFallback";
import { ToolResultCard } from "./ToolResultCard";
import { extractError, parseToolResult } from "./helpers";

interface EntityEventsEnvelope {
  entity_id?: string;
  time_range?: { start?: string; end?: string };
  scada?: unknown;
  alarms?: unknown;
}

export function EntityEventsResult({ result }: ToolResultProps) {
  const parsed = parseToolResult<EntityEventsEnvelope & Record<string, unknown>>(result);
  if (!parsed) return <JsonFallback result={result} />;

  const errDetail = extractError(parsed);
  if (errDetail) return <ToolResultCard error={{ detail: errDetail }} />;

  const scope: { label: string; value: string }[] = [];
  if (parsed.entity_id) scope.push({ label: "entity", value: parsed.entity_id });
  if (parsed.time_range?.start && parsed.time_range?.end) {
    scope.push({ label: "window", value: `${parsed.time_range.start} → ${parsed.time_range.end}` });
  }

  const scadaJson = JSON.stringify(parsed.scada ?? {});
  const alarmsJson = JSON.stringify(parsed.alarms ?? {});

  return (
    <ToolResultCard scope={scope}>
      <div className="space-y-3">
        <section className="space-y-1">
          <div className="text-label font-semibold uppercase tracking-wider text-text-muted">
            SCADA readings
          </div>
          <TabularResult result={scadaJson} toolName="find_scada" />
        </section>
        <section className="space-y-1">
          <div className="text-label font-semibold uppercase tracking-wider text-text-muted">
            Alarm events
          </div>
          <TabularResult result={alarmsJson} toolName="find_alarms" />
        </section>
      </div>
    </ToolResultCard>
  );
}
