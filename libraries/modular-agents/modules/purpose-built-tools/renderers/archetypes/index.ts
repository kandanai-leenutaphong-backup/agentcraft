/**
 * The archetype registry.
 *
 * WHY ARCHETYPES RATHER THAN A CARD PER TOOL
 * ------------------------------------------
 * The Nth tool must not require the Nth bespoke renderer, or new tools stop
 * getting one and quietly fall through to a JSON dump. Eight shapes cover
 * what tools actually return, so a new tool declares which shape it produces
 * and is rendered properly on day one.
 *
 * Bespoke cards remain available for the few results that genuinely deserve
 * one. The rule is that a tool resolves to *something* — never to raw JSON in
 * production.
 *
 * The keys here are a contract: they are named in CONTRACT.md and asserted by
 * the box's selftest, so renaming one without updating the mapping fails the
 * build rather than silently orphaning a tool.
 */

import type { ComponentType } from "react";
import type { ArchetypeRendererProps } from "./_common";
import { TabularRenderer } from "./TabularRenderer";
import { MultiTabularRenderer } from "./MultiTabularRenderer";
import { GraphRenderer } from "./GraphRenderer";
import { SearchRenderer } from "./SearchRenderer";
import { MetricsRenderer } from "./MetricsRenderer";
import { DocumentRenderer } from "./DocumentRenderer";
import { StatusRenderer } from "./StatusRenderer";
import { ActionRenderer } from "./ActionRenderer";

export enum RendererArchetype {
  /** {columns, rows|data, scope} — records. */
  Tabular = "tabular",
  /** {tables: [{title?, headers, rows}]} — several named tables in one answer. */
  MultiTabular = "multi-tabular",
  /** {nodes, edges, summary} or a bare node list — traversals. */
  Graph = "graph",
  /** {results: [{title, source, score, text}], count} — retrieval. */
  Search = "search",
  /** {metrics: [{label, value, unit}]} or a scalar map — aggregates. */
  Metrics = "metrics",
  /** {title, document|text|content|body} or plain text — prose. */
  Document = "document",
  /** {status, message?, detail?} — confirmations. */
  Status = "status",
  /** {action, status?, simulated?} — side effects, real or simulated. */
  Action = "action",
}

const ARCHETYPE_RENDERERS: Record<RendererArchetype, ComponentType<ArchetypeRendererProps>> = {
  [RendererArchetype.Tabular]: TabularRenderer,
  [RendererArchetype.MultiTabular]: MultiTabularRenderer,
  [RendererArchetype.Graph]: GraphRenderer,
  [RendererArchetype.Search]: SearchRenderer,
  [RendererArchetype.Metrics]: MetricsRenderer,
  [RendererArchetype.Document]: DocumentRenderer,
  [RendererArchetype.Status]: StatusRenderer,
  [RendererArchetype.Action]: ActionRenderer,
};

/** Every known key, for validating a tool's declared archetype at build time. */
export const RENDERER_ARCHETYPES: ReadonlySet<string> = new Set(Object.values(RendererArchetype));

/** Resolve a key to its renderer, or null when the key is unknown. */
export function getArchetypeRenderer(
  archetype: string,
): ComponentType<ArchetypeRendererProps> | null {
  return ARCHETYPE_RENDERERS[archetype as RendererArchetype] ?? null;
}

/**
 * Resolve a tool to its renderer through a name -> archetype map.
 *
 * A tool with no entry returns null, and the caller decides what to do. That
 * decision should be loud: silently substituting a JSON dump is how a tool
 * ships for months without anyone noticing it has no card.
 */
export function resolveToolRenderer(
  toolName: string,
  archetypeByTool: Record<string, string>,
): ComponentType<ArchetypeRendererProps> | null {
  const archetype = archetypeByTool[toolName];
  return archetype ? getArchetypeRenderer(archetype) : null;
}
