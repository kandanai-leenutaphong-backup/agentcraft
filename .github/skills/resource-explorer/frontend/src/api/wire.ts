/**
 * The wire boundary. `contracts/tree.schema.json` is the authority; this file
 * is its TypeScript reading, and nothing downstream of a `parse*` function
 * touches an unvalidated value.
 *
 * A malformed payload is a thrown `MalformedResponse`, never a partially
 * trusted object: the surface renders the failure against one node and keeps
 * the rest of the estate on screen.
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

export const NODE_KINDS = [
  "root",
  "resource_group",
  "resource_type",
  "resource",
  "collection",
  "arm_child",
  "properties",
  "blob_container",
  "blob_folder",
  "blob",
  "cosmos_database",
  "cosmos_container",
  "gremlin_database",
  "gremlin_graph",
  "kusto_database",
  "kusto_table",
  "search_index",
  "search_field",
  "log_table",
  "registry_repository",
  "registry_tag",
] as const;

export type NodeKind = (typeof NODE_KINDS)[number];

export const CONTENT_KINDS = [
  "none",
  "text",
  "json",
  "csv",
  "markdown",
  "image",
  "binary",
  "rows",
] as const;

export type ContentKind = (typeof CONTENT_KINDS)[number];

export type DetailValue = string | number | boolean | null;

export interface TreeNode {
  id: string;
  label: string;
  kind: NodeKind;
  expandable: boolean;
  hasContent: boolean;
  status: NodeStatus;
  detail: Record<string, DetailValue> | null;
  error: string | null;
}

export interface TreeResponse {
  schemaVersion: 1;
  fixtures: boolean;
  node: string;
  label: string;
  kind: NodeKind;
  breadcrumb: string[];
  status: NodeStatus;
  children: TreeNode[];
  truncated: boolean;
  hasContent: boolean;
  detail: Record<string, DetailValue> | null;
  error: string | null;
  observedAt: string;
}

export interface ContentResponse {
  schemaVersion: 1;
  fixtures: boolean;
  node: string;
  label: string;
  kind: NodeKind;
  breadcrumb: string[];
  status: NodeStatus;
  contentKind: ContentKind;
  mediaType: string;
  text: string | null;
  dataBase64: string | null;
  rows: Record<string, unknown>[] | null;
  columns: string[] | null;
  sizeBytes: number;
  truncated: boolean;
  detail: Record<string, DetailValue> | null;
  error: string | null;
  observedAt: string;
}

export interface SearchHit {
  node: string;
  label: string;
  kind: NodeKind;
  resourceGroup: string;
  type: string;
  location: string;
  matchedIn: string;
  detail: Record<string, DetailValue> | null;
}

export interface SearchResponse {
  schemaVersion: 1;
  fixtures: boolean;
  query: string;
  status: NodeStatus;
  hits: SearchHit[];
  truncated: boolean;
  error: string | null;
  observedAt: string;
}

export class MalformedResponse extends Error {
  constructor(field: string) {
    super(`The server sent a payload this client cannot read (${field}).`);
    this.name = "MalformedResponse";
  }
}

export class SessionExpired extends Error {
  constructor() {
    super("The sign-in session is no longer valid.");
    this.name = "SessionExpired";
  }
}

/** The server refused an id or a term this client sent. Retrying it is pointless. */
export class RejectedRequest extends Error {
  readonly code: "invalid_node" | "invalid_query" | "invalid_limit";

  constructor(code: "invalid_node" | "invalid_query" | "invalid_limit", message: string) {
    super(message);
    this.name = "RejectedRequest";
    this.code = code;
  }
}

function asRecord(value: unknown, field: string): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new MalformedResponse(field);
  }
  return value as Record<string, unknown>;
}

function asString(value: unknown, field: string): string {
  if (typeof value !== "string") throw new MalformedResponse(field);
  return value;
}

function asBoolean(value: unknown, field: string): boolean {
  if (typeof value !== "boolean") throw new MalformedResponse(field);
  return value;
}

function asNumber(value: unknown, field: string): number {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new MalformedResponse(field);
  }
  return value;
}

function asStatus(value: unknown, field: string): NodeStatus {
  const text = asString(value, field);
  const found = NODE_STATUSES.find((status) => status === text);
  if (found === undefined) throw new MalformedResponse(field);
  return found;
}

function asKind(value: unknown, field: string): NodeKind {
  const text = asString(value, field);
  const found = NODE_KINDS.find((kind) => kind === text);
  if (found === undefined) throw new MalformedResponse(field);
  return found;
}

function asContentKind(value: unknown, field: string): ContentKind {
  const text = asString(value, field);
  const found = CONTENT_KINDS.find((kind) => kind === text);
  if (found === undefined) throw new MalformedResponse(field);
  return found;
}

function asNullableString(value: unknown, field: string): string | null {
  if (value === null) return null;
  return asString(value, field);
}

function asStringArray(value: unknown, field: string): string[] {
  if (!Array.isArray(value)) throw new MalformedResponse(field);
  return value.map((entry, index) => asString(entry, `${field}[${index}]`));
}

function asDetail(value: unknown, field: string): Record<string, DetailValue> | null {
  if (value === null || value === undefined) return null;
  const source = asRecord(value, field);
  const detail: Record<string, DetailValue> = {};
  for (const [key, entry] of Object.entries(source)) {
    if (
      entry !== null &&
      typeof entry !== "string" &&
      typeof entry !== "number" &&
      typeof entry !== "boolean"
    ) {
      throw new MalformedResponse(`${field}.${key}`);
    }
    detail[key] = entry;
  }
  return detail;
}

function asTreeNode(value: unknown, field: string): TreeNode {
  const source = asRecord(value, field);
  return {
    id: asString(source["id"], `${field}.id`),
    label: asString(source["label"], `${field}.label`),
    kind: asKind(source["kind"], `${field}.kind`),
    expandable: asBoolean(source["expandable"], `${field}.expandable`),
    hasContent: asBoolean(source["hasContent"], `${field}.hasContent`),
    status: asStatus(source["status"], `${field}.status`),
    detail: asDetail(source["detail"], `${field}.detail`),
    error: asNullableString(source["error"], `${field}.error`),
  };
}

function requireVersion(source: Record<string, unknown>): void {
  if (source["schemaVersion"] !== 1) throw new MalformedResponse("schemaVersion");
}

export function parseTreeResponse(value: unknown): TreeResponse {
  const source = asRecord(value, "response");
  requireVersion(source);
  const rawChildren = source["children"];
  if (!Array.isArray(rawChildren)) throw new MalformedResponse("children");
  return {
    schemaVersion: 1,
    fixtures: asBoolean(source["fixtures"], "fixtures"),
    node: asString(source["node"], "node"),
    label: asString(source["label"], "label"),
    kind: asKind(source["kind"], "kind"),
    breadcrumb: asStringArray(source["breadcrumb"], "breadcrumb"),
    status: asStatus(source["status"], "status"),
    children: rawChildren.map((entry, index) => asTreeNode(entry, `children[${index}]`)),
    truncated: asBoolean(source["truncated"], "truncated"),
    hasContent: asBoolean(source["hasContent"], "hasContent"),
    detail: asDetail(source["detail"], "detail"),
    error: asNullableString(source["error"], "error"),
    observedAt: asString(source["observedAt"], "observedAt"),
  };
}

/** Row cells are arbitrary JSON; only the row container's shape is checked. */
function asRows(value: unknown, field: string): Record<string, unknown>[] | null {
  if (value === null || value === undefined) return null;
  if (!Array.isArray(value)) throw new MalformedResponse(field);
  return value.map((entry, index) => asRecord(entry, `${field}[${index}]`));
}

export function parseContentResponse(value: unknown): ContentResponse {
  const source = asRecord(value, "response");
  requireVersion(source);
  const rawColumns = source["columns"];
  return {
    schemaVersion: 1,
    fixtures: asBoolean(source["fixtures"], "fixtures"),
    node: asString(source["node"], "node"),
    label: asString(source["label"], "label"),
    kind: asKind(source["kind"], "kind"),
    breadcrumb: asStringArray(source["breadcrumb"], "breadcrumb"),
    status: asStatus(source["status"], "status"),
    contentKind: asContentKind(source["contentKind"], "contentKind"),
    mediaType: asString(source["mediaType"], "mediaType"),
    text: asNullableString(source["text"], "text"),
    dataBase64: asNullableString(source["dataBase64"], "dataBase64"),
    rows: asRows(source["rows"], "rows"),
    columns:
      rawColumns === null || rawColumns === undefined
        ? null
        : asStringArray(rawColumns, "columns"),
    sizeBytes: asNumber(source["sizeBytes"], "sizeBytes"),
    truncated: asBoolean(source["truncated"], "truncated"),
    detail: asDetail(source["detail"], "detail"),
    error: asNullableString(source["error"], "error"),
    observedAt: asString(source["observedAt"], "observedAt"),
  };
}

function asSearchHit(value: unknown, field: string): SearchHit {
  const source = asRecord(value, field);
  return {
    node: asString(source["node"], `${field}.node`),
    label: asString(source["label"], `${field}.label`),
    kind: asKind(source["kind"], `${field}.kind`),
    resourceGroup: asString(source["resourceGroup"], `${field}.resourceGroup`),
    type: asString(source["type"], `${field}.type`),
    location: asString(source["location"], `${field}.location`),
    matchedIn: asString(source["matchedIn"], `${field}.matchedIn`),
    detail: asDetail(source["detail"], `${field}.detail`),
  };
}

export function parseSearchResponse(value: unknown): SearchResponse {
  const source = asRecord(value, "response");
  requireVersion(source);
  const rawHits = source["hits"];
  if (!Array.isArray(rawHits)) throw new MalformedResponse("hits");
  return {
    schemaVersion: 1,
    fixtures: asBoolean(source["fixtures"], "fixtures"),
    query: asString(source["query"], "query"),
    status: asStatus(source["status"], "status"),
    hits: rawHits.map((entry, index) => asSearchHit(entry, `hits[${index}]`)),
    truncated: asBoolean(source["truncated"], "truncated"),
    error: asNullableString(source["error"], "error"),
    observedAt: asString(source["observedAt"], "observedAt"),
  };
}
