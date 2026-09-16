/**
 * The HTTP client. Four reads, each carrying this tab's selection header.
 *
 * ADAPTED from `resource_explorer/frontend/src/api/client.ts`. See
 * PROVENANCE.md. The `401`/session-expiry path is dropped — the host owns
 * authentication and this component must not grow a second story about it —
 * and two codes are added that upstream has no equivalent for: `409` when the
 * reader has switched this source off, and `400 invalid_selection` when the
 * tab is carrying an id the server no longer declares.
 *
 * Every call takes an `AbortSignal`. A pane that repopulates from a request
 * the reader has already moved on from is worse than an empty one.
 */

import {
  SELECTION_HEADER,
  selectionHeader,
  type StoredSelection,
} from "./selection";
import {
  parseContent,
  parseResource,
  parseSelection,
  parseTree,
  type ContentResponse,
  type ResourceResponse,
  type SelectionResponse,
  type TreeResponse,
} from "./wire";

export const DEFAULT_BASE = "/api/cyber/inventory";

/** The source is real and this tab switched it off. Recoverable by re-enabling. */
export class SourceDisabledError extends Error {
  constructor() {
    super("this source is switched off for this browser session");
    this.name = "SourceDisabledError";
  }
}

/** The stored selection names something the server does not. Recoverable by resetting. */
export class StaleSelectionError extends Error {
  constructor() {
    super("the stored selection no longer matches the declared sources");
    this.name = "StaleSelectionError";
  }
}

export interface ClientOptions {
  base?: string;
  fetchImpl?: typeof fetch;
}

async function read<T>(
  path: string,
  selection: StoredSelection,
  parse: (raw: unknown) => T,
  signal: AbortSignal | undefined,
  options: ClientOptions,
): Promise<T> {
  const base = options.base ?? DEFAULT_BASE;
  const call = options.fetchImpl ?? fetch;
  const response = await call(`${base}${path}`, {
    method: "GET",
    headers: {
      Accept: "application/json",
      [SELECTION_HEADER]: selectionHeader(selection),
    },
    // The payload names the stores this deployment reads. Never from a cache.
    cache: "no-store",
    signal,
  });
  if (response.status === 409) throw new SourceDisabledError();
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => ({}));
    const code =
      typeof body === "object" && body !== null && "error" in body
        ? String((body as { error: unknown }).error)
        : "";
    if (code === "invalid_selection") throw new StaleSelectionError();
    throw new Error(code ? `${code} (HTTP ${String(response.status)})` : `HTTP ${String(response.status)}`);
  }
  return parse(await response.json());
}

export function createClient(options: ClientOptions = {}) {
  return {
    tree: (node: string, selection: StoredSelection, signal?: AbortSignal): Promise<TreeResponse> =>
      read(`/tree?node=${encodeURIComponent(node)}`, selection, parseTree, signal, options),
    resource: (
      node: string,
      selection: StoredSelection,
      signal?: AbortSignal,
    ): Promise<ResourceResponse> =>
      read(`/resource?node=${encodeURIComponent(node)}`, selection, parseResource, signal, options),
    content: (
      node: string,
      selection: StoredSelection,
      limit: number,
      signal?: AbortSignal,
    ): Promise<ContentResponse> =>
      read(
        `/content?node=${encodeURIComponent(node)}&limit=${String(limit)}`,
        selection,
        parseContent,
        signal,
        options,
      ),
    selection: (
      selection: StoredSelection,
      signal?: AbortSignal,
    ): Promise<SelectionResponse> =>
      read("/selection", selection, parseSelection, signal, options),
  };
}

export type InventoryClient = ReturnType<typeof createClient>;
