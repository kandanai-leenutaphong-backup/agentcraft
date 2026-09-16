/**
 * PanelToolSummary — compact confirmation renderer for panel update
 * tools, inside the ToolResultCard scaffold.
 *
 * R4 invariants:
 *   - Honour `parsed.status` / `parsed.error` instead of always rendering
 *     a success badge. Error envelopes route to the red banner.
 *   - Resolve the panel label from the `toolName` prop (threaded by
 *     ToolCallDisplay) when the envelope does not echo the tool name.
 *     This eliminates the "Panel" generic fallback when the backend
 *     omitted the `tool` field.
 */

import type { ToolResultProps } from "./index";
import { ToolResultCard } from "./ToolResultCard";
import { extractError, parseToolResult } from "./helpers";

/** Map tool names to human-readable labels. */
const PANEL_LABELS: Record<string, string> = {
  update_disturbance_summary: "Disturbance Summary",
  update_operating_state: "Operating State",
  update_priority_actions: "Priority Actions",
  push_priority_action: "Priority Actions",
  push_action: "Priority Actions",
  // push_classifier_verdict label removed 2026-05-18 with the classifier retirement.
  set_investigation_plan: "Investigation Plan",
};

function resolveLabel(parsed: Record<string, unknown> | null, toolName?: string): string {
  /* Prefer envelope-echoed tool name when present (stub tools include
     a `tool` field), then the dispatcher-threaded toolName, finally
     a generic fallback. */
  const envelopeTool = parsed && typeof parsed.tool === "string" ? (parsed.tool as string) : null;
  return (
    (envelopeTool && PANEL_LABELS[envelopeTool]) ||
    (toolName && PANEL_LABELS[toolName]) ||
    "Panel"
  );
}

export function PanelToolSummary({ result, toolName }: ToolResultProps) {
  const parsed = parseToolResult(result);

  const errDetail = extractError(parsed);
  if (errDetail) return <ToolResultCard error={{ detail: errDetail }} />;

  const label = resolveLabel(parsed, toolName);

  /* Compact success tone — kept visually narrow (single chip) so panel
     confirmations do not dominate scroll. */
  return (
    <ToolResultCard
      signal={[{ label: "updated", value: label, tone: "success" }]}
    />
  );
}
