/**
 * PinnedSituationPanel — the body of the centre "Situation" tab.
 *
 * Purpose:
 *   Operator-selected stations are pinned into a sequential list so
 *   their full situation evidence stays front-and-centre while the
 *   left-column Situation Alerts feed continues to scroll / update.
 *
 * Pin paradigm (operator brief 2026-05-25):
 *   - Pin unit is the STATION, not an individual situation. A pinned
 *     entry carries the station code + the situation list snapshot at
 *     pin time.
 *   - Pin triggers:
 *       1. Manual: Pin icon on a station-group accordion header in
 *          SituationAlertsPanel (switches to this tab).
 *       2. Auto: any Investigate action (per-row or station-level)
 *          pins silently in the background; the operator's foreground
 *          remains the chat surface.
 *   - Re-pinning moves the station to the head with a fresh
 *     situations snapshot (latest live enrichment wins).
 *
 * Role in system:
 *   Reads `pinnedStations` from panelStore. When empty, renders an
 *   empty-state instructing the operator to use the pin icon. When
 *   populated, renders a vertical stack of station accordions
 *   mirroring the SituationAlertsPanel layout — first station
 *   expanded, others collapsed (10× expanded cards is heavy).
 *
 * Key collaborators:
 *   - panelStore:       source of `pinnedStations`, owner of
 *                       unpinStation / clearPinnedStations actions.
 *   - SituationCard:    per-situation render surface.
 *   - sessionStore /    investigate handler creates a session,
 *     chatStore /         activates the default agent, and sends the
 *     agentStore:         situation prompt — matches
 *                       SituationAlertsPanel so the two surfaces feel
 *                       like sibling views of the same data.
 *   - topologyStore:    loadStation for the "View topology" footer
 *                       button on each card.
 */

import { useState } from "react";
import { AlertTriangle, ChevronDown, ChevronRight, Pin, X } from "lucide-react";
import { usePanelStore } from "@/stores/panelStore";
import { useSituationStore } from "@/stores/situationStore";
import { useSessionStore } from "@/stores/sessionStore";
import { useChatStore } from "@/stores/chatStore";
import { useAgentStore } from "@/stores/agentStore";
import { useTopologyStore, extractOverlayEquipmentIds } from "@/stores/topologyStore";
import { SituationCard } from "./SituationCard";
import { BUCKET_BADGE, bucketFor, rankFor } from "@/lib/severity";
import { hhmm } from "@/lib/situationRecord";
import type { SituationRecord } from "@/api/situationApi";

export function PinnedSituationPanel() {
  /* Subscribe to the pinned list + store actions. Individual selectors
     keep the component from re-rendering on unrelated panel updates
     (priority actions, disturbance summary, etc.). */
  const pinnedStations = usePanelStore((s) => s.pinnedStations);
  const unpinStation = usePanelStore((s) => s.unpinStation);
  const clearPinnedStations = usePanelStore((s) => s.clearPinnedStations);
  const setCenterTab = usePanelStore((s) => s.setCenterTab);

  /* Per-station accordion open/close. First entry defaults to open
     so the freshest pin reads as a full-detail view on tab switch;
     deeper entries collapse so many pinned stations do not mount
     hundreds of cards at once. Operator can expand any entry. */
  const [openStations, setOpenStations] = useState<Set<string>>(() => {
    return new Set(pinnedStations.length > 0 ? [pinnedStations[0].station] : []);
  });
  const toggleStation = (station: string) => {
    setOpenStations((prev) => {
      const next = new Set(prev);
      if (next.has(station)) next.delete(station);
      else next.add(station);
      return next;
    });
  };

  /* Investigate + topology handlers — mirror SituationAlertsPanel so the
     operator gets identical behaviour regardless of which surface they
     acted from. Duplicated rather than hoisted because the list panel
     and the pinned panel can exist independently in tests and future
     refactors. */
  const buildPrompt = useSituationStore((s) => s.buildInvestigatePrompt);
  const createSession = useSessionStore((s) => s.createSession);
  const sendMessage = useChatStore((s) => s.sendMessage);
  const setActiveAgent = useAgentStore((s) => s.setActiveAgent);
  const loadTopology = useTopologyStore((s) => s.loadStation);

  /* Route through the configured DEFAULT agent so the T1 Grid Captain
     cutover (and any future cutover) takes effect without editing this
     handler. */
  const handleInvestigate = async (sit: SituationRecord) => {
    const session = await createSession();
    if (!session) return;
    const prompt = buildPrompt(sit);
    const agents = useAgentStore.getState().agents;
    const defaultAgentId = agents.find((a) => a.is_default)?.id ?? agents[0]?.id ?? "grid_manager";
    setActiveAgent(defaultAgentId);
    await sendMessage(session.id, prompt, defaultAgentId);
  };

  /* Swap to the Topology tab and overlay the situation's equipment list. */
  const handleViewTopology = (sit: SituationRecord) => {
    const equipmentIds = extractOverlayEquipmentIds(sit.affected_equipment);
    setCenterTab("topology");
    void loadTopology(sit.station, {
      overlay: { equipmentIds, severity: sit.severity },
    });
  };

  /* Empty state — no stations pinned. Instructs the operator rather
     than showing a blank screen. */
  if (pinnedStations.length === 0) {
    return (
      <div
        data-testid="pinned-situation-empty"
        className="h-full flex flex-col items-center justify-center text-center px-6 gap-3 text-text-muted"
      >
        <AlertTriangle className="h-8 w-8 text-text-tertiary" />
        <div className="space-y-1">
          <p className="text-sm font-semibold text-text-secondary">No stations pinned</p>
          <p className="text-xs text-text-muted max-w-xs">
            Click the <Pin className="inline h-3 w-3 align-middle" /> icon on
            any station header in the Alerts list to pin its situations here,
            or use Investigate to auto-pin in the background.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div data-testid="pinned-situation-panel" className="h-full flex flex-col min-h-0">
      {/* Header — pin count + clear-all. Uses the same visual language
          as SituationAlertsPanel's header so the two surfaces feel like
          sibling views of the same data. */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-border bg-neutral-bg2 shrink-0">
        <Pin className="w-4 h-4 text-brand" />
        <h3 className="text-sm font-bold text-foreground">Pinned Stations</h3>
        <span className="text-xs text-text-secondary font-mono font-bold">
          ({pinnedStations.length})
        </span>
        <div className="flex-1" />
        <button
          data-testid="pinned-stations-clear"
          onClick={() => clearPinnedStations()}
          className="flex items-center gap-1 px-2 py-1 text-xs font-semibold rounded bg-neutral-bg3 text-text-secondary border border-border hover:text-text-primary hover:bg-neutral-bg4 transition-colors"
          title="Clear all pinned stations"
        >
          <X className="h-3 w-3" />
          Clear
        </button>
      </div>

      {/* Body — vertical stack of station accordions, newest pin first.
          Mirrors the SituationAlertsPanel layout so the operator's
          mental model is identical across both surfaces. */}
      <div className="flex-1 overflow-y-auto p-2 space-y-1.5 min-h-0">
        {pinnedStations.map((group) => {
          const isOpen = openStations.has(group.station);
          if (group.situations.length === 0) return null;
          /* Worst-severity row + window range — same derivation as the
             alerts panel station-group header. */
          const worst = group.situations.reduce(
            (acc, s) => (rankFor(s.severity) < rankFor(acc.severity) ? s : acc),
            group.situations[0],
          );
          const minStart = group.situations.reduce(
            (acc, s) => (s.window_start < acc ? s.window_start : acc),
            group.situations[0].window_start,
          );
          const maxEnd = group.situations.reduce(
            (acc, s) => (s.window_end > acc ? s.window_end : acc),
            group.situations[0].window_end,
          );
          return (
            <div
              key={group.station}
              data-testid={`pinned-station-group-${group.station}`}
              className="rounded border border-border bg-neutral-bg1 overflow-hidden"
            >
              <div className="flex items-center bg-neutral-bg2 hover:bg-neutral-bg3">
                <button
                  type="button"
                  data-testid={`pinned-station-header-${group.station}`}
                  aria-expanded={isOpen}
                  onClick={() => toggleStation(group.station)}
                  className="flex-1 min-w-0 flex items-center gap-2 px-2 py-1.5 text-left"
                >
                  {isOpen ? (
                    <ChevronDown className="w-3.5 h-3.5 text-text-muted shrink-0" />
                  ) : (
                    <ChevronRight className="w-3.5 h-3.5 text-text-muted shrink-0" />
                  )}
                  <span
                    className={`px-1.5 py-0.5 text-micro font-black tracking-wide rounded ${
                      BUCKET_BADGE[bucketFor(worst.severity)]
                    }`}
                  >
                    {bucketFor(worst.severity)}
                  </span>
                  <span className="text-sm font-bold text-text-primary">{group.station}</span>
                  <span className="text-micro font-mono text-text-muted">
                    {hhmm(minStart)} → {hhmm(maxEnd)}
                  </span>
                  <span className="ml-auto text-micro text-text-muted">
                    {group.situations.length} situation{group.situations.length === 1 ? "" : "s"}
                  </span>
                </button>
                {/* Unpin × — single station eviction. stopPropagation so
                    the click does not also toggle the accordion. */}
                <button
                  type="button"
                  data-testid={`unpin-station-${group.station}`}
                  aria-label={`Unpin ${group.station}`}
                  title={`Unpin ${group.station}`}
                  onClick={(e) => {
                    e.stopPropagation();
                    unpinStation(group.station);
                  }}
                  className="shrink-0 px-2 py-1.5 text-text-muted hover:text-text-primary hover:bg-neutral-bg4 border-l border-border/50"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              {isOpen && (
                <div className="divide-y divide-border/40">
                  {group.situations.map((sit) => (
                    <div key={sit.situation_id} className="px-1 py-1">
                      <SituationCard
                        situation={sit}
                        onInvestigate={handleInvestigate}
                        onViewTopology={handleViewTopology}
                        defaultExpanded
                      />
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
