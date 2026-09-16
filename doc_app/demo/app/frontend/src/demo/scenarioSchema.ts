/**
 * Demo scenario schema (gridiq-demo/v1).
 *
 * Module role:
 *   Type definitions for the kiosk-mode demo scenario file format.
 *   A scenario is a self-contained, hand-authored JSON file that
 *   fully describes a demo run: every UI element's content + timing.
 *
 * Design constraints (from KIOSK_DEMO_HANDOFF.md):
 *   - Hand-authored, never captured.
 *   - Self-contained — no external lookups, no per-tool fixtures.
 *   - Declarative — each frame says what the UI should look like.
 *   - Small op vocabulary — new ops go in the player, never in the scenario.
 *   - Stable, versioned schema.
 *
 * The player walks `frames` in order, applies each frame's `patch` instantly,
 * then waits `transition_ms / speed` before advancing. Frames whose `chapter`
 * is set are chapter boundaries (drives narration overlay, step-mode auto-pause,
 * progress bar segmentation).
 */

import type { ApiMessage, ToolCallStatus } from "@/api/types";
import type { SummaryState } from "@/api/types";
import type { DetectorConfigPatch, DetectorConfigResponse, GridStatus } from "@/api/situationApi";
import type { AuditReport, AuditStreamEvent } from "@/api/auditApi";
import type { CenterTab, ClassifyVerdictState } from "@/stores/panelStore";
import type { DetectorComparisonResult } from "@/stores/situationStore";

/** Schema version. Player rejects files with unknown values. */
export const SCENARIO_SCHEMA = "gridiq-demo/v1";

// ── Patch operations ─────────────────────────────────────────────────────

/** Add a new chat message to an agent's thread. */
export interface ChatAppendOp {
  agent: string;
  role: "user" | "assistant";
  /** Initial text. Empty string is valid for assistant messages that will
   *  receive streamed tokens via subsequent ChatAppendTokenOp frames. */
  text: string;
  /** Display name shown above the bubble for assistant messages. */
  agent_name?: string;
  /** Tool call cards rendered with this message. Status governs the
   *  visual state (running spinner / complete result / error). */
  tool_calls?: PatchToolCall[];
  /** Mark this message as a delegation hand-off (renders as a forwarded task). */
  is_delegation?: boolean;
}

/** Append text to the last assistant message on an agent's thread. */
export interface ChatAppendTokenOp {
  agent: string;
  text: string;
}

/** Update an existing tool call by id within an agent's last assistant message. */
export interface ChatUpdateToolOp {
  agent: string;
  /** Tool call id assigned in the original ChatAppendOp. */
  id: string;
  status?: ToolCallStatus;
  result?: string;
  duration_ms?: number;
  arguments?: Record<string, unknown>;
}

/** Tool call shape used inside scenario patches. Mirrors api/types.ts ToolCall
 *  but with optional fields treated as more permissive (player fills defaults). */
export interface PatchToolCall {
  id: string;
  name: string;
  arguments: Record<string, unknown>;
  status: ToolCallStatus;
  result?: string;
  duration_ms?: number;
}

/** Append a single priority action to the panel. */
export interface PriorityActionAppendOp {
  action: string;
  reasoning: string;
  guide: string;
  priority: number;
  contacts?: { name: string; role: string; phone: string; teams: string }[];
  /** Procedure / clue source citations rendered as chips under the
   *  rationale block. Populated for actions whose reasoning depends
   *  on PAWS sections, near-hit reports, or investigation clues. */
  sources?: string[];
}

/** Replace the situations list shown in the situation panel. */
export interface SituationsSetOp {
  situations: Record<string, unknown>[];
  grid_status?: GridStatus | null;
}

/** Begin a fake situation scan — flips the situation store into its
 *  loading state so the radar/spinner ScanProgressPanel renders. The
 *  scan is closed by the next ``panel.situations.set`` op which writes
 *  the result and clears ``loading``. */
export interface SituationsScanStartOp {
  /** Apparent scan duration in ms — drives the progress bar fill rate
   *  and the ETA text. The actual completion is controlled by the
   *  scenario's frame timing, not this value. Default 10_000. */
  estimate_ms?: number;
}

/** Switch the active agent tab. */
export interface ActiveAgentSetOp {
  agent: string;
}

/** Switch the center Workspace mode. */
export interface CenterTabSetOp {
  tab: CenterTab;
}

/** Hydrate the situation summary card without calling the backend summarizer. */
export interface SummarySetOp {
  summary: SummaryState | null;
}

/** Hydrate the classifier verdict card without a live classify tool call. */
export interface ClassifyVerdictSetOp {
  verdict: ClassifyVerdictState | null;
}

/** Hydrate detector-tuning UI with kiosk-local config, draft, and comparison. */
export interface DetectorConfigSetOp {
  detectorConfig: DetectorConfigResponse;
  detectorDraft?: DetectorConfigPatch;
  detectorDirty?: boolean;
  detectorComparison?: DetectorComparisonResult | null;
  windowMinutes?: number;
  maxAlarmRows?: number;
  maxScadaRows?: number;
}

/** Hydrate the detector comparison result after a draft preview. */
export interface DetectorConfigPreviewOp {
  detectorComparison: DetectorComparisonResult | null;
  detectorDirty?: boolean;
}

/** Hydrate the SessionAuditPanel with a completed synthetic report. */
export interface AuditSetOp {
  status: "completed" | "running";
  auditId: string;
  report: AuditReport;
  streamEvents?: AuditStreamEvent[];
  partialNarration?: string;
}

/** Replace a dock-surface assistant thread, usually Data Search. */
export interface DockThreadSetOp {
  agent: string;
  messages: ApiMessage[];
}

/** Inject NER 4.2.3 classification results into the situation store.
 *  Used by the demo player to animate the "Classifying per NER 4.2.3..."
 *  spinner → badge reveal transition. Each entry maps a situation_id to
 *  its classification verdict. The handler writes entries with
 *  status: "ready" so the SituationCard renders the coloured badge. */
export interface SituationsClassifyOp {
  classifications: SituationClassificationEntry[];
}

/** A single classification verdict for one situation, as authored in
 *  the scenario JSON or kiosk_bootstrap.classifications. */
export interface SituationClassificationEntry {
  situation_id: string;
  classification: "credible" | "non_credible" | "non_event";
  ner_citation: string;
  rationale: string;
}

/** Pre-load a topology graph into the topology store. The shape mirrors
 *  TopologyGraph from api/topologyApi but is left as a free record so
 *  the player does not need to validate every field of every equipment
 *  row. The store ingests it via setState. */
export interface TopologySetOp {
  /** Center station code — also used as the activeStation. */
  station: string;
  /** Full TopologyGraph object: { center, neighbors, links }. */
  graph: Record<string, unknown>;
  /** Optional alarm overlay applied at load time. */
  overlay?: { equipmentIds: string[]; severity: string };
}

/** Update the topology alarm overlay in place — does NOT touch the
 *  loaded graph, breadcrumb, selection, or expansion state. Used by
 *  the precursor reveal to spotlight a specific bus or piece of plant
 *  without forcing a full topology reload. Pass `null` to clear. */
export interface TopologyOverlaySetOp {
  overlay: { equipmentIds: string[]; severity: string } | null;
}

/** Activate the presentation spotlight on a specific UI element.
 *  The element is identified by a ``data-spotlight-id`` attribute —
 *  the player resolves it via document.querySelector at render time.
 *  Used SPARINGLY so each activation lands as a distinct narrative
 *  beat (e.g. "look at this card before I read what is on it"). */
export interface SpotlightSetOp {
  /** Value of ``data-spotlight-id`` on the element to highlight. */
  target: string;
  /** Caption shown next to the spotlight bubble. Short — one or two
   *  sentences max. */
  caption: string;
  /** Optional preferred caption placement. Defaults to ``auto``. */
  placement?: "top" | "bottom" | "left" | "right" | "auto";
  /** Optional padding (px) around the spotlit element. Default 8. */
  padding?: number;
}

/** Clear the active spotlight. No-op if none is active. */
export type SpotlightClearOp = Record<string, never>;

/** Pin a situation/alert (by its `station` value) into the centre
 *  "Situation" tab and switch to it, so the detail stays on display
 *  after playback. The situation snapshot is taken from the current
 *  situation store. */
export interface PanelPinSetOp {
  /** `station` value of the situation to pin (e.g. "WIN-FIN-07"). */
  station: string;
}

// ── Frame ────────────────────────────────────────────────────────────────

/**
 * One step in the scenario. The player applies `patch` instantly, then
 * waits `transition_ms` (divided by current speed multiplier) before
 * advancing. Frames whose `chapter` is set are chapter boundaries.
 */
export interface Frame {
  id: string;
  /** Chapter title — when set, this frame starts a new chapter. */
  chapter?: string;
  /** Narration text shown in the overlay during this chapter. */
  narration?: string;
  /** Milliseconds to wait AFTER applying the patch before advancing. */
  transition_ms: number;
  /** Optional auto-spotlight anchored to this frame.
   *
   *  Fired by the player when the frame becomes active IF the user has
   *  the Annotations toggle ON. Cleared automatically when the next
   *  chapter boundary fires (so annotations don't bleed past their
   *  beat). Use this for the "look here, this is what just happened"
   *  callout that follows each chapter advance — typed by scenario
   *  authors as a sibling to ``chapter`` / ``narration``.
   *
   *  If you want a one-off spotlight that ignores the Annotations
   *  toggle (e.g. the precursor reveal, which is mandatory), use the
   *  imperative ``ui.spotlight.set`` patch op instead. */
  annotation?: {
    /** Value of ``data-spotlight-id`` on the element to highlight. */
    target: string;
    /** Short caption shown next to the spotlight bubble. */
    caption: string;
    /** Optional preferred placement. Defaults to ``auto``. */
    placement?: "top" | "bottom" | "left" | "right" | "auto";
    /** Optional padding (px) around the spotlit element. Default 8. */
    padding?: number;
  };
  /** Patch operations. Each key is a fully-qualified op name; the value
   *  shape depends on the op (see types above). Multiple ops in one
   *  frame all apply atomically before the wait begins. */
  patch: FramePatch;
}

/** All supported patch ops. The player switches on these keys; new ops
 *  must be added here AND in applyPatch.ts at the same time. */
export interface FramePatch {
  "chat.append"?: ChatAppendOp;
  "chat.append_token"?: ChatAppendTokenOp;
  "chat.update_tool"?: ChatUpdateToolOp;
  "panel.priority_action.append"?: PriorityActionAppendOp;
  "panel.situations.set"?: SituationsSetOp;
  "panel.situations.scan_start"?: SituationsScanStartOp;
  "panel.situations.classify"?: SituationsClassifyOp;
  "agent.set_active"?: ActiveAgentSetOp;
  "panel.center_tab.set"?: CenterTabSetOp;
  "panel.summary.set"?: SummarySetOp;
  "panel.classify_verdict.set"?: ClassifyVerdictSetOp;
  "panel.detector_config.set"?: DetectorConfigSetOp;
  "panel.detector_config.preview"?: DetectorConfigPreviewOp;
  "panel.audit.set"?: AuditSetOp;
  "dock.thread.set"?: DockThreadSetOp;
  "topology.set"?: TopologySetOp;
  "topology.overlay.set"?: TopologyOverlaySetOp;
  "ui.spotlight.set"?: SpotlightSetOp;
  "ui.spotlight.clear"?: SpotlightClearOp;
  "panel.pin.set"?: PanelPinSetOp;
}

// ── Scenario ─────────────────────────────────────────────────────────────

/** A complete demo scenario file. */
export interface Scenario {
  schema: typeof SCENARIO_SCHEMA;
  id: string;
  label: string;
  description: string;
  frames: Frame[];
  /** Optional kiosk-mode bootstrap state — agent rosters, dock welcome
   *  messages, and canned dock-chat replies. Lets the entire demo
   *  surface be edited from this one file rather than separate .ts
   *  modules. Read once on app mount by kioskBootstrap.ts; replies
   *  are read by chatStore.sendMessage on every dock send. */
  kiosk_bootstrap?: KioskBootstrap;
}

/** Bootstrap state seeded into stores when the kiosk build mounts. */
export interface KioskBootstrap {
  /** Right-hand-column chat agents. The first entry with is_default
   *  becomes the active agent on load. */
  main_agents?: KioskAgentSeed[];
  /** Bottom-dock data-search agents. The first entry becomes the active
   *  dock tab on load. */
  dock_agents?: KioskDockAgentSeed[];
  /** Pre-seeded NER 4.2.3 classification results keyed by situation_id.
   *  Injected into situationStore.classifications with status "ready"
   *  on mount, before the demo player starts. Prevents the SituationCard
   *  useEffect from firing a network request that would 404 in kiosk. */
  classifications?: Record<string, Omit<SituationClassificationEntry, "situation_id">>;
  /** Display names for tool cards. Tool IDs remain the real GridIQ
   *  function names. */
  tool_display_names?: Record<string, string>;
}

/** Minimal agent definition for kiosk mode. */
export interface KioskAgentSeed {
  id: string;
  name: string;
  description: string;
  is_default?: boolean;
}

/** Dock-surface agent definition with a welcome message and canned
 *  reply table for the offline interactive chat. */
export interface KioskDockAgentSeed {
  id: string;
  name: string;
  description: string;
  /** Tool ids surfaced in the dock UI (cosmetic). */
  tools?: string[];
  /** Markdown shown as the assistant's first message in this agent's
   *  dock thread. */
  welcome?: string;
  /** Keyword-match table consulted on every dock send. First entry
   *  whose match (lowercased) appears as a substring of the user
   *  prompt wins; an entry with match === "" is the catch-all. */
  replies?: KioskReplyEntry[];
}

/** One canned-reply rule. */
export interface KioskReplyEntry {
  match: string;
  text: string;
}

/** Runtime guard — verifies an unknown value matches the Scenario shape
 *  and the supported schema version. Throws with a clear message on
 *  mismatch so a typo in a scenario file fails loudly at load time. */
export function assertScenario(value: unknown): asserts value is Scenario {
  if (typeof value !== "object" || value === null) {
    throw new Error("Scenario must be an object");
  }
  const v = value as Record<string, unknown>;
  if (v.schema !== SCENARIO_SCHEMA) {
    throw new Error(
      `Unsupported scenario schema: ${String(v.schema)} (expected ${SCENARIO_SCHEMA})`,
    );
  }
  if (typeof v.id !== "string" || !v.id) throw new Error("Scenario.id required");
  if (typeof v.label !== "string" || !v.label) throw new Error("Scenario.label required");
  if (!Array.isArray(v.frames) || v.frames.length === 0) {
    throw new Error("Scenario.frames must be a non-empty array");
  }
}
