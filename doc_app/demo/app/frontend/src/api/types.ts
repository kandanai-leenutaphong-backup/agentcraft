/**
 * TypeScript types mirroring the backend Pydantic models.
 *
 * Module role:
 *   The frontend's single source of truth for API shapes. Every interface
 *   here corresponds to a Pydantic model on the backend. Changes to backend
 *   models MUST be reflected here to maintain wire-level type safety; there
 *   is no codegen step.
 *
 * Type groups (illustrative; this file declares more — read the file):
 *   - Enums        : Role, MessageStatus, StreamEventType, ToolCallStatus
 *   - Content      : ContentPart (text | tool_call)
 *   - Core models  : ToolCall, ApiMessage, Message, Session, SessionSummary
 *   - API I/O      : ChatRequest, CreateSessionRequest, UpdateSessionRequest
 *   - SSE events   : StreamMetadata + the StreamEventType union
 *
 * Backend source of truth:
 *   - foundation/models.py         — Pydantic models (Role, Message, ToolCall,
 *                                    Session, StreamEventType, etc.)
 *   - hosting/fastapi/routers/chat.py — SSE event names (`event: <name>`)
 *
 * Key consumers:
 *   - api/client.ts + api/*Api.ts  — request/response signatures
 *   - stores/chatStore.ts          — Message, ContentPart, StreamMetadata
 *   - stores/sessionStore.ts       — Session, SessionSummary
 *   - features/chat/messageModels.ts — ApiMessage → ChatMessage normalisation
 */

// ── Enums ───────────────────────────────────────────────────────────────────

export type Role = "system" | "user" | "assistant" | "tool";

export type MessageStatus =
  | "pending"
  | "streaming"
  | "complete"
  | "error"
  | "aborted";

export type AgentRunStatus =
  | "queued"
  | "running"
  | "complete"
  | "error"
  | "aborted";

export type StreamEventType =
  | "token"
  | "tool_call_start"
  | "tool_call_delta"
  | "tool_call_end"
  | "tool_result"
  | "citation"
  | "error"
  | "done"
  | "aborted"
  | "metadata"
  | "rate_limited"
  | "keepalive"
  | "delegation_start"
  | "delegation_token"
  | "delegation_tool_start"
  | "delegation_tool_delta"
  | "delegation_tool_end"
  | "delegation_tool_result"
  | "delegation_done"
  | "delegation_error"
  | "background_start"
  | "background_token"
  | "background_tool_start"
  | "background_tool_delta"
  | "background_tool_end"
  | "background_tool_result"
  | "background_done"
  | "background_error"
  | "background_aborted";

// ── Tool Calls ──────────────────────────────────────────────────────────────

export type ToolCallStatus = "pending" | "running" | "complete" | "error";

export interface ToolCall {
  id: string;
  name: string;
  arguments: Record<string, unknown>;
  result?: string | null;
  status: ToolCallStatus;
  summary?: string;
  duration_ms?: number | null;
  /** Epoch ms when this tool call started — used for live timer persistence across tab switches. */
  start_ms?: number | null;
  /**
   * Partial JSON argument string accumulated from TOOL_CALL_DELTA events
   * before the call closes. Cleared when ``arguments`` is installed by
   * TOOL_CALL_END. Never persisted — transient render-only state used
   * by ToolCallDisplay to show character-by-character growth.
   */
  pendingArgsRaw?: string;
}

// ── Content Parts (ordered, interleaved rendering) ──────────────────────────

export type ContentPart =
  | { type: "text"; text: string }
  | { type: "tool_call"; toolCall: ToolCall }

// ── Messages ────────────────────────────────────────────────────────────────

export interface ApiMessage {
  id: string;
  role: Role;
  content: string;
  parts?: ContentPart[] | null;      // transport field; normalized by messageModels.ts
  status: MessageStatus;
  tool_calls: ToolCall[];
  agent_name: string;          // Which agent authored this message
  context_snapshot?: Record<string, unknown> | null;  // Audit record of LLM context
  created_at: string; // ISO 8601
  /** True when this message is a delegation task from the controller, not from the user. */
  _isDelegation?: boolean;
}

export interface Message extends ApiMessage {
  parts: ContentPart[];
}

// ── Agent Threads ───────────────────────────────────────────────────────────

/** Per-agent conversation thread within a session (schema v3). */
export interface AgentThread {
  agent_session_id: string;
  agent_id: string;
  agent_name: string;
  messages: ApiMessage[];
  created_at: string;
}

export interface BackgroundAgentRun {
  run_id: string;
  agent_id: string;
  source_agent_id: string;
  status: AgentRunStatus;
  requested_task: string;
  queued_at: string;
  started_at?: string | null;
  completed_at?: string | null;
  error?: string | null;
}

export type SummarySourceKind = "user_message" | "agent_message" | "tool_call" | "tool_result" | "panel_action" | "lifecycle";
export type SummaryConfidence = "low" | "medium" | "high";
export type SummarizerStatus = "idle" | "queued" | "running" | "error";

export interface SummarySourceEvent {
  event_id: string;
  session_id: string;
  agent_id: string;
  kind: SummarySourceKind;
  event_type: string;
  source_id: string;
  payload_preview: string;
  observed_at: string;
}

export interface SituationSummary {
  headline: string;
  bullets: string[];
  open_questions: string[];
  confidence: SummaryConfidence;
  source_event_ids: string[];
  updated_at: string;
}

export interface SummaryRevision {
  revision_id: string;
  sequence: number;
  summary: SituationSummary;
  trigger_event_ids: string[];
  created_at: string;
}

export interface SummaryState {
  status: SummarizerStatus;
  current: SituationSummary | null;
  revisions: SummaryRevision[];
  processed_event_ids: string[];
  pending_event_ids: string[];
  last_error: string | null;
}

export type PriorityActionStatus = "pending" | "completed" | "declined";

export interface PriorityActionDecision {
  action_id: string;
  status: PriorityActionStatus;
  note: string;
  action_text: string;
  reasoning: string;
  guide: string;
  priority: number;
  actor_user_id: string;
  actor_name: string;
  updated_at: string;
}

export interface PriorityActionTimelineEntry {
  event_id: string;
  action_id: string;
  status: PriorityActionStatus;
  note: string;
  action_text: string;
  reasoning: string;
  guide: string;
  priority: number;
  actor_user_id: string;
  actor_name: string;
  created_at: string;
}

export interface PriorityActionState {
  decisions: Record<string, PriorityActionDecision>;
  timeline: PriorityActionTimelineEntry[];
}

// ── Agent Info ──────────────────────────────────────────────────────────────

/** Agent metadata returned by GET /api/agents. */
export interface AgentInfo {
  id: string;
  name: string;
  description: string;
  tools: string[];
  is_default: boolean;
  tool_count: number;
  headshot_url?: string | null;
  full_body_url?: string | null;
  product_summary?: string | null;
  powered_by?: {
    logo_url: string;
    label: string;
    description: string;
  }[];
}

// ── Sessions ────────────────────────────────────────────────────────────────

export interface Session {
  id: string;
  title: string;
  schema_version: number;
  scenario_name: string;
  user_id: string;
  threads: Record<string, AgentThread>;  // keyed by agent_id (schema v3)
  background_runs: Record<string, BackgroundAgentRun>;
  summary_state?: SummaryState;
  priority_action_state?: PriorityActionState;
  created_at: string;
  updated_at: string;
}

export interface SessionSummary {
  id: string;
  title: string;
  scenario_name: string;
  user_id: string;
  message_count: number;
  tool_call_count: number;
  user_prompt_count: number;
  agent_response_count: number;
  created_at: string;
  updated_at: string;
}

// ── API Requests ────────────────────────────────────────────────────────────

export interface ChatRequest {
  content: string;
  max_context_turns?: number | null;
}

export interface CreateSessionRequest {
  title?: string;
}

export interface UpdateSessionRequest {
  title: string;
}

export interface PriorityActionDecisionRequest {
  status: PriorityActionStatus;
  note?: string;
  action_text?: string;
  reasoning?: string;
  guide?: string;
  priority?: number;
}

// ── SSE Events ──────────────────────────────────────────────────────────────

export interface StreamMetadata {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  duration_ms: number;
  model: string;
  assistant_message_id: string;
  estimated_cost_usd?: number | null;
}

// ── Scenarios ───────────────────────────────────────────────────────────────

/** Scenario info returned by GET /api/scenarios. */
export interface ScenarioInfo {
  name: string;
  display_name: string;
  description: string;
  has_topology: boolean;
  is_active: boolean;
}

export interface ReplayTourStep {
  title: string;
  body: string;
  cta: string;
  agentImage?: string;
  poweredBy?: {
    logoSrc: string;
    label: string;
    description: string;
  };
}

export interface ReplayHighlight {
  title: string;
  body: string;
}

export interface ScenarioDetail {
  scenario_name: string;
  display_name: string;
  description: string;
  domain: string;
  version: string;
  use_cases: string[];
  example_questions: string[];
  graph_schema?: {
    vertices: { label: string; properties: string[] }[];
    edges: { label: string; source: string; target: string }[];
  };
  demo_flows?: {
    title: string;
    steps: { prompt: string }[];
  }[];
  replay_tour?: ReplayTourStep[];
  replay_tour_detailed?: ReplayTourStep[];
  replay_highlights?: Record<string, ReplayHighlight>;
  replay_conversation_url?: string | null;
}

// ── Auth (continued) ────────────────────────────────────────────────────────

/** Response from GET /api/auth_setup — MSAL configuration for the frontend. */
export interface AuthSetupResponse {
  useLogin: boolean;
  clientId?: string;
  authority?: string;
  scopes?: string[];
}

