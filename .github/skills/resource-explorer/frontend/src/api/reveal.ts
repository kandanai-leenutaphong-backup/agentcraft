/**
 * Positioning a search hit inside the tree.
 *
 * Node ids are opaque, so no ancestor id can be derived from a hit. What can
 * be done is walk down from the root using values the server itself sent: the
 * hit's resource group name, then the ARM type each `resource_type` node
 * declares in its own detail, then the hit's label. Nothing is constructed and
 * nothing is parsed out of a token.
 */

import type { SearchHit, TreeNode } from "./wire";

export function pickByLabel(children: TreeNode[], label: string): TreeNode | null {
  const wanted = label.toLowerCase();
  return children.find((child) => child.label.toLowerCase() === wanted) ?? null;
}

/**
 * A `resource_type` node labels itself `Type (n)` and repeats the bare type in
 * `detail.type`. The detail is matched first because the label carries a count
 * that changes as the estate does.
 */
export function pickResourceType(
  children: TreeNode[],
  armType: string,
): TreeNode | null {
  const wanted = armType.toLowerCase();
  const byDetail = children.find(
    (child) =>
      child.kind === "resource_type" &&
      String(child.detail?.["type"] ?? "").toLowerCase() === wanted,
  );
  if (byDetail !== undefined) return byDetail;
  const prefix = `${wanted} (`;
  return (
    children.find(
      (child) =>
        child.kind === "resource_type" && child.label.toLowerCase().startsWith(prefix),
    ) ?? null
  );
}

/** How deep the walk has to go for this hit. */
export function revealDepth(hit: SearchHit): 1 | 3 {
  return hit.kind === "resource_group" ? 1 : 3;
}
