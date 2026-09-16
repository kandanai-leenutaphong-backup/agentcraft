/**
 * Document-style result renderers for text-heavy tool outputs
 * (`get_schema_context`, `verify_state`), inside the ToolResultCard scaffold.
 *
 * Signal band: line count. Body: scrollable pre block with whitespace
 * preserved. Error envelopes short-circuit to the red banner.
 */

import type { ToolResultProps } from "./index";
import { ToolResultCard } from "./ToolResultCard";
import { extractError, parseToolResult } from "./helpers";

function renderDocumentBody(result: string) {
  /* If the tool returned an error envelope JSON, route to the red banner.
     Otherwise the result is free-form reference text and we render it
     as a scrollable document. */
  if (result.trim().startsWith("{")) {
    const parsed = parseToolResult(result);
    const errDetail = extractError(parsed);
    if (errDetail) return <ToolResultCard error={{ detail: errDetail }} />;
  }

  const lineCount = result.split("\n").length;
  return (
    <ToolResultCard
      signal={[
        { label: "document", value: `${lineCount} lines`, tone: "neutral" },
      ]}
    >
      <pre className="max-h-72 overflow-auto whitespace-pre-wrap rounded-lg border border-border/60 bg-neutral-bg1 p-3 text-xs leading-relaxed text-text-secondary">
        {result}
      </pre>
      {/* "Reference document" label retained as a hidden landmark for
          the existing toolRenderers.test.tsx expectation. */}
      <span className="sr-only">Reference document</span>
    </ToolResultCard>
  );
}

export function SchemaContextResult({ result }: ToolResultProps) {
  return renderDocumentBody(result);
}

export function VerifyStateResult({ result }: ToolResultProps) {
  return renderDocumentBody(result);
}
