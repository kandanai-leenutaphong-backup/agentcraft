/**
 * The three calls this browser makes. Nothing else leaves the origin: there is
 * no Azure endpoint, no SDK and no token here, only `/api/*` on the server
 * that already holds the identity.
 *
 * Node ids are opaque and server-minted. This client constructs none, parses
 * none, and derives nothing from one.
 */

import {
  MalformedResponse,
  parseContentResponse,
  parseSearchResponse,
  parseTreeResponse,
  RejectedRequest,
  ROOT_ID,
  SessionExpired,
  type ContentResponse,
  type SearchResponse,
  type TreeResponse,
} from "./wire";

export const SEARCH_LIMIT = 50;
export const MAX_SEARCH_TERM_CHARS = 200;

export function treeUrl(nodeId: string): string {
  return nodeId === ROOT_ID
    ? "/api/tree"
    : `/api/tree?node=${encodeURIComponent(nodeId)}`;
}

export function contentUrl(nodeId: string): string {
  return `/api/content?node=${encodeURIComponent(nodeId)}`;
}

export function searchUrl(term: string, limit: number = SEARCH_LIMIT): string {
  return `/api/search?q=${encodeURIComponent(term)}&limit=${String(limit)}`;
}

async function readJson(response: Response): Promise<unknown> {
  try {
    return (await response.json()) as unknown;
  } catch {
    throw new MalformedResponse("body");
  }
}

/** A 400 names its reason in the body; anything else is reported as it arrived. */
async function refuse(response: Response, fallback: string): Promise<never> {
  if (response.status === 401) throw new SessionExpired();
  if (response.status === 400) {
    let code: unknown = null;
    try {
      const body = (await response.json()) as { error?: unknown };
      code = body.error;
    } catch {
      code = null;
    }
    if (code === "invalid_node") {
      throw new RejectedRequest(
        "invalid_node",
        "The server no longer recognises this node id. Refresh the tree and open it again.",
      );
    }
    if (code === "invalid_query") {
      throw new RejectedRequest(
        "invalid_query",
        `A search term must be 1 to ${String(MAX_SEARCH_TERM_CHARS)} characters.`,
      );
    }
  }
  if (response.status === 422) {
    throw new RejectedRequest("invalid_limit", "The server rejected the result limit.");
  }
  throw new Error(`${fallback} (the server answered ${String(response.status)}).`);
}

async function get<T>(
  url: string,
  parse: (value: unknown) => T,
  fallback: string,
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch(url, {
    headers: { Accept: "application/json" },
    credentials: "same-origin",
    ...(signal ? { signal } : {}),
  });
  if (!response.ok) await refuse(response, fallback);
  return parse(await readJson(response));
}

export function fetchTree(nodeId: string, signal?: AbortSignal): Promise<TreeResponse> {
  return get(
    treeUrl(nodeId),
    parseTreeResponse,
    "This branch could not be expanded",
    signal,
  );
}

export function fetchContent(
  nodeId: string,
  signal?: AbortSignal,
): Promise<ContentResponse> {
  return get(
    contentUrl(nodeId),
    parseContentResponse,
    "These contents could not be read",
    signal,
  );
}

export function fetchSearch(
  term: string,
  signal?: AbortSignal,
): Promise<SearchResponse> {
  return get(
    searchUrl(term),
    parseSearchResponse,
    "The search could not be run",
    signal,
  );
}
