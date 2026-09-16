/**
 * GraphResult — renders Gremlin graph query results inside the
 * ToolResultCard scaffold, using the shared ResultTable primitive.
 *
 * Input shape: JSON string of `[{key: value, ...}, ...]`. The header
 * set is the union of keys across all objects; the table delegates to
 * ResultTable for preview-rows / prominent-columns behaviour.
 */

import type { ToolResultProps } from "./index";
import { getProminentColumns } from "./index";
import { JsonFallback } from "./JsonFallback";
import { ToolResultCard } from "./ToolResultCard";
import { ResultTable } from "./ResultTable";
import { extractError, parseToolResult } from "./helpers";

export function GraphResult({ result, toolName }: ToolResultProps) {
  let parsed: unknown = parseToolResult(result);
  if (parsed === null) return <JsonFallback result={result} />;

  /* Object-shaped error envelope short-circuit. */
  if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
    const obj = parsed as Record<string, unknown>;
    const errDetail = extractError(obj);
    if (errDetail) {
      return <ToolResultCard error={{ detail: errDetail }} />;
    }
    /* Single object — wrap in array for uniform rendering. */
    parsed = [obj];
  }

  if (!Array.isArray(parsed) || parsed.length === 0) {
    return (
      <ToolResultCard signal={[{ label: "rows", value: 0, tone: "neutral" }]}>
        <div className="text-xs text-text-muted italic py-1">No results returned</div>
      </ToolResultCard>
    );
  }

  /* Infer headers from the union of all object keys. */
  const headerSet = new Set<string>();
  for (const item of parsed) {
    if (item && typeof item === "object" && !Array.isArray(item)) {
      for (const key of Object.keys(item as Record<string, unknown>)) {
        headerSet.add(key);
      }
    }
  }
  const headers = Array.from(headerSet);

  if (headers.length === 0) {
    return <JsonFallback result={result} />;
  }

  const rows = (parsed as Record<string, unknown>[]).map((item) =>
    headers.map((h) => item[h]),
  );

  return (
    <ToolResultCard signal={[{ label: "rows", value: rows.length }]}>
      <ResultTable
        headers={headers}
        rows={rows}
        prominentColumns={getProminentColumns(toolName)}
      />
    </ToolResultCard>
  );
}
