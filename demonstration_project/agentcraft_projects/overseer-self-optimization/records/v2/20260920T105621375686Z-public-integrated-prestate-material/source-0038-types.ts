export type Severity = "critical" | "high" | "medium" | "low";

export type { AgentCatalogueEntry, AgentToolInfo } from "@agentcraft/resource-explorer";

/** Derived by the backend from the rule's own KQL — never authored prose. */
export interface RuleExplanation {
  rule_id: string;
  version: string;
  role: string;
  score: number;
  threshold: number;
  source_table: string;
  time_predicate: string;
  filters: string[];
  derived_fields: string[];
  aggregations: string[];
  group_by: string[];
  qualification: string[];
  projection: string[];
  ordering: string[];
  pipeline_steps: number;
}

/** Derived by the backend from what the executed rule actually returned. */
export interface RuleObservation {
  groups_returned: number;
  groups_qualified: number;
  threshold_expression: string;
  max_group_count: number;
  elapsed_ms: number;
  entities: string[];
  outcome: "hit" | "miss";
}

export interface FactorObserved {
  entity: string;
  event_count: number;
  qualification_test: string;
  returned_columns: string[];
  evidence_ids_returned: number;
}

export type FactorDerivation = RuleExplanation & { observed: FactorObserved };

export interface MetricContribution {
  source: string;
  detail: string;
  value: string;
}

export type MetricId = "correlated_patterns" | "confidence" | "evidence_representations";

export interface SituationMetric {
  metric_id: MetricId | string;
  label: string;
  value: string;
  definition: string;
  derivation: string;
  contributions: MetricContribution[];
}

export interface RuleExecution {
  rule_id: string;
  version: string;
  name: string;
  role: string;
  hit_count: number;
  elapsed_ms: number;
  explanation: RuleExplanation;
  observation: RuleObservation;
}

export interface Pattern {
  detector: string;
  rule_id: string;
  rule_version: string;
  label: string;
  description: string;
  observed_fact: string;
  count: number;
  score: number;
  confidence: "high" | "medium" | "low";
  role: "anchor" | "corroborator" | "contextual";
  first_seen: string;
  last_seen: string;
  summary: string;
  evidence_columns: string[];
  evidence_ids: string[];
  evidence_semantics: string;
  behaviour_class?: string;
  technique_ids?: string[];
  derivation?: FactorDerivation;
}

export type RuleRunStatus = "pending" | "running" | "miss" | "hit";

export interface RuleRun {
  rule_id: string;
  version: string;
  label: string;
  description?: string;
  role?: "anchor" | "corroborator" | "contextual";
  evidence_semantics?: string;
  status: RuleRunStatus;
  hit_count?: number;
  elapsed_ms?: number;
  explanation?: RuleExplanation;
  observation?: RuleObservation;
}

export interface EvidenceRun {
  status: "pending" | "running" | "complete";
  evidence_count?: number;
}

export type ScanStreamEvent =
  | { type: "rule_started"; data: { rule_id: string; version: string; name: string; description: string; role: "anchor" | "corroborator" | "contextual"; evidence_semantics: string; explanation: RuleExplanation } }
  | { type: "rule_completed"; data: { rule_id: string; version: string; name: string; description: string; role: "anchor" | "corroborator" | "contextual"; evidence_semantics: string; hit_count: number; elapsed_ms: number; explanation: RuleExplanation; observation: RuleObservation } }
  | { type: "situation_partial"; data: Situation }
  | { type: "evidence_started"; data: { situation_id: string; rule_id: string } }
  | { type: "evidence_completed"; data: { situation_id: string; rule_id: string; evidence_count: number } }
  | { type: "situation"; data: Situation }
  | { type: "done"; data: ScanResponse }
  | { type: "error"; data: { error_code: string; message: string } };

export interface Situation {
  situation_id: string;
  host: string;
  principal: string;
  severity: Severity;
  confidence: "high" | "medium" | "low";
  first_seen: string;
  last_seen: string;
  detector_count: number;
  patterns: Pattern[];
  metrics?: SituationMetric[];
  status: "open" | "reviewed";
  historical_replay: true;
}

export interface ScanResponse {
  kind: "cybereye_scan";
  window_start: string;
  window_end: string;
  situations: Situation[];
  summary: {
    situations: number;
    critical: number;
    high: number;
    evidence_rows: number;
    elapsed_ms: number;
  };
  rule_executions?: RuleExecution[];
  historical_replay: true;
}

export interface SituationSummary {
  situation_id: string;
  summary: string;
  model: string;
  historical_replay: true;
  elapsed_ms: number;
}

export interface SituationCitation {
  type_id: string;
  label: string;
  source: string;
  path: string;
  commit: string;
}

export interface Scenario {
  id: string;
  name: string;
  start: string;
  end: string;
  description: string;
}

export interface QueryResult {
  columns: string[];
  rows: unknown[][];
  row_count: number;
  truncated: boolean;
  max_rows: number;
  elapsed_ms: number;
  client_request_id: string;
}

export interface ToolRun {
  id: string;
  name: string;
  displayName?: string;
  fallback?: boolean;
  args?: Record<string, unknown>;
  pendingArgs?: string;
  result?: unknown;
  status: "running" | "done" | "error";
  startedAt: number;
  durationMs?: number;
}

/**
 * The model's own summary of its reasoning for one step of a run.
 *
 * Narration, not analysis: it is never evidence, never a finding, and never reaches the
 * board, the sequence cards, or a recorded artefact. It exists only in the chat stream.
 */
export interface ReasoningBlock {
  id: string;
  text: string;
  done: boolean;
}

export interface SituationDiagnosis {
  situation_id: string;
  headline: string;
  narrative: string;
  assessment: string;
  confidence: "low" | "medium" | "high";
  supporting_observations: string[];
  would_change_the_call: string[];
  evidence_ids: string[];
  situation_type: string;
  situation_type_supported: boolean;
  citations: SituationCitation[];
  unsupported_citations: string[];
  model: string;
  elapsed_ms: number;
}

/** Where one evidence row came from, observed by the server as the tool ran. */
export interface EvidenceRetrieval {
  tool: string;
  display_name: string;
  datasource: string;
  query: string;
  retrieved_at: string;
  row_count: number;
}

export interface StepEvidence {
  evidence_id: string;
  record: Record<string, unknown>;
  retrieval: EvidenceRetrieval;
}

export interface SequenceStep {
  description: string;
  timestamp: string;
  evidence_ids: string[];
  evidence: StepEvidence[];
  //: Cited by the model but returned by no tool in this run.
  unsupported_evidence_ids: string[];
}

export interface SequenceStepEvent extends SequenceStep {
  situation_id: string;
  position: number;
}

export interface SituationSequence {
  situation_id: string;
  steps: SequenceStep[];
  ordering_note: string;
  model: string;
  elapsed_ms: number;
}

export interface GraphNode {
  id: string;
  label: string;
  name: string;
  event_count: number;
  first_seen: string;
  last_seen: string;
  properties: Record<string, unknown>;
}

export interface GraphEdge {
  id: string;
  label: string;
  kind: "structural" | "event";
  from: string;
  to: string;
  event_count: number;
  first_seen: string;
  last_seen: string;
  buckets: Record<string, number>;
  window_scoped?: boolean;
  properties: Record<string, unknown>;
}

export interface GraphEntity {
  id: string;
  label: string;
  name: string;
  event_count: number;
}

export interface GraphWindow {
  start: string;
  end: string;
}

export type GraphScope = "only" | "shared" | "all";

export interface GraphSlice {
  focus: string;
  depth?: number;
  scope?: GraphScope;
  selected?: string[];
  shared?: string[];
  nodes: GraphNode[];
  edges: GraphEdge[];
  truncated?: boolean;
  window?: { start: string; end: string; bucket_minutes: number };
}

export interface GraphOverview {
  nodes_by_label: Record<string, number>;
  edges_by_label: Record<string, number>;
  edges_by_kind: Record<string, number>;
  observed_window: { start: string; end: string };
  bucket_minutes: number;
  seeds: GraphNode[];
}

export interface GraphStatus {
  available: boolean;
  detail?: string;
  account?: string;
  database?: string;
  graph?: string;
  vertices?: number;
  edges?: number;
}

export interface AgentIdentity {
  id: string;
  name: string;
  model: string;
  version: number;
}

export interface ChatMessage {
  id: string;
  role: "user" | "agent";
  text: string;
  tools?: ToolRun[];
  reasoning?: ReasoningBlock[];
  activity?: string;
  notice?: string;
  agent?: AgentIdentity;
}

export interface RuleDefinition {
  rule_id: string;
  label: string;
  version: string;
  role: string;
  score: number;
  confidence: string;
  behaviour_class: string;
  threshold: number;
  technique_ids: string[];
  description: string;
}
