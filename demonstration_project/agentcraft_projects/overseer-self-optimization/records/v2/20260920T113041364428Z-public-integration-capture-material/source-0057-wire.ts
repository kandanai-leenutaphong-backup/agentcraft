/**
 * The wire contract, in TypeScript, plus the parsers that refuse a payload
 * this client cannot trust.
 *
 * ADAPTED from `resource_explorer/frontend/src/api/wire.ts`. See PROVENANCE.md.
 *
 * Every field is read defensively. A response that lost a field to a version
 * skew must degrade to a legible state rather than throwing inside a render:
 * an unknown status is `unavailable`, a missing list is empty, and a missing
 * string is "". What is never guessed is a *number*: an absent count stays
 * absent, because a zero invented here would read as a real measurement.
 */

export const ROOT_ID = "root";

export const NODE_STATUSES = [
  "ok",
  "empty",
  "forbidden",
  "unreachable",
  "unconfigured",
  "unavailable",
] as const;
export type NodeStatus = (typeof NODE_STATUSES)[number];

export const NODE_KINDS = ["root", "use_case", "source"] as const;
export type NodeKind = (typeof NODE_KINDS)[number];

export const CONTENT_KINDS = ["none", "rows", "json"] as const;
export type ContentKind = (typeof CONTENT_KINDS)[number];

export const SOURCE_TYPES = ["adx_table", "cosmos_container", "gremlin_graph", "search_index", "local_table"] as const;
export type SourceType = (typeof SOURCE_TYPES)[number];

export type DetailValue = string | number | boolean | null;

export interface TreeNode {
  id: string;
  label: string;
  kind: NodeKind;
  expandable: boolean;
  hasContent: boolean;
  status: NodeStatus;
  useCaseId: string;
  sourceId: string;
  sourceType: SourceType | null;
  tags: string[];
  enabled: boolean | null;
  configured: boolean;
  detail: Record<string, DetailValue> | null;
  error: string | null;
}

export interface TreeResponse {
  schemaVersion: number;
  fixtures: boolean;
  node: string;
  label: string;
  kind: NodeKind;
  breadcrumb: string[];
  status: NodeStatus;
  children: TreeNode[];
  truncated: boolean;
  hasContent: boolean;
  selectionScope: string;
  detail: Record<string, DetailValue> | null;
  error: string | null;
  observedAt: string;
}

export interface ConnectorIdentity {
  id: string;
  name: string;
  reachedBy: string;
}

export interface SchemaField {
  name: string;
  type: string;
}

export interface ResourceResponse {
  schemaVersion: number;
  fixtures: boolean;
  node: string;
  label: string;
  kind: NodeKind;
  breadcrumb: string[];
  useCaseId: string;
  sourceId: string;
  sourceType: SourceType;
  status: NodeStatus;
  configured: boolean;
  enabled: boolean;
  holds: string;
  capabilities: string[];
  connector: ConnectorIdentity;
  coordinates: Record<string, DetailValue>;
  metrics: Record<string, DetailValue>;
  schemaFields: SchemaField[] | null;
  settings: string[];
  provenance: string;
  detail: Record<string, DetailValue> | null;
  error: string | null;
  observedAt: string;
}

export interface ContentResponse {
  schemaVersion: number;
  fixtures: boolean;
  node: string;
  label: string;
  kind: NodeKind;
  breadcrumb: string[];
  useCaseId: string;
  sourceId: string;
  status: NodeStatus;
  contentKind: ContentKind;
  mediaType: string;
  text: string | null;
  rows: Record<string, unknown>[] | null;
  columns: string[] | null;
  sizeBytes: number;
  rowLimit: number;
  sampleOf: number | null;
  truncated: boolean;
  /** What a bound cut from this sample, in the server's words. */
  sampleNotes: string[];
  provenance: string;
  detail: Record<string, DetailValue> | null;
  error: string | null;
  observedAt: string;
}

export type SelectionMode = "all" | "none" | "explicit";

export interface SelectionSource {
  sourceId: string;
  useCaseId: string;
  label: string;
  sourceType: SourceType;
  configured: boolean;
  enabled: boolean;
}

export interface SelectionResponse {
  schemaVersion: number;
  mode: SelectionMode;
  enabled: string[];
  sources: SelectionSource[];
  scope: string;
  observedAt: string;
}

function record(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function text(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function flag(value: unknown, fallback = false): boolean {
  return typeof value === "boolean" ? value : fallback;
}

function count(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

/** An absent number stays absent. Inventing a zero would read as a measurement. */
function maybeCount(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function stringList(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function status(value: unknown): NodeStatus {
  return NODE_STATUSES.includes(value as NodeStatus)
    ? (value as NodeStatus)
    : "unavailable";
}

function kind(value: unknown): NodeKind {
  return NODE_KINDS.includes(value as NodeKind) ? (value as NodeKind) : "source";
}

function contentKind(value: unknown): ContentKind {
  return CONTENT_KINDS.includes(value as ContentKind) ? (value as ContentKind) : "none";
}

function sourceType(value: unknown): SourceType | null {
  return SOURCE_TYPES.includes(value as SourceType) ? (value as SourceType) : null;
}

function detailMap(value: unknown): Record<string, DetailValue> | null {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return null;
  const out: Record<string, DetailValue> = {};
  for (const [key, item] of Object.entries(value as Record<string, unknown>)) {
    if (item === null || typeof item === "string" || typeof item === "number" || typeof item === "boolean") {
      out[key] = item;
    } else {
      out[key] = String(item);
    }
  }
  return out;
}

function nullableText(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

export function parseTreeNode(raw: unknown): TreeNode {
  const source = record(raw);
  return {
    id: text(source.id),
    label: text(source.label),
    kind: kind(source.kind),
    expandable: flag(source.expandable),
    hasContent: flag(source.hasContent),
    status: status(source.status),
    useCaseId: text(source.useCaseId),
    sourceId: text(source.sourceId),
    sourceType: sourceType(source.sourceType),
    tags: stringList(source.tags),
    enabled: typeof source.enabled === "boolean" ? source.enabled : null,
    configured: flag(source.configured, true),
    detail: detailMap(source.detail),
    error: nullableText(source.error),
  };
}

export function parseTree(raw: unknown): TreeResponse {
  const source = record(raw);
  return {
    schemaVersion: count(source.schemaVersion),
    fixtures: flag(source.fixtures),
    node: text(source.node, ROOT_ID),
    label: text(source.label),
    kind: kind(source.kind),
    breadcrumb: stringList(source.breadcrumb),
    status: status(source.status),
    children: Array.isArray(source.children) ? source.children.map(parseTreeNode) : [],
    truncated: flag(source.truncated),
    hasContent: flag(source.hasContent),
    selectionScope: text(source.selectionScope),
    detail: detailMap(source.detail),
    error: nullableText(source.error),
    observedAt: text(source.observedAt),
  };
}

export function parseResource(raw: unknown): ResourceResponse {
  const source = record(raw);
  const connector = record(source.connector);
  const fields = Array.isArray(source.schemaFields)
    ? source.schemaFields.map((item) => {
        const entry = record(item);
        return { name: text(entry.name), type: text(entry.type) };
      })
    : null;
  return {
    schemaVersion: count(source.schemaVersion),
    fixtures: flag(source.fixtures),
    node: text(source.node),
    label: text(source.label),
    kind: kind(source.kind),
    breadcrumb: stringList(source.breadcrumb),
    useCaseId: text(source.useCaseId),
    sourceId: text(source.sourceId),
    sourceType: sourceType(source.sourceType) ?? "adx_table",
    status: status(source.status),
    configured: flag(source.configured, true),
    enabled: flag(source.enabled, true),
    holds: text(source.holds),
    capabilities: stringList(source.capabilities),
    connector: {
      id: text(connector.id),
      name: text(connector.name),
      reachedBy: text(connector.reachedBy),
    },
    coordinates: detailMap(source.coordinates) ?? {},
    metrics: detailMap(source.metrics) ?? {},
    schemaFields: fields,
    settings: stringList(source.settings),
    provenance: text(source.provenance),
    detail: detailMap(source.detail),
    error: nullableText(source.error),
    observedAt: text(source.observedAt),
  };
}

export function parseContent(raw: unknown): ContentResponse {
  const source = record(raw);
  return {
    schemaVersion: count(source.schemaVersion),
    fixtures: flag(source.fixtures),
    node: text(source.node),
    label: text(source.label),
    kind: kind(source.kind),
    breadcrumb: stringList(source.breadcrumb),
    useCaseId: text(source.useCaseId),
    sourceId: text(source.sourceId),
    status: status(source.status),
    contentKind: contentKind(source.contentKind),
    mediaType: text(source.mediaType),
    text: typeof source.text === "string" ? source.text : null,
    rows: Array.isArray(source.rows) ? source.rows.map((row) => record(row)) : null,
    columns: Array.isArray(source.columns) ? stringList(source.columns) : null,
    sizeBytes: count(source.sizeBytes),
    rowLimit: count(source.rowLimit),
    sampleOf: maybeCount(source.sampleOf),
    truncated: flag(source.truncated),
    sampleNotes: stringList(source.sampleNotes),
    provenance: text(source.provenance),
    detail: detailMap(source.detail),
    error: nullableText(source.error),
    observedAt: text(source.observedAt),
  };
}

export function parseSelection(raw: unknown): SelectionResponse {
  const source = record(raw);
  const mode = source.mode;
  return {
    schemaVersion: count(source.schemaVersion),
    mode: mode === "all" || mode === "none" || mode === "explicit" ? mode : "all",
    enabled: stringList(source.enabled),
    sources: Array.isArray(source.sources)
      ? source.sources.map((item) => {
          const entry = record(item);
          return {
            sourceId: text(entry.sourceId),
            useCaseId: text(entry.useCaseId),
            label: text(entry.label),
            sourceType: sourceType(entry.sourceType) ?? "adx_table",
            configured: flag(entry.configured, true),
            enabled: flag(entry.enabled, true),
          };
        })
      : [],
    scope: text(source.scope),
    observedAt: text(source.observedAt),
  };
}
