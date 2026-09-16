/**
 * The frontend half of the inventory component, as one import.
 *
 * A host imports from `@agentcraft/resource-explorer` and nothing
 * deeper. Package exports provide built ESM and declarations; hosts need no
 * source aliases into this library.
 *
 * Styles load with this barrel and stay scoped under `inv-` or `rex-`.
 */

import "./inventory.css";
import "./explorer.css";

export { ResourceExplorer, AgentToolDetail } from "./ResourceExplorer.js";
export { ExplorerLayout } from "./ExplorerLayout.js";
export type { ExplorerLayoutProps } from "./ExplorerLayout.js";
export type { ResourceExplorerProps, AgentCatalogueEntry, AgentToolInfo, AgentDatasource } from "./ResourceExplorer.js";
export { InventoryExplorer } from "./InventoryExplorer.js";
export type { InventoryExplorerProps } from "./InventoryExplorer.js";
export { TreeView } from "./TreeView.js";
export type { TreeViewProps } from "./TreeView.js";
export { DetailPane } from "./DetailPane.js";
export type { DetailPaneProps } from "./DetailPane.js";
export { RowsTable } from "./RowsTable.js";
export type { RowsTableProps } from "./RowsTable.js";
export { StatusBadge, StatusNote } from "./StatusNote.js";
export type { StatusNoteProps } from "./StatusNote.js";

export {
  createClient,
  DEFAULT_BASE,
  SourceDisabledError,
  StaleSelectionError,
} from "./client.js";
export type { ClientOptions, InventoryClient } from "./client.js";

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
} from "./selection.js";
export type { StoredSelection } from "./selection.js";

export { HANDLED_KEYS, keyboardMove } from "./keyboard.js";
export type { KeyMove } from "./keyboard.js";

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
} from "./state.js";
export type { Action, Expansion, InventoryState, Row } from "./state.js";

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
} from "./rows.js";
export type { SortDirection, SortState } from "./rows.js";

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
} from "./status.js";
export type { Tone } from "./status.js";

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
} from "./wire.js";
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
} from "./wire.js";
