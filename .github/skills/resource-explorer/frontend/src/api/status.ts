/**
 * Every state this surface can show, as words.
 *
 * A dark branch that renders as an empty one throws away the operator's whole
 * diagnosis, so each status carries a name, a meaning and who can fix it.
 * Colour is decoration on top of the text and never the only carrier: two
 * statuses share the warning tone and are still told apart by their words.
 */

import type { ContentKind, DetailValue, NodeStatus } from "./wire";

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
  unconfigured: "A coordinate nobody set. The cause below names it.",
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
  text: "Text",
  json: "JSON",
  csv: "Delimited text",
  markdown: "Markdown",
  image: "Image",
  binary: "Binary",
  rows: "Rows",
};

export function detailValueText(value: DetailValue): string {
  if (value === null) return NULL_VALUE_LABEL;
  if (value === "") return EMPTY_VALUE_LABEL;
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "number") return String(value);
  return value;
}

export const TONE_BADGE: Record<Tone, string> = {
  neutral: "border-border text-secondary",
  muted: "border-border-soft text-muted",
  flow: "border-flow text-flow",
  warning: "border-warning text-warning",
  critical: "border-critical text-critical",
};

export const TONE_PANEL: Record<Tone, string> = {
  neutral: "border-border bg-surface",
  muted: "border-border-soft bg-canvas2",
  flow: "border-flow bg-flow-tint",
  warning: "border-warning bg-warning-tint",
  critical: "border-critical bg-critical-tint",
};

export const TONE_TEXT: Record<Tone, string> = {
  neutral: "text-secondary",
  muted: "text-muted",
  flow: "text-flow",
  warning: "text-warning",
  critical: "text-critical",
};
