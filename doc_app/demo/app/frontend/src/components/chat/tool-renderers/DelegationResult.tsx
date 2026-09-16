/**
 * DelegationResult — renders `delegate_to_agent` results as a specialist
 * report card inside the ToolResultCard scaffold.
 *
 * Scope band: agent id (status + duration become signal chips).
 * Body: markdown response, or error tone when status === "error".
 */

import type { ToolResultProps } from "./index";
import { MarkdownRenderer } from "../../shared/MarkdownRenderer";
import { ToolResultCard } from "./ToolResultCard";
import { extractError, parseToolResult } from "./helpers";

interface DelegationEnvelope {
  agent_id?: string;
  status?: string;
  response?: string;
  duration_ms?: number;
  error?: string;
}

export function DelegationResult({ result }: ToolResultProps) {
  const parsed = parseToolResult<DelegationEnvelope & Record<string, unknown>>(result);
  if (!parsed) {
    return (
      <ToolResultCard>
        <pre className="text-text-muted whitespace-pre-wrap text-xs">{result}</pre>
      </ToolResultCard>
    );
  }

  const errDetail = extractError(parsed);
  if (errDetail) return <ToolResultCard error={{ detail: errDetail }} />;

  const { agent_id, status, response, duration_ms } = parsed;
  const durationStr = duration_ms ? `${(duration_ms / 1000).toFixed(1)}s` : null;

  const scope = agent_id ? [{ label: "agent", value: agent_id }] : undefined;
  const signal = [
    { label: "status", value: status ?? "unknown", tone: "success" as const },
    ...(durationStr ? [{ label: "took", value: durationStr, tone: "neutral" as const }] : []),
  ];

  return (
    <ToolResultCard scope={scope} signal={signal}>
      {response ? (
        /* Emoji removed from a11y tree; the agent_id badge is the
           accessible name for the speaker. */
        <div className="prose prose-sm max-w-none text-text-secondary [font-size:inherit]">
          <MarkdownRenderer content={response} />
        </div>
      ) : (
        <p className="text-text-muted italic text-xs">No response</p>
      )}
    </ToolResultCard>
  );
}
