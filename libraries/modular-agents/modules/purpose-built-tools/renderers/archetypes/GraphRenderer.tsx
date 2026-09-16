/**
 * GraphRenderer — nodes and edges, or a bare list of node objects.
 *
 * A graph result has one property no table has: the node objects are
 * heterogeneous. A site carries different keys from an asset, so the headers
 * are the union of every key seen, not the keys of the first row — a detail
 * that silently truncates a result if you get it wrong.
 *
 * It has a second property: the edges mean something. When edges are present
 * the result is drawn as a graph and the table is kept underneath, because the
 * picture answers "what connects to what" and the table answers "what exactly
 * did it return" — and a reader needs both at different moments.
 */

import { ToolResultCard } from "../ToolResultCard";
import { ResultTable } from "../ResultTable";
import { GraphView } from "../GraphView";
import { parseToolResult, scopeBadges } from "../helpers";
import {
  ArchetypeEmpty,
  ArchetypeUnresolved,
  renderEnvelopeState,
  type ArchetypeRendererProps,
} from "./_common";

interface GraphEnvelope {
  nodes?: unknown[];
  edges?: unknown[];
  summary?: string;
}

/** Union-keyed headers, so a heterogeneous node set loses no column. */
function tableFromObjects(items: Record<string, unknown>[]): {
  headers: string[];
  rows: unknown[][];
} {
  const headers: string[] = [];
  const seen = new Set<string>();
  for (const item of items) {
    for (const key of Object.keys(item ?? {})) {
      if (!seen.has(key)) {
        seen.add(key);
        headers.push(key);
      }
    }
  }
  return { headers, rows: items.map((item) => headers.map((header) => item?.[header])) };
}

const isObject = (value: unknown): value is Record<string, unknown> =>
  !!value && typeof value === "object";

export function GraphRenderer({ resizeKey, result, prominentColumns }: ArchetypeRendererProps) {
  const parsed = parseToolResult<GraphEnvelope | Record<string, unknown> | unknown[]>(result);
  if (parsed === null) return <ArchetypeUnresolved archetype="graph" result={result} />;

  /* A bare array of nodes — the shape a traversal returns with no envelope. */
  if (Array.isArray(parsed)) {
    if (parsed.length === 0) return <ArchetypeEmpty label="nodes" message="No nodes returned" />;
    const objects = parsed.filter(isObject);
    if (objects.length === 0) return <ArchetypeUnresolved archetype="graph" result={result} />;
    const { headers, rows } = tableFromObjects(objects);
    return (
      <ToolResultCard resizeKey={resizeKey} signal={[{ label: "nodes", value: rows.length }]}>
        <ResultTable headers={headers} rows={rows} prominentColumns={prominentColumns} />
      </ToolResultCard>
    );
  }

  if (!isObject(parsed)) return <ArchetypeUnresolved archetype="graph" result={result} />;

  const envelopeState = renderEnvelopeState(parsed);
  if (envelopeState) return envelopeState;

  const envelope = parsed as GraphEnvelope;
  if (!Array.isArray(envelope.nodes) && !Array.isArray(envelope.edges)) {
    return <ArchetypeUnresolved archetype="graph" result={result} />;
  }

  const nodes = Array.isArray(envelope.nodes) ? envelope.nodes : [];
  const edges = Array.isArray(envelope.edges) ? envelope.edges : [];
  const scope = scopeBadges(parsed);
  if (nodes.length === 0 && edges.length === 0) {
    return <ArchetypeEmpty label="nodes" message="No graph elements returned" scope={scope} />;
  }

  const { headers, rows } = tableFromObjects(nodes.filter(isObject));
  return (
    <ToolResultCard
      resizeKey={resizeKey}
      scope={scope}
      signal={[
        { label: "nodes", value: nodes.length },
        { label: "edges", value: edges.length, tone: "neutral" },
      ]}
      note={typeof envelope.summary === "string" && envelope.summary ? envelope.summary : null}
      noteTone="info"
    >
      {edges.length > 0 && <GraphView nodes={nodes} edges={edges} />}
      {rows.length > 0 && (
        <ResultTable headers={headers} rows={rows} prominentColumns={prominentColumns} />
      )}
    </ToolResultCard>
  );
}
