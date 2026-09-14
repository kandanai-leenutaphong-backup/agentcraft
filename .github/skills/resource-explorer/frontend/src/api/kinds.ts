/**
 * The twenty-one node kinds, as words a reader who has read no documentation
 * can act on.
 *
 * A kind is carried three ways at once — an icon, the kind word in the row's
 * accessible name, and a `data-kind` attribute — because a glyph alone is a
 * guess and a colour alone is unreadable.
 */

import type { NodeKind } from "./wire";

export type IconName =
  | "subscription"
  | "group"
  | "type"
  | "resource"
  | "collection"
  | "child"
  | "properties"
  | "bucket"
  | "folder"
  | "file"
  | "database"
  | "table"
  | "graph"
  | "index"
  | "field"
  | "logs"
  | "repository"
  | "tag";

export const KIND_LABEL: Record<NodeKind, string> = {
  root: "Subscription",
  resource_group: "Resource group",
  resource_type: "Resource type",
  resource: "Resource",
  collection: "Collection",
  arm_child: "ARM child",
  properties: "Properties",
  blob_container: "Blob container",
  blob_folder: "Blob folder",
  blob: "Blob",
  cosmos_database: "Cosmos database",
  cosmos_container: "Cosmos container",
  gremlin_database: "Gremlin database",
  gremlin_graph: "Gremlin graph",
  kusto_database: "Kusto database",
  kusto_table: "Kusto table",
  search_index: "Search index",
  search_field: "Search field",
  log_table: "Log Analytics table",
  registry_repository: "Registry repository",
  registry_tag: "Registry tag",
};

export const KIND_MEANING: Record<NodeKind, string> = {
  root: "The whole subscription. Opens into its resource groups.",
  resource_group: "One resource group. Opens into its resources, grouped by ARM type.",
  resource_type: "Every resource of one ARM type in this group.",
  resource: "One Azure resource. Always opens into its complete ARM properties.",
  collection: "A branch a resource type declares — containers, databases, indexes, tables.",
  arm_child: "A child resource ARM returns under its parent, such as a revision.",
  properties: "The resource's complete ARM document, as JSON.",
  blob_container: "A blob container. Opens into one prefix level of folders and blobs.",
  blob_folder: "A blob name prefix, shown as a folder.",
  blob: "One blob. Its bytes are typed and rendered.",
  cosmos_database: "A Cosmos SQL database. Opens into its containers.",
  cosmos_container: "A Cosmos container. Its documents are sampled as rows.",
  gremlin_database: "A Gremlin database. Opens into its graphs.",
  gremlin_graph: "A Gremlin graph. Its vertices are sampled as rows.",
  kusto_database: "A Data Explorer database. Opens into its tables.",
  kusto_table: "A Data Explorer table. Its rows are sampled.",
  search_index: "A Search index. Opens into its fields, and samples its documents.",
  search_field: "One field of a Search index, flattened as parent/child.",
  log_table: "A Log Analytics table. Its last seven days are sampled.",
  registry_repository: "A container registry repository. Opens into its tags.",
  registry_tag: "One image tag in a registry repository.",
};

export const KIND_ICON: Record<NodeKind, IconName> = {
  root: "subscription",
  resource_group: "group",
  resource_type: "type",
  resource: "resource",
  collection: "collection",
  arm_child: "child",
  properties: "properties",
  blob_container: "bucket",
  blob_folder: "folder",
  blob: "file",
  cosmos_database: "database",
  cosmos_container: "table",
  gremlin_database: "database",
  gremlin_graph: "graph",
  kusto_database: "database",
  kusto_table: "table",
  search_index: "index",
  search_field: "field",
  log_table: "logs",
  registry_repository: "repository",
  registry_tag: "tag",
};

/** Where a search matched, spelled out. `matchedIn` is a server-chosen word. */
export function matchedInLabel(matchedIn: string): string {
  switch (matchedIn) {
    case "name":
      return "matched on name";
    case "type":
      return "matched on resource type";
    case "resourceGroup":
      return "matched on resource group";
    case "location":
      return "matched on location";
    case "tags":
      return "matched on a tag";
    case "properties":
      return "matched inside its properties";
    default:
      return `matched on ${matchedIn}`;
  }
}
