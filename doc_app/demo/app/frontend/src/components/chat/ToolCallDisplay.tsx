/**
 * @module ToolCallDisplay
 *
 * Collapsible tool invocation card — renders a single tool call within
 * an assistant message bubble.
 *
 * Displays a compact header row with an emoji icon (mapped from
 * `TOOL_ICONS`), the tool name in monospace, and a status indicator:
 *   - `running`  — pulsing brand-colour dot + "Running…" label
 *   - `complete` — green check icon + one-line result summary
 *   - `error`    — red X icon + error description
 *
 * Clicking the header toggles an expand/collapse transition to reveal
 * the full tool arguments (JSON) and result payload (JSON) in
 * syntax-highlighted `<pre>` blocks.
 *
 * @props
 *   - `toolCall`    — the {@link ToolCall} object (name, arguments, result, status)
 *   - `isStreaming`  — whether the parent message is still streaming (affects status logic)
 *
 * @collaborators
 *   - lucide-react icons (CheckCircle2, XCircle, ChevronDown, ChevronRight)
 *
 * @dependents
 *   Rendered by {@link MessageBubble} for each `type: 'tool_call'` ContentPart.
 */

import { useState, useRef, useEffect, memo } from "react";
import { useAgentStore } from "@/stores/agentStore";
import {
  CheckCircle2,
  AlertTriangle,
  ChevronDown,
  ChevronRight,
} from "lucide-react";
import type { ToolCall } from "@/api/types";
import { getAgentHeadshot } from "@/utils/agentHeadshots";
import { getToolResultRenderer, getToolArgsRenderer, ArgumentsGrid } from "./tool-renderers";
import { useTypewriter } from "@/hooks/useTypewriter";

interface ToolCallDisplayProps {
  toolCall: ToolCall;
  isStreaming?: boolean;
}

const TOOL_ICONS: Record<string, string> = {
  get_schema_context: "🧭",
  query_graph: "🔍",
  query_ontology: "📋",
  query_grid_violations: "⚡",
  query_telemetry: "📊",
  search_incident_reports: "📚",
  search_incident_lessons: "📚",
  search_operator_manual: "📖",
  search_procedures: "📖",
  search_nearhit_reports: "📚",
  search_investigation_clues: "🔎",
  search_participants: "👥",
  search_station_contacts: "☎️",
  search_knowledge_base: "📖",
  search_runbooks: "📚",
  search_tickets: "🎫",
  search_equipment: "🧰",
  search_infra_specs: "📐",
  /* Watcher KQL investigation tools */
  find_asset: "🏭",
  find_alarms: "🚨",
  find_alerts: "🚨",
  find_scada: "📊",
  find_surveillance: "📡",
  find_traffic: "✈️",
  find_alarm_by_mrid: "🔎",
  find_connected_stations: "🔗",
  find_scada_changes: "⚡",
  find_event_timeline: "📅",
  find_station_assets: "🏭",
  find_station_summary: "🏭",
  pattern_history: "〰️",
  /* Graph CIM topology tools */
  graph_node: "🔍",
  graph_neighbors: "🔍",
  graph_find_remote_station: "🔍",
  graph_path: "🔍",
  graph_station_equipment: "🏭",
  graph_equipment_properties: "⚙️",
  graph_equipment_connections: "🔗",
  graph_bus_topology: "📊",
  graph_property_keys: "📋",
  /* Raw query fallbacks */
  query_kql: "💾",
  query_gremlin: "💾",
  /* GQL semantic layer (legacy) */
  get_nodes: "🔍",
  get_neighbors: "🔍",
  get_node_properties: "🔍",
  find_path: "🔍",
  count_nodes: "🔍",
  get_edges: "🔍",
  aggregate: "🔍",
  lookup_entity: "🔍",
  /* KQL semantic layer (legacy) */
  get_scada_readings: "⚡",
  get_scada_timeline: "⚡",
  summarize_scada: "⚡",
  get_scada_extremes: "⚡",
  get_alarm_sequence: "🚨",
  summarize_alarms: "🚨",
  get_entity_events: "🔗",
  verify_state: "🩺",
  push_situation_alert: "🚨",
  report_normal: "✅",
  /* Actions & panels */
  push_priority_action: "🎯",
  push_action: "🎯",
  /* grid_manager NER 4.2.3 verdict tool (replaces the retired
     push_classifier_verdict). */
  classify: "⚖️",
  set_investigation_plan: "🗺️",
  summarize_situation: "✨",
  update_disturbance_summary: "📡",
  update_operating_state: "🛡️",
  update_priority_actions: "🎯",
  dispatch_field_engineer: "🚀",
  call_engineer: "📞",
  send_incident_report: "📧",
  delegate_to_agent: "🤖",
  /* Phase 1 compound investigation tools (2026-05-18) — distinct icons
     so an 8-tool investigation sequence scans cleanly. */
  reconstruct_event_timeline_causal: "🕒",
  bus_zone_audit: "🛡️",
  breaker_fail_signature: "🚦",
  frequency_disturbance_profile: "〰️",
};

export const ToolCallDisplay = memo(function ToolCallDisplay({
  toolCall,
  isStreaming = false,
}: ToolCallDisplayProps) {
  const [expanded, setExpanded] = useState(false);
  const [elapsedMs, setElapsedMs] = useState(0);
  /* Track whether the user has manually toggled the card so the
     auto-expand-while-running behaviour does not fight a deliberate
     collapse. The auto-open only fires the first time we see the box
     in a running state. */
  const userToggledRef = useRef(false);
  const rootRef = useRef<HTMLDivElement>(null);
  /* Stable id for the expandable body region so the toggle button can
     advertise `aria-controls` (R7 a11y). useState rather than useId so
     SSR is irrelevant — this is a client-only component. */
  const bodyIdRef = useRef(
    `tool-card-body-${Math.random().toString(36).slice(2, 10)}`,
  );
  const icon = TOOL_ICONS[toolCall.name] ?? "\uD83D\uDD27";
  const hasResult = !!toolCall.result;
  const isRunning = toolCall.status === "running" || (isStreaming && !hasResult);
  const isError = toolCall.status === "error";
  const hasArgs = Object.keys(toolCall.arguments).length > 0;
  /* Real-time partial JSON buffer streamed via TOOL_CALL_DELTA events.
     When set we render the raw text under <pre data-testid='tool-args-raw'>
     so operators see character-by-character growth as the model emits
     the call. Once the buffer parses cleanly the reducer installs
     ``arguments`` and clears this field, swapping the view to the
     structured ArgumentsGrid. */
  const pendingRaw = toolCall.pendingArgsRaw ?? "";
  const hasPendingRaw = isRunning && pendingRaw.length > 0;

  /* Auto-expand when a replay highlight targets this card. */
  useEffect(() => {
    const el = rootRef.current;
    if (!el) return;
    const handler = () => setExpanded(true);
    el.addEventListener("replay-expand", handler);
    return () => el.removeEventListener("replay-expand", handler);
  }, []);

  /* Auto-expand while the tool is running so the operator sees activity
     immediately — args streaming in, then the result arriving — instead
     of staring at a collapsed box wondering whether the chat hung.
     Once the result lands the card auto-collapses (unless the user
     manually toggled it open). */
  useEffect(() => {
    if (userToggledRef.current) return;
    if (isRunning) setExpanded(true);
    else if (hasResult) setExpanded(false);
  }, [isRunning, hasResult]);

  // Live timer for running tool calls — uses toolCall.start_ms so the
  // elapsed time persists across tab switches (component unmount/remount).
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  useEffect(() => {
    if (isRunning && !toolCall.duration_ms) {
      // Use the persisted start timestamp from the store, not Date.now().
      // This prevents the timer from resetting to 0 on tab switch.
      const start = toolCall.start_ms ?? Date.now();
      // Set initial elapsed immediately (non-zero on remount)
      setElapsedMs(Date.now() - start);
      intervalRef.current = setInterval(() => setElapsedMs(Date.now() - start), 100);
      return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
    }
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [isRunning, toolCall.duration_ms, toolCall.start_ms]);

  // Duration to display: persisted duration_ms, or live elapsed
  const displayDuration = toolCall.duration_ms ?? (isRunning ? elapsedMs : null);

  // Extract agent_id from delegation tool arguments (for "View Tab" button)
  const delegationAgentId = toolCall.name === "delegate_to_agent"
    ? (toolCall.arguments.agent_id as string) ?? null
    : null;

  // For delegate_to_agent, resolve the target agent's headshot
  const agents = useAgentStore((s) => s.agents);
  const delegationAgent = delegationAgentId
    ? agents.find((a) => a.id === delegationAgentId)
    : null;
  const delegationIcon = delegationAgent
    ? (delegationAgent.headshot_url ?? getAgentHeadshot(delegationAgent.name))
    : (delegationAgentId ? getAgentHeadshot(delegationAgentId) : null);

  // Resolve human-readable tool name from config, fall back to function name
  const toolDisplayNames = useAgentStore((s) => s.toolDisplayNames);
  const displayName = toolDisplayNames[toolCall.name] ?? toolCall.name;

  return (
    <div ref={rootRef} data-tool-id={toolCall.id} data-spotlight-id={`tool-${toolCall.id}`} className="my-px rounded-md border border-border bg-neutral-bg2 overflow-hidden transition-all [font-size:inherit]">
      {/* Header row */}
      <div className="flex items-center">
        {/* View Reasoning button — delegation tool only */}
        {delegationAgentId && (
          <button
            onClick={(e) => {
              e.stopPropagation();
              useAgentStore.getState().viewDelegatedTab(delegationAgentId);
            }}
            className="shrink-0 px-2 py-1.5 text-label font-medium text-brand hover:bg-brand/10 border-r border-border transition-colors"
            title={`View ${delegationAgentId} reasoning`}
          >
            View Reasoning
          </button>
        )}

        {/* Expand/collapse toggle — rest of header */}
        <button
          onClick={() => {
            userToggledRef.current = true;
            setExpanded(!expanded);
          }}
          aria-expanded={expanded}
          aria-controls={bodyIdRef.current}
          className="flex flex-1 items-center gap-1.5 px-2 py-1 hover:bg-neutral-bg3 transition-colors text-left min-w-0"
        >
        {delegationIcon ? (
          <img
            src={delegationIcon}
            alt=""
            className="h-10 w-10 rounded-full object-cover shrink-0"
            onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
          />
        ) : (
          /* R7 a11y: emoji is decorative — the tool name text below is
             the accessible name. Hide from screen readers. */
          <span aria-hidden="true" className="shrink-0">{icon}</span>
        )}
        <div className="flex flex-col min-w-0 flex-1">
          <span className="font-medium text-text-primary truncate">
            {displayName}
          </span>
          {/* Intention subtitle — shows why the model is calling this tool */}
          {typeof toolCall.arguments.intention === "string" && toolCall.arguments.intention && (
            <span className="text-label text-text-muted truncate">
              {toolCall.arguments.intention}
            </span>
          )}
        </div>

        {/* Duration timer */}
        {displayDuration != null && (
          <span className="text-label font-mono text-text-muted tabular-nums">
            {(displayDuration / 1000).toFixed(1)}s
          </span>
        )}

        {/* Status indicator — icon only, no summary text */}
        {isRunning && (
          <span className="h-1.5 w-1.5 rounded-full bg-brand animate-pulse ml-auto shrink-0" />
        )}
        {hasResult && !isError && (
          <CheckCircle2 className="h-3.5 w-3.5 text-status-success shrink-0 ml-auto" />
        )}
        {isError && (
          <AlertTriangle className="h-3.5 w-3.5 text-status-warning shrink-0 ml-auto" />
        )}

        {/* Chevron */}
        {expanded ? (
          <ChevronDown className="h-3.5 w-3.5 text-text-muted shrink-0" />
        ) : (
          <ChevronRight className="h-3.5 w-3.5 text-text-muted shrink-0" />
        )}
      </button>
      </div>

{/* Expandable detail — uses specialized renderers. The id matches
         `aria-controls` on the toggle button above (R7 a11y). */}
      {expanded && (
        <div id={bodyIdRef.current} className="border-t border-border px-2 py-1 space-y-1">
          {/* Arguments — custom renderer or clean key-value grid.
              While we are still waiting for the model to commit the
              arguments (box appeared from TOOL_CALL_START but no args
              yet) we show a brief "Composing input…" placeholder so
              the operator sees activity. Once the args land we render
              them through the specialised renderer. */}
          {!hasArgs && !hasPendingRaw && isRunning && (
            <div>
              <span className="text-micro font-medium text-text-muted uppercase tracking-wider">
                Arguments
              </span>
              <div className="mt-1 rounded bg-neutral-bg1 p-2 text-label text-text-muted italic flex items-center gap-2">
                <span className="inline-flex gap-0.5">
                  <span className="h-1 w-1 rounded-full bg-brand animate-pulse" />
                  <span className="h-1 w-1 rounded-full bg-brand animate-pulse [animation-delay:120ms]" />
                  <span className="h-1 w-1 rounded-full bg-brand animate-pulse [animation-delay:240ms]" />
                </span>
                Composing input…
              </div>
            </div>
          )}
          {hasPendingRaw && !hasArgs && (
            <div>
              <span className="text-micro font-medium text-text-muted uppercase tracking-wider">
                Arguments
              </span>
              <div className="mt-1 rounded bg-neutral-bg1 p-2">
                {/* Raw JSON-fragment view \u2014 streamed via TOOL_CALL_DELTA.
                    The blinking caret signals that more characters are
                    inbound; the renderer flips to the structured grid
                    once the JSON parses cleanly. */}
                <pre
                  data-testid="tool-args-raw"
                  className="font-mono text-xs text-text-secondary whitespace-pre-wrap break-all"
                >
                  {pendingRaw}
                  <span
                    data-testid="tool-args-caret"
                    className="inline-block w-1 h-3 bg-brand/60 ml-0.5 animate-pulse align-middle"
                  />
                </pre>
              </div>
            </div>
          )}
          {hasArgs && (
            <div>
              <span className="text-micro font-medium text-text-muted uppercase tracking-wider">
                Arguments
              </span>
              <div
                data-testid="tool-args-grid"
                className="mt-1 rounded bg-neutral-bg1 p-2"
              >
                <ToolArgumentsBlock
                  toolName={toolCall.name}
                  args={toolCall.arguments}
                  /* Animate per-value reveal as a fallback when the
                     backend (Azure AI Foundry Agents API) delivers
                     arguments atomically. The raw streaming view above
                     wins when TOOL_CALL_DELTA fragments actually
                     arrive; otherwise this typewriter preserves the
                     "agent is composing" affordance. */
                  animate={isRunning && !hasPendingRaw}
                />
              </div>
            </div>
          )}

          {/* Result — dispatched to specialized renderer by tool name */}
          {hasResult && (
            <div>
              <span
                className={`text-micro font-medium uppercase tracking-wider ${
                  isError ? "text-status-error" : "text-status-success"
                }`}
              >
                Result
              </span>
              <div className="mt-1">
                {(() => {
                  const Renderer = getToolResultRenderer(toolCall.name);
                  /* R4: thread toolName so renderers can resolve registry
                     hints (e.g. PanelToolSummary's label, ResultTable's
                     prominent-column hint) without re-parsing the envelope. */
                  return <Renderer result={toolCall.result!} toolName={toolCall.name} />;
                })()}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
});

/* ── Internal helpers ──────────────────────────────────────────────────── */

/**
 * ToolArgumentsBlock — renders tool arguments through the configured
 * custom renderer (when one exists) or the canonical ArgumentsGrid,
 * with an optional typewriter reveal of per-value strings.
 *
 * Why this exists: most tools register a typed args renderer that
 * displays their arguments in a domain-specific layout. Tools without
 * one fall through to the generic key/value grid. Per-value typewriter
 * animation runs ONLY when the backend delivered arguments atomically
 * — when TOOL_CALL_DELTA fragments actually stream in, the raw view
 * upstream renders progressive growth and ``animate`` is false.
 */
function ToolArgumentsBlock({
  toolName,
  args,
  animate,
}: {
  toolName: string;
  args: Record<string, unknown>;
  animate: boolean;
}) {
  const ArgsRenderer = getToolArgsRenderer(toolName);
  if (ArgsRenderer) {
    // Custom renderers are arbitrary React trees and cannot be
    // animated character-by-character; render as-is.
    return <ArgsRenderer args={args} />;
  }
  return <TypewriterArguments args={args} animate={animate} />;
}

/**
 * TypewriterArguments — drop-in replacement for ArgumentsGrid that
 * progressively reveals each value's string form. Active only when
 * ``animate`` is true; falls through to ArgumentsGrid otherwise so
 * historical / non-streaming cards render identically to before.
 */
function TypewriterArguments({
  args,
  animate,
}: {
  args: Record<string, unknown>;
  animate: boolean;
}) {
  if (!animate) return <ArgumentsGrid args={args} />;
  const entries = Object.entries(args);
  if (entries.length === 0) return null;
  return (
    <div className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-[0.85em]">
      {entries.map(([key, value]) => (
        <div key={key} className="contents">
          <span className="text-text-muted font-medium">{key}</span>
          <TypewriterValue value={formatValue(value)} />
        </div>
      ))}
    </div>
  );
}

/* Renders a single value with a typewriter reveal. Duration scales with
   length so very short values do not animate at noticeable speed. */
function TypewriterValue({ value }: { value: string }) {
  // ~30ms per char, capped at 600ms so even long JSON blobs finish fast.
  const duration = Math.min(600, Math.max(120, value.length * 30));
  const text = useTypewriter(value, duration);
  return (
    <span
      data-testid="tool-args-typewriter"
      className="font-mono text-text-secondary break-all"
    >
      {text}
      {text.length < value.length && (
        <span
          data-testid="tool-args-caret"
          className="inline-block w-1 h-3 bg-brand/60 ml-0.5 animate-pulse align-middle"
        />
      )}
    </span>
  );
}

/* Mirrors ArgumentsGrid.formatValue — kept local so this file does not
   reach into the renderers/ internals. */
function formatValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return JSON.stringify(value);
}
