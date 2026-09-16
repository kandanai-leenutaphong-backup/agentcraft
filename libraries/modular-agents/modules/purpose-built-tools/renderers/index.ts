/**
 * Tool result cards — the operator-facing half of the tool contract.
 *
 * The same envelope a tool returns and the weight meter scores is what these
 * components render. One declaration, three consumers: the description the
 * model reads, the wire shape the meter counts, and the card an operator
 * looks at. Nothing here re-derives the shape — it reads the fields
 * CONTRACT.md defines.
 *
 * Usage:
 *
 *   import "@agentcraft/modular-agents/styles";
 *   import { getArchetypeRenderer } from "@agentcraft/modular-agents";
 *
 *   const Renderer = getArchetypeRenderer("tabular");
 *   <Renderer result={toolResultString} prominentColumns={["site", "kind"]} />
 *
 * Dependencies: React 18+ and Tailwind. See renderers/README.md — the cards
 * render unstyled without the token stylesheet and the preset (GOTCHAS.md G17).
 */

export { ToolResultCard } from "./ToolResultCard";
export type {
  NoteTone,
  ScopeBadge,
  SignalChip,
  SignalTone,
  ToolResultCardProps,
} from "./ToolResultCard";

export { ResultTable } from "./ResultTable";
export type { ResultTableProps } from "./ResultTable";

export {
  extractDuplicate,
  extractError,
  extractRefusal,
  formatCell,
  parseToolResult,
  scopeBadges,
} from "./helpers";

export {
  ArchetypeEmpty,
  ArchetypeUnresolved,
  renderEnvelopeState,
} from "./archetypes/_common";
export type { ArchetypeRendererProps } from "./archetypes/_common";

export { TabularRenderer } from "./archetypes/TabularRenderer";
export { GraphRenderer } from "./archetypes/GraphRenderer";
export { SearchRenderer } from "./archetypes/SearchRenderer";
export { MetricsRenderer } from "./archetypes/MetricsRenderer";
export { DocumentRenderer } from "./archetypes/DocumentRenderer";
export type { DocumentRendererProps } from "./archetypes/DocumentRenderer";
export { StatusRenderer } from "./archetypes/StatusRenderer";
export { ActionRenderer } from "./archetypes/ActionRenderer";

export {
  RENDERER_ARCHETYPES,
  RendererArchetype,
  getArchetypeRenderer,
  resolveToolRenderer,
} from "./archetypes";

export { GraphView } from "./GraphView";
export { buildGraphLayout } from "./graphLayout";
export { MarkdownBody } from "./MarkdownBody";
