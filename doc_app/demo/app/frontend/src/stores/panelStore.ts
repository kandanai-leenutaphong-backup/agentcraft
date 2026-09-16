/**
 * panelStore — Zustand store for agent-driven control room panels.
 *
 * Updated from chatStore when tool_call_end events arrive for panel tools
 * (tools whose name starts with "update_"). Each panel's data is the
 * structured arguments the agent passed to the tool.
 */

import { create } from "zustand";
import type {
  AgentThread,
  PriorityActionState,
  PriorityActionStatus,
  PriorityActionTimelineEntry,
  ToolCall,
} from "@/api/types";
import type { SituationRecord } from "@/api/situationApi";

// ── Panel Data Types ────────────────────────────────────────────────────────

export interface DisturbanceSummaryData {
  event_type: string;
  location: string;
  timestamp: string;
  generation_lost_mw: number;
  load_shed_mw: number;
  units_affected: string[];
  network_trips: string[];
  ufls_status: string;
}

export interface OperatingStateCheck {
  name: string;
  category: "satisfactory" | "secure";
  status: "pass" | "fail";
  detail?: string;
}

export interface OperatingStateData {
  checks: OperatingStateCheck[];
}

export interface PriorityAction {
  action_id: string;
  step: number;
  action: string;
  reasoning: string;
  guide: string;
  priority: number;
  pinned: boolean;
  status: PriorityActionStatus;
  note?: string;
  decided_at?: string;
  contacts?: { name: string; role: string; phone: string; teams: string }[];
  sources?: string[];
}

export interface PriorityActionsData {
  actions: PriorityAction[];
}

// ── Classify verdict (Phase 2 workstream C, 2026-05-18) ───────────────────────
//
// Restores the dedicated verdict panel under the SituationSummaryCard, in
// the slot the retired classifier_verdict panel used to occupy. The panel
// is always rendered (empty placeholder when no verdict yet), and updates
// when the grid_manager `classify` tool fires. Verdict shape mirrors the
// `tools/panels/_classify.py` return envelope.

export type ClassifyVerdict =
  | "credible_event"
  | "non_credible_event"
  | "non_event"
  | "indeterminate";

export interface ClassifyVerdictState {
  verdict: ClassifyVerdict;
  justification: string;
  sources: string[];
  updated_at: string;
}

// ── Helpers ─────────────────────────────────────────────────────────────────

function emptyPriorityActionState(): PriorityActionState {
  return { decisions: {}, timeline: [] };
}

function stableHash(value: string): string {
  let hash = 5381;
  for (let index = 0; index < value.length; index += 1) {
    hash = ((hash << 5) + hash) ^ value.charCodeAt(index);
  }
  return (hash >>> 0).toString(36);
}

function priorityActionId(action: Record<string, unknown>, index: number): string {
  const existing = action.action_id ?? action.id;
  if (typeof existing === "string" && existing.trim()) return existing.trim();
  const raw = [
    action.action ?? action.requested_action ?? "",
    action.reasoning ?? "",
    action.guide ?? "",
    action.priority ?? "",
    index,
  ].join("\u001f");
  return `pa_${stableHash(raw)}`;
}

function applyPriorityActionState(actions: PriorityAction[], state: PriorityActionState): PriorityAction[] {
  return actions.map((action) => {
    const decision = state.decisions[action.action_id];
    if (!decision) return action;
    return {
      ...action,
      status: decision.status,
      note: decision.note || undefined,
      decided_at: decision.updated_at,
    };
  });
}

function orderPriorityActions(actions: PriorityAction[]): PriorityAction[] {
  const unpinned = actions
    .filter((action) => !action.pinned)
    .sort((left, right) => right.priority - left.priority);
  return actions
    .map((action) => (action.pinned ? action : unpinned.shift()!))
    .map((action, index) => ({ ...action, step: index + 1 }));
}

function nextPriorityActionState(
  current: PriorityActionState,
  action: PriorityAction,
  status: PriorityActionStatus,
  note: string,
): PriorityActionState {
  const now = new Date().toISOString();
  const decision = {
    action_id: action.action_id,
    status,
    note,
    action_text: action.action,
    reasoning: action.reasoning,
    guide: action.guide,
    priority: action.priority,
    actor_user_id: "local",
    actor_name: "Local operator",
    updated_at: now,
  };
  const entry: PriorityActionTimelineEntry = {
    event_id: `local_${stableHash(`${action.action_id}:${status}:${now}`)}`,
    action_id: action.action_id,
    status,
    note,
    action_text: action.action,
    reasoning: action.reasoning,
    guide: action.guide,
    priority: action.priority,
    actor_user_id: "local",
    actor_name: "Local operator",
    created_at: now,
  };
  return {
    decisions: { ...current.decisions, [action.action_id]: decision },
    timeline: [...current.timeline, entry].slice(-200),
  };
}

/**
 * Convert tool-call arguments or persisted panel payloads into the single
 * frontend PriorityAction shape expected by the panel and tests.
 */
function normalizePriorityAction(action: Record<string, unknown>, index: number): PriorityAction {
  const actionId = priorityActionId(action, index);
  return {
    action_id: actionId,
    step: (action.step as number) ?? index + 1,
    action: (action.action as string) ?? (action.requested_action as string) ?? "",
    reasoning: (action.reasoning as string) ?? "",
    guide: (action.guide as string) ?? "",
    priority: typeof action.priority === "number" ? action.priority : 3,
    pinned: typeof action.pinned === "boolean" ? action.pinned : false,
    status: "pending",
    contacts: Array.isArray(action.contacts) ? action.contacts as PriorityAction["contacts"] : undefined,
    sources: Array.isArray(action.sources) ? action.sources as string[] : undefined,
  };
}

// ── Store ───────────────────────────────────────────────────────────────────

/**
 * Which tab is active in the center column.
 *   - "priorities": Priority Actions panel (default).
 *   - "situation":  Pinned Situation detail — full expanded view of a single
 *                   situation promoted from the Situation Alerts list via the
 *                   pin button. Added 2026-04-17 so the operator can keep one
 *                   situation front-and-centre while the alert list on the
 *                   left continues to scroll/update.
 *   - "status":     Grid Status — NEM dashboard + regional breakdown +
 *                   threat breakdown. Migrated 2026-04-17 out of the
 *                   left column so Situation Alerts can use the full
 *                   vertical height of the left pane.
 *   - "topology":   Abstract NEM topology map (opened via the situation-card
 *                   "View topology" button or the tab click).
 *   - "data":       Data Search Assistant dock content (single dock-surface
 *                   agent: data_assistant). Migrated 2026-04-17 from a
 *                   bottom dock panel into a center tab.
 */
export type CenterTab = "priorities" | "situation" | "status" | "topology" | "data" | "tuning" | "evaluations";

interface PanelState {
  disturbanceSummary: DisturbanceSummaryData | null;
  operatingState: OperatingStateData | null;
  priorityActions: PriorityActionsData | null;
  priorityActionState: PriorityActionState;
  /** Latest grid_manager `classify` verdict for the active session, or
   *  null when the agent has not classified yet. Rendered by
   *  ClassifyVerdictCard directly below the SituationSummaryCard. */
  classifyVerdict: ClassifyVerdictState | null;
  /** Current tab shown in the center column. Defaults to priorities. */
  centerTab: CenterTab;
  /** Stations currently pinned into the centre "Situation" tab, in
   *  most-recent-first order. Each entry carries the station code plus
   *  the situation list snapshot captured at pin time. Re-pinning a
   *  station moves its entry to the head with a fresh situations
   *  snapshot (operator brief 2026-05-25 — pin unit is the station,
   *  not the individual situation). Empty array when nothing is
   *  pinned. References, not deep clones, so live-enrichment updates
   *  to the same SituationRecord propagate.
   *
   *  Populated by:
   *    - manual `pinStation` (Pin icon on station-group header)
   *    - auto-pin on Investigate (per-row + station-level Investigate
   *      buttons in `SituationAlertsPanel`) — silent, no tab switch.
   *  Consumed by `PinnedSituationPanel`. */
  pinnedStations: PinnedStationGroup[];

  updatePanel: (toolName: string, args: Record<string, unknown>) => void;
  togglePin: (step: number) => void;
  reorderActions: (actions: PriorityAction[]) => void;
  hydratePriorityActionState: (state?: PriorityActionState | null) => void;
  recordLocalPriorityActionDecision: (action: PriorityAction, status: PriorityActionStatus, note: string) => void;
  syncPriorityActionsFromThreads: (threads: Record<string, AgentThread>) => void;
  setCenterTab: (tab: CenterTab) => void;
  /** Pin a station's situations into the centre tab.
   *  `switchTab=true` (default for manual pin) also switches the
   *  centre tab to "situation"; auto-pin via Investigate passes
   *  `switchTab=false` so the operator stays on the chat surface. */
  pinStation: (station: string, situations: SituationRecord[], opts?: { switchTab?: boolean }) => void;
  /** Remove a single pinned station by code. Tab is left as-is. */
  unpinStation: (station: string) => void;
  /** Drop all pinned stations. Tab is left as-is. */
  clearPinnedStations: () => void;
  clearPanels: () => void;
}

/** Single pinned-station entry held by `panelStore.pinnedStations`. */
export interface PinnedStationGroup {
  station: string;
  situations: SituationRecord[];
  /** Epoch ms when this entry was pinned (or last re-pinned). Used by
   *  the panel header for a "pinned 5m ago" caption. */
  pinnedAt: number;
}

export const usePanelStore = create<PanelState>((set, get) => ({
  disturbanceSummary: null,
  centerTab: "priorities",
  operatingState: null,
  priorityActions: null,
  priorityActionState: emptyPriorityActionState(),
  pinnedStations: [],
  classifyVerdict: null,

  updatePanel: (toolName: string, args: Record<string, unknown>) => {
    switch (toolName) {
      case "update_disturbance_summary":
        set({
          disturbanceSummary: {
            event_type: (args.event_type as string) ?? "",
            location: (args.location as string) ?? "",
            timestamp: (args.timestamp as string) ?? "",
            generation_lost_mw: (args.generation_lost_mw as number) ?? 0,
            load_shed_mw: (args.load_shed_mw as number) ?? 0,
            units_affected: (args.units_affected as string[]) ?? [],
            network_trips: (args.network_trips as string[]) ?? [],
            ufls_status: (args.ufls_status as string) ?? "",
          },
        });
        break;
      case "update_operating_state":
        set({
          operatingState: {
            checks: (Array.isArray(args.checks) ? args.checks : []).map((check: Record<string, unknown>) => ({
              name: (check.name as string) ?? "",
              category: ((check.category as "satisfactory" | "secure") ?? "satisfactory"),
              status: ((check.status as "pass" | "fail") ?? "fail"),
              detail: (check.detail as string | undefined) ?? undefined,
            })),
          },
        });
        break;
      case "update_priority_actions":
        set({
          priorityActions: {
            actions: orderPriorityActions(applyPriorityActionState(
              (Array.isArray(args.actions) ? args.actions : []).map((action: Record<string, unknown>, index: number) =>
                normalizePriorityAction(action, index),
              ),
              get().priorityActionState,
            )),
          },
        });
        break;
      case "push_priority_action":
      case "push_action": {
        /* Append a single action from push_action or push_priority_action tool call args. */
        const current = get().priorityActions;
        const existing = current?.actions ?? [];
        const step = existing.length + 1;
        const newAction: PriorityAction = {
          action_id: priorityActionId(args, existing.length),
          step,
          action: (args.action as string) ?? (args.requested_action as string) ?? "",
          reasoning: (args.reasoning as string) ?? "",
          guide: (args.guide as string) ?? "",
          priority: typeof args.priority === "number" ? (args.priority as number) : 3,
          pinned: false,
          status: "pending",
        };
        const merged = orderPriorityActions(applyPriorityActionState(
          [...existing, newAction].map((a, i) => ({ ...a, step: i + 1 })),
          get().priorityActionState,
        ));
        set({
          priorityActions: { actions: merged },
        });
        break;
      }
      // push_classifier_verdict case removed 2026-05-18 with the
      // classifier retirement. See spec.
      case "classify": {
        /* Update the classify verdict panel from a `classify` tool call.
         * Args validated upstream by the pydantic Field constraints in
         * tools/panels/_classify.py; here we just shape them into the
         * FE state. The grid_manager calls classify AT MOST ONCE per
         * investigation (or overwrites within the same turn), so we
         * replace the slot rather than merging. */
        const verdict = (args.verdict as ClassifyVerdict) || "indeterminate";
        const justification = (args.justification as string) ?? "";
        const sourcesRaw = args.sources;
        const sources = Array.isArray(sourcesRaw) ? (sourcesRaw as string[]) : [];
        set({
          classifyVerdict: {
            verdict,
            justification,
            sources,
            updated_at: new Date().toISOString(),
          },
        });
        break;
      }
    }
  },

  togglePin: (step: number) => {
    const current = get().priorityActions;
    if (!current || !Array.isArray(current.actions)) return;

    const toggled = current.actions.map((action) =>
      action.step === step ? { ...action, pinned: !action.pinned } : action,
    );

    set({ priorityActions: { actions: toggled } });
  },

  syncPriorityActionsFromThreads: (threads: Record<string, AgentThread>) => {
    let hydratedActions: PriorityAction[] | null = null;
    let hydratedClassify: ClassifyVerdictState | null = null;
    // Classifier verdict hydration removed 2026-05-18 — classifier retired.

    const messages = Object.values(threads)
      .flatMap((thread) => thread.messages ?? [])
      .sort((left, right) => left.created_at.localeCompare(right.created_at));

    for (const message of messages) {
      for (const toolCall of message.tool_calls ?? []) {
        const tool = toolCall as ToolCall;

        // Classify verdict hydration — replay every `classify` tool call
        // in chronological order; the latest one wins (the tool itself
        // overwrites within a session).
        if (tool.name === "classify") {
          const args = (tool.arguments ?? {}) as Record<string, unknown>;
          const verdict = (args.verdict as ClassifyVerdict) || "indeterminate";
          const justification = (args.justification as string) ?? "";
          const sources = Array.isArray(args.sources) ? (args.sources as string[]) : [];
          hydratedClassify = {
            verdict,
            justification,
            sources,
            updated_at: message.created_at,
          };
          continue;
        }

        if (
          tool.name !== "push_action"
          && tool.name !== "push_priority_action"
          && tool.name !== "update_priority_actions"
        ) {
          continue;
        }

        if (tool.result) {
          try {
            const parsed = JSON.parse(tool.result) as { panel?: string; actions?: Record<string, unknown>[] };
            if (parsed.panel === "priority_actions" && Array.isArray(parsed.actions)) {
              hydratedActions = parsed.actions.map((action, index) =>
                normalizePriorityAction(action, index),
              );
              continue;
            }
          } catch {
            // Fall back to arguments when the persisted result is not JSON.
          }
        }

        const existing: PriorityAction[] = hydratedActions ?? [];
        hydratedActions = [
          ...existing,
          normalizePriorityAction(tool.arguments as Record<string, unknown>, existing.length),
        ];
      }
    }

    set((state) => ({
      priorityActions: hydratedActions
        ? { actions: applyPriorityActionState(hydratedActions.map((a, i) => ({ ...a, step: i + 1 })), state.priorityActionState) }
        : state.priorityActions,
      classifyVerdict: hydratedClassify ?? state.classifyVerdict,
    }));
  },

  reorderActions: (actions: PriorityAction[]) => {
    set({ priorityActions: { actions } });
  },

  hydratePriorityActionState: (state) => {
    const nextState = state ?? emptyPriorityActionState();
    set((current) => ({
      priorityActionState: nextState,
      priorityActions: current.priorityActions
        ? { actions: applyPriorityActionState(current.priorityActions.actions, nextState) }
        : current.priorityActions,
    }));
  },

  recordLocalPriorityActionDecision: (action, status, note) => {
    const nextState = nextPriorityActionState(get().priorityActionState, action, status, note.trim());
    get().hydratePriorityActionState(nextState);
  },

  setCenterTab: (tab) => set({ centerTab: tab }),

  /* Pin a station's situation list to the head of pinnedStations.
     Operator brief 2026-05-25: pin granularity is the station, not the
     individual situation. Re-pinning moves the entry to head with a
     fresh situations snapshot (latest live enrichment wins). The
     `switchTab` option lets auto-pin-on-investigate happen silently
     (operator stays on chat) while manual pin clicks always surface
     the Situation tab. */
  pinStation: (station, situations, opts) => set((s) => {
    const filtered = s.pinnedStations.filter((g) => g.station !== station);
    const entry: PinnedStationGroup = {
      station,
      situations,
      pinnedAt: Date.now(),
    };
    const next: Partial<PanelState> = { pinnedStations: [entry, ...filtered] };
    if (opts?.switchTab) next.centerTab = "situation";
    return next;
  }),

  /* Remove a single pinned station by code. No-op when absent. */
  unpinStation: (station) => set((s) => ({
    pinnedStations: s.pinnedStations.filter((g) => g.station !== station),
  })),

  /* Empty the pinned-stations list. Tab is left as-is; the
     PinnedSituationPanel falls back to its empty state when consulted. */
  clearPinnedStations: () => set({ pinnedStations: [] }),

  clearPanels: () =>
    set({
      disturbanceSummary: null,
      operatingState: null,
      priorityActions: null,
      priorityActionState: emptyPriorityActionState(),
      pinnedStations: [],
      classifyVerdict: null,
    }),
}));
