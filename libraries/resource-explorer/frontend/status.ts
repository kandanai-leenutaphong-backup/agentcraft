/**
 * Every state this surface can show, as words.
 *
 * ADAPTED from `resource_explorer/frontend/src/api/status.ts`. See PROVENANCE.md.
 * The tone tables are the change: upstream emits Tailwind utility strings, and
 * this host has no Tailwind. They emit a single scoped class name each, defined
 * in `inventory.css`, so the host's own stylesheet is never reset.
 *
 * A dark branch that renders as an empty one throws away the operator's whole
 * diagnosis, so each status carries a name, a meaning and who can fix it.
 * Colour is decoration on top of the text and never the only carrier: two
 * statuses share the warning tone and are still told apart by their words.
 */

import type { ContentKind, DetailValue, NodeStatus, SourceType } from "./wire.js";

export const LOADING_LABEL = "Loading…";
export const EMPTY_VALUE_LABEL = "(empty)";
export const NULL_VALUE_LABEL = "(none)";

export type Tone = "neutral" | "muted" | "flow" | "warning" | "critical";

const STATUS_LABELS: Record<NodeStatus, string> = {
  ok: "OK",
  empty: "Empty",
  forbidden: "Forbidden",
  unreachable: "Unreachable",
  unconfigured: "Not configured",
  unavailable: "Unavailable",
};

const STATUS_MEANINGS: Record<NodeStatus, string> = {
  ok: "The call succeeded.",
  empty: "The call succeeded and there is genuinely nothing here.",
  forbidden: "The signed-in identity is missing a data or control-plane role for this.",
  unreachable:
    "The service refused the connection — a network rule, private DNS, or a firewall.",
  unconfigured: "A coordinate nobody set. No probe was attempted. The cause below names it.",
  unavailable:
    "The service refused, an SDK is missing, or the provider declares no api-version.",
};

const STATUS_REMEDIES: Record<NodeStatus, string> = {
  ok: "",
  empty: "Nothing to fix — this is a true answer, not a failure.",
  forbidden: "Fixed by a role grant on the identity this app runs as.",
  unreachable: "Fixed by a network change. A role grant does nothing here.",
  unconfigured: "Fixed by an operator setting the coordinate named in the cause.",
  unavailable: "Depends on the cause below. Often retryable.",
};

const STATUS_TONES: Record<NodeStatus, Tone> = {
  ok: "neutral",
  empty: "muted",
  forbidden: "warning",
  unreachable: "critical",
  unconfigured: "flow",
  unavailable: "warning",
};

/** Which statuses a retry could plausibly change. `forbidden` and
 * `unconfigured` need an operator, so offering retry on them is a lie. */
const RETRYABLE: Record<NodeStatus, boolean> = {
  ok: true,
  empty: true,
  forbidden: false,
  unreachable: true,
  unconfigured: false,
  unavailable: true,
};

export function statusLabel(status: NodeStatus): string {
  return STATUS_LABELS[status];
}

export function statusMeaning(status: NodeStatus): string {
  return STATUS_MEANINGS[status];
}

export function statusRemedy(status: NodeStatus): string {
  return STATUS_REMEDIES[status];
}

export function statusTone(status: NodeStatus): Tone {
  return STATUS_TONES[status];
}

export function isRetryable(status: NodeStatus): boolean {
  return RETRYABLE[status];
}

/** `ok` is the unremarkable case and earns no badge; everything else does. */
export function showsStatusBadge(status: NodeStatus): boolean {
  return status !== "ok";
}

/** A branch that did not answer must never be drawn as an answered empty one. */
export function answered(status: NodeStatus): boolean {
  return status === "ok" || status === "empty";
}

export const CONTENT_KIND_LABEL: Record<ContentKind, string> = {
  none: "No contents",
  rows: "Rows",
  json: "JSON",
};

export const SOURCE_TYPE_LABEL: Record<SourceType, string> = {
  adx_table: "ADX table",
  gremlin_graph: "Cosmos graph",
  search_index: "Azure AI Search index",
  local_table: "Local table",
};

export function detailValueText(value: DetailValue): string {
  if (value === null) return NULL_VALUE_LABEL;
  if (value === "") return EMPTY_VALUE_LABEL;
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "number") return value.toLocaleString("en");
  return value;
}

/** One scoped class per tone. Defined in `inventory.css`, not in a framework. */
export const TONE_CLASS: Record<Tone, string> = {
  neutral: "inv-tone-neutral",
  muted: "inv-tone-muted",
  flow: "inv-tone-flow",
  warning: "inv-tone-warning",
  critical: "inv-tone-critical",
};

/** A human label for a coordinate key, so the pane is not a bag of slugs. */
const COORDINATE_LABELS: Record<string, string> = {
  endpoint: "Endpoint",
  database: "Database",
  table: "Table",
  account: "Account",
  graph: "Graph",
  index: "Index",
};

export function coordinateLabel(key: string): string {
  return COORDINATE_LABELS[key] ?? key;
}

const METRIC_LABELS: Record<string, string> = {
  row_count: "Rows",
  column_count: "Columns",
  vertices: "Vertices",
  edges: "Edges",
  document_count: "Documents",
};

export function metricLabel(key: string): string {
  return METRIC_LABELS[key] ?? key;
}
