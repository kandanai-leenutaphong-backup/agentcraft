/**
 * StatusResult — compact confirmation renderer for action/status tools
 * (dispatch_field_engineer, call_engineer, send_incident_report,
 * report_normal, push_situation_alert), inside the ToolResultCard scaffold.
 *
 * Signal band: status + optional classification. Body: any detail /
 * situation / action prose lines included by the backend.
 */

import type { ToolResultProps } from "./index";
import { JsonFallback } from "./JsonFallback";
import { ToolResultCard, type SignalTone } from "./ToolResultCard";
import { extractError, parseToolResult } from "./helpers";

export function StatusResult({ result }: ToolResultProps) {
  const parsed = parseToolResult(result);
  if (!parsed) return <JsonFallback result={result} />;

  const errDetail = extractError(parsed);
  if (errDetail) return <ToolResultCard error={{ detail: errDetail }} />;

  const status = typeof parsed.status === "string" ? parsed.status : "complete";
  const tone: SignalTone = status === "error" ? "error" : "success";

  const signal: { label: string; value: string; tone?: SignalTone }[] = [
    { label: "status", value: status, tone },
  ];
  if (typeof parsed.classification === "string") {
    signal.push({ label: "class", value: parsed.classification, tone: "neutral" });
  }

  const bodyLines = (["detail", "situation", "action"] as const)
    .map((k) => (typeof parsed[k] === "string" ? (parsed[k] as string) : null))
    .filter((v): v is string => v !== null);

  return (
    <ToolResultCard signal={signal}>
      {bodyLines.length > 0 && (
        <div className="space-y-1">
          {bodyLines.map((line, i) => (
            <div key={i} className="text-text-secondary text-xs">
              {line}
            </div>
          ))}
        </div>
      )}
    </ToolResultCard>
  );
}
