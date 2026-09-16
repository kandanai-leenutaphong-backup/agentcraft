/**
 * Patch dispatcher — applies a single FramePatch to the demo's working state
 * and pushes the result into the relevant Zustand stores.
 *
 * Module role:
 *   The translation layer between the declarative scenario format and the
 *   imperative store APIs. Keep this dumb — one switch on the op name,
 *   no logic in the scenario. New ops go HERE and in scenarioSchema.ts
 *   simultaneously.
 *
 * Working state:
 *   The player maintains a ScenarioState object that is the source of truth
 *   for the scenario's current display. Each patch mutates this object,
 *   then we push the relevant slice into the corresponding store.
 *   This makes restart trivial (drop the working state, rewind to frame 0).
 */

import type { ApiMessage, ToolCall } from "@/api/types";
import type {
  FramePatch,
  PatchToolCall,
  PriorityActionAppendOp,
} from "./scenarioSchema";
import { useChatStore } from "@/stores/chatStore";
import { usePanelStore } from "@/stores/panelStore";
import { useSituationStore } from "@/stores/situationStore";
import { useAgentStore } from "@/stores/agentStore";
import { useTopologyStore } from "@/stores/topologyStore";
import { useSpotlightStore } from "@/stores/spotlightStore";
import type { TopologyGraph } from "@/api/topologyApi";
import { EMPTY_SUMMARY_STATE, useSummaryStore } from "@/stores/summaryStore";
import { useAuditStore } from "@/stores/auditStore";
import { useLookupStore } from "@/stores/lookupStore";

/** Internal working state — one source of truth per scenario run. */
export interface ScenarioState {
  /** Per-agent message lists. Keys are agent ids. */
  chat: Record<string, ApiMessage[]>;
  /** Priority action cards in display order. */
  priorityActions: PriorityActionAppendOp[];
}

/** Build a fresh empty working state. Called at scenario start + restart. */
export function freshScenarioState(): ScenarioState {
  return { chat: {}, priorityActions: [] };
}

// ── Helpers ─────────────────────────────────────────────────────────────

/** Convert scenario tool-call shape to the api/types ToolCall shape. */
function toToolCall(tc: PatchToolCall): ToolCall {
  return {
    id: tc.id,
    name: tc.name,
    arguments: tc.arguments,
    status: tc.status,
    result: tc.result ?? null,
    duration_ms: tc.duration_ms ?? null,
  };
}

/** Push a single agent's message list into the chatStore. */
function syncChatSlice(agent: string, messages: ApiMessage[]): void {
  /* setMessages takes ApiMessage[] and overwrites the slice. The chat
     store handles parts normalization internally so we don't have to
     synthesise ContentPart arrays here. */
  useChatStore.getState().setMessages(agent, messages);
}

/** Push the priority actions list into the panel store via the existing
 *  update_priority_actions op (which replaces the full list). */
function syncPriorityActions(actions: PriorityActionAppendOp[]): void {
  usePanelStore.getState().updatePanel("update_priority_actions", {
    actions: actions.map((a) => ({
      action: a.action,
      reasoning: a.reasoning,
      guide: a.guide,
      priority: a.priority,
      contacts: a.contacts,
      sources: a.sources,
    })),
  });
}

/** Build a fresh ApiMessage from a chat.append op. */
function buildMessage(
  agent: string,
  role: "user" | "assistant",
  text: string,
  agentName: string,
  toolCalls: ToolCall[],
  isDelegation: boolean,
): ApiMessage {
  /* Stable id — uses agent + index hash so re-rendering doesn't churn. */
  const id = `demo-${agent}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  return {
    id,
    role,
    content: text,
    /* parts is normalised by the chat store; passing null lets it derive
       parts from `content` + `tool_calls`. */
    parts: null,
    status: "complete",
    tool_calls: toolCalls,
    agent_name: agentName,
    created_at: new Date().toISOString(),
    ...(isDelegation ? { _isDelegation: true } : {}),
  };
}

// ── Public dispatcher ───────────────────────────────────────────────────

/**
 * Apply one frame's patch to the working state and push the relevant
 * slices into the Zustand stores. Returns the mutated state for chaining.
 *
 * Invariant: each op handler updates `state` first, then calls a sync
 * helper. Order matters — a chat.append followed by chat.append_token
 * in the same frame must see the new message before tokens are appended.
 */
export function applyPatch(state: ScenarioState, patch: FramePatch): ScenarioState {
  // ── chat.append ──────────────────────────────────────────────────────
  if (patch["chat.append"]) {
    const op = patch["chat.append"];
    const list = state.chat[op.agent] ?? [];
    const toolCalls = (op.tool_calls ?? []).map(toToolCall);
    const msg = buildMessage(
      op.agent,
      op.role,
      op.text,
      op.agent_name ?? "",
      toolCalls,
      Boolean(op.is_delegation),
    );
    state.chat[op.agent] = [...list, msg];
    syncChatSlice(op.agent, state.chat[op.agent]);
    console.info("[demo] chat.append", op.agent, op.role, "len=", state.chat[op.agent].length);
  }

  // ── chat.append_token ────────────────────────────────────────────────
  /* Append text to the LAST message in the agent's thread. Used for
     streamed assistant responses — one frame per chunk. */
  if (patch["chat.append_token"]) {
    const op = patch["chat.append_token"];
    const list = state.chat[op.agent] ?? [];
    if (list.length === 0) {
      /* Defensive: token op with no message to append to. The scenario
         author messed up; log loudly so it's caught in dev. */
      console.warn("[demo] chat.append_token with no prior message", op);
    } else {
      const last = list[list.length - 1];
      const updated: ApiMessage = {
        ...last,
        content: last.content + op.text,
        /* Force parts re-derivation by clearing the cached parts array. */
        parts: null,
      };
      state.chat[op.agent] = [...list.slice(0, -1), updated];
      syncChatSlice(op.agent, state.chat[op.agent]);
    }
  }

  // ── chat.update_tool ─────────────────────────────────────────────────
  /* Update an existing tool call by id within the agent's last assistant
     message. Used to flip a `running` card to `complete` with a result. */
  if (patch["chat.update_tool"]) {
    const op = patch["chat.update_tool"];
    const list = state.chat[op.agent] ?? [];
    if (list.length === 0) {
      console.warn("[demo] chat.update_tool with no message", op);
    } else {
      /* Walk backwards to find the message that owns this tool call id. */
      const idx = (() => {
        for (let i = list.length - 1; i >= 0; i--) {
          if (list[i].tool_calls.some((tc) => tc.id === op.id)) return i;
        }
        return -1;
      })();
      if (idx === -1) {
        console.warn("[demo] chat.update_tool: tool id not found", op.id);
      } else {
        const target = list[idx];
        const newToolCalls = target.tool_calls.map((tc) =>
          tc.id === op.id
            ? {
                ...tc,
                ...(op.status !== undefined ? { status: op.status } : {}),
                ...(op.result !== undefined ? { result: op.result } : {}),
                ...(op.duration_ms !== undefined ? { duration_ms: op.duration_ms } : {}),
                ...(op.arguments !== undefined ? { arguments: op.arguments } : {}),
              }
            : tc,
        );
        const updated: ApiMessage = {
          ...target,
          tool_calls: newToolCalls,
          /* Force parts re-derivation so the tool card visually updates. */
          parts: null,
        };
        state.chat[op.agent] = [
          ...list.slice(0, idx),
          updated,
          ...list.slice(idx + 1),
        ];
        syncChatSlice(op.agent, state.chat[op.agent]);
      }
    }
  }

  // ── panel.priority_action.append ─────────────────────────────────────
  if (patch["panel.priority_action.append"]) {
    const op = patch["panel.priority_action.append"];
    state.priorityActions = [...state.priorityActions, op];
    syncPriorityActions(state.priorityActions);
  }

  // ── panel.situations.set ─────────────────────────────────────────────
  if (patch["panel.situations.set"]) {
    const op = patch["panel.situations.set"];
    /* The situation store is structured around scan results; we set the
       situations list directly via setState. Cast through unknown is the
       price of bypassing the fetch path — acceptable in demo mode.
       Always clear scanStartedAt/scanEstimateMs so the ScanProgressPanel
       unmounts even if the prior frame opened a fake scan. */
    useSituationStore.setState({
      rawSituations: op.situations as never,
      situations: op.situations as never,
      gridStatus: op.grid_status ?? null,
      loading: false,
      error: null,
      scanStartedAt: null,
      scanEstimateMs: null,
    });
  }

  // ── panel.situations.scan_start ──────────────────────────────────────
  /* Spoofs the loading half of a situation scan: the SituationAlertsPanel
     swaps its empty state for the radar/spinner ScanProgressPanel and
     ScanProgressBar driven off scanStartedAt + scanEstimateMs. The
     scenario controls when the scan "completes" by following up with
     a panel.situations.set frame; the estimate_ms here only governs the
     visual fill rate and the ETA text the user sees. */
  if (patch["panel.situations.scan_start"]) {
    const op = patch["panel.situations.scan_start"];
    const estimate = op.estimate_ms ?? 10_000;
    useSituationStore.setState({
      rawSituations: [],
      situations: [],
      gridStatus: null,
      loading: true,
      error: null,
      scanStartedAt: Date.now(),
      scanEstimateMs: estimate,
    });
  }

  // ── panel.situations.classify ─────────────────────────────────────
  /* Inject NER 4.2.3 classification results into the situation store.
     Each entry in the classifications array is written with status "ready"
     so the SituationCard renders the coloured badge immediately. Used
     by the demo player to animate a delayed classification reveal. */
  if (patch["panel.situations.classify"]) {
    const op = patch["panel.situations.classify"];
    const current = useSituationStore.getState().classifications;
    const next = { ...current };
    for (const entry of op.classifications) {
      next[entry.situation_id] = {
        status: "ready",
        classification: entry.classification,
        ner_citation: entry.ner_citation,
        rationale: entry.rationale,
      };
    }
    useSituationStore.setState({ classifications: next });
    console.info("[demo] panel.situations.classify", op.classifications.length, "entries");
  }

  // ── agent.set_active ─────────────────────────────────────────────────
  if (patch["agent.set_active"]) {
    useAgentStore.getState().setActiveAgent(patch["agent.set_active"].agent);
  }
  // ── panel.center_tab.set ─────────────────────────────────────────────
  if (patch["panel.center_tab.set"]) {
    usePanelStore.getState().setCenterTab(patch["panel.center_tab.set"].tab);
  }
  // ── panel.summary.set ────────────────────────────────────────────────
  if (patch["panel.summary.set"]) {
    const op = patch["panel.summary.set"];
    useSummaryStore.setState({
      summaryState: op.summary ?? EMPTY_SUMMARY_STATE,
      loading: false,
      error: null,
      streamingText: "",
    });
  }
  // ── panel.classify_verdict.set ───────────────────────────────────────
  if (patch["panel.classify_verdict.set"]) {
    usePanelStore.setState({ classifyVerdict: patch["panel.classify_verdict.set"].verdict });
  }
  // ── panel.detector_config.set / preview ─────────────────────────────
  if (patch["panel.detector_config.set"]) {
    const op = patch["panel.detector_config.set"];
    useSituationStore.setState({
      detectorConfig: op.detectorConfig,
      detectorDraft: op.detectorDraft ?? op.detectorConfig.patch ?? {},
      detectorDirty: op.detectorDirty ?? false,
      detectorSaving: false,
      detectorComparison: op.detectorComparison ?? null,
      windowMinutes: op.windowMinutes ?? op.detectorDraft?.window_minutes ?? op.detectorConfig.patch.window_minutes ?? useSituationStore.getState().windowMinutes,
      maxAlarmRows: op.maxAlarmRows ?? useSituationStore.getState().maxAlarmRows,
      maxScadaRows: op.maxScadaRows ?? useSituationStore.getState().maxScadaRows,
    });
  }
  if (patch["panel.detector_config.preview"]) {
    const op = patch["panel.detector_config.preview"];
    useSituationStore.setState({
      detectorComparison: op.detectorComparison,
      detectorDirty: op.detectorDirty ?? useSituationStore.getState().detectorDirty,
    });
  }
  // ── panel.audit.set ─────────────────────────────────────────────────
  if (patch["panel.audit.set"]) {
    const op = patch["panel.audit.set"];
    useAuditStore.setState({
      status: op.status,
      auditId: op.auditId,
      report: op.report,
      reportSource: "live",
      streamEvents: op.streamEvents ?? [],
      partialNarration: op.partialNarration ?? "",
      history: [{
        id: op.report.id,
        session_id: op.report.session_id,
        started_at: op.report.started_at,
        finished_at: op.report.finished_at,
        duration_seconds: op.report.duration_seconds ?? null,
        headline: op.report.headline,
        band: op.report.band,
        weighted_score: op.report.weighted_score,
        score_pct: op.report.score_pct,
        confidence: op.report.confidence,
        tool_call_count: op.report.tool_call_count ?? null,
        context_prompt: op.report.context_prompt,
        improvement_count: op.report.improvements?.length ?? 0,
      }],
      loadingHistory: false,
      loadingReport: false,
      error: null,
      controller: null,
    });
  }
  // ── dock.thread.set ─────────────────────────────────────────────────
  if (patch["dock.thread.set"]) {
    const op = patch["dock.thread.set"];
    useLookupStore.setState({
      activeDockAgentId: op.agent,
      dockSessionId: "demo-dock-session",
    });
    useChatStore.getState().setMessages(op.agent, op.messages);
  }
  // ── topology.set ─────────────────────────────────────────────────────
  /* Pre-load a topology graph for the demo so that View topology and
     auto-load on tab switch render real-looking content rather than the
     empty state. The store's loadStation respects this cache in kiosk
     mode by skipping the network call when the requested station
     matches the pre-loaded center. */
  if (patch["topology.set"]) {
    const op = patch["topology.set"];
    useTopologyStore.setState({
      activeStation: op.station,
      graph: op.graph as unknown as TopologyGraph,
      breadcrumb: [op.station],
      overlay: op.overlay ?? null,
      loading: false,
      error: null,
      selectedEquipment: null,
      expandedStations: new Set<string>(),
      expandingStations: new Set<string>(),
    });
  }
  // ── topology.overlay.set ─────────────────────────────────────────────
  /* Surgical overlay swap. Leaves the loaded graph, breadcrumb, selection,
     and expansion state untouched so the operator's view is preserved.
     Used by the precursor reveal (07_precursor.ts) to spotlight the
     bus that flashed over without forcing a topology reload. */
  if (patch["topology.overlay.set"]) {
    useTopologyStore.setState({ overlay: patch["topology.overlay.set"].overlay });
  }
  // ── ui.spotlight.set / ui.spotlight.clear ────────────────────────────
  /* Presentation spotlight — draws a bright box around one DOM element
     identified by its data-spotlight-id attribute and shows a caption
     bubble next to it. Used SPARINGLY by scenario authors to land a
     single beat of narration on a single element. The set op replaces
     any active spotlight; the clear op removes it. */
  if (patch["ui.spotlight.set"]) {
    const op = patch["ui.spotlight.set"];
    useSpotlightStore.getState().setSpotlight({
      targetId: op.target,
      caption: op.caption,
      placement: op.placement,
      padding: op.padding,
    });
  }
  if (patch["ui.spotlight.clear"]) {
    useSpotlightStore.getState().clearSpotlight();
  }

  // ── panel.pin.set ────────────────────────────────────────────────────
  /* Auto-pin a situation/alert (by its `station` value) into the centre
     "Situation" tab and switch to it, so the detail view stays on
     display after playback for unattended viewing. The situations
     snapshot is read from the current situation store. */
  if (patch["panel.pin.set"]) {
    const op = patch["panel.pin.set"];
    const sits = useSituationStore.getState().situations;
    usePanelStore.getState().pinStation(op.station, sits as never, { switchTab: true });
  }
  return state;
}

/** Reset all stores the player touches, leaving the UI in its initial
 *  empty state. Called on restart and when the player stops. */
export function resetDemoStores(): void {
  useChatStore.getState().clearAll();
  usePanelStore.getState().clearPanels();
  useTopologyStore.getState().clear();
  useSpotlightStore.getState().clearSpotlight();
  useSummaryStore.getState().resetLocal();
  useAuditStore.getState().reset();
  usePanelStore.setState({ classifyVerdict: null, pinnedStations: [] });
  useSituationStore.setState({
    rawSituations: [],
    situations: [],
    gridStatus: null,
    classifications: {},
    loading: false,
    error: null,
    queryTimeMs: null,
    freqSummary: null,
    scanStartedAt: null,
    scanEstimateMs: null,
  });
}
