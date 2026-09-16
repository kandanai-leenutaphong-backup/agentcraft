/**
 * The frontend half of the inventory component, as one import.
 *
 * A host imports from `@agentcraft/resource-explorer` and nothing
 * deeper; that alias is declared in the host's `tsconfig`, its Vite config and
 * `architecture.json`, so a reach past this barrel is visible to the
 * architecture checker rather than merely discouraged.
 *
 * Styles load with this barrel and stay scoped under `inv-` or `rex-`.
 */

import "./inventory.css";
import "./explorer.css";

export { ResourceExplorer, AgentToolDetail } from "./ResourceExplorer";
export { ExplorerLayout } from "./ExplorerLayout";
export type { ExplorerLayoutProps } from "./ExplorerLayout";
export type { ResourceExplorerProps, AgentCatalogueEntry, AgentToolInfo, AgentDatasource } from "./ResourceExplorer";
export { InventoryExplorer } from "./InventoryExplorer";
export type { InventoryExplorerProps } from "./InventoryExplorer";
export { TreeView } from "./TreeView";
export type { TreeViewProps } from "./TreeView";
export { DetailPane } from "./DetailPane";
export type { DetailPaneProps } from "./DetailPane";
export { RowsTable } from "./RowsTable";
export type { RowsTableProps } from "./RowsTable";
export { StatusBadge, StatusNote } from "./StatusNote";
export type { StatusNoteProps } from "./StatusNote";

export {
  createClient,
  DEFAULT_BASE,
  SourceDisabledError,
  StaleSelectionError,
} from "./client";
export type { ClientOptions, InventoryClient } from "./client";

export {
  ALL_SELECTED,
  SELECTION_HEADER,
  STORAGE_KEY,
  enabledIds,
  isEnabled,
  prune,
  readSelection,
  selectAll,
  selectNone,
  selectionHeader,
  toggle,
  writeSelection,
} from "./selection";
export type { StoredSelection } from "./selection";

export { HANDLED_KEYS, keyboardMove } from "./keyboard";
export type { KeyMove } from "./keyboard";

export {
  descendantIds,
  effectiveActiveId,
  findRow,
  initialState,
  pendingLoads,
  reducer,
  rowIndex,
  selectedNode,
  visibleRows,
} from "./state";
export type { Action, Expansion, InventoryState, Row } from "./state";

export {
  ABSENT_CELL,
  MAX_CELL_CHARS,
  NULL_CELL,
  cellText,
  columnsOf,
  compareValues,
  nextSort,
  sortAriaValue,
  sortRows,
  truncateCell,
} from "./rows";
export type { SortDirection, SortState } from "./rows";

export {
  CONTENT_KIND_LABEL,
  EMPTY_VALUE_LABEL,
  LOADING_LABEL,
  NULL_VALUE_LABEL,
  SOURCE_TYPE_LABEL,
  TONE_CLASS,
  answered,
  coordinateLabel,
  detailValueText,
  isRetryable,
  metricLabel,
  showsStatusBadge,
  statusLabel,
  statusMeaning,
  statusRemedy,
  statusTone,
} from "./status";
export type { Tone } from "./status";

export {
  CONTENT_KINDS,
  NODE_KINDS,
  NODE_STATUSES,
  ROOT_ID,
  SOURCE_TYPES,
  parseContent,
  parseResource,
  parseSelection,
  parseTree,
  parseTreeNode,
} from "./wire";
export type {
  ConnectorIdentity,
  ContentKind,
  ContentResponse,
  DetailValue,
  NodeKind,
  NodeStatus,
  ResourceResponse,
  SchemaField,
  SelectionMode,
  SelectionResponse,
  SelectionSource,
  SourceType,
  TreeNode,
  TreeResponse,
} from "./wire";
